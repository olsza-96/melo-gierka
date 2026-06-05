# First Playable Round Implementation Plan

## Overview

This plan implements S-03: the first real gameplay slice after players can already gather in a lobby. The host will start one actual round backed by Spotify browser playback, each joined player will receive four artist options on their phone, the first click will lock the answer, and the round will end either at the scheduled deadline or as soon as every joined player has submitted.

The slice stops intentionally after that one round. It must prove the core product loop works end to end without pulling the ten-round session manager, automatic round progression, or end-of-game flow forward from S-04.

## Current State Analysis

S-01 and S-02 already cover the pre-game path: Spotify OAuth is in place, the host can create a session, players can join by code, and both sides poll the canonical `/api/sessions/<code>/state` endpoint. The persistence layer is also partially ready for gameplay because `Round` already exists with `track`, `offset_ms`, `started_at`, and `locked_at`, while `Player.score` already gives the project a running-score field to mutate.

What is still missing is the playable-round contract itself. There is no mutation to start a round, no persisted answer record, no generation of four distinct artist options, no answer submission path, no score calculation, no host playback bootstrap in the browser, and no player-facing active round or result state. The current state endpoint is also unsafe for live gameplay because it serializes the correct track title and artist inside `current_round`, which is acceptable only because no one is using that payload for a real round yet.

## Desired End State

After this plan is complete, a host who already has at least one joined player can activate the Spotify browser player from the host session page and start a single real round. The host hears a 30-second fragment that starts from a persisted random offset, while every joined player sees four artist options within the existing polling budget and can submit exactly one answer.

The round then ends either when the 30-second window expires or when all currently joined players have answered. Only after the lock moment do both host and players see the correct artist and the updated scores, and the session lands on a dedicated round-results state that supports pause/resume/skip/restart semantics without pretending the full ten-round loop exists yet.

### Key Discoveries:

- `Round` already stores `track`, `offset_ms`, `started_at`, and `locked_at`, so S-03 should extend this model instead of inventing a parallel gameplay state store in a different subsystem (`game/models.py`).
- The canonical polling surface is already fixed at `GET /api/sessions/<code>/state`; S-03 should extend this contract rather than add a second read endpoint just for rounds (`game/api_urls.py`, `game/state.py`).
- The current snapshot builder exposes `current_round.track.artist` and `current_round.track.title`, which would leak the correct answer to any polling client during a real round and therefore must be hidden from the public round payload until result state (`game/state.py`).
- The existing `ETag` behavior only works because the snapshot contains semantic state, not a ticking countdown. S-03 must keep that property by exposing stable timestamps rather than per-poll remaining-time fields (`game/views.py`, `game/state.py`).
- Spotify host auth is already stored in Django session, and the Web Playback SDK + Web API both support the required primitives (`seek`, `pause`, `resume`, `ready`, `not_ready`, `autoplay_failed`, device-targeted playback start), so the risky part is not API availability but making the browser readiness and round timing line up cleanly with the polling model (`game/spotify_auth.py`, Spotify Web Playback SDK docs, Spotify Start/Resume Playback docs).

## What We're NOT Doing

- Auto-advancing to round 2 or implementing the ten-round loop
- Building the final end-of-game ranking screen from S-04
- Adding WebSockets, SSE, or any second live-read API beside the canonical session-state route
- Allowing players to change their answer after the first click
- Revealing correctness immediately after a player answers
- Solving rejoin-with-score recovery or host-recovery flows
- Implementing token refresh automation beyond the already existing OAuth session contract
- Building a polished between-round scoreboard beyond the single round-results state needed to end this slice clearly

## Implementation Approach

Keep the existing host and player session URLs as the canonical browser locations, but let those routes branch between lobby, active round, paused round, and round-results surfaces based on the persisted session/round state. Extend the existing API namespace with host-only control mutations and a bound-player answer submission mutation, while keeping `/api/sessions/<code>/state` as the single source of truth for round visibility, lock timing, and result visibility.

Persist the round as a durable domain object rather than letting the browser invent the round shape locally. That means storing stable answer options on `Round`, storing each player answer in its own row, computing scores on the server, and exposing only the state that the current viewer is allowed to know. The host browser gets the playback bootstrap payload through host-owned routes and control responses, while the shared public snapshot stays safe for code-based polling clients.

