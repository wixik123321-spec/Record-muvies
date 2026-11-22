"""Выразительный 2D-персонаж (по пояс): эмоции, позы, моргание, движение губ под голос.

Персонаж рисуется заново в каждом кадре (дёшево: векторные фигуры в 2x,
затем уменьшение), поэтому рот открывается по громкости голоса, глаза
моргают, корпус «дышит», а рука в позе «wave» машет.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw

CW, CH = 700, 1000   # холст персонажа (1x)
S = 2                # supersampling


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _dark(c, k=0.75):
    return tuple(int(v * k) for v in c)


POSES = {  # (левый локоть, левая кисть, правый локоть, правая кисть) относительно центра плеч
    "idle":     ((-185, 190), (-165, 330), (185, 190), (165, 330)),
    "point":    ((-185, 190), (-165, 330), (180, -40), (300, -110)),
    "hands_up": ((-250, -60), (-280, -220), (250, -60), (280, -220)),
    "think":    ((-185, 190), (-165, 330), (150, 170), (40, -40)),
    "shrug":    ((-260, 110), (-300, 0), (260, 110), (300, 0)),
    "wave":     ((-185, 190), (-165, 330), (220, -30), (250, -200)),
}

BROWS = {  # (наклон внутреннего края, подъём)
    # tilt > 0 опускает внутренний край (злость), < 0 поднимает его (грусть, страх)
    "neutral": (0, 0), "happy": (-3, 6), "surprised": (-2, 26), "scared": (-14, 18), "thinking": (0, 0),
    "sad": (-16, 4), "angry": (18, -6), "excited": (-3, 14),
}


class Character:
    def __init__(self, skin="#F2C29B", hair="#2B1B14", shirt="#3D7BFF", pants="#2A2E45"):
        self.skin, self.hair, self.shirt, self.pants = _rgb(skin), _rgb(hair), _rgb(shirt), _rgb(pants)

    def draw(self, t: float, emotion: str = "neutral", pose: str = "idle", talk: float = 0.0,
             look: float = 0.0, flip: bool = False) -> Image.Image:
        img = Image.new("RGBA", (CW * S, CH * S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        k = S
        bob = math.sin(t * 2.2) * 6
        cx = CW / 2
        sh_y = 600 + bob  # линия плеч

        def P(x, y):
            return (x * k, y * k)

        skin, shirt = self.skin, self.shirt
        # туловище
        d.rounded_rectangle((*P(cx - 175, sh_y - 30), *P(cx + 175, CH + 40)), radius=110 * k, fill=shirt)
        d.polygon([P(cx - 60, sh_y - 30), P(cx + 60, sh_y - 30), P(cx, sh_y + 60)], fill=skin)
        d.line([P(cx - 60, sh_y - 30), P(cx, sh_y + 60), P(cx + 60, sh_y - 30)], fill=_dark(shirt), width=10 * k)
        # шея
        d.rectangle((*P(cx - 45, sh_y - 120), *P(cx + 45, sh_y - 20)), fill=_dark(skin, 0.9))

        # руки
        le, lh, re_, rh = POSES.get(pose, POSES["idle"])
        if pose == "wave":
            a = math.sin(t * 9) * 40
            rh = (rh[0] + a, rh[1] + abs(a) * 0.2)
        arms = [((cx - 150, sh_y + 10), le, lh), ((cx + 150, sh_y + 10), re_, rh)]
        for (sx, sy), (ex, ey), (hx, hy) in arms:
            e = (cx + ex, sh_y + ey)
            h = (cx + hx, sh_y + hy)
            d.line([P(sx, sy), P(*e), P(*h)], fill=_dark(shirt, 0.88), width=62 * k, joint="curve")
            for pt in ((sx, sy), e):
                d.ellipse((*P(pt[0] - 31, pt[1] - 31), *P(pt[0] + 31, pt[1] + 31)), fill=_dark(shirt, 0.88))
            d.ellipse((*P(h[0] - 36, h[1] - 36), *P(h[0] + 36, h[1] + 36)), fill=skin)
        if pose == "point":  # указательный палец
            hx, hy = cx + rh[0], sh_y + rh[1]
            d.line([P(hx, hy), P(hx + 55, hy - 28)], fill=skin, width=22 * k)

        # голова
        hx, hy = cx, sh_y - 255
        d.ellipse((*P(hx - 172, hy - 20), *P(hx - 128, hy + 40)), fill=_dark(skin, 0.92))  # уши
        d.ellipse((*P(hx + 128, hy - 20), *P(hx + 172, hy + 40)), fill=_dark(skin, 0.92))
        d.ellipse((*P(hx - 150, hy - 175), *P(hx + 150, hy + 165)), fill=skin)
        # волосы
        d.chord((*P(hx - 160, hy - 195), *P(hx + 160, hy + 60)), 180, 360, fill=self.hair)
        d.polygon([P(hx - 160, hy - 60), P(hx - 40, hy - 120), P(hx + 70, hy - 85), P(hx + 160, hy - 60),
                   P(hx + 150, hy - 120), P(hx - 150, hy - 120)], fill=self.hair)
        d.pieslice((*P(hx - 165, hy - 140), *P(hx - 60, hy + 40)), 150, 270, fill=self.hair)

        # глаза
        blink = (t * 1.0) % 3.7 < 0.12
        ex_off, ey = 62, hy + 10
        eh = {"surprised": 48, "scared": 50, "excited": 44, "happy": 30, "sad": 32, "angry": 30}.get(emotion, 40)
        for side in (-1, 1):
            ex = hx + side * ex_off
            if blink or emotion == "happy":
                d.arc((*P(ex - 34, ey - 18), *P(ex + 34, ey + 30)), 200, 340, fill=(40, 28, 30), width=10 * k)
                continue
            d.ellipse((*P(ex - 34, ey - eh), *P(ex + 34, ey + eh)), fill=(255, 255, 255))
            pr = 22 if emotion not in ("scared", "surprised") else 15
            px = ex + look * 12 + (6 if emotion == "thinking" else 0)
            py = ey + (-10 if emotion == "thinking" else 4)
            d.ellipse((*P(px - pr, py - pr), *P(px + pr, py + pr)), fill=(35, 30, 45))
            d.ellipse((*P(px - pr * 0.25 + 6, py - pr * 0.6), *P(px + pr * 0.45 + 6, py - pr * 0.0)), fill=(255, 255, 255))
        # брови
        tilt, lift = BROWS.get(emotion, (0, 0))
        for side in (-1, 1):
            ex = hx + side * ex_off
            by = ey - eh - 22 - lift
            if emotion == "thinking" and side == 1:
                by -= 18
            inner = (ex - side * 34, by + tilt)
            outer = (ex + side * 34, by - tilt * 0.4)
            d.line([P(*inner), P(*outer)], fill=self.hair, width=15 * k)
        # нос и щёки
        d.arc((*P(hx - 14, hy + 50), *P(hx + 14, hy + 80)), 20, 160, fill=_dark(skin, 0.75), width=6 * k)
        if emotion in ("happy", "excited"):
            for side in (-1, 1):
                d.ellipse((*P(hx + side * 95 - 26, hy + 75), *P(hx + side * 95 + 26, hy + 100)), fill=(255, 140, 140))
        # рот: форма по эмоции + открытие по голосу
        my = hy + 115
        o = max(0.0, min(1.0, talk))
        mouth_dark, tongue = (90, 25, 40), (235, 110, 120)
        if emotion in ("surprised", "scared"):
            r = 22 + o * 14
            d.ellipse((*P(hx - r * 0.8, my - r), *P(hx + r * 0.8, my + r)), fill=mouth_dark)
        elif o > 0.08:
            w = 46 if emotion in ("happy", "excited") else 38
            hgt = 8 + o * 42
            top = my - (6 if emotion in ("happy", "excited") else 0)
            d.chord((*P(hx - w, top - hgt * 0.35), *P(hx + w, top + hgt)), 0, 180, fill=mouth_dark)
            d.ellipse((*P(hx - w * 0.5, top + hgt * 0.35), *P(hx + w * 0.5, top + hgt * 0.95)), fill=tongue)
            if emotion in ("happy", "excited"):
                d.rectangle((*P(hx - w * 0.8, top - 2), *P(hx + w * 0.8, top + 9)), fill=(255, 255, 255))
        elif emotion in ("happy", "excited"):
            d.chord((*P(hx - 48, my - 34), *P(hx + 48, my + 30)), 0, 180, fill=mouth_dark)
            d.rectangle((*P(hx - 38, my - 2), *P(hx + 38, my + 8)), fill=(255, 255, 255))
        elif emotion in ("sad", "angry"):
            d.arc((*P(hx - 34, my), *P(hx + 34, my + 40)), 200, 340, fill=mouth_dark, width=10 * k)
        elif emotion == "thinking":
            d.line([P(hx - 26, my + 10), P(hx + 30, my)], fill=mouth_dark, width=10 * k)
        else:
            d.arc((*P(hx - 32, my - 20), *P(hx + 32, my + 16)), 20, 160, fill=mouth_dark, width=10 * k)

        img = img.reduce(S)
        if flip:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        return img
