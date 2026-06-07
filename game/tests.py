import json
from datetime import timedelta, timezone as dt_timezone
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import Client
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from catalog.models import MusicSet, Track
from game import codegen, spotify_auth, views as game_views
from game.models import Answer, GameSession, Player, Round


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
def test_round_allows_repeated_track_per_session(session, track):
    started = timezone.now()
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=started,
    )
    Round.objects.create(
        session=session,
        index=2,
        track=track,
        offset_ms=30_000,
        started_at=started,
    )

    assert Round.objects.filter(session=session, track=track).count() == 2


@pytest.mark.django_db
def test_choose_round_track_prefers_unused_track_before_repeat_fallback(session, track, monkeypatch):
    unused_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="unused-track",
        artist="Artist B",
        title="Title B",
        duration_ms=180_000,
    )
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=timezone.now(),
    )

    checked_track_ids = []
    monkeypatch.setattr(game_views.secrets, "choice", lambda sequence: sequence[0])

    def fetch_track_details(*, access_token, spotify_track_id):
        checked_track_ids.append(spotify_track_id)
        return {
            "spotify_track_id": spotify_track_id,
            "is_playable": True,
            "restriction_reason": None,
        }

    monkeypatch.setattr(spotify_auth, "fetch_track_details", fetch_track_details)

    selected_track = game_views._choose_round_track(session, access_token="access-token")

    assert selected_track == unused_track
    assert checked_track_ids == [unused_track.spotify_track_id]


@pytest.mark.django_db
def test_choose_round_track_uses_repeat_fallback_when_unused_tracks_are_unplayable(session, track, monkeypatch):
    unused_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="unused-track",
        artist="Artist B",
        title="Title B",
        duration_ms=180_000,
    )
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=timezone.now(),
    )

    monkeypatch.setattr(game_views.secrets, "choice", lambda sequence: sequence[0])

    def fetch_track_details(*, access_token, spotify_track_id):
        return {
            "spotify_track_id": spotify_track_id,
            "is_playable": spotify_track_id != unused_track.spotify_track_id,
            "restriction_reason": "market" if spotify_track_id == unused_track.spotify_track_id else None,
        }

    monkeypatch.setattr(spotify_auth, "fetch_track_details", fetch_track_details)

    selected_track = game_views._choose_round_track(session, access_token="access-token")

    assert selected_track == track


@pytest.mark.django_db
def test_choose_round_track_returns_none_when_no_playable_track_exists(session, track, monkeypatch):
    unused_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="unused-track",
        artist="Artist B",
        title="Title B",
        duration_ms=180_000,
    )
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=timezone.now(),
    )

    monkeypatch.setattr(game_views.secrets, "choice", lambda sequence: sequence[0])
    monkeypatch.setattr(
        spotify_auth,
        "fetch_track_details",
        lambda *, access_token, spotify_track_id: {
            "spotify_track_id": spotify_track_id,
            "is_playable": False,
            "restriction_reason": "market",
        },
    )

    assert game_views._choose_round_track(session, access_token="access-token") is None


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
        last_activity_at=timezone.now(),  # within idle window
    )
    call_command("cleanup_sessions")
    assert GameSession.objects.filter(code="9003").exists()


@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
    SPOTIFY_SCOPE="streaming user-read-email",
)
def test_build_authorize_url_includes_pkce_parameters():
    authorize_url = spotify_auth.build_authorize_url(
        state="state-123",
        code_verifier="a" * 64,
        redirect_uri="https://example.com/oauth/spotify/callback",
    )

    parsed_url = urlparse(authorize_url)
    params = parse_qs(parsed_url.query)

    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "accounts.spotify.com"
    assert parsed_url.path == "/authorize"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://example.com/oauth/spotify/callback"]
    assert params["scope"] == ["streaming user-read-email"]
    assert params["state"] == ["state-123"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"][0] != "a" * 64


def test_normalize_token_payload_adds_expiry_timestamp():
    payload = spotify_auth.normalize_token_payload(
        {
            "access_token": "access-token",
            "token_type": "Bearer",
            "scope": "streaming user-read-email",
            "expires_in": 3600,
            "refresh_token": "refresh-token",
        }
    )

    assert payload["access_token"] == "access-token"
    assert payload["refresh_token"] == "refresh-token"
    assert payload["expires_in"] == 3600
    assert payload["expires_at"] > int(timezone.now().timestamp())


def test_fetch_user_profile_includes_product(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "spotify-user-id",
                "display_name": "Host User",
                "email": "host@example.com",
                "product": "premium",
            }

    monkeypatch.setattr(spotify_auth.httpx, "get", lambda *args, **kwargs: Response())

    profile = spotify_auth.fetch_user_profile("access-token")

    assert profile == {
        "id": "spotify-user-id",
        "display_name": "Host User",
        "email": "host@example.com",
        "product": "premium",
    }


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
    SPOTIFY_SCOPE="streaming user-read-email",
)
def test_spotify_login_redirects_to_authorize_url_and_stores_pkce_state(client):
    response = client.get(
        reverse("game_host:spotify-login"),
        {"next": "/host/create"},
    )

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"].startswith("https://accounts.spotify.com/authorize?")
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Foauth%2Fspotify%2Fcallback" in response.headers["Location"]
    assert session_data[game_views.SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY] == "/host/create"
    assert session_data[game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY]
    assert session_data[game_views.SPOTIFY_CODE_VERIFIER_SESSION_KEY]


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
)
def test_spotify_callback_stores_auth_payload_and_profile(client, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        spotify_auth,
        "exchange_code_for_token",
        lambda *, code, code_verifier, redirect_uri: captured.update(
            {
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            }
        )
        or {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "scope": "streaming user-read-email",
            "token_type": "Bearer",
            "expires_in": 3600,
            "expires_at": 9_999_999_999,
        },
    )
    monkeypatch.setattr(
        spotify_auth,
        "fetch_user_profile",
        lambda access_token: {
            "id": "spotify-user-id",
            "display_name": "Host User",
            "email": "host@example.com",
            "product": "premium",
        },
    )

    client.get(reverse("game_host:spotify-login"), {"next": "/host/create"})
    oauth_state = client.session[game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY]

    response = client.get(
        reverse("game_host:spotify-callback"),
        {"code": "oauth-code", "state": oauth_state},
    )

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"] == "/host/create"
    assert captured["code"] == "oauth-code"
    assert captured["redirect_uri"] == "http://testserver/oauth/spotify/callback"
    assert session_data[game_views.SPOTIFY_AUTH_SESSION_KEY]["access_token"] == "access-token"
    assert session_data[game_views.SPOTIFY_USER_SESSION_KEY]["display_name"] == "Host User"
    assert session_data[game_views.SPOTIFY_USER_SESSION_KEY]["product"] == "premium"
    assert game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY not in session_data
    assert session_data.session_key is not None


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
)
def test_spotify_callback_handles_provider_error(client):
    client.get(reverse("game_host:spotify-login"))

    response = client.get(
        reverse("game_host:spotify-callback"),
        {"error": "access_denied"},
    )

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("catalog:index")
    assert game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY not in session_data


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
)
def test_spotify_callback_rejects_missing_code(client):
    client.get(reverse("game_host:spotify-login"))
    oauth_state = client.session[game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY]

    response = client.get(
        reverse("game_host:spotify-callback"),
        {"state": oauth_state},
    )

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("catalog:index")
    assert game_views.SPOTIFY_AUTH_SESSION_KEY not in session_data
    assert game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY not in session_data


def _set_host_auth(client, *, display_name="Host User", product="premium"):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "scope": settings.SPOTIFY_SCOPE,
        "expires_at": int(timezone.now().timestamp()) + 3600,
    }
    session_data[game_views.SPOTIFY_USER_SESSION_KEY] = {
        "display_name": display_name,
        "product": product,
    }
    session_data.save()

def _bind_host_session(client, session):
    session_data = client.session
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])


def _bind_player_session(client, session, player):
    session_data = client.session
    session_data[game_views.PLAYER_SESSION_BINDING_SESSION_KEY] = {
        "session_code": session.code,
        "player_id": player.pk,
    }
    session_data.save()

def _set_playback_ready(client, session, *, device_id="spotify-device-1"):
    session_data = client.session
    session_data[game_views.SPOTIFY_PLAYBACK_SESSION_KEY] = {
        "session_code": session.code,
        "device_id": device_id,
        "ready": True,
    }
    session_data.save()


def _add_round_tracks(session, *, count=4, prefix="track", start=1):
    return [
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"{prefix}-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )
        for index in range(start, start + count)
    ]


