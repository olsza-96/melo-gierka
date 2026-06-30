# Playlist Catalog Expansion Implementation Plan

## Overview

This plan expands the existing five predefined music sets by adding more tracks to each set, while keeping the current game flow and set taxonomy unchanged. The goal is to improve replayability and reduce repetition across sessions.

Selected decisions:

1. Target size: at least 10 curated tracks per set with no overlap across sets.
2. Source of truth: curated static fixture stored in the repo.
3. Validation style: fail-fast quality gates.

## Current State Analysis

- Catalog data is seeded from `catalog/fixtures/initial.json`.
- Seed command currently loads fixture data as-is via `catalog/management/commands/seed_catalog.py`.
- Catalog data model already enforces uniqueness of Spotify track ID per set in `catalog/models.py`.
- Baseline catalog tests exist in `catalog/tests.py`, including minimum capacity checks.
- Round track selection logic consumes set tracks and used-track history in `game/views.py`.

## Desired End State

After this change:

1. Each of the five existing sets has at least 10 tracks and each track belongs to only one set.
2. Seed remains deterministic and repo-driven.
3. Catalog quality is guarded by strict automated tests that fail fast on bad data.
4. Gameplay continues to function without model or API redesign.

## What We Are Not Doing

1. No new music sets.
2. No runtime sync from Spotify APIs.
3. No schema changes in catalog models.
4. No UI redesign for host/player set selection.
5. No changes to session architecture, polling, or scoring rules.

## Implementation Approach

Use the existing fixture-first architecture and strengthen the data contract:

1. Expand fixture data in place for current set IDs/slugs.
2. Keep seed command simple and deterministic.
3. Tighten tests to encode catalog quality rules.
4. Verify game behavior with existing and targeted gameplay tests.

## Catalog Quality Contract

Each set must satisfy all rules:

1. Track count: at least 10.
2. Artist diversity: at least 4 distinct artists.
3. Spotify ID format: 22-char base62 string.
4. Duration floor: at least 90,000 ms.
5. No duplicate Spotify track IDs within a set.
6. No duplicate Spotify track IDs across different sets.

## Phase 1: Define And Lock Quality Gates

### Goal

Convert quality expectations into explicit automated constraints before large data edits.

### Changes

1. Add or update catalog tests in `catalog/tests.py` to assert all contract rules.
2. Keep checks deterministic and fixture-driven.

### Success Criteria

1. Quality tests fail when malformed IDs, short durations, or insufficient diversity are introduced.
2. Quality tests pass on valid curated fixture.

## Phase 2: Curate Distinct Fixture Sets

### Goal

Increase catalog breadth by extending current sets only.

### Changes

1. Edit `catalog/fixtures/initial.json` to add tracks for each existing set.
2. Keep existing set identities stable: slug, name, and set count remain unchanged.
3. Add records in a consistent, reviewable structure per set.

### Success Criteria

1. Fixture contains at least 50 tracks total.
2. Each set reaches at least 10 tracks.
3. A track never appears in more than one set.
4. Seed command still loads fixture without custom migration logic.

## Phase 3: Strengthen Seed And Idempotency Verification

### Goal

Ensure repeated local and CI seeding remains safe and predictable.

### Changes

1. Keep `catalog/management/commands/seed_catalog.py` behavior unchanged unless a verification improvement is strictly needed.
2. Add tests proving seed flow remains valid and repeatable.

### Success Criteria

1. Seeding works cleanly on fresh DB.
2. Re-running seed does not violate uniqueness constraints or create inconsistent catalog state.

## Phase 4: Gameplay Safety Validation With Larger Catalog

### Goal

Confirm larger datasets do not break round flow and track selection logic.

### Changes

1. Run targeted game selection tests in `game/tests.py`.
2. Add a regression test if needed to ensure normal no-repeat behavior remains intact for 10-round sessions on large sets.

### Success Criteria

1. Session round flow still works with expanded catalog.
2. No regressions in track selection behavior under normal path.

## Verification Checklist

Automated verification:

1. `DJANGO_DEBUG=True uv run python manage.py seed_catalog`
2. `DJANGO_DEBUG=True uv run pytest catalog/tests.py -k seed`
3. `DJANGO_DEBUG=True uv run pytest catalog/tests.py -k capacity`
4. `DJANGO_DEBUG=True uv run pytest catalog/tests.py -k spotify`
5. `DJANGO_DEBUG=True uv run pytest game/tests.py -k choose_round_track`
6. `DJANGO_DEBUG=True uv run python manage.py check`

Manual verification:

1. Host create-session still shows exactly five sets.
2. Each set can start a round without catalog-related errors.
3. No Spotify invalid-id failures for newly added tracks.

## Risks And Mitigations

1. Invalid Spotify IDs in curated data.
Mitigation: strict ID format tests and targeted smoke checks.

2. Regional or account-level playback restrictions for some tracks.
Mitigation: preserve existing playable-track fallback behavior and verify representative tracks per set.

3. Fixture maintenance overhead as catalog grows.
Mitigation: enforce clear fixture organization and quality-gate tests for safe future updates.

## Progress

- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Verification complete
