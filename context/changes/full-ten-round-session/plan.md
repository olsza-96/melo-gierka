# Full Ten-Round Session Implementation Plan

## Overview

This plan implements S-04: the north-star gameplay loop where a host can run a complete 10-round session from the existing lobby through final results. It builds directly on S-03's one-round flow: Spotify browser playback stays host-owned, the canonical session-state endpoint remains the shared polling surface, and scores remain server-authoritative.

The key change is lifecycle orchestration. A locked round no longer means the game is over; the host can review the result state, explicitly start the next round, and after round 10 every browser lands on final results with winner/co-winner treatment plus the full ranking.

## Current State Analysis

S-03 is implemented and reviewed. The app can create one playable round, start Spotify playback, accept one answer per player, score correct answers with time weighting, lock early when everyone answers, and expose locked result state through polling. Host controls already cover pause, resume, skip, and restart for the one-round slice.

What is missing is the full session lifecycle. `session_start_round` only accepts sessions in `lobby`, so it cannot start round 2 after round 1 locks. `session_restart` currently creates a replacement round with `index=1`, which is not compatible with later rounds. The state endpoint can serialize a `finished` session, but there is no final-results route/template, no client transition to final results, and no automatic transition from locked round 10 to `GameSession.Status.FINISHED`. The seed catalog also has only 7 tracks per set, while S-04 needs 10 rounds.

## Desired End State

After this plan lands, every seeded music set can support a 10-round session. The host starts round 1 from the lobby, then starts each later round from the locked result state. Normal selection avoids repeating tracks in a session; if Spotify rejects all unused tracks for the host account, the app can fall back to a playable repeat rather than strand the party before final results.

Round deadlines are server-authoritative: active rounds lock on the next state/control request after `deadline_at`, late answers are rejected, and no slow player can hold up the room. When round 10 locks, the session is marked `finished`, `finished_at` is set, polling clients transition to dedicated final-results URLs, and final screens show co-winners when top scores tie plus the score-ordered full ranking.

### Key Discoveries:

- `GameSession` already has `FINISHED` and `finished_at`, so S-04 should use the existing terminal state instead of adding a parallel game-over flag (`game/models.py`).
- `Round` currently enforces both unique index and unique track per session; the unique index remains load-bearing, but the unique track constraint must be relaxed to allow the selected repeat fallback (`game/models.py`).
- `_choose_round_track()` already excludes used tracks before choosing candidates, which is the right normal-path behavior to keep and extend with fallback logic (`game/views.py`).
- The state endpoint computes ETags from the semantic snapshot and adds `server_now` only after the ETag; S-04 must keep countdowns client-derived from stable timestamps (`game/state.py`, `game/views.py`).
- `round.js` already protects against stale poll responses and applies authoritative control snapshots, which is the pattern to reuse for next-round and finished-session transitions (`game/static/game/round.js`).
- The deployment DB is SQLite baked into the image with seed data loaded at build time; fixture changes are deployment-significant and must be verified with `seed_catalog` and `collectstatic` (`Dockerfile`, `context/deployment/deploy-plan.md`).

## What We're NOT Doing

- No WebSockets, Channels, SSE, background scheduler, or client-held game clock.
- No per-round scoreboard/history beyond the existing locked round result state and the final ranking.
- No rejoin-with-score recovery; a rejoined player is still a new player with 0 points per the PRD.
- No Spotify token refresh automation; S-06 owns multi-session evening resilience.
- No persisted history after cleanup/deploy; sessions remain ephemeral.
- No exact timer worker that locks rounds at the millisecond deadline.
- No host recovery if the host closes the tab mid-game.

## Implementation Approach

Keep the existing session pages as the main browser surfaces during play, but add dedicated final-results URLs for the terminal state. Backend lifecycle changes should center around a small set of server helpers: lock expired rounds idempotently, determine whether a locked round should finish the session, and start the next host-paced round using the existing Spotify playback readiness path.