@pytest.mark.django_db
def test_session_create_redirects_to_owned_host_lobby(client, music_set):
    _set_host_auth(client)

    response = client.post(
        reverse("game_host:session-create"),
        {"music_set": str(music_set.pk)},
    )

    created_session = GameSession.objects.get()
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "game_host:host-lobby",
        kwargs={"code": created_session.code},
    )
    assert created_session.host_session_key == client.session.session_key
    assert created_session.music_set == music_set


@pytest.mark.django_db
def test_session_create_rejects_unauthenticated_host(client, music_set):
    response = client.post(
        reverse("game_host:session-create"),
        {"music_set": str(music_set.pk)},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("catalog:index")
    assert GameSession.objects.count() == 0


@pytest.mark.django_db
def test_session_create_retries_after_integrity_error(client, music_set, monkeypatch):
    _set_host_auth(client)
    GameSession.objects.create(
        code="1111",
        music_set=music_set,
        host_session_key="other-session",
    )

    codes = iter(["1111", "2222"])
    monkeypatch.setattr(codegen, "generate_session_code", lambda: next(codes))

    response = client.post(
        reverse("game_host:session-create"),
        {"music_set": str(music_set.pk)},
    )

    created_session = GameSession.objects.get(code="2222")
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "game_host:host-lobby",
        kwargs={"code": created_session.code},
    )


@pytest.mark.django_db
def test_host_lobby_renders_for_owner(client, session):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "scope": settings.SPOTIFY_SCOPE,
        "expires_at": int(timezone.now().timestamp()) + 3600,
    }
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert session.code in content
    assert session.music_set.name in content
    assert reverse("game_host:music-set-edit", kwargs={"code": session.code}) in content
    assert reverse("game:session-state", kwargs={"code": session.code}) in content
    assert "Live roster" in content
    assert 'data-start-round' in content
    assert 'data-start-round disabled' not in content


@pytest.mark.django_db
def test_host_lobby_refreshes_expired_spotify_auth_before_render(client, session, monkeypatch):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {
        "access_token": "stale-token",
        "refresh_token": "refresh-token",
        "scope": settings.SPOTIFY_SCOPE,
        "expires_at": int(timezone.now().timestamp()) - 10,
    }
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    monkeypatch.setattr(
        spotify_auth,
        "refresh_access_token",
        lambda *, refresh_token: {
            "access_token": "fresh-token",
            "refresh_token": refresh_token,
            "scope": settings.SPOTIFY_SCOPE,
            "expires_in": 3600,
            "expires_at": int(timezone.now().timestamp()) + 3600,
        },
    )

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert 'data-access-token="fresh-token"' in response.content.decode()
    assert client.session[game_views.SPOTIFY_AUTH_SESSION_KEY]["access_token"] == "fresh-token"


@pytest.mark.django_db
def test_host_lobby_clears_under_scoped_spotify_auth_and_shows_reconnect_message(client, session):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "scope": "user-read-email user-read-private",
        "expires_at": int(timezone.now().timestamp()) + 3600,
    }
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert "Reconnect Spotify before preparing browser playback." in response.content.decode()
    assert game_views.SPOTIFY_AUTH_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_host_owner_guard_blocks_other_browser(client, session):
    other_client = client.__class__()
    response = other_client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    assert response.status_code == 404


@pytest.mark.django_db
def test_music_set_edit_updates_lobby_without_changing_code(client, session):
    other_music_set = MusicSet.objects.create(slug="set-b", name="Set B")
    session_data = client.session
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    response = client.post(
        reverse("game_host:music-set-edit", kwargs={"code": session.code}),
        {"music_set": str(other_music_set.pk)},
    )

    session.refresh_from_db()
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "game_host:host-lobby",
        kwargs={"code": session.code},
    )
    assert session.code == "0001"
    assert session.music_set == other_music_set


@pytest.mark.django_db
def test_music_set_edit_rejects_non_lobby_session(client, session):
    other_music_set = MusicSet.objects.create(slug="set-b", name="Set B")
    session.status = GameSession.Status.PLAYING
    session.save(update_fields=["status"])
    session_data = client.session
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    response = client.post(
        reverse("game_host:music-set-edit", kwargs={"code": session.code}),
        {"music_set": str(other_music_set.pk)},
    )

    session.refresh_from_db()
    assert response.status_code == 404
    assert session.music_set != other_music_set
    assert game_views.SPOTIFY_AUTH_SESSION_KEY not in session_data


@pytest.mark.django_db
def test_player_join_creates_player_and_redirects_to_bound_lobby(client, session):
    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    player = Player.objects.get(session=session, name="Adam")
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "game_host:player-lobby",
        kwargs={"code": session.code},
    )
    assert client.session[game_views.PLAYER_SESSION_BINDING_SESSION_KEY] == {
        "session_code": session.code,
        "player_id": player.pk,
    }


@pytest.mark.django_db
def test_player_join_renders_bound_player_lobby(client, session):
    client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "You are in the lobby." in content
    assert session.code in content
    assert "Adam" in content
    assert reverse("game:session-state", kwargs={"code": session.code}) in content
    assert "Who is here" in content
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_host_lobby_renders_player_roster_polling_hooks(client, session):
    Player.objects.create(session=session, name="Adam")
    session_data = client.session
    session_data.save()
    session.host_session_key = session_data.session_key
    session.save(update_fields=["host_session_key"])

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "data-lobby-state-root" in content
    assert 'data-empty-label="No players yet."' in content
    assert reverse("game:session-state", kwargs={"code": session.code}) in content


