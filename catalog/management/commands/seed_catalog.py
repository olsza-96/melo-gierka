from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load the initial catalog fixture (5 music sets with sample tracks)."

    def handle(self, *args, **options):
        call_command("loaddata", "initial.json", app_label="catalog", verbosity=1)
        self.stdout.write(self.style.SUCCESS("Catalog seeded from catalog/fixtures/initial.json"))
