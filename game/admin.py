from django.contrib import admin

from game.models import GameSession, Player, Round


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("code", "status", "music_set", "created_at", "last_activity_at")
    list_filter = ("status",)
    search_fields = ("code",)
    list_select_related = ("music_set",)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "session", "score", "joined_at")
    search_fields = ("name",)
    list_select_related = ("session",)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("session", "index", "track", "started_at", "locked_at")
    list_select_related = ("session", "track")