## Critical Implementation Details

### Timing & lifecycle

The public snapshot must not expose the correct answer while a round is active. Host playback still needs the track URI and offset, but that data belongs to the host-only HTML/control path, not to the public polling payload that any code holder can read.

### State sequencing

Starting a round must stay fail-closed: if the host does not have a ready Spotify browser device, or if there are no joined players, the session stays in `lobby` and no `Round` row is created. Once the round exists, only the server decides whether it is active, paused, locked, skipped, or restarted.

### Performance constraints

Do not serialize ticking counters like `remaining_ms` or live playback position into the canonical snapshot. Clients should derive countdowns from stable timestamps such as `started_at`, `deadline_at`, `paused_at`, and `locked_at`; otherwise every poll invalidates the `ETag` and the idle-path efficiency from F-04 disappears.

## Phase 1: Playback Readiness And Round Contract

### Overview

Lay down the durable round data contract, the safe public snapshot shape, and the host-side playback readiness path that can start one round without leaking correct-answer data to players.

### Changes Required:

#### 1. Round persistence extensions

**File**: `game/models.py`

**Intent**: Extend the existing gameplay schema so a single round can persist stable answer options, pause/deadline timing, and per-player submissions without relying on ad-hoc browser state.

**Contract**: Add durable round metadata for the playable window and the option set, and introduce a dedicated per-player/per-round answer model with a uniqueness constraint on `(round, player)`. `Player.score` remains the running total, while the answer row records the submitted artist, the submission timestamp, the response time, whether the answer was correct, and the points that were awarded.

**File**: `game/migrations/*.py`

**Intent**: Carry the schema changes cleanly into the database without rewriting the existing session and player tables by hand.

**Contract**: Migration adds the new round fields and the answer table while preserving all existing S-01/S-02 constraints and relations.

#### 2. Public round snapshot and host-only start contract

**File**: `game/state.py`

**Intent**: Turn the current snapshot builder into a round-phase aware serializer that stays safe for code-based polling clients and still supports result visibility after lock.

**Contract**: During an active round, the shared snapshot exposes the round index, stable timing fields, answer options, aggregate progress, and the viewer's own locked-answer state when applicable, but it must omit the correct artist/title. After lock or skip, the same snapshot reveals the correct artist and the updated score ordering. The host playback payload stays outside the public snapshot.

**File**: `game/views.py`

**Intent**: Add the host-owned mutation that creates one round only when playback can actually begin.

**Contract**: A host-only start-round mutation validates session ownership, requires at least one joined player, verifies Spotify playback readiness for the current host browser session, creates a new round atomically with a random unused track and a random offset in the allowed 20–80% band, stores the four distinct artist options, flips the session into `playing`, and returns the host playback bootstrap payload needed to begin playback in the browser.

**File**: `game/api_urls.py`

**Intent**: Register the new start-round API surface under the existing `/api/sessions/<code>/...` namespace.

**Contract**: Extend the current session API family instead of creating a second route group for gameplay state. Keep the route naming consistent with the existing `session-state` endpoint and the same session-code addressing scheme.

#### 3. Host playback bootstrap

**File**: `game/templates/game/host_round.html`

**Intent**: Introduce the host's active-round surface that can own Spotify playback, timing status, and control hooks once the session leaves lobby.

**Contract**: The template renders the current round shell, exposes only host-owned data attributes required for playback bootstrap and control requests, and preserves the existing host session URL instead of inventing a second host-round path.

**File**: `game/static/game/spotify_player.js`

**Intent**: Isolate Web Playback SDK integration so host playback concerns do not leak into the shared polling script.

**Contract**: The script initializes the Spotify browser player, handles readiness and error events (`ready`, `not_ready`, `autoplay_failed`, `authentication_error`, `account_error`, `playback_error`), activates the player on user interaction, and starts the selected track at the persisted offset for the host-owned device. If the SDK is not ready, it must surface a host-visible failure instead of silently transitioning the session into a broken round.

### Success Criteria:

#### Automated Verification:

