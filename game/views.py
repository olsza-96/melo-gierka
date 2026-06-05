import json
import hmac
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import parse_etags, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods

from game import codegen, spotify_auth
from game.forms import HostSessionCreateForm, PlayerJoinForm, build_player_name_suggestion
from game.models import GameSession, Player, Round
from game.state import build_snapshot_etag, get_session_state


SPOTIFY_AUTH_SESSION_KEY = "spotify_auth"
SPOTIFY_USER_SESSION_KEY = "spotify_user"
SPOTIFY_OAUTH_STATE_SESSION_KEY = "spotify_oauth_state"
SPOTIFY_CODE_VERIFIER_SESSION_KEY = "spotify_code_verifier"
SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY = "spotify_post_auth_redirect"
SPOTIFY_PLAYBACK_SESSION_KEY = "spotify_playback"
SESSION_CREATE_RETRY_ATTEMPTS = 3
PLAYER_SESSION_BINDING_SESSION_KEY = "joined_player"
ROUND_DURATION_MS = 30_000
ROUND_OFFSET_MIN_RATIO = 0.2
ROUND_OFFSET_MAX_RATIO = 0.8
PLAYBACK_DEVICE_READY_ATTEMPTS = 5
PLAYBACK_DEVICE_READY_DELAY_SECONDS = 0.2


def _root_redirect() -> str:
    return reverse("catalog:index")


def _spotify_callback_uri(request) -> str:
    return request.build_absolute_uri(reverse("game_host:spotify-callback"))


def _spotify_is_configured() -> bool:
    return bool(settings.SPOTIFY_CLIENT_ID)


def _validated_redirect_target(request, candidate: str | None) -> str:
    default_target = _root_redirect()
    if not candidate:
        return default_target
    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return default_target


def _clear_pending_oauth(request) -> None:
    for key in (
        SPOTIFY_OAUTH_STATE_SESSION_KEY,
        SPOTIFY_CODE_VERIFIER_SESSION_KEY,
        SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY,
    ):
        request.session.pop(key, None)


def _clear_spotify_auth(request) -> None:
    _clear_pending_oauth(request)
    request.session.pop(SPOTIFY_AUTH_SESSION_KEY, None)
    request.session.pop(SPOTIFY_USER_SESSION_KEY, None)
    request.session.pop(SPOTIFY_PLAYBACK_SESSION_KEY, None)


def _ensure_session_key(request) -> None:
    if request.session.session_key is None:
        request.session.save()


def _spotify_required_scopes() -> set[str]:
    return {scope for scope in settings.SPOTIFY_SCOPE.split() if scope}


def _spotify_auth_has_required_scopes(auth_payload: dict) -> bool:
    scope_value = str(auth_payload.get("scope") or "").strip()
    if not scope_value:
        return True
    granted_scopes = {scope for scope in scope_value.split() if scope}
    return _spotify_required_scopes().issubset(granted_scopes)


def _refresh_host_auth_payload(request) -> dict | None:
    auth_payload = request.session.get(SPOTIFY_AUTH_SESSION_KEY) or {}
    refresh_token = auth_payload.get("refresh_token")
    if not refresh_token:
        return None

    refreshed_payload = spotify_auth.refresh_access_token(refresh_token=refresh_token)
    if not refreshed_payload.get("refresh_token"):
        refreshed_payload["refresh_token"] = refresh_token
    request.session[SPOTIFY_AUTH_SESSION_KEY] = refreshed_payload
    return refreshed_payload


def _get_host_auth_payload(request) -> dict | None:
    auth_payload = request.session.get(SPOTIFY_AUTH_SESSION_KEY) or {}
    if not auth_payload:
        return None

    expires_at = int(auth_payload.get("expires_at") or 0)
    if expires_at and expires_at <= int(time.time()) + 30:
        try:
            auth_payload = _refresh_host_auth_payload(request) or {}
        except spotify_auth.SpotifyOAuthError:
            _clear_spotify_auth(request)
            return None

    if not auth_payload or not _spotify_auth_has_required_scopes(auth_payload):
        _clear_spotify_auth(request)
        return None

    return auth_payload


def _get_host_access_token(request) -> str | None:
    auth_payload = _get_host_auth_payload(request) or {}
    return auth_payload.get("access_token")


