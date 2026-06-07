# Full Ten-Round Session Plan Brief

Full plan: `context/changes/full-ten-round-session/plan.md`

## What & Why

S-04 turns the current S-03 one-round party flow into the MVP's complete 10-round session. The app already proves host-owned Spotify playback, player answering, scoring, locking, and HTTP polling for one round. This slice adds host-paced next-round progression, server-side timeout locking, final session completion, and dedicated final-results pages with winner/co-winner display plus full ranking.

## Starting Point

- S-03 supports one playable round and intentionally stops before the 10-round loop.
- `GameSession` already has `FINISHED` and `finished_at`.
- `Round` has `index`, `deadline_at`, `locked_at`, `paused_at`, `answer_options`, and a DB uniqueness constraint on `(session, track)`.
- `session_start_round` is lobby-only and `session_restart` currently recreates `index=1`.
- Polling uses `GET /api/sessions/<code>/state` with semantic ETags and client-derived countdowns.
- Each seeded catalog set currently has 7 tracks; S-04 needs at least 10.

## Desired End State

A host can run rounds 1-10 from the browser. After each round locks, players see results while the host explicitly starts the next round. Deadlines lock on the next state/control request, late answers are rejected with 0 points, and no missing-answer rows are created. After round 10 locks, the session becomes `finished`, clients redirect to dedicated host/player results URLs, and final pages show co-winners on top-score ties plus the full score ranking.

## Key Decisions Made

| Decision | Source |
| --- | --- |
| Host explicitly starts the next round; no automatic timed autoplay between rounds. | User planning answer |
| Locked result state remains visible until host advances. | User planning answer |
| Expired rounds lock server-side on the next poll/control request; no scheduler. | User planning answer |
| Late or lagging players do not block; late answers are rejected and score 0. | User planning answer |
| Pause, resume, skip, and restart stay active-round controls only. | User planning answer |
| Restart applies only to the unlocked active round and must preserve the current round index. | User planning answer + code review |
| Use dedicated final-results URLs. | User planning answer |
| Final UI shows winner/co-winners plus full ranking. | User planning answer |
| Top-score ties produce co-winners. | User planning answer |
| Missing answers do not create explicit `Answer` rows. | User planning answer |
| Expand every seeded set to at least 10 tracks. | User planning answer + S-04 requirement |
| Allow repeat fallback if Spotify rejects all unused tracks. | User planning answer |
| Drop DB `(session, track)` uniqueness and enforce no-repeat-first in app logic/tests. | User follow-up decision |
| Deployed smoke is optional; local 10-round smoke is required before marking done. | User planning answer |

## Scope

In scope:

- Expand seed catalog capacity.
- Remove `unique_track_per_session` via migration.
- Add no-repeat-first track selection with repeat fallback.
- Add host next-round API mutation.
- Add request-driven timeout locking and round-10 finish transition.
- Fix restart for multi-round sessions.
- Add host/player final-results views, routes, templates, and polling redirects.
- Add full-session regression tests and S-04 smoke handoff.

Out of scope:

- WebSockets, Channels, SSE, or a scheduler.
- Per-round score history beyond locked round result state.
- Rejoin recovery, global history, or profiles.
- Spotify token refresh resilience beyond existing helpers.
- Durable Fly storage or production session persistence across deploys.

## Architecture / Approach

Keep the existing Django + HTTP polling architecture. Add small lifecycle helpers in `game/views.py` that are idempotent and request-driven: lock expired active rounds, decide whether round 10 should finish the session, and validate whether the host can advance. Continue to keep Spotify API/playback calls outside `transaction.atomic()` blocks, then commit short DB transitions afterward.

Track selection should prefer unused playable tracks and only fall back to repeats after all unused candidates fail Spotify validation. Because that fallback conflicts with the current DB constraint, the plan includes a migration to remove `(session, track)` uniqueness while keeping `(session, index)` uniqueness.

## Phases At A Glance

1. Catalog Capacity And Round Invariants: expand fixtures, remove track uniqueness, test no-repeat-first plus fallback.
2. Host-Paced Round Lifecycle: add timeout lock, next-round mutation, finish-session transition, and restart fixes.
3. Final Results Browser Flow: add final routes/templates and update JS/templates for round 1-10 plus finished redirects.
4. Regression Coverage And Smoke Handoff: add full-session tests, catalog tests, smoke docs, and readiness checks.

## Prerequisites / Estimated Effort

- Expected complexity: medium-high for this codebase because it crosses schema, seed data, host controls, polling, templates, and manual Spotify smoke.
- Run local commands with `DJANGO_DEBUG=True` unless intentionally using production-style checks.
- Expect a migration for the removed round track uniqueness constraint.
- Manual verification needs one host browser plus at least one separate player browser/profile.

## Open Risks & Assumptions

- Spotify playability can vary by account/market; tests should mock this, while manual smoke proves the real path.
- Starting playback before DB commit preserves the current S-03 failure behavior, but duplicate/stale host requests must still be guarded after playback and before creating the next round.
- Production SQLite remains image-baked and non-durable; deploys during active games can wipe runtime sessions.
- Fixture expansion requires valid Spotify track IDs; bad IDs can make the normal path look broken even if lifecycle code is correct.

## Success Criteria Summary

- Every seeded music set has at least 10 tracks.
- Full targeted S-04 tests and full `uv run pytest` pass.
- `manage.py check`, migration drift check, and `collectstatic` pass.
- Local two-browser smoke completes all 10 rounds, including timeout/late-answer behavior.
- Final results show co-winners on ties and the full player ranking.
- Roadmap status changes only after implementation and verification, not during planning.