@pytest.mark.django_db
def test_host_lobby_branches_to_round_surface_with_shared_state_hooks(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "data-round-state-root" in content
    assert 'data-round-controls' in content
    assert reverse("game:session-pause", kwargs={"code": session.code}) in content
    assert reverse("game:session-restart", kwargs={"code": session.code}) in content
    assert reverse("game:session-next-round", kwargs={"code": session.code}) in content
    assert reverse("game:session-stop-playback", kwargs={"code": session.code}) in content
    assert reverse("game_host:host-results", kwargs={"code": session.code}) in content
    assert reverse("game:session-state", kwargs={"code": session.code}) in content
    assert "Round 1 is live." in content
    assert "round.js?v=20260607d" in content


@pytest.mark.django_db
def test_host_round_locked_surface_renders_complete_countdown(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Round 1 results." in content
    assert "Round complete" in content
    assert "Start next round" in content
    assert reverse("game:session-next-round", kwargs={"code": session.code}) in content
    assert reverse("game:session-stop-playback", kwargs={"code": session.code}) in content
    assert reverse("game_host:host-results", kwargs={"code": session.code}) in content
    assert "round.js?v=20260607d" in content


@pytest.mark.django_db
def test_host_lobby_redirects_finished_session_to_host_results(client, session):
    _bind_host_session(client, session)
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("game_host:host-results", kwargs={"code": session.code})


@pytest.mark.django_db
def test_host_results_renders_co_winners_and_full_ranking(client, session):
    _bind_host_session(client, session)
    Player.objects.create(session=session, name="Adam", score=900)
    Player.objects.create(session=session, name="Beata", score=900)
    Player.objects.create(session=session, name="Celina", score=400)
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game_host:host-results", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Co-winners" in content
    assert "Adam" in content
    assert "Beata" in content
    assert "Celina" in content
    assert "900 pts" in content
    assert "400 pts" in content
    assert "Start next round" not in content


@pytest.mark.django_db
def test_host_results_redirects_non_finished_session(client, session):
    _bind_host_session(client, session)

    response = client.get(reverse("game_host:host-results", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("game_host:host-lobby", kwargs={"code": session.code})


@pytest.mark.django_db
def test_host_results_owner_guard_blocks_other_browser(client, session):
    _bind_host_session(client, session)
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    other_client = client.__class__()
    response = other_client.get(reverse("game_host:host-results", kwargs={"code": session.code}))

    assert response.status_code == 404


@pytest.mark.django_db
def test_pause_round_marks_round_paused_for_host(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    paused_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=paused_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views.spotify_auth.pause_playback"
    ) as pause_playback:
        response = client.post(
            reverse("game:session-pause", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    current_round.refresh_from_db()
    body = response.json()
    assert response.status_code == 200
    assert current_round.paused_at == paused_at
    assert body["snapshot"]["current_round"]["phase"] == "paused"
    pause_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
    )


@pytest.mark.django_db(transaction=True)
def test_pause_round_calls_spotify_outside_database_transaction(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )

    def assert_not_in_transaction(**_kwargs):
        assert not connection.in_atomic_block

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.pause_playback", side_effect=assert_not_in_transaction):
        response = client.post(
            reverse("game:session-pause", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 200


@pytest.mark.django_db
def test_stop_playback_pauses_spotify_for_locked_round(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )

    with mock.patch("game.views.spotify_auth.pause_playback") as pause_playback:
        response = client.post(
            reverse("game:session-stop-playback", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 200
    assert response.json()["stopped"] is True
    pause_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
    )


@pytest.mark.django_db
def test_stop_playback_rejects_unlocked_round(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )

    with mock.patch("game.views.spotify_auth.pause_playback") as pause_playback:
        response = client.post(
            reverse("game:session-stop-playback", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "round_not_locked"
    pause_playback.assert_not_called()


@pytest.mark.django_db
def test_stop_playback_rejects_stale_round_without_pausing_new_round(client, session, track):
    next_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="next-track",
        artist="Artist B",
        title="Title B",
        duration_ms=180_000,
    )
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=20)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=20),
        deadline_at=timezone.now() - timedelta(seconds=1),
        locked_at=timezone.now() - timedelta(seconds=1),
    )
    Round.objects.create(
        session=session,
        index=2,
        track=next_track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", next_track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )

    with mock.patch("game.views.spotify_auth.pause_playback") as pause_playback:
        response = client.post(
            reverse("game:session-stop-playback", kwargs={"code": session.code}),
            data=json.dumps({"round_index": 1}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_round"
    pause_playback.assert_not_called()


@pytest.mark.django_db
def test_resume_round_shifts_deadline_by_paused_duration(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=15)
    session.save(update_fields=["status", "started_at"])
    paused_at = timezone.now() - timedelta(seconds=5)
    original_deadline = timezone.now() + timedelta(seconds=15)
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=15),
        deadline_at=original_deadline,
        paused_at=paused_at,
    )
    resumed_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=resumed_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback") as transfer_playback, mock.patch(
        "game.views.spotify_auth.resume_playback"
    ) as resume_playback:
        response = client.post(
            reverse("game:session-resume", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    current_round.refresh_from_db()
    body = response.json()
    assert response.status_code == 200
    assert current_round.paused_at is None
    assert current_round.deadline_at == original_deadline + (resumed_at - paused_at)
    assert body["snapshot"]["current_round"]["phase"] == "active"
    transfer_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
        play=True,
    )
    resume_playback.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_resume_round_calls_spotify_outside_database_transaction(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=15)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=15),
        deadline_at=timezone.now() + timedelta(seconds=15),
        paused_at=timezone.now() - timedelta(seconds=5),
    )

    def assert_not_in_transaction(**_kwargs):
        assert not connection.in_atomic_block

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views._resume_round_playback", side_effect=assert_not_in_transaction):
        response = client.post(
            reverse("game:session-resume", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 200


@pytest.mark.django_db
def test_skip_round_locks_round_and_reveals_results(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    joined_player = Player.objects.create(session=session, name="Adam", score=500)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    skipped_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=skipped_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.pause_playback") as pause_playback:
        response = client.post(
            reverse("game:session-skip", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    current_round.refresh_from_db()
    state_response = client.get(reverse("game:session-state", kwargs={"code": session.code}))
    assert response.status_code == 200
    assert current_round.locked_at == skipped_at
    assert state_response.json()["current_round"]["track"]["artist"] == track.artist
    pause_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
    )


@pytest.mark.django_db
def test_skip_round_ten_finishes_session(client, session, track):
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(minutes=5)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=game_views.SESSION_ROUND_LIMIT,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    skipped_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=skipped_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.pause_playback"):
        response = client.post(
            reverse("game:session-skip", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    session.refresh_from_db()
    current_round.refresh_from_db()
    assert response.status_code == 200
    assert current_round.locked_at == skipped_at
    assert session.status == GameSession.Status.FINISHED
    assert session.finished_at == skipped_at


@pytest.mark.django_db
def test_restart_round_replaces_current_round_and_clears_answers(client, session, track):
    replacement_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="replacement-track",
        artist="Artist Z",
        title="Title Z",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="extra-track-1",
        artist="Artist B",
        title="Title B",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="extra-track-2",
        artist="Artist C",
        title="Title C",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="extra-track-3",
        artist="Artist D",
        title="Title D",
        duration_ms=180_000,
    )
    joined_player = Player.objects.create(session=session, name="Adam", score=500)
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=track.artist,
        submitted_at=timezone.now(),
        response_ms=5_000,
        is_correct=True,
        points_awarded=500,
    )

    with mock.patch("game.views._choose_round_track", return_value=replacement_track), mock.patch(
        "game.views._build_answer_options",
        return_value=["Artist B", "Artist C", "Artist D", replacement_track.artist],
    ), mock.patch("game.views._build_round_offset_ms", return_value=12_345), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.start_playback"
    ):
        response = client.post(
            reverse("game:session-restart", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    replacement_round = Round.objects.get(session=session)
    assert response.status_code == 200
    assert Round.objects.filter(session=session).count() == 1
    assert replacement_round.pk != current_round.pk
    assert replacement_round.index == 1
    assert replacement_round.track == replacement_track
    assert replacement_round.offset_ms == 12_345
    assert Answer.objects.filter(round=replacement_round).count() == 0
    assert Answer.objects.filter(round=current_round).count() == 0


@pytest.mark.django_db
def test_restart_round_replaces_non_first_round_and_rolls_back_points(client, session, track):
    current_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="current-track",
        artist="Artist Current",
        title="Current Title",
        duration_ms=180_000,
    )
    replacement_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="replacement-track",
        artist="Artist Z",
        title="Title Z",
        duration_ms=180_000,
    )
    _add_round_tracks(session, count=3, prefix="extra-track")
    joined_player = Player.objects.create(session=session, name="Adam", score=900)
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=60)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=60),
        deadline_at=timezone.now() - timedelta(seconds=30),
        locked_at=timezone.now() - timedelta(seconds=30),
    )
    current_round = Round.objects.create(
        session=session,
        index=2,
        track=current_track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", current_track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=current_track.artist,
        submitted_at=timezone.now(),
        response_ms=5_000,
        is_correct=True,
        points_awarded=500,
    )

    with mock.patch("game.views._choose_round_track", return_value=replacement_track), mock.patch(
        "game.views._build_answer_options",
        return_value=["Artist 1", "Artist 2", "Artist 3", replacement_track.artist],
    ), mock.patch("game.views._build_round_offset_ms", return_value=12_345), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.start_playback"
    ):
        response = client.post(
            reverse("game:session-restart", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    joined_player.refresh_from_db()
    replacement_round = Round.objects.get(session=session, index=2)
    assert response.status_code == 200
    assert Round.objects.filter(session=session).count() == 2
    assert replacement_round.pk != current_round.pk
    assert replacement_round.track == replacement_track
    assert joined_player.score == 400
    assert Answer.objects.filter(round=replacement_round).count() == 0


@pytest.mark.django_db
def test_restart_round_rejects_locked_round(client, session, track):
    _add_round_tracks(session, count=4)
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )

    response = client.post(
        reverse("game:session-restart", kwargs={"code": session.code}),
        HTTP_X_REQUESTED_WITH="fetch",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "round_locked"


@pytest.mark.django_db(transaction=True)
def test_restart_round_calls_spotify_outside_database_transaction(client, session, track):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"replacement-{index}",
            artist=f"Artist {index}",
            title=f"Replacement {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )

    def assert_fetch_not_in_transaction(*, spotify_track_id, **_kwargs):
        assert not connection.in_atomic_block
        return {
            "spotify_track_id": spotify_track_id,
            "is_playable": True,
            "restriction_reason": None,
        }

    def assert_start_not_in_transaction(**_kwargs):
        assert not connection.in_atomic_block

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch("game.views.spotify_auth.fetch_track_details", side_effect=assert_fetch_not_in_transaction), mock.patch(
        "game.views._start_round_playback", side_effect=assert_start_not_in_transaction
    ):
        response = client.post(
            reverse("game:session-restart", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 200


@pytest.mark.django_db
def test_pause_resume_pause_sequence_keeps_round_pauseable(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )

    paused_at = timezone.now()
    resumed_at = paused_at + timedelta(seconds=3)
    paused_again_at = resumed_at + timedelta(seconds=4)

    with mock.patch("game.views.timezone.now", return_value=paused_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views.spotify_auth.pause_playback"
    ) as first_pause:
        first_response = client.post(
            reverse("game:session-pause", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    with mock.patch("game.views.timezone.now", return_value=resumed_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.resume_playback"
    ) as resume_playback:
        resume_response = client.post(
            reverse("game:session-resume", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )
    resume_playback.assert_not_called()

    with mock.patch("game.views.timezone.now", return_value=paused_again_at), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views.spotify_auth.pause_playback"
    ) as second_pause:
        second_response = client.post(
            reverse("game:session-pause", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    current_round.refresh_from_db()
    assert first_response.status_code == 200
    assert resume_response.status_code == 200
    assert second_response.status_code == 200
    assert current_round.paused_at == paused_again_at
    assert second_response.json()["snapshot"]["current_round"]["phase"] == "paused"
    assert first_pause.call_count == 1
    second_pause.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
    )


@pytest.mark.django_db
def test_pause_round_reselects_live_device_when_stored_device_drifted(client, session, track):
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="browser-device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=10)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "desktop-device-99", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.pause_playback") as pause_playback:
        response = client.post(
            reverse("game:session-pause", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert response.status_code == 200
    assert client.session[game_views.SPOTIFY_PLAYBACK_SESSION_KEY]["device_id"] == "desktop-device-99"
    pause_playback.assert_called_once_with(
        access_token="access-token",
        device_id="desktop-device-99",
    )

@pytest.mark.django_db
def test_start_round_rejects_host_without_ready_playback(client, session):
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)

    response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    session.refresh_from_db()
    assert response.status_code == 409
    assert session.status == GameSession.Status.LOBBY
    assert Round.objects.count() == 0


@pytest.mark.django_db
def test_start_round_rejects_non_premium_host_before_spotify_playback(client, session):
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client, product="free")
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "spotify_premium_required"
    assert "Spotify Premium is required" in response.json()["error"]["message"]
    assert Round.objects.count() == 0


@pytest.mark.django_db
def test_session_playback_ready_accepts_csrf_protected_fetch(client, session):
    csrf_client = Client(enforce_csrf_checks=True)
    _set_host_auth(csrf_client)
    _bind_host_session(csrf_client, session)

    lobby_response = csrf_client.get(reverse("game_host:host-lobby", kwargs={"code": session.code}))
    csrf_token = csrf_client.cookies["csrftoken"].value

    with mock.patch(
        "game.views.spotify_auth.fetch_available_devices",
        return_value=[{"id": "device-42", "is_restricted": False}],
    ):
        response = csrf_client.post(
            reverse("game:session-playback-ready", kwargs={"code": session.code}),
            data=json.dumps({"device_id": "device-42"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert lobby_response.status_code == 200
    assert response.status_code == 200
    assert response.json() == {"ready": True, "device_id": "device-42"}


@pytest.mark.django_db
def test_session_playback_ready_rejects_restricted_spotify_device(client, session):
    _set_host_auth(client)
    _bind_host_session(client, session)

    with mock.patch(
        "game.views.spotify_auth.fetch_available_devices",
        return_value=[{"id": "device-42", "is_restricted": True}],
    ):
        response = client.post(
            reverse("game:session-playback-ready", kwargs={"code": session.code}),
            data=json.dumps({"device_id": "device-42"}),
            content_type="application/json",
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spotify_device_not_ready"
    assert "restricted" in response.json()["error"]["message"].lower()
    assert game_views.SPOTIFY_PLAYBACK_SESSION_KEY not in client.session


@pytest.mark.django_db
def test_session_playback_diagnostics_returns_live_device_and_track_checks(client, session):
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="track-1",
        artist="Artist 1",
        title="Title 1",
        duration_ms=180_000,
    )
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    with mock.patch(
        "game.views.spotify_auth.fetch_available_devices",
        return_value=[
            {
                "id": "device-42",
                "name": "melo-gierka Host Player",
                "type": "computer",
                "is_active": True,
                "is_private_session": False,
                "is_restricted": False,
            }
        ],
    ), mock.patch(
        "game.views.spotify_auth.fetch_track_details",
        return_value={
            "spotify_track_id": "track-1",
            "is_playable": True,
            "restriction_reason": None,
        },
    ):
        response = client.get(reverse("game:session-playback-diagnostics", kwargs={"code": session.code}))

    body = response.json()
    assert response.status_code == 200
    assert body["host"]["product"] == "premium"
    assert body["playback_state"]["device_id"] == "device-42"
    assert body["devices"] == [
        {
            "id": "device-42",
            "name": "melo-gierka Host Player",
            "type": "computer",
            "is_active": True,
            "is_private_session": False,
            "is_restricted": False,
        }
    ]
    assert body["track_checks"] == [
        {
            "spotify_track_id": "track-1",
            "artist": "Artist 1",
            "title": "Title 1",
            "is_playable": True,
            "restriction_reason": None,
        }
    ]

@pytest.mark.django_db
def test_start_round_creates_round_and_returns_host_playback_bootstrap(client, session):
    tracks = [
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )
        for index in range(1, 5)
    ]
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback") as transfer_playback, mock.patch(
        "game.views.spotify_auth.start_playback"
    ) as start_playback:
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    session.refresh_from_db()
    created_round = Round.objects.get(session=session)
    body = response.json()
    assert response.status_code == 200
    assert session.status == GameSession.Status.PLAYING
    assert created_round.index == 1
    assert created_round.track in tracks
    assert len(created_round.answer_options) == 4
    assert len(set(created_round.answer_options)) == 4
    assert created_round.track.artist in created_round.answer_options
    assert 36_000 <= created_round.offset_ms <= 144_000
    assert body["playback"] == {
        "device_id": "device-42",
        "spotify_track_id": created_round.track.spotify_track_id,
        "offset_ms": created_round.offset_ms,
    }
    transfer_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
        play=True,
    )
    start_playback.assert_called_once_with(
        access_token="access-token",
        device_id="device-42",
        spotify_track_id=created_round.track.spotify_track_id,
        position_ms=created_round.offset_ms,
    )


@pytest.mark.django_db
def test_next_round_creates_round_two_from_locked_result(client, session, track):
    next_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="next-track",
        artist="Artist Next",
        title="Next Title",
        duration_ms=180_000,
    )
    _add_round_tracks(session, count=3, prefix="option-track")
    Player.objects.create(session=session, name="Adam", score=500)
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=30)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=30),
        deadline_at=timezone.now() - timedelta(seconds=1),
        locked_at=timezone.now() - timedelta(seconds=1),
    )

    with mock.patch("game.views._choose_round_track", return_value=next_track), mock.patch(
        "game.views._build_answer_options",
        return_value=["Artist 1", "Artist 2", "Artist 3", next_track.artist],
    ), mock.patch("game.views._build_round_offset_ms", return_value=22_000), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.start_playback"
    ) as start_playback:
        response = client.post(
            reverse("game:session-next-round", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    session.refresh_from_db()
    created_round = Round.objects.get(session=session, index=2)
    body = response.json()
    assert response.status_code == 200
    assert session.status == GameSession.Status.PLAYING
    assert created_round.track == next_track
    assert created_round.offset_ms == 22_000
    assert body["snapshot"]["current_round"]["index"] == 2
    assert body["playback"] == {
        "device_id": "device-42",
        "spotify_track_id": next_track.spotify_track_id,
        "offset_ms": 22_000,
    }
    start_playback.assert_called_once()


@pytest.mark.django_db
def test_next_round_rejects_active_round_without_duplicate(client, session, track):
    _add_round_tracks(session, count=4)
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )

    response = client.post(
        reverse("game:session-next-round", kwargs={"code": session.code}),
        HTTP_X_REQUESTED_WITH="fetch",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "round_not_locked"
    assert Round.objects.filter(session=session).count() == 1



@pytest.mark.django_db
def test_next_round_rejects_duplicate_after_advance_without_duplicate(client, session, track):
    next_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="next-track",
        artist="Artist Next",
        title="Next Title",
        duration_ms=180_000,
    )
    _add_round_tracks(session, count=3, prefix="option-track")
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=30)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=30),
        deadline_at=timezone.now() - timedelta(seconds=1),
        locked_at=timezone.now() - timedelta(seconds=1),
    )

    with mock.patch("game.views._choose_round_track", return_value=next_track), mock.patch(
        "game.views._build_answer_options",
        return_value=["Artist 1", "Artist 2", "Artist 3", next_track.artist],
    ), mock.patch("game.views._build_round_offset_ms", return_value=22_000), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.start_playback"
    ):
        first_response = client.post(
            reverse("game:session-next-round", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    second_response = client.post(
        reverse("game:session-next-round", kwargs={"code": session.code}),
        HTTP_X_REQUESTED_WITH="fetch",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "round_not_locked"
    assert Round.objects.filter(session=session).count() == 2


@pytest.mark.django_db
def test_full_session_happy_path_completes_ten_rounds_with_unique_tracks(client, session, track):
    host_client = client
    player_client = Client()
    tracks = [track]
    tracks.extend(_add_round_tracks(session, count=9, prefix="full-session-track", start=2))
    joined_player = Player.objects.create(session=session, name="Adam")
    _set_host_auth(host_client)
    _bind_host_session(host_client, session)
    _set_playback_ready(host_client, session, device_id="device-42")
    _bind_player_session(player_client, session, joined_player)

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.fetch_track_details") as fetch_track_details, mock.patch(
        "game.views.spotify_auth.transfer_playback"
    ), mock.patch("game.views.spotify_auth.start_playback"):
        fetch_track_details.return_value = {
            "spotify_track_id": "track-id",
            "is_playable": True,
            "restriction_reason": None,
        }

        start_response = host_client.post(reverse("game:session-start-round", kwargs={"code": session.code}))
        assert start_response.status_code == 200

        for round_index in range(1, game_views.SESSION_ROUND_LIMIT + 1):
            current_round = Round.objects.get(session=session, index=round_index)
            answer_response = player_client.post(
                reverse("game:session-answer", kwargs={"code": session.code}),
                data=json.dumps({"artist": current_round.track.artist}),
                content_type="application/json",
            )
            assert answer_response.status_code == 200

            if round_index < game_views.SESSION_ROUND_LIMIT:
                next_response = host_client.post(
                    reverse("game:session-next-round", kwargs={"code": session.code}),
                    HTTP_X_REQUESTED_WITH="fetch",
                )
                assert next_response.status_code == 200

    session.refresh_from_db()
    joined_player.refresh_from_db()
    used_track_ids = list(session.rounds.order_by("index").values_list("track_id", flat=True))
    host_results = host_client.get(reverse("game_host:host-results", kwargs={"code": session.code}))
    player_results = player_client.get(reverse("game_host:player-results", kwargs={"code": session.code}))

    assert session.status == GameSession.Status.FINISHED
    assert session.finished_at is not None
    assert session.rounds.count() == game_views.SESSION_ROUND_LIMIT
    assert len(set(used_track_ids)) == game_views.SESSION_ROUND_LIMIT
    assert set(used_track_ids) == {created_track.pk for created_track in tracks}
    assert joined_player.score > 0
    assert host_results.status_code == 200
    assert player_results.status_code == 200
    assert "Adam (you)" in player_results.content.decode()


@pytest.mark.django_db
def test_full_session_timeout_round_missing_answer_scores_zero_and_can_advance(client, session, track):
    next_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="next-track",
        artist="Artist Next",
        title="Next Title",
        duration_ms=180_000,
    )
    _add_round_tracks(session, count=3, prefix="timeout-option")
    joined_player = Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=60)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=31),
        deadline_at=timezone.now() - timedelta(seconds=1),
    )

    state_response = client.get(reverse("game:session-state", kwargs={"code": session.code}))
    current_round.refresh_from_db()
    joined_player.refresh_from_db()

    assert state_response.status_code == 200
    assert state_response.json()["current_round"]["phase"] == "locked"
    assert current_round.locked_at is not None
    assert not Answer.objects.filter(round=current_round, player=joined_player).exists()
    assert joined_player.score == 0

    with mock.patch("game.views._choose_round_track", return_value=next_track), mock.patch(
        "game.views._build_answer_options",
        return_value=["Artist 1", "Artist 2", "Artist 3", next_track.artist],
    ), mock.patch("game.views._build_round_offset_ms", return_value=22_000), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views.spotify_auth.start_playback"
    ):
        next_response = client.post(
            reverse("game:session-next-round", kwargs={"code": session.code}),
            HTTP_X_REQUESTED_WITH="fetch",
        )

    assert next_response.status_code == 200
    assert Round.objects.filter(session=session, index=2, track=next_track).exists()


