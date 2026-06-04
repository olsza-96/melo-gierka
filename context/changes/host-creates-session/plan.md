# Host Creates Session Implementation Plan

## Overview

Implement the first host-facing end-to-end slice for melo-gierka: the host lands on the app, authenticates with Spotify, selects one of the seeded music sets, creates a session, and sees a stable 4-digit code on a lobby screen. Because the repo does not yet have the OAuth flow or the first HTML/template shell this journey depends on, this plan keeps the S-01 outcome as the boundary while absorbing only the minimum F-01 and F-03 work required to make that flow real.

## Current State Analysis

The data spine for sessions already exists: `GameSession`, `Player`, and `Round` are implemented in `game/models.py:5-79`, and the current code generator already emits a unique 4-digit numeric code in `game/codegen.py:4-23`. The catalog data source also exists via `MusicSet` and `Track` in `catalog/models.py:4-28`, seeded from `catalog/fixtures/initial.json:1-42` with five placeholder sets.

What is still missing is everything user-facing for the host flow. The root page is plain text in `catalog/views.py:12-19`; there are no templates or static assets yet; and there is no Spotify env wiring, OAuth callback route, token storage logic, or host HTML routes in `melo_gierka/settings.py:1-151`, `game/views.py:1-42`, or `game/urls.py:1-8`. The repo also routes `game` only under `/api/` in `melo_gierka/urls.py:4-8`, so adding host HTML routes requires a small URL split rather than just appending more paths to the current API include.

## Desired End State

After this plan lands, the host can open `/`, click a Spotify login CTA, complete the OAuth round-trip, and return to the same app with a session-backed authenticated host state. The root page then shows a host session-creation form populated from the existing five `MusicSet` rows, and submitting it creates a `GameSession` owned by the current Django session.

The host is redirected to a dedicated lobby page that shows the 4-digit numeric session code, the chosen set, a waiting-state shell, and simple controls to change Spotify account or edit the chosen set in place while the session remains in `lobby`. The plan deliberately stops before player join behavior, live lobby polling, start-round behavior, or any playback orchestration.

### Key Discoveries:

- Session ownership already has a storage slot: `GameSession.host_session_key` exists in `game/models.py:16`, so S-01 can bind a session to a host without changing the schema.
- The current generator already matches the selected code format: `generate_session_code()` returns zero-padded 4-digit strings in `game/codegen.py:4-23`.
- The five placeholder set choices already exist in fixture data (`catalog/fixtures/initial.json:1-42`), so S-01 does not need to block on final playlist curation.
- The root page currently belongs to `catalog` (`catalog/urls.py:5-8`, `catalog/views.py:12-19`), while `game` is API-only (`melo_gierka/urls.py:4-8`, `game/urls.py:1-8`), so the clean path is to keep `/` in `catalog` and split `game` into HTML routes plus API routes.
- Spotify app registration and callback allowlisting are already documented in `context/changes/spotify-oauth-scaffold/change.md:1-25`; what is missing is the actual PKCE flow and session persistence in code.
- The documented near-term Spotify scopes are broader than the current roadmap shorthand: `TODO.md:17-21` and `context/deployment/deploy-plan.md:137` both call out `streaming`, `user-read-email`, `user-read-private`, `user-modify-playback-state`, and `user-read-playback-state`.

## What We're NOT Doing

- Player join form submission, name validation, or lobby population (S-02)
- Live player polling on the host lobby (F-04 already exists as an API; S-02 decides how the host UI consumes it)
- Start-game controls, round orchestration, answer options, or scoring (S-03/S-04)
- Final playlist curation or replacing placeholder `spotify_track_id` values with real Spotify track IDs
- Token refresh automation (S-06); only the initial OAuth session is in scope here
- Rejoin / host-recovery flows across browsers or devices beyond a simple same-browser change-account action

## Implementation Approach

