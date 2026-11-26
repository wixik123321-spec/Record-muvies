"""Вертикальное превью для Shorts (1080x1920): фото сверху, крупный текст снизу, высокий контраст.

python short_thumb.py ФОТО ВЫХОД.png "ПЛАШКА" "СТРОКА 1|цвет" "СТРОКА 2|цвет" ...
Цвета: white, red, yellow, cyan. Первая строка с «*» в начале — мелкая (подзаголовок).
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import render as R  # noqa: E402

W, H = 1080, 1920
COLORS = {"white": (255, 255, 255), "red": (255, 50, 80), "yellow": (255, 214, 64), "cyan": (95, 225, 255)}


def main(photo, out, badge, *lines):
    R.W, R.H = W, H
    ph = R.graded(str(photo), W, 1250)                  # фото — верхние ~2/3 кадра
    bg = np.zeros((H, W, 3), np.float32)
    bg[:] = (10, 7, 28)
    bg[:1250] = ph.astype(np.float32) * 1.08
    y = np.linspace(0, 1, 1250, dtype=np.float32)[:, None, None]
    fade = np.clip((y - 0.55) / 0.45, 0, 1) ** 1.3       # растворение фото в тёмный низ
    bg[:1250] = bg[:1250] * (1 - fade) + np.array((10, 7, 28), np.float32) * fade
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    bg += np.exp(-((yy - 0.9) / 0.18) ** 2) * np.array((90, 20, 140), np.float32) * 0.6
    img = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    # плашка сверху
    fb = R.F("Black", 54)
    bw = d.textlength(badge, font=fb) + 70
    d.rounded_rectangle((W / 2 - bw / 2, 210, W / 2 + bw / 2, 300), 18, fill=(*COLORS["yellow"], 255))
    d.text((W / 2, 255), badge, font=fb, fill=(10, 8, 20), anchor="mm")
    # текстовый блок снизу
    items = []
    for ln in lines:
        txt, col = (ln.split("|") + ["white"])[:2]
        small = txt.startswith("*")
        txt = txt.lstrip("*")
        size = 64 if small else 150
        f = R.F("Bold" if small else "Black", size)
        while d.textlength(txt, font=f) > W - 90:
            size -= 6
            f = R.F("Bold" if small else "Black", size)
        items.append((txt, f, COLORS.get(col, COLORS["white"]), small))
    heights = [int(f.size * (1.25 if s else 1.02)) for _, f, _, s in items]
    ytop = 1560 - sum(heights) // 2
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    yc = ytop
    for (txt, f, col, small), hgt in zip(items, heights):
        g.text((W / 2, yc + hgt / 2), txt, font=f, fill=(*col, 200), anchor="mm")
        yc += hgt
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(img)
    yc = ytop
    for (txt, f, col, small), hgt in zip(items, heights):
        d.text((W / 2, yc + hgt / 2), txt, font=f, fill=col, anchor="mm", stroke_width=5 if small else 9,
               stroke_fill=(6, 5, 16))
        yc += hgt
    img.convert("RGB").save(out)
    print(out, img.size)


if __name__ == "__main__":
    main(*sys.argv[1:])
