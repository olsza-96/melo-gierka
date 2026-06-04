from django.urls import path

from game import views

app_name = "game_host"

urlpatterns = [
    path("oauth/spotify/login", views.spotify_login, name="spotify-login"),
    path("oauth/spotify/callback", views.spotify_callback, name="spotify-callback"),
    path("oauth/spotify/logout", views.spotify_logout, name="spotify-logout"),
]