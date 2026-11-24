"""Превью (обложка), шапка канала и аватар в стиле видео.

* Превью 1280x720 (требование YouTube: 16:9, до 2 МБ, JPG/PNG): крупный текст в две
  строки слева, эмоциональный персонаж справа, предметы, стрелка.
* Шапка 2560x1440: всё важное — в безопасной зоне 1546x423 по центру
  (её видно и на телефоне, и на компьютере, и на ТВ).
* Аватар 800x800: лицо персонажа в круге (YouTube обрезает аватар по кругу).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .art.backgrounds import palette, render_layers
from .art.character import Character
from .art.props import prop_image
from .utils import font


def _bg(setting: str, w: int, h: int, seed: int = 5) -> Image.Image:
    L = render_layers(setting, w, h, seed=seed)
    img = L["far"].copy()
    img.alpha_composite(L["mid"])
    img.alpha_composite(L["near"])
    return img


def _fit_font(text: str, max_w: int, size: int, min_size: int = 40):
    f = font("Inter:style=Black", size)
    while f.getlength(text) > max_w and size > min_size:
        size -= 4
        f = font("Inter:style=Black", size)
    return f


def _glow_text(img: Image.Image, xy, text: str, f, fill, stroke: int, anchor="lm", glow=None):
    if glow:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).text(xy, text, font=f, anchor=anchor, fill=glow + (200,),
                                   stroke_width=stroke * 2, stroke_fill=glow + (200,))
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(stroke * 2)))
    d = ImageDraw.Draw(img)
    d.text((xy[0] + stroke // 2 + 3, xy[1] + stroke // 2 + 5), text, font=f, anchor=anchor, fill=(0, 0, 0, 170))
    d.text(xy, text, font=f, anchor=anchor, fill=fill, stroke_width=stroke, stroke_fill=(12, 8, 24))


def _character(cfg, emotion: str, pose: str, flip=False) -> Image.Image:
    ch = cfg.visuals.character
    return Character(ch.skin, ch.hair, ch.shirt, ch.pants).draw(0.6, emotion, pose, talk=0.0, look=-1.0, flip=flip)


def thumbnail(spec: dict, cfg, out: Path, size=(1280, 720)) -> Path:
    W, H = size
    setting = spec.get("setting", "night_city")
    pal = palette(setting)
    acc = tuple(pal[5])
    img = _bg(setting, W, H, seed=spec.get("seed", 9))
    # затемнение слева под текст
    grad = np.linspace(0.78, 0.0, W)[None, :, None] * np.ones((H, 1, 1))
    shade = Image.fromarray((np.concatenate([np.zeros((H, W, 3)), grad * 255], axis=2)).astype(np.uint8), "RGBA")
    img.alpha_composite(shade)
    # свечение за персонажем
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W * 0.55, H * 0.05, W * 1.05, H * 1.1), fill=acc + (150,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(90)))
    # персонаж
    char = _character(cfg, spec.get("emotion", "surprised"), spec.get("pose", "hands_up"))
    s = H * 1.25 / char.height
    char = char.resize((int(char.width * s), int(char.height * s)), Image.LANCZOS)
    img.alpha_composite(char, (int(W * 0.76 - char.width / 2), int(H * 0.02)))
    # предметы
    for k, name in enumerate(spec.get("props", [])[:2]):
        p = prop_image(name, int(H * (0.42 if k == 0 else 0.28)), "#%02X%02X%02X" % acc)
        pos = [(int(W * 0.50), int(H * 0.05)), (int(W * 0.88), int(H * 0.62))][k]
        img.alpha_composite(p, pos)
    # текст
    top, bottom = spec.get("top", "").upper(), spec.get("bottom", "").upper()
    max_w = int(W * 0.50)
    f1 = _fit_font(top, max_w, 128)
    f2 = _fit_font(bottom, max_w, 128)
    _glow_text(img, (int(W * 0.045), int(H * 0.40)), top, f1, (255, 255, 255), 10)
    _glow_text(img, (int(W * 0.045), int(H * 0.62)), bottom, f2, (255, 225, 60), 10, glow=(255, 140, 0))
    # бейдж
    if spec.get("badge"):
        fb = font("Inter:style=Black", 44)
        tw = fb.getlength(spec["badge"].upper())
        d = ImageDraw.Draw(img)
        x0, y0 = int(W * 0.045), int(H * 0.08)
        d.rounded_rectangle((x0, y0, x0 + tw + 48, y0 + 72), radius=36, fill=(230, 33, 23))
        d.text((x0 + 24, y0 + 36), spec["badge"].upper(), font=fb, anchor="lm", fill=(255, 255, 255))
    # стрелка от текста к главному предмету (над текстом, чтобы не перекрывать буквы)
    if spec.get("arrow", True):
        d = ImageDraw.Draw(img)
        (x0, y0), (x1, y1) = (W * 0.33, H * 0.27), (W * 0.47, H * 0.16)
        import math
        ang = math.atan2(y1 - y0, x1 - x0)
        for col, wd in (((255, 255, 255), 30), ((230, 33, 23), 18)):
            d.line((x0, y0, x1 - math.cos(ang) * 20, y1 - math.sin(ang) * 20), fill=col, width=wd)
        head = [(x1 + math.cos(ang) * 22, y1 + math.sin(ang) * 22),
                (x1 + math.cos(ang + 2.4) * 46, y1 + math.sin(ang + 2.4) * 46),
                (x1 + math.cos(ang - 2.4) * 46, y1 + math.sin(ang - 2.4) * 46)]
        d.polygon(head, fill=(230, 33, 23), outline=(255, 255, 255), width=5)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    return out


def banner(channel: str, tagline: str, cfg, out: Path, setting: str = "abstract") -> Path:
    W, H = 2560, 1440
    pal = palette(setting)
    acc = tuple(pal[5])
    img = _bg(setting, W, H, seed=21)
    veil = Image.new("RGBA", (W, H), (10, 8, 24, 110))
    img.alpha_composite(veil)
    sx0, sy0, sx1, sy1 = (W - 1546) // 2, (H - 423) // 2, (W + 1546) // 2, (H + 423) // 2  # безопасная зона
    # предметы по краям полосы, которую видно на компьютере (2560x423)
    for k, (name, x) in enumerate([("brain", 210), ("lightbulb", 2150), ("star", 60), ("globe", 2380)]):
        sz = 230 if k < 2 else 150
        img.alpha_composite(prop_image(name, sz, "#%02X%02X%02X" % acc), (x, (H - sz) // 2 + (20 if k % 2 else -20)))
    f = _fit_font(channel.upper(), 1400, 170)
    _glow_text(img, (W // 2, sy0 + 160), channel.upper(), f, (255, 255, 255), 12, anchor="mm", glow=acc)
    ft = font("Inter:style=Bold", 56)
    d = ImageDraw.Draw(img)
    d.text((W // 2, sy0 + 320), tagline, font=ft, anchor="mm", fill=acc + (255,))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, quality=92)
    # служебная версия с разметкой безопасной зоны
    guide = img.copy()
    ImageDraw.Draw(guide).rectangle((sx0, sy0, sx1, sy1), outline=(255, 0, 0, 255), width=6)
    guide.convert("RGB").save(out.with_name(out.stem + "_safe_area.png"))
    return out


def avatar(cfg, out: Path, setting: str = "abstract") -> Path:
    S = 800
    pal = palette(setting)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bg = _bg(setting, S, S, seed=4)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, S, S), fill=255)
    img.paste(bg, (0, 0), mask)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * 0.15, S * 0.1, S * 0.85, S * 0.8), fill=tuple(pal[5]) + (140,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60)))
    char = _character(cfg, "happy", "idle")
    s = S * 1.45 / char.height
    char = char.resize((int(char.width * s), int(char.height * s)), Image.LANCZOS)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.alpha_composite(char, (int(S / 2 - char.width / 2), int(S * 0.02)))
    img.paste(layer, (0, 0), Image.composite(layer.getchannel("A"), Image.new("L", (S, S), 0), mask))
    q = prop_image("question", 230, "#%02X%02X%02X" % tuple(pal[5]))
    img.alpha_composite(q, (int(S * 0.62), int(S * 0.06)))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
