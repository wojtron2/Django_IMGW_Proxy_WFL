from django.core.management.base import BaseCommand
from meteo.services import fetch_imgw, upsert_imgw

class Command(BaseCommand):
    help = "Fetch IMGW warnings and upsert into DB."

    def handle(self, *args, **opts):
        items = fetch_imgw()
        n = upsert_imgw(items)
        self.stdout.write(self.style.SUCCESS(f"Upserted {n} warnings"))