# Dark Violet UX Refresh Implementation Plan

## Overview

This plan modernizes the app visual identity by replacing the current warm/beige-green theme with a deep dark, violet-first system across all key surfaces. The goal is to improve aesthetic consistency, mobile legibility, and perceived product quality without touching product behavior.

## Current State Analysis

- The current global tokens in catalog/static/catalog/app.css are warm/light with green accents.
- Typography uses a serif-first stack (Georgia/Times), which amplifies an editorial look but not the desired modern dark product feel.
- Most interface surfaces (landing panels, lobby, cards, alerts, buttons, form controls) consume the same token set, so token-level redesign can achieve broad coverage with low structural risk.
- Existing responsive structure is serviceable; pain point is visual language, not layout architecture.

## Desired End State

After this change:

1. App surfaces use a deep-dark baseline with layered violet surfaces and clear elevation.
2. CTA and focus states use high-visibility electric-violet accents with accessible contrast.
3. Typography shifts to modern display headings + readable sans body/UI stack.
4. Visual style is consistent across landing, lobby, round/result states using shared tokens.
5. Existing user flows remain functionally unchanged.

## Complexity Assessment

MEDIUM

Reasoning:

1. This is cross-cutting UI work touching many selectors in one shared stylesheet.
2. No backend or data model changes are needed.
3. Risk is mostly visual regression, contrast/accessibility issues, and inconsistent state coloring.

## What We Are Not Doing

1. No structural template rewrite beyond minor class-level support for typography hierarchy.
2. No redesign of product copy or information architecture.
3. No JavaScript behavior changes.
4. No dark/light toggle in this change.

## Design Constraints

1. Preserve tap target sizes and form control usability on mobile.
2. Maintain AA-like contrast for text and controls against dark surfaces.
3. Keep semantic status colors (error/warn/success) distinguishable from primary violet accent.
4. Avoid hardcoding one-off colors; use tokenized variables.

## Phase 1: Token System Redesign

### Goal

Replace current root variables with a coherent dark-violet token scale.

### Changes Required

1. Redefine root tokens in catalog/static/catalog/app.css:
   - background, surface, elevated surface,
   - primary text, secondary text, muted text,
   - border/divider,
   - primary accent, accent hover, soft accent,
   - semantic states.
2. Update body background gradients and atmospheric overlays to dark-violet direction.
3. Ensure shadow model matches dark UI (subtle glow + depth, no muddy gray halos).

### Success Criteria

1. No leftover warm palette tokens remain in active use.
2. Core UI elements derive colors from token system only.

## Phase 2: Typography Modernization

### Goal

Introduce a more contemporary typographic hierarchy that reads well on dark surfaces.

### Changes Required

1. Update font stack in catalog/static/catalog/app.css:
   - display stack for headings,
   - sans stack for body/UI text.
2. Rebalance heading sizes/line-heights for mobile first readability.
3. Tighten small text styles (microcopy, footnotes, labels) to remain legible on dark backgrounds.

### Success Criteria

1. Heading/body contrast in style is clear without reducing readability.
2. Mobile text remains legible at default browser zoom.

## Phase 3: Component Theming Coverage

### Goal

Apply the new visual language consistently across all existing components.

### Changes Required

1. Buttons and links:
   - primary/secondary styles,
   - disabled states,
   - hover/focus-visible outlines.
2. Panels/cards/status blocks:
   - hero panel, lobby cards, roster cards, code card, placeholders, alerts.
3. Forms:
   - select/input backgrounds, borders, text, placeholder and focus states.
4. Message states:
   - global flash messages and error list styling in dark context.
5. Maintain desktop media-query behavior while inheriting new tokens.

### Success Criteria

1. No component keeps old light-theme assumptions (washed backgrounds, low contrast text).
2. Focus/active/disabled states are visually distinct.

## Phase 4: Accessibility And Regression Verification

### Goal

Validate readability, contrast, and UI stability across core flows.

### Automated Verification

1. DJANGO_DEBUG=True uv run pytest catalog/tests.py -q
2. DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or choose_round_track" -q
3. DJANGO_DEBUG=True uv run python manage.py check

### Manual Verification

1. Landing signed-out: CTA contrast and hierarchy are clear on mobile.
2. Landing signed-in: form controls and status blocks remain readable and discoverable.
3. Lobby/round/result screens: no contrast regressions in cards, badges, and messages.
4. Focus-visible states are clearly visible when navigating with keyboard.
5. Desktop layout remains structurally stable.

### Success Criteria

1. Functional tests remain green.
2. No severe contrast/readability regressions in core screens.

## Risks And Mitigations

1. Risk: violet overuse causes eye fatigue.
   Mitigation: keep violet as accent + controlled surface tints, not full-saturation fills.
2. Risk: semantic colors conflict with accent hue.
   Mitigation: reserve distinct semantic ramp for error/warn/success.
3. Risk: typography swap causes layout shift.
   Mitigation: adjust line-height/spacing tokens and verify mobile breakpoints.
4. Risk: inconsistent overrides across legacy selectors.
   Mitigation: centralize tokens and review high-frequency components first.

## Progress

- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Verification complete
