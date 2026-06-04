# Player Joins Lobby Implementation Plan

## Overview

This plan implements S-02: the first real player-facing slice after host session creation. A player will enter a 4-digit code and name, join a waiting lobby tied to an existing session, and both host and player will see the live roster update through the already-implemented polling endpoint.

## Current State Analysis

S-01 already creates stable host-owned sessions and renders a host lobby with the 4-digit code, but the player area on `/` is still placeholder-only. The underlying model and read side are in place: `Player` already exists with a unique-per-session name constraint, and `/api/sessions/<code>/state` already returns ordered players with ETag support and `last_activity_at` refresh.

What is missing is the write path and the UI consumers. There is no player join route, no player join form, no player lobby template, and no host-side polling UI that renders the changing roster even though the API already exposes the player list.

## Desired End State

After this plan is complete, a player can open the public app, enter a valid session code and name on a dedicated join page, and be redirected into a waiting lobby for that session. The host lobby shows a live list of joined player names within the existing ≤1s polling guardrail, and invalid codes, duplicate names, and non-lobby sessions are handled explicitly without widening the gameplay scope.

### Key Discoveries:

- `Player` already exists and enforces uniqueness only at the exact database string level via `unique_player_name_per_session` in `game/models.py`.
- The canonical live-read surface is already fixed at `/api/sessions/<code>/state` in `game/api_urls.py`, and S-02 should reuse it instead of adding a second lobby API.
- The host lobby already has the correct ownership guard in `game/views.py`, so S-02 only needs a parallel player-session binding rather than a broader auth system.
- The session snapshot already serializes players and refreshes `last_activity_at` on both `200` and `304`, which means S-02 can add client polling without reopening the cleanup contract.
- The public landing page already reserves visual space for the player path in `catalog/templates/catalog/index.html`, so the slice can replace the placeholder rather than redesign the shell.

## What We're NOT Doing

- Adding a gameplay start button, round UI, answer submission, or score presentation
- Allowing late joins after the session leaves `lobby`
- Introducing a readiness state, spectator mode, or rejoin-with-score recovery flow
- Enforcing a hard player cap in the backend
- Changing the existing polling payload shape beyond what the current snapshot already exposes

## Implementation Approach

The slice will add a dedicated player join flow and a session-bound player lobby on top of the existing S-01 host flow. The core strategy is to keep the existing snapshot endpoint as the single source of live session truth and use a small shared polling client for both host and player lobby templates, while the join mutation and player-lobby access are handled through standard Django form + session patterns.

## Critical Implementation Details

### State sequencing

A successful player join should store a session-bound player reference in the Django session so the same browser can refresh and remain in the same waiting lobby without creating another `Player` row. A fresh browser session, however, should still be treated as a new join attempt, preserving the PRD's v0 assumption that reconnecting creates a new player entry.

### Timing & lifecycle

Do not introduce a second read route for lobby state. Both the host roster and the player waiting screen should consume the existing `/api/sessions/<code>/state` contract and respect its `ETag` / `304` behavior, because that same contract must remain the foundation for S-03 and S-04.

## Phase 1: Player Join Contract

### Overview

Add the dedicated player join route and the mutation path that creates a `Player` for an existing lobby session with clear inline validation for code and name failures.

### Changes Required:

#### 1. Player join form and validation

**File**: `game/forms.py`

**Intent**: Add a dedicated `PlayerJoinForm` that owns code lookup, exact-string name collision handling, and the suggestion behavior required by FR-005.

**Contract**: The form accepts a 4-digit code plus a player name, resolves the `GameSession`, rejects joins when the session is missing or not in `lobby`, and reports duplicate-name collisions inline with a generated suggestion (for example the next available numeric suffix) while preserving exact-string uniqueness semantics rather than case-insensitive normalization.

#### 2. Player join and player-lobby access views

**File**: `game/views.py`

**Intent**: Add the player-facing GET/POST join flow and the browser-session binding that keeps the same player in the same waiting lobby on refresh.

**Contract**: A dedicated join view renders the form on `GET` and processes it on `POST`. Successful submission creates a `Player` atomically, stores a player binding in `request.session`, and redirects to a player lobby route. Invalid code, duplicate name, or non-lobby session submissions re-render the join form with inline errors instead of redirecting back to `/`. The player lobby view resolves through the session-bound player reference rather than a public player identifier in the URL.

#### 3. Player-facing routes

**File**: `game/urls.py`

**Intent**: Expose the dedicated join page and player lobby without renaming the existing HTML route include.

**Contract**: Add player-facing routes under the current `game/urls.py` include and preserve all existing host routes and URL names unchanged. The namespace may remain historical; S-02 should not spend scope on renaming routing structures that already work.

