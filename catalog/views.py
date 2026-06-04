from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from catalog.models import MusicSet
from game.forms import HostSessionCreateForm
from game.views import SPOTIFY_AUTH_SESSION_KEY, SPOTIFY_USER_SESSION_KEY


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def index(request):
    spotify_auth = request.session.get(SPOTIFY_AUTH_SESSION_KEY)
    spotify_user = request.session.get(SPOTIFY_USER_SESSION_KEY, {})
    host_is_authenticated = bool(spotify_auth)

    context = {
        "host_is_authenticated": host_is_authenticated,
        "host_create_form": HostSessionCreateForm() if host_is_authenticated else None,
        "spotify_user": spotify_user,
        "spotify_login_url": f"{reverse('game_host:spotify-login')}?next=/",
        "spotify_logout_url": reverse("game_host:spotify-logout"),
        "music_set_count": MusicSet.objects.count(),
    }
    return render(request, "catalog/index.html", context)
