from django.db import models
from django.utils import timezone


class GameSession(models.Model):
    class Status(models.TextChoices):
        LOBBY = "lobby", "Lobby"
        PLAYING = "playing", "Playing"
        FINISHED = "finished", "Finished"

    code = models.CharField(max_length=4, unique=True, db_index=True)
    music_set = models.ForeignKey(
        "catalog.MusicSet",
        on_delete=models.PROTECT,
    )
    host_session_key = models.CharField(max_length=40)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOBBY,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} ({self.status})"


class Player(models.Model):
    session = models.ForeignKey(
        GameSession,
        related_name="players",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=40)
    score = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "name"],
                name="unique_player_name_per_session",
            ),
        ]
        ordering = ["session", "-score", "joined_at"]

    def __str__(self) -> str:
        return f"{self.name} @ {self.session.code}"


class Round(models.Model):
    session = models.ForeignKey(
        GameSession,
        related_name="rounds",
        on_delete=models.CASCADE,
    )
    index = models.PositiveSmallIntegerField()
    track = models.ForeignKey(
        "catalog.Track",
        on_delete=models.PROTECT,
    )
    offset_ms = models.PositiveIntegerField()
    answer_options = models.JSONField(default=list)
    started_at = models.DateTimeField()
    deadline_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "index"],
                name="unique_round_index_per_session",
            ),
        ]
        ordering = ["session", "index"]

    def __str__(self) -> str:
        return f"Round {self.index} of {self.session.code}"


class Answer(models.Model):
    round = models.ForeignKey(
        Round,
        related_name="answers",
        on_delete=models.CASCADE,
    )
    player = models.ForeignKey(
        Player,
        related_name="answers",
        on_delete=models.CASCADE,
    )
    selected_artist = models.CharField(max_length=200)
    submitted_at = models.DateTimeField(default=timezone.now)
    response_ms = models.PositiveIntegerField(default=0)
    is_correct = models.BooleanField(default=False)
    points_awarded = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["round", "player"],
                name="unique_answer_per_round_player",
            ),
        ]
        ordering = ["round", "submitted_at", "player"]

    def __str__(self) -> str:
        return f"{self.player.name} -> {self.round}"