Keep the public entry point at `/`, but replace the plain-text index with a combined landing page rendered by `catalog`. When there is no authenticated host session, the page shows a Spotify login CTA; when the current Django session already contains Spotify auth state, the page reveals the host session-creation form populated from `MusicSet`.

Use a minimal server-side Spotify PKCE flow with isolated helper functions and `httpx` for the token exchange. Persist the PKCE verifier/state and resulting token payload in Django session storage, not in the database, and bind each created `GameSession` to `request.session.session_key`. Keep host-only HTML routes under `game`, move the existing state endpoint to a dedicated API URL module, and make the lobby/edit actions session-owned so a guessed session code alone cannot grant host access.

## Critical Implementation Details

### Timing & lifecycle

Call `request.session.save()` before creating the first `GameSession` if the host session does not yet have a `session_key`; otherwise `GameSession.host_session_key` can be saved as empty and ownership checks will fail later. The PKCE `state` and `code_verifier` also need to be written to the same session before redirecting to Spotify, then cleared immediately after a successful or terminal callback.

### State sequencing

The in-place lobby edit chosen for this slice must update only `GameSession.music_set` while the session remains in `lobby`; it must not regenerate the code, replace the row, or mutate `host_session_key`. This preserves a stable spoken code while keeping the edit path compatible with S-02, where players may already be looking at the lobby.

## Phase 1: OAuth Contract And Host Auth Session

### Overview

Add the Spotify PKCE flow, settings contract, and host-auth session state needed for all later host actions.

### Changes Required:

#### 1. Settings and dependency contract

**File**: `pyproject.toml`

**Intent**: Add the small HTTP client dependency required to perform the server-side token exchange and keep the auth integration explicit instead of burying it in a larger SDK.

**Contract**: Add `httpx` to runtime dependencies; do not add a full framework-level auth library for this slice.

**File**: `melo_gierka/settings.py`

**Intent**: Define the Spotify settings surface and make the callback/session behavior explicit in configuration rather than scattering constants through views.

**Contract**: Expose `SPOTIFY_CLIENT_ID`, `SPOTIFY_REDIRECT_URI`, and a canonical scope list for the selected near-term gameplay scopes. Keep token bytes in Django session storage; do not add DB fields for Spotify auth.

#### 2. Spotify auth helper

**File**: `game/spotify_auth.py`

**Intent**: Isolate PKCE verifier/challenge generation, authorize-URL construction, and token exchange so views stay thin and tests can patch a single boundary.

**Contract**: Provide helper functions that (a) generate PKCE/session state inputs, (b) build the Spotify authorize URL, and (c) exchange the callback `code` for a normalized token payload. The token exchange must use `application/x-www-form-urlencoded` parameters and exact `redirect_uri` matching.

#### 3. Auth views and routes

**File**: `game/views.py`

**Intent**: Add host-auth endpoints for starting the Spotify flow, handling the callback, and clearing/restarting the host auth session.

**Contract**: Add views for login start, callback, and change-account/sign-out. On success, store the Spotify token payload and minimal identity display data in `request.session`; on callback failure (`error`, mismatched `state`, failed token exchange), redirect back to `/` with a host-visible error message.

**File**: `game/urls.py`

**Intent**: Define the non-API host routes for auth and later lobby actions.

**Contract**: Add root-level `oauth/spotify/...` and `host/...` routes here; do not keep these endpoints under `/api/`.

**File**: `game/api_urls.py`

**Intent**: Preserve the current polling endpoint contract while separating it from host HTML routes.

**Contract**: Move the existing `session_state` route definition here so `melo_gierka/urls.py` can keep `/api/sessions/<code>/state` stable.

**File**: `melo_gierka/urls.py`

**Intent**: Rewire includes so the existing API path remains stable while host HTML/auth routes become reachable at root-level paths.

**Contract**: Keep `/api/sessions/<code>/state` unchanged and continue serving `/` from `catalog`; add a separate root include for `game` host routes.

### Success Criteria:

#### Automated Verification:

