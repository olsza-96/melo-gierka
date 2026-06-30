<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Session State Polling Endpoint (F-04)

- **Plan**: context/changes/session-state-polling/plan.md
- **Scope**: All 3 phases
- **Date**: 2026-06-04
- **Verdict**: APPROVED
- **Findings**: 0 critical · 0 warnings · 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | WARNING |
| Safety & Quality | PASS |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Summary

- Diff matches the plan's file list exactly (`game/{urls,views,state,tests}.py`, `melo_gierka/urls.py`, change README). No unplanned source files.
- Routing decisions from plan & change.md honored: canonical `/api/sessions/<code>/state`, no `/api/room` alias, no DRF, no write endpoints, no answer options / lock-state.
- Activity-refresh-on-304 contract verified by tests; ETag excludes `server_now` and `last_activity_at` (correct — otherwise 304 would never trigger).
- Re-ran automated success criteria: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "state or etag"` → 8 passed; `DJANGO_DEBUG=True uv run python manage.py check` → 0 issues.
- `context/foundation/lessons.md` (Fly health-check / `SECURE_SSL_REDIRECT`) is not relevant to this slice — endpoint sits under public `/api/`, not the health-check path.

Commits in scope: `19cb59f` (p1), `9d08c6a` (p2), `63af875` (p3), `3cca1b9` (progress sha).

## Findings

### F1 — Player ordering by `-score` is an undocumented scope decision

- **Severity**: ℹ️ OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: game/state.py:17, game/tests.py:240
- **Detail**: The plan says "ordered players (`name`, `score`, `joined_at`)" without specifying the order key. Implementation orders by `-score, joined_at` (scoreboard ordering) and the lobby test locks that order. PRD assigns the per-round scoreboard to slice S-05 (`per-round-scoreboard`, FR-012). In the lobby phase this ordering is effectively `joined_at` (no scores yet), but in the finished phase it doubles as a leaderboard, slightly preempting S-05's framing. Not harmful — just an undocumented contract decision the next slice will inherit.
- **Fix**: Note the ordering choice in `context/changes/session-state-polling/README.md` (one line under "Response shape: players") so S-02 / S-05 inherit a documented contract rather than reverse-engineering it from a test.
- **Decision**: PENDING
