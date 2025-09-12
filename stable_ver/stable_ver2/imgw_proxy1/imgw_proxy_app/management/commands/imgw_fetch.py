from django.core.management.base import BaseCommand
from django.utils import timezone
from imgw_proxy_app.models import Warning
from imgw_proxy_app.services.ingest import fetch_imgw, normalize

class Command(BaseCommand):
    help = "Fetch IMGW warnings and archive full records."

    def handle(self, *args, **opts):
        data = fetch_imgw()
        now = timezone.now()
        new = 0
        for rec in data:
            n = normalize(rec)
            _, created = Warning.objects.update_or_create(uid=n["uid"], defaults=n)
            if created:
                new += 1
        # dezaktywuj przeterminowane
        Warning.objects.filter(is_active=True, valid_to__lt=now).update(is_active=False)
        self.stdout.write(self.style.SUCCESS(f"Fetched {new} new"))
