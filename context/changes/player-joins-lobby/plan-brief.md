# Player Joins Lobby — Plan Brief

> Full plan: `context/changes/player-joins-lobby/plan.md`

## What & Why

This plan implements S-02: the first player-facing multiplayer slice after host session creation. It turns the existing 4-digit session code and polling foundation into a real lobby flow so a player can join with a name, wait in-session, and appear live on the host screen before gameplay starts.

## Starting Point

The repo already has the session model, `Player` model, host-created lobbies, and the canonical polling endpoint at `/api/sessions/<code>/state`. What does not exist yet is any player join mutation, player waiting screen, or live roster rendering in the host UI.

## Desired End State

After this plan, a player can leave the public landing page, enter a valid session code and name on a dedicated join page, and land in a waiting lobby tied to that browser session. The host sees the player roster update through polling, and invalid codes, duplicate names, and non-lobby sessions are handled explicitly without dragging gameplay into the slice.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Player entry surface | Dedicated join page from `/` | Keeps the shared landing page legible while giving the player flow room for validation states. |
| Duplicate-name behavior | Reject inline with a suggested variant | Matches the PRD requirement and keeps identity changes explicit to the player. |
| Name uniqueness semantics | Exact string match only | Follows your chosen rule even though it allows case-variant names in the same session. |
| Join boundary | Reject once session status is not `lobby` | Keeps S-02 narrowly scoped and prevents late-join complexity from leaking into S-03. |
| Player identity persistence | Bind player lobby access to the Django browser session | Lets the same browser refresh without creating another `Player` row while keeping fresh-browser rejoins simple. |
| Live roster source | Reuse `/api/sessions/<code>/state` for both lobbies | Preserves one canonical read contract and avoids unnecessary API sprawl before gameplay slices. |
| Player cap policy | No hard cap in S-02 | Keeps the slice aligned with the roadmap's target scale without freezing a product policy too early. |

## Scope

**In scope:**
- Dedicated player join page and join mutation
- Duplicate-name suggestion UX
- Player waiting lobby bound to the current browser session
- Live host roster and player roster via the existing polling endpoint
- Focused tests and a slice-local smoke checklist

**Out of scope:**
- Gameplay start and round UI
- Readiness toggles or spectator mode
- Late joins after the session leaves `lobby`
- Hard player limits
- Rejoin-with-score recovery across fresh browser sessions

## Architecture / Approach

S-02 adds a standard Django form + view join flow and a session-bound player lobby on top of the existing models. Host and player lobbies share a small polling client that reads the already-implemented session snapshot endpoint, so the slice extends the current architecture instead of inventing new state channels.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Player Join Contract | Join form, mutation, validation, and player session binding | Getting duplicate-name and non-lobby rejection behavior precise without widening scope |
| 2. Lobby UX And Polling | Real player join CTA, player waiting lobby, and live host roster | Polling UI drift from the existing API contract or accidental host-flow regression |
| 3. Verification And Slice Handoff | Focused regression coverage and slice smoke checklist | Missing a browser-session edge case that only shows up after refresh/rejoin |

**Prerequisites:** S-01 and F-04 are already implemented; no schema changes are needed.
**Estimated effort:** ~2-3 implementation sessions across 3 phases.

## Open Risks & Assumptions

- Exact-string uniqueness means visually similar names like `Adam` and `ADAM` are allowed in the same session by design.
- Polling now fans out to host plus player browsers, so the implementation must preserve the existing `ETag`/`304` benefit.
- The browser-session player binding is intentionally local; a fresh browser session still rejoins as a new player in v0.

## Success Criteria (Summary)

- Players can join a valid session with code and name and land in a waiting lobby.
- The host sees the joined roster update live through polling.
- Invalid code, duplicate-name, and non-lobby join cases fail clearly without destabilizing the existing host flow.