def _get_host_playback_state(request, *, code: str) -> dict | None:
    playback_state = request.session.get(SPOTIFY_PLAYBACK_SESSION_KEY)
    if not playback_state:
        return None
    if playback_state.get("session_code") != code:
        return None
    return playback_state


def _get_host_user_profile(request) -> dict | None:
    user_profile = request.session.get(SPOTIFY_USER_SESSION_KEY) or {}
    if user_profile.get("product"):
        return user_profile

    access_token = _get_host_access_token(request)
    if not access_token:
        return user_profile or None

    try:
        user_profile = spotify_auth.fetch_user_profile(access_token)
    except spotify_auth.SpotifyOAuthError:
        return user_profile or None

    request.session[SPOTIFY_USER_SESSION_KEY] = user_profile
    return user_profile


def _host_playback_block_reason(request) -> str | None:
    user_profile = _get_host_user_profile(request) or {}
    product = str(user_profile.get("product") or "").strip().lower()
    if product and product != "premium":
        return "Spotify Premium is required for browser playback in this host flow. Reconnect with a Premium account to start a round."
    return None


def _choose_round_track(session: GameSession, *, access_token: str):
    used_track_ids = session.rounds.values_list("track_id", flat=True)
    available_tracks = list(session.music_set.tracks.exclude(pk__in=used_track_ids))
    if not available_tracks:
        return None

    candidates = available_tracks[:]
    while candidates:
        track = secrets.choice(candidates)
        candidates.remove(track)

        try:
            track_details = spotify_auth.fetch_track_details(
                access_token=access_token,
                spotify_track_id=track.spotify_track_id,
            )
        except spotify_auth.SpotifyOAuthError as exc:
            if exc.status_code in {400, 404}:
                continue
            return track

        if track_details.get("is_playable") is False:
            continue

        if track_details.get("restriction_reason"):
            continue

        return track

    return None


def _build_answer_options(session: GameSession, *, correct_artist: str) -> list[str] | None:
    distractor_artists = list(
        session.music_set.tracks.exclude(artist=correct_artist)
        .values_list("artist", flat=True)
        .distinct()
    )
    if len(distractor_artists) < 3:
        return None

    options = distractor_artists[:]
    selected = []
    while len(selected) < 3:
        candidate = secrets.choice(options)
        options.remove(candidate)
        selected.append(candidate)

    answer_options = selected + [correct_artist]
    shuffled = []
    while answer_options:
        candidate = secrets.choice(answer_options)
        answer_options.remove(candidate)
        shuffled.append(candidate)
    return shuffled


def _build_round_offset_ms(duration_ms: int) -> int:
    lower = int(duration_ms * ROUND_OFFSET_MIN_RATIO)
    upper = int(duration_ms * ROUND_OFFSET_MAX_RATIO)
    upper = min(upper, max(duration_ms - ROUND_DURATION_MS, 0))
    if upper < lower:
        upper = lower
    if upper <= lower:
        return max(lower, 0)
    return secrets.randbelow((upper - lower) + 1) + lower


def _current_round_for_host(session: GameSession) -> Round | None:
    return session.rounds.select_related("track").order_by("-index").first()


def _wait_for_commandable_playback_device(*, access_token: str, device_id: str) -> dict | None:
    last_seen_device = None

    for attempt in range(PLAYBACK_DEVICE_READY_ATTEMPTS):
        devices = spotify_auth.fetch_available_devices(access_token=access_token)
        matching_device = next((device for device in devices if device.get("id") == device_id), None)
        if matching_device is not None:
            last_seen_device = matching_device
            if not matching_device.get("is_restricted"):
                return matching_device

        if attempt < PLAYBACK_DEVICE_READY_ATTEMPTS - 1:
            time.sleep(PLAYBACK_DEVICE_READY_DELAY_SECONDS * (attempt + 1))

    return last_seen_device


def _pick_start_round_fallback_device(
    devices: list[dict],
    *,
    exclude_device_id: str | None = None,
) -> dict | None:
    commandable_devices = [
        device
        for device in devices
        if not device.get("is_restricted") and device.get("id") != exclude_device_id
    ]
    active_device = next((device for device in commandable_devices if device.get("is_active")), None)
    if active_device is not None:
        return active_device
    if len(commandable_devices) == 1:
        return commandable_devices[0]
    return None