The normal track rule remains no repeats. Because the user chose a repeat fallback when all unused tracks are rejected by Spotify, S-04 will drop the hard `(session, track)` uniqueness constraint and enforce no-repeat-first selection in tested application logic. This is a deliberate tradeoff: fairness remains the normal path, but party continuity wins in rare catalog/playability failures.

## Critical Implementation Details

### Timing & Lifecycle

State polling becomes a lifecycle participant because there is no background scheduler. Before serializing a playing session, the server should lock an expired active round if it is past `deadline_at` and not paused. If that expired round is round 10, the same idempotent lifecycle helper should mark the session finished before the snapshot is returned.

### State Sequencing

Starting the next round must preserve the S-03 Spotify-outside-transaction pattern to avoid SQLite lock issues. Re-check session and current-round state after playback preflight/start and before committing the new round, because a stale host click must not create an extra round after another request already advanced or finished the session.

### Restart Semantics

Restart is only available for an unlocked active round. It must replace the current round with the same index, not `index=1`, and it must roll back any points awarded by answers on that active round before deleting those answers. Locked historical rounds are not restartable in S-04.

### Deferred Follow-Up: Duplicate Answer Option Artists

Manual testing showed that a round can render the same artist name more than once in the four answer options. Do not fix this inside Phase 2; capture it for a later selection-quality pass. The eventual fix should make `_build_answer_options()` return distinct artist labels whenever the music set has enough distinct artists, and should add a regression test that fails when duplicate option text is shown for a round.

## Phase 1: Catalog Capacity And Round Invariants

### Overview

Make the data and model constraints compatible with a full 10-round session before adding lifecycle behavior. This phase expands seed data, relaxes the hard unique-track DB constraint, and pins the selection invariants in tests.

### Changes Required:

#### 1. Seed catalog expansion

**File**: `catalog/fixtures/initial.json`

**Intent**: Ensure every host-selectable music set can complete S-04's 10 no-repeat rounds in the normal path.

**Contract**: Each of the 5 seeded `MusicSet` rows has at least 10 associated `Track` rows with distinct artists and usable `duration_ms`. Existing primary keys may remain stable; new tracks use new fixture primary keys and valid Spotify track IDs.

#### 2. Catalog seed command verification

**File**: `catalog/management/commands/seed_catalog.py`

**Intent**: Keep the deployment build path compatible with the expanded fixture.

**Contract**: The existing `loaddata initial.json` seed flow continues to work without custom migration logic or runtime user input.

#### 3. Round uniqueness migration

**File**: `game/models.py`

**Intent**: Relax the absolute no-repeat database rule so S-04 can use the chosen repeat fallback when all unused tracks are rejected by Spotify.

**Contract**: Keep the unique `(session, index)` constraint. Remove the unique `(session, track)` constraint from the model metadata and rely on tested selection logic for no-repeat-first behavior.

**File**: `game/migrations/*.py`

**Intent**: Apply the model constraint change cleanly.

**Contract**: Add a migration that removes `unique_track_per_session`. No data backfill is required because existing sessions are ephemeral.

#### 4. Round selection tests

**File**: `game/tests.py`

**Intent**: Replace the removed DB constraint with explicit behavioral coverage.

**Contract**: Add or update tests proving normal round selection excludes already used tracks, allows a repeated track only through the fallback path, and still fails clearly when no playable track can be found at all.

### Success Criteria:

#### Automated Verification:

- Expanded fixture loads cleanly: `DJANGO_DEBUG=True uv run python manage.py seed_catalog`.
- Migration drift is clean after the constraint change: `DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`.
- Round selection tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "round_unique or choose_round_track or repeat_fallback"`.
- Django configuration remains valid: `DJANGO_DEBUG=True uv run python manage.py check`.

#### Manual Verification:

- In Django shell, each seeded music set reports at least 10 tracks.
- Spot-check the host create-session form still lists all 5 sets after reseeding.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets; the corresponding `- [ ]` checkboxes live in the `## Progress` section.

---

## Phase 2: Host-Paced Round Lifecycle

### Overview

Add the server lifecycle needed to move from one locked round to the next, lock timed-out rounds through normal requests, and finish the session after round 10.

### Changes Required:

#### 1. Lifecycle constants and helpers