@pytest.mark.django_db
def test_next_round_rejects_after_round_limit_and_finishes_session(client, session, track):
    _add_round_tracks(session, count=4)
    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(minutes=5)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=game_views.SESSION_ROUND_LIMIT,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=30),
        deadline_at=timezone.now() - timedelta(seconds=1),
        locked_at=timezone.now() - timedelta(seconds=1),
    )

    response = client.post(
        reverse("game:session-next-round", kwargs={"code": session.code}),
        HTTP_X_REQUESTED_WITH="fetch",
    )

    session.refresh_from_db()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_finished"
    assert session.status == GameSession.Status.FINISHED
    assert session.finished_at is not None


@pytest.mark.django_db(transaction=True)
def test_start_round_calls_spotify_outside_database_transaction(client, session):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    def assert_fetch_not_in_transaction(*, spotify_track_id, **_kwargs):
        assert not connection.in_atomic_block
        return {
            "spotify_track_id": spotify_track_id,
            "is_playable": True,
            "restriction_reason": None,
        }

    def assert_start_not_in_transaction(**_kwargs):
        assert not connection.in_atomic_block

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch("game.views.spotify_auth.fetch_track_details", side_effect=assert_fetch_not_in_transaction), mock.patch(
        "game.views._start_round_playback", side_effect=assert_start_not_in_transaction
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 200


@pytest.mark.django_db
def test_start_round_retries_playback_start_when_device_is_not_active_yet(client, session, monkeypatch):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    start_attempts = {"count": 0}

    monkeypatch.setattr(spotify_auth, "transfer_playback", lambda **_kwargs: None)

    def flaky_start_playback(**_kwargs):
        start_attempts["count"] += 1
        if start_attempts["count"] < 3:
            raise spotify_auth.SpotifyOAuthError(
                "Spotify playback start failed.",
                status_code=404,
                response_body={"error": {"message": "No active device found"}},
            )

    monkeypatch.setattr(spotify_auth, "start_playback", flaky_start_playback)

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert start_attempts["count"] == 3


@pytest.mark.django_db
def test_start_round_retries_transient_spotify_restriction_unknown(client, session, monkeypatch):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    start_attempts = {"count": 0}

    monkeypatch.setattr(spotify_auth, "transfer_playback", lambda **_kwargs: None)

    def flaky_start_playback(**_kwargs):
        start_attempts["count"] += 1
        if start_attempts["count"] < 3:
            raise spotify_auth.SpotifyOAuthError(
                "Spotify playback start failed.",
                status_code=403,
                response_body={
                    "error": {
                        "status": 403,
                        "message": "Player command failed: Restriction violated",
                        "reason": "UNKNOWN",
                    }
                },
            )

    monkeypatch.setattr(spotify_auth, "start_playback", flaky_start_playback)

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert start_attempts["count"] == 3


@pytest.mark.django_db
def test_start_round_skips_unplayable_tracks_for_host_account(client, session, monkeypatch):
    blocked_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="track-blocked",
        artist="Artist 1",
        title="Blocked Title",
        duration_ms=180_000,
    )
    playable_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="track-playable",
        artist="Artist 2",
        title="Playable Title",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="track-3",
        artist="Artist 3",
        title="Title 3",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="track-4",
        artist="Artist 4",
        title="Title 4",
        duration_ms=180_000,
    )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    choices = iter([blocked_track, playable_track])

    def choose_candidate(sequence):
        first_item = sequence[0]
        if isinstance(first_item, Track):
            return next(choices)
        return first_item

    monkeypatch.setattr(game_views.secrets, "choice", choose_candidate)
    monkeypatch.setattr(
        spotify_auth,
        "fetch_track_details",
        lambda *, access_token, spotify_track_id: {
            "spotify_track_id": spotify_track_id,
            "is_playable": spotify_track_id != blocked_track.spotify_track_id,
            "restriction_reason": "market" if spotify_track_id == blocked_track.spotify_track_id else None,
        },
    )
    monkeypatch.setattr(spotify_auth, "transfer_playback", lambda **_kwargs: None)
    monkeypatch.setattr(spotify_auth, "start_playback", lambda **_kwargs: None)

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    created_round = Round.objects.get(session=session)
    assert response.status_code == 200
    assert created_round.track == playable_track