def _resolve_start_round_playback_device(*, access_token: str, preferred_device_id: str) -> dict | None:
    last_seen_device = None
    last_fallback_device = None

    for attempt in range(PLAYBACK_DEVICE_READY_ATTEMPTS):
        devices = spotify_auth.fetch_available_devices(access_token=access_token)
        matching_device = next((device for device in devices if device.get("id") == preferred_device_id), None)
        if matching_device is not None:
            last_seen_device = matching_device
            if not matching_device.get("is_restricted"):
                fallback_device = _pick_start_round_fallback_device(
                    devices,
                    exclude_device_id=preferred_device_id,
                )
                if fallback_device is not None and not matching_device.get("is_active"):
                    last_fallback_device = fallback_device
                    return fallback_device
                return matching_device

        fallback_device = _pick_start_round_fallback_device(
            devices,
            exclude_device_id=preferred_device_id,
        )
        if fallback_device is not None:
            last_fallback_device = fallback_device
            return fallback_device

        if attempt < PLAYBACK_DEVICE_READY_ATTEMPTS - 1:
            time.sleep(PLAYBACK_DEVICE_READY_DELAY_SECONDS * (attempt + 1))

    return last_seen_device or last_fallback_device


def _playback_device_error_message(device_state: dict | None) -> str:
    if device_state is None:
        return "Spotify connected this browser player, but it is not available as a controllable device yet. Keep this tab active and try preparing playback again."
    if device_state.get("is_restricted"):
        return "Spotify connected this browser player, but Spotify still marks it as restricted. Disable private session or other device restrictions, then prepare playback again."
    return "Spotify browser playback is not ready yet."


def _playback_device_active_error_message(device_state: dict | None) -> str:
    if device_state is None:
        return "Spotify browser playback could not be activated on this device. Keep this tab active and try starting the round again."
    if device_state.get("is_restricted"):
        return _playback_device_error_message(device_state)
    if not device_state.get("is_active"):
        return "Spotify connected this browser player, but it never became the active playback device. Keep this tab focused and try starting the round again."
    return "Spotify browser playback is not active yet."


def _wait_for_active_playback_device(*, access_token: str, device_id: str) -> dict | None:
    last_seen_device = None

    for attempt in range(PLAYBACK_DEVICE_READY_ATTEMPTS):
        devices = spotify_auth.fetch_available_devices(access_token=access_token)
        matching_device = next((device for device in devices if device.get("id") == device_id), None)
        if matching_device is not None:
            last_seen_device = matching_device
            if not matching_device.get("is_restricted") and matching_device.get("is_active"):
                return matching_device

        if attempt < PLAYBACK_DEVICE_READY_ATTEMPTS - 1:
            time.sleep(PLAYBACK_DEVICE_READY_DELAY_SECONDS * (attempt + 1))

    return last_seen_device


def _build_spotify_diagnostics(request, *, session: GameSession) -> dict:
    access_token = _get_host_access_token(request)
    user_profile = _get_host_user_profile(request) or {}
    playback_state = _get_host_playback_state(request, code=session.code) or {}

    diagnostics = {
        "host": {
            "display_name": user_profile.get("display_name"),
            "product": user_profile.get("product"),
            "blocked_reason": _host_playback_block_reason(request),
        },
        "playback_state": playback_state,
        "devices": [],
        "track_checks": [],
    }

    if not access_token:
        diagnostics["error"] = {
            "code": "spotify_auth_missing",
            "message": "Reconnect Spotify before running playback diagnostics.",
        }
        return diagnostics

    try:
        devices = spotify_auth.fetch_available_devices(access_token=access_token)
    except spotify_auth.SpotifyOAuthError as exc:
        diagnostics["devices_error"] = {
            "status_code": exc.status_code,
            "response_body": exc.response_body,
        }
        devices = []

    diagnostics["devices"] = [
        {
            "id": device.get("id"),
            "name": device.get("name"),
            "type": device.get("type"),
            "is_active": device.get("is_active"),
            "is_private_session": device.get("is_private_session"),
            "is_restricted": device.get("is_restricted"),
        }
        for device in devices
    ]

    remaining_tracks = list(
        session.music_set.tracks.exclude(pk__in=session.rounds.values_list("track_id", flat=True))[:8]
    )
    for track in remaining_tracks:
        track_check = {
            "spotify_track_id": track.spotify_track_id,
            "artist": track.artist,
            "title": track.title,
        }
        try:
            track_check.update(
                spotify_auth.fetch_track_details(
                    access_token=access_token,
                    spotify_track_id=track.spotify_track_id,
                )
            )
        except spotify_auth.SpotifyOAuthError as exc:
            track_check["lookup_error"] = {
                "status_code": exc.status_code,
                "response_body": exc.response_body,
            }
        diagnostics["track_checks"].append(track_check)

    return diagnostics