### Success Criteria:

#### Automated Verification:

- Player-join request tests pass for happy path, invalid code, duplicate name, and non-lobby session rejection: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_join or duplicate_name or invalid_code or late_join"`
- Django configuration still passes after the new form and routes land: `DJANGO_DEBUG=True uv run python manage.py check`

#### Manual Verification:

- A signed-out visitor can leave `/` and reach the dedicated player join page.
- Submitting an invalid code or duplicate exact name stays on the join form with an inline error.
- A successful join redirects the same browser into a player-specific waiting lobby.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 2: Lobby UX And Polling

### Overview

Turn the placeholder player path and static host lobby into the first real shared lobby experience powered by the existing polling contract.

### Changes Required:

#### 1. Landing-page player CTA and join template

**File**: `catalog/templates/catalog/index.html`

**Intent**: Replace the S-01 placeholder player panel with a real call-to-action that sends players into the dedicated join flow while keeping the host flow intact.

**Contract**: The landing page continues to serve both roles, but the player panel now links to the new join route rather than rendering placeholder-only copy.

**File**: `catalog/tests.py`

**Intent**: Keep the root page tests aligned with the new player CTA so the shared landing shell remains covered.

**Contract**: Signed-out landing-page coverage asserts the presence of the player join entrypoint without regressing the host CTA expectations.

**File**: `game/templates/game/player_join.html`

**Intent**: Render the dedicated mobile-first join form for players.

**Contract**: The template presents only the code and name join controls plus inline validation feedback. It should fit the existing app shell and not expose gameplay controls or host-only actions.

#### 2. Shared lobby polling surfaces

**File**: `game/templates/game/host_lobby.html`

**Intent**: Add the first live roster surface for the host using the existing state endpoint.

**Contract**: The host lobby shows a names-only player list that updates via polling and preserves the existing session code and music-set editing controls.

**File**: `game/templates/game/player_lobby.html`

**Intent**: Render the player waiting lobby that confirms the join succeeded and shows the same live roster.

**Contract**: The player lobby displays the player's chosen name, the session code, the current joined roster, and a waiting-for-start state. It should not introduce gameplay UI or readiness toggles.

**File**: `game/static/game/lobby.js`

**Intent**: Centralize the polling client shared by both lobby templates instead of duplicating inline scripts.

**Contract**: The script polls `/api/sessions/<code>/state` within the existing ≤1s guardrail, handles `304` as no-op, renders the names list, and treats a `404` as a terminal session-ended state for the current lobby screen.

**File**: `catalog/static/catalog/app.css`

**Intent**: Extend the existing layout primitives so the player join page, player lobby, and live host roster fit the current visual system.

**Contract**: Styling changes stay scoped to the S-02 lobby/join surfaces and do not redesign the host shell beyond what the new roster and player waiting state require.

### Success Criteria:

#### Automated Verification:

- Landing and lobby view tests pass for the player join CTA and session-bound player lobby access: `DJANGO_DEBUG=True uv run pytest catalog/tests.py game/tests.py -k "join_cta or player_lobby or host_lobby"`
- The existing session-state contract tests still pass while the new lobby surfaces consume it: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_state or etag"`

#### Manual Verification:

- The landing page exposes a real player join CTA without regressing the host flow.
- When a player joins, the host lobby shows the player's name within the existing polling budget.
- Refreshing the player lobby in the same browser keeps the player in the same waiting lobby instead of creating another join.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 3: Verification And Slice Handoff

### Overview

Lock the player-join edge cases with request-level coverage and capture the manual smoke path that S-03 will build on.

### Changes Required:

#### 1. Request-level regression coverage

**File**: `game/tests.py`

**Intent**: Add focused tests for the new player mutation and session-bound player lobby behavior.

**Contract**: Cover successful join, invalid code, duplicate exact-name rejection with suggestion, case-variant acceptance under the chosen exact-string rule, non-lobby join rejection, and same-browser refresh of the player lobby without creating a second `Player` row.

#### 2. Slice-local smoke documentation

**File**: `context/changes/player-joins-lobby/README.md`

**Intent**: Document the local and deployed smoke flow so S-02 does not end at unit tests.

**Contract**: Capture the exact host+player manual flow for local verification, note the expected player join boundary (`lobby` only), and include a Fly smoke path using two browser sessions or devices.

### Success Criteria:

#### Automated Verification:

- The targeted player-join regression suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_join or player_lobby or duplicate_name"`
- Root smoke plus lobby/game tests pass together: `DJANGO_DEBUG=True uv run pytest catalog/tests.py tests/test_smoke.py game/tests.py`

