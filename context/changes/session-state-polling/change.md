---
change_id: session-state-polling
title: Session state polling endpoint
status: implementing
created: 2026-06-04
updated: 2026-06-04
archived_at: null
---

## Notes

Lifted from roadmap **F-04** (`@context/foundation/roadmap.md`).

**Outcome:** endpoint `GET /api/sessions/<code>/state` zwraca pełen stan sesji w JSON dla pollingowego UI: status sesji, lista graczy, aktualna runda z timingiem oraz warunkowe `ETag` / `304` dla niezmienionego stanu.

**PRD refs:** FR-006, FR-009, FR-013, NFR §Lag pokazania pytania ≤ 1 sekundy, NFR §Sesja ulotna (`@context/foundation/prd.md`).

**Unlocks:** S-02 (#6 player-joins-lobby), S-03 (#7 first-playable-round), S-04 (#8 full-ten-round-session).

**Planning decisions captured here:**
- Canonical route stays `GET /api/sessions/<code>/state` (not `/api/room/...`).
- F-04 exposes session + players + current round metadata only; answer options / locks stay for S-03.
- Endpoint is readable by anyone holding the valid 4-char code in v0.
- Endpoint always returns the latest snapshot when a client is late.
- Finished sessions keep returning final state until TTL cleanup deletes them.
- `ETag` support is in scope now, not deferred.

**Known follow-up:** S-03 extends the payload with answer options and lock state without replacing the F-04 route.
