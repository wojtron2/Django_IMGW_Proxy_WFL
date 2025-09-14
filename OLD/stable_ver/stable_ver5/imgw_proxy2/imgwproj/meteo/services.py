import json, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from .models import Warning, Powiat

IMGW_URL = "https://danepubliczne.imgw.pl/api/data/warningsmeteo"
GEO_URL  = "https://mapy.geoportal.gov.pl/wss/ims/maps/PRG_gugik_wyszukiwarka/MapServer/1/query"

def teryt4_from_latlon(lat: float, lon: float):
    """Zwraca (teryt4, nazwa_pow) dla danego punktu, korzystajac z Geoportalu."""
    geom = json.dumps({"x": round(lon, 6), "y": round(lat, 6)})  # ArcGIS: x=lon, y=lat
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
        return None, None
    a = feats[0]["attributes"]
    return str(a.get("teryt")), a.get("nazwa")

def _pl_to_utc(s: str):
    """Daty IMGW sa w Europe/Warsaw; konwertuj do UTC (aware)."""
    if not s:
        return None
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Warsaw"))
    return dt.astimezone(ZoneInfo("UTC"))

def fetch_imgw():
    r = requests.get(IMGW_URL, timeout=20)
    r.raise_for_status()
    return r.json()

def upsert_imgw(items):
    """Upsert rekordow IMGW po id + M2M powiatow."""
    upserted = 0
    for it in items:
        wid = str(it.get("id") or "")
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
        # Powiazanie powiatow
        teryts = [str(x).strip() for x in (it.get("teryt") or []) if str(x).isdigit() and len(str(x)) == 4]
        if teryts:
            powiaty = []
            for t4 in teryts:
                p, _ = Powiat.objects.get_or_create(teryt4=t4)
                powiaty.append(p)
            obj.coverage.set(powiaty)
        upserted += 1
    return upserted