def _is_retryable_start_playback_error(exc: spotify_auth.SpotifyOAuthError) -> bool:
    if exc.status_code == 404:
        return True

    if exc.status_code != 403:
        return False

    response_body = exc.response_body or {}
    error_body = response_body.get("error") if isinstance(response_body, dict) else None
    if not isinstance(error_body, dict):
        return False

    message = str(error_body.get("message") or "")
    reason = str(error_body.get("reason") or "")
    return message == "Player command failed: Restriction violated" and reason == "UNKNOWN"


def _start_round_playback(
    *,
    access_token: str,
    device_id: str,
    spotify_track_id: str,
    position_ms: int,
) -> None:
    spotify_auth.transfer_playback(
        access_token=access_token,
        device_id=device_id,
        play=True,
    )

    active_device = _wait_for_active_playback_device(
        access_token=access_token,
        device_id=device_id,
    )
    if active_device is None or active_device.get("is_restricted") or not active_device.get("is_active"):
        raise spotify_auth.SpotifyOAuthError(
            _playback_device_active_error_message(active_device),
            status_code=409,
            response_body={"device": active_device},
        )

    last_error = None
    for attempt in range(3):
        try:
            spotify_auth.start_playback(
                access_token=access_token,
                device_id=device_id,
                spotify_track_id=spotify_track_id,
                position_ms=position_ms,
            )
            return
        except spotify_auth.SpotifyOAuthError as exc:
            last_error = exc
            if not _is_retryable_start_playback_error(exc) or attempt == 2:
                raise
            _wait_for_active_playback_device(
                access_token=access_token,
                device_id=device_id,
            )
            time.sleep(0.25 * (attempt + 1))

    if last_error is not None:
        raise last_error


def _get_owned_host_session(request, *, code: str) -> GameSession:
    session_key = request.session.session_key
    if session_key is None:
        raise Http404("Session not found.")
    return get_object_or_404(
        GameSession.objects.select_related("music_set"),
        code=code,
        host_session_key=session_key,
    )


def _get_bound_player(request, *, code: str) -> Player | None:
    binding = request.session.get(PLAYER_SESSION_BINDING_SESSION_KEY)
    if not binding or binding.get("session_code") != code:
        return None

    player_id = binding.get("player_id")
    if player_id is None:
        return None

    return (
        Player.objects.select_related("session", "session__music_set")
        .filter(pk=player_id, session__code=code)
        .first()
    )


@require_GET
def spotify_login(request):
    if not _spotify_is_configured():
        return HttpResponse("Spotify OAuth is not configured.", status=503)

    redirect_target = _validated_redirect_target(request, request.GET.get("next"))
    state = spotify_auth.generate_oauth_state()
    code_verifier = spotify_auth.generate_code_verifier()

    request.session[SPOTIFY_OAUTH_STATE_SESSION_KEY] = state
    request.session[SPOTIFY_CODE_VERIFIER_SESSION_KEY] = code_verifier
    request.session[SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY] = redirect_target

    return redirect(
        spotify_auth.build_authorize_url(
            state=state,
            code_verifier=code_verifier,
            redirect_uri=_spotify_callback_uri(request),
        )
    )


