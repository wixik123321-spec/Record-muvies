"""Сборка кадра: камера, параллакс, персонаж, предметы, крупный текст, частицы, переходы.

Работает в двух форматах: вертикальные Shorts (1080x1920) и обычные видео
YouTube (1920x1080) с главами. Каждая сцена — отдельный «план» со своим фоном
и движением камеры; внутри сцены картинка меняется постоянно (наезд/панорама,
появление предметов с отскоком, мимика и губы персонажа), между сценами —
переход (fade / slide / zoom / flash / whip). В длинных видео добавляются
анимированные карточки (титул, главы, конечная заставка), плашка текущей
главы и полоса прогресса по главам.

Слои фонов создаются лениво и хранятся в небольшом кэше (uint8), поэтому даже
видео на десятки сцен не требует много памяти.
"""

from __future__ import annotations

import math
import random
import zlib
from collections import OrderedDict

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .art.backgrounds import palette, render_layers
from .art.character import Character
from .art.props import prop_image
from .utils import font

W, H = 1080, 1920
OVER = 1.16                          # запас фона под движение камеры
LW, LH = int(W * OVER) // 2 * 2, int(H * OVER) // 2 * 2
PARALLAX = {"far": 0.35, "mid": 0.65, "action": 0.85, "near": 1.0}
TRANS = 0.36                          # длительность перехода, с


def configure(width: int, height: int) -> None:
    """Задать размер кадра (до создания Animator)."""
    global W, H, LW, LH
    W, H = int(width), int(height)
    LW, LH = int(W * OVER) // 2 * 2, int(H * OVER) // 2 * 2
    Animator._glow_cache = None


