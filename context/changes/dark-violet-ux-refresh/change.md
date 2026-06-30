---
change_id: dark-violet-ux-refresh
title: Dark violet UX refresh
status: implemented
created: 2026-06-30
updated: 2026-06-30
archived_at: null
---

## Notes

Lifted from UX direction request to move away from the current warm/light palette.

Outcome: the interface adopts a dark-first, violet-led visual system with improved modern readability on mobile and desktop while preserving existing app behavior.

Scope decisions captured on 2026-06-30:
- Theme depth: deep dark baseline.
- Color direction: rich violet surfaces + electric violet highlights.
- Typography: modern display headlines + readable sans for body/UI text.
- Scope: whole app.css (landing, lobby, round/result surfaces), not landing-only.

Out of scope:
- No route/API/model changes.
- No gameplay logic changes.
- No auth/session behavior changes.
- No feature additions.

Implementation + verification completed on 2026-06-30:
- Replaced global color tokens in `catalog/static/catalog/app.css` with a dark-violet system (base, surfaces, accents, semantic colors).
- Updated typography to modern display/sans hierarchy for headings and body copy.
- Themed core components (panels, buttons, forms, messages, roster/status cards, focus-visible states) to dark-violet contrast rules.
- Preserved existing routing, auth/session flows, and gameplay behavior.
- Automated verification commands passed:
	- `DJANGO_DEBUG=True uv run pytest catalog/tests.py -q`
	- `DJANGO_DEBUG=True uv run pytest game/tests.py -k "start_round or choose_round_track" -q`
	- `DJANGO_DEBUG=True uv run python manage.py check`
