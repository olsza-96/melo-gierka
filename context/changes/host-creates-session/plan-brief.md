# Host Creates Session — Plan Brief

> Full plan: `context/changes/host-creates-session/plan.md`

## What & Why

Build the first real host flow for melo-gierka: the host opens the app, logs into Spotify, chooses one of the existing five music sets, creates a session, and receives a 4-digit lobby code. This is the first user-visible slice on the core path from empty app shell to a playable party session, and it de-risks the auth/session boundary before player joins or playback enter the picture.

## Starting Point

The repo already has the session data model (`GameSession`, `Player`, `Round`) and a working 4-digit code generator, plus seeded `MusicSet` rows. What it does not have yet is any host-facing HTML, any Spotify OAuth code, or any route structure outside `/api/`; the root page is still plain text.

## Desired End State

When this plan is done, the host can complete a Spotify OAuth round-trip and return to the app with an authenticated host session. The landing page then reveals a create-session form backed by the existing placeholder `MusicSet` rows, and submitting it redirects to a host lobby page showing the stable 4-digit code and chosen set.

That lobby remains intentionally thin: it is a waiting-room shell, not a live multiplayer screen yet. The host can change Spotify account and edit the chosen set in place while the session stays in lobby, but player joins, polling UI, and round-start behavior remain out of scope.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Public entry point | Combined landing page at `/` | Matches the PRD path where everyone starts from the app URL and avoids a later route reshuffle. |
| Session code format | Keep 4-digit numeric codes | Reuses the existing generator and preserves the easiest spoken party-day code shape. |
| Music-set source | Use current seeded `MusicSet` rows | Keeps the slice unblocked while the real playlist curation remains an explicit later task. |
| Post-create screen | Host lobby shell, no live players yet | Gives S-02 a stable page to extend without pulling player behavior forward. |
| Spotify consent scope | Request full near-term gameplay scopes now | Avoids a second consent step before S-03 and stabilizes the auth contract early. |
| Host account recovery | Simple change-account action | Covers the likely wrong-account mistake without overbuilding account management. |
| Wrong set after create | Edit the created lobby in place | Preserves the spoken code and fits the current model as a simple `music_set` update while still in lobby. |
| Done definition | Local plus deployed Fly OAuth smoke | The callback/cookie boundary is the risky part, so localhost-only is not enough. |

## Scope

**In scope:**
- Spotify PKCE login/callback flow stored in Django session
- Combined landing page at `/` with host CTA and host session-create form
- Host session creation using existing `MusicSet` rows and current 4-digit code generator
- Host lobby page with code display, change-account action, and in-place set editing
- Focused regression tests and a written OAuth smoke checklist

**Out of scope:**
- Functional player join flow
- Live player polling on the lobby page
- Playback / Web Playback SDK integration
- Scoring, rounds, or final rankings
- Token refresh automation
- Replacing placeholder Spotify track IDs or finalizing curated playlists

## Architecture / Approach

Keep `/` in `catalog` and turn it into a rendered landing page, while splitting `game` into host HTML routes and API routes so `/api/sessions/<code>/state` stays stable. Add a small `game/spotify_auth.py` helper for PKCE URL generation and token exchange, store host auth state in Django session, and bind created lobbies to `GameSession.host_session_key` so host-only pages remain tied to the creating browser session.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. OAuth contract and host auth session | Spotify login/callback/change-account flow | Session state or callback mismatch can break the PKCE round-trip silently. |
| 2. Landing page and host creation form | First real HTML shell and set selector at `/` | The root-page rewrite can accidentally pre-commit too much of S-02 if not kept disciplined. |
| 3. Session creation and editable host lobby | Actual `GameSession` creation plus stable lobby code screen | Ownership checks must fail closed so a guessed code is not enough for host access. |
| 4. Verification coverage and Fly smoke readiness | Edge-path tests plus written smoke procedure | Easy to stop at unit tests and miss the real HTTPS callback behavior on Fly. |

**Prerequisites:** Spotify app secrets/callbacks remain configured, existing seeded `MusicSet` rows remain present, and the host tests run with `DJANGO_DEBUG=True` for local manage.py commands.
**Estimated effort:** ~3-4 focused implementation sessions across 4 phases.

## Open Risks & Assumptions

- The plan keeps PKCE on a server-rendered Django app to match the existing design notes; that means the already-configured client secret may stay unused in this slice.
- The chosen in-place set edit is safe today because no player join behavior exists yet; S-02 should revisit whether the same rule still holds once players can watch the lobby.
- Placeholder track IDs are fine for S-01 because the slice only needs `MusicSet` names, not real playback yet.

## Success Criteria (Summary)

- The host can log in with Spotify and return to the app with a persistent same-browser host session.
- The host can create a session from `/`, see a 4-digit code on a lobby page, and edit the selected set without regenerating the code.
- The same flow works locally and once on the deployed Fly URL with the real callback/HTTPS boundary.