@pytest.mark.django_db
def test_start_round_skips_tracks_with_invalid_spotify_ids(client, session, monkeypatch):
    invalid_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="invalid-track-id",
        artist="Artist 1",
        title="Invalid Title",
        duration_ms=180_000,
    )
    playable_track = Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="trackplayable0000000001",
        artist="Artist 2",
        title="Playable Title",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="trackplayable0000000002",
        artist="Artist 3",
        title="Title 3",
        duration_ms=180_000,
    )
    Track.objects.create(
        music_set=session.music_set,
        spotify_track_id="trackplayable0000000003",
        artist="Artist 4",
        title="Title 4",
        duration_ms=180_000,
    )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    choices = iter([invalid_track, playable_track])

    def choose_candidate(sequence):
        first_item = sequence[0]
        if isinstance(first_item, Track):
            return next(choices)
        return first_item

    monkeypatch.setattr(game_views.secrets, "choice", choose_candidate)

    def fetch_track_details(*, access_token, spotify_track_id):
        if spotify_track_id == invalid_track.spotify_track_id:
            raise spotify_auth.SpotifyOAuthError(
                "Spotify track lookup failed.",
                status_code=400,
                response_body={"error": {"status": 400, "message": "Invalid base62 id"}},
            )
        return {
            "spotify_track_id": spotify_track_id,
            "is_playable": True,
            "restriction_reason": None,
        }

    monkeypatch.setattr(spotify_auth, "fetch_track_details", fetch_track_details)
    monkeypatch.setattr(spotify_auth, "transfer_playback", lambda **_kwargs: None)
    monkeypatch.setattr(spotify_auth, "start_playback", lambda **_kwargs: None)

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": True},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    created_round = Round.objects.get(session=session)
    assert response.status_code == 200
    assert created_round.track == playable_track