**File**: `game/views.py`

**Intent**: Make the 10-round limit and transition rules explicit instead of scattering round-count checks across view functions.

**Contract**: Introduce a single round-count constant for S-04, plus helper functions that can answer: current round, active vs locked, expired active round, can start next round, and should finish after round 10. Helpers should be idempotent so repeated polling or double-clicked controls do not create duplicate transitions.

#### 2. Expired-round locking

**File**: `game/views.py`

**Intent**: Close active rounds when their deadline has passed even if no player submits a late answer.

**Contract**: Before returning session state and before host controls evaluate the current round, lock an unpaused active round whose `deadline_at <= timezone.now()`. Missing answers remain absent and score 0. If the locked round index is 10, transition the session to `finished` and set `finished_at` in the same transaction.

**File**: `game/state.py`

**Intent**: Keep the snapshot contract aligned with the lifecycle helper.

**Contract**: A finished session snapshot exposes final players and `finished_at`; it should not make clients continue treating the last locked round as an active round surface.

#### 3. Next-round host mutation

**File**: `game/views.py`

**Intent**: Let the host explicitly start round 2 through round 10 from the locked result state.

**Contract**: Add a host-only mutation that requires session ownership, `PLAYING` status, a locked latest round, and latest round index below 10. It verifies playback readiness, builds a no-repeat-first candidate with repeat fallback, starts Spotify playback using the current host device pattern, then creates `Round(index=latest.index + 1)` and returns a redirect or control payload for the existing host session page.

**File**: `game/api_urls.py`

**Intent**: Register the next-round route beside existing host control endpoints.

**Contract**: Use the existing session-code route style, for example `sessions/<str:code>/next-round`, and keep it host-owned.

#### 4. Existing start/restart guard fixes

**File**: `game/views.py`

**Intent**: Keep S-03 controls correct once multiple rounds exist.

**Contract**: `session_start_round` remains lobby-only for round 1. `session_restart` applies only to an unlocked active round, reuses the current round index, clears that round's answers, rolls back any points awarded by those answers, and refuses locked or finished sessions.

### Success Criteria:

#### Automated Verification:

- Next-round lifecycle tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "next_round or full_session or finish_session"`.
- Timeout-lock tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "deadline or timeout or late_answer"`.
- Restart regression tests pass for non-first active rounds: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "restart"`.
- Existing S-03 host-control tests still pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or pause or resume or skip or restart"`.

#### Manual Verification:

- From a locked round 1 result state, the host can start round 2 and both host/player browsers move to the new round.
- A timed-out round with unanswered players locks on the next poll/control request and missing players receive 0 points.
- Restarting active round 2 replaces round 2, not round 1, and does not corrupt scores from round 1.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets; the corresponding `- [ ]` checkboxes live in the `## Progress` section.

---

## Phase 3: Final Results Browser Flow

### Overview

Add the host/player final-results experience and the client-side transitions that take browsers from a finished session snapshot to dedicated results URLs.

### Changes Required:

#### 1. Final results views and routes

**File**: `game/views.py`

**Intent**: Provide dedicated final results pages for both roles while preserving the existing ownership/binding guards.

**Contract**: Add host final-results and player final-results views. The host view requires the same host session ownership as the host lobby. The player view requires the same bound-player browser session as the player lobby. Both views require `GameSession.Status.FINISHED`; otherwise they redirect to the canonical session page for the current state.

**File**: `game/urls.py`

**Intent**: Expose role-specific final-results URLs.

**Contract**: Add routes such as `host/sessions/<str:code>/results` and `player/sessions/<str:code>/results` without breaking existing route names.

#### 2. Final results templates

**File**: `game/templates/game/host_results.html`

**Intent**: Show the host the finished game state and enough context to close the party loop.

**Contract**: Render the session code, winner or co-winners, and full score-ordered ranking. Do not include controls for starting an 11th round.

**File**: `game/templates/game/player_results.html`

**Intent**: Show each player the same final ranking with their own identity still visible.

**Contract**: Render winner or co-winners, full ranking, and a player-specific marker for the bound player. No login or rejoin behavior is introduced.