- Round contract and start-round tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or round_contract or round_state"`
- Django configuration and migration drift stay clean after the new schema lands: `DJANGO_DEBUG=True uv run python manage.py check && DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- A host session with at least one joined player can activate the Spotify browser player and start a round from the existing host session URL.
- Attempting to start without a ready playback device or without joined players leaves the session in lobby with a host-visible error.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 2: Player Answering And Time-Locked Gameplay

### Overview

Turn the existing player waiting screen into a real round surface, add bound-player answer submission, and make the server enforce first-click locking, early completion, and linear time-weighted scoring.

### Changes Required:

#### 1. Session routes branch from lobby into round state

**File**: `game/views.py`

**Intent**: Reuse the existing host/player session URLs as the durable browser locations while letting the rendered surface follow the current session phase.

**Contract**: `GET /host/sessions/<code>` and `GET /player/sessions/<code>` remain the canonical URLs from S-01/S-02, but once a session is in `playing` they render round-aware templates rather than the lobby templates. The bound-player guard from S-02 still applies to the player route.

**File**: `game/templates/game/player_round.html`

**Intent**: Render the player's active-round state, including unanswered, answered-waiting, and locked-result variants.

**Contract**: The template shows four artist options, a countdown derived from stable timestamps, one-click answer controls, and a waiting state after submission. It must not reveal correctness until the round is locked or skipped.

#### 2. Answer submission and scoring

**File**: `game/views.py`

**Intent**: Add the bound-player mutation that finalizes one answer per player and computes score effects on the server.

**Contract**: The answer submission endpoint accepts only the player bound to the current browser session, rejects answers when the round is paused or already locked, stores the first valid answer only, computes a linear time-weighted score for correct answers, updates `Player.score`, and triggers early lock when the number of persisted answers reaches the number of currently joined players.

**File**: `game/api_urls.py`

**Intent**: Register the answer submission path under the same API namespace as the session-state and host-control endpoints.

**Contract**: The route stays session-code addressed and does not expose a public player identifier in the URL or payload.

#### 3. Shared round polling client

**File**: `game/static/game/round.js`

**Intent**: Replace lobby-only polling assumptions with a round-aware client that can render active round state, answered-waiting state, and result state for both host and players.

**Contract**: The client continues to poll the canonical session-state endpoint with `If-None-Match`, derives countdown display from stable timestamps, submits answers once, and transitions from active round to locked result without requiring a second read endpoint. It must preserve the viewer's own answer state across refresh and avoid taking authority away from server timestamps.

### Success Criteria:

#### Automated Verification:

- Player-answer and scoring tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_answer or early_lock or scoring"`
- Round-state and `ETag` tests still pass with the extended snapshot shape: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_state or round_state or etag"`

#### Manual Verification:

- A joined player sees four artist options within roughly one second of the host starting the round, and the first click locks that answer immediately.
- When all joined players answer before the scheduled 30-second deadline, the round closes early instead of waiting for the full timer.
- Refreshing the player page after answering preserves the answered-waiting or result state instead of reopening the question.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 3: Host Control Surface And Round-End Results

### Overview

Finish the one-round slice by implementing the widened host control deck and the dedicated result state that ends the round cleanly for everyone.

### Changes Required:

#### 1. Host control mutations

**File**: `game/views.py`

**Intent**: Add the host-owned pause/resume/skip/restart controls chosen during planning without expanding into S-04's full round loop.

**Contract**: Pause freezes the round globally by freezing both playback and the server-side deadline progression; resume continues the same round from the paused state; skip locks the active round immediately and reveals results; restart discards the current round and any persisted answers for it, then generates a fresh replacement round for the same session without pretending a second scored round exists.

**File**: `game/api_urls.py`

**Intent**: Register the pause/resume/skip/restart endpoints beside the existing start and answer routes.

**Contract**: All control routes remain host-only and session-code addressed. They must fail closed for non-host browsers even if the session code is known.

#### 2. Result-state rendering

**File**: `game/state.py`

**Intent**: Make the canonical snapshot expose the post-lock information needed to end the round clearly and consistently.

