---
change_id: playlist-catalog-expansion
title: Playlist catalog expansion
status: implemented
created: 2026-06-30
updated: 2026-06-30
archived_at: null
---

## Notes

Lifted from roadmap open data-curation scope for existing sets (`@context/foundation/roadmap.md`).

**Outcome:** each of the 5 already-defined music sets contains distinct music, so the same track does not appear across different sets while the current host/player flow stays unchanged.

**PRD refs:** FR-003 (five predefined sets), FR-008 (round playback over catalog tracks), FR-013 (10-round sessions) (`@context/foundation/prd.md`).

**Planning decisions captured on 2026-06-30:**
- Expand existing sets only; do not add new set taxonomy in v0.
- Target capacity is at least 10 tracks per set with no cross-set duplicates.
- Keep static curated fixture in-repo as the source of truth (`catalog/fixtures/initial.json`).
- Keep `seed_catalog` deterministic and fixture-driven; no runtime Spotify sync/import flow.
- Enforce fail-fast catalog quality gates in tests:
  - at least 10 tracks per set,
  - at least 4 distinct artists per set,
  - Spotify track IDs in valid 22-char base62 format,
  - minimum duration floor (>= 90s),
  - no duplicate Spotify IDs within a set,
  - no duplicate Spotify IDs across different sets.
- Preserve existing gameplay/session architecture: no schema redesign, no API shape changes, no scoring/polling changes.
- Verify with catalog seed tests and targeted game track-selection regressions before implementation closure.

**Implementation + verification completed on 2026-06-30:**
- Rebuilt `catalog/fixtures/initial.json` to keep 5 sets with distinct, non-overlapping track pools (50 tracks total).
- Strengthened `catalog/tests.py` with seeded quality gates, cross-set dedup checks, and idempotency coverage aligned with the plan contract.
- Updated `catalog/management/commands/seed_catalog.py` to clear dependent game/session rows before reloading fixture data, so reseeding remains deterministic with protected FKs.
- Verification commands passed:
  - `DJANGO_DEBUG=True uv run python manage.py seed_catalog`
  - `DJANGO_DEBUG=True uv run python manage.py check`
  - `DJANGO_DEBUG=True uv run pytest catalog/tests.py -q`
  - `DJANGO_DEBUG=True uv run pytest game/tests.py -k "choose_round_track" -q`
  - `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round" -q`
