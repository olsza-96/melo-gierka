# First Playable Round — Plan Brief

> Full plan: `context/changes/first-playable-round/plan.md`

## What & Why

Build the first real gameplay round for melo-gierka: the host starts one round from the existing session page, Spotify playback begins from a persisted random offset, players answer from four artist options on their phones, and the round ends on a dedicated result state with updated scores. This is the first slice that proves the core product hypothesis rather than just the lobby plumbing.

## Starting Point

The repo already has host OAuth, session creation, player joining, and the canonical polling endpoint. `GameSession`, `Player`, and `Round` already exist, but there is no answer persistence, no host playback bootstrap in the browser, no answer submission path, and no safe active-round snapshot yet.

## Desired End State

When this plan is done, one joined player is enough for the host to start a real round from the existing host session URL. Players see four artist options within the polling guardrail, their first click locks an answer, the round closes on timeout or early completion, and everyone lands on a round-results state.

The slice stops there on purpose. It does not auto-advance to round 2 or pretend the full ten-round loop is already solved.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Slice boundary | One playable round only | Smallest vertical slice that proves playback, answer locking, and scoring together before S-04 owns progression. |
| Answer persistence | Separate answer model | Keeps scoring, restart, and result rendering queryable and auditable. |
| Timing authority | Server timestamps, client countdown | Fits the existing polling architecture while keeping lock decisions authoritative. |
| Early completion | Lock immediately when all players answer | You chose faster round closure over a fixed 30-second wait once everyone is done. |
| Correctness reveal | After round lock, not on click | Prevents early answer leakage and creates a distinct waiting state. |
| Distractor rule | Four distinct artists from the same set | Matches FR-009 directly and keeps difficulty coherent. |
| Host controls | Start, true pause/resume, skip, restart | This slice now includes a fuller host control deck rather than the minimal start-only surface. |
| Control semantics | Skip reveals now; restart discards and replaces | Gives meaningful recovery controls without pulling full multi-round logic into S-03. |
| Submission auth | Bound-player browser session only | Reuses the S-02 trust model and avoids new player tokens. |
| Playback failure | Block round start and stay in lobby | Fails closed instead of entering a broken gameplay state. |

## Scope

**In scope:** one playable round, persisted answers, linear time-weighted scoring, early lock, host playback readiness, host controls, round-results state, regression coverage, and smoke docs.

**Out of scope:** round 2+, full ten-round automation, token refresh, reconnect-with-score recovery, WebSockets, and immediate correctness reveal on click.

## Architecture / Approach

Keep the current URLs stable: `/host/sessions/<code>` and `/player/sessions/<code>` branch between lobby, active round, and results. Extend the canonical `/api/sessions/<code>/state` payload for safe round state, add host-only POST controls plus a bound-player answer POST, and keep the Spotify Web Playback SDK isolated to a host-only browser module.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Playback Readiness And Round Contract | Schema, safe snapshot, host start-round, SDK readiness | Browser autoplay/device readiness can block the whole round. |
| 2. Player Answering And Time-Locked Gameplay | Player round UI, answer submission, early lock, scoring | Active-round state must stay synchronized without leaking the answer. |
| 3. Host Control Surface And Round-End Results | Pause/resume/skip/restart and result-state UX | True pause semantics widen state complexity noticeably. |
| 4. Verification And Smoke Handoff | Focused regressions and manual smoke path | Easy to pass tests but miss the real browser playback boundary. |

**Prerequisites:** S-02 remains the active baseline, Spotify auth stays configured, and the host can use a Premium account in a browser that supports the Web Playback SDK.
**Estimated effort:** ~4 focused implementation sessions across 4 phases.

## Open Risks & Assumptions

- The canonical polling snapshot currently exposes correct-answer metadata; S-03 must remove that leak before gameplay is live.
- True pause/resume is the most scope-expanding decision in this slice because it requires synchronized time-freeze semantics, not just local playback controls.
- The Web Playback SDK supports the needed primitives, but autoplay and readiness still have to be proven in the actual browser environment used for manual smoke.

## Success Criteria (Summary)

- The host can start one real Spotify-backed round from the existing host session page with at least one joined player.
- Players receive four artist options, can submit one locked answer, and the round closes correctly on timeout or early completion.
- Host and players land on a result state with the correct artist and updated scores, and the host controls behave according to the chosen semantics.
# First Playable Round — Plan Brief

> Full plan: `context/changes/first-playable-round/plan.md`

## What & Why

Build the first real gameplay slice for melo-gierka: the host starts one Spotify-backed round, players receive four artist options on their phones, answers lock on first click, and everyone lands on a result state with updated scores. This is the smallest end-to-end round that proves the product is more than a lobby prototype and de-risks the highest-risk boundary in the roadmap: browser playback synchronized with polling-driven game state.

