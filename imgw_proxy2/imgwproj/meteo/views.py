import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Warning, PointSnapshot
from .serializers import WarningSerializer
from .services import teryt4_from_latlon, fetch_imgw, upsert_imgw


# PRG / Geoportal – warstwa powiatow
GEO_URL = "https://mapy.geoportal.gov.pl/wss/ims/maps/PRG_gugik_wyszukiwarka/MapServer/1/query"


@api_view(["GET"])
def warnings_for_point(request):
    """
    Aktualne ostrzezenia dla punktu (lat/lon).
    Domyslnie: pobiera swiezy feed IMGW i zapisuje do DB.
    Zwraca też imgw_available=True/False.
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"},
                        status=status.HTTP_400_BAD_REQUEST)

    # mapowanie punktu -> TERYT-4
    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"},
                        status=status.HTTP_404_NOT_FOUND)

    # fetch + zapis do bazy (best-effort)
    imgw_ok = True
    try:
        items = fetch_imgw()
        upsert_imgw(items)
    except Exception:
        imgw_ok = False

    # aktywne TERAZ z DB (zadziała także, gdy IMGW padlo)
    qs = Warning.current_for_powiat(teryt4)
    data = WarningSerializer(qs, many=True).data
    
    future_count = (Warning.objects
                .filter(coverage__teryt4=teryt4, valid_from__gt=timezone.now())
                .distinct()
                .count())

    # opcjonalny snapshot
    saved = None
    if request.query_params.get("save") in ("1", "true", "True", "yes"):
        with transaction.atomic():
            snap = PointSnapshot.objects.create(
                lat=lat, lon=lon, teryt4=teryt4, area_name=area or ""
            )
            snap.warnings.set(qs)
            saved = snap.id

    return Response({
        "point": {"lat": lat, "lon": lon},
        "area": {"teryt4": teryt4, "name": area},
        "count": len(data),
        "items": data,
        "currently_active_IMGW_alerts": len(data),
        "saved_snapshot_id": saved,
        "imgw_available": imgw_ok,
        "future_IMGW_alerts_for_this_teryt": future_count,   
    })


@api_view(["GET"])
def status_view(request):
    last_pub = Warning.objects.aggregate(Max("published_at"))["published_at__max"]
    return Response({"now": timezone.now(), "last_published": last_pub})


def _parse_dt_local_utc(s: str | None):
    """
    Przyjmuje np. '2025-09-14' albo '2025-09-14T12:30:00' (czas lokalny PL)
    i zwraca aware UTC. Gdy podano sama date – 00:00:00 lokalnie.
    """
    if not s:
        return None
    try:
        if len(s) == 10:
            dt = datetime.strptime(s, "%Y-%m-%d")
        else:
            dt = datetime.fromisoformat(s)
    except Exception:
        return None
    return dt.replace(tzinfo=ZoneInfo("Europe/Warsaw")).astimezone(ZoneInfo("UTC"))


def _history_qs_for_teryt(teryt4: str, since_utc, until_utc, active_at_utc):
    """
    Historia ostrzezen dla powiatu:
    - active_at_utc: co obowiazywalo w danej chwili
    - since/until: przeciecie przedzialow czasu
    - brak filtrow: pelna historia
    """
    base = Warning.objects.filter(coverage__teryt4=teryt4).distinct()
    if active_at_utc:
        return base.filter(valid_from__lte=active_at_utc, valid_to__gte=active_at_utc) \
                   .order_by("-valid_from")
    if since_utc or until_utc:
        if since_utc and until_utc and since_utc > until_utc:
            since_utc, until_utc = until_utc, since_utc
        cond = Q()
        if since_utc:
            cond &= Q(valid_to__gte=since_utc)
        if until_utc:
            cond &= Q(valid_from__lte=until_utc)
        return base.filter(cond).order_by("-valid_from")
    return base.order_by("-valid_from")


@api_view(["GET"])
def warnings_for_teryt(request, teryt4: str):
    """Aktualne TERAZ ostrzezenia dla zadanego TERYT-4."""
    qs = Warning.current_for_powiat(teryt4)
    data = WarningSerializer(qs, many=True).data
    return Response({
        "teryt4": teryt4,
        "count": len(data),
        "items": data,
        "currently_active_IMGW_alerts": len(data),
    })


@api_view(["GET"])
def history_for_point(request):
    """
    Historia ostrzezen dla punktu (lat/lon).
    Query:
      lat, lon (wymagane)
      since=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      until=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      active_at=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      refresh=0|1 (czy dociągnac IMGW przed odpowiedzia; domyslnie 1)
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"}, status=400)

    imgw_ok = True
    do_refresh = request.query_params.get("refresh", "1") not in ("0", "false", "False", "no")
    if do_refresh:
        try:
            upsert_imgw(fetch_imgw())
        except Exception:
            imgw_ok = False

    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"}, status=404)

    since_utc  = _parse_dt_local_utc(request.query_params.get("since"))
    until_utc  = _parse_dt_local_utc(request.query_params.get("until"))
    active_utc = _parse_dt_local_utc(request.query_params.get("active_at"))

    qs = _history_qs_for_teryt(teryt4, since_utc, until_utc, active_utc)
    data = WarningSerializer(qs, many=True).data
    return Response({
        "point": {"lat": lat, "lon": lon},
        "area": {"teryt4": teryt4, "name": area},
        "filters": {"since": since_utc, "until": until_utc, "active_at": active_utc},
        "count": len(data),
        "items": data,
        "currently_active_IMGW_alerts": len(data),
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def history_for_teryt(request, teryt4: str):
    """
    Historia ostrzezen dla zadanego TERYT-4.
    Te same filtry co wyzej: since / until / active_at / refresh.
    """
    imgw_ok = True
    do_refresh = request.query_params.get("refresh", "1") not in ("0", "false", "False", "no")
    if do_refresh:
        try:
            upsert_imgw(fetch_imgw())
        except Exception:
            imgw_ok = False

    since_utc  = _parse_dt_local_utc(request.query_params.get("since"))
    until_utc  = _parse_dt_local_utc(request.query_params.get("until"))
    active_utc = _parse_dt_local_utc(request.query_params.get("active_at"))

    qs = _history_qs_for_teryt(teryt4, since_utc, until_utc, active_utc)
    data = WarningSerializer(qs, many=True).data
    return Response({
        "area": {"teryt4": teryt4},
        "filters": {"since": since_utc, "until": until_utc, "active_at": active_utc},
        "count": len(data),
        "items": data,
        "currently_active_IMGW_alerts": len(data),
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def warnings_live(request):
    """
    Świeży odczyt IMGW dla danego lat/lon, bez zapisu w bazie.
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"}, status=400)

    # mapowanie punkt -> TERYT (z cache TerytCache, jeżeli wlaczony)
    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"}, status=404)

    # pobierz feed IMGW (bez zapisu)
    try:
        items = fetch_imgw()
        imgw_ok = True
    except Exception as e:
        return Response({"detail": f"IMGW fetch failed: {e}"}, status=502)

    # filtruj ostrzezenia dla tego TERYT, ktore obowiazuja TERAZ
    now = datetime.now(ZoneInfo("UTC"))

    def _pl_to_utc(s):
        if not s:
            return None
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Warsaw"))
        return dt.astimezone(ZoneInfo("UTC"))

    filtered = []
    for it in items:
        if teryt4 not in {str(x) for x in (it.get("teryt") or [])}:
            continue
        vf, vt = _pl_to_utc(it.get("obowiazuje_od")), _pl_to_utc(it.get("obowiazuje_do"))
        if vf and vt and vf <= now <= vt:
            filtered.append({
                "id": it.get("id"),
                "event_name": it.get("nazwa_zdarzenia"),
                "level": it.get("stopien"),
                "probability": it.get("prawdopodobienstwo"),
                "valid_from": vf,
                "valid_to": vt,
                "content": it.get("tresc"),
                "comment": it.get("komentarz"),
                "office": it.get("biuro"),
            })

    return Response({
        "point": {"lat": lat, "lon": lon},
        "area": {"teryt4": teryt4, "name": area},
        "count": len(filtered),
        "items": filtered,
        "currently_active_IMGW_alerts": len(filtered),
        "imgw_available": imgw_ok,
    })


# --------- Narzędzie pomocnicze: lat/lon dla zadanego TERYT-4 ---------

@api_view(["GET"])
def centroid_for_teryt(request):
    """
    Zwraca (lat, lon) dla TERYT-4 z PRG.
    Fallbacki:
      1) centroid z serwera (returnCentroid)
      2) środek z wierzchołków polygonu
      3) środek bbox (returnExtentOnly)
    """
    teryt = (request.query_params.get("teryt") or "").strip()
    if not teryt.isdigit() or len(teryt) != 4:
        return Response({"detail": "teryt must be 4-digit string"}, status=400)

    params = {
        "f": "pjson",
        "where": f"teryt='{teryt}'",
        "outFields": "teryt,nazwa",
        "returnGeometry": "true",
        "returnCentroid": "true",
        "outSR": 4326,  # WGS84 (lon/lat)
    }
    try:
        r = requests.get(GEO_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return Response({"detail": f"Geoportal error: {e}"}, status=502)

    feats = data.get("features") or []
    if not feats:
        return Response({"detail": "not found"}, status=404)

    a = feats[0].get("attributes") or {}
    lon = lat = None

    # 1) centroid z odpowiedzi
    c = feats[0].get("centroid")
    if isinstance(c, dict):
        lon = c.get("x")
        lat = c.get("y")

    # 2) fallback – srodek z wierzchołków polygonu
    if lon is None or lat is None:
        geom = feats[0].get("geometry") or {}
        rings = geom.get("rings") or []
        xs, ys = [], []
        for ring in rings:
            for x, y in ring:
                xs.append(x); ys.append(y)
        if xs and ys:
            lon = sum(xs) / len(xs)
            lat = sum(ys) / len(ys)

    # 3) fallback – srodek bbox (returnExtentOnly)
    if lon is None or lat is None:
        try:
            r2 = requests.get(
                GEO_URL,
                params={
                    "f": "pjson",
                    "where": f"teryt='{teryt}'",
                    "returnExtentOnly": "true",
                    "outSR": 4326,
                },
                timeout=10,
            )
            r2.raise_for_status()
            ext = r2.json().get("extent") or {}
            xmin, xmax = ext.get("xmin"), ext.get("xmax")
            ymin, ymax = ext.get("ymin"), ext.get("ymax")
            if None not in (xmin, xmax, ymin, ymax):
                lon = (xmin + xmax) / 2.0
                lat = (ymin + ymax) / 2.0
        except Exception:
            pass

    if lon is None or lat is None:
        return Response({"detail": "centroid unavailable"}, status=502)

    return Response({
        "teryt4": str(a.get("teryt")),
        "name": a.get("nazwa"),
        "lat": float(lat),
        "lon": float(lon),
        "hint": f"http://127.0.0.1:8000/api/meteo/warnings?lat={lat}&lon={lon}"
    })



# meteo/views.py

@api_view(["GET"])
def future_for_teryt(request, teryt4: str):
    """
    Przyszłe ostrzezenia (valid_from > now) dla podanego TERYT-4.
    Parametr opcjonalny: refresh=0|1 (domyślnie 1) – czy dociąagnac IMGW przed odpowiedzia.
    """
    do_refresh = request.query_params.get("refresh", "1") not in ("0", "false", "False", "no")
    imgw_ok = True
    if do_refresh:
        try:
            upsert_imgw(fetch_imgw())
        except Exception:
            imgw_ok = False

    qs = Warning.objects.filter(
        coverage__teryt4=teryt4,
        valid_from__gt=timezone.now()
    ).order_by("valid_from").distinct()  # albo Warning.future_for_powiat(teryt4)

    return Response({
        "teryt4": teryt4,
        "count": qs.count(),
        "items": WarningSerializer(qs, many=True).data,
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def future_for_point(request):
    """
    Przyszle ostrzezenia dla punktu (lat/lon) – najpierw mapowanie do TERYT.
    Parametry: lat, lon (wymagane), refresh=0|1 (domyślnie 1).
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"}, status=400)

    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"}, status=404)

    do_refresh = request.query_params.get("refresh", "1") not in ("0", "false", "False", "no")
    imgw_ok = True
    if do_refresh:
        try:
            upsert_imgw(fetch_imgw())
        except Exception:
            imgw_ok = False

    qs = Warning.objects.filter(
        coverage__teryt4=teryt4,
        valid_from__gt=timezone.now()
    ).order_by("valid_from").distinct()  # albo Warning.future_for_powiat(teryt4)

    return Response({
        "point": {"lat": lat, "lon": lon},
        "area": {"teryt4": teryt4, "name": area},
        "count": qs.count(),
        "items": WarningSerializer(qs, many=True).data,
        "imgw_available": imgw_ok,
    })
