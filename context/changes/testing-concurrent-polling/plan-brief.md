# Testing Concurrent Polling — Plan Brief

> Full plan: `context/changes/testing-concurrent-polling/plan.md`

## What & Why

Add a test proving that the `session_state` polling endpoint is lifecycle-idempotent under concurrent requests. When two players poll simultaneously and both find an expired round, the round should be locked exactly once — not twice. The risk is subtle because `select_for_update` is the production guard, but the test DB is SQLite where that guard is silently a no-op.

## Starting Point

Nine `session_state` tests already exist in `game/tests.py` and cover the sequential lifecycle-on-poll path (`test_session_state_locks_expired_round_on_poll`). None simulate two callers racing into `_apply_session_lifecycle_for_code` simultaneously.

## Desired End State

One new test in `game/tests.py` that uses a monkeypatch wrapper to call `_apply_session_lifecycle_for_code` twice in a row (simulating two concurrent pollers), instruments `Round.save` to count `locked_at` writes, and asserts the count is exactly 1.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
|---|---|---|---|
| Which concurrent scenario to cover | Lifecycle idempotency (expire-on-poll race) | Core `select_for_update` contract; highest blast radius if wrong | Plan |
| Race simulation strategy | Monkeypatch-based inline (double-call wrapper) | Deterministic, single-threaded; matches existing `test_player_join_handles_concurrent_duplicate_name_inline` pattern | Plan |
| SQLite gap handling | Document inline, don't skip | The monkeypatch proves the idempotency invariant regardless of backend; comment explains the PostgreSQL guard | Plan |
| Double-fire assertion shape | `Round.save` call count where `"locked_at" in update_fields` | Precise — proves the mutation fires once, not just that the final state looks right | Plan |
| Test location | Append to `game/tests.py` after existing session_state lifecycle tests | Zero new files; same import set | Plan |

## Scope

**In scope:** One test covering the expired-round lifecycle-idempotency race

**Out of scope:** `last_activity_at` concurrent writes, ETag coherence under simultaneous first-polls, round-10 finish race, real-threading tests, PostgreSQL-only skip markers

## Architecture / Approach

Monkeypatch `game.views._apply_session_lifecycle_for_code` with a wrapper that calls the original twice. Instrument `Round.save` with a call counter. Fire one `GET /api/sessions/<code>/state`. Assert `locked_at` write count == 1 and response phase == `"locked"`.

## Phases at a Glance

| Phase | What it delivers | Key risk |
|---|---|---|
| 1. Add concurrent polling test | One new test in `game/tests.py` | Monkeypatch targeting the wrong attribute path (e.g. `game.state` vs `game.views`) |

**Prerequisites:** Existing test suite passes  
**Estimated effort:** ~1 session, 1 phase

## Open Risks & Assumptions

- The test proves the idempotency invariant on SQLite; it does not prove the PostgreSQL row-lock serialization in CI — that would require a PostgreSQL test database
- If `_apply_session_lifecycle_for_code` is ever inlined into `session_state` directly, the monkeypatch target path would need updating

## Success Criteria (Summary)

- `uv run pytest game/tests.py -k concurrent` collects 1 test and it passes
- Full `game/tests.py` suite remains green
- Inline SQLite gap comment is present and accurate