#### 3. Round and lobby client transitions

**File**: `game/static/game/round.js`

**Intent**: Send connected round pages to final results when the shared snapshot says the session is finished.

**Contract**: If polling returns `status === "finished"`, redirect to a data-provided results URL or the template's configured result URL. Continue to avoid ticking fields in the snapshot and preserve ETag behavior.

**File**: `game/static/game/lobby.js`

**Intent**: Keep any stale lobby page from getting stranded if a browser returns after the session is already finished.

**Contract**: If polling sees `finished`, redirect to the appropriate results URL instead of rendering lobby roster forever.

#### 4. Template copy and control state updates

**File**: `game/templates/game/host_lobby.html`

**Intent**: Keep round-1-only copy limited to the true lobby start state.

**Contract**: Existing round-1 copy may remain on the lobby start button, but any shared status used after round 1 must be dynamic.

**File**: `game/templates/game/host_round.html`

**Intent**: Make the host round screen work for round 1 through round 10.

**Contract**: Replace hard-coded visible `Round 1` status with `current_round.index`. Add a host-only Next round action in locked result state when the session has not reached round 10. Hide next-round controls after round 10 or when the session is finished.

**File**: `game/templates/game/player_round.html`

**Intent**: Keep player round copy and controls correct across all 10 rounds.

**Contract**: No next-round control for players; locked result state waits for host progression or redirects to final results after round 10 finishes.

### Success Criteria:

#### Automated Verification:

- Final-results view tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "final_results or finished"`.
- Host/player route guard tests pass for finished and non-finished sessions: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "host_results or player_results or owner_guard"`.
- Template regression tests pass for dynamic round labels and result links: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "host_round or player_round or lobby"`.

#### Manual Verification:

- After round 10 locks, host and player browsers transition to dedicated final-results pages.
- Final results show all top-score tied players as co-winners.
- The full ranking includes every player and makes the bound player recognizable on the player page.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets; the corresponding `- [ ]` checkboxes live in the `## Progress` section.

---

## Phase 4: Regression Coverage And Smoke Handoff

### Overview

Lock S-04 down with an automated 10-round lifecycle suite, local two-browser smoke instructions, and deploy-readiness checks that reflect the current Fly/SQLite seed-data model.

### Changes Required:

#### 1. Full-session regression tests

**File**: `game/tests.py`

**Intent**: Prove the north-star lifecycle without relying on live Spotify in every test run.

**Contract**: Add request/model tests for a 10-round happy path with at least one player, no-repeat-first track selection, repeat fallback when all unused tracks are rejected, timeout lock with missing answers scoring 0, final-session transition after round 10, final ranking/co-winner rendering, and idempotency for double next-round calls.

#### 2. Catalog regression tests

**File**: `catalog/tests.py`

**Intent**: Prevent future seed edits from breaking S-04 capacity.

**Contract**: Add coverage that seeded catalog data contains 5 sets and at least 10 tracks per set after `seed_catalog` loads.

#### 3. S-04 smoke documentation

**File**: `context/changes/full-ten-round-session/README.md`

**Intent**: Give the implementer and human tester a precise local and deployed smoke path for the full game.

**Contract**: Document preconditions, local two-browser 10-round smoke, timeout/late-answer checks, restart-active-only checks, final-results checks, and an optional Fly deployed smoke. Include the operational warning that production deploys reset the image-baked SQLite DB and should not happen during an active party session.

#### 4. Roadmap and change status handoff

**File**: `context/foundation/roadmap.md`

**Intent**: Keep the roadmap aligned after implementation, without marking S-04 complete during planning.

**Contract**: The implementation phase updates S-04 status only after the full plan is implemented and verified. Planning should not prematurely change roadmap status from `ready` to `implemented`.

### Success Criteria:

#### Automated Verification:

- Full targeted S-04 suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "full_session or next_round or final_results or repeat_fallback"`.
- Catalog capacity tests pass: `DJANGO_DEBUG=True uv run pytest catalog/tests.py -k "seed or catalog_capacity"`.
- Full test suite passes: `DJANGO_DEBUG=True uv run pytest`.
- Static collection still passes: `DJANGO_DEBUG=True uv run python manage.py collectstatic --noinput`.
- Production-style checks remain acceptable: `DJANGO_DEBUG=False DJANGO_SECRET_KEY='<strong-placeholder>' DJANGO_ALLOWED_HOSTS=melo-gierka.fly.dev,localhost,127.0.0.1 uv run python manage.py check --deploy`.

#### Manual Verification:

- A local host browser and at least one separate player browser complete all 10 rounds from lobby through final results.
- A timeout round with no answer still advances the session correctly and gives the missing player 0 points.
- A top-score tie displays co-winners on the final results page.
- Optional deployed Fly smoke repeats the 10-round path with real OAuth and Spotify browser playback when credentials and timing allow.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before marking the slice implemented. Phase blocks use plain bullets; the corresponding `- [ ]` checkboxes live in the `## Progress` section.

## Testing Strategy

### Unit Tests:

- Round candidate selection prefers unused tracks and only permits repeat fallback when all unused tracks fail playability checks.
- Expired active rounds lock idempotently and do not create explicit zero-point `Answer` rows for missing players.
- Restart on an unlocked non-first round keeps the same round index, removes active-round answers, and rolls back active-round awarded points.
- Winner/co-winner selection returns every player sharing the top score.

### Integration Tests:

- Host starts round 1 from lobby, starts rounds 2-10 from locked result states, and the session finishes after round 10 locks.
- Late answers after deadline are rejected and do not change score.
- Double-clicking Next round or sending duplicate next-round requests does not create duplicate round indexes.
- Finished host/player routes enforce ownership and player binding.
- The session-state endpoint transitions clients to final results without volatile countdown fields breaking ETag behavior.

### Manual Testing Steps:

1. Run migrations, reseed catalog, and start the local server.
2. Create a host session with one seeded music set and join from a separate player browser/profile.
3. Start round 1, answer, and confirm the locked result state shows scores.
4. Use the host Next round action until round 10, verifying the round number changes and no browser returns to lobby.
5. Let one round timeout without answering and verify it locks on the next poll/control request with 0 points for the missing answer.
6. Exercise pause/resume/skip on one active round and restart on one active non-first round.
7. Complete round 10 and verify host/player final results pages, including co-winner behavior if a tie is constructed.
8. Optionally repeat on Fly after deploy with real Spotify OAuth and browser playback.

## Performance Considerations

S-04 keeps the 1-second polling model. The endpoint can safely mutate expired-round lifecycle state because it already updates `last_activity_at` on polls, but the snapshot must continue to exclude volatile fields like `remaining_ms` or live countdown values. Player count remains tiny, so prefetching players, rounds, and answers is sufficient; no new cache layer or WebSocket transport is introduced.

The only added write path on polling is idempotent timeout locking. That path should be cheap and guarded by status/phase checks so normal unchanged polls still return `304` when semantic state has not changed.

## Migration Notes

A schema migration is expected to remove the `unique_track_per_session` constraint. This is safe for MVP because sessions are ephemeral and the application will enforce no-repeat-first behavior in tests. The expanded fixture affects deployment because the Dockerfile seeds SQLite during image build; a deploy after this change ships a fresh DB with the larger catalog.

Rollback note: if the constraint-removal migration is rolled back while repeated rounds exist locally, SQLite may reject the rollback. Production deploys bake a fresh DB, so the practical rollback path is redeploying a prior image rather than preserving runtime sessions.

## References

- Product requirements: `context/foundation/prd.md`
- Roadmap slice definition: `context/foundation/roadmap.md`
- Existing one-round implementation plan: `context/changes/first-playable-round/plan.md`
- Existing one-round smoke handoff: `context/changes/first-playable-round/README.md`
- Polling endpoint plan: `context/changes/session-state-polling/plan.md`
- Deployment contract: `context/deployment/deploy-plan.md`
- Gameplay models: `game/models.py`
- Session snapshot builder: `game/state.py`
- Host/player views and controls: `game/views.py`
- Round polling client: `game/static/game/round.js`
- Spotify host player client: `game/static/game/spotify_player.js`
- Catalog fixture: `catalog/fixtures/initial.json`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Catalog Capacity And Round Invariants