**Contract**: Once a round is locked or skipped, the snapshot reveals the correct artist, the updated ordered scores, and the round phase needed for host/player result rendering. Before lock, none of those result-only fields appear in the public round payload.

**File**: `game/templates/game/host_round.html`

**Intent**: Expand the host round surface to show paused state, result state, and the full host control deck.

**Contract**: The host can see whether playback is active, paused, skipped, restarted, or completed, and can trigger the chosen controls without leaving the existing host session URL.

**File**: `game/templates/game/player_round.html`

**Intent**: End the player experience on a dedicated result state rather than bouncing back to lobby or freezing ambiguously on the answer form.

**Contract**: After lock or skip, the player sees the correct artist and updated session scores, but the page still represents only one completed round rather than a full multi-round scoreboard.

### Success Criteria:

#### Automated Verification:

- Host control tests pass for pause, resume, skip, and restart: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "pause or resume or skip or restart"`
- The full slice regression suite passes after the round-end state lands: `DJANGO_DEBUG=True uv run pytest catalog/tests.py tests/test_smoke.py game/tests.py`

#### Manual Verification:

- Pause freezes playback and the countdown for all connected clients, and resume continues the same round.
- Skip reveals the round result immediately, while restart discards the current round and creates a fresh replacement with cleared answers.
- Correct artist and updated scores appear only after lock or skip, not immediately when a player answers.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 4: Verification And Smoke Handoff

### Overview

Lock the slice down with focused regression coverage and the manual smoke instructions needed before S-04 builds multi-round progression on top of it.

### Changes Required:

#### 1. Regression coverage for the one-round gameplay slice

**File**: `game/tests.py`

**Intent**: Cover the new gameplay lifecycle so S-03 does not rely on live-browser luck for the core round contract.

**Contract**: Add tests for round creation with safe snapshot serialization, distinct artist-option generation, bound-player answer submission, linear score calculation, early lock when all joined players answer, pause/resume deadline shifting, skip, restart-as-replacement, and result visibility only after lock.

#### 2. Slice-local smoke documentation

**File**: `context/changes/first-playable-round/README.md`

**Intent**: Capture the exact host-plus-player smoke path needed to validate real Spotify playback and synchronized round behavior outside the unit-test suite.

**Contract**: Document the local two-browser smoke flow, the required host/browser/player preconditions, the expected behavior for early lock and pause/resume, and one deployed Fly smoke path using real OAuth plus real browser playback.

### Success Criteria:

#### Automated Verification:

- The targeted playable-round suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or player_answer or scoring or pause or restart"`
- Django configuration and migration drift remain clean at slice handoff: `DJANGO_DEBUG=True uv run python manage.py check && DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`

#### Manual Verification:

- A local host browser plus at least one player browser can complete one real round from start through result state with Spotify playback, answer locking, and updated scores.
- One deployed Fly smoke run validates the same single-round host/player loop with real OAuth and browser playback.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

## Testing Strategy

### Unit Tests:

- Round option generation returns four distinct artists from the selected `MusicSet` and never reuses the correct artist as a distractor.
- Public active-round snapshots do not reveal the correct answer before lock, while locked snapshots do reveal it.
- Score calculation follows the chosen linear time-weighted rule for correct answers, and incorrect or missing answers score zero.
- Pause/resume updates the effective deadline correctly, skip locks immediately, and restart discards the current round plus answers before generating a replacement.

### Integration Tests:

- A joined player can answer exactly once from the bound browser session, and an unbound browser cannot answer for that player.
- Starting a round requires both a ready host playback device and at least one joined player; otherwise the session remains in lobby.
- All players answering early locks the round before the original deadline and reveals result state consistently to host and players.
- The host control deck changes the same round state that polling clients observe; no client needs a second read endpoint to understand pause/skip/restart.

### Manual Testing Steps:

1. Create a host session and join it from at least one separate player browser.
2. Activate the Spotify browser player on the host session screen and start one round.
3. Confirm the host hears the selected 30-second fragment and the player sees four artist options within the lag guardrail.
4. Submit one answer from each joined player and verify the first click locks immediately.
5. Confirm that when the final joined player answers, the round locks early and both host and players move into the result state.
6. Run a second pass that exercises pause/resume mid-round and verifies the countdown freezes and resumes consistently.
7. Run a third pass that exercises skip and restart, confirming skip reveals results immediately and restart discards the current round for a fresh replacement.

