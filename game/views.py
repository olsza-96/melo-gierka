from django.http import JsonResponse
from django.views.decorators.http import require_GET

from game.state import get_session_snapshot


@require_GET
def session_state(request, code):
    snapshot = get_session_snapshot(code)
    if snapshot is None:
        return JsonResponse(
            {
                "error": {
                    "code": "session_not_found",
                    "message": "Session not found.",
                }
            },
            status=404,
        )

    return JsonResponse(snapshot)