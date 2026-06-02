# cleanup_sessions — operational note

`game.cleanup_sessions` deletes `GameSession` rows (and cascades to `Player` / `Round`) whose `last_activity_at` is older than `--idle-hours` (default 1 h). Backs the PRD NFR "Sesja jest ulotna".

## Manual run

```bash
# Inspect what would be deleted, no changes.
DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --dry-run

# Actually delete.
DJANGO_DEBUG=True uv run python manage.py cleanup_sessions

# Custom threshold (e.g. 6 hours of inactivity).
DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --idle-hours 6
```

Output is written via `self.stdout.write(self.style.WARNING(...))` and also logged through the `game.cleanup` logger so the action is greppable in production logs.

## Production wiring (TODO)

**Not in scope for this change.** This change does NOT modify `fly.toml` or `.github/workflows/`. Wiring the command to run on a Fly scheduled machine (or equivalent cron) lands in a future **deployment** change, once F-04 (polling endpoint) and S-01 (lobby) prove the model survives a real party.

When that change happens, the natural shape is a Fly scheduled machine running `uv run python manage.py cleanup_sessions` hourly. The command is idempotent and safe to over-run.

## Failure modes

- **No stale sessions**: command prints `deleted 0 session(s): []` and exits 0. Not an error.
- **DB unavailable**: command raises the underlying `OperationalError` and exits non-zero. Fly's scheduled-machine logs will surface this; manual re-run once the DB is back.
- **Mid-game deploy / restart loses an in-flight session**: out of scope — PRD §Open Q #3 documents that Redis with TTL is the v1 swap when this bites. v0 accepts "the party can't survive a deploy".