@require_GET
def spotify_callback(request):
    if not _spotify_is_configured():
        return HttpResponse("Spotify OAuth is not configured.", status=503)

    if request.GET.get("error"):
        messages.error(request, "Spotify login was cancelled or denied.")
        _clear_pending_oauth(request)
        return redirect(_root_redirect())

    expected_state = request.session.get(SPOTIFY_OAUTH_STATE_SESSION_KEY)
    code_verifier = request.session.get(SPOTIFY_CODE_VERIFIER_SESSION_KEY)
    state = request.GET.get("state")
    code = request.GET.get("code")

    if not expected_state or not code_verifier or not code or not hmac.compare_digest(state or "", expected_state):
        messages.error(request, "Spotify login could not be verified. Please try again.")
        _clear_pending_oauth(request)
        return redirect(_root_redirect())

    try:
        token_payload = spotify_auth.exchange_code_for_token(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=_spotify_callback_uri(request),
        )
        user_profile = spotify_auth.fetch_user_profile(token_payload["access_token"])
    except spotify_auth.SpotifyOAuthError:
        messages.error(request, "Spotify login failed. Please try again.")
        _clear_pending_oauth(request)
        return redirect(_root_redirect())

    redirect_target = _validated_redirect_target(
        request,
        request.session.get(SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY),
    )
    _clear_pending_oauth(request)
    request.session[SPOTIFY_AUTH_SESSION_KEY] = token_payload
    request.session[SPOTIFY_USER_SESSION_KEY] = user_profile
    request.session.cycle_key()
    return redirect(redirect_target)


@require_http_methods(["GET", "POST"])
def spotify_logout(request):
    _clear_spotify_auth(request)
    messages.info(request, "Spotify account disconnected.")
    return redirect(_root_redirect())


@require_http_methods(["POST"])
def session_create(request):
    if not request.session.get(SPOTIFY_AUTH_SESSION_KEY):
        messages.error(request, "Log in with Spotify before creating a session.")
        return redirect(_root_redirect())

    _ensure_session_key(request)
    form = HostSessionCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid music set before creating a session.")
        return redirect(_root_redirect())

    for _ in range(SESSION_CREATE_RETRY_ATTEMPTS):
        code = codegen.generate_session_code()
        try:
            with transaction.atomic():
                session = GameSession.objects.create(
                    code=code,
                    music_set=form.cleaned_data["music_set"],
                    host_session_key=request.session.session_key,
                )
        except IntegrityError:
            continue
        return redirect("game_host:host-lobby", code=session.code)

    raise RuntimeError("could not create a host session after retrying")


@require_GET
def host_lobby(request, code):
    session = _get_owned_host_session(request, code=code)
    current_round = _current_round_for_host(session)
    spotify_blocked_reason = _host_playback_block_reason(request)
    spotify_access_token = _get_host_access_token(request) or ""

    if not spotify_access_token:
        messages.error(
            request,
            "Reconnect Spotify before preparing browser playback. The current login expired or is missing playback permissions.",
        )
    elif spotify_blocked_reason:
        messages.error(request, spotify_blocked_reason)
        spotify_access_token = ""

    if session.status == GameSession.Status.PLAYING and current_round is not None:
        return render(
            request,
            "game/host_round.html",
            {
                "host_session": session,
                "current_round": current_round,
                "spotify_access_token": spotify_access_token,
                "spotify_blocked_reason": spotify_blocked_reason or "",
                "spotify_playback_ready_url": reverse(
                    "game:session-playback-ready",
                    kwargs={"code": session.code},
                ),
            },
        )

    form = HostSessionCreateForm(initial={"music_set": session.music_set_id})
    return render(
        request,
        "game/host_lobby.html",
        {
            "host_session": session,
            "music_set_form": form,
            "spotify_logout_url": reverse("game_host:spotify-logout"),
            "spotify_access_token": spotify_access_token,
            "spotify_blocked_reason": spotify_blocked_reason or "",
            "spotify_playback_ready_url": reverse(
                "game:session-playback-ready",
                kwargs={"code": session.code},
            ),
            "session_start_round_url": reverse(
                "game:session-start-round",
                kwargs={"code": session.code},
            ),
        },
    )


@require_http_methods(["POST"])
def music_set_edit(request, code):
    session = _get_owned_host_session(request, code=code)
    if session.status != GameSession.Status.LOBBY:
        return HttpResponse(status=404)

    form = HostSessionCreateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid music set before updating the lobby.")
        return redirect("game_host:host-lobby", code=session.code)

    session.music_set = form.cleaned_data["music_set"]
    session.save(update_fields=["music_set"])
    messages.success(request, "Music set updated.")
    return redirect("game_host:host-lobby", code=session.code)


