"""Этап 3 — фото со свободной лицензией из Wikimedia Commons.

python fetch_images.py            скачать до 3 кандидатов на каждый ключ из ASSETS
python fetch_images.py --sheet    собрать контактный лист для просмотра
Выбор кандидата: build/image_choice.json {"ключ": номер_кандидата} (по умолчанию 0).

Берутся только лицензии, допускающие коммерческое использование без «копилефта»:
Public domain, CC0, CC BY (любая версия). CC BY-SA и прочие пропускаются.
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMG = ROOT / "assets" / "images"
UA = {"User-Agent": "WhatIfVideoBuilder/1.0 (educational YouTube video; image credits listed in description)"}
API = "https://commons.wikimedia.org/w/api.php"
OK = re.compile(r"^(public domain|pd\b|pd-|cc0|cc[ -]?by[ -]?\d|cc[ -]?by$|cc by \d)", re.I)


def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=150) as r:
                time.sleep(6.0)
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            wait = 90 + attempt * 30 if "429" in str(e) else 3 + attempt * 4
            print(f"  API: {e} — жду {wait} с", flush=True)
            time.sleep(wait)
    raise RuntimeError("Wikimedia API недоступен")


def strip(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def candidates(query, n=3):
    out = []
    for q in query.split("|"):
        out += [c for c in _search(q.strip(), n) if c["title"] not in {o["title"] for o in out}]
        if len(out) >= n:
            break
    return out[:n]


def _search(query, n):
    d = api({"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
             "gsrlimit": 50, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": 1920})
    pages = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 999))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = strip(meta.get("LicenseShortName", {}).get("value", ""))
        if "sa" in lic.lower().replace("usage", "") and "by-sa" in lic.lower().replace(" ", "-"):
            continue
        if not OK.search(lic) or "SA" in lic.upper().split():
            continue
        w, h = ii.get("width", 0), ii.get("height", 0)
        if ii.get("mime") not in ("image/jpeg", "image/png") or w < 1200 or w / max(h, 1) < 1.0:
            continue
        out.append({"title": p["title"], "page": ii.get("descriptionurl"), "url": (ii.get("thumburl") or ii.get("url")).replace("//thumb.wikimedia.org/", "//upload.wikimedia.org/"),
                    "license": lic, "license_url": strip(meta.get("LicenseUrl", {}).get("value", "")),
                    "author": strip(meta.get("Artist", {}).get("value", ""))[:120] or "неизвестен",
                    "width": w, "height": h})
        if len(out) >= n:
            break
    return out


def fetch_all():
    sys.path.insert(0, str(ROOT))
    from shots import ASSETS
    IMG.mkdir(parents=True, exist_ok=True)
    meta_path = ROOT / "build" / "images.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    import collections
    shots = json.loads((ROOT / "build" / "shots.json").read_text(encoding="utf-8"))["shots"]
    uses = collections.Counter({"green_city": 1, "slum_towers": 1})   # фоны для сравнения утопия/антиутопия
    for s in shots:
        v = s["visual"]
        if isinstance(v, str) and v.startswith("img:"):
            uses[v[4:]] += 1
        elif isinstance(v, dict) and v.get("photo"):
            uses[v["photo"]] += 1
    for key, query in ASSETS.items():
        if not uses[key]:
            continue
        if key in meta and all((IMG / f"{key}_{i}.jpg").exists() for i in range(len(meta[key]))) and meta[key]:
            continue
        cands = candidates(query, 3 if uses[key] >= 3 else 2)
        for i, c in enumerate(cands):
            dest = IMG / f"{key}_{i}.jpg"
            for attempt in range(4):
                try:
                    req = urllib.request.Request(c["url"], headers=UA)
                    with urllib.request.urlopen(req, timeout=120) as r:
                        dest.write_bytes(r.read())
                    break
                except Exception as e:  # noqa: BLE001
                    wait = 90 + attempt * 30 if "429" in str(e) else 3 + attempt * 4
                    print(f"  повтор {key}_{i}: {e} — жду {wait} с", flush=True)
                    time.sleep(wait)
            time.sleep(10.0)
        meta[key] = cands
        print(f"{key:22s} {len(cands)} шт. — {query}", flush=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def sheet():
    from PIL import Image, ImageDraw, ImageFont
    meta = json.loads((ROOT / "build" / "images.json").read_text(encoding="utf-8"))
    keys = list(meta)
    tw, th = 320, 180
    f = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 16)
    for page in range(0, len(keys), 14):
        ks = keys[page:page + 14]
        im = Image.new("RGB", (tw * 3 + 200, th * len(ks)), (20, 20, 20))
        d = ImageDraw.Draw(im)
        for r, k in enumerate(ks):
            d.text((8, r * th + 8), k, font=f, fill=(255, 255, 0))
            for i in range(len(meta[k])):
                p = IMG / f"{k}_{i}.jpg"
                if p.exists():
                    t = Image.open(p).convert("RGB")
                    t.thumbnail((tw - 6, th - 6))
                    im.paste(t, (200 + i * tw, r * th + 3))
                    d.text((204 + i * tw, r * th + 6), str(i), font=f, fill=(255, 80, 80))
        im.save(ROOT / "build" / f"images_sheet_{page // 14 + 1}.jpg", quality=85)


if __name__ == "__main__":
    sheet() if "--sheet" in sys.argv else fetch_all()
