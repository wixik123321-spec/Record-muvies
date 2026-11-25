"""Этап 3 (дополнение) — фото со свободной лицензией через Openverse (каталог CC-фото, источник Flickr).

Wikimedia ограничивает частоту скачиваний (HTTP 429), поэтому недостающие ключи добираются здесь.
Берутся только лицензии без ограничений на коммерческое использование и без «копилефта»:
CC BY, CC0, Public Domain Mark. Метаданные пишутся в тот же build/images.json.

python fetch_openverse.py                 все недостающие ключи
python fetch_openverse.py key1 key2       перекачать указанные ключи (заменяет варианты)
"""

import collections
import json
import sys
import time
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
IMG = ROOT / "assets" / "images"
UA = {"User-Agent": "WhatIfVideoBuilder/1.0 (educational YouTube video; image credits listed in description)"}
API = "https://api.openverse.org/v1/images/"
LIC_NAME = {"by": "CC BY", "cc0": "CC0", "pdm": "Public Domain Mark"}


def get(url, tries=5):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            wait = 30 + a * 30 if "429" in str(e) else 2 + a * 3
            print(f"  повтор: {str(e)[:70]} — жду {wait} с", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"не удалось скачать {url}")


def search(query, n):
    out, seen = [], set()
    for q in query.split("|"):
        params = {"q": q.strip(), "license": "by,cc0,pdm", "source": "flickr", "page_size": 20,
                  "mature": "false", "aspect_ratio": "wide"}
        d = json.loads(get(API + "?" + urllib.parse.urlencode(params)))
        time.sleep(1.5)
        for r in d.get("results", []):
            w, h = r.get("width") or 0, r.get("height") or 0
            if r["id"] in seen or w < 1000 or w / max(h, 1) < 1.2 or r.get("license") not in LIC_NAME:
                continue
            if "live.staticflickr.com" not in r.get("url", ""):
                continue
            seen.add(r["id"])
            out.append({"title": r.get("title") or "untitled", "page": r.get("foreign_landing_url"),
                        "url": r["url"], "license": f"{LIC_NAME[r['license']]} {r.get('license_version') or ''}".strip(),
                        "license_url": r.get("license_url") or "", "author": (r.get("creator") or "неизвестен")[:120],
                        "width": w, "height": h, "source": "Openverse / Flickr", "attribution": r.get("attribution", "")})
            if len(out) >= n:
                return out
    return out


def main(only=None):
    sys.path.insert(0, str(ROOT))
    from shots import ASSETS
    meta_path = ROOT / "build" / "images.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    shots = json.loads((ROOT / "build" / "shots.json").read_text(encoding="utf-8"))["shots"]
    uses = collections.Counter({"green_city": 1, "slum_towers": 1})
    for s in shots:
        v = s["visual"]
        if isinstance(v, str) and v.startswith("img:"):
            uses[v[4:]] += 1
        elif isinstance(v, dict) and v.get("photo"):
            uses[v["photo"]] += 1
    for key, query in ASSETS.items():
        if only and key not in only:
            continue
        if not uses[key]:
            continue
        have = [i for i in range(len(meta.get(key, []))) if (IMG / f"{key}_{i}.jpg").exists()]
        if have and not only:
            continue
        cands = search(query, 3)
        got = []
        for c in cands:
            data = get(c["url"])
            im = Image.open(BytesIO(data)).convert("RGB")
            im.save(IMG / f"{key}_{len(got)}.jpg", quality=93)
            got.append(c)
            time.sleep(0.5)
        if got:
            for old in IMG.glob(f"{key}_*.jpg"):   # убрать лишние старые варианты
                if int(old.stem.rsplit("_", 1)[1]) >= len(got):
                    old.unlink()
            meta[key] = got
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{key:22s} {len(got)} шт. — {query}", flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