def landscape() -> bool:
    return W > H


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def back_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _rgba(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"), np.float32) / 255


def _u8(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"), np.uint8)


def _comp(dst: np.ndarray, layer: np.ndarray) -> np.ndarray:
    a = layer[..., 3:4]
    return dst * (1 - a) + layer[..., :3] * a


def _wrap(text: str, f, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if f.getlength(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def layout() -> dict:
    """Положение персонажа, предметов и надписей для текущего формата."""
    if landscape():
        return {
            "char_x": {"left": W * 0.22, "right": W * 0.78, "center": W * 0.5},
            "prop_x": {"left": W * 0.70, "right": W * 0.30, "center": W * 0.5},
            "char_scale": H / 1080 * 0.92,
            "char_cy": H - 500 * (H / 1080 * 0.92) + H * 0.06,
            "slots": lambda side, px: [(px, H * 0.46), (px + (-W * 0.13 if side == "left" else W * 0.13), H * 0.70),
                                       (px + (W * 0.12 if side == "left" else -W * 0.12), H * 0.30)],
            "slots_nochar": [(W * 0.5, H * 0.52), (W * 0.24, H * 0.46), (W * 0.76, H * 0.50)],
            "prop_sizes": (int(H * 0.31), int(H * 0.24)),
            "big_y": H * 0.2, "big_size": int(H * 0.15),
        }
    return {
        "char_x": {"left": 320, "right": 760, "center": 540},
        "prop_x": {"left": 760, "right": 320, "center": 540},
        "char_scale": 1.12,
        "char_cy": H - 640,
        "slots": lambda side, px: [(px, 700), (px + (-150 if side == "left" else 150), 1000), (px, 400)],
        "slots_nochar": [(540, 860), (270, 560), (810, 600)],
        "prop_sizes": (380, 290),
        "big_y": 360, "big_size": 190,
    }


class SceneArt:
    """Предметы, крупный текст и частицы одной сцены (фон — общий кэш Animator.layers)."""

    def __init__(self, scene, idx: int, script):
        self.s, self.idx = scene, idx
        self.pal = palette(scene.setting)
        lay = layout()
        acc = "#%02X%02X%02X" % self.pal[5]
        big, small = lay["prop_sizes"]
        self.props = [_rgba(prop_image(p, big if i == 0 else small, acc)) for i, p in enumerate(scene.props)]
        self.big = self._big_text(scene.big_text, self.pal[5], lay["big_size"]) if scene.big_text else None
        rnd = random.Random(idx)
        self.particles = [(rnd.random(), rnd.random(), rnd.uniform(2, 6), rnd.uniform(0.2, 1.0), rnd.random())
                          for _ in range(46 if not landscape() else 60)]
        self.card = None
        if scene.card:
            self.card = CardArt(scene, script, self.pal)

    @staticmethod
    def _big_text(text: str, color, size: int) -> np.ndarray:
        f = font("Inter:style=Black", size)
        while f.getlength(text.upper()) > W - 200 and size > 60:
            size -= 8
            f = font("Inter:style=Black", size)
        img = Image.new("RGBA", (W, int(size * 1.5)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((W / 2 + 8, img.height / 2 + 10), text.upper(), font=f, anchor="mm", fill=(0, 0, 0, 120))
        d.text((W / 2, img.height / 2), text.upper(), font=f, anchor="mm", fill=tuple(color),
               stroke_width=max(6, size // 16), stroke_fill=(20, 14, 34))
        return _rgba(img)


class CardArt:
    """Текстовые слои титульной карточки, карточки главы или конечной заставки."""

    def __init__(self, scene, script, pal):
        self.kind = scene.card
        acc = tuple(pal[5])
        u = H / 1080 if landscape() else W / 1080
        self.layers: list[tuple[np.ndarray, float, float, float]] = []  # (rgba, cx, cy, delay)
        if self.kind == "chapter" and 0 <= scene.chapter < len(script.chapters):
            title = script.chapters[scene.chapter]["title"]
            num = f"{scene.chapter + 1:02d}"
            fn = font("Inter:style=Black", int(330 * u))
            img = Image.new("RGBA", (int(fn.getlength(num) + 60), int(400 * u)), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((30, img.height / 2), num, font=fn, anchor="lm", fill=acc + (70,),
                                     stroke_width=int(6 * u), stroke_fill=acc + (255,))
            self.layers.append((_rgba(img), W * (0.30 if landscape() else 0.5), H * (0.40 if landscape() else 0.34), 0.0))
            fl = font("Inter:style=Bold", int(46 * u))
            img = Image.new("RGBA", (W, int(80 * u)), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((W / 2, img.height / 2), f"ГЛАВА {scene.chapter + 1}", font=fl, anchor="mm",
                                     fill=acc + (255,))
            self.layers.append((_rgba(img), W / 2, H * (0.30 if landscape() else 0.45), 0.15))
            self.layers.append((self._title(title.upper(), int(112 * u), (255, 255, 255)), W / 2,
                                H * (0.56 if landscape() else 0.56), 0.3))
        elif self.kind == "title":
            if script.channel:
                fl = font("Inter:style=Bold", int(44 * u))
                img = Image.new("RGBA", (W, int(80 * u)), (0, 0, 0, 0))
                ImageDraw.Draw(img).text((W / 2, img.height / 2), script.channel.upper(), font=fl, anchor="mm",
                                         fill=acc + (255,))
                self.layers.append((_rgba(img), W / 2, H * 0.28, 0.0))
            self.layers.append((self._title(script.title.upper(), int(104 * u), (255, 255, 255)), W / 2, H * 0.5, 0.2))
        elif self.kind == "end":
            self.layers.append((self._title("СПАСИБО ЗА ПРОСМОТР!", int(86 * u), (255, 255, 255)), W / 2, H * 0.13, 0.0))
            if landscape():
                # места под элементы конечной заставки YouTube: два видео и кнопка подписки
                bw, bh = int(W * 0.31), int(W * 0.31 * 9 / 16)
                for cx in (W * 0.25, W * 0.75):
                    img = Image.new("RGBA", (bw + 8, bh + 60), (0, 0, 0, 0))
                    d = ImageDraw.Draw(img)
                    d.rounded_rectangle((4, 4, bw + 4, bh + 4), radius=int(24 * u), outline=acc + (255,),
                                        width=int(6 * u), fill=(10, 10, 20, 120))
                    d.text((bw / 2, bh / 2), "СМОТРИ ДАЛЬШЕ", font=font("Inter:style=Bold", int(40 * u)),
                           anchor="mm", fill=(255, 255, 255, 200))
                    self.layers.append((_rgba(img), cx, H * 0.50, 0.25))
            r = int(H * 0.1 if landscape() else W * 0.14)
            img = Image.new("RGBA", (r * 6, r * 2 + 20), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.ellipse((r * 3 - r, 10, r * 3 + r, 10 + 2 * r), outline=(255, 255, 255, 230), width=int(6 * u))
            d.rounded_rectangle((r * 0.6, r * 0.55 + 10, r * 5.4, r * 1.45 + 10), radius=int(r * 0.45),
                                fill=(230, 33, 23, 255))
            d.text((r * 3, r + 10), "ПОДПИСАТЬСЯ", font=font("Inter:style=Black", int(r * 0.42)), anchor="mm",
                   fill=(255, 255, 255, 255))
            self.layers.append((_rgba(img), W / 2, H * (0.84 if landscape() else 0.62), 0.45))

    @staticmethod
    def _title(text: str, size: int, color) -> np.ndarray:
        f = font("Inter:style=Black", size)
        lines = _wrap(text, f, int(W * 0.84))
        lh = int(size * 1.12)
        img = Image.new("RGBA", (W, lh * len(lines) + 40), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for i, ln in enumerate(lines):
            y = 20 + i * lh + lh / 2
            d.text((W / 2 + 6, y + 8), ln, font=f, anchor="mm", fill=(0, 0, 0, 130))
            d.text((W / 2, y), ln, font=f, anchor="mm", fill=color + (255,), stroke_width=max(4, size // 18),
                   stroke_fill=(16, 12, 30, 255))
        return _rgba(img)


class Animator:
    _glow_cache = None

    def __init__(self, script, cfg, voice_env: np.ndarray, env_fps: int, images: dict | None = None):
        self.script, self.cfg = script, cfg
        self.env, self.env_fps = voice_env, env_fps
        self.images = images or {}
        ch = cfg.visuals.character
        self.char = Character(ch.skin, ch.hair, ch.shirt, ch.pants)
        self.lay = layout()
        self._art: OrderedDict = OrderedDict()
        self._layers: OrderedDict = OrderedDict()
        self.duration = script.scenes[-1].end if script.scenes else 0.0
        self.chapter_ui = script.format == "long" and bool(script.chapters)
        self._pills: dict = {}
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((x - W / 2) / (W * 0.75)) ** 2 + ((y - H / 2) / (H * 0.7)) ** 2)
        self.vignette = np.clip(1.12 - d ** 2 * 0.55, 0.45, 1.0)[..., None].astype(np.float32)
        rng = np.random.default_rng(1)
        amt = float(cfg.visuals.film_grain) / 255
        self.grain = [rng.normal(0, amt, (H // 2, W // 2)).astype(np.float32) for _ in range(6)] if amt else []

    # -------------------------------------------------------------- caches
    def art(self, i: int) -> SceneArt:
        if i in self._art:
            self._art.move_to_end(i)
            return self._art[i]
        a = SceneArt(self.script.scenes[i], i, self.script)
        self._art[i] = a
        while len(self._art) > 6:
            self._art.popitem(last=False)
        return a

    def layers(self, i: int) -> dict:
        sc = self.script.scenes[i]
        if i in self.images:
            key = ("img", i)
        elif self.script.format == "long":
            key = (sc.setting, sc.chapter)       # одна глава — один «декор» для каждого места
        else:
            key = (sc.setting, i)
        if key in self._layers:
            self._layers.move_to_end(key)
            return self._layers[key]
        if key[0] == "img":
            bg = self.images[i].convert("RGBA")
            scale = max(LW / bg.width, LH / bg.height)
            bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1), Image.LANCZOS)
            x0, y0 = (bg.width - LW) // 2, (bg.height - LH) // 2
            lay = {"far": _u8(bg.crop((x0, y0, x0 + LW, y0 + LH)))}
        else:
            seed = (zlib.crc32(repr(key).encode()) % 997) if self.script.format == "long" else i * 7 + 3
            imgs = render_layers(sc.setting, LW, LH, seed=seed)
            lay = {k: _u8(v) for k, v in imgs.items()}
        self._layers[key] = lay
        while len(self._layers) > 4:
            self._layers.popitem(last=False)
        return lay

    # -------------------------------------------------------------- camera
    def camera(self, scene, k: float, t: float):
        cam = scene.camera
        z0, z1, dx, dy = 1.0, 1.0, 0.0, 0.0
        u = min(W, H) / 1080
        if cam == "zoom_in":
            z0, z1 = 1.0, 1.13
        elif cam == "zoom_out":
            z0, z1 = 1.14, 1.0
        elif cam == "pan_left":
            z0 = z1 = 1.06
            dx = 70 * u
        elif cam == "pan_right":
            z0 = z1 = 1.06
            dx = -70 * u
        elif cam == "push_up":
            z0, z1, dy = 1.04, 1.1, 60 * u
        e = ease(k)
        z = z0 + (z1 - z0) * e
        ox, oy = dx * (e - 0.5) * 2, dy * (e - 0.5) * 2
        if cam == "shake" or (scene.sfx == "boom" and k < 0.25):
            amp = (14 * (1 - k * 4) if scene.sfx == "boom" else 6) * u
            ox += math.sin(t * 61) * amp
            oy += math.cos(t * 47) * amp
        ox += math.sin(t * 0.8) * 5 * u
        oy += math.cos(t * 0.6) * 4 * u
        return z, ox, oy

    @staticmethod
    def _warp(layer: np.ndarray, z: float, ox: float, oy: float, factor: float) -> np.ndarray:
        zz = 1 + (z - 1) * factor
        s = 1.0 / zz
        lh, lw = layer.shape[:2]
        cx, cy = lw / 2 - ox * factor, lh / 2 - oy * factor
        M = np.float32([[s, 0, cx - s * W / 2], [0, s, cy - s * H / 2]])
        out = cv2.warpAffine(layer, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REPLICATE)
        return out.astype(np.float32) * (1 / 255)

    def _place(self, frame, img: np.ndarray, cx: float, cy: float, scale: float = 1.0, angle: float = 0.0,
               z=1.0, ox=0.0, oy=0.0, alpha: float = 1.0):
        """Положить RGBA-картинку центром в (cx, cy) экрана с учётом камеры (план «action»)."""
        f = PARALLAX["action"]
        zz = 1 + (z - 1) * f
        h, w = img.shape[:2]
        sc = scale * zz
        px = W / 2 + (cx - W / 2) * zz + ox * f
        py = H / 2 + (cy - H / 2) * zz + oy * f
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, sc)
        M[0, 2] += px - w / 2
        M[1, 2] += py - h / 2
        x0 = int(max(0, px - w * sc * 0.8))
        x1 = int(min(W, px + w * sc * 0.8))
        y0 = int(max(0, py - h * sc * 0.8))
        y1 = int(min(H, py + h * sc * 0.8))
        if x1 <= x0 or y1 <= y0:
            return frame
        M[0, 2] -= x0
        M[1, 2] -= y0
        warped = cv2.warpAffine(img, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        if alpha < 1:
            warped[..., 3] *= alpha
        frame[y0:y1, x0:x1] = _comp(frame[y0:y1, x0:x1], warped)
        return frame

    def talk_level(self, t: float) -> float:
        i = int(t * self.env_fps)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0

    # -------------------------------------------------------------- scene frame
    def scene_frame(self, i: int, t: float) -> np.ndarray:
        sc, art = self.script.scenes[i], self.art(i)
        lay = self.layers(i)
        dur = max(0.01, sc.end - sc.start)
        lt = t - sc.start
        k = lt / dur
        if art.card is not None:
            return self._card_frame(sc, art, lay, lt, k, t)
        z, ox, oy = self.camera(sc, k, t)
        frame = self._warp(lay["far"], z, ox, oy, PARALLAX["far"])[..., :3].copy()
        if "mid" in lay:
            frame = _comp(frame, self._warp(lay["mid"], z, ox, oy, PARALLAX["mid"]))
        light = np.array(art.pal[6], np.float32) / 255
        frame += self._glow_mask() * light * (0.10 + 0.03 * math.sin(t * 1.7))

        L = self.lay
        side = sc.character_side
        char_x, prop_x = L["char_x"][side], L["prop_x"][side]
        has_char = sc.character_emotion is not None and i not in self.images

        if art.big is not None:
            a = back_out((lt - 0.15) / 0.35)
            if a > 0:  # крупный текст в экранных координатах: камера не должна его обрезать
                frame = self._place(frame, art.big, W / 2, L["big_y"] + math.sin(t * 2) * 6, 0.6 + 0.4 * a,
                                    alpha=min(1, a))
        slots = L["slots"](side, prop_x) if has_char else L["slots_nochar"]
        for j, img in enumerate(art.props):
            a = back_out((lt - 0.25 - j * 0.35) / 0.45)
            if a <= 0:
                continue
            x, y = slots[j]
            bob = math.sin(t * 2.4 + j) * 14
            ang = math.sin(t * 1.8 + j * 2) * 6
            sc_ = (1.35 if not has_char and j == 0 else 1.0) * a
            frame = self._place(frame, img, x, y + bob, sc_, ang, z, ox, oy, min(1, a * 1.5))
        if "near" in lay:
            frame = _comp(frame, self._warp(lay["near"], z, ox, oy, PARALLAX["near"]))
        if has_char:
            look = 1.0 if side == "left" else (-1.0 if side == "right" else 0.0)
            img = self.char.draw(t, sc.character_emotion, sc.character_pose, self.talk_level(t), look,
                                 flip=(side == "right"))
            prev = self.script.scenes[i - 1] if i > 0 else None
            enter = ease(lt / 0.3) if prev is None or prev.character_emotion is None or prev.card else 1.0
            cy = L["char_cy"] + (1 - enter) * H * 0.16
            frame = self._place(frame, _rgba(img), char_x, cy, L["char_scale"], 0, z, ox, oy)
        if self.cfg.visuals.particles:
            frame = self._particles(frame, sc.setting, art, t)
        return frame

    def _card_frame(self, sc, art, lay, lt, k, t):
        z = 1.0 + 0.06 * ease(k)
        frame = self._warp(lay["far"], z, 0, 0, 1.0)[..., :3] * 0.45
        accent = np.array(art.pal[5], np.float32) / 255
        frame += self._glow_mask() * accent * 0.25
        frame = self._particles(frame, "space", art, t)
        for j, (img, cx, cy, delay) in enumerate(art.card.layers):
            a = back_out((lt - delay) / 0.5)
            if a <= 0:
                continue
            dx = (1 - min(1, a)) * (-W * 0.08 if j == 0 and sc.card == "chapter" else 0)
            dy = (1 - min(1, a)) * H * 0.05
            frame = self._place(frame, img, cx + dx, cy + dy + math.sin(t * 1.5 + j) * 4, 0.9 + 0.1 * min(1, a),
                                alpha=min(1.0, a))
        if sc.card == "chapter":  # растущая линия под названием главы
            u = H / 1080 if landscape() else W / 1080
            w = int(W * 0.5 * ease((lt - 0.45) / 0.6))
            y = int(H * (0.67 if landscape() else 0.64))
            if w > 2:
                frame[y:y + int(8 * u), W // 2 - w // 2:W // 2 + w // 2] = accent
        return frame

    def _glow_mask(self):
        if Animator._glow_cache is None or Animator._glow_cache.shape[:2] != (H, W):
            y, x = np.mgrid[0:H, 0:W].astype(np.float32)
            d = np.sqrt(((x - W * 0.5) / W) ** 2 + ((y - H * 0.25) / H) ** 2)
            Animator._glow_cache = np.clip(1 - d * 1.8, 0, 1)[..., None] ** 2
        return Animator._glow_cache

    def _particles(self, frame, setting, art, t):
        overlay = np.zeros((H, W), np.float32)
        kind = {"underwater": "bubble", "space": "star", "night_city": "star", "brain": "spark",
                "forest": "firefly", "lab": "spark"}.get(setting, "dust")
        for (px, py, r, sp, ph) in art.particles:
            if kind == "bubble":
                x, y = px * W + math.sin(t * 2 + ph * 6) * 20, (py - t * sp * 0.08) % 1.0 * H
                cv2.circle(overlay, (int(x), int(y)), int(r * 2), 0.5, 2, cv2.LINE_AA)
            elif kind == "star":
                x, y = px * W, py * H * 0.7
                a = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * 3 * sp + ph * 6))
                cv2.circle(overlay, (int(x), int(y)), int(r * 0.6), a, -1, cv2.LINE_AA)
            else:
                x = (px * W + math.sin(t * sp + ph * 6) * 40) % W
                y = (py * H - t * sp * 25) % H
                a = 0.25 + 0.35 * (0.5 + 0.5 * math.sin(t * 2 + ph * 9))
                cv2.circle(overlay, (int(x), int(y)), int(r * 0.8), a, -1, cv2.LINE_AA)
        overlay = cv2.GaussianBlur(overlay, (0, 0), 1.2)[..., None]
        col = np.array(art.pal[6], np.float32) / 255
        return frame + overlay * col * 0.8

    # -------------------------------------------------------------- chapter UI
    def _pill(self, ch: int) -> np.ndarray:
        if ch not in self._pills:
            u = H / 1080
            f = font("Inter:style=Bold", int(30 * u))
            text = f"{ch + 1:02d}  ·  {self.script.chapters[ch]['title'].upper()}"
            w = int(f.getlength(text) + 80 * u)
            img = Image.new("RGBA", (w, int(64 * u)), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w - 1, img.height - 1), radius=int(32 * u), fill=(12, 10, 24, 170))
            d.ellipse((int(22 * u), img.height / 2 - 8 * u, int(38 * u), img.height / 2 + 8 * u), fill=(255, 210, 63, 255))
            d.text((int(54 * u), img.height / 2), text, font=f, anchor="lm", fill=(255, 255, 255, 235))
            self._pills[ch] = _rgba(img)
        return self._pills[ch]

    def _chapter_ui(self, frame: np.ndarray, t: float, sc) -> np.ndarray:
        u = H / 1080
        if sc.card == "" and sc.chapter >= 0:
            pill = self._pill(sc.chapter)
            x0, y0 = int(40 * u), int(36 * u)
            h, w = pill.shape[:2]
            frame[y0:y0 + h, x0:x0 + w] = _comp(frame[y0:y0 + h, x0:x0 + w], pill)
        # полоса прогресса с делениями по главам
        bh = max(4, int(6 * u))
        frac = min(1.0, t / max(0.01, self.duration))
        frame[H - bh:H, :] = frame[H - bh:H, :] * 0.4 + np.array([0.15, 0.15, 0.2], np.float32) * 0.6
        frame[H - bh:H, :int(W * frac)] = np.array([1.0, 0.82, 0.25], np.float32)
        for s in self.script.scenes:
            if s.card == "chapter":
                x = int(W * s.start / max(0.01, self.duration))
                frame[H - bh - 2:H, max(0, x - 2):x + 2] = 0.05
        return frame

    # -------------------------------------------------------------- full frame with transitions
    def frame(self, t: float) -> np.ndarray:
        scenes = self.script.scenes
        i = next((j for j, s in enumerate(scenes) if s.start <= t < s.end), len(scenes) - 1)
        cur = self.scene_frame(i, t)
        if i > 0 and t - scenes[i].start < TRANS / 2:
            prev = self.scene_frame(i - 1, t)
            k = 0.5 + (t - scenes[i].start) / TRANS
            cur = self._transition(prev, cur, k, scenes[i].transition)
        elif i + 1 < len(scenes) and scenes[i].end - t < TRANS / 2:
            nxt = self.scene_frame(i + 1, t)
            k = 0.5 - (scenes[i].end - t) / TRANS
            cur = self._transition(cur, nxt, k, scenes[i + 1].transition)
        out = cur * self.vignette
        if self.chapter_ui:
            out = self._chapter_ui(out, t, scenes[i])
        if self.grain:
            g = self.grain[int(t * 24) % len(self.grain)]
            out = out + cv2.resize(g, (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
        return out

    @staticmethod
    def _transition(a: np.ndarray, b: np.ndarray, k: float, kind: str) -> np.ndarray:
        k = min(1.0, max(0.0, k))
        e = ease(k)
        if kind in ("slide", "whip"):
            off = int(e * W)
            out = np.empty_like(a)
            out[:, : W - off] = a[:, off:]
            out[:, W - off:] = b[:, :off]
            if kind == "whip":
                blur = int(1 + 120 * math.sin(math.pi * k))
                return cv2.blur(out, (blur, 1)) if blur > 2 else out
            return out
        if kind == "zoom":
            A = cv2.warpAffine(a, cv2.getRotationMatrix2D((W / 2, H / 2), 0, 1 + 0.25 * e), (W, H),
                               borderMode=cv2.BORDER_REFLECT)
            B = cv2.warpAffine(b, cv2.getRotationMatrix2D((W / 2, H / 2), 0, 0.85 + 0.15 * e), (W, H),
                               borderMode=cv2.BORDER_REFLECT)
            return A * (1 - e) + B * e
        if kind == "flash":
            base = a if k < 0.5 else b
            return base + (1 - abs(k - 0.5) * 2) * 0.9
        return a * (1 - e) + b * e
