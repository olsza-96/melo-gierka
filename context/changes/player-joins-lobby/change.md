---
change_id: player-joins-lobby
title: Player joins lobby
status: impl_reviewed
created: 2026-06-04
updated: 2026-06-05
archived_at: null
---

## Notes

Lifted from roadmap **S-02** (`@context/foundation/roadmap.md`).

**Outcome:** player enters a 4-digit session code and name, lands in a waiting lobby, and the host sees the live player roster update through the existing polling contract.

**PRD refs:** FR-004, FR-005, FR-006, US-01 (`@context/foundation/prd.md`).

**Planning decisions captured on 2026-06-04:**
- Keep `/` as the shared landing page and route players into a dedicated join page.
- Reject duplicate player names with a suggested variant, but keep exact-string uniqueness semantics (no case folding).
- Reject joins once `GameSession.status != "lobby"`.
- Keep S-02 focused on roster visibility only: no readiness state, no gameplay start, no hard player cap.
- Bind joined-player lobby access to the Django browser session so refresh in the same browser keeps the player in the lobby.
