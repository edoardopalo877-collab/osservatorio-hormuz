"""Posizioni delle navi nel Golfo da Global Fishing Watch (AIS satellitare + terrestre, ritardo ~96 ore).
Usa il dataset public-global-presence (una posizione all'ora per nave). Scrive gfw.json.
Dati: Global Fishing Watch, CC BY-NC 4.0, solo uso non commerciale."""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("GFW_TOKEN", "").strip()
OUT = sys.argv[1] if len(sys.argv) > 1 else "gfw.json"
RITARDO_GIORNI = int(os.environ.get("GFW_RITARDO", "4"))
# Golfo Persico, Hormuz, Golfo di Oman, Mar Arabico occidentale, Mar Rosso
POLI = [
    [[47.5, 23.5], [57.5, 23.5], [57.5, 30.6], [47.5, 30.6], [47.5, 23.5]],
    [[56.0, 21.5], [62.0, 21.5], [62.0, 26.8], [56.0, 26.8], [56.0, 21.5]],
    [[32.0, 11.5], [44.5, 11.5], [44.5, 30.2], [32.0, 30.2], [32.0, 11.5]],
]
URL = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"

def chiama(giorno, poli, geo_stringa=True):
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [poli]}}]}
    q = {"spatial-resolution": "HIGH", "format": "JSON", "group-by": "VESSEL_ID", "temporal-resolution": "HOURLY",
         "datasets[0]": "public-global-presence:latest", "date-range": f"{giorno},{giorno + timedelta(days=1)}", "spatial-aggregation": "false"}
    body = json.dumps({"geojson": json.dumps(fc) if geo_stringa else fc}).encode()
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(q), data=body, method="POST",
                                 headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json", "Content-Language": "en-EN"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())

def righe(x):
    if isinstance(x, dict):
        if "lat" in x and "lon" in x:
            yield x
        else:
            for v in x.values():
                yield from righe(v)
    elif isinstance(x, list):
        for v in x:
            yield from righe(v)

def g(r, *nomi):
    for n in nomi:
        if r.get(n) not in (None, ""):
            return r[n]
    return None

def main():
    if not TOKEN:
        print("Manca GFW_TOKEN"); sys.exit(0)
    giorno = (datetime.now(timezone.utc) - timedelta(days=RITARDO_GIORNI)).date()
    tutte = []
    for i, p in enumerate(POLI):
        dati = None
        for tent in range(3):
            try:
                dati = chiama(giorno, p, geo_stringa=(tent != 1))
                break
            except urllib.error.HTTPError as e:
                print("zona", i, "HTTP", e.code, e.read()[:400]); time.sleep(10 if e.code in (429, 503, 524) else 2)
            except Exception as e:
                print("zona", i, "errore", repr(e)); time.sleep(5)
        if dati is None:
            continue
        rr = list(righe(dati))
        if rr and i == 0:
            print("esempio:", json.dumps(rr[0])[:500])
        print("zona", i, "righe", len(rr))
        tutte += rr
    if not tutte:
        print("nessun dato"); sys.exit(0)
    navi = {}
    for r in tutte:
        vid = str(g(r, "vesselId", "vessel_id", "mmsi") or "")
        if not vid:
            continue
        d = str(g(r, "date") or "")
        s = navi.setdefault(vid, {"pts": []})
        for k, nomi in (("n", ("shipName", "ship_name")), ("mmsi", ("mmsi",)), ("fl", ("flag",)), ("ty", ("vesselType", "vessel_type")),
                        ("imo", ("imo",)), ("cs", ("callsign",))):
            v = g(r, *nomi)
            if v is not None:
                s[k] = v
        s["pts"].append((d, round(float(r["lat"]), 3), round(float(r["lon"]), 3)))
    out = {}
    for vid, s in navi.items():
        pts = sorted(set(s.pop("pts")))
        ult = pts[-1]
        s["la"], s["lo"], s["t"] = ult[1], ult[2], ult[0]
        s["tr"] = [[p[1], p[2]] for p in pts[-8:]]
        out[vid] = s
    res = {"agg": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "giorno": str(giorno),
           "fonte": "Global Fishing Watch, public-global-presence (CC BY-NC 4.0)", "navi": out}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    tipi = {}
    for s in out.values():
        tipi[s.get("ty")] = tipi.get(s.get("ty"), 0) + 1
    print("navi", len(out), "tipi", tipi)

if __name__ == "__main__":
    main()
