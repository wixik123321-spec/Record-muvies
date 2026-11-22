"""Необязательно: иллюстрации сцен через OpenAI Images API (visuals.provider: openai).

Ключ: OPENAI_API_KEY (platform.openai.com → API keys). Каждая сцена получает
вертикальную картинку 1024x1536 по image_prompt; общее описание стиля и
персонажа добавляется к каждому запросу, чтобы кадры были в одном стиле.
Картинки кэшируются в рабочей папке — повторный рендер их не перезапрашивает.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

from PIL import Image

from .utils import ShortsError, log

STYLE = ("Modern 2D animation still, vibrant flat colours, cinematic lighting, expressive cartoon character, "
         "clean shapes, vertical 9:16 composition, no text, no letters, no watermark. ")


def generate_images(script, cfg, work: Path) -> dict[int, Image.Image]:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ShortsError("visuals.provider: openai требует OPENAI_API_KEY (platform.openai.com → API keys)")
    import requests

    work.mkdir(parents=True, exist_ok=True)
    ch = cfg.visuals.character
    hero = (f"Main character (same in every image): young adult, short dark hair, {ch.shirt} t-shirt. ")
    out = {}
    for i, sc in enumerate(script.scenes):
        path = work / f"scene_{i:02d}.png"
        if path.exists():
            out[i] = Image.open(path).convert("RGB")
            continue
        prompt = STYLE + hero + (sc.image_prompt or f"Scene: {sc.setting}, mood {script.mood}")
        log.info("Картинка сцены %d/%d…", i + 1, len(script.scenes))
        r = requests.post("https://api.openai.com/v1/images/generations",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": cfg.visuals.openai_model, "prompt": prompt, "size": "1024x1536", "n": 1},
                          timeout=300)
        if r.status_code != 200:
            raise ShortsError(f"OpenAI Images вернул {r.status_code}: {r.text[:300]}")
        data = r.json()["data"][0]
        if "b64_json" in data:
            raw = base64.b64decode(data["b64_json"])
        else:
            raw = requests.get(data["url"], timeout=120).content
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.save(path)
        out[i] = img
    return out
