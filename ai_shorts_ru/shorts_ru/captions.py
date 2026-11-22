"""Русские субтитры: короткие фразы по 1–3 слова, крупный шрифт с обводкой.

Звучащее слово подсвечивается, ключевые слова — отдельным ярким цветом.
Фраза появляется с коротким «pop»-масштабированием и проявлением.
Текст берётся из сценария (не из распознавания), поэтому опечаток нет.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from .utils import font, hex_rgb


@dataclass
class Phrase:
    words: list[dict]   # [{"w","s","e"}]
    start: float
    end: float


def _norm(w: str) -> str:
    return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


def build_phrases(scenes, max_words: int, max_chars: int) -> list[Phrase]:
    phrases: list[Phrase] = []
    for sc in scenes:
        cur: list[dict] = []
        for w in sc.words:
            text_len = len(" ".join(x["w"] for x in cur + [w]))
            if cur and (len(cur) >= max_words or text_len > max_chars or w["s"] - cur[-1]["e"] > 0.35):
                phrases.append(Phrase(cur, cur[0]["s"], cur[-1]["e"]))
                cur = []
            cur.append(w)
            if re.search(r"[.!?…,;:—]$", w["w"]):
                phrases.append(Phrase(cur, cur[0]["s"], cur[-1]["e"]))
                cur = []
        if cur:
            phrases.append(Phrase(cur, cur[0]["s"], cur[-1]["e"]))
    # фраза держится до начала следующей (но не дольше 0.6 с после последнего слова)
    for a, b in zip(phrases, phrases[1:]):
        a.end = min(b.start, a.end + 0.6)
    if phrases:
        phrases[-1].end += 0.6
    return phrases


class CaptionRenderer:
    def __init__(self, cfg, scenes, width: int = 1080):
        c = cfg.captions
        self.f = font(c.font, int(c.size))
        self.color, self.active = hex_rgb(c.color), hex_rgb(c.active_color)
        self.kw = hex_rgb(c.keyword_color)
        self.stroke, self.upper = int(c.stroke), bool(c.uppercase)
        self.y, self.W = int(c.y), width
        self.phrases = build_phrases(scenes, int(c.max_words), int(c.max_chars))
        self.keywords = set()
        for sc in scenes:
            for k in sc.keywords:
                for part in str(k).split():
                    if _norm(part):
                        self.keywords.add(_norm(part))
        self.cache: dict = {}

    def _render(self, ph: Phrase, active: int) -> Image.Image:
        key = (id(ph), active)
        if key in self.cache:
            return self.cache[key]
        words = [w["w"].upper() if self.upper else w["w"] for w in ph.words]
        space = self.f.getlength(" ")
        widths = [self.f.getlength(w) for w in words]
        total = sum(widths) + space * (len(words) - 1)
        lines = [(words, widths)]
        if total > self.W - 120 and len(words) > 1:  # перенос на две строки
            half = len(words) // 2 + len(words) % 2
            lines = [(words[:half], widths[:half]), (words[half:], widths[half:])]
        lh = int(self.f.size * 1.18)
        img = Image.new("RGBA", (self.W, lh * len(lines) + 60), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        idx = 0
        for li, (ws, wds) in enumerate(lines):
            x = (self.W - (sum(wds) + space * (len(ws) - 1))) / 2
            y = 30 + li * lh
            for w, wd in zip(ws, wds):
                is_kw = _norm(ph.words[idx]["w"]) in self.keywords
                col = self.active if idx == active else (self.kw if is_kw else self.color)
                d.text((x + 4, y + 7), w, font=self.f, fill=(0, 0, 0, 150))  # тень
                d.text((x, y), w, font=self.f, fill=col, stroke_width=self.stroke, stroke_fill=(10, 8, 20))
                x += wd + space
                idx += 1
        self.cache[key] = img
        return img

    def overlay(self, frame: np.ndarray, t: float) -> np.ndarray:
        ph = next((p for p in self.phrases if p.start - 0.05 <= t < p.end), None)
        if ph is None:
            return frame
        active = -1
        for i, w in enumerate(ph.words):
            if w["s"] - 0.03 <= t:
                active = i
        img = self._render(ph, active)
        age = t - (ph.start - 0.05)
        k = min(1.0, age / 0.14)
        scale = 0.82 + 0.18 * (1 - (1 - k) ** 3) + 0.04 * np.sin(min(1.0, age / 0.25) * np.pi)
        alpha = min(1.0, age / 0.1)
        if abs(scale - 1) > 0.005:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.BILINEAR)
        arr = np.asarray(img, np.float32) / 255
        h, w = arr.shape[:2]
        x0 = (frame.shape[1] - w) // 2
        y0 = self.y - h // 2
        ys, ye = max(0, y0), min(frame.shape[0], y0 + h)
        xs, xe = max(0, x0), min(frame.shape[1], x0 + w)
        sub = arr[ys - y0:ye - y0, xs - x0:xe - x0]
        a = sub[..., 3:4] * alpha
        frame[ys:ye, xs:xe] = frame[ys:ye, xs:xe] * (1 - a) + sub[..., :3] * a
        return frame
