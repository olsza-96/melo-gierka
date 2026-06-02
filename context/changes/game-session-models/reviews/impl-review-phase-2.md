<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Game Session Models + Ephemeral Cleanup

- **Plan**: `context/changes/game-session-models/plan.md`
- **Scope**: Phase 2 of 3
- **Date**: 2026-06-02
- **Verdict**: NEEDS ATTENTION → all critical/warning findings triaged & fixed
- **Findings**: 1 critical | 3 warnings | 2 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING (fixed) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | FAIL (fixed) |

## Findings

### F1 — Codegen retry test doesn't actually assert the retry

- **Severity**: CRITICAL
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria (test validity)
- **Location**: game/tests.py:101-114
- **Detail**: Test seeds code "0001", monkeypatches `secrets.randbelow` to return 1 then 2, asserts return "0002". It would also pass if the function never retried — never observes call count.
- **Fix**: Wrap randbelow with a call counter; assert `calls == 2`.
- **Decision**: FIXED

### F2 — Codegen TOCTOU undocumented; callers may not handle IntegrityError

- **Severity**: WARNING
- **Impact**: MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality (reliability)
- **Location**: game/codegen.py:5-13
- **Detail**: `filter().exists()` + caller `create()` is a TOCTOU race. At MVP scale rare but the function silently advertises a stronger guarantee than it provides.
- **Fix A ⭐ Recommended**: Document TOCTOU in docstring; caller wraps with try/except IntegrityError.
  - Strength: Honest about MVP constraint; forces S-01 author to handle the race.
  - Tradeoff: Burden on every caller.
  - Confidence: HIGH — plan explicitly accepts MVP-scale ergonomics.
- **Fix B**: Add `create_session_with_unique_code(**kwargs)` helper that retries on IntegrityError.
  - Strength: Eliminates the race; caller has a clean API.
  - Tradeoff: More coupling; bigger Phase 2 footprint than planned.
  - Confidence: MEDIUM.
- **Decision**: FIXED via Fix A

### F3 — Admin list views N+1 on FK columns

- **Severity**: WARNING
- **Impact**: LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality (performance)
- **Location**: game/admin.py:8 / :15 / :21
- **Detail**: `list_display` references FK fields (music_set, session, track). Each changelist row issues an extra SELECT.
- **Fix**: Add `list_select_related` on all three admin classes.
- **Decision**: FIXED

### F4 — Exhaustion test name misleading; doesn't assert message

- **Severity**: WARNING
- **Impact**: LOW
- **Dimension**: Pattern Consistency (test naming)
- **Location**: game/tests.py:118-126
- **Detail**: Test name says `when_exhausted` but scenario is `every attempt collides with the seeded row`. Assert doesn't verify `max_attempts=3` in the message.
- **Fix**: Rename to `test_generate_session_code_raises_when_all_attempts_collide`; use `pytest.raises(RuntimeError, match=r"3 attempts")`.
- **Decision**: FIXED

### F5 — Redundant db_index=True on unique code field

- **Severity**: OBSERVATION
- **Impact**: LOW
- **Dimension**: Safety & Quality (performance)
- **Location**: game/models.py:11
- **Detail**: `unique=True` already creates a unique B-tree index. `db_index=True` is a no-op.
- **Fix**: Drop db_index=True; regenerate migration.
- **Decision**: SKIPPED (loyal to plan; harmless)

### F6 — Unused timedelta import in tests

- **Severity**: OBSERVATION
- **Impact**: LOW
- **Dimension**: Pattern Consistency
- **Location**: game/tests.py:1
- **Detail**: `from datetime import timedelta` imported but never used (prepared for Phase 3 cleanup tests).
- **Fix**: Remove now; re-add in Phase 3.
- **Decision**: SKIPPED (Phase 3 will need it shortly)
