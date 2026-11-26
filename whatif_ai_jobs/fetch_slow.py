"""Бережное скачивание фото из Wikimedia Commons при жёстком лимите запросов.

Поиск (commons.wikimedia.org) и скачивание оригиналов (upload.wikimedia.org) идут в двух потоках,
каждый строго соблюдает заголовок Retry-After. Для каждого ключа ищутся до 4 кандидатов
(лицензии PD / CC0 / CC BY, без SA), скачивается первый; остальные доступны командой:

WHATIF_ROOT=папка python fetch_slow.py                 искать и скачивать недостающее
WHATIF_ROOT=папка python fetch_slow.py next key1 key2  скачать следующего кандидата для ключей
"""

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("WHATIF_ROOT") or CODE).resolve()
IMG = ROOT / "assets" / "images"
CANDS = ROOT / "build" / "candidates.json"
META = ROOT / "build" / "images.json"
UA = {"User-Agent": "WhatIfVideoBuilder/1.0 (educational YouTube video; image credits listed in description)"}
API = "https://commons.wikimedia.org/w/api.php"
OK = re.compile(r"^(public domain|pd\b|pd-|cc0|cc[ -]?by[ -]?\d|cc[ -]?by$|cc by \d)", re.I)
lock = threading.Lock()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def fetch(url, tries=12):
    for a in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 30) + 2
                time.sleep(min(wait, 180))
                continue
            if e.code == 404:
                raise
            time.sleep(3 + a * 3)
        except Exception:  # noqa: BLE001
            time.sleep(3 + a * 3)
    raise RuntimeError(f"не удалось: {url[:90]}")


def strip(html):
    return re.sub(r"<[^>]+>", "", html or "").strip()


def search(query, n=4):
    out = []
    for q in query.split("|"):
        params = {"action": "query", "generator": "search", "gsrsearch": f"{q.strip()} filetype:bitmap",
                  "gsrnamespace": 6, "gsrlimit": 40, "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime",
                  "format": "json"}
        d = json.loads(fetch(API + "?" + urllib.parse.urlencode(params)))
        pages = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 999))
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = strip(meta.get("LicenseShortName", {}).get("value", ""))
            w, h = ii.get("width", 0), ii.get("height", 0)
            if not OK.search(lic) or "sa" in lic.lower().replace(" ", "-").split("-"):
                continue
            if ii.get("mime") not in ("image/jpeg", "image/png") or w < 1600 or w / max(h, 1) < 1.2:
                continue
            if ii.get("size", 0) > 12_000_000 or p["title"] in {o["title"] for o in out}:
                continue
            out.append({"title": p["title"], "page": ii.get("descriptionurl"), "url": ii.get("url"),
                        "license": lic, "license_url": strip(meta.get("LicenseUrl", {}).get("value", "")),
                        "author": strip(meta.get("Artist", {}).get("value", ""))[:120] or "неизвестен",
                        "width": w, "height": h, "source": "Wikimedia Commons"})
            if len(out) >= n:
                return out
    return out


def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(p, d):
    with lock:
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def download(key, c, idx):
    data = fetch(c["url"])
    im = Image.open(BytesIO(data)).convert("RGB")
    if im.width > 2400:
        im = im.resize((2400, round(im.height * 2400 / im.width)), Image.LANCZOS)
    im.save(IMG / f"{key}_{idx}.jpg", quality=92)


def searcher(assets, cands, done):
    for key, q in assets.items():
        if key in cands:
            continue
        try:
            cands[key] = search(q)
        except Exception as e:  # noqa: BLE001
            log("поиск не удался", key, e)
            cands[key] = []
        save(CANDS, cands)
        log(f"поиск {key}: {len(cands[key])} кандидатов")
    done.set()


def downloader(assets, cands, meta, done):
    while True:
        todo = [k for k in assets if k in cands and cands[k] and k not in meta]
        if not todo:
            if done.is_set() and all(k in cands for k in assets):
                return
            time.sleep(3)
            continue
        key = todo[0]
        for c in cands[key]:
            try:
                download(key, c, 0)
                meta[key] = [c]
                save(META, meta)
                log(f"скачано {key}: {c['title'][:60]}")
                break
            except Exception as e:  # noqa: BLE001
                log("не скачалось", key, e)
        else:
            meta[key] = []
            save(META, meta)
        time.sleep(2)


def main():
    sys.path.insert(0, str(ROOT))
    from shots import ASSETS
    IMG.mkdir(parents=True, exist_ok=True)
    cands, meta = load(CANDS), load(META)
    if len(sys.argv) > 2 and sys.argv[1] == "next":
        for key in sys.argv[2:]:
            have = meta.get(key, [])
            rest = [c for c in cands.get(key, []) if c["title"] not in {h["title"] for h in have}]
            if rest:
                download(key, rest[0], len(have))
                meta[key] = have + [rest[0]]
                save(META, meta)
                log(f"{key}: добавлен вариант {len(have)} — {rest[0]['title'][:60]}")
        return
    done = threading.Event()
    t = threading.Thread(target=searcher, args=(ASSETS, cands, done))
    t.start()
    downloader(ASSETS, cands, meta, done)
    t.join()
    log("DONE")


if __name__ == "__main__":
    main()
