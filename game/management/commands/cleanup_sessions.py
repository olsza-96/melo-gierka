import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from game.models import GameSession

logger = logging.getLogger("game.cleanup")


class Command(BaseCommand):
    help = "Delete GameSessions idle for more than --idle-hours (default 1)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without executing.",
        )
        parser.add_argument(
            "--idle-hours",
            type=int,
            default=1,
            help="Sessions with last_activity_at older than this are deleted.",
        )

    def handle(self, *args, dry_run=False, idle_hours=1, **options):
        cutoff = timezone.now() - timedelta(hours=idle_hours)
        stale = GameSession.objects.filter(last_activity_at__lt=cutoff)
        codes = list(stale.values_list("code", flat=True))
        count = len(codes)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] would delete {count} session(s): {codes}"
                )
            )
            logger.info("cleanup dry-run: %d session(s) would be deleted", count)
            return

        stale.delete()
        self.stdout.write(
            self.style.WARNING(f"deleted {count} session(s): {codes}")
        )
        logger.info("cleanup: deleted %d session(s)", count)
