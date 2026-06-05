from datetime import timedelta, timezone as dt_timezone
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from catalog.models import MusicSet, Track
from game import codegen, spotify_auth, views as game_views
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


def _set_host_auth(client, *, display_name="Host User"):
    session_data = client.session
    session_data[game_views.SPOTIFY_AUTH_SESSION_KEY] = {"access_token": "access-token"}
    session_data[game_views.SPOTIFY_USER_SESSION_KEY] = {"display_name": display_name}
    session_data.save()


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
        started_at=round_started_at,
    )

    response = client.get(reverse("game:session-state", kwargs={"code": session.code}))

    assert response.status_code == 200
    round_body = response.json()["current_round"]
    assert round_body["index"] == 1
    assert _same_millisecond(round_body["started_at"], round_started_at)
    assert round_body["offset_ms"] == 30_000
    assert round_body["track"] == {
        "spotify_track_id": track.spotify_track_id,
        "artist": track.artist,
        "title": track.title,
        "duration_ms": track.duration_ms,
    }
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
