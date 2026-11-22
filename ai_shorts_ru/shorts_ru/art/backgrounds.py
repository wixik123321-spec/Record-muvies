"""Фоны сцен в стиле плоской 2D-анимации: три слоя (дальний, средний, ближний) для параллакса.

Рисуется в двойном разрешении и уменьшается (сглаживание краёв). Каждому месту
действия соответствует своя палитра и набор силуэтов; случайность зависит от
seed, поэтому одна и та же сцена при повторном рендере выглядит одинаково.
"""

from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 2  # supersampling

PALETTES = {
    #              sky top      sky bottom    far          mid          near         accent       light
    "night_city": ("#0B1030", "#3A1C5C", "#2A2350", "#1A1536", "#0E0B1E", "#FFB547", "#7B6CFF"),
    "city_day":   ("#5FB4FF", "#CDEBFF", "#9CB8D8", "#6F8DB5", "#3C5578", "#FFD166", "#FFFFFF"),
    "room":       ("#2B2250", "#4A3A78", "#3A2E63", "#2A2148", "#1B1530", "#FFC27A", "#FFB45E"),
    "space":      ("#05040F", "#1A1040", "#2B1B5E", "#3D2A80", "#120C2A", "#FF6FD8", "#7AD7FF"),
    "ocean":      ("#FF9A5A", "#FFD39A", "#2E6FA8", "#1F5385", "#123A61", "#FFE08A", "#FFD39A"),
    "underwater": ("#0A4D7A", "#0B2340", "#0E5E8C", "#0A3E63", "#062038", "#5CF2E0", "#8FE9FF"),
    "forest":     ("#1F3B3A", "#5E8C6A", "#2F5A48", "#1E4034", "#0F2620", "#FFD86B", "#CFF5B5"),
    "mountains":  ("#FF8A65", "#FFD1A8", "#7A6BA8", "#4E4A8A", "#2B2A5A", "#FFE6A1", "#FFE6A1"),
    "desert":     ("#FFB566", "#FFE3B0", "#E0A060", "#C27F45", "#8F5A2E", "#FFF1C2", "#FFF1C2"),
    "lab":        ("#0F2A3A", "#1B4A5E", "#1E5868", "#14404D", "#0B252E", "#4DFFD2", "#9AF7FF"),
    "brain":      ("#14062E", "#3B0F5E", "#4B1C7A", "#2E0F52", "#170830", "#FF5CA8", "#B48CFF"),
    "sky_sunset": ("#FF6B6B", "#FFD07A", "#E8766E", "#C2566A", "#7A2E55", "#FFF2B3", "#FFE2A0"),
    "abstract":   ("#1D2671", "#C33764", "#3B2A8A", "#5B2C8A", "#24124A", "#FFD23F", "#FF9ECF"),
}


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def palette(setting):
    return [hex2rgb(c) for c in PALETTES.get(setting, PALETTES["abstract"])]


def _gradient(w, h, top, bottom):
    t = np.linspace(0, 1, h)[:, None, None]
    g = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    g = np.repeat(g, w, axis=1)
    return Image.fromarray(np.concatenate([g, np.full((h, w, 1), 255)], axis=2).astype(np.uint8), "RGBA")


def _glow(img, cx, cy, r, color, alpha=160):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.45))
    return Image.alpha_composite(img, layer)


