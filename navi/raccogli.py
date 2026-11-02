"""Raccoglie le posizioni AIS delle navi tra Golfo, Mar Rosso e Mar Arabico da aisstream.io
e scrive navi.json (posizioni recenti + ultime tracce). Gira in una GitHub Action ogni 15 minuti."""
import asyncio, json, os, sys, time
from datetime import datetime, timezone
import websockets

KEY = os.environ.get("AISSTREAM_KEY", "").strip()
OUT = sys.argv[1] if len(sys.argv) > 1 else "navi.json"
DURATA = int(os.environ.get("DURATA", "540"))      # secondi di ascolto per giro
TIENI_ORE = 12                                      # navi non viste da piu' di 12 ore escono
PUNTI_TRACCIA = 8
BOX = [[[11.0, 32.0], [31.5, 66.0]]]               # [lat,lon] SO -> NE: Mar Rosso, Golfo, Golfo di Oman, Mar Arabico

def ora():
    return datetime.now(timezone.utc)

def carica():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"navi": {}}

async def ascolta(navi):
    sub = {"APIKey": KEY, "BoundingBoxes": BOX,
           "FilterMessageTypes": ["PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport", "ShipStaticData", "StaticDataReport"]}
    fine = time.time() + DURATA
    n = 0
    while time.time() < fine:
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream", open_timeout=30, ping_interval=20) as ws:
                await ws.send(json.dumps(sub))
                while time.time() < fine:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=max(1, fine - time.time()))
                    except asyncio.TimeoutError:
                        break
                    m = json.loads(raw)
                    if "error" in m:
                        print("errore aisstream:", m["error"]); return n
                    md = m.get("MetaData", {}); mmsi = str(md.get("MMSI", ""))
                    if not mmsi:
                        continue
                    t = m.get("MessageType"); body = m.get("Message", {}).get(t, {})
                    s = navi.setdefault(mmsi, {"tr": []})
                    nome = (md.get("ShipName") or "").strip()
                    if nome: s["n"] = nome
                    if t in ("ShipStaticData",):
                        if body.get("Type"): s["ty"] = body["Type"]
                        if body.get("Destination"): s["de"] = body["Destination"].strip()
                        d = body.get("Dimension") or {}
                        if d.get("A") is not None: s["lu"] = (d.get("A") or 0) + (d.get("B") or 0)
                        if body.get("MaximumStaticDraught"): s["dr"] = body["MaximumStaticDraught"]
                        if body.get("ImoNumber"): s["imo"] = body["ImoNumber"]
                    elif t == "StaticDataReport":
                        b = body.get("ReportB") or {}
                        if b.get("Valid") and b.get("ShipType"): s["ty"] = b["ShipType"]
                    else:
                        lat, lon = md.get("latitude"), md.get("longitude")
                        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
                            continue
                        s["la"], s["lo"] = round(lat, 4), round(lon, 4)
                        sog = body.get("Sog"); cog = body.get("Cog"); hd = body.get("TrueHeading")
                        if sog is not None and sog < 102.3: s["v"] = round(sog, 1)
                        if cog is not None and cog < 360: s["c"] = round(cog)
                        if hd is not None and hd < 360: s["h"] = hd
                        if t == "PositionReport" and body.get("NavigationalStatus") is not None: s["st"] = body["NavigationalStatus"]
                        s["t"] = int(time.time())
                        tr = s["tr"]
                        if not tr or abs(tr[-1][0] - s["la"]) + abs(tr[-1][1] - s["lo"]) > 0.02:
                            tr.append([s["la"], s["lo"], s["t"]]); del tr[:-PUNTI_TRACCIA]
                        n += 1
        except Exception as e:
            print("connessione:", repr(e)); await asyncio.sleep(5)
    return n

def main():
    if not KEY:
        print("Manca il segreto AISSTREAM_KEY"); sys.exit(1)
    dati = carica(); navi = dati.get("navi", {})
    n = asyncio.run(ascolta(navi))
    lim = time.time() - TIENI_ORE * 3600
    navi = {k: v for k, v in navi.items() if v.get("t", 0) >= lim and "la" in v}
    for v in navi.values():
        v["tr"] = [p for p in v.get("tr", []) if p[2] >= lim]
    out = {"agg": ora().strftime("%Y-%m-%dT%H:%M:%SZ"), "messaggi_ultimo_giro": n, "secondi_ascolto": DURATA,
           "fonte": "aisstream.io (ricevitori AIS terrestri)", "navi": navi}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"messaggi {n}, navi {len(navi)}")

if __name__ == "__main__":
    main()
