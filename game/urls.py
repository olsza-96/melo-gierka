from django.urls import path

from game import views

app_name = "game_host"

urlpatterns = [
    path("oauth/spotify/login", views.spotify_login, name="spotify-login"),
    path("oauth/spotify/callback", views.spotify_callback, name="spotify-callback"),
    path("oauth/spotify/logout", views.spotify_logout, name="spotify-logout"),
    path("host/sessions/create", views.session_create, name="session-create"),
    path("host/sessions/<str:code>", views.host_lobby, name="host-lobby"),
    path("host/sessions/<str:code>/music-set", views.music_set_edit, name="music-set-edit"),
]