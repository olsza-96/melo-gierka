from django.contrib import admin

from catalog.models import MusicSet, Track


class TrackInline(admin.TabularInline):
    model = Track
    extra = 0
    fields = ("artist", "title", "spotify_track_id", "duration_ms")


@admin.register(MusicSet)
class MusicSetAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "track_count")
    search_fields = ("slug", "name")
    inlines = [TrackInline]

    @admin.display(description="Tracks")
    def track_count(self, obj: MusicSet) -> int:
        return obj.tracks.count()


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ("artist", "title", "music_set", "duration_ms")
    list_filter = ("music_set",)
    search_fields = ("artist", "title", "spotify_track_id")
