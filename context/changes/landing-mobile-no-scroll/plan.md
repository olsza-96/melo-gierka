# Landing Mobile No-Scroll Implementation Plan

## Overview

This plan improves the landing page UX on phones where current content density forces scrolling and weakens first action clarity. The target is a compact mobile-first above-the-fold experience where users can immediately reach all core actions.

## Current State Analysis

- Landing content is split into three stacked panels in `catalog/templates/catalog/index.html`.
- Mobile layout remains single-column with relatively large typography, spacing, and multi-line copy in `catalog/static/catalog/app.css`.
- Global shell padding and message stack consume vertical space before content in `melo_gierka/templates/base.html` and `catalog/static/catalog/app.css`.
- CTA paths are already correct (Spotify login, create session when signed in, player join); problem is presentation density, not flow logic.

## Desired End State

On mobile viewport widths (especially iPhone-sized), the first screen shows:

1. Hero context (short)
2. Host primary action (login or create-session affordance)
3. Player join action

without requiring vertical scroll to access those core CTAs.

## Constraints And Decisions

1. Keep single-column layout on mobile.
2. Apply moderate copy trimming (not complete removal of explanatory text).
3. No changes to backend behavior or URL flow.
4. Maintain accessible tap targets and contrast after compaction.

## What We Are Not Doing

1. No host/player tab switcher in this change.
2. No animation-heavy redesign.
3. No changes to desktop IA beyond preserving responsive behavior.

## Phase 1: Content Compaction Strategy

### Goal

Reduce vertical text footprint while preserving essential orientation.

### Changes Required

1. Shorten hero `h1` and `lede` in `catalog/templates/catalog/index.html`.
2. Shorten panel descriptions (`panel-copy`, `microcopy`, footnotes) for signed-in/signed-out states.
3. Keep one clear sentence per section before CTA where possible.

### Success Criteria

1. No panel has long multi-sentence paragraph blocks on mobile.
2. Core CTA labels remain explicit and understandable.

## Phase 2: Mobile Layout Density Tuning

### Goal

Fit key interface blocks into one viewport on phone widths.

### Changes Required

1. Add mobile-first spacing reductions in `catalog/static/catalog/app.css`:
   - smaller `page-shell` top/bottom padding,
   - smaller panel padding and gaps,
   - tighter margins for headings and copy.
2. Reduce mobile heading scale and line-height while preserving hierarchy.
3. Ensure buttons remain touch-safe (`min-height` and horizontal padding preserved).
4. Make message stack less intrusive on mobile (spacing/margins), without removing alerts.

### Success Criteria

1. On common phone viewport heights, core CTA set is visible without scrolling.
2. No clipped text/buttons and no overlap artifacts.

## Phase 3: Signed-In And Signed-Out State Fit

### Goal

Guarantee no-scroll CTA access in both landing states.

### Changes Required

1. Verify signed-out state (Spotify login + player join) fits above fold.
2. Verify signed-in state (host setup + player join) keeps both actions above fold.
3. If needed, collapse low-priority footnotes behind shorter microcopy.

### Success Criteria

1. Both states satisfy no-scroll core-CTA rule.
2. Session-create form remains immediately discoverable when authenticated.

## Phase 4: Verification

### Automated Verification

1. `DJANGO_DEBUG=True uv run pytest catalog/tests.py -q`
2. `DJANGO_DEBUG=True uv run python manage.py check`

### Manual Verification

1. Phone-sized viewport check against screenshots for before/after comparison.
2. Signed-out page: Spotify login + player join visible without scrolling.
3. Signed-in page: create-session affordance + player join visible without scrolling.
4. Desktop breakpoint still renders three panels cleanly.

## Risks And Mitigations

1. Risk: Single-column constraint may still force scroll on very small devices.
   Mitigation: prioritize CTA visibility over long copy; aggressively tighten spacing only at narrow heights.
2. Risk: Over-compaction can reduce readability.
   Mitigation: keep typographic contrast and min touch targets; verify in manual pass.
3. Risk: Flash messages can push content below fold.
   Mitigation: reduce message stack vertical footprint on mobile and cap top margin.

## Progress

- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Verification complete
