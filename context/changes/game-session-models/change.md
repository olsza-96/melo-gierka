---
change_id: game-session-models
title: Game session models + ephemeral cleanup
status: implementing
created: 2026-06-02
updated: 2026-06-02
archived_at: null
---

## Notes

Lifted from roadmap **F-02** (`@context/foundation/roadmap.md`). GitHub issue: https://github.com/olsza-96/melo-gierka/issues/2.

**Outcome:** modele `GameSession` (4-char code, host token ref, music_set FK, status, started_at), `Player` (session, name unique-per-session, score), `Round` (session, track FK, started_at, offset_ms, locked_at) z migracjami; task cleanup usuwa sesje bez aktywności > 1h.

**PRD refs:** NFR §Sesja ulotna, FR-002, FR-005, FR-006, FR-013 (`@context/foundation/prd.md`).

**Unlocks:** F-04 (#4 session-state-polling — polling czyta z tych modeli), S-01..S-04 (#5–#8).

**Open question carrying into planning:**
- PRD §Open Q #3 — magazyn ulotnych danych: Django DB + cron cleanup czy Redis-like z TTL. Default dla v0: Django DB; przeskok do Redisa otwiera się dopiero gdy "mid-game deploy = lost games" (per `@context/foundation/infrastructure.md` Risk #3) zacznie boleć.

**Decyzja jednorazowa do podjęcia w `/10x-plan`:** czy `Player.score` jest persistowany w kolumnie, czy obliczany z `Round` events on-the-fly. Wpływa na shape modelu, ale nie na user-facing zachowanie.

**Existing baseline (do reuse'u, nie odbudowywać):** `catalog.MusicSet` i `catalog.Track` w `catalog/models.py:4-32` — `Round.track` FK celuje w istniejący `Track`, `GameSession.music_set` FK celuje w istniejący `MusicSet`.
