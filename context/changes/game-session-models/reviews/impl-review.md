<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Game Session Models + Ephemeral Cleanup (full plan)

- **Plan**: `context/changes/game-session-models/plan.md`
- **Scope**: Full plan (Phases 1, 2, 3) — Phase 2 separately reviewed in `impl-review-phase-2.md`
- **Date**: 2026-06-02
- **Verdict**: APPROVED (1 warning fixed, 2 observations skipped, 1 observation fixed)
- **Findings**: 0 critical | 1 warning | 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING (F1 fixed; F3 fixed; F2 skipped) |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS — 11/11 automated tests green |

## Findings (Phase 1, Phase 3, cross-phase)

Phase 2 findings (F1–F6) are tracked separately in `impl-review-phase-2.md` and not repeated here.

### F1 — test_cleanup_preserves_fresh_sessions implicitly couples to default --idle-hours

- **Severity**: WARNING
- **Impact**: LOW
- **Dimension**: Pattern Consistency (test convention)
- **Location**: game/tests.py:182-189
- **Detail**: Test relied on the `last_activity_at` model default. Plan explicitly chose "set last_activity_at explicitly on creation, no time mocking" as the convention.
- **Fix**: Pass `last_activity_at=timezone.now()` explicitly + a "within idle window" comment.
- **Decision**: FIXED

### F2 — cleanup_sessions materializes full code list before delete

- **Severity**: OBSERVATION
- **Impact**: LOW
- **Dimension**: Safety & Quality (performance)
- **Location**: game/management/commands/cleanup_sessions.py:31
- **Detail**: Logged code list grows unbounded if cleanup runs over a backlog. Zero impact at MVP scale.
- **Fix**: Cap log sample to codes[:20] + "(+N more)" — defer until observed.
- **Decision**: SKIPPED (defer until cleanup is observed running over a real backlog)

### F3 — --idle-hours accepts 0 / negative without guard

- **Severity**: OBSERVATION
- **Impact**: LOW
- **Dimension**: Safety & Quality (data safety)
- **Location**: game/management/commands/cleanup_sessions.py:23
- **Detail**: `--idle-hours 0` would delete every session.
- **Fix**: Validate `idle_hours > 0` in handle(); raise CommandError on invalid input.
- **Decision**: FIXED

### F4 — pyproject.toml lacks [tool.coverage.report] exclusions

- **Severity**: OBSERVATION
- **Impact**: LOW
- **Dimension**: Pattern Consistency
- **Location**: pyproject.toml:28-29
- **Detail**: No `fail_under` / no exclusions for migrations/ or admin.py. Cosmetic until CI gates on coverage.
- **Fix**: Defer until CI integration of pytest lands.
- **Decision**: SKIPPED (out of scope per plan)
