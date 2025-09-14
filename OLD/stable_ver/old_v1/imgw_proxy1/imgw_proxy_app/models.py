from django.db import models

class Warning(models.Model):
    uid = models.CharField(max_length=128, unique=True, db_index=True)
    teryt_powiat = models.CharField(max_length=6, null=True, blank=True, db_index=True)
    teryt_woj = models.CharField(max_length=2, null=True, blank=True, db_index=True)
    valid_from = models.DateTimeField(null=True, blank=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    fetched_at = models.DateTimeField(auto_now=True)
    raw = models.JSONField()

    class Meta:
        indexes = [models.Index(fields=["is_active", "valid_to"])]