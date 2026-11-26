"""Поиск реальных фото в PD12M (12,4 млн изображений, только Public Domain / CC0) по подписям.

Индекс: build/pd12m/index_landscape.parquet (горизонтальные фото ≥1600 px) — собирается из метаданных
Spawning/PD12M с Hugging Face. Изображения лежат в бакете pd12m.s3.us-west-2.amazonaws.com.

WHATIF_ROOT=папка python pd_search.py            найти кандидатов для PD_QUERIES из shots.py и скачать их
WHATIF_ROOT=папка python pd_search.py --sheet    контактные листы build/pd_sheet_N.jpg
"""

import concurrent.futures as cf
import json
import os
import re
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("WHATIF_ROOT") or CODE).resolve()
INDEX = Path(os.environ.get("PD12M_INDEX") or ROOT / "build" / "pd12m" / "index_landscape.parquet")
CAND_DIR = ROOT / "build" / "pd_cands"
OUT = ROOT / "build" / "pd_candidates.json"
N = 6
BAD = re.compile(r"painting|drawing|illustration|engraving|lithograph|sketch|diagram|poster|postcard|stamp|"
                 r"cartoon|watercolor|etching|woodcut|print of|map of|insect|butterfly|beetle|bird|caterpillar|"
                 r"spider|moth|fungus|mushroom|lichen|specimen|herbarium", re.I)
GOOD_SRC = {"Wikimedia Commons": 2, "Deutsche Fotothek": 1, "Swedish National Heritage Board": 1, "PHOTOCONSORTIUM": 1,
            "The Danish Agency for Culture": 1, "Regional Archive Nijmegen": 1}


def search(df, groups, exclude=None):
    sub = df
    for g in groups:
        sub = sub[sub["cap"].str.contains(g, regex=True)]
        if sub.empty:
            return sub
    sub = sub[~sub["cap"].str.contains(BAD)]
    if exclude:
        sub = sub[~sub["cap"].str.contains(exclude, regex=True)]
    sub = sub.assign(score=sub["source"].map(GOOD_SRC).fillna(0) * 10
                     - (sub["cap"].str.len() / 400) + (sub["width"].clip(upper=4000) / 4000))
    return sub.sort_values("score", ascending=False)


def fetch(c, dest):
    with urllib.request.urlopen(c["url"], timeout=120) as r:
        im = Image.open(BytesIO(r.read())).convert("RGB")
    if im.width > 2400:
        im = im.resize((2400, round(im.height * 2400 / im.width)), Image.LANCZOS)
    im.save(dest, quality=92)
    return dest


def main():
    import pandas as pd
    sys.path.insert(0, str(ROOT))
    from shots import PD_QUERIES
    df = pd.read_parquet(INDEX)
    df["cap"] = df["caption"].str.lower()
    res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for key, spec in PD_QUERIES.items():
        if key in res and res[key]:
            continue
        groups, exclude = (spec, None) if isinstance(spec, list) else (spec["all"], spec.get("not"))
        hits = search(df, groups, exclude)
        rows = hits.head(N)
        res[key] = [{"id": r.id, "url": r.url, "caption": r.caption, "width": int(r.width), "height": int(r.height),
                     "license": "CC0" if "zero" in r.license else "Public Domain", "license_url": r.license,
                     "source": f"PD12M / {r.source}", "author": r.source, "title": r.caption[:90],
                     "page": f"https://source.plus/item/{r.id}"} for r in rows.itertuples()]
        print(f"{key:18s} {len(hits):6d} совпадений", flush=True)
        OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [(c, CAND_DIR / f"{k}_{i}.jpg") for k, cs in res.items() for i, c in enumerate(cs)
            if not (CAND_DIR / f"{k}_{i}.jpg").exists()]
    with cf.ThreadPoolExecutor(8) as ex:
        for f in cf.as_completed([ex.submit(fetch, c, d) for c, d in jobs]):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print("не скачалось:", e, flush=True)
    print("DONE", flush=True)


def sheet():
    res = json.loads(OUT.read_text(encoding="utf-8"))
    keys = list(res)
    tw, th = 300, 170
    f = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 15)
    for page in range(0, len(keys), 12):
        ks = keys[page:page + 12]
        im = Image.new("RGB", (170 + tw * N, th * len(ks)), (20, 20, 20))
        d = ImageDraw.Draw(im)
        for r, k in enumerate(ks):
            d.text((6, r * th + 6), k, font=f, fill=(255, 255, 0))
            for i in range(len(res[k])):
                p = CAND_DIR / f"{k}_{i}.jpg"
                if p.exists():
                    t = Image.open(p)
                    t.thumbnail((tw - 6, th - 6))
                    im.paste(t, (170 + i * tw, r * th + 3))
                    d.text((174 + i * tw, r * th + 5), str(i), font=f, fill=(255, 70, 70))
        im.save(ROOT / "build" / f"pd_sheet_{page // 12 + 1}.jpg", quality=82)


if __name__ == "__main__":
    sheet() if "--sheet" in sys.argv else main()
