from django.core.management import call_command
from django.core.management.base import BaseCommand

from catalog.models import MusicSet, Track
from game.models import Answer, GameSession, Player, Round


class Command(BaseCommand):
    help = "Load the initial catalog fixture (5 music sets with sample tracks)."

    def handle(self, *args, **options):
        # Reset game rows first because Round.track uses PROTECT.
        Answer.objects.all().delete()
        Round.objects.all().delete()
        Player.objects.all().delete()
        GameSession.objects.all().delete()

        # Reset catalog rows so loaddata can safely apply fixture remaps.
        Track.objects.all().delete()
        MusicSet.objects.all().delete()
        call_command("loaddata", "initial.json", app_label="catalog", verbosity=1)
        self.stdout.write(self.style.SUCCESS("Catalog seeded from catalog/fixtures/initial.json"))
