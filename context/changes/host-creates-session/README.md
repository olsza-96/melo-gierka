# Host Creates Session

## Scope

S-01 covers host authentication with Spotify, session creation from the landing page, the first host lobby, and in-place music-set edits while the session stays in `lobby`.

## Local Smoke Checklist

Prerequisites:

- `.env` contains a valid `SPOTIFY_CLIENT_ID` and local callback URL.
- Local commands run with `DJANGO_DEBUG=True` so the dev settings contract accepts the local sentinel secret.
- The seeded catalog rows exist (`Dance Floor Hits`, `Indie Mix`, `Polish Hits`, `Pop Hits 2010s`, `Rock Classics`).

Local verification steps:

1. Run `DJANGO_DEBUG=True uv run python manage.py runserver`.
2. Open `http://127.0.0.1:8000/` and confirm the signed-out page shows the Spotify host CTA.
3. Complete Spotify login and confirm the landing page now shows the host music-set dropdown.
4. Create a session and confirm the app redirects to `/host/sessions/<code>` with a 4-digit code visible in the lobby.
5. Change the selected music set and confirm the code stays the same while the displayed set updates.
6. Open the same lobby URL in a private window or different browser session and confirm access is denied with a `404`.
7. Use the change-account action and confirm the app returns to the signed-out landing state.

Recommended local verification commands:

- `DJANGO_DEBUG=True uv run pytest game/tests.py -k "oauth or host_lobby or music_set_edit"`
- `DJANGO_DEBUG=True uv run pytest tests/test_smoke.py game/tests.py`

## Fly Smoke Checklist

Prerequisites:

- Fly secrets already include `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, and `SPOTIFY_CLIENT_ID`.
- The Spotify app allowlist already includes `https://melo-gierka.fly.dev/oauth/spotify/callback`.
- The deployed app is serving the current build.

Production verification steps:

1. Visit `https://melo-gierka.fly.dev/` and confirm the host CTA appears on the signed-out landing page.
2. Complete Spotify login and confirm the callback returns to the Fly app over HTTPS.
3. Create a session and confirm the lobby code renders.
4. Update the music set once and confirm the code does not change.
5. Repeat the lobby URL in a separate browser session and confirm host access is denied.

## Known Boundaries

- Host ownership is bound to the Django session cookie, not the Spotify user ID.
- Lobby edits are only allowed while `GameSession.status == "lobby"`.
- `/api/sessions/<code>/state` stays stable and is not part of this manual smoke checklist beyond ensuring the host flow still reaches a valid lobby.