@require_http_methods(["GET", "POST"])
def player_join(request):
    initial = {"code": request.GET.get("code", "")}
    form = PlayerJoinForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        requested_session = form.cleaned_data["session"]
        player_name = form.cleaned_data["name"]
        _ensure_session_key(request)

        try:
            with transaction.atomic():
                locked_session = GameSession.objects.select_for_update().get(
                    pk=requested_session.pk
                )
                if locked_session.status != GameSession.Status.LOBBY:
                    form.add_error(
                        "code",
                        "This session is no longer accepting players.",
                    )
                else:
                    player = Player.objects.create(
                        session=locked_session,
                        name=player_name,
                    )
        except GameSession.DoesNotExist:
            form.add_error("code", "Enter a valid session code.")
        except IntegrityError:
            suggestion = build_player_name_suggestion(
                session=requested_session,
                base_name=player_name,
            )
            form.suggested_name = suggestion
            form.add_error(
                "name",
                f'"{player_name}" is already taken in this session. Try "{suggestion}".',
            )
        else:
            if not form.errors:
                request.session[PLAYER_SESSION_BINDING_SESSION_KEY] = {
                    "session_code": locked_session.code,
                    "player_id": player.pk,
                }
                return redirect("game_host:player-lobby", code=locked_session.code)

    return render(
        request,
        "game/player_join.html",
        {
            "join_form": form,
        },
    )


@require_GET
def player_lobby(request, code):
    player = _get_bound_player(request, code=code)
    if player is None:
        messages.error(request, "Join a session before entering the player lobby.")
        return redirect(f"{reverse('game_host:player-join')}?code={code}")

    return render(
        request,
        "game/player_lobby.html",
        {
            "joined_player": player,
            "player_session": player.session,
        },
    )


@require_GET
def session_state(request, code):
    state = get_session_state(code)
    if state is None:
        return JsonResponse(
            {
                "error": {
                    "code": "session_not_found",
                    "message": "Session not found.",
                }
            },
            status=404,
        )

    session, snapshot = state
    etag = build_snapshot_etag(snapshot)
    cache_control = "private, max-age=0, must-revalidate"

    session.last_activity_at = timezone.now()
    session.save(update_fields=["last_activity_at"])

    if etag in parse_etags(request.META.get("HTTP_IF_NONE_MATCH", "")):
        response = HttpResponse(status=304)
        response["ETag"] = etag
        response["Cache-Control"] = cache_control
        return response

    response = JsonResponse(
        {
            **snapshot,
            "server_now": timezone.now(),
        }
    )
    response["ETag"] = etag
    response["Cache-Control"] = cache_control
    return response


@require_http_methods(["POST"])
def session_playback_ready(request, code):
    session = _get_owned_host_session(request, code=code)
    access_token = _get_host_access_token(request)
    if not access_token:
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_auth_missing",
                    "message": "Reconnect Spotify before preparing browser playback.",
                }
            },
            status=403,
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}

    device_id = str(payload.get("device_id") or "").strip()
    if not device_id:
        return JsonResponse(
            {
                "error": {
                    "code": "missing_device_id",
                    "message": "Spotify playback device id is required.",
                }
            },
            status=400,
        )

    try:
        device_state = _wait_for_commandable_playback_device(
            access_token=access_token,
            device_id=device_id,
        )
    except spotify_auth.SpotifyOAuthError:
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_device_lookup_failed",
                    "message": "Spotify browser playback could not be verified right now. Try preparing the player again.",
                }
            },
            status=502,
        )

    if device_state is None or device_state.get("is_restricted"):
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_device_not_ready",
                    "message": _playback_device_error_message(device_state),
                }
            },
            status=409,
        )

    request.session[SPOTIFY_PLAYBACK_SESSION_KEY] = {
        "session_code": session.code,
        "device_id": device_id,
        "ready": True,
    }
    return JsonResponse({"ready": True, "device_id": device_id})


@require_GET
def session_playback_diagnostics(request, code):
    session = _get_owned_host_session(request, code=code)
    return JsonResponse(_build_spotify_diagnostics(request, session=session))