def _shade(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def _ridge(d, w, h, base, amp, color, rnd, step=40, smooth=3):
    pts = [(0, h)]
    ys = [base + rnd.uniform(-amp, amp) for _ in range(w // step + 3)]
    for _ in range(smooth):
        ys = [ys[0]] + [(ys[i - 1] + ys[i] * 2 + ys[i + 1]) / 4 for i in range(1, len(ys) - 1)] + [ys[-1]]
    for i, y in enumerate(ys):
        pts.append((i * step, y))
    pts.append((w, h))
    d.polygon(pts, fill=color)


def _buildings(d, w, h, base, color, window, rnd, lit=0.3, minw=90, maxw=220, minh=300, maxh=900):
    x = -20
    while x < w:
        bw, bh = rnd.randint(minw, maxw), rnd.randint(minh, maxh)
        d.rectangle((x, base - bh, x + bw, h), fill=color)
        if rnd.random() < 0.3:
            d.rectangle((x + bw * 0.4, base - bh - 60, x + bw * 0.46, base - bh), fill=color)
        for wy in range(int(base - bh + 30), int(base) - 20, 46):
            for wx in range(int(x + 16), int(x + bw - 26), 36):
                if rnd.random() < lit:
                    d.rectangle((wx, wy, wx + 18, wy + 26), fill=window)
        x += bw + rnd.randint(0, 24)


def _tree(d, x, base, s, color):
    for k in range(3):
        y = base - s * (0.5 + k * 0.42)
        ww = s * (0.55 - k * 0.12)
        d.polygon([(x - ww, y + s * 0.45), (x + ww, y + s * 0.45), (x, y - s * 0.35)], fill=color)
    d.rectangle((x - s * 0.06, base - s * 0.15, x + s * 0.06, base + 20), fill=color)


def _stars(d, w, h, n, rnd, color=(255, 255, 255), ymax=1.0):
    for _ in range(n):
        x, y, r = rnd.uniform(0, w), rnd.uniform(0, h * ymax), rnd.choice([1.5, 2, 2.5, 3.5])
        a = rnd.randint(120, 255)
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (a,))


def _cloud(d, x, y, s, color):
    for dx, dy, r in ((0, 0, 1.0), (0.9, 0.15, 0.8), (-0.9, 0.2, 0.75), (0.4, -0.45, 0.75), (-0.35, -0.3, 0.65)):
        rr = s * r
        d.ellipse((x + dx * s - rr, y + dy * s - rr, x + dx * s + rr, y + dy * s + rr), fill=color)


def render_layers(setting: str, w: int, h: int, seed: int = 0) -> dict[str, Image.Image]:
    """Возвращает {"far","mid","near"} — RGBA слои размером w x h."""
    rnd = random.Random(seed)
    W, H = w * SS, h * SS
    sky_t, sky_b, far_c, mid_c, near_c, accent, light = palette(setting)
    far = _gradient(W, H, sky_t, sky_b)
    mid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    near = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    df, dm, dn = ImageDraw.Draw(far, "RGBA"), ImageDraw.Draw(mid, "RGBA"), ImageDraw.Draw(near, "RGBA")
    g = H * 0.70  # линия горизонта

    if setting in ("night_city", "city_day"):
        night = setting == "night_city"
        if night:
            _stars(df, W, H, 260, rnd, ymax=0.5)
            far = _glow(far, W * 0.75, H * 0.18, 260, light, 120)
            df = ImageDraw.Draw(far, "RGBA")
            df.ellipse((W * 0.75 - 110, H * 0.18 - 110, W * 0.75 + 110, H * 0.18 + 110), fill=(255, 246, 220, 255))
        else:
            for _ in range(5):
                _cloud(df, rnd.uniform(0, W), rnd.uniform(H * 0.08, H * 0.4), rnd.uniform(70, 140), (255, 255, 255, 220))
        _buildings(df, W, H, g - 120, far_c + (255,), _shade(accent, 0.7) + (160,), rnd, 0.15, 120, 260, 500, 1300)
        _buildings(dm, W, H, g + 60, mid_c + (255,), accent + (230,), rnd, 0.35 if night else 0.1, 160, 320, 400, 1100)
        dn.rectangle((0, g + 60, W, H), fill=near_c + (255,))
        for x in range(200, W, 700):
            dn.rectangle((x, g - 360, x + 22, g + 60), fill=_shade(near_c, 1.4) + (255,))
            dn.ellipse((x - 40, g - 400, x + 62, g - 340), fill=accent + (255,))
        if night:
            for x in range(200, W, 700):
                near = _glow(near, x + 11, g - 370, 170, accent, 90)
            dn = ImageDraw.Draw(near, "RGBA")
    elif setting == "room":
        df.rectangle((W * 0.55, H * 0.14, W * 0.92, H * 0.46), fill=_shade(sky_t, 0.6) + (255,))
        df.rectangle((W * 0.57, H * 0.155, W * 0.90, H * 0.445), fill=(18, 22, 60, 255))
        _stars(df, int(W * 0.33), int(H * 0.29), 40, rnd)
        df.ellipse((W * 0.80 - 50, H * 0.22 - 50, W * 0.80 + 50, H * 0.22 + 50), fill=(255, 245, 215, 255))
        df.line((W * 0.735, H * 0.155, W * 0.735, H * 0.445), fill=_shade(sky_t, 0.6) + (255,), width=16)
        far = _glow(far, W * 0.22, H * 0.42, 420, accent, 120)
        df = ImageDraw.Draw(far, "RGBA")
        dm.rectangle((W * 0.08, H * 0.30, W * 0.42, H * 0.315), fill=mid_c + (255,))
        for i, bh in enumerate((150, 120, 170, 135, 160)):
            dm.rectangle((W * 0.1 + i * 70, H * 0.30 - bh, W * 0.1 + i * 70 + 55, H * 0.30),
                         fill=_shade(accent, 0.45 + i * 0.08) + (255,))
        dn.rectangle((0, g + 40, W, H), fill=near_c + (255,))
        dn.rectangle((W * 0.05, g - 60, W * 0.5, g + 40), fill=_shade(near_c, 1.6) + (255,))
        dn.polygon([(W * 0.12, g - 60), (W * 0.2, g - 60), (W * 0.24, g - 260), (W * 0.08, g - 260)],
                   fill=accent + (255,))
        near = _glow(near, W * 0.16, g - 200, 300, accent, 110)
        dn = ImageDraw.Draw(near, "RGBA")
    elif setting == "space":
        for _ in range(7):
            far = _glow(far, rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(250, 600),
                        rnd.choice([accent, light, mid_c]), rnd.randint(40, 90))
        df = ImageDraw.Draw(far, "RGBA")
        _stars(df, W, H, 700, rnd)
        px, py, pr = W * 0.75, H * 0.28, 260
        dm.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(255, 140, 90, 255))
        dm.ellipse((px - pr * 0.9, py - pr * 0.95, px + pr * 0.6, py + pr * 0.2), fill=(255, 185, 120, 255))
        dm.ellipse((px - pr * 1.7, py - pr * 0.25, px + pr * 1.7, py + pr * 0.25), outline=(255, 220, 180, 230), width=18)
        for _ in range(4):
            x, y, r = rnd.uniform(0, W), rnd.uniform(H * 0.6, H), rnd.uniform(60, 160)
            dn.ellipse((x - r, y - r * 0.8, x + r, y + r * 0.8), fill=_shade(near_c, 2.5) + (255,))
    elif setting == "ocean":
        far = _glow(far, W * 0.5, H * 0.42, 300, (255, 240, 180), 200)
        df = ImageDraw.Draw(far, "RGBA")
        df.rectangle((0, H * 0.45, W, H), fill=far_c + (255,))
        for i in range(14):
            y = H * 0.47 + i * i * 9
            dm.line((0, y, W, y + rnd.uniform(-8, 8)), fill=_shade(light, 0.9) + (60 + i * 6,), width=6 + i)
        dn.rectangle((0, g + 200, W, H), fill=near_c + (255,))
    elif setting == "underwater":
        for i in range(6):
            x = rnd.uniform(0, W)
            rays = Image.new("RGBA", far.size, (0, 0, 0, 0))
            ImageDraw.Draw(rays).polygon([(x - 40, 0), (x + 40, 0), (x + 260, H * 0.9), (x + 60, H * 0.9)],
                                         fill=light + (22,))
            far = Image.alpha_composite(far, rays.filter(ImageFilter.GaussianBlur(30)))
        df = ImageDraw.Draw(far, "RGBA")
        _ridge(dm, W, H, g + 80, 120, mid_c + (255,), rnd)
        for x in range(0, W, 140):
            hh = rnd.uniform(300, 700)
            pts = [(x + math.sin(k / 3) * 30, g + 300 - k * hh / 12) for k in range(13)]
            dn.line(pts, fill=_shade(accent, 0.45) + (255,), width=26, joint="curve")
        _ridge(dn, W, H, g + 320, 80, near_c + (255,), rnd)
    elif setting == "forest":
        far = _glow(far, W * 0.5, H * 0.32, 380, light, 140)
        df = ImageDraw.Draw(far, "RGBA")
        for x in range(-50, W + 100, 120):
            _tree(df, x + rnd.uniform(-30, 30), g - 40, rnd.uniform(260, 380), far_c + (255,))
        for x in range(-80, W + 100, 220):
            _tree(dm, x + rnd.uniform(-40, 40), g + 120, rnd.uniform(420, 560), mid_c + (255,))
        dn.rectangle((0, g + 200, W, H), fill=near_c + (255,))
        for x in range(-100, W + 100, 520):
            _tree(dn, x + rnd.uniform(-60, 60), g + 380, rnd.uniform(650, 820), near_c + (255,))
    elif setting in ("mountains", "sky_sunset", "desert"):
        far = _glow(far, W * 0.62, H * 0.33, 240, (255, 250, 220), 230)
        df = ImageDraw.Draw(far, "RGBA")
        df.ellipse((W * 0.62 - 120, H * 0.33 - 120, W * 0.62 + 120, H * 0.33 + 120), fill=(255, 248, 225, 255))
        for _ in range(4):
            _cloud(df, rnd.uniform(0, W), rnd.uniform(H * 0.1, H * 0.35), rnd.uniform(60, 120), _shade(light, 1.0) + (170,))
        if setting == "desert":
            _ridge(df, W, H, g - 40, 40, far_c + (255,), rnd, step=160)
            for px in (W * 0.25, W * 0.42):
                df.polygon([(px - 170, g - 20), (px + 170, g - 20), (px, g - 250)], fill=_shade(far_c, 0.8) + (255,))
            _ridge(dm, W, H, g + 120, 60, mid_c + (255,), rnd, step=220)
            _ridge(dn, W, H, g + 380, 60, near_c + (255,), rnd, step=260)
        elif setting == "sky_sunset":
            _ridge(df, W, H, g + 40, 90, far_c + (255,), rnd, step=300, smooth=4)
            _ridge(dm, W, H, g + 200, 70, mid_c + (255,), rnd, step=340, smooth=4)
            _ridge(dn, W, H, g + 420, 50, near_c + (255,), rnd, step=380, smooth=4)
            for _ in range(5):
                bx, by, bs = rnd.uniform(W * 0.2, W * 0.8), rnd.uniform(H * 0.15, H * 0.3), rnd.uniform(18, 30)
                dm.line([(bx - bs, by - bs * 0.4), (bx, by), (bx + bs, by - bs * 0.4)], fill=(60, 30, 50, 230), width=6)
        else:
            _ridge(df, W, H, g - 300, 260, far_c + (255,), rnd, step=90, smooth=1)
            _ridge(dm, W, H, g - 60, 200, mid_c + (255,), rnd, step=110, smooth=1)
            _ridge(dn, W, H, g + 280, 120, near_c + (255,), rnd, step=140)
    elif setting == "lab":
        for y in range(0, int(g), 120):
            df.line((0, y, W, y), fill=_shade(far_c, 1.2) + (90,), width=3)
        for x in range(0, W, 120):
            df.line((x, 0, x, g), fill=_shade(far_c, 1.2) + (90,), width=3)
        for i, x in enumerate((W * 0.15, W * 0.62)):
            dm.rounded_rectangle((x, H * 0.2, x + W * 0.25, H * 0.36), 20, fill=(10, 30, 40, 255),
                                 outline=accent + (255,), width=8)
            for k in range(5):
                yy = H * 0.23 + k * 40
                dm.line((x + 40, yy, x + 40 + rnd.uniform(80, W * 0.18), yy), fill=accent + (200,), width=10)
        dn.rectangle((0, g, W, H), fill=near_c + (255,))
        for x, c in ((W * 0.1, accent), (W * 0.3, light), (W * 0.82, (255, 120, 180))):
            dn.ellipse((x - 70, g - 130, x + 70, g + 10), fill=c + (220,))
            dn.rectangle((x - 25, g - 260, x + 25, g - 110), fill=c + (200,))
    elif setting == "brain":
        nodes = [(rnd.uniform(0, W), rnd.uniform(0, H)) for _ in range(70)]
        for i, (x, y) in enumerate(nodes):
            for (x2, y2) in nodes[i + 1:]:
                if math.hypot(x - x2, y - y2) < 420 and rnd.random() < 0.5:
                    df.line((x, y, x2, y2), fill=light + (70,), width=4)
        for x, y in nodes:
            r = rnd.uniform(6, 16)
            dm.ellipse((x - r, y - r, x + r, y + r), fill=accent + (255,))
        mid = Image.alpha_composite(mid.filter(ImageFilter.GaussianBlur(8)), mid)
        dm = ImageDraw.Draw(mid, "RGBA")
    else:  # abstract
        for _ in range(8):
            far = _glow(far, rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(200, 520),
                        rnd.choice([accent, light, mid_c]), rnd.randint(50, 110))
        df = ImageDraw.Draw(far, "RGBA")
        for _ in range(12):
            x, y, s = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(40, 140)
            shape = rnd.choice(["c", "r", "t"])
            col = rnd.choice([accent, light]) + (90,)
            if shape == "c":
                dm.ellipse((x - s, y - s, x + s, y + s), outline=col, width=10)
            elif shape == "r":
                dm.rounded_rectangle((x - s, y - s, x + s, y + s), 20, outline=col, width=10)
            else:
                dm.polygon([(x, y - s), (x + s, y + s), (x - s, y + s)], outline=col, width=10)

    out = {}
    for name, img in (("far", far), ("mid", mid), ("near", near)):
        out[name] = img.resize((w, h), Image.LANCZOS)
    return out
