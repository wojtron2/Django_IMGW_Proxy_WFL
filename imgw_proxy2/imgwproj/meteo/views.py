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


@api_view(["GET"])
def warnings_for_point(request):
    """
    Aktualne ostrzeżenia IMGW dla punktu (lat/lon).
    Domyślnie pobiera świeży feed i zapisuje do DB.
    Zwraca też pole imgw_available=True/False.
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"},
                        status=status.HTTP_400_BAD_REQUEST)

    # mapowanie punktu
    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"},
                        status=status.HTTP_404_NOT_FOUND)

    # fetch-on-demand + zapis do DB
    imgw_ok = True
    try:
        items = fetch_imgw()
        upsert_imgw(items)
    except Exception:
        imgw_ok = False

    # aktywne ostrzezenia (z DB – nawet jesli IMGW padlo)
    qs = Warning.current_for_powiat(teryt4)
    data = WarningSerializer(qs, many=True).data

    # opcjonalny zapis snapshotu
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
        "currently_active_IMGW_alerts": len(data) > 0,
        "saved_snapshot_id": saved,
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def status_view(request):
    last_pub = Warning.objects.aggregate(Max("published_at"))["published_at__max"]
    return Response({"now": timezone.now(), "last_published": last_pub})


def _parse_dt_local_utc(s: str | None):
    """
    Przyjmuje np. '2025-09-14' albo '2025-09-14T12:30:00' (czas lokalny PL)
    i zwraca aware UTC. Gdy podano samą datę, przyjmujemy 00:00:00 lokalnie.
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
    Zwraca QS ostrzeżeń dla powiatu:
    - active_at_utc: co obowiązywało o tej chwili
    - since/until: przecięcie przedziałów
    - bez filtrów: pełna historia
    """
    base = Warning.objects.filter(coverage__teryt4=teryt4).distinct()
    if active_at_utc:
        return base.filter(valid_from__lte=active_at_utc, valid_to__gte=active_at_utc).order_by("-valid_from")
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
    """Aktualne TERAZ ostrzezenia dla zadanego TERYT-4 (bez Geoportalu)."""
    qs = Warning.current_for_powiat(teryt4)
    data = WarningSerializer(qs, many=True).data
    return Response({
        "teryt4": teryt4,
        "count": len(data),
        "items": data,
        "currently_active_IMGW_alerts": len(data) > 0,
    })


@api_view(["GET"])
def history_for_point(request):
    """
    Historia ostrzezen dla punktu (lat/lon), z opcjonalnym filtrem czasu.
    Query params:
      lat, lon (wymagane)
      since=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      until=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      active_at=YYYY-MM-DD[THH:MM:SS] (lokalny PL)
      refresh=0|1 (czy dociagac IMGW przed odpowiedzia; domyslnie 1)
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
        "currently_active_IMGW_alerts": len(data) > 0,
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def history_for_teryt(request, teryt4: str):
    """
    Historia ostrzezen dla zadanego TERYT-4 (bez Geoportalu).
    Te same parametry filtrujace co wyzej: since / until / active_at / refresh.
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
        "currently_active_IMGW_alerts": len(data) > 0,
        "imgw_available": imgw_ok,
    })


@api_view(["GET"])
def warnings_live(request):
    """
    Swiezy odczyt ostrzezen IMGW dla danego lat/lon, bez zapisu w bazie.
    """
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"}, status=400)

    # mapowanie punkt -> TERYT (z cache TerytCache, jesli wlaczony)
    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"}, status=404)

    # pobierz feed IMGW (ale nie zapisuj)
    try:
        items = fetch_imgw()
        imgw_ok = True
    except Exception as e:
        return Response({"detail": f"IMGW fetch failed: {e}"}, status=502)

    # filtruj ostrzezenia z feedu dla tego TERYT, ktore obowiazuja teraz
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
        "currently_active_IMGW_alerts": len(filtered) > 0,
        "imgw_available": imgw_ok,
    })
