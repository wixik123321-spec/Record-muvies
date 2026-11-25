"""Свежие фото для Shorts через Openverse (Flickr, лицензии CC BY / CC0 / PDM)."""
import json
import sys
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from fetch_openverse import get, search  # noqa: E402

QUERIES = {
    "money_hand": "cash in hand|holding money|money hand",
    "hammock": "hammock relax|relaxing hammock|hammock",
    "kenya_market": "Kenya market|Nairobi market|Kenya shop",
    "dollars": "hundred dollar bills|dollar bills|us dollars",
    "office_worker": "office worker|working at desk|office desk",
    "happy_woman": "smiling woman outdoors|happy woman|woman laughing",
}

meta_p = HERE / "images.json"
meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
for key, q in QUERIES.items():
    if key in meta:
        continue
    got = []
    for c in search(q, 3):
        im = Image.open(BytesIO(get(c["url"]))).convert("RGB")
        im.save(HERE / "assets" / f"{key}_{len(got)}.jpg", quality=93)
        got.append(c)
        time.sleep(0.5)
    meta[key] = got
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(key, len(got), flush=True)