## Performance Considerations

S-03 increases the semantic surface of the session-state payload, but it must keep the payload stable enough for `ETag` caching to remain useful. That means countdown math stays client-side, answer options remain persisted on the round, and the public snapshot exposes timestamps rather than a constantly changing derived timer.

The early-lock path is the most write-sensitive operation in the slice because it can be triggered by the final player answer. That path should stay transactional so that answer persistence, score updates, and `locked_at` transition together instead of leaving clients in a half-locked state during polling.

## Migration Notes

This slice introduces real gameplay persistence. Expect a schema migration for the new answer table and the extra round fields needed for stable options and pause/deadline tracking. Existing sessions and rounds are ephemeral, so the migration risk is low; restart semantics can safely discard the current round plus its answer rows because v0 explicitly treats gameplay state as disposable once abandoned.

## References

- Product requirements: `context/foundation/prd.md`
- Roadmap slice definition: `context/foundation/roadmap.md`
- Stack decision: `context/foundation/tech-stack.md`
- Existing host slice: `context/changes/host-creates-session/plan.md`
- Existing player slice: `context/changes/player-joins-lobby/plan.md`
- Existing polling slice: `context/changes/session-state-polling/plan.md`
- Host auth helper: `game/spotify_auth.py`
- Gameplay models: `game/models.py`
- Current session snapshot builder: `game/state.py`
- Existing host/player session routes: `game/views.py`
- Existing lobby polling client: `game/static/game/lobby.js`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Playback Readiness And Round Contract

#### Automated

- [x] 1.1 Round contract and start-round tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or round_contract or round_state"`
- [x] 1.2 Django configuration and migration drift stay clean after the new schema lands: `DJANGO_DEBUG=True uv run python manage.py check && DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [x] 1.3 A host session with at least one joined player can activate the Spotify browser player and start a round from the existing host session URL.
- [x] 1.4 Attempting to start without a ready playback device or without joined players leaves the session in lobby with a host-visible error.

### Phase 2: Player Answering And Time-Locked Gameplay

#### Automated

- [ ] 2.1 Player-answer and scoring tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_answer or early_lock or scoring"`
- [ ] 2.2 Round-state and `ETag` tests still pass with the extended snapshot shape: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_state or round_state or etag"`

#### Manual

- [ ] 2.3 A joined player sees four artist options within roughly one second of the host starting the round, and the first click locks that answer immediately.
- [ ] 2.4 When all joined players answer before the scheduled 30-second deadline, the round closes early instead of waiting for the full timer.
- [ ] 2.5 Refreshing the player page after answering preserves the answered-waiting or result state instead of reopening the question.

### Phase 3: Host Control Surface And Round-End Results

#### Automated

- [ ] 3.1 Host control tests pass for pause, resume, skip, and restart: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "pause or resume or skip or restart"`
- [ ] 3.2 The full slice regression suite passes after the round-end state lands: `DJANGO_DEBUG=True uv run pytest catalog/tests.py tests/test_smoke.py game/tests.py`

#### Manual

- [ ] 3.3 Pause freezes playback and the countdown for all connected clients, and resume continues the same round.
- [ ] 3.4 Skip reveals the round result immediately, while restart discards the current round and creates a fresh replacement with cleared answers.
- [ ] 3.5 Correct artist and updated scores appear only after lock or skip, not immediately when a player answers.

### Phase 4: Verification And Smoke Handoff

#### Automated

- [ ] 4.1 The targeted playable-round suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or player_answer or scoring or pause or restart"`
- [ ] 4.2 Django configuration and migration drift remain clean at slice handoff: `DJANGO_DEBUG=True uv run python manage.py check && DJANGO_DEBUG=True uv run python manage.py makemigrations --check --dry-run`

#### Manual

- [ ] 4.3 A local host browser plus at least one player browser can complete one real round from start through result state with Spotify playback, answer locking, and updated scores.
- [ ] 4.4 One deployed Fly smoke run validates the same single-round host/player loop with real OAuth and browser playback.
