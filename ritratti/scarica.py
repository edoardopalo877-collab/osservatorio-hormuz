"""Scarica i ritratti dei leader da Wikimedia Commons (solo licenze libere) e li ritaglia sul volto."""
import json, re, sys, urllib.parse, urllib.request, io, html
import cv2, numpy as np
UA = {"User-Agent": "OsservatorioHormuz/1.0 (https://osservatoriohormuz.com; edoardopalo877@gmail.com)"}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
def jget(url):
    import time
    for i in range(4):
        d = json.loads(get(url))
        if "error" not in d: return d
        print("errore API, riprovo:", d["error"].get("code")); time.sleep(3 * (i + 1))
    return d
FREE = re.compile(r"^(CC0|CC BY|Public domain|PD|GFDL|Attribution)", re.I)
elenco = json.load(open("ritratti/elenco.json"))
try:
    crediti = json.load(open("ritratti/crediti.json"))
except Exception:
    crediti = {}
try:
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
except Exception as e:
    print("riconoscimento volti non disponibile:", e); casc = None
for id_, title in elenco.items():
    try:
        cands = []
        try:
            s = jget("https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title))
            cands.append(urllib.parse.unquote(s["originalimage"]["source"].split("?")[0].split("/")[-1]))
        except Exception as e:
            print(id_, "riassunto Wikipedia non disponibile:", e)
        sr = jget("https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search&srnamespace=6&srlimit=8&srsearch=" + urllib.parse.quote(title.replace("_", " ") + " filetype:bitmap"))
        cands += [r["title"][5:] for r in sr["query"]["search"]]
        ii = None
        for fname in cands:
            q = jget("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=600&titles=" + urllib.parse.quote("File:" + fname))
            page = next(iter(q["query"]["pages"].values()))
            if "imageinfo" not in page:
                print(id_, "non su Commons:", fname); continue
            md = page["imageinfo"][0].get("extmetadata", {})
            lic = md.get("LicenseShortName", {}).get("value", "")
            if not FREE.search(lic):
                print(id_, "licenza non libera:", fname, lic); continue
            ii = page["imageinfo"][0]; fname = page["title"][5:].replace(" ", "_"); break
        if ii is None:
            print(id_, "NESSUNA FOTO LIBERA"); continue
        artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", ""))
        artist = re.sub(r"\s+", " ", html.unescape(artist)).strip()[:80]
        if "Unknown author" in artist: artist = "autore sconosciuto"
        img = cv2.imdecode(np.frombuffer(get(ii["thumburl"]), np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        faces = [] if casc is None else casc.detectMultiScale(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 1.1, 5, minSize=(w // 10, w // 10))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            cx, cy, side = x + fw / 2, y + fh / 2 + fh * 0.08, fw * 1.7
        else:
            print(id_, "volto non trovato, ritaglio in alto")
            side = min(w, h * 0.6); cx, cy = w / 2, side / 2 + h * 0.03
        side = min(side, w, h)
        x0 = int(max(0, min(w - side, cx - side / 2))); y0 = int(max(0, min(h - side, cy - side / 2)))
        crop = cv2.resize(img[y0:y0 + int(side), x0:x0 + int(side)], (160, 160), interpolation=cv2.INTER_AREA)
        cv2.imwrite(f"ritratti/{id_}.jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 82])
        crediti[id_] = {"file": fname, "licenza": lic, "autore": artist, "faccia": bool(len(faces))}
        print(id_, "ok", lic, artist, "volto" if len(faces) else "")
    except Exception as e:
        print(id_, "errore", e)
json.dump(crediti, open("ritratti/crediti.json", "w"), ensure_ascii=False, indent=1)
