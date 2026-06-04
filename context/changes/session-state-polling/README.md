# Session State Polling Endpoint

Phase 3 handoff note for F-04.

## Canonical Route

`GET /api/sessions/<code>/state`

- Canonical session-state polling route for v0.
- Reads state by possession of the valid 4-char session code.
- Reused by downstream slices for lobby, round sync, and finished-session rendering.
- The older `/api/room/<code>/state` wording from `TODO.md` is not a live alias.

## Response Contract

### `200 OK`

Returned for valid sessions in `lobby`, `playing`, or `finished` state.

Shape:

```json
{
  "code": "1234",
  "status": "playing",
  "music_set": {
    "slug": "set-a",
    "name": "Set A"
  },
  "started_at": "2026-06-04T11:00:00Z",
  "finished_at": null,
  "players": [
    {
      "name": "Beata",
      "score": 12,
      "joined_at": "2026-06-04T10:59:30Z"
    }
  ],
  "current_round": {
    "index": 1,
    "started_at": "2026-06-04T11:00:00Z",
    "offset_ms": 30000,
    "track": {
      "spotify_track_id": "abc123",
      "artist": "Artist A",
      "title": "Title A",
      "duration_ms": 180000
    }
  },
  "server_now": "2026-06-04T11:00:05Z"
}
```

Notes:

- `players` are ordered by score descending, then `joined_at` ascending.
- `current_round` is `null` when no round exists yet.
- `finished` sessions still return `200` and the final player ranking snapshot until TTL cleanup deletes the session.
- `server_now` exists on `200` responses only and is not part of the ETag key.

### `404 Not Found`

Returned when the session code is unknown or the session was already cleaned up.

```json
{
  "error": {
    "code": "session_not_found",
    "message": "Session not found."
  }
}
```

## Cache Behavior

- `Cache-Control: private, max-age=0, must-revalidate`
- `ETag: "<sha256-of-semantic-snapshot>"`
- `If-None-Match` is honored for unchanged semantic state.
- On unchanged state, the endpoint returns `304 Not Modified` with the same `ETag` and `Cache-Control` headers.
- `last_activity_at` is refreshed on both `200` and `304` responses for valid sessions so polling traffic keeps active sessions alive.

## Explicitly Out Of Scope For F-04

- Answer options / distractors
- Lock-state / answer-submission flags
- Join / start / submit-answer mutations
- Any auth boundary beyond possession of the session code

Those fields and mutations belong to S-02 / S-03 and extend this route rather than replacing it.

## Local Verification Flow

### 1. Start the dev server

```bash
DJANGO_DEBUG=True uv run python manage.py runserver
```

### 2. Create a known session in the shell

```bash
DJANGO_DEBUG=True uv run python manage.py shell
```

```python
from django.utils import timezone
from catalog.models import MusicSet, Track
from game.models import GameSession, Player, Round

GameSession.objects.filter(code="1234").delete()

music_set = MusicSet.objects.first()
track = Track.objects.filter(music_set=music_set).first()

session = GameSession.objects.create(
    code="1234",
    music_set=music_set,
    host_session_key="local-host",
)

Player.objects.create(session=session, name="Adam", score=4)
Player.objects.create(session=session, name="Beata", score=12)

session.status = GameSession.Status.PLAYING
session.started_at = timezone.now()
session.save(update_fields=["status", "started_at"])

Round.objects.create(
    session=session,
    index=1,
    track=track,
    offset_ms=30000,
    started_at=timezone.now(),
)
```

### 3. Verify `200 OK`

```bash
curl -i http://127.0.0.1:8000/api/sessions/1234/state
```

Check for:

- `200 OK`
- JSON body with `players`, `current_round`, and `server_now`
- `ETag` header
- `Cache-Control` header

### 4. Verify `304 Not Modified`

```bash
ETAG=$(curl -si http://127.0.0.1:8000/api/sessions/1234/state | awk -F': ' '/^ETag:/{print $2}' | tr -d '\r')
curl -i -H "If-None-Match: $ETAG" http://127.0.0.1:8000/api/sessions/1234/state
```

Check for:

- `304 Not Modified`
- Same `ETag`
- Same `Cache-Control`

### 5. Verify changed state produces fresh `200`

In the shell:

```python
from game.models import GameSession, Player

session = GameSession.objects.get(code="1234")
Player.objects.create(session=session, name="Celina", score=20)
```

Then repeat:

```bash
curl -i -H "If-None-Match: $ETAG" http://127.0.0.1:8000/api/sessions/1234/state
```

Check for:

- `200 OK`
- New `ETag`
- `Celina` present in the player list

### 6. Verify polling refreshes activity

In the shell, force the session stale:

```python
from datetime import timedelta
from django.utils import timezone

session = GameSession.objects.get(code="1234")
session.last_activity_at = timezone.now() - timedelta(hours=2)
session.save(update_fields=["last_activity_at"])
```

Poll once:

```bash
curl -s http://127.0.0.1:8000/api/sessions/1234/state > /dev/null
```

Then inspect again in the shell:

```python
session.refresh_from_db()
print(session.last_activity_at)
```

Finally confirm cleanup no longer sees it as stale:

```bash
DJANGO_DEBUG=True uv run python manage.py cleanup_sessions --dry-run
```

`1234` should not appear in the deletion list.