# Player Joins Lobby Smoke Notes

## Local Smoke Flow

1. Start the app locally with `DJANGO_DEBUG=True uv run python manage.py runserver`.
2. In a host browser session, open `http://127.0.0.1:8000/`, log in with Spotify, and create a session.
3. Keep the host lobby open and note the 4-digit code.
4. In a second browser session or private window, open `http://127.0.0.1:8000/` and use the player CTA to enter the join page.
5. Join with the host's 4-digit code and a unique player name.
6. Confirm the player reaches the waiting lobby and the host roster updates within about 1 second.
7. Refresh the player lobby in the same browser and confirm the player stays in the same waiting lobby without creating a duplicate row.
8. Open a fresh browser session and confirm it must join again rather than inheriting the prior player binding.
9. Attempt the same exact player name again and confirm the join form rejects it with a suggested variant.
10. Retry with a case-variant name and confirm it is allowed under the exact-string uniqueness rule.
11. Change the session status away from `lobby` in the admin and confirm further join attempts are rejected.

## Expected Join Boundary

- Player joins are allowed only while `GameSession.status == "lobby"`.
- The same browser session keeps its existing player binding on refresh.
- A fresh browser session does not recover that binding in v0.

## Fly Smoke Flow

1. Open `https://melo-gierka.fly.dev/` on the host device and create a session.
2. Join the session from a second browser session or another device using the player CTA.
3. Confirm the host lobby roster updates within about 1 second.
4. Refresh the player lobby on the second browser session and confirm the player remains in the same waiting lobby.
5. Attempt a duplicate exact name and confirm the production join form still shows the inline suggestion behavior.