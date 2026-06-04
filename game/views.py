import hmac

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
from game.models import GameSession, Player
from game.state import build_snapshot_etag, get_session_state


SPOTIFY_AUTH_SESSION_KEY = "spotify_auth"
SPOTIFY_USER_SESSION_KEY = "spotify_user"
SPOTIFY_OAUTH_STATE_SESSION_KEY = "spotify_oauth_state"
SPOTIFY_CODE_VERIFIER_SESSION_KEY = "spotify_code_verifier"
SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY = "spotify_post_auth_redirect"
SESSION_CREATE_RETRY_ATTEMPTS = 3
PLAYER_SESSION_BINDING_SESSION_KEY = "joined_player"


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


def _ensure_session_key(request) -> None:
    if request.session.session_key is None:
        request.session.save()


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
    form = HostSessionCreateForm(initial={"music_set": session.music_set_id})
    return render(
        request,
        "game/host_lobby.html",
        {
            "host_session": session,
            "music_set_form": form,
            "spotify_logout_url": reverse("game_host:spotify-logout"),
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