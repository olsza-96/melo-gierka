from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.utils import timezone

from catalog.models import MusicSet, Track
from game import codegen
from game.models import GameSession, Player, Round


@pytest.fixture
def music_set(db):
    return MusicSet.objects.create(slug="set-a", name="Set A")


@pytest.fixture
def track(music_set):
    return Track.objects.create(
        music_set=music_set,
        spotify_track_id="abc123",
        artist="Artist A",
        title="Title A",
        duration_ms=180_000,
    )


@pytest.fixture
def session(music_set):
    return GameSession.objects.create(
        code="0001",
        music_set=music_set,
        host_session_key="host-session-key",
    )


@pytest.mark.django_db
def test_game_session_defaults(music_set):
    gs = GameSession.objects.create(
        code="0042",
        music_set=music_set,
        host_session_key="host-key",
    )
    assert gs.status == GameSession.Status.LOBBY
    assert gs.created_at is not None
    assert gs.last_activity_at is not None
    assert gs.started_at is None
    assert gs.finished_at is None


@pytest.mark.django_db
def test_player_unique_name_per_session(session):
    Player.objects.create(session=session, name="Adam")
    with pytest.raises(IntegrityError):
        Player.objects.create(session=session, name="Adam")


@pytest.mark.django_db
def test_round_unique_index_per_session(session, track):
    started = timezone.now()
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=started,
    )
    other_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="xyz789",
        artist="Other",
        title="Other Title",
        duration_ms=200_000,
    )
    with pytest.raises(IntegrityError):
        Round.objects.create(
            session=session,
            index=1,
            track=other_track,
            offset_ms=30_000,
            started_at=started,
        )


@pytest.mark.django_db
def test_round_unique_track_per_session(session, track):
    started = timezone.now()
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=started,
    )
    with pytest.raises(IntegrityError):
        Round.objects.create(
            session=session,
            index=2,
            track=track,
            offset_ms=30_000,
            started_at=started,
        )


@pytest.mark.django_db
def test_generate_session_code_format():
    code = codegen.generate_session_code()
    assert len(code) == 4
    assert code.isdigit()


@pytest.mark.django_db
def test_generate_session_code_retries_on_collision(music_set, monkeypatch):
    GameSession.objects.create(
        code="0001",
        music_set=music_set,
        host_session_key="host",
    )
    values = iter([1, 2])
    calls = 0

    def fake_randbelow(_n):
        nonlocal calls
        calls += 1
        return next(values)

    monkeypatch.setattr(codegen.secrets, "randbelow", fake_randbelow)
    assert codegen.generate_session_code() == "0002"
    assert calls == 2


@pytest.mark.django_db
def test_generate_session_code_raises_when_all_attempts_collide(music_set, monkeypatch):
    GameSession.objects.create(
        code="0001",
        music_set=music_set,
        host_session_key="host",
    )
    monkeypatch.setattr(codegen.secrets, "randbelow", lambda _n: 1)
    with pytest.raises(RuntimeError, match=r"3 attempts"):
        codegen.generate_session_code(max_attempts=3)


@pytest.mark.django_db
def test_cleanup_dry_run_deletes_nothing(music_set):
    stale_at = timezone.now() - timedelta(hours=2)
    GameSession.objects.create(
        code="9001",
        music_set=music_set,
        host_session_key="host",
        last_activity_at=stale_at,
    )
    call_command("cleanup_sessions", "--dry-run")
    assert GameSession.objects.filter(code="9001").exists()


@pytest.mark.django_db
def test_cleanup_deletes_idle_sessions(music_set, track):
    stale_at = timezone.now() - timedelta(hours=2)
    gs = GameSession.objects.create(
        code="9002",
        music_set=music_set,
        host_session_key="host",
        last_activity_at=stale_at,
    )
    Player.objects.create(session=gs, name="Adam")
    Round.objects.create(
        session=gs,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=timezone.now(),
    )
    call_command("cleanup_sessions")
    assert not GameSession.objects.filter(code="9002").exists()
    assert not Player.objects.filter(session=gs).exists()
    assert not Round.objects.filter(session=gs).exists()


@pytest.mark.django_db
def test_cleanup_preserves_fresh_sessions(music_set):
    GameSession.objects.create(
        code="9003",
        music_set=music_set,
        host_session_key="host",
    )
    call_command("cleanup_sessions")
    assert GameSession.objects.filter(code="9003").exists()
