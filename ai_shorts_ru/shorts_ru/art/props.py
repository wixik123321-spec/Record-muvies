"""Плоские иконки-предметы для сцен (вопрос, лампочка, мозг, сердце, часы…)."""

from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from .character import _rgb

S = 2
OUT = (30, 24, 48)


def _star(cx, cy, r1, r2, n=5, rot=-90):
    pts = []
    for i in range(n * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.radians(rot + i * 180 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


@lru_cache(maxsize=None)
def prop_image(name: str, size: int = 300, accent: str = "#FFD23F") -> Image.Image:
    """Иконка с обводкой и мягкой тенью, RGBA size x size."""
    n = size * S
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, m = n / 2, n * 0.08
    w = int(n * 0.035)
    acc = _rgb(accent)

    def E(x0, y0, x1, y1, fill, ow=w):
        d.ellipse((x0, y0, x1, y1), fill=fill, outline=OUT, width=ow)

    if name == "question" or name == "exclamation":
        f = _font(int(n * 0.85))
        txt = "?" if name == "question" else "!"
        d.text((c, c), txt, font=f, anchor="mm", fill=acc, stroke_width=w, stroke_fill=OUT)
    elif name == "lightbulb":
        E(c - n * 0.28, m, c + n * 0.28, n * 0.62, (255, 236, 120))
        d.rectangle((c - n * 0.13, n * 0.6, c + n * 0.13, n * 0.8), fill=(170, 175, 190), outline=OUT, width=w)
        for i in range(3):
            y = n * 0.65 + i * n * 0.05
            d.line((c - n * 0.13, y, c + n * 0.13, y), fill=OUT, width=w // 2)
        d.arc((c - n * 0.08, n * 0.3, c + n * 0.08, n * 0.5), 200, 340, fill=(240, 150, 40), width=w)
    elif name == "brain":
        for dx, dy, r in ((-0.15, -0.08, 0.2), (0.12, -0.1, 0.21), (-0.2, 0.1, 0.18), (0.18, 0.1, 0.19), (0, 0.12, 0.2)):
            E(c + (dx - r) * n, c + (dy - r) * n, c + (dx + r) * n, c + (dy + r) * n, (255, 150, 190))
        d.line((c, n * 0.2, c, n * 0.78), fill=OUT, width=w)
        for dx, dy in ((-0.18, -0.05), (0.15, 0.08), (-0.1, 0.18), (0.2, -0.12)):
            d.arc((c + (dx - 0.08) * n, c + (dy - 0.05) * n, c + (dx + 0.08) * n, c + (dy + 0.05) * n), 0, 180, fill=OUT, width=w // 2)
    elif name == "heart":
        r = n * 0.2
        E(c - 2 * r, n * 0.22, c, n * 0.22 + 2 * r, (255, 80, 110), 0)
        E(c, n * 0.22, c + 2 * r, n * 0.22 + 2 * r, (255, 80, 110), 0)
        d.polygon([(c - 2 * r + n * 0.01, n * 0.22 + r * 1.3), (c + 2 * r - n * 0.01, n * 0.22 + r * 1.3), (c, n * 0.86)],
                  fill=(255, 80, 110))
        d.ellipse((c - r * 1.6, n * 0.3, c - r * 1.0, n * 0.4), fill=(255, 200, 210))
    elif name == "clock":
        E(m, m, n - m, n - m, (250, 250, 255))
        for i in range(12):
            a = math.radians(i * 30)
            d.line((c + math.cos(a) * n * 0.33, c + math.sin(a) * n * 0.33, c + math.cos(a) * n * 0.38,
                    c + math.sin(a) * n * 0.38), fill=OUT, width=w // 2)
        d.line((c, c, c, c - n * 0.28), fill=OUT, width=w)
        d.line((c, c, c + n * 0.2, c + n * 0.06), fill=(230, 60, 80), width=w)
        d.ellipse((c - w, c - w, c + w, c + w), fill=OUT)
    elif name == "coin":
        E(m, m, n - m, n - m, (255, 200, 60))
        E(n * 0.2, n * 0.2, n * 0.8, n * 0.8, (255, 220, 110), w // 2)
        d.text((c, c), "₽", font=_font(int(n * 0.42)), anchor="mm", fill=(200, 130, 20))
    elif name == "phone":
        d.rounded_rectangle((n * 0.27, m, n * 0.73, n - m), n * 0.07, fill=(40, 44, 60), outline=OUT, width=w)
        d.rounded_rectangle((n * 0.31, n * 0.15, n * 0.69, n * 0.82), n * 0.04, fill=(120, 200, 255))
        d.rounded_rectangle((n * 0.35, n * 0.25, n * 0.6, n * 0.33), 10, fill=(255, 255, 255))
        d.rounded_rectangle((n * 0.4, n * 0.4, n * 0.65, n * 0.48), 10, fill=(60, 140, 255))
    elif name == "globe":
        E(m, m, n - m, n - m, (80, 170, 255))
        for pts in ([(0.3, 0.3), (0.45, 0.25), (0.5, 0.4), (0.38, 0.5), (0.28, 0.42)],
                    [(0.55, 0.55), (0.72, 0.5), (0.75, 0.68), (0.6, 0.75)]):
            d.polygon([(x * n, y * n) for x, y in pts], fill=(90, 210, 120))
        d.arc((n * 0.3, m, n * 0.7, n - m), 0, 360, fill=(255, 255, 255, 120), width=w // 3)
    elif name == "eye":
        d.ellipse((m, n * 0.25, n - m, n * 0.75), fill=(255, 255, 255), outline=OUT, width=w)
        E(c - n * 0.17, c - n * 0.17, c + n * 0.17, c + n * 0.17, (90, 160, 255))
        d.ellipse((c - n * 0.08, c - n * 0.08, c + n * 0.08, c + n * 0.08), fill=OUT)
        d.ellipse((c - n * 0.04, c - n * 0.1, c + n * 0.02, c - n * 0.04), fill=(255, 255, 255))
    elif name == "key":
        E(n * 0.1, n * 0.3, n * 0.45, n * 0.65, (255, 205, 70))
        d.ellipse((n * 0.2, n * 0.4, n * 0.35, n * 0.55), fill=(0, 0, 0, 0), outline=OUT, width=w)
        d.rectangle((n * 0.43, n * 0.44, n * 0.9, n * 0.52), fill=(255, 205, 70), outline=OUT, width=w)
        d.rectangle((n * 0.72, n * 0.52, n * 0.78, n * 0.64), fill=(255, 205, 70), outline=OUT, width=w)
        d.rectangle((n * 0.82, n * 0.52, n * 0.88, n * 0.6), fill=(255, 205, 70), outline=OUT, width=w)
    elif name == "star":
        d.polygon(_star(c, c * 1.05, n * 0.44, n * 0.18), fill=acc, outline=OUT, width=w)
    elif name == "book":
        d.polygon([(m, n * 0.25), (c, n * 0.32), (c, n * 0.85), (m, n * 0.78)], fill=(255, 255, 255), outline=OUT, width=w)
        d.polygon([(n - m, n * 0.25), (c, n * 0.32), (c, n * 0.85), (n - m, n * 0.78)], fill=(245, 245, 255), outline=OUT, width=w)
        for i in range(4):
            y = n * (0.4 + i * 0.09)
            d.line((n * 0.16, y, n * 0.42, y + n * 0.02), fill=(160, 170, 200), width=w // 2)
    elif name == "magnifier":
        d.line((c + n * 0.12, c + n * 0.12, n - m, n - m), fill=(120, 80, 60), width=int(n * 0.1))
        E(m, m, n * 0.68, n * 0.68, (190, 235, 255))
        d.ellipse((n * 0.18, n * 0.18, n * 0.32, n * 0.32), fill=(255, 255, 255))
    elif name == "lightning":
        d.polygon([(n * 0.58, m), (n * 0.22, n * 0.55), (n * 0.48, n * 0.55), (n * 0.38, n - m), (n * 0.8, n * 0.4),
                   (n * 0.52, n * 0.4)], fill=(255, 225, 60), outline=OUT, width=w)
    elif name == "rocket":
        d.polygon([(c, m), (c + n * 0.17, n * 0.35), (c + n * 0.17, n * 0.72), (c - n * 0.17, n * 0.72),
                   (c - n * 0.17, n * 0.35)], fill=(240, 240, 250), outline=OUT, width=w)
        E(c - n * 0.08, n * 0.32, c + n * 0.08, n * 0.48, (90, 170, 255))
        d.polygon([(c - n * 0.17, n * 0.55), (c - n * 0.32, n * 0.8), (c - n * 0.17, n * 0.72)], fill=(255, 80, 90), outline=OUT, width=w)
        d.polygon([(c + n * 0.17, n * 0.55), (c + n * 0.32, n * 0.8), (c + n * 0.17, n * 0.72)], fill=(255, 80, 90), outline=OUT, width=w)
        d.polygon([(c - n * 0.1, n * 0.72), (c + n * 0.1, n * 0.72), (c, n - m)], fill=(255, 170, 40))
    elif name == "fish":
        d.ellipse((n * 0.15, n * 0.3, n * 0.72, n * 0.7), fill=(255, 150, 70), outline=OUT, width=w)
        d.polygon([(n * 0.7, c), (n - m, n * 0.3), (n - m, n * 0.7)], fill=(255, 150, 70), outline=OUT, width=w)
        d.ellipse((n * 0.26, n * 0.42, n * 0.34, n * 0.5), fill=OUT)
    elif name == "skull":
        E(n * 0.18, m, n * 0.82, n * 0.68, (245, 245, 240))
        d.rectangle((n * 0.32, n * 0.6, n * 0.68, n * 0.82), fill=(245, 245, 240), outline=OUT, width=w)
        for x in (0.32, 0.56):
            d.ellipse((n * x, n * 0.32, n * (x + 0.13), n * 0.47), fill=OUT)
        for x in (0.42, 0.5, 0.58):
            d.line((n * x, n * 0.68, n * x, n * 0.82), fill=OUT, width=w // 2)
    elif name == "moon":
        E(m, m, n - m, n - m, (255, 240, 190))
        cut = Image.new("L", img.size, 0)
        ImageDraw.Draw(cut).ellipse((n * 0.34, m * 0.2, n * 1.1, n * 0.78), fill=255)
        img.putalpha(Image.composite(Image.new("L", img.size, 0), img.getchannel("A"), cut))
        d = ImageDraw.Draw(img)
    elif name == "gift":
        d.rectangle((m, n * 0.4, n - m, n - m), fill=(255, 90, 120), outline=OUT, width=w)
        d.rectangle((m * 0.6, n * 0.28, n - m * 0.6, n * 0.42), fill=(255, 120, 150), outline=OUT, width=w)
        d.rectangle((c - n * 0.06, n * 0.28, c + n * 0.06, n - m), fill=(255, 220, 80))
        d.ellipse((c - n * 0.22, n * 0.12, c, n * 0.3), outline=(255, 220, 80), width=w)
        d.ellipse((c, n * 0.12, c + n * 0.22, n * 0.3), outline=(255, 220, 80), width=w)
    img = img.resize((size, size), Image.LANCZOS)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(img.getchannel("A").point(lambda a: int(a * 0.45)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.04))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(shadow, (int(size * 0.03), int(size * 0.05)))
    out.alpha_composite(img)
    return out


def _font(size):
    from ..utils import font
    return font("Inter:style=Black", size)