- Auth helper and callback tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "spotify or oauth or callback"`
- Framework configuration still passes checks: `DJANGO_DEBUG=True uv run python manage.py check`

#### Manual Verification:

- Visiting the host login route redirects to Spotify with the selected scopes and exact configured callback URL.
- Completing the callback returns to the app with a persistent host-auth session in the same browser.
- Using the change-account action clears host auth state and allows a fresh login.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 2: Landing Page And Host Creation Form

### Overview

Replace the plain-text root page with the first real app shell and expose the host session-creation UI against the existing `MusicSet` data.

### Changes Required:

#### 1. Base template and shared styling

**File**: `melo_gierka/templates/base.html`

**Intent**: Introduce the shared HTML shell that all later host/player pages can extend instead of continuing with plain text responses.

**Contract**: Provide the common document structure, message surface, and slots for page title/body content. Keep the layout simple, mobile-safe, and compatible with later player pages.

**File**: `catalog/static/catalog/app.css`

**Intent**: Add the first minimal stylesheet so the landing page and host lobby are legible and intentionally structured.

**Contract**: Define only the small shared layout primitives this slice needs; avoid committing to player-round styling here.

#### 2. Combined landing page

**File**: `catalog/views.py`

**Intent**: Replace the plain-text index with a rendered landing page that adapts to host auth state while leaving player join behavior unimplemented.

**Contract**: `GET /` renders a template. When the current session has no Spotify host auth, the page shows the login CTA. When host auth is present, it shows the host session-create form bound to the existing `MusicSet` queryset. Any future player entry area is placeholder-only in this slice.

**File**: `catalog/templates/catalog/index.html`

**Intent**: Render the combined landing page structure chosen during planning.

**Contract**: Show a host-focused path now and reserve visual space for the later player path without introducing a functional join form.

#### 3. Host creation form

**File**: `game/forms.py`

**Intent**: Centralize validation for host session creation and later lobby set editing so both flows use the same music-set rules.

**Contract**: Add a form that validates a selected `MusicSet` against the current seeded rows and can be reused for in-lobby edits.

### Success Criteria:

#### Automated Verification:

- Landing-page tests pass for signed-out and signed-in host states: `DJANGO_DEBUG=True uv run pytest catalog/tests.py game/tests.py -k "index or landing or host_create_form"`
- Static/template build sanity passes: `DJANGO_DEBUG=True uv run python manage.py collectstatic --noinput`

#### Manual Verification:

- A signed-out visitor at `/` sees a host login CTA rather than plain text.
- A signed-in host at `/` sees the five placeholder music sets from the seeded fixture as selectable options.
- The page renders cleanly in a desktop browser without exposing a working player-join flow yet.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 3: Session Creation And Editable Host Lobby

### Overview

Create the actual host-owned `GameSession`, show the stable 4-digit code, and allow the host to edit the chosen set in place while the session stays in lobby.

### Changes Required:

#### 1. Session creation workflow

**File**: `game/views.py`

**Intent**: Add the write path that turns an authenticated host session plus a chosen `MusicSet` into a persistent `GameSession` row.

**Contract**: Add a session-create action that requires host auth, ensures `request.session.session_key` exists, generates a 4-digit code with retry semantics compatible with `generate_session_code()`, persists `host_session_key`, and redirects to a host lobby URL on success.

**File**: `game/tests.py`

**Intent**: Lock the host session-creation contract before later slices build on it.

**Contract**: Cover successful creation, unauthenticated rejection, code-generation retry behavior at the view layer, and ownership binding through `host_session_key`.

#### 2. Host lobby shell and ownership guard

**File**: `game/views.py`

**Intent**: Add the first host lobby page as the stable destination after session creation.

**Contract**: Add a host lobby view that resolves only sessions owned by the current Django session, renders the code and current `MusicSet`, and deliberately omits live player data. Non-owner access should fail closed.

**File**: `game/templates/game/host_lobby.html`

**Intent**: Render the waiting-room shell S-02 will later extend.

**Contract**: Show the session code prominently, display the chosen set, include a waiting-state message, and expose controls for in-place set editing plus the change-account action.

#### 3. In-place lobby editing

**File**: `game/views.py`

**Intent**: Implement the user-chosen ability to revise the selected set after creation without discarding the lobby code.

**Contract**: Add an edit action that updates only `GameSession.music_set` while `status == lobby`; keep the same `code`, `host_session_key`, and row identity. Reject edits for non-owners and non-lobby sessions.

**File**: `game/forms.py`

**Intent**: Reuse the same music-set validation rules for the lobby edit path.

**Contract**: The lobby edit uses the same validated `MusicSet` choices as the creation form rather than a separate ad-hoc parser.

### Success Criteria:

#### Automated Verification:

- Session-create and host-lobby tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_create or host_lobby or host_owner or music_set_edit"`
- Django system checks still pass after route/template additions: `DJANGO_DEBUG=True uv run python manage.py check`