@pytest.mark.django_db
def test_start_round_rejects_restricted_spotify_device(client, session):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": True},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spotify_device_not_ready"
    assert Round.objects.count() == 0


@pytest.mark.django_db
def test_start_round_rejects_browser_player_that_never_becomes_active(client, session):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="device-42")

    with mock.patch(
        "game.views.spotify_auth.fetch_track_details",
        return_value={
            "spotify_track_id": "track-1",
            "is_playable": True,
            "restriction_reason": None,
        },
    ), mock.patch("game.views.spotify_auth.transfer_playback"), mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "device-42", "is_restricted": False},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "device-42", "is_restricted": False, "is_active": False},
    ):
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "spotify_device_not_active"
    assert "never became the active playback device" in response.json()["error"]["message"]
    assert Round.objects.count() == 0


@pytest.mark.django_db
def test_start_round_falls_back_to_live_commandable_device_when_browser_player_disappears(client, session):
    for index in range(1, 5):
        Track.objects.create(
            music_set=session.music_set,
            spotify_track_id=f"track-{index}",
            artist=f"Artist {index}",
            title=f"Title {index}",
            duration_ms=180_000,
        )

    Player.objects.create(session=session, name="Adam")
    _set_host_auth(client)
    _bind_host_session(client, session)
    _set_playback_ready(client, session, device_id="browser-device-42")

    with mock.patch(
        "game.views._resolve_start_round_playback_device",
        return_value={"id": "desktop-device-99", "is_restricted": False, "is_active": True},
    ), mock.patch(
        "game.views._wait_for_active_playback_device",
        return_value={"id": "desktop-device-99", "is_restricted": False, "is_active": True},
    ), mock.patch("game.views.spotify_auth.transfer_playback") as transfer_playback, mock.patch(
        "game.views.spotify_auth.start_playback"
    ) as start_playback:
        response = client.post(reverse("game:session-start-round", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert client.session[game_views.SPOTIFY_PLAYBACK_SESSION_KEY]["device_id"] == "desktop-device-99"
    transfer_playback.assert_called_once_with(
        access_token="access-token",
        device_id="desktop-device-99",
        play=True,
    )
    assert start_playback.call_args.kwargs["device_id"] == "desktop-device-99"


def test_resolve_start_round_playback_device_prefers_other_commandable_device_when_browser_is_inactive(monkeypatch):
    monkeypatch.setattr(
        spotify_auth,
        "fetch_available_devices",
        lambda *, access_token: [
            {"id": "browser-device", "is_restricted": False, "is_active": False},
            {"id": "desktop-device", "is_restricted": False, "is_active": False},
        ],
    )

    resolved = game_views._resolve_start_round_playback_device(
        access_token="access-token",
        preferred_device_id="browser-device",
    )

    assert resolved == {"id": "desktop-device", "is_restricted": False, "is_active": False}

@pytest.mark.django_db
def test_session_state_hides_correct_track_details_for_active_round(client, session, track):
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    round_started_at = timezone.now()
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        started_at=round_started_at,
        deadline_at=round_started_at + timedelta(seconds=30),
        answer_options=["Artist A", "Artist B", "Artist C", "Artist D"],
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    round_body = response.json()["current_round"]
    assert response.status_code == 200
    assert round_body["index"] == 1
    assert round_body["offset_ms"] == 30_000
    assert round_body["answer_options"] == ["Artist A", "Artist B", "Artist C", "Artist D"]
    assert parse_datetime(round_body["deadline_at"]) is not None
    assert "track" not in round_body


@pytest.mark.django_db
def test_session_state_locks_expired_round_on_poll(client, session, track):
    Player.objects.create(session=session, name="Adam")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=60)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=31),
        deadline_at=timezone.now() - timedelta(seconds=1),
    )
    locked_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=locked_at):
        response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    current_round.refresh_from_db()
    body = response.json()
    assert response.status_code == 200
    assert current_round.locked_at == locked_at
    assert body["current_round"]["phase"] == "locked"
    assert body["current_round"]["track"]["artist"] == track.artist


@pytest.mark.django_db
def test_session_state_finishes_session_when_round_ten_expires(client, session, track):
    Player.objects.create(session=session, name="Adam")
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(minutes=5)
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=game_views.SESSION_ROUND_LIMIT,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=31),
        deadline_at=timezone.now() - timedelta(seconds=1),
    )
    finished_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=finished_at):
        response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    session.refresh_from_db()
    body = response.json()
    assert response.status_code == 200
    assert session.status == GameSession.Status.FINISHED
    assert session.finished_at == finished_at
    assert body["status"] == GameSession.Status.FINISHED
    assert parse_datetime(body["finished_at"]) is not None


@pytest.mark.django_db
def test_player_lobby_renders_current_player_polling_hooks(client, session):
    client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "data-lobby-state-root" in content
    assert 'data-current-player="Adam"' in content


@pytest.mark.django_db
def test_player_lobby_branches_to_round_surface_for_bound_player(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "data-round-state-root" in content
    assert reverse("game:session-state", kwargs={"code": session.code}) in content
    assert reverse("game:session-answer", kwargs={"code": session.code}) in content
    assert reverse("game_host:player-results", kwargs={"code": session.code}) in content
    assert "You are in the lobby." not in content
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_player_lobby_renders_results_link_for_lobby_polling(client, session):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert reverse("game_host:player-results", kwargs={"code": session.code}) in content
    assert "lobby.js?v=20260607a" in content


@pytest.mark.django_db
def test_player_lobby_redirects_finished_session_to_player_results(client, session):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("game_host:player-results", kwargs={"code": session.code})


@pytest.mark.django_db
def test_player_results_renders_ranking_and_marks_bound_player(client, session):
    adam = Player.objects.create(session=session, name="Adam", score=500)
    Player.objects.create(session=session, name="Beata", score=900)
    Player.objects.create(session=session, name="Celina", score=900)
    _bind_player_session(client, session, adam)
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game_host:player-results", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Co-winners" in content
    assert "Beata" in content
    assert "Celina" in content
    assert "Adam (you)" in content
    assert "900 pts" in content
    assert "500 pts" in content


@pytest.mark.django_db
def test_player_results_redirects_non_finished_session(client, session):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)

    response = client.get(reverse("game_host:player-results", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == reverse("game_host:player-lobby", kwargs={"code": session.code})


@pytest.mark.django_db
def test_player_results_requires_bound_player(client, session):
    session.status = GameSession.Status.FINISHED
    session.finished_at = timezone.now()
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game_host:player-results", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == f"{reverse('game_host:player-join')}?code={session.code}"


@pytest.mark.django_db
def test_player_answer_persists_first_click_scores_and_locks_single_player_round(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=5),
        deadline_at=timezone.now() + timedelta(seconds=25),
    )

    response = client.post(
        reverse("game:session-answer", kwargs={"code": session.code}),
        data=json.dumps({"artist": track.artist}),
        content_type="application/json",
    )

    current_round.refresh_from_db()
    joined_player.refresh_from_db()
    stored_answer = Answer.objects.get(round=current_round, player=joined_player)
    assert response.status_code == 200
    assert stored_answer.selected_artist == track.artist
    assert stored_answer.is_correct is True
    assert stored_answer.points_awarded > 0
    assert joined_player.score == stored_answer.points_awarded
    assert current_round.locked_at is not None


@pytest.mark.django_db
def test_late_answer_locks_round_without_answer_or_points(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam", score=200)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(seconds=60)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=31),
        deadline_at=timezone.now() - timedelta(seconds=1),
    )

    response = client.post(
        reverse("game:session-answer", kwargs={"code": session.code}),
        data=json.dumps({"artist": track.artist}),
        content_type="application/json",
    )

    current_round.refresh_from_db()
    joined_player.refresh_from_db()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "round_locked"
    assert current_round.locked_at is not None
    assert Answer.objects.filter(round=current_round, player=joined_player).count() == 0
    assert joined_player.score == 200


@pytest.mark.django_db
def test_last_answer_in_round_ten_finishes_session(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now() - timedelta(minutes=5)
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=game_views.SESSION_ROUND_LIMIT,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=5),
        deadline_at=timezone.now() + timedelta(seconds=25),
    )
    answered_at = timezone.now()

    with mock.patch("game.views.timezone.now", return_value=answered_at):
        response = client.post(
            reverse("game:session-answer", kwargs={"code": session.code}),
            data=json.dumps({"artist": track.artist}),
            content_type="application/json",
        )

    session.refresh_from_db()
    current_round.refresh_from_db()
    assert response.status_code == 200
    assert current_round.locked_at == answered_at
    assert session.status == GameSession.Status.FINISHED
    assert session.finished_at == answered_at


