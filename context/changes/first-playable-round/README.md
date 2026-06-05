# First Playable Round Smoke Handoff

This change implements one complete playable round for `S-03`: host starts Spotify playback, joined players answer once, the server scores and locks the round, and everyone lands in a result state. It intentionally stops before the `S-04` ten-round loop.

## Preconditions

- Local database is migrated: `DJANGO_DEBUG=True uv run python manage.py migrate`
- Catalog data exists: `DJANGO_DEBUG=True uv run python manage.py seed_catalog`
- Host Spotify OAuth is configured in local env with a Premium-capable account.
- Use one host browser profile and at least one separate player browser/profile so Django sessions do not overlap.
- Keep the host tab focused while preparing Spotify browser playback.

## Local Smoke Path

1. Start local server: `DJANGO_DEBUG=True uv run python manage.py runserver`.
2. Open `http://127.0.0.1:8000/` as host.
3. Log in with Spotify, choose a music set, and create a session.
4. In a separate player browser, open the app, enter the 4-character code, and join with a player name.
5. On the host page, activate the Spotify browser player and start the round.
6. Confirm the host hears a track fragment and the player sees four artist options within about one second.
7. Submit one player answer and confirm the answer locks immediately.
8. With one joined player, confirm the round locks early, results appear on host and player, the correct artist is revealed, and scores update.

## Host Control Smoke Path

Run these from a fresh active round.

1. Pause: playback stops, host and player countdowns show paused state, answer buttons are disabled while paused.
2. Resume: playback continues on the same round, countdown continues from the shifted deadline, and both browsers leave paused state.
3. Skip: playback stops, the round locks immediately, host and player show results, and countdown text reads `Round complete`.
4. Restart: the current round and answers are discarded, a fresh replacement round appears, answer buttons are usable again, and discarded answers do not carry into the replacement.

## Result Visibility Checks

- Before lock, neither host nor player should see the correct artist/title in the public round state.
- A player who has answered before lock should see an answered/waiting state, not the correct answer.
- After all joined players answer, timeout lock, or host skip, host and player should see the correct artist and updated scores.

## Deployed Fly Smoke Path

1. Deploy the current branch to Fly using the project deploy flow.
2. Open the production app URL as host and repeat the local smoke path with real OAuth and browser playback.
3. Join from a separate mobile browser or private profile using the session code.
4. Confirm the same start, answer lock, result visibility, pause/resume, skip, and restart behavior.
5. Verify static assets load in production, especially `game/round.js` and `game/spotify_player.js`.

## Known Boundaries

- This slice has no automatic next-round progression.
- The final ten-round session and final leaderboard belong to `S-04`.
- Per-round scoreboard polish belongs after `S-04` unless needed for a bug fix.