@require_http_methods(["POST"])
def session_start_round(request, code):
    session = _get_owned_host_session(request, code=code)
    spotify_blocked_reason = _host_playback_block_reason(request)
    if spotify_blocked_reason:
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_premium_required",
                    "message": spotify_blocked_reason,
                }
            },
            status=403,
        )

    playback_state = _get_host_playback_state(request, code=code)
    if not playback_state or not playback_state.get("ready"):
        return JsonResponse(
            {
                "error": {
                    "code": "playback_not_ready",
                    "message": "Activate the Spotify browser player before starting the round.",
                }
            },
            status=409,
        )

    access_token = _get_host_access_token(request)
    if not access_token:
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_auth_missing",
                    "message": "Reconnect Spotify before starting the round. The current login expired or is missing playback permissions.",
                }
            },
            status=403,
        )

    try:
        device_state = _resolve_start_round_playback_device(
            access_token=access_token,
            preferred_device_id=playback_state["device_id"],
        )
    except spotify_auth.SpotifyOAuthError:
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_device_lookup_failed",
                    "message": "Spotify browser playback could not be verified right now. Try preparing the player again.",
                }
            },
            status=502,
        )

    if device_state is None or device_state.get("is_restricted"):
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_device_not_ready",
                    "message": _playback_device_error_message(device_state),
                }
            },
            status=409,
        )

    if device_state.get("id") and device_state.get("id") != playback_state["device_id"]:
        request.session[SPOTIFY_PLAYBACK_SESSION_KEY] = {
            **playback_state,
            "device_id": device_state["id"],
        }
        playback_state = request.session[SPOTIFY_PLAYBACK_SESSION_KEY]

    try:
        with transaction.atomic():
            locked_session = GameSession.objects.select_for_update().select_related(
                "music_set"
            ).get(pk=session.pk)

            if locked_session.status != GameSession.Status.LOBBY:
                return JsonResponse(
                    {
                        "error": {
                            "code": "session_not_in_lobby",
                            "message": "This session has already left the lobby.",
                        }
                    },
                    status=409,
                )

            if locked_session.players.count() == 0:
                return JsonResponse(
                    {
                        "error": {
                            "code": "players_required",
                            "message": "At least one joined player is required before starting the round.",
                        }
                    },
                    status=409,
                )

            track = _choose_round_track(
                locked_session,
                access_token=access_token,
            )
            if track is None:
                return JsonResponse(
                    {
                        "error": {
                            "code": "no_playable_tracks",
                            "message": "No playable Spotify tracks are available for this host account in the selected music set.",
                        }
                    },
                    status=409,
                )

            answer_options = _build_answer_options(
                locked_session,
                correct_artist=track.artist,
            )
            if answer_options is None:
                return JsonResponse(
                    {
                        "error": {
                            "code": "insufficient_artists",
                            "message": "This music set needs at least four distinct artists for a round.",
                        }
                    },
                    status=409,
                )

            started_at = timezone.now()
            offset_ms = _build_round_offset_ms(track.duration_ms)
            round_obj = Round.objects.create(
                session=locked_session,
                index=locked_session.rounds.count() + 1,
                track=track,
                offset_ms=offset_ms,
                answer_options=answer_options,
                started_at=started_at,
                deadline_at=started_at + timedelta(milliseconds=ROUND_DURATION_MS),
            )

            _start_round_playback(
                access_token=access_token,
                device_id=playback_state["device_id"],
                spotify_track_id=track.spotify_track_id,
                position_ms=offset_ms,
            )

            locked_session.status = GameSession.Status.PLAYING
            if locked_session.started_at is None:
                locked_session.started_at = started_at
                locked_session.save(update_fields=["status", "started_at"])
            else:
                locked_session.save(update_fields=["status"])
    except spotify_auth.SpotifyOAuthError as exc:
        if exc.status_code == 409:
            return JsonResponse(
                {
                    "error": {
                        "code": "spotify_device_not_active",
                        "message": str(exc),
                    }
                },
                status=409,
            )

        message = "Spotify playback could not start on the active browser device."
        if settings.DEBUG and exc.status_code is not None:
            detail = exc.response_body
            if isinstance(detail, dict):
                detail = detail.get("error", detail)
            message = f"{message} Spotify responded with {exc.status_code}: {detail}"
        return JsonResponse(
            {
                "error": {
                    "code": "spotify_playback_failed",
                    "message": message,
                }
            },
            status=502,
        )

    return JsonResponse(
        {
            "playback": {
                "device_id": playback_state["device_id"],
                "spotify_track_id": round_obj.track.spotify_track_id,
                "offset_ms": round_obj.offset_ms,
            },
            "redirect_url": reverse("game_host:host-lobby", kwargs={"code": code}),
        }
    )