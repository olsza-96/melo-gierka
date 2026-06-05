import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch

from game.models import Answer, GameSession, Player, Round


def get_session_state(code: str, *, viewer_player_id: int | None = None) -> tuple[GameSession, dict] | None:
    session = (
        GameSession.objects.select_related("music_set")
        .prefetch_related(
            Prefetch(
                "players",
                queryset=Player.objects.order_by("-score", "joined_at"),
            ),
            Prefetch(
                "rounds",
                queryset=Round.objects.select_related("track").prefetch_related(
                    Prefetch("answers", queryset=Answer.objects.select_related("player"))
                ).order_by("-index"),
            ),
        )
        .filter(code=code)
        .first()
    )
    if session is None:
        return None

    current_round = session.rounds.first()
    players = list(session.players.all())
    players_snapshot = _serialize_players(players, current_round=current_round)

    snapshot = {
        "code": session.code,
        "status": session.status,
        "music_set": {
            "slug": session.music_set.slug,
            "name": session.music_set.name,
        },
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "players": players_snapshot,
        "current_round": _serialize_round(
            current_round,
            total_players=len(players),
            viewer_player_id=viewer_player_id,
        ),
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


def _serialize_players(players: list[Player], *, current_round: Round | None) -> list[dict]:
    hidden_score_by_player_id = {}
    if current_round is not None and current_round.locked_at is None:
        hidden_score_by_player_id = {
            answer.player_id: answer.points_awarded
            for answer in current_round.answers.all()
        }

    payload = [
        {
            "name": player.name,
            "score": player.score - hidden_score_by_player_id.get(player.pk, 0),
            "joined_at": player.joined_at,
        }
        for player in players
    ]
    payload.sort(key=lambda player: (-player["score"], player["joined_at"]))
    return payload


def _serialize_round(
    round_obj: Round | None,
    *,
    total_players: int,
    viewer_player_id: int | None,
) -> dict | None:
    if round_obj is None:
        return None

    phase = "locked"
    if round_obj.paused_at is not None:
        phase = "paused"
    elif round_obj.locked_at is None:
        phase = "active"

    payload = {
        "index": round_obj.index,
        "phase": phase,
        "started_at": round_obj.started_at,
        "deadline_at": round_obj.deadline_at,
        "paused_at": round_obj.paused_at,
        "locked_at": round_obj.locked_at,
        "offset_ms": round_obj.offset_ms,
        "answer_options": round_obj.answer_options,
        "answered_count": len(round_obj.answers.all()),
        "total_players": total_players,
    }

    if viewer_player_id is not None:
        viewer_answer = next(
            (answer for answer in round_obj.answers.all() if answer.player_id == viewer_player_id),
            None,
        )
        if viewer_answer is not None:
            payload["viewer_answer"] = {
                "selected_artist": viewer_answer.selected_artist,
                "submitted_at": viewer_answer.submitted_at,
                "response_ms": viewer_answer.response_ms,
            }
            if round_obj.locked_at is not None:
                payload["viewer_answer"]["is_correct"] = viewer_answer.is_correct
                payload["viewer_answer"]["points_awarded"] = viewer_answer.points_awarded

    if round_obj.locked_at is not None:
        payload["track"] = {
            "spotify_track_id": round_obj.track.spotify_track_id,
            "artist": round_obj.track.artist,
            "title": round_obj.track.title,
            "duration_ms": round_obj.track.duration_ms,
        }

    return payload