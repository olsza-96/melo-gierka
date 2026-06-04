from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import parse_etags, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_http_methods

from game import spotify_auth
from game.state import build_snapshot_etag, get_session_state


SPOTIFY_AUTH_SESSION_KEY = "spotify_auth"
SPOTIFY_USER_SESSION_KEY = "spotify_user"
SPOTIFY_OAUTH_STATE_SESSION_KEY = "spotify_oauth_state"
SPOTIFY_CODE_VERIFIER_SESSION_KEY = "spotify_code_verifier"
SPOTIFY_POST_AUTH_REDIRECT_SESSION_KEY = "spotify_post_auth_redirect"


def _root_redirect() -> str:
    return reverse("catalog:index")


def _spotify_is_configured() -> bool:
    return bool(settings.SPOTIFY_CLIENT_ID and settings.SPOTIFY_REDIRECT_URI)


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

    if not expected_state or not code_verifier or not code or state != expected_state:
        messages.error(request, "Spotify login could not be verified. Please try again.")
        _clear_pending_oauth(request)
        return redirect(_root_redirect())

    try:
        token_payload = spotify_auth.exchange_code_for_token(
            code=code,
            code_verifier=code_verifier,
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
    _ensure_session_key(request)
    return redirect(redirect_target)


@require_http_methods(["GET", "POST"])
def spotify_logout(request):
    _clear_spotify_auth(request)
    messages.info(request, "Spotify account disconnected.")
    return redirect(_root_redirect())


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