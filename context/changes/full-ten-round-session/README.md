# Full Ten-Round Session Smoke Handoff

This change delivers S-04: a host can run a complete 10-round session from lobby through final results. Use this handoff for local smoke testing and, when credentials and timing allow, a deployed Fly smoke.

## Preconditions

- Local dependencies are synced with `uv sync`.
- Database migrations are applied: `DJANGO_DEBUG=True uv run python manage.py migrate`.
- Seed data is loaded: `DJANGO_DEBUG=True uv run python manage.py seed_catalog`.
- The host uses a Spotify Premium account authorized for the app with playback scope.
- The host browser keeps the Spotify Web Playback SDK tab open during the session.

## Local Two-Browser Smoke

1. Start the server with `DJANGO_DEBUG=True uv run python manage.py runserver`.
2. Open the host flow in one browser/profile, log in with Spotify, choose any seeded music set, and create a session.
3. Open a separate browser/profile or private window for the player, join with the 4-digit code, and enter a player name.
4. On the host page, prepare browser playback, then start round 1.
5. Answer from the player page and confirm both browsers move to the locked result state.
6. Use the host Next round action through round 10. Confirm the round number changes and neither browser returns to lobby between rounds.
7. Complete round 10 and confirm the host and player land on dedicated final-results pages.
8. Confirm final results show every player in score order and the player page marks the bound player.

## Timeout And Late-Answer Smoke

1. Start a round and leave at least one player unanswered until the deadline passes.
2. Trigger the next poll or host control request.
3. Confirm the round locks, the missing answer receives 0 points, and the host can still start the next round.
4. Try submitting after lock and confirm the score does not change.

## Restart And Active-Round Controls

1. During one active non-first round, use pause and resume and confirm playback controls remain usable.
2. Use skip on an active round and confirm the round locks and reveals the correct artist.
3. Use restart on an active non-first round and confirm it replaces the current round number, not round 1, and does not corrupt points from earlier locked rounds.
4. Confirm restart is unavailable once a round is locked.

## Final Results Checks

- A single top scorer appears as the winner.
- Players tied at the top appear as co-winners.
- The full ranking includes every player.
- The player page marks the current bound player with `(you)`.
- No host control can start an 11th round from final results.

## Optional Fly Smoke

Run this only when real OAuth credentials are configured and no active party session is in progress.

1. Deploy the image through the normal Fly path.
2. Open `https://melo-gierka.fly.dev` and repeat the local two-browser smoke with real Spotify playback.
3. Verify `/health` remains healthy and the app serves static assets.
4. Confirm final results still work after the 10th round.

Production deploy warning: runtime sessions are ephemeral and the SQLite database is baked into the image during build. Deploying replaces the runtime DB state and can interrupt active party sessions, so do not deploy during a live game.
