# meteo/services.py
from __future__ import annotations

import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Warning, Powiat, TerytCache

# --- zrodla danych ---
IMGW_URL = "https://danepubliczne.imgw.pl/api/data/warningsmeteo"
GEO_URL  = "https://mapy.geoportal.gov.pl/wss/ims/maps/PRG_gugik_wyszukiwarka/MapServer/1/query"


def teryt4_from_latlon(
    lat: float,
    lon: float,
    *,
    use_cache: Optional[bool] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Mapuje (lat, lon) -> (teryt4, nazwa_pow) z wykorzystaniem trwalego cache'u w DB.
    - use_cache=True  -> korzysta z TerytCache (read/write)
    - use_cache=False -> pomija cache, pyta Geoportal i NIE zapisuje do cache
    - use_cache=None  -> decyzja wg settings.METEO_CACHE_ENABLED (domyslnie True)
    """
    if use_cache is None:
        use_cache = getattr(settings, "METEO_CACHE_ENABLED", True)

    # normalizacja do 6 miejsc (jak w modelach)
    lat = round(float(lat), 6)
    lon = round(float(lon), 6)

    # 1) proba odczytu z cache (DB)
    if use_cache:
        try:
            rec = TerytCache.objects.get(lat=lat, lon=lon)
            TerytCache.objects.filter(pk=rec.pk).update(
                hits=F("hits") + 1,
                last_used=timezone.now(),
            )
            return rec.teryt4, rec.area_name
        except TerytCache.DoesNotExist:
            pass

    # 2) zapytanie do Geoportalu
    geom = json.dumps({"x": lon, "y": lat})  # ArcGIS: x=lon, y=lat
    params = {
        "f": "pjson",
        "geometry": geom,
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "teryt,nazwa",
        "returnGeometry": "false",
    }
    r = requests.get(GEO_URL, params=params, timeout=10)
    r.raise_for_status()
    feats = r.json().get("features") or []
    if not feats:
        # zapisujemy „brak” tylko gdy cache wlaczony; dzieki temu nie spamujemy Geoportalu
        if use_cache:
            with transaction.atomic():
                obj, created = TerytCache.objects.get_or_create(
                    lat=lat,
                    lon=lon,
                    defaults={"teryt4": None, "area_name": ""},
                )
                if not created:
                    TerytCache.objects.filter(pk=obj.pk).update(
                        last_used=timezone.now(),
                        hits=F("hits") + 1,
                    )
        return None, None

    attrs = feats[0]["attributes"]
    teryt = str(attrs.get("teryt"))
    name  = (attrs.get("nazwa") or "").strip()

    # 3) zapis do cache (jesli wlaczony)
    if use_cache:
        with transaction.atomic():
            obj, created = TerytCache.objects.get_or_create(
                lat=lat,
                lon=lon,
                defaults={"teryt4": teryt, "area_name": name, "hits": 1},
            )
            if not created:
                TerytCache.objects.filter(pk=obj.pk).update(
                    teryt4=teryt,
                    area_name=name,
                    last_used=timezone.now(),
                    hits=F("hits") + 1,
                )

    return teryt, name


def _pl_to_utc(s: str) -> Optional[datetime]:
    """Daty IMGW sa w Europe/Warsaw; zwroc aware UTC."""
    if not s:
        return None
    dt_local = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("Europe/Warsaw")
    )
    return dt_local.astimezone(ZoneInfo("UTC"))


def fetch_imgw() -> list[dict]:
    """Pobiera surowy feed IMGW (lista ostrzezen dla calej Polski)."""
    r = requests.get(IMGW_URL, timeout=20)
    r.raise_for_status()
    return r.json()


def upsert_imgw(items: list[dict]) -> int:
    """
    Upsert rekordow IMGW po id + M2M z powiatami (TERYT-4).
    Zwraca liczbe zaktualizowanych/dodanych ostrzezen.
    """
    upserted = 0
    for it in items:
        wid = str(it.get("id") or "").strip()
        if not wid:
            continue

        obj, _ = Warning.objects.update_or_create(
            id=wid,
            defaults=dict(
                event_name=(it.get("nazwa_zdarzenia") or "").strip(),
                level=int(str(it.get("stopien") or "0")),
                probability=int(str(it.get("prawdopodobienstwo") or "0")),
                valid_from=_pl_to_utc(it.get("obowiazuje_od")),
                valid_to=_pl_to_utc(it.get("obowiazuje_do")),
                published_at=_pl_to_utc(it.get("opublikowano")),
                content=it.get("tresc") or "",
                comment=it.get("komentarz") or "",
                office=it.get("biuro") or "",
            ),
        )
        # powiazanie z powiatami (lista teryt-4)
        teryts = [
            str(x).strip()
            for x in (it.get("teryt") or [])
            if str(x).isdigit() and len(str(x)) == 4
        ]
        if teryts:
            powiaty = []
            for t4 in teryts:
                p, _ = Powiat.objects.get_or_create(teryt4=t4)
                powiaty.append(p)
            obj.coverage.set(powiaty)

        upserted += 1

    return upserted
