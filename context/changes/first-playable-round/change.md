---
change_id: first-playable-round
title: First playable round
status: implementing
created: 2026-06-05
updated: 2026-06-05
archived_at: null
---

## Notes

Lifted from roadmap **S-03** (`@context/foundation/roadmap.md`).

**Outcome:** the host can start one real gameplay round with Spotify playback, players see four artist options on their phones, answers lock on first click, the round closes on timeout or early completion, and everyone lands on a dedicated round-results state with updated scores.

**PRD refs:** FR-007, FR-008, FR-009, FR-010, FR-011, US-01 (`@context/foundation/prd.md`).

**Planning decisions captured on 2026-06-05:**
- Keep S-03 scoped to **one** fully playable round; multi-round progression stays for S-04.
- Persist answers in a dedicated per-player/per-round model rather than deriving outcomes only from score updates.
- Use server-authoritative round timing (`started_at`, `deadline_at`, `locked_at`) with early lock when all joined players have answered.
- Reveal correctness only after round lock; an answered player sees a locked waiting state during the active round.
- Keep answer submission bound to the joined-player browser session introduced in S-02.
- Include the host control deck in this slice: start, true pause/resume, skip to results, and restart as discard-plus-replacement.
- Fail closed when Spotify playback is not ready: keep the session in lobby rather than entering a broken round.
