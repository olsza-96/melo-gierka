from django.urls import path

from game import views

app_name = "game"

urlpatterns = [
    path(
        "sessions/<str:code>/playback-ready",
        views.session_playback_ready,
        name="session-playback-ready",
    ),
    path(
        "sessions/<str:code>/playback-diagnostics",
        views.session_playback_diagnostics,
        name="session-playback-diagnostics",
    ),
    path(
        "sessions/<str:code>/start-round",
        views.session_start_round,
        name="session-start-round",
    ),
    path(
        "sessions/<str:code>/answer",
        views.session_answer,
        name="session-answer",
    ),
    path("sessions/<str:code>/pause", views.session_pause, name="session-pause"),
    path("sessions/<str:code>/resume", views.session_resume, name="session-resume"),
    path("sessions/<str:code>/skip", views.session_skip, name="session-skip"),
    path("sessions/<str:code>/restart", views.session_restart, name="session-restart"),
    path("sessions/<str:code>/state", views.session_state, name="session-state"),
]