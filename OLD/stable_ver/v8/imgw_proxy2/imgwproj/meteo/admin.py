from django.contrib import admin
from .models import Powiat, Warning, WarningCoverage, PointSnapshot, TerytCache

@admin.register(Powiat)
class PowiatAdmin(admin.ModelAdmin):
    list_display = ("teryt4", "name")
    search_fields = ("teryt4", "name")

@admin.register(Warning)
class WarningAdmin(admin.ModelAdmin):
    list_display = ("id", "event_name", "level", "valid_from", "valid_to", "published_at")
    list_filter = ("level", "office")
    search_fields = ("id", "event_name", "content")
    date_hierarchy = "valid_from"

admin.site.register(WarningCoverage)

@admin.register(PointSnapshot)
class PointSnapshotAdmin(admin.ModelAdmin):
    list_display = ("lat", "lon", "teryt4", "area_name", "fetched_at")
    list_filter = ("teryt4",)
    date_hierarchy = "fetched_at"

@admin.register(TerytCache)
class TerytCacheAdmin(admin.ModelAdmin):
    list_display = ("lat","lon","teryt4","area_name","hits","first_seen","last_used")
    search_fields = ("teryt4","area_name")
    list_filter = ("teryt4",)