#### Manual Verification:

- A player can join a valid lobby with code and name and immediately appears in the host roster.
- A duplicate exact name is rejected with a suggested variant, while a case-variant name remains allowed under the chosen exact-string rule.
- The same browser can refresh the player lobby without creating another player row, while a fresh browser session must join again.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

## Testing Strategy

### Unit Tests:

- `PlayerJoinForm` resolves only existing lobby sessions from a 4-digit code
- Duplicate exact-name validation produces a suggested variant
- Case-variant names remain valid because S-02 uses exact-string uniqueness semantics
- Player session binding keeps the same browser in the same lobby without reopening join logic

### Integration Tests:

- Player joins a lobby from the dedicated join page and the host roster updates through the existing polling endpoint
- Invalid session code and non-lobby session attempts fail without creating `Player` rows
- Same-browser player lobby refresh preserves the joined player, while a fresh browser session must join again

### Manual Testing Steps:

1. Create a host session from `/` and keep the host lobby open.
2. In a second browser session or device, open the public app, follow the player join CTA, and join with the host's 4-digit code.
3. Confirm the player reaches a waiting lobby and the host sees the player name appear within ~1s.
4. Attempt the same exact player name again and confirm the join form rejects it with a suggested variant.
5. Retry with a case-variant name and confirm it is accepted under the chosen exact-string uniqueness rule.
6. Refresh the player lobby in the same browser and confirm the player remains in the same waiting lobby rather than creating another row.
7. Change the host session status away from `lobby` and confirm further join attempts are rejected.

## Performance Considerations

S-02 deliberately reuses the existing polling endpoint rather than adding a new lobby read surface, which keeps the backend contract small but increases the number of polling clients now that players poll too. The existing ETag behavior should absorb idle lobby requests; the implementation should avoid adding volatile fields to the rendered change detection path or the `304` win disappears.

## Migration Notes

No schema migration is expected. `Player`, `GameSession`, and the session snapshot contract already exist; S-02 is a route/template/session-binding slice on top of them.

## References

- Product requirements: `context/foundation/prd.md`
- Roadmap slice definition: `context/foundation/roadmap.md`
- Existing host slice: `context/changes/host-creates-session/plan.md`
- Existing polling brief: `context/changes/session-state-polling/plan-brief.md`
- Player and session models: `game/models.py`
- Current snapshot builder: `game/state.py`
- Current host lobby shell: `game/templates/game/host_lobby.html`
- Current landing page placeholder: `catalog/templates/catalog/index.html`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Player Join Contract

#### Automated

- [x] 1.1 Player-join request tests pass for happy path, invalid code, duplicate name, and non-lobby session rejection: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_join or duplicate_name or invalid_code or late_join"` — 4249ed6
- [x] 1.2 Django configuration still passes after the new form and routes land: `DJANGO_DEBUG=True uv run python manage.py check` — 4249ed6

#### Manual

- [x] 1.3 A signed-out visitor can leave `/` and reach the dedicated player join page. — 4249ed6
- [x] 1.4 Submitting an invalid code or duplicate exact name stays on the join form with an inline error. — 4249ed6
- [x] 1.5 A successful join redirects the same browser into a player-specific waiting lobby. — 4249ed6

### Phase 2: Lobby UX And Polling

#### Automated

- [x] 2.1 Landing and lobby view tests pass for the player join CTA and session-bound player lobby access: `DJANGO_DEBUG=True uv run pytest catalog/tests.py game/tests.py -k "join_cta or player_lobby or host_lobby"`
- [x] 2.2 The existing session-state contract tests still pass while the new lobby surfaces consume it: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_state or etag"`

#### Manual

- [x] 2.3 The landing page exposes a real player join CTA without regressing the host flow.
- [x] 2.4 When a player joins, the host lobby shows the player's name within the existing polling budget.
- [x] 2.5 Refreshing the player lobby in the same browser keeps the player in the same waiting lobby instead of creating another join.

### Phase 3: Verification And Slice Handoff

#### Automated

- [ ] 3.1 The targeted player-join regression suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "player_join or player_lobby or duplicate_name"`
- [ ] 3.2 Root smoke plus lobby/game tests pass together: `DJANGO_DEBUG=True uv run pytest catalog/tests.py tests/test_smoke.py game/tests.py`

#### Manual

- [ ] 3.3 A player can join a valid lobby with code and name and immediately appears in the host roster.
- [ ] 3.4 A duplicate exact name is rejected with a suggested variant, while a case-variant name remains allowed under the chosen exact-string rule.
- [ ] 3.5 The same browser can refresh the player lobby without creating another player row, while a fresh browser session must join again.