@pytest.mark.django_db
def test_session_state_returns_bound_player_answer_without_revealing_result_before_lock(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist="Artist B",
        submitted_at=timezone.now(),
        response_ms=1_250,
        is_correct=False,
        points_awarded=0,
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    round_body = response.json()["current_round"]
    assert response.status_code == 200
    assert round_body["viewer_answer"] == {
        "selected_artist": "Artist B",
        "submitted_at": round_body["viewer_answer"]["submitted_at"],
        "response_ms": 1_250,
    }
    assert "track" not in round_body
    assert "is_correct" not in round_body["viewer_answer"]
    assert "points_awarded" not in round_body["viewer_answer"]


@pytest.mark.django_db
def test_session_state_reveals_viewer_result_after_round_lock(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam", score=700)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=track.artist,
        submitted_at=timezone.now(),
        response_ms=10_000,
        is_correct=True,
        points_awarded=700,
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    round_body = response.json()["current_round"]
    assert response.status_code == 200
    assert round_body["track"]["artist"] == track.artist
    assert round_body["viewer_answer"]["selected_artist"] == track.artist
    assert round_body["viewer_answer"]["is_correct"] is True
    assert round_body["viewer_answer"]["points_awarded"] == 700


@pytest.mark.django_db
def test_session_state_hides_updated_scores_until_round_lock(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam", score=500)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=track.artist,
        submitted_at=timezone.now(),
        response_ms=10_000,
        is_correct=True,
        points_awarded=500,
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert response.json()["players"] == [
        {
            "name": "Adam",
            "score": 0,
            "joined_at": response.json()["players"][0]["joined_at"],
        }
    ]


@pytest.mark.django_db
def test_session_state_reveals_updated_scores_after_round_lock(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam", score=500)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=track.artist,
        submitted_at=timezone.now(),
        response_ms=10_000,
        is_correct=True,
        points_awarded=500,
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    assert response.status_code == 200
    assert response.json()["players"] == [
        {
            "name": "Adam",
            "score": 500,
            "joined_at": response.json()["players"][0]["joined_at"],
        }
    ]


@pytest.mark.django_db
def test_player_answer_rejects_second_submission_from_same_bound_player(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    Player.objects.create(session=session, name="Beata")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )

    first_response = client.post(
        reverse("game:session-answer", kwargs={"code": session.code}),
        data=json.dumps({"artist": track.artist}),
        content_type="application/json",
    )
    second_response = client.post(
        reverse("game:session-answer", kwargs={"code": session.code}),
        data=json.dumps({"artist": "Artist A"}),
        content_type="application/json",
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "answer_already_submitted"
    assert Answer.objects.filter(round=current_round, player=joined_player).count() == 1


@pytest.mark.django_db
def test_player_answer_uses_linear_time_weighted_scoring(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    started_at = timezone.now()
    session.status = GameSession.Status.PLAYING
    session.started_at = started_at
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=started_at,
        deadline_at=started_at + timedelta(seconds=30),
    )
    answer_time = started_at + timedelta(seconds=5)

    with mock.patch("game.views.timezone.now", return_value=answer_time):
        response = client.post(
            reverse("game:session-answer", kwargs={"code": session.code}),
            data=json.dumps({"artist": track.artist}),
            content_type="application/json",
        )

    joined_player.refresh_from_db()
    stored_answer = Answer.objects.get(round=current_round, player=joined_player)
    assert response.status_code == 200
    assert stored_answer.response_ms == 5_000
    assert stored_answer.points_awarded == 833
    assert joined_player.score == 833


@pytest.mark.django_db
def test_last_joined_player_answer_locks_round_when_all_players_have_answered(client, session, track):
    first_player = Player.objects.create(session=session, name="Adam")
    second_player = Player.objects.create(session=session, name="Beata")
    _bind_player_session(client, session, second_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )
    Answer.objects.create(
        round=current_round,
        player=first_player,
        selected_artist="Artist A",
        submitted_at=timezone.now(),
        response_ms=2_000,
        is_correct=False,
        points_awarded=0,
    )

    response = client.post(
        reverse("game:session-answer", kwargs={"code": session.code}),
        data=json.dumps({"artist": track.artist}),
        content_type="application/json",
    )

    current_round.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["locked"] is True
    assert current_round.locked_at is not None


@pytest.mark.django_db
def test_player_lobby_refresh_preserves_answered_waiting_state(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam")
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now(),
        deadline_at=timezone.now() + timedelta(seconds=30),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist="Artist B",
        submitted_at=timezone.now(),
        response_ms=2_000,
        is_correct=False,
        points_awarded=0,
    )

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Answer locked: Artist B. Waiting for the round to close." in content
    assert "data-answer-options" in content
    assert "hidden" in content


@pytest.mark.django_db
def test_player_lobby_branches_to_locked_result_surface(client, session, track):
    joined_player = Player.objects.create(session=session, name="Adam", score=500)
    _bind_player_session(client, session, joined_player)
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    current_round = Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", track.artist],
        started_at=timezone.now() - timedelta(seconds=10),
        deadline_at=timezone.now() + timedelta(seconds=20),
        locked_at=timezone.now(),
    )
    Answer.objects.create(
        round=current_round,
        player=joined_player,
        selected_artist=track.artist,
        submitted_at=timezone.now(),
        response_ms=10_000,
        is_correct=True,
        points_awarded=500,
    )

    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Round 1 results." in content
    assert "Round complete" in content
    assert "Correct artist: Artist A." in content
    assert "data-round-results" in content
    assert reverse("game_host:player-results", kwargs={"code": session.code}) in content
    assert "round.js?v=20260607d" in content


@pytest.mark.django_db
def test_player_join_rejects_invalid_code_inline(client):
    response = client.post(
        reverse("game_host:player-join"),
        {"code": "9999", "name": "Adam"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Enter a valid session code." in content
    assert Player.objects.count() == 0


@pytest.mark.django_db
def test_player_join_rejects_deleted_session_inline(client, session, monkeypatch):
    class DeletedSessionQuerySet:
        def get(self, **_kwargs):
            raise GameSession.DoesNotExist

    monkeypatch.setattr(
        game_views.GameSession.objects,
        "select_for_update",
        lambda: DeletedSessionQuerySet(),
    )

    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Enter a valid session code." in content
    assert Player.objects.count() == 0


@pytest.mark.django_db
def test_duplicate_name_rejects_player_join_with_suggestion(client, session):
    Player.objects.create(session=session, name="Adam")

    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "That name is already taken in this session." in content
    assert "Adam 2" in content
    assert Player.objects.filter(session=session, name="Adam").count() == 1


@pytest.mark.django_db
def test_player_join_handles_concurrent_duplicate_name_inline(client, session, monkeypatch):
    create_called = False
    suggestion_called = False

    def raise_integrity_error(**_kwargs):
        nonlocal create_called
        create_called = True
        raise IntegrityError

    def fake_suggestion(**_kwargs):
        nonlocal suggestion_called
        suggestion_called = True
        return "Adam 2"

    monkeypatch.setattr(
        game_views.Player.objects,
        "create",
        raise_integrity_error,
    )
    monkeypatch.setattr(
        game_views,
        "build_player_name_suggestion",
        fake_suggestion,
    )

    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert create_called is True
    assert suggestion_called is True
    assert "already taken in this session." in content
    assert "Adam 2" in content
    assert Player.objects.count() == 0


@pytest.mark.django_db
def test_case_variant_name_is_allowed_in_same_session(client, session):
    Player.objects.create(session=session, name="Adam")

    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "ADAM"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "game_host:player-lobby",
        kwargs={"code": session.code},
    )
    assert Player.objects.filter(session=session, name="Adam").count() == 1
    assert Player.objects.filter(session=session, name="ADAM").count() == 1


@pytest.mark.django_db
def test_late_join_rejects_non_lobby_session(client, session):
    session.status = GameSession.Status.PLAYING
    session.save(update_fields=["status"])

    response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "This session is no longer accepting players." in content
    assert Player.objects.count() == 0


@pytest.mark.django_db
def test_player_lobby_refresh_keeps_same_player_without_creating_new_row(client, session):
    join_response = client.post(
        reverse("game_host:player-join"),
        {"code": session.code, "name": "Adam"},
    )

    player_id = client.session[game_views.PLAYER_SESSION_BINDING_SESSION_KEY]["player_id"]

    first_refresh = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))
    second_refresh = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    assert join_response.status_code == 302
    assert first_refresh.status_code == 200
    assert second_refresh.status_code == 200
    assert Player.objects.filter(session=session, name="Adam").count() == 1
    assert client.session[game_views.PLAYER_SESSION_BINDING_SESSION_KEY]["player_id"] == player_id


@pytest.mark.django_db
def test_player_join_redirects_unbound_browser_back_to_join(client, session):
    response = client.get(reverse("game_host:player-lobby", kwargs={"code": session.code}))

    assert response.status_code == 302
    assert response.headers["Location"] == (
        f"{reverse('game_host:player-join')}?code={session.code}"
    )


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
)
def test_spotify_callback_rejects_state_mismatch(client):
    client.get(reverse("game_host:spotify-login"))

    response = client.get(
        reverse("game_host:spotify-callback"),
        {"code": "oauth-code", "state": "wrong-state"},
    )

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("catalog:index")
    assert game_views.SPOTIFY_AUTH_SESSION_KEY not in session_data
    assert game_views.SPOTIFY_OAUTH_STATE_SESSION_KEY not in session_data


@pytest.mark.django_db
@override_settings(
    SPOTIFY_CLIENT_ID="client-id",
    SPOTIFY_REDIRECT_URI="http://127.0.0.1:8000/oauth/spotify/callback",
)
def test_spotify_logout_clears_auth_session(client):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {"access_token": "access-token"}
    session_data[game_views.SPOTIFY_USER_SESSION_KEY] = {"display_name": "Host User"}
    session_data.save()

    response = client.get(reverse("game_host:spotify-logout"))

    session_data = client.session
    assert response.status_code == 302
    assert response.headers["Location"] == reverse("catalog:index")
    assert game_views.SPOTIFY_AUTH_SESSION_KEY not in session_data
    assert game_views.SPOTIFY_USER_SESSION_KEY not in session_data


@pytest.mark.django_db
def test_session_state_returns_404_for_missing_session(client):
    response = client.get(reverse("game:session-state", kwargs={"code": "9999"}))

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "session_not_found",
            "message": "Session not found.",
        }
    }


