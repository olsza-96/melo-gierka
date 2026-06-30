---
change_id: landing-mobile-no-scroll
title: Landing page mobile no-scroll polish
status: implemented
created: 2026-06-30
updated: 2026-06-30
archived_at: null
---

## Notes

Lifted from UX feedback and mobile screenshots (`IMG_0541.PNG`, `IMG_0542.PNG`).

**Outcome:** the landing page presents all core actions within one mobile viewport (no vertical scrolling needed for primary CTA access), while keeping the current host/player flows and backend logic unchanged.

**Scope decisions captured on 2026-06-30:**
- No-scroll target applies to **core CTAs in one viewport** (not every possible explanatory line).
- Keep **single-column mobile layout** (no tabs/segmented switch in this change).
- Apply **moderate copy trim** to reduce vertical height without removing all context.

**Out of scope:**
- No changes to routing, auth/session behavior, form validation, or API endpoints.
- No redesign of desktop layout beyond compatibility with mobile changes.
- No new product features on landing; this is layout/content polish only.

**Implementation + verification completed on 2026-06-30:**
- Compacted landing copy in `catalog/templates/catalog/index.html` to keep CTA context concise.
- Added mobile density tuning and tight-height behavior in `catalog/static/catalog/app.css` to prioritize above-the-fold CTA visibility.
- Preserved existing CTA labels and route flow (`Log in with Spotify`, `Create session`, `Open player join`).
- Verification commands passed:
	- `DJANGO_DEBUG=True uv run pytest catalog/tests.py -q`
	- `DJANGO_DEBUG=True uv run python manage.py check`

**Final UI tuning completed on 2026-06-30:**
- Reduced mobile heading scale for better first-screen balance.
- Restored section support descriptions on short-height mobile viewports (while keeping compact typography).
- Kept no-scroll priority for core CTAs and retained current host/player flow.
- Changes committed in git commit `d91838d`.