#### Automated

- [x] 1.1 Expanded fixture loads cleanly: `DJANGO_DEBUG=True uv run python manage.py seed_catalog`. — afdc590
- [x] 1.2 Migration drift is clean after the constraint change: `DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`. — afdc590
- [x] 1.3 Round selection tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "round_unique or choose_round_track or repeat_fallback"`. — afdc590
- [x] 1.4 Django configuration remains valid: `DJANGO_DEBUG=True uv run python manage.py check`. — afdc590

#### Manual

- [x] 1.5 In Django shell, each seeded music set reports at least 10 tracks. — afdc590
- [x] 1.6 Spot-check the host create-session form still lists all 5 sets after reseeding. — afdc590

### Phase 2: Host-Paced Round Lifecycle

#### Automated

- [x] 2.1 Next-round lifecycle tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "next_round or full_session or finish_session"`. — 1c6aecc
- [x] 2.2 Timeout-lock tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "deadline or timeout or late_answer"`. — 1c6aecc
- [x] 2.3 Restart regression tests pass for non-first active rounds: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "restart"`. — 1c6aecc
- [x] 2.4 Existing S-03 host-control tests still pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or pause or resume or skip or restart"`. — 1c6aecc

#### Manual

- [x] 2.5 From a locked round 1 result state, the host can start round 2 and both host/player browsers move to the new round. — 1c6aecc
- [x] 2.6 A timed-out round with unanswered players locks on the next poll/control request and missing players receive 0 points. — 1c6aecc
- [x] 2.7 Restarting active round 2 replaces round 2, not round 1, and does not corrupt scores from round 1. — 1c6aecc

### Phase 3: Final Results Browser Flow

#### Automated

- [x] 3.1 Final-results view tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "final_results or finished"`. — 0ca21aa
- [x] 3.2 Host/player route guard tests pass for finished and non-finished sessions: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "host_results or player_results or owner_guard"`. — 0ca21aa
- [x] 3.3 Template regression tests pass for dynamic round labels and result links: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "host_round or player_round or lobby"`. — 0ca21aa

#### Manual

- [x] 3.4 After round 10 locks, host and player browsers transition to dedicated final-results pages. — 0ca21aa
- [x] 3.5 Final results show all top-score tied players as co-winners. — 0ca21aa
- [x] 3.6 The full ranking includes every player and makes the bound player recognizable on the player page. — 0ca21aa

### Phase 4: Regression Coverage And Smoke Handoff

#### Automated

- [x] 4.1 Full targeted S-04 suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "full_session or next_round or final_results or repeat_fallback"`. — 1fd9f90
- [x] 4.2 Catalog capacity tests pass: `DJANGO_DEBUG=True uv run pytest catalog/tests.py -k "seed or catalog_capacity"`. — 1fd9f90
- [x] 4.3 Full test suite passes: `DJANGO_DEBUG=True uv run pytest`. — 1fd9f90
- [x] 4.4 Static collection still passes: `DJANGO_DEBUG=True uv run python manage.py collectstatic --noinput`. — 1fd9f90
- [x] 4.5 Production-style checks remain acceptable: `DJANGO_DEBUG=False DJANGO_SECRET_KEY='<strong-placeholder>' DJANGO_ALLOWED_HOSTS=melo-gierka.fly.dev,localhost,127.0.0.1 uv run python manage.py check --deploy`. — 1fd9f90

#### Manual

- [x] 4.6 A local host browser and at least one separate player browser complete all 10 rounds from lobby through final results. — 1fd9f90
- [x] 4.7 A timeout round with no answer still advances the session correctly and gives the missing player 0 points. — 1fd9f90
- [x] 4.8 A top-score tie displays co-winners on the final results page. — 1fd9f90
- [x] 4.9 Optional deployed Fly smoke repeats the 10-round path with real OAuth and Spotify browser playback when credentials and timing allow. — 1fd9f90
