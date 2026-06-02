from django.contrib import admin

from game.models import GameSession, Player, Round


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("code", "status", "music_set", "created_at", "last_activity_at")
    list_filter = ("status",)
    search_fields = ("code",)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "session", "score", "joined_at")
    search_fields = ("name",)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ("session", "index", "track", "started_at", "locked_at")
