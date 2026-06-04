import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch

from game.models import GameSession, Player, Round


def get_session_state(code: str) -> tuple[GameSession, dict] | None:
    session = (
        GameSession.objects.select_related("music_set")
        .prefetch_related(
            Prefetch(
                "players",
                queryset=Player.objects.order_by("-score", "joined_at"),
            ),
            Prefetch(
                "rounds",
                queryset=Round.objects.select_related("track").order_by("-index"),
            ),
        )
        .filter(code=code)
        .first()
    )
    if session is None:
        return None

    current_round = session.rounds.first()

    snapshot = {
        "code": session.code,
        "status": session.status,
        "music_set": {
            "slug": session.music_set.slug,
            "name": session.music_set.name,
        },
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "players": [
            {
                "name": player.name,
                "score": player.score,
                "joined_at": player.joined_at,
            }
            for player in session.players.all()
        ],
        "current_round": _serialize_round(current_round),
    }

    return session, snapshot


def get_session_snapshot(code: str) -> dict | None:
    state = get_session_state(code)
    if state is None:
        return None
    _, snapshot = state
    return snapshot


def build_snapshot_etag(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, cls=DjangoJSONEncoder)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def _serialize_round(round_obj: Round | None) -> dict | None:
    if round_obj is None:
        return None

    return {
        "index": round_obj.index,
        "started_at": round_obj.started_at,
        "offset_ms": round_obj.offset_ms,
        "track": {
            "spotify_track_id": round_obj.track.spotify_track_id,
            "artist": round_obj.track.artist,
            "title": round_obj.track.title,
            "duration_ms": round_obj.track.duration_ms,
        },
    }