#### Manual Verification:

- An authenticated host can create a session from `/` and is redirected to a lobby showing the generated 4-digit code.
- Editing the chosen set from the lobby updates the displayed set in place without changing the code.
- Opening the same lobby URL from a different browser session does not grant host access.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

---

## Phase 4: Verification Coverage And Fly Smoke Readiness

### Overview

Finish the slice with explicit verification coverage for the real OAuth/cookie boundary and document the smoke path the implementer must run before considering S-01 done.

### Changes Required:

#### 1. Edge-path regression coverage

**File**: `game/tests.py`

**Intent**: Add the small but high-value regression cases that tend to break OAuth/session-bound host flows.

**Contract**: Cover callback error handling (`access_denied` or missing code), mismatched PKCE/session state, and the lobby-edit guard once the session is no longer editable.

#### 2. Slice-local verification notes

**File**: `context/changes/host-creates-session/README.md`

**Intent**: Capture the exact local and deployed smoke steps for this slice so implementation does not end at unit tests.

**Contract**: Document the local host-auth flow, the expected Fly smoke path using the production callback URL, and the known prerequisite that secrets/config must already be present.

### Success Criteria:

#### Automated Verification:

- The targeted host-flow regression suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "oauth or host_lobby or music_set_edit"`
- Root smoke plus targeted game tests pass together: `DJANGO_DEBUG=True uv run pytest tests/test_smoke.py game/tests.py`

#### Manual Verification:

- The local S-01 flow succeeds end-to-end: `/` → Spotify login → set selection → lobby code display.
- The deployed Fly app succeeds once through the same OAuth callback path with HTTPS and the allowlisted production redirect URI.
- The implementer has a written smoke checklist for repeating the verification after regressions.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase. Phase blocks use plain bullets — the corresponding `- [ ]` checkboxes for these items live in the `## Progress` section at the bottom of the plan.

## Testing Strategy

### Unit Tests:

- PKCE helper behavior: verifier/challenge/state generation and authorize URL parameter assembly
- Landing-page rendering for signed-out vs signed-in host session states
- Session creation ownership binding: `GameSession.host_session_key == request.session.session_key`
- In-place lobby editing allowed only for owned sessions in `lobby`
- Callback and ownership error paths fail closed with a visible redirect/message path

### Integration Tests:

- Authenticated host can create a session from `/` and reach the lobby in one server-side flow
- Same-browser host can revisit the lobby URL while a different browser session cannot
- Change-account action clears host auth state and returns the user to the signed-out landing screen

### Manual Testing Steps:

1. Run locally with valid Spotify settings and verify `/` shows the signed-out CTA, then the signed-in create form after callback.
2. Create a session, confirm the generated code is 4 digits, and refresh the lobby to confirm the same browser session retains access.
3. Change the selected set in the lobby and confirm the code stays stable while only the set label changes.
4. Open the lobby URL in a separate browser/private window and confirm host access is denied.
5. Repeat the login/create flow once against `https://melo-gierka.fly.dev` to validate the exact allowlisted callback and secure-cookie behavior.

## Performance Considerations

