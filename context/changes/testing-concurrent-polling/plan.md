# Testing Concurrent Polling Implementation Plan

## Overview

Add a test that proves `session_state` polling is lifecycle-idempotent under concurrent requests: an expired round is locked exactly once even when two pollers race to apply the lifecycle mutation.

## Current State Analysis

The `session_state` view calls `_apply_session_lifecycle_for_code(code)` on every poll. That function opens a `transaction.atomic()` block with a `SELECT FOR UPDATE` on the session row, then calls `_apply_session_lifecycle` which checks `_round_is_expired(current_round, now=now)` — which returns `True` only when `round_obj.locked_at is None`. If both callers see `locked_at is None` simultaneously, the idempotency guard is that second caller's read sees the row already updated after the first commits.

**Nine existing `session_state` tests** cover 404, lobby/round/finished snapshots, ETag 304 caching, lifecycle-on-poll (expired round → lock, round 10 → finish), and `last_activity_at` refresh. None covers the concurrent-poll safety property.

**SQLite gap**: `select_for_update()` is a no-op on SQLite (Django silently skips it). In production (PostgreSQL) the row lock serializes concurrent callers at the DB level. The monkeypatch approach below tests the code-path invariant — idempotency via the `locked_at is None` guard — which holds regardless of the locking backend.

### Key Discoveries

- `game/views.py:1052` — `session_state` view; calls `_apply_session_lifecycle_for_code` before reading state
- `game/views.py` (`_apply_session_lifecycle`) — checks `_round_is_expired` which requires `round_obj.locked_at is None`; sets `current_round.locked_at = now` then calls `round.save(update_fields=["locked_at"])`
- `game/tests.py:3184` — `test_player_join_handles_concurrent_duplicate_name_inline` — canonical monkeypatch race-simulation pattern in this codebase
- `game/tests.py:2524` — `test_session_state_locks_expired_round_on_poll` — the sequential counterpart; new test extends this scenario to the concurrent case

## Desired End State

One new test in `game/tests.py` immediately after the existing `session_state` lifecycle tests:

- Monkeypatches `game.views._apply_session_lifecycle_for_code` to call the original implementation twice in a row (simulating two concurrent pollers both entering the function before either has committed)
- Instruments `Round.save` to count calls where `"locked_at"` is in `update_fields`
- Asserts the count is `1` — the round is locked exactly once
- Asserts both the DB state (`round.locked_at is not None`) and the response phase (`"locked"`) are correct

Verification: `uv run pytest game/tests.py -k concurrent` passes; no existing tests regress.

## What We're NOT Doing

- Not testing `last_activity_at` concurrent writes (write race is benign — both callers write `timezone.now()` independently)
- Not testing ETag coherence under simultaneous first-polls
- Not using real threads or `@pytest.mark.django_db(transaction=True)`
- Not adding a PostgreSQL-only test variant or a skip marker
- Not testing the round-10 → session-finish path concurrently (covered by extending the pattern to that scenario is out of scope here)

## Implementation Approach

Single test function appended to `game/tests.py` after `test_session_state_finishes_session_when_round_ten_expires` (line ~2580). Uses the monkeypatch-based inline race simulation established by `test_player_join_handles_concurrent_duplicate_name_inline`.

## Phase 1: Add concurrent polling test

### Overview

Add one test function to `game/tests.py` that proves lifecycle idempotency under a simulated concurrent expired-round poll race.

### Changes Required

#### 1. New test in `game/tests.py`

**File**: `game/tests.py`

**Intent**: Insert a new `@pytest.mark.django_db` test function after `test_session_state_finishes_session_when_round_ten_expires`. The test uses monkeypatch to (a) replace `game.views._apply_session_lifecycle_for_code` with a wrapper that calls the original twice in sequence — simulating two concurrent callers both entering before either commits — and (b) instrument `Round.save` to count calls where `"locked_at"` is in `update_fields`. It then fires one GET to `/api/sessions/<code>/state` and asserts the count is exactly 1.

**Contract**: No new imports needed; `monkeypatch` is a built-in pytest fixture, and `game_views`, `Round`, `timezone`, `timedelta`, `reverse` are all already imported at the top of `game/tests.py`. The function signature is `test_concurrent_expire_polls_lock_round_exactly_once(client, session, track, monkeypatch)`.

The `double_lifecycle` wrapper replaces `game_views._apply_session_lifecycle_for_code`:

```python
original = game_views._apply_session_lifecycle_for_code

def double_lifecycle(code):
    # Simulate two concurrent pollers entering the lifecycle function before either
    # commits. On PostgreSQL the SELECT FOR UPDATE row lock serializes them; this
    # tests the secondary idempotency guard: _round_is_expired returns False once
    # locked_at is set, so the second call is a no-op.
    # NOTE: select_for_update is silently ignored on SQLite.
    original(code)
    original(code)

monkeypatch.setattr(game_views, "_apply_session_lifecycle_for_code", double_lifecycle)
```

The `Round.save` instrumentation counts calls where `"locked_at" in (update_fields or [])`.

### Success Criteria

#### Automated Verification

- New test passes: `uv run pytest game/tests.py -k concurrent`
- No regressions: `uv run pytest game/tests.py`

#### Manual Verification

- Read the test and confirm the `double_lifecycle` wrapper matches the real concurrent-entry shape described above
- Confirm the inline SQLite gap comment is present and accurate

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests

- The new test IS the unit test for this change

### Manual Testing Steps

1. Run `uv run pytest game/tests.py -k concurrent -v` — confirm 1 test collected and passes
2. Run `uv run pytest game/tests.py` — confirm full suite is green
3. Read the test body and verify the SQLite gap comment is present

## References

- `game/views.py` `session_state` view and `_apply_session_lifecycle_for_code`
- `game/tests.py:3184` — `test_player_join_handles_concurrent_duplicate_name_inline` (canonical monkeypatch race pattern)
- `game/tests.py:2524` — `test_session_state_locks_expired_round_on_poll` (sequential counterpart)

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles.

### Phase 1: Add concurrent polling test

#### Automated

- [x] 1.1 New test passes: `uv run pytest game/tests.py -k concurrent`
- [x] 1.2 No regressions: `uv run pytest game/tests.py`

#### Manual

- [ ] 1.3 `double_lifecycle` wrapper matches the real concurrent-entry shape described above
- [ ] 1.4 Inline SQLite gap comment is present and accurate
