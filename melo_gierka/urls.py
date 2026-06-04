from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(("game.api_urls", "game"), namespace="game")),
    path("", include(("game.urls", "game_host"), namespace="game_host")),
    path("", include("catalog.urls")),
]