## Starting Point

The app already handles the pre-game path. Spotify OAuth works for the host, sessions can be created, players can join by code, and `/api/sessions/<code>/state` already drives live lobby polling. The persistence model is partially ready too: `Round` exists with `track`, `offset_ms`, `started_at`, and `locked_at`, but there is still no answer model, no round-start mutation, no active-round UI, and no safe live-round payload.

## Desired End State

When this plan is done, one joined player is enough for the host to start a real round from the existing host session URL. The host hears a 30-second fragment from a random offset, players see four artist options within the lag guardrail, the first click locks, and the round ends either at timeout or as soon as every joined player has answered.

After the lock moment, host and players move into a dedicated round-results state that reveals the correct artist and updated scores. The slice stops there on purpose: no auto-advance to round 2, no ten-round loop, and no final game-over screen yet.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Slice boundary | One playable round only | Proves the gameplay loop without dragging S-04's multi-round progression forward. |
| Answer persistence | Separate answer row per player per round | Keeps scoring, restart, and result-state logic queryable and auditable. |
| Scoring model | Linear time-weighted points for correct answers | Satisfies FR-011 with simple, explainable math instead of arbitrary bands. |
| Timing authority | Server timestamps with client-derived countdowns | Preserves fairness and fits the existing polling architecture. |
| Early completion | Lock early when all joined players have answered | Matches your chosen pacing and gives small-group sessions a faster loop. |
| Correctness reveal | Only after round lock | Prevents immediate answer leakage during the active round. |
| Submission auth | Bound player browser session only | Reuses the S-02 trust model and avoids public player identifiers. |
| Host controls | Start, true pause/resume, skip, restart | Expands host control beyond the minimal recommendation, so the plan includes explicit state handling for each action. |
| Skip/restart semantics | Skip reveals results now; restart discards and replaces the current round | Gives useful recovery controls without pretending the full round loop already exists. |
| Failure strategy | Playback-not-ready blocks round start and keeps lobby state | Avoids entering a broken round with no music. |

## Scope

**In scope:**
- One Spotify-backed round from host start to result state
- Distinct artist-option generation and bound-player answer submission
- Linear time-weighted scoring with early lock when all players answer
- Host playback bootstrap plus pause/resume/skip/restart controls
- Round/result UI on the existing host and player session URLs
- Focused regression coverage and written manual smoke steps

**Out of scope:**
- Automatic round progression or the ten-round session loop
- Final end-of-session ranking screen
- Immediate correct/incorrect reveal on answer click
- Rejoin-with-score recovery
- Token refresh automation
- WebSockets or a second read API for gameplay

## Architecture / Approach

Keep `/api/sessions/<code>/state` as the canonical read model, but make it safe for live rounds by hiding correct-answer metadata until lock and by exposing only stable timestamps plus persisted option data. Add host-only control mutations and a bound-player answer mutation under `game/api_urls.py`, keep the existing host/player session URLs as the browser entrypoints, and isolate Spotify playback into a host-only JS module so the shared round polling client stays focused on game state rather than audio control.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Playback Readiness And Round Contract | Schema, safe snapshot shape, host start-round path, Spotify bootstrap | Browser playback/device readiness can fail even when auth is valid. |
| 2. Player Answering And Time-Locked Gameplay | Player round UI, answer submission, early lock, scoring | Wrong timing model would break fairness and result visibility. |
| 3. Host Control Surface And Round-End Results | Pause/resume/skip/restart plus dedicated result state | The widened host control deck increases state-transition complexity. |
| 4. Verification And Smoke Handoff | Regression suite and manual smoke docs | Easy to miss real-browser playback issues if validation stops at pytest. |

**Prerequisites:** S-02 remains the current entry flow, Spotify auth/session state keeps working, and the host has a real browser/device capable of Web Playback SDK playback.
**Estimated effort:** ~4 focused sessions across 4 phases.

## Open Risks & Assumptions

- The public session-state route is currently safe only because no active round uses it; S-03 must remove correct-answer leakage without breaking host playback needs.
- True pause/resume is the most expensive user-chosen control because it requires global timer freezing, not just stopping host audio.
- Spotify playback APIs exist, but browser autoplay/device activation behavior still needs an early spike and manual validation on a real host browser.

## Success Criteria (Summary)

- The host can start one real round with Spotify playback from the existing host session page.
- Joined players can answer once, the round locks on timeout or early completion, and scores update correctly.
- Host and players land on a clear result state, and the same flow works in a real browser smoke run rather than only in tests.
