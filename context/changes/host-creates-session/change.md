---
change_id: host-creates-session
title: Host creates session
status: impl_reviewed
created: 2026-06-04
updated: 2026-06-04
archived_at: null
---

## Notes

Lifted from roadmap **S-01** (`@context/foundation/roadmap.md`).

**Outcome:** host enters the app, authenticates with Spotify, picks one of the existing 5 music sets, and receives a 4-digit session code on a lobby screen.

**PRD refs:** FR-001, FR-002, FR-003, US-01 (`@context/foundation/prd.md`).

**Planning decisions captured on 2026-06-04:**
- Combined landing page at `/` for host now and player entry later.
- Keep the existing 4-digit numeric session code.
- Use current seeded `MusicSet` rows as placeholder choices.
- Show a host lobby shell after creation, but keep live player joins out of this slice.
- Request the full near-term Spotify scopes up front.
- Include a simple change-account action.
- Allow editing the chosen set in-place while the session remains in lobby.
- Done means local flow plus one deployed Fly OAuth smoke test.
