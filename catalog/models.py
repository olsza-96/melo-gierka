from django.db import models


class MusicSet(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Track(models.Model):
    music_set = models.ForeignKey(
        MusicSet,
        related_name="tracks",
        on_delete=models.CASCADE,
    )
    spotify_track_id = models.CharField(max_length=22)
    artist = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    duration_ms = models.IntegerField()

    class Meta:
        unique_together = ("music_set", "spotify_track_id")
        ordering = ["music_set", "artist", "title"]

    def __str__(self) -> str:
        return f"{self.artist} — {self.title}"
