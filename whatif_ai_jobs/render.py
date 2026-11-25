"""Этап 4б — монтаж и рендер: final_video.mp4 (1920x1080, 30 fps, H.264 + AAC).

python render.py                 полный рендер (музыка + сведение + видео)
python render.py --stills 1,10   отдельные кадры (середина указанных кадров раскадровки) → build/stills/
python render.py --at 12.5,40    кадры в указанные секунды → build/stills/
python render.py --audio         только музыка и сведение → build/mix.wav

Стиль: тёмный футуристичный, неоновые синие/фиолетовые акценты, шрифт Inter.
Фото: цветокоррекция в палитру ролика + эффект Кена Бёрнса. Инфографика рисуется кодом.
Каждый кадр раскадровки стоит ровно на своей строке озвучки (таймкоды Whisper из build/timing.json).
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import re
import subprocess
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
IMG = ROOT / "assets" / "images"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "ai_shorts_ru"))

W, H, FPS = 1920, 1080, 30
XF = 0.4                     # длительность перехода (crossfade), с
FONT_DIR = Path("/usr/share/fonts/opentype/inter")

BG_TOP, BG_BOT = (6, 9, 26), (17, 8, 38)
CYAN = (56, 200, 255)
PURPLE = (150, 95, 255)
MAGENTA = (255, 70, 200)
RED = (255, 80, 110)
GREEN = (70, 245, 170)
WHITE = (242, 245, 255)
MUTED = (150, 158, 196)
KW = (95, 225, 255)          # ключевые слова в субтитрах
ACCENT = {"red": RED, "green": GREEN, "blue": CYAN}

KEY_STEMS = ("ии", "искусствен", "интеллект", "нейросет", "робот", "безработ", "професс", "деньг", "доход",
             "налог", "зарплат", "экономи", "банкомат", "кассир", "конвейер", "луддит", "смысл", "навык",
             "утопи", "антиутопи", "автоматиз", "голдман", "маккинзи", "форум", "кейнс", "форд", "альтман",
             "финлянд", "кени", "стоктон", "миллион", "миллиард", "процент", "доллар", "евро", "тысяч",
             "тишина", "парадокс", "дефицит", "пособи", "алгоритм", "подпиш")


# ---------------------------------------------------------------- helpers

def norm(w: str) -> str:
    return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


@lru_cache(maxsize=None)
def F(weight: str, size: int) -> ImageFont.FreeTypeFont:
    p = FONT_DIR / f"Inter-{weight}.otf"
    if not p.exists():
        from shorts_ru.utils import font
        return font(f"Inter:style={weight}", size)
    return ImageFont.truetype(str(p), size)


def clip01(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clip01(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clip01(x)
    return x * x * (3 - 2 * x)


def prog(u, a, b):
    return clip01((u - a) / max(1e-6, b - a))


def blend(frame: np.ndarray, rgba: np.ndarray, x: int, y: int, alpha: float = 1.0) -> None:
    """Наложить RGBA-картинку на кадр (на месте), с обрезкой по краям."""
    if alpha <= 0.003:
        return
    h, w = rgba.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = sub[..., 3:4] * (alpha / 255.0)
    reg = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (reg + (sub[..., :3] - reg) * a + 0.5).astype(np.uint8)


def compose(bg: np.ndarray, layer: Image.Image, glow: float = 0.9) -> np.ndarray:
    """Слой PIL (RGBA, W×H) поверх фона с неоновым свечением (размытие на 1/4 разрешения)."""
    a = np.asarray(layer)
    out = bg.astype(np.float32)
    if glow > 0:
        small = cv2.resize(a, (W // 4, H // 4), interpolation=cv2.INTER_AREA).astype(np.float32)
        pm = small[..., :3] * (small[..., 3:4] / 255.0)
        g = cv2.GaussianBlur(pm, (0, 0), 6)
        out += cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR) * glow
    al = a[..., 3:4].astype(np.float32) / 255.0
    out += (a[..., :3] - out) * al
    return np.clip(out, 0, 255).astype(np.uint8)


def fmt_num(v: float) -> str:
    if abs(v - round(v)) < 1e-6:
        s = f"{int(round(v)):,}".replace(",", " ")
    else:
        s = f"{v:.1f}".replace(".", ",")
    return s


def text_w(f, s):
    return f.getlength(s)


def wrap(f, text, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_w(f, t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- backgrounds

@lru_cache(maxsize=1)
def tech_base() -> np.ndarray:
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    x = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    base = np.array(BG_TOP, np.float32) * (1 - y) + np.array(BG_BOT, np.float32) * y
    base = np.broadcast_to(base, (H, W, 3)).copy()

    def blob(cx, cy, r, col, a):
        d = ((x - cx) * (W / H)) ** 2 + (y - cy) ** 2
        return np.exp(-d / (r * r)) * np.array(col, np.float32) * a
    base += blob(0.12, 0.92, 0.55, PURPLE, 0.30) + blob(0.9, 0.08, 0.5, CYAN, 0.16) + blob(0.55, 0.5, 0.9, (20, 30, 80), 0.25)
    return np.clip(base, 0, 255).astype(np.uint8)


GRID = 90


@lru_cache(maxsize=12)
def tech_bg(off: int) -> np.ndarray:
    """Фон инфографики: градиент + медленно плывущая сетка (смещение кратно 6 px)."""
    base = tech_base().astype(np.float32)
    m = np.zeros((H, W), np.float32)
    for yy in range((-off) % GRID, H, GRID):
        m[yy:yy + 1, :] = 1
    for xx in range(0, W, GRID):
        m[:, xx:xx + 1] = 1
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    m *= 0.35 + 0.65 * yy  # сетка ярче к низу кадра
    base += m[..., None] * np.array(CYAN, np.float32) * 0.075
    return np.clip(base, 0, 255).astype(np.uint8)


def tech_frame(t: float) -> np.ndarray:
    return tech_bg(int(t * 18) // 6 * 6 % GRID).copy()


@lru_cache(maxsize=1)
def vignette() -> np.ndarray:
    y = np.linspace(-1, 1, H, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, W, dtype=np.float32)[None, :]
    v = 1 - 0.55 * np.clip((x ** 2 * 0.8 + y ** 2 * 1.0) - 0.15, 0, 1.4) / 1.4
    return v


SRC_W, SRC_H = int(W * 1.16), int(H * 1.16)


@lru_cache(maxsize=8)
def graded(path: str, w: int = SRC_W, h: int = SRC_H, tint: str = "neon") -> np.ndarray:
    """Фото → заполнение кадра (cover) + цветокоррекция в палитру ролика."""
    im = Image.open(path).convert("RGB")
    sc = max(w / im.width, h / im.height)
    nw, nh = max(w, round(im.width * sc)), max(h, round(im.height * sc))
    im = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = int((nh - h) * 0.4)  # чуть выше центра — чтобы не резать головы
    a = np.asarray(im.crop((left, top, left + w, top + h)), np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    a = lum[..., None] * 0.42 + a * 0.58                     # приглушить цвет
    a = np.clip((a - 0.5) * 1.2 + 0.5, 0, 1)                 # контраст
    a = a ** 1.15                                            # плотнее тени и середина
    sh = (1 - lum)[..., None] ** 1.5
    tone = {"neon": (0.10, 0.07, 0.30), "red": (0.30, 0.04, 0.10), "blue": (0.03, 0.12, 0.30)}[tint]
    a = a * (1 - 0.45 * sh) + np.array(tone, np.float32) * 0.45 * sh   # тени в сине-фиолетовый
    hi = np.clip(lum - 0.55, 0, 1)[..., None]
    a += hi * np.array((0.02, 0.10, 0.16), np.float32)       # блики чуть в циан
    a *= 0.74
    # светлое небо/верх кадра — притемнить и увести в холодный тон
    top = np.clip(1 - (np.linspace(0, 1, h, dtype=np.float32)[:, None, None] / 0.45), 0, 1) ** 1.5
    a = a * (1 - 0.35 * top) + np.array((0.05, 0.06, 0.18), np.float32) * 0.35 * top
    yv = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    xv = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    vig = 1 - 0.6 * np.clip((xv ** 2 * 0.75 + yv ** 2) - 0.2, 0, 1.3) / 1.3
    a *= vig[..., None]
    # неоновые засветки по краям
    a += np.exp(-(((xv + 1.05) * 1.6) ** 2 + ((yv - 0.9) * 1.3) ** 2))[..., None] * np.array((0.20, 0.06, 0.32), np.float32)
    a += np.exp(-(((xv - 1.05) * 1.6) ** 2 + ((yv + 0.9) * 1.3) ** 2))[..., None] * np.array((0.02, 0.14, 0.24), np.float32)
    # нижняя треть темнее — под субтитры
    a *= (1 - 0.35 * np.clip((yv - 0.35) / 0.65, 0, 1) ** 1.5)[..., None]
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def kenburns(src: np.ndarray, u: float, dur: float, seed: int, out_w: int = W, out_h: int = H) -> np.ndarray:
    r = np.random.default_rng(seed)
    sh, sw = src.shape[:2]
    p = (u + XF / 2) / (dur + XF)            # движение не останавливается и во время перехода
    p = min(1.05, max(-0.05, p))
    zin = r.random() < 0.62
    full, tight = sw, sw / 1.13
    vw = full + (tight - full) * p if zin else tight + (full - tight) * p
    vw = min(sw, vw)
    vh = vw * out_h / out_w
    ang = r.uniform(0, 2 * math.pi)
    mx, my = (sw - tight) / 2, (sh - tight * out_h / out_w) / 2
    cx = sw / 2 + math.cos(ang) * mx * 0.8 * (p - 0.5)
    cy = sh / 2 + math.sin(ang) * my * 0.8 * (p - 0.5)
    cx = min(sw - vw / 2, max(vw / 2, cx))
    cy = min(sh - vh / 2, max(vh / 2, cy))
    s = out_w / vw
    M = np.array([[s, 0, -(cx - vw / 2) * s], [0, s, -(cy - vh / 2) * s]], np.float32)
    return cv2.warpAffine(src, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


# ---------------------------------------------------------------- overlays

@lru_cache(maxsize=32)
def label_img(text: str) -> np.ndarray:
    size = 54
    f = F("Black", size)
    while text_w(f, text) > 1400 and size > 34:
        size -= 4
        f = F("Black", size)
    tw = int(text_w(f, text))
    pad, h = 30, 92
    w = tw + pad * 2 + 16
    im = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, 2 + w, 2 + h), 12, fill=(7, 9, 26, 200), outline=(*CYAN, 170), width=2)
    d.rounded_rectangle((2, 2, 12, 2 + h), 4, fill=CYAN)
    d.text((2 + pad + 14, 2 + h / 2 + 2), text, font=f, fill=WHITE, anchor="lm")
    return np.asarray(im)


@lru_cache(maxsize=16)
def hud_img(idx: int, total: int, title: str) -> np.ndarray:
    f = F("Bold", 26)
    txt = f"{idx:02d} / {total:02d}   {title}"
    tw = int(text_w(f, txt))
    w, h = max(tw, total * 34) + 20, 74
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((w - 10, 4), txt, font=f, fill=(*WHITE, 230), anchor="ra")
    for k in range(total):
        x1 = w - 10 - (total - 1 - k) * 34
        col = (*CYAN, 255) if k + 1 == idx else ((*PURPLE, 200) if k + 1 < idx else (*MUTED, 90))
        d.rounded_rectangle((x1 - 28, 52, x1, 58), 3, fill=col)
    return np.asarray(im)


@lru_cache(maxsize=1)
def corner_patches():
    L, T = 46, 3
    out = []
    for fx, fy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = L - T if fx else 0
        y = L - T if fy else 0
        d.rectangle((0, y, L, y + T - 1), fill=(*CYAN, 150))
        d.rectangle((x, 0, x + T - 1, L), fill=(*CYAN, 150))
        out.append((np.asarray(im), fx, fy))
    return out


def draw_corners(frame, alpha=1.0):
    m = 34
    for p, fx, fy in corner_patches():
        blend(frame, p, W - m - p.shape[1] if fx else m, H - m - p.shape[0] if fy else m, alpha)


# ---------------------------------------------------------------- captions

class Captions:
    """Крупные субтитры снизу по центру: 1–2 строки, обводка, ключевые слова цветом."""

    def __init__(self, phrases, keywords: dict, hidden: list):
        self.ph = phrases
        self.starts = [p[1] for p in phrases]
        self.kw = keywords       # номер кадра → слова из надписи на экране
        self.hidden = hidden
        self.f = F("Black", 58)

    def is_kw(self, w, shot):
        n = norm(w)
        if not n:
            return False
        if re.search(r"\d", w) or (len(n) >= 5 and n[:5] in self.kw.get(shot, ())):
            return True
        return n == "ии" or any(n.startswith(s) for s in KEY_STEMS if len(s) > 2)

    @lru_cache(maxsize=12)
    def img(self, k):
        words = [w["w"] for w in self.ph[k][0]]
        shot = self.ph[k][0][0]["shot"]
        f = self.f
        sp = text_w(f, " ")
        widths = [text_w(f, w) for w in words]
        lines = [list(range(len(words)))]
        if sum(widths) + sp * (len(words) - 1) > 1560 and len(words) > 1:
            best = None
            for cut in range(1, len(words)):
                a = sum(widths[:cut]) + sp * (cut - 1)
                b = sum(widths[cut:]) + sp * (len(words) - cut - 1)
                if best is None or max(a, b) < best[0]:
                    best = (max(a, b), cut)
            lines = [list(range(best[1])), list(range(best[1], len(words)))]
        lh = 74
        im = Image.new("RGBA", (W, lh * len(lines) + 30), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for li, idxs in enumerate(lines):
            lw = sum(widths[i] for i in idxs) + sp * (len(idxs) - 1)
            x = (W - lw) / 2
            y = 10 + li * lh
            for i in idxs:
                col = KW if self.is_kw(words[i], shot) else WHITE
                d.text((x + 3, y + 5), words[i], font=f, fill=(0, 0, 0, 160))
                d.text((x, y), words[i], font=f, fill=col, stroke_width=6, stroke_fill=(6, 6, 18))
                x += widths[i] + sp
        return np.asarray(im)

    def draw(self, frame, t):
        import bisect
        k = bisect.bisect_right(self.starts, t + 0.05) - 1
        if k < 0:
            return
        ph, s, e = self.ph[k]
        if not (s - 0.05 <= t < e) or any(a <= s < b for a, b in self.hidden):
            return
        im = self.img(k)
        age = t - (s - 0.05)
        al = clip01(age / 0.12) * clip01((e - t) / 0.08 + 0.2)
        dy = int(8 * (1 - ease(age / 0.18)))
        blend(frame, im, 0, H - 52 - im.shape[0] + dy, al)


# ---------------------------------------------------------------- infographics (PIL)

def title_block(d, title, u, y=205, color=WHITE, accent=CYAN):
    e = ease(u / 0.45)
    f = F("Black", 66)
    while text_w(f, title) > 1400:
        f = F("Black", f.size - 4)
    a = int(255 * e)
    d.text((W / 2, y + 12 * (1 - e)), title, font=f, fill=(*color, a), anchor="mm")
    lw = int(260 * ease(prog(u, 0.15, 0.7)))
    d.rounded_rectangle((W / 2 - lw, y + 52, W / 2 + lw, y + 57), 3, fill=(*accent, a))


def note_block(d, note, u, y=812):
    if note:
        a = int(220 * ease(prog(u, 0.8, 1.3)))
        d.text((W / 2, y), note, font=F("Medium", 30), fill=(*MUTED, a), anchor="mm")


def g_timeline(d, v, u, dur):
    items = v["items"]
    n = len(items)
    title_block(d, v.get("title", ""), u)
    x0, x1, y = 230, 1690, 520
    span = max(1.2, min(dur * 0.85, n * 1.1))
    p = ease_io(prog(u, 0.25, 0.25 + span))
    d.rounded_rectangle((x0, y - 3, x1, y + 3), 3, fill=(*MUTED, 70))
    d.rounded_rectangle((x0, y - 3, x0 + (x1 - x0) * p, y + 3), 3, fill=(*CYAN, 255))
    for i, it in enumerate(items):
        xi = x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)
        reach = (xi - x0) / (x1 - x0)
        e = ease((p - reach) / 0.12 + 0.0001) if p >= reach - 0.001 else 0.0
        if e <= 0.01:
            continue
        active = p >= reach and (i == n - 1 or p < (i + 1) / (n - 1))
        r = 16 + 6 * e
        col = CYAN if not active else MAGENTA
        d.ellipse((xi - r - 8, y - r - 8, xi + r + 8, y + r + 8), outline=(*col, int(160 * e)), width=3)
        d.ellipse((xi - r, y - r, xi + r, y + r), fill=(*col, int(255 * e)))
        parts = it.split(" ", 1)
        if re.search(r"\d", parts[0]) and len(parts) == 2:
            top, bot = parts
        else:
            top, bot = "", it
        dy = int(14 * (1 - e))
        if top:
            d.text((xi, y - 70 - dy), top, font=F("Black", 46), fill=(*CYAN, int(255 * e)), anchor="mm")
        fb = F("Bold", 38 if n <= 5 else 32)
        d.text((xi, y + 72 + dy), bot, font=fb, fill=(*WHITE, int(255 * e)), anchor="mm")


def _icon(d, kind, cx, cy, col, a):
    r = 26
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(*col, a), width=4)
    if kind == "red":
        k = 10
        d.line((cx - k, cy - k, cx + k, cy + k), fill=(*col, a), width=5)
        d.line((cx - k, cy + k, cx + k, cy - k), fill=(*col, a), width=5)
    elif kind == "green":
        d.line((cx - 11, cy + 1, cx - 3, cy + 9, cx + 12, cy - 9), fill=(*col, a), width=5, joint="curve")
    else:
        d.polygon(((cx - 7, cy - 11), (cx + 11, cy), (cx - 7, cy + 11)), fill=(*col, a))


def g_list(d, v, u, dur):
    col = ACCENT.get(v.get("color"), CYAN)
    title_block(d, v["title"], u, color=WHITE, accent=col)
    items = v["items"]
    n = len(items)
    step = min(0.7, max(0.25, (dur * 0.7 - 0.4) / max(1, n)))
    fb = F("Bold", 50)
    row_h = min(92, 460 // n)
    y0 = 315 + (460 - row_h * n) // 2
    maxw = max(text_w(fb, it) for it in items) + 90
    x0 = int((W - maxw) / 2)
    for i, it in enumerate(items):
        e = ease(prog(u, 0.45 + i * step, 0.8 + i * step))
        if e <= 0:
            continue
        a = int(255 * e)
        y = y0 + i * row_h + row_h // 2
        x = x0 - int(50 * (1 - e))
        d.rounded_rectangle((x - 30, y - row_h // 2 + 8, x + maxw + 30, y + row_h // 2 - 8), 14,
                            fill=(12, 14, 40, int(150 * e)), outline=(*col, int(70 * e)), width=2)
        _icon(d, v.get("color"), x + 26, y, col, a)
        d.text((x + 80, y), it, font=fb, fill=(*WHITE, a), anchor="lm")
    note_block(d, v.get("note"), u)


def g_counter(d, v, u, dur):
    lab = v["label"]
    fl = F("Bold", 46)
    while text_w(fl, lab) > 1600:
        fl = F("Bold", fl.size - 3)
    e0 = ease(u / 0.4)
    d.text((W / 2, 330), lab, font=fl, fill=(*WHITE, int(240 * e0)), anchor="mm")
    span = max(1.0, min(dur * 0.65, 3.2))
    p = ease_io(prog(u, 0.2, 0.2 + span))
    a, b = float(v["from"]), float(v["to"])
    val = a + (b - a) * p
    pre, suf = v.get("prefix", ""), v.get("suffix", "")
    m = re.match(r"^(\d+)–$", pre)
    if m:  # диапазон «6–7%»: считаем обе границы
        pre = f"{round(int(m.group(1)) * p)}–"
    num = f"{pre}{fmt_num(round(val))}{suf}"
    col = RED if v.get("down") else CYAN
    fn = F("Black", 200)
    while text_w(fn, num) > 1700:
        fn = F("Black", fn.size - 10)
    d.text((W / 2, 535), num, font=fn, fill=(*col, 255), anchor="mm")
    bw = 900
    frac = (val - min(a, b)) / max(1e-9, abs(b - a)) if b != a else 1
    d.rounded_rectangle((W / 2 - bw / 2, 690, W / 2 + bw / 2, 704), 7, fill=(*MUTED, 60))
    if frac > 0.003:
        d.rounded_rectangle((W / 2 - bw / 2, 690, W / 2 - bw / 2 + max(14, bw * clip01(frac)), 704), 7, fill=(*col, 255))
    note_block(d, v.get("note"), u, y=790)


def g_bars(d, v, u, dur):
    title_block(d, v["title"], u)
    bars = v["bars"]
    n = len(bars)
    mx = max(b[1] for b in bars)
    fl, fv = F("Bold", 38), F("Black", 46)
    lab_w = max(text_w(fl, b[0]) for b in bars)
    x_lab = int(max(560, (W - (lab_w + 40 + 860 + 160)) / 2 + lab_w))
    x0, full = x_lab + 40, 820
    row = min(112, 470 // n)
    y0 = 310 + (470 - row * n) // 2
    step = min(0.45, max(0.2, (dur * 0.55) / n))
    for i, (lab, val) in enumerate(bars):
        e = ease_io(prog(u, 0.4 + i * step, 1.3 + i * step))
        y = y0 + i * row + row // 2
        if v.get("pairs"):
            col = CYAN if i < 2 else PURPLE
        elif lab.lower().startswith("исчез"):
            col = RED
        elif lab.lower().startswith("появ"):
            col = GREEN
        else:
            col = CYAN if i % 2 == 0 else PURPLE
        a0 = int(255 * ease(prog(u, 0.25 + i * step, 0.6 + i * step)))
        d.text((x_lab, y), lab, font=fl, fill=(*WHITE, a0), anchor="rm")
        bh = min(58, row - 30)
        L = full * val / mx * e
        d.rounded_rectangle((x0, y - bh / 2, x0 + full, y + bh / 2), 10, fill=(*MUTED, int(28 * a0 / 255)))
        if L > 4:
            d.rounded_rectangle((x0, y - bh / 2, x0 + L, y + bh / 2), 10, fill=(*col, 255))
        if e > 0.02:
            d.text((x0 + L + 18, y), f"{fmt_num(val * e if e < 1 else val)}{v.get('unit', '')}", font=fv,
                   fill=(*WHITE, int(255 * min(1, e * 2))), anchor="lm")
    note_block(d, v.get("note"), u)


def g_bigtext(d, v, u, dur):
    text = v["text"]
    size = 132
    f = F("Black", size)
    lines = wrap(f, text, 1600)
    while (len(lines) > 3 or max(text_w(f, l) for l in lines) > 1650) and size > 60:
        size -= 8
        f = F("Black", size)
        lines = wrap(f, text, 1600)
    lh = int(size * 1.12)
    sub = v.get("sub", "")
    total_h = lh * len(lines) + (90 if sub else 0)
    y = 500 - total_h / 2 + lh / 2
    k = 0
    for li, line in enumerate(lines):
        words = line.split()
        sp = text_w(f, " ")
        lw = text_w(f, line)
        x = W / 2 - lw / 2
        for w in words:
            e = ease(prog(u, 0.1 + k * 0.09, 0.45 + k * 0.09))
            col = CYAN if ("≠" in w or k == 0 and len(lines) == 1) else WHITE
            d.text((x, y + li * lh + 20 * (1 - e)), w, font=f, fill=(*col, int(255 * e)), anchor="lm")
            x += text_w(f, w) + sp
            k += 1
    if sub:
        e = ease(prog(u, 0.5 + k * 0.09, 1.0 + k * 0.09))
        fs = F("Medium", 40)
        d.text((W / 2, y + len(lines) * lh - lh / 2 + 70), sub, font=fs, fill=(*MUTED, int(255 * e)), anchor="mm")


def g_split(d, v, u, dur):
    e = ease(u / 0.6)
    for side, txt, col in ((0, v["left"], CYAN), (1, v["right"], RED)):
        f = F("Black", 92)
        cx = W * (0.25 if side == 0 else 0.75) + (-80 if side == 0 else 80) * (1 - e)
        d.text((cx, 470), txt, font=f, fill=(*col, int(255 * e)), anchor="mm")
        sub = "мир изобилия" if side == 0 else "мир неравенства"
        d.text((cx, 570), sub, font=F("Medium", 44), fill=(*WHITE, int(230 * ease(prog(u, 0.4, 0.9)))), anchor="mm")
    h = int(760 * ease(prog(u, 0.1, 0.7)))
    if h > 4:
        d.rounded_rectangle((W / 2 - 3, 520 - h / 2, W / 2 + 3, 520 + h / 2), 3, fill=(*WHITE, 230))
    vs = ease(prog(u, 0.5, 0.9))
    if vs > 0.01:
        d.ellipse((W / 2 - 46, 474, W / 2 + 46, 566), fill=(10, 10, 30, int(255 * vs)), outline=(*WHITE, int(255 * vs)), width=3)
        d.text((W / 2, 520), "VS", font=F("Black", 40), fill=(*WHITE, int(255 * vs)), anchor="mm")


def g_chart_down(d, v, u, dur):
    title_block(d, v["title"], u, accent=RED)
    x0, x1, y0, y1 = 240, 1680, 300, 770
    for k in range(5):
        yy = y0 + (y1 - y0) * k / 4
        d.line((x0, yy, x1, yy), fill=(*MUTED, 40), width=1)
    rng = np.random.default_rng(7)
    n = 90
    vals = []
    v_ = 0.45
    for i in range(n):
        if i < 64:
            v_ += 0.006 + rng.normal(0, 0.012)
        else:
            v_ -= 0.024 + abs(rng.normal(0, 0.01))
        vals.append(min(0.95, max(0.05, v_)))
    span = max(1.5, dur * 0.85)
    p = ease_io(prog(u, 0.3, 0.3 + span))
    m = max(2, int(n * p))
    pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * vals[i]) for i in range(m)]
    crash = 64
    if len(pts) > 1:
        up = pts[:min(m, crash + 1)]
        d.polygon(up + [(up[-1][0], y1), (up[0][0], y1)], fill=(*CYAN, 28))
        d.line(up, fill=(*CYAN, 255), width=6, joint="curve")
        if m > crash:
            dn = pts[crash:]
            d.polygon(dn + [(dn[-1][0], y1), (dn[0][0], y1)], fill=(*RED, 32))
            d.line(dn, fill=(*RED, 255), width=6, joint="curve")
            fl = clip01((m - crash) / 6)
            d.text((pts[-1][0] - 10, pts[-1][1] - 60), "−48%", font=F("Black", 64), fill=(*RED, int(255 * fl)), anchor="rm")
        xe, ye = pts[-1]
        d.ellipse((xe - 10, ye - 10, xe + 10, ye + 10), fill=(*WHITE, 255))
    note_block(d, v.get("note"), u, y=812)


def g_endcard(d, v, u, dur):
    e = ease(u / 0.6)
    d.text((W / 2, 150), "СПАСИБО ЗА ПРОСМОТР", font=F("Black", 70), fill=(*WHITE, int(255 * e)), anchor="mm")
    d.text((W / 2, 225), "Новые сценарии «Что если?» — каждую неделю", font=F("Medium", 38),
           fill=(*MUTED, int(255 * e)), anchor="mm")
    # места под элементы конечной заставки YouTube (видео слева и справа, подписка в центре)
    for i, (x, lab) in enumerate(((150, "СМОТРИ ДАЛЬШЕ"), (W - 150 - 600, "ЛУЧШЕЕ НА КАНАЛЕ"))):
        ei = ease(prog(u, 0.3 + i * 0.2, 0.9 + i * 0.2))
        yb = 330 + int(30 * (1 - ei))
        d.rounded_rectangle((x, yb, x + 600, yb + 338), 18, fill=(10, 12, 34, int(200 * ei)),
                            outline=(*(CYAN if i == 0 else PURPLE), int(230 * ei)), width=3)
        d.polygon(((x + 270, yb + 130), (x + 340, yb + 169), (x + 270, yb + 208)), fill=(*WHITE, int(200 * ei)))
        d.text((x + 300, yb + 380), lab, font=F("Bold", 34), fill=(*WHITE, int(230 * ei)), anchor="mm")
    es = ease(prog(u, 0.5, 1.1))
    pulse = 1 + 0.05 * math.sin(u * 4)
    r = 112 * pulse
    cx, cy = W / 2, 500
    d.ellipse((cx - r - 16, cy - r - 16, cx + r + 16, cy + r + 16), outline=(*MAGENTA, int(160 * es)), width=4)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*RED, int(255 * es)))
    d.polygon(((cx - 26, cy - 38), (cx + 38, cy), (cx - 26, cy + 38)), fill=(*WHITE, int(255 * es)))
    d.text((cx, cy + 175), "ПОДПИШИСЬ", font=F("Black", 54), fill=(*WHITE, int(255 * es)), anchor="mm")


HISTORIC = {"henry_ford", "keynes", "luddites", "textile_mill", "industrial_revolution", "ford_line", "model_t"}

FALLBACK = {
    "call_center": ["laptop_night", "office_empty"], "programmer": ["laptop_night"], "coworking": ["laptop_night", "office_empty"],
    "team_meeting": ["crowd", "office_empty"], "window_man": ["city_night", "laptop_night"], "city_night": ["highway_night", "finance_towers"],
    "empty_street": ["highway_night", "city_night"], "mall_empty": ["office_empty", "empty_street"], "park_people": ["crowd"],
    "stock_exchange": ["trading_screens", "finance_towers"], "trading_screens": ["stock_exchange", "finance_towers"],
    "data_center": ["laptop_night"], "green_city": ["finance_towers", "city_night"], "slum_towers": ["finance_towers", "crowd"],
    "runners": ["crowd", "park_people"], "family_picnic": ["park_people", "crowd"], "artist": ["coworking", "crowd"],
    "stockton": ["empty_street", "highway_night"], "helsinki": ["city_night", "finance_towers"], "banknotes": ["atm", "finance_towers"],
    "atm": ["banknotes", "finance_towers"], "warehouse_robot": ["car_robots", "data_center"], "car_robots": ["warehouse_robot", "ford_line"],
    "humanoid": ["warehouse_robot", "car_robots", "data_center"], "model_t": ["ford_line", "henry_ford"], "ford_line": ["model_t", "car_robots"],
    "textile_mill": ["industrial_revolution", "luddites"], "industrial_revolution": ["textile_mill", "luddites"],
    "luddites": ["textile_mill", "industrial_revolution"], "electrician": ["plumber"], "plumber": ["electrician"],
}

GRAPHICS = {"timeline": g_timeline, "list": g_list, "counter": g_counter, "bars": g_bars, "bigtext": g_bigtext,
            "split": g_split, "chart_down": g_chart_down, "endcard": g_endcard}


# ---------------------------------------------------------------- renderer

class Renderer:
    def __init__(self):
        from align import make_phrases
        data = json.loads((BUILD / "shots.json").read_text(encoding="utf-8"))
        timing = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
        meta_p = BUILD / "images.json"
        self.meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        choice_p = BUILD / "image_choice.json"
        self.choice = json.loads(choice_p.read_text(encoding="utf-8")) if choice_p.exists() else {}
        self.shots = data["shots"]
        self.sections = data["sections"]
        self.duration = timing["duration"]
        self.lines = timing["lines"]
        self.start = [l["shot_start"] for l in self.lines]
        self.end = [l["shot_end"] for l in self.lines]
        sec_ids = [s[0] for s in self.sections]
        self.sec_idx = {s: i for i, s in enumerate(sec_ids)}
        # какая картинка в каком кадре: повторы ключа берут следующий вариант
        seen: dict = {}
        self.photo = {}
        for i, s in enumerate(self.shots):
            keys = []
            v = s["visual"]
            if isinstance(v, str) and v.startswith("img:"):
                keys = [v[4:]]
            elif isinstance(v, dict) and v.get("photo"):
                keys = [v["photo"]]
            for k in keys:
                n = seen.get(k, 0)
                seen[k] = n + 1
                self.photo[i] = self._pick(k, n)
                if self.photo[i] is None and k not in HISTORIC:
                    # последний вариант: любое уже скачанное фото (разное для разных кадров)
                    pool = sorted(str(x) for x in IMG.glob("*.jpg")
                                  if x.stem.rsplit("_", 1)[0] not in HISTORIC and x.stem.rsplit("_", 1)[0] in self.meta)
                    if pool:
                        self.photo[i] = pool[zlib.crc32(f"pool{s['id']}".encode()) % len(pool)]
        kws = {}
        for i, s in enumerate(self.shots):
            kws[i] = {norm(w)[:5] for w in (s.get("onscreen") or "").split() if len(norm(w)) >= 5}
        hidden = [(self.start[i], self.end[i]) for i, s in enumerate(self.shots) if s["visual"] == "card"]
        self.caps = Captions(make_phrases(timing["words"]), kws, hidden)

    def _pick(self, key, n, _depth=0):
        cands = self.meta.get(key) or []
        if not any((IMG / f"{key}_{i}.jpg").exists() for i in range(len(cands))) and _depth == 0:
            for alt in FALLBACK.get(key, []):   # нет своего фото — ближайшее по смыслу
                r = self._pick(alt, n, 1)
                if r:
                    return r
        avail = [i for i in range(len(cands)) if (IMG / f"{key}_{i}.jpg").exists()]
        order = self.choice.get(key, avail)
        if isinstance(order, int):
            order = [order] + [i for i in avail if i != order]
        order = [i for i in order if i in avail]
        if not order:
            return None
        return str(IMG / f"{key}_{order[n % len(order)]}.jpg")

    def idx_at(self, t):
        import bisect
        return max(0, min(len(self.shots) - 1, bisect.bisect_right(self.start, t) - 1))

    # --- один кадр раскадровки в момент t (u — время от начала кадра)
    def shot_frame(self, i, t):
        s = self.shots[i]
        u = t - self.start[i]
        dur = self.end[i] - self.start[i]
        v = s["visual"]
        sec = s["section"]
        seed = zlib.crc32(f"shot{s['id']}".encode())
        if v == "card":
            return self.card_frame(i, u, dur, t)
        if isinstance(v, str) and v.startswith("img:"):
            path = self.photo.get(i)
            if path:
                tint = "red" if sec == "newworld" and s["id"] in (79, 80) else "neon"
                fr = kenburns(graded(path, tint=tint), u, dur, seed)
            else:  # нет подходящего фото — абстрактный фон с надписью
                fr = tech_frame(t)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                g_bigtext(ImageDraw.Draw(lay), {"text": s.get("onscreen") or self.sections[self.sec_idx[sec]][1] or "ЧТО ЕСЛИ?"}, u, dur)
                fr = compose(fr, lay)
        elif isinstance(v, dict) and v["kind"] == "factcard":
            fr = self.factcard(i, v, u, dur, t, seed)
        elif isinstance(v, dict) and v["kind"] == "split":
            fr = tech_frame(t)
            for side, key, tint in ((0, "green_city", "blue"), (1, "slum_towers", "red")):
                pth = self._pick(key, 0)
                if pth:
                    half = kenburns(graded(pth, int(W / 2 * 1.16), int(H * 1.16), tint=tint), u, dur, seed + side, W // 2, H)
                    e = ease(u / 0.6)
                    half = (half.astype(np.float32) * 0.55).astype(np.uint8)
                    rgba = np.dstack([half, np.full(half.shape[:2], int(255 * e), np.uint8)])
                    blend(fr, rgba, side * W // 2 + int((-60 if side == 0 else 60) * (1 - e)), 0)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            g_split(ImageDraw.Draw(lay), v, u, dur)
            fr = compose(fr, lay)
        else:
            fr = tech_frame(t)
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(lay)
            GRAPHICS[v["kind"]](d, v, u, dur)
            fr = compose(fr, lay)
        fr = np.ascontiguousarray(fr)
        if s.get("onscreen") and not (isinstance(v, dict) and v.get("kind") == "endcard"):
            e = ease(prog(u, 0.25, 0.7))
            blend(fr, label_img(s["onscreen"]), 70 - int(60 * (1 - e)), 66, e)
        k = self.sec_idx[sec]
        if k > 0 and not (isinstance(v, dict) and v.get("kind") == "endcard"):
            hud = hud_img(k, len(self.sections) - 1, self.sections[k][1])
            blend(fr, hud, W - 64 - hud.shape[1], 62, 0.9)
        draw_corners(fr, 0.8)
        return fr

    def factcard(self, i, v, u, dur, t, seed):
        fr = tech_frame(t)
        path = self.photo.get(i)
        bx, by, bw, bh = 110, 170, 860, 640
        if path:
            ph = kenburns(graded(path, int(bw * 1.15), int(bh * 1.15)), u, dur, seed, bw, bh)
            e = ease(u / 0.5)
            mask = np.zeros((bh, bw), np.uint8)
            cv2.rectangle(mask, (0, 0), (bw, bh), 255, -1)
            rgba = np.dstack([ph, (mask * e).astype(np.uint8)])
            blend(fr, rgba, bx - int(40 * (1 - e)), by, 1.0)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        e = ease(u / 0.5)
        d.rounded_rectangle((bx - 6, by - 6, bx + bw + 6, by + bh + 6), 16, outline=(*CYAN, int(220 * e)), width=4)
        x = 1050
        ft = F("Black", 72)
        while text_w(ft, v["title"]) > 800:
            ft = F("Black", ft.size - 4)
        d.text((x, 235), v["title"], font=ft, fill=(*CYAN, int(255 * e)), anchor="lm")
        d.rounded_rectangle((x, 290, x + int(300 * ease(prog(u, 0.2, 0.7))), 295), 3, fill=(*PURPLE, 255))
        for k, (key, val) in enumerate(v["rows"]):
            ek = ease(prog(u, 0.5 + k * 0.45, 0.9 + k * 0.45))
            y = 370 + k * 140
            d.text((x + int(30 * (1 - ek)), y), key.upper(), font=F("SemiBold", 30), fill=(*MUTED, int(255 * ek)), anchor="lm")
            fv = F("Black", 56)
            while text_w(fv, val) > 780:
                fv = F("Black", fv.size - 4)
            d.text((x + int(30 * (1 - ek)), y + 52), val, font=fv, fill=(*WHITE, int(255 * ek)), anchor="lm")
        return compose(fr, lay, glow=0.6)

    def card_frame(self, i, u, dur, t):
        s = self.shots[i]
        k = self.sec_idx[s["section"]]
        title = s["section_title"] or s["text"].upper().rstrip(".")
        fr = tech_frame(t)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        e = ease(u / 0.45)
        n = len(self.sections) - 1
        d.text((W / 2, 360 - 20 * (1 - e)), f"ГЛАВА {k}", font=F("Bold", 40), fill=(*CYAN, int(255 * e)), anchor="mm")
        f = F("Black", 190)
        while text_w(f, title) > 1700:
            f = F("Black", f.size - 10)
        sc = 1.06 - 0.06 * e
        d.text((W / 2, 520), title, font=f, fill=(*WHITE, int(255 * e)), anchor="mm")
        lw = int(520 * ease(prog(u, 0.15, 0.8)) * sc)
        d.rounded_rectangle((W / 2 - lw, 640, W / 2 + lw, 646), 3, fill=(*PURPLE, 255))
        # мини-карта глав
        x0 = W / 2 - (n - 1) * 105
        for j in range(n):
            xj = x0 + j * 210
            col = CYAN if j + 1 == k else (PURPLE if j + 1 < k else MUTED)
            a = int((255 if j + 1 <= k else 110) * ease(prog(u, 0.2 + j * 0.04, 0.6 + j * 0.04)))
            r = 13 if j + 1 == k else 8
            if a > 3:
                d.ellipse((xj - r, 760 - r, xj + r, 760 + r), fill=(*col, a))
            if j + 1 < n and a > 3:
                d.line((xj + 18, 760, xj + 192, 760), fill=(*MUTED, a // 3), width=2)
            short = self.sections[j + 1][1].replace("ЧЕРЕЗ ", "").replace("ЧТО ДЕЛАТЬ ", "")
            if a > 3:
                d.text((xj, 800), short, font=F("SemiBold", 22), fill=(*col, a), anchor="mm")
        fr = compose(fr, lay, glow=1.1)
        # глитч в первые 0.35 с: RGB-сдвиг и смещённые полосы
        g = 1 - clip01(u / 0.35)
        if g > 0:
            rng = np.random.default_rng(int(t * 1000))
            dx = int(14 * g)
            fr[..., 0] = np.roll(fr[..., 0], dx, axis=1)
            fr[..., 2] = np.roll(fr[..., 2], -dx, axis=1)
            for _ in range(5):
                y0 = int(rng.integers(300, 760))
                hh = int(rng.integers(6, 30))
                fr[y0:y0 + hh] = np.roll(fr[y0:y0 + hh], int(rng.integers(-60, 60) * g), axis=1)
        return fr

    def frame(self, t):
        i = self.idx_at(t)
        fr = self.shot_frame(i, t)
        # переход: окно XF вокруг границы кадров
        if i + 1 < len(self.shots) and t > self.end[i] - XF / 2:
            a = (t - (self.end[i] - XF / 2)) / XF
            fr = cv2.addWeighted(fr, 1 - a, self.shot_frame(i + 1, t), a, 0)
        elif i > 0 and t < self.start[i] + XF / 2:
            a = (t - (self.start[i] - XF / 2)) / XF
            fr = cv2.addWeighted(self.shot_frame(i - 1, t), 1 - a, fr, a, 0)
        fr = np.ascontiguousarray(fr)
        self.caps.draw(fr, t)
        if t > self.duration - 1.0:  # затемнение в самом конце
            fr = (fr.astype(np.float32) * clip01((self.duration - t) / 1.0)).astype(np.uint8)
        return fr


# ---------------------------------------------------------------- audio

def make_audio() -> Path:
    from shorts_ru import audio
    SR = audio.SR
    timing = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
    data = json.loads((BUILD / "shots.json").read_text(encoding="utf-8"))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ROOT / "voiceover.wav"), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    voice = np.frombuffer(raw, np.float32).astype(np.float64)
    total = timing["duration"]
    n = int(total * SR)
    v = np.zeros(n)
    v[:min(n, len(voice))] = voice[:n]
    # музыка: своя тема на каждую главу, плавные переходы
    moods = {s[0]: s[2] for s in data["sections"]}
    bounds = []
    for i, s in enumerate(data["shots"]):
        if i == 0 or s["section"] != data["shots"][i - 1]["section"]:
            bounds.append((max(0.0, timing["lines"][i]["shot_start"] - 0.4), moods[s["section"]], 31 + len(bounds) * 13))
    m = np.zeros(n)
    xf = int(2.5 * SR)
    for k, (st, mood, seed) in enumerate(bounds):
        en = bounds[k + 1][0] if k + 1 < len(bounds) else total
        i0 = int(st * SR)
        ln = min(n, int(en * SR) + xf) - i0
        seg = audio.music(mood, ln / SR + 0.1, seed=seed, fade_out=2.5 if k + 1 < len(bounds) else 3.0)[:ln]
        if k > 0:
            f = min(xf, len(seg))
            seg[:f] *= np.linspace(0, 1, f)
        m[i0:i0 + len(seg)] += seg
    m[: int(1.5 * SR)] *= np.linspace(0, 1, int(1.5 * SR))   # fade in
    # уровень музыки: на ~20 дБ ниже голоса в речи, в паузах чуть громче (ducking)
    hop = 441
    c = np.cumsum(np.concatenate([[0.0], v ** 2]))
    lvl = np.sqrt(np.maximum(0, (c[hop:] - c[:-hop]) / hop))
    lvl = np.pad(lvl, (hop // 2, n - len(lvl) - hop // 2))
    talk = (lvl > 0.01).astype(np.float64)
    sm = np.zeros(n)
    g = 0.0
    att, rel = 1 - np.exp(-1 / (0.05 * SR)), 1 - np.exp(-1 / (0.5 * SR))
    for i in range(0, n, hop):
        target = talk[i]
        g += (target - g) * (1 - (1 - (att if target > g else rel)) ** hop)
        sm[i:i + hop] = g
    speech = talk > 0.5
    v_rms = np.sqrt(np.mean(v[speech] ** 2)) if speech.any() else 0.1
    m_rms = np.sqrt(np.mean(m ** 2)) + 1e-9
    base = v_rms / m_rms * 10 ** (-20 / 20)                   # −20 дБ под голосом
    gain = base * 10 ** ((6 * (1 - sm)) / 20)                # в паузах +6 дБ
    mix = v + m * gain
    # звуковые акценты: «вжух» на заставках глав
    for i, s in enumerate(data["shots"]):
        if s["visual"] == "card":
            x = audio.sfx("whoosh")
            j = max(0, int((timing["lines"][i]["shot_start"] - 0.25) * SR))
            mix[j:j + len(x)] += x[: n - j] * 0.28
    fo = int(2.0 * SR)
    mix[-fo:] *= np.linspace(1, 0, fo)
    peak = np.max(np.abs(mix))
    if peak > 0.98:
        mix = np.tanh(mix / peak * 1.2) / np.tanh(1.2) * 0.97
    wav = BUILD / "mix_raw.wav"
    import wave
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes())
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af",
                            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    mm = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={mm['input_i']}:measured_TP={mm['input_tp']}:"
          f"measured_LRA={mm['input_lra']}:measured_thresh={mm['input_thresh']}:offset={mm['target_offset']}:linear=true")
    out = BUILD / "mix.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", af, "-ar", "48000", "-ac", "2", str(out)],
                   check=True)
    print(f"сведение: {out} ({total:.1f} с)", flush=True)
    return out


# ---------------------------------------------------------------- video

def _chunk(job):
    cv2.setNumThreads(1)
    r = Renderer()
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-g", str(FPS * 2), "-threads", "2", job["out"]]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in range(job["f0"], job["f1"]):
        p.stdin.write(r.frame(f / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(p.stderr.read().decode(errors="ignore")[-1200:])
    return job["out"]


def render_full(workers: int):
    mix = make_audio()
    r = Renderer()
    total = int(round(r.duration * FPS))
    seg = BUILD / "segments"
    seg.mkdir(exist_ok=True)
    chunk = FPS * 20
    jobs = [{"f0": f0, "f1": min(total, f0 + chunk), "out": str(seg / f"seg_{k:04d}.mp4")}
            for k, f0 in enumerate(range(0, total, chunk))]
    print(f"рендер {total} кадров в {workers} процессах, {len(jobs)} кусков", flush=True)
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        futs = [ex.submit(_chunk, j) for j in jobs]
        for fu in as_completed(futs):
            fu.result()
            done += 1
            el = time.time() - t0
            print(f"  {done}/{len(jobs)} кусков, прошло {el / 60:.1f} мин, осталось ~"
                  f"{el / max(done, min(workers, len(jobs))) * (len(jobs) - done) / 60:.1f} мин", flush=True)
    lst = seg / "list.txt"
    lst.write_text("".join(f"file '{Path(j['out']).name}'\n" for j in jobs), encoding="utf-8")
    out = ROOT / "final_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(mix),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(out)], check=True)
    for j in jobs:
        Path(j["out"]).unlink(missing_ok=True)
    print(f"готово: {out} за {(time.time() - t0) / 60:.1f} мин", flush=True)


def stills(times, names):
    out = BUILD / "stills"
    out.mkdir(exist_ok=True)
    r = Renderer()
    for t, nm in zip(times, names):
        t0 = time.time()
        fr = r.frame(t)
        Image.fromarray(fr).save(out / f"{nm}.jpg", quality=90)
        print(f"{nm}: t={t:.2f} ({(time.time() - t0) * 1000:.0f} мс)", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", help="номера кадров раскадровки через запятую")
    ap.add_argument("--at", help="секунды через запятую")
    ap.add_argument("--audio", action="store_true")
    ap.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 2)))
    a = ap.parse_args()
    if a.stills:
        r = Renderer()
        ids = [int(x) for x in a.stills.split(",")]
        ts = [(r.start[i - 1] + r.end[i - 1]) / 2 for i in ids]
        stills(ts, [f"shot_{i:02d}" for i in ids])
    elif a.at:
        ts = [float(x) for x in a.at.split(",")]
        stills(ts, [f"t_{x:07.2f}" for x in ts])
    elif a.audio:
        make_audio()
    else:
        render_full(a.workers)
