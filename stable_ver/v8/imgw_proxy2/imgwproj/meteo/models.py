from django.db import models
from django.utils import timezone
from django.db.models import F
from django.core.validators import MinValueValidator, MaxValueValidator

class Powiat(models.Model):
    teryt4 = models.CharField(max_length=4, primary_key=True)
    name = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.teryt4} {self.name}".strip()

class Warning(models.Model):
    id = models.CharField(primary_key=True, max_length=64)  # id z IMGW
    event_name = models.CharField(max_length=160)
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(3)]
    )
    probability = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    valid_from = models.DateTimeField()  # przechowujemy w UTC
    valid_to = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    content = models.TextField(blank=True)
    comment = models.TextField(blank=True)
    office = models.CharField(max_length=120, blank=True)

    coverage = models.ManyToManyField(
        'Powiat', through='WarningCoverage', related_name='warnings', blank=True
    )

    class Meta:
        indexes = [models.Index(fields=['valid_from', 'valid_to'])]
        ordering = ['-valid_from']

    @classmethod
    def current_for_powiat(cls, teryt4: str):
        now = timezone.now()
        return (
            cls.objects.filter(
                valid_from__lte=now,
                valid_to__gte=now,
                coverage__teryt4=teryt4,
            )
            .distinct()
            .order_by('-level', 'valid_to')
        )

class WarningCoverage(models.Model):
    warning = models.ForeignKey(Warning, on_delete=models.CASCADE)
    powiat = models.ForeignKey(Powiat, on_delete=models.CASCADE)

    class Meta:
        unique_together = [('warning', 'powiat')]
        indexes = [
            models.Index(fields=['warning']),
            models.Index(fields=['powiat']),
        ]

class PointSnapshot(models.Model):
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lon = models.DecimalField(max_digits=9, decimal_places=6)
    teryt4 = models.CharField(max_length=4)
    area_name = models.CharField(max_length=120, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    warnings = models.ManyToManyField(Warning, related_name='snapshots', blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['fetched_at']),
            models.Index(fields=['teryt4']),
        ]



class TerytCache(models.Model):
    # zapisujemy wartosci, ktire przychodza w zapytaniu
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lon = models.DecimalField(max_digits=9, decimal_places=6)

    # wynik mapowania
    teryt4 = models.CharField(max_length=4, null=True, blank=True)
    area_name = models.CharField(max_length=120, blank=True)

    # metryki uzycia
    hits = models.PositiveIntegerField(default=0)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('lat', 'lon')]
        indexes = [models.Index(fields=['lat', 'lon'])]

    def __str__(self):
        return f"{self.lat},{self.lon} -> {self.teryt4 or '-'}"