@pytest.mark.django_db
def test_session_state_returns_lobby_snapshot(client, session):
    adam = Player.objects.create(session=session, name="Adam", score=4)
    beata = Player.objects.create(session=session, name="Beata", score=12)

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    body = response.json()
    assert response.status_code == 200
    assert body["code"] == "0001"
    assert body["status"] == "lobby"
    assert body["music_set"] == {
        "slug": session.music_set.slug,
        "name": session.music_set.name,
    }
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["current_round"] is None
    assert [player["name"] for player in body["players"]] == ["Beata", "Adam"]
    assert [player["score"] for player in body["players"]] == [12, 4]
    assert _same_millisecond(body["players"][0]["joined_at"], beata.joined_at)
    assert _same_millisecond(body["players"][1]["joined_at"], adam.joined_at)


@pytest.mark.django_db
def test_session_state_returns_current_round_snapshot(client, session, track):
    session.status = GameSession.Status.PLAYING
    session.started_at = timezone.now()
    session.save(update_fields=["status", "started_at"])
    round_started_at = timezone.now()
    Round.objects.create(
        session=session,
        index=1,
        track=track,
        offset_ms=30_000,
        answer_options=["Artist A", "Artist B", "Artist C", "Artist D"],
        started_at=round_started_at,
        deadline_at=round_started_at + timedelta(seconds=30),
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    assert response.status_code == 200
    round_body = response.json()["current_round"]
    assert round_body["index"] == 1
    assert round_body["phase"] == "active"
    assert _same_millisecond(round_body["started_at"], round_started_at)
    assert round_body["offset_ms"] == 30_000
    assert round_body["answer_options"] == ["Artist A", "Artist B", "Artist C", "Artist D"]
    assert parse_datetime(round_body["deadline_at"]) is not None
    assert round_body["answered_count"] == 0
    assert round_body["total_players"] == 0
    assert "track" not in round_body
    assert parse_datetime(response.json()["server_now"]) is not None


@pytest.mark.django_db
def test_session_state_returns_finished_snapshot(client, session):
    Player.objects.create(session=session, name="Adam", score=5)
    Player.objects.create(session=session, name="Beata", score=15)
    finished_at = timezone.now()
    session.status = GameSession.Status.FINISHED
    session.finished_at = finished_at
    session.save(update_fields=["status", "finished_at"])

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "finished"
    assert _same_millisecond(body["finished_at"], finished_at)
    assert [player["name"] for player in body["players"]] == ["Beata", "Adam"]


@pytest.mark.django_db
def test_session_state_returns_304_for_matching_etag(client, session):
    first_response = client.get(
        reverse("game:session-state", kwargs={"code": session.code})
    )

    response = client.get(
        reverse("game:session-state", kwargs={"code": session.code}),
        HTTP_IF_NONE_MATCH=first_response.headers["ETag"],
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["ETag"] == first_response.headers["ETag"]
    assert response.headers["Cache-Control"] == "private, max-age=0, must-revalidate"


@pytest.mark.django_db
def test_session_state_returns_new_etag_when_semantic_state_changes(client, session):
    first_response = client.get(
        reverse("game:session-state", kwargs={"code": session.code})
    )
    Player.objects.create(session=session, name="Adam", score=1)

    response = client.get(
        reverse("game:session-state", kwargs={"code": session.code}),
        HTTP_IF_NONE_MATCH=first_response.headers["ETag"],
    )

    assert response.status_code == 200
    assert response.headers["ETag"] != first_response.headers["ETag"]
    assert response.json()["players"] == [
        {
            "name": "Adam",
            "score": 1,
            "joined_at": response.json()["players"][0]["joined_at"],
        }
    ]


@pytest.mark.django_db
def test_session_state_refreshes_last_activity_at_on_200(client, session):
    stale_at = timezone.now() - timedelta(minutes=5)
    session.last_activity_at = stale_at
    session.save(update_fields=["last_activity_at"])

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    session.refresh_from_db()
    assert response.status_code == 200
    assert session.last_activity_at > stale_at


@pytest.mark.django_db
def test_session_state_refreshes_last_activity_at_on_304(client, session):
    first_response = client.get(
        reverse("game:session-state", kwargs={"code": session.code})
    )
    stale_at = timezone.now() - timedelta(minutes=5)
    session.last_activity_at = stale_at
    session.save(update_fields=["last_activity_at"])

    response = client.get(
        reverse("game:session-state", kwargs={"code": session.code}),
        HTTP_IF_NONE_MATCH=first_response.headers["ETag"],
    )

    session.refresh_from_db()
    assert response.status_code == 304
    assert session.last_activity_at > stale_at


def _same_millisecond(serialized_value, expected_datetime):
    parsed_value = parse_datetime(serialized_value)
    expected = expected_datetime.astimezone(dt_timezone.utc)
    return abs((parsed_value - expected).total_seconds()) < 0.001
