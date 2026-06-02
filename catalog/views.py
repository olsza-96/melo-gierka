from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from catalog.models import MusicSet


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def index(request):
    slugs = list(MusicSet.objects.values_list("slug", flat=True))
    if slugs:
        body = "melo-gierka is up — available catalog sets: " + ", ".join(slugs)
    else:
        body = "melo-gierka is up — no catalog sets seeded yet"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
