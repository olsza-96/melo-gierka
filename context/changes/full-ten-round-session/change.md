---
change_id: full-ten-round-session
title: Full ten-round session
status: implementing
created: 2026-06-07
updated: 2026-06-07
archived_at: null
---

## Notes

Lifted from roadmap **S-04** (`@context/foundation/roadmap.md`).

**Outcome:** the host can run a full 10-round game from the existing lobby through final results. Rounds advance under host control after each locked result state, tracks are selected without repeats whenever possible, and after round 10 every participant sees a final winner/co-winner display plus the full ranking.

**PRD refs:** FR-013, US-01, NFR lag <= 1s, NFR ephemeral session (`@context/foundation/prd.md`).

**Planning decisions captured on 2026-06-07:**
- Host explicitly starts each next round from the result state; there is no automatic timed autoplay between rounds.
- Expired rounds are locked by server-side request handling on the next poll/control request; no background worker is introduced.
- Slow or late players do not hold up the room; late answers are rejected and score 0.
- Pause/resume/skip remain active-round controls; restart applies only to an unlocked active round.
- Final results use dedicated host/player result URLs and show winner/co-winners plus full ranking.
- Tied top scores produce co-winners; ranking remains score ordered.
- Missing answers do not create explicit `Answer` rows.
- Seed catalog data must expand each music set to at least 10 tracks.
- The normal rule remains no repeats, but the hard DB uniqueness constraint on `(session, track)` will be relaxed so the app can use a repeat fallback if Spotify rejects all unused tracks.
- Automated tests plus local 10-round smoke are required; deployed Fly smoke is documented but optional before marking the slice implemented.
