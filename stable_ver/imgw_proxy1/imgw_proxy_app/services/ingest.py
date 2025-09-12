import hashlib, requests
from datetime import datetime

URL = "https://danepubliczne.imgw.pl/api/data/warningsmeteo"

def fetch_imgw():
    r = requests.get(URL, timeout=20)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("results", [])

def normalize(rec):
    def parse_dt(v):
        if not v: 
            return None
        try:
            return datetime.fromisoformat(v.replace("Z","+00:00"))
        except Exception:
            return None

    t_pow = rec.get("teryt_powiat") or rec.get("powiat_teryt") or rec.get("powiat_taryt")
    t_woj = rec.get("teryt_woj") or (t_pow[:2] if t_pow else None)

    uid = hashlib.sha256(str(rec).encode("utf-8")).hexdigest()

    return {
        "uid": uid,
        "teryt_powiat": t_pow,
        "teryt_woj": t_woj,
        "valid_from": parse_dt(rec.get("from") or rec.get("od")),
        "valid_to":   parse_dt(rec.get("to")   or rec.get("do")),
        "is_active": True,
        "raw": rec,
    }
