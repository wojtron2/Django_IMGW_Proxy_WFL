from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from .models import Warning, PointSnapshot
from .serializers import WarningSerializer
from .services import teryt4_from_latlon, fetch_imgw, upsert_imgw

@api_view(["GET"])
def warnings_for_point(request):
    # 1) lat/lon
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except Exception:
        return Response({"detail": "lat and lon are required floats"}, status=status.HTTP_400_BAD_REQUEST)

    # 2) lat/lon -> TERYT-4
    teryt4, area = teryt4_from_latlon(lat, lon)
    if not teryt4:
        return Response({"detail": "county not found for this point"}, status=status.HTTP_404_NOT_FOUND)

    # 3) dociagnij i upsertuj feed IMGW (best-effort; jak padnie, korzystamy z bazy)
    try:
        items = fetch_imgw()
        upsert_imgw(items)
    except Exception:
        pass

    # 4) aktywne teraz ostrzezenia dla powiatu
    qs = Warning.current_for_powiat(teryt4)
    data = WarningSerializer(qs, many=True).data

    # 5) opcjonalny zapis snapshotu
    saved = None
    if request.query_params.get("save") in ("1","true","True","yes"):
        with transaction.atomic():
            snap = PointSnapshot.objects.create(lat=lat, lon=lon, teryt4=teryt4, area_name=area or "")
            snap.warnings.set(qs)
            saved = snap.id

    return Response({
        "point": {"lat": lat, "lon": lon},
        "area": {"teryt4": teryt4, "name": area},
        "count": len(data),
        "items": data,
        "saved_snapshot_id": saved,
    })