S-01 adds no continuous polling or round-state fan-out. The hot path is one `MusicSet` query on `/`, one OAuth callback exchange, one `GameSession` insert, and occasional lobby updates to a single row. Keep templates and CSS lightweight, and do not introduce a client-side framework or long-running browser polling in this slice.

## Migration Notes

No database schema migration is expected for this slice because the existing `GameSession.music_set` and `host_session_key` fields already cover the session-creation contract. The only runtime migration surface is the new `httpx` dependency and the added Spotify settings/env contract.

## References

- Product requirements: `context/foundation/prd.md`
- Roadmap slice definition: `context/foundation/roadmap.md`
- Spotify app registration note: `context/changes/spotify-oauth-scaffold/change.md`
- Deployment auth note: `context/deployment/deploy-plan.md:137`
- Existing session model: `game/models.py:5-79`
- Existing code generator: `game/codegen.py:4-23`
- Current root page: `catalog/views.py:12-19`
- Current URL split: `melo_gierka/urls.py:4-8`, `game/urls.py:1-8`, `catalog/urls.py:5-8`
- Current placeholder set data: `catalog/fixtures/initial.json:1-42`
- Spotify PKCE reference: `https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: OAuth Contract And Host Auth Session

#### Automated

- [x] 1.1 Auth helper and callback tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "spotify or oauth or callback"` — 432a4e7
- [x] 1.2 Framework configuration still passes checks: `DJANGO_DEBUG=True uv run python manage.py check` — 432a4e7

#### Manual

- [x] 1.3 Visiting the host login route redirects to Spotify with the selected scopes and exact configured callback URL. — 432a4e7
- [x] 1.4 Completing the callback returns to the app with a persistent host-auth session in the same browser. — 432a4e7
- [x] 1.5 Using the change-account action clears host auth state and allows a fresh login. — 432a4e7

### Phase 2: Landing Page And Host Creation Form

#### Automated

- [x] 2.1 Landing-page tests pass for signed-out and signed-in host states: `DJANGO_DEBUG=True uv run pytest catalog/tests.py game/tests.py -k "index or landing or host_create_form"`
- [x] 2.2 Static/template build sanity passes: `DJANGO_DEBUG=True uv run python manage.py collectstatic --noinput`

#### Manual

- [x] 2.3 A signed-out visitor at `/` sees a host login CTA rather than plain text.
- [x] 2.4 A signed-in host at `/` sees the five placeholder music sets from the seeded fixture as selectable options.
- [x] 2.5 The page renders cleanly in a desktop browser without exposing a working player-join flow yet.

### Phase 3: Session Creation And Editable Host Lobby

#### Automated

- [x] 3.1 Session-create and host-lobby tests pass: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "session_create or host_lobby or host_owner or music_set_edit"`
- [x] 3.2 Django system checks still pass after route/template additions: `DJANGO_DEBUG=True uv run python manage.py check`

#### Manual

- [x] 3.3 An authenticated host can create a session from `/` and is redirected to a lobby showing the generated 4-digit code.
- [x] 3.4 Editing the chosen set from the lobby updates the displayed set in place without changing the code.
- [x] 3.5 Opening the same lobby URL from a different browser session does not grant host access.

### Phase 4: Verification Coverage And Fly Smoke Readiness

#### Automated

- [x] 4.1 The targeted host-flow regression suite passes: `DJANGO_DEBUG=True uv run pytest game/tests.py -k "oauth or host_lobby or music_set_edit"`
- [x] 4.2 Root smoke plus targeted game tests pass together: `DJANGO_DEBUG=True uv run pytest tests/test_smoke.py game/tests.py`

#### Manual

- [x] 4.3 The local S-01 flow succeeds end-to-end: `/` → Spotify login → set selection → lobby code display.
- [x] 4.4 The deployed Fly app succeeds once through the same OAuth callback path with HTTPS and the allowlisted production redirect URI.
- [x] 4.5 The implementer has a written smoke checklist for repeating the verification after regressions.
