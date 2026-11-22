"""Сборка кадра: камера, параллакс, персонаж, предметы, крупный текст, частицы, переходы.

Каждая сцена — отдельный «план» со своим фоном и движением камеры. Внутри
сцены картинка меняется постоянно (наезд/панорама, появление предметов с
отскоком, мимика и губы персонажа), а между сценами — переход
(fade / slide / zoom / flash / whip). Так визуальное изменение происходит
каждые 2–4 секунды.
"""

from __future__ import annotations

import math
import random

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


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def back_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    c = 1.7
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def _rgba(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGBA"), np.float32) / 255


def _comp(dst: np.ndarray, layer: np.ndarray) -> np.ndarray:
    a = layer[..., 3:4]
    return dst * (1 - a) + layer[..., :3] * a


class SceneArt:
    """Подготовленные слои одной сцены."""

    def __init__(self, scene, idx: int, cfg, external_image: Image.Image | None = None):
        self.s, self.idx = scene, idx
        self.pal = palette(scene.setting)
        if external_image is not None:
            bg = external_image.convert("RGBA")
            scale = max(LW / bg.width, LH / bg.height)
            bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1), Image.LANCZOS)
            x0, y0 = (bg.width - LW) // 2, (bg.height - LH) // 2
            self.layers = {"far": _rgba(bg.crop((x0, y0, x0 + LW, y0 + LH)))}
            self.external = True
        else:
            imgs = render_layers(scene.setting, LW, LH, seed=idx * 7 + 3)
            self.layers = {k: _rgba(v) for k, v in imgs.items()}
            self.external = False
        acc = "#%02X%02X%02X" % self.pal[5]
        self.props = [_rgba(prop_image(p, 380 if i == 0 else 290, acc)) for i, p in enumerate(scene.props)]
        self.big = None
        if scene.big_text:
            self.big = self._big_text(scene.big_text, self.pal[5])
        rnd = random.Random(idx)
        n = 46
        self.particles = [(rnd.random(), rnd.random(), rnd.uniform(2, 6), rnd.uniform(0.2, 1.0), rnd.random())
                          for _ in range(n)]

    @staticmethod
    def _big_text(text: str, color) -> np.ndarray:
        size = 190
        f = font("Inter:style=Black", size)
        while f.getlength(text.upper()) > W - 200 and size > 70:
            size -= 10
            f = font("Inter:style=Black", size)
        img = Image.new("RGBA", (W, int(size * 1.5)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.text((W / 2 + 8, img.height / 2 + 10), text.upper(), font=f, anchor="mm", fill=(0, 0, 0, 120))
        d.text((W / 2, img.height / 2), text.upper(), font=f, anchor="mm", fill=tuple(color),
               stroke_width=12, stroke_fill=(20, 14, 34))
        return _rgba(img)


class Animator:
    def __init__(self, script, cfg, voice_env: np.ndarray, env_fps: int, images: dict | None = None):
        self.script, self.cfg = script, cfg
        self.env, self.env_fps = voice_env, env_fps
        ch = cfg.visuals.character
        self.char = Character(ch.skin, ch.hair, ch.shirt, ch.pants)
        self.art = [SceneArt(s, i, cfg, (images or {}).get(i)) for i, s in enumerate(script.scenes)]
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((x - W / 2) / (W * 0.75)) ** 2 + ((y - H / 2) / (H * 0.7)) ** 2)
        self.vignette = np.clip(1.12 - d ** 2 * 0.55, 0.45, 1.0)[..., None].astype(np.float32)
        rng = np.random.default_rng(1)
        amt = float(cfg.visuals.film_grain) / 255
        self.grain = [rng.normal(0, amt, (H // 2, W // 2, 1)).astype(np.float32) for _ in range(6)] if amt else []

    # -------------------------------------------------------------- camera
    def camera(self, scene, k: float, t: float):
        cam = scene.camera
        z0, z1, dx, dy = 1.0, 1.0, 0.0, 0.0
        if cam == "zoom_in":
            z0, z1 = 1.0, 1.13
        elif cam == "zoom_out":
            z0, z1 = 1.14, 1.0
        elif cam == "pan_left":
            z0 = z1 = 1.06
            dx = 70
        elif cam == "pan_right":
            z0 = z1 = 1.06
            dx = -70
        elif cam == "push_up":
            z0, z1, dy = 1.04, 1.1, 60
        e = ease(k)
        z = z0 + (z1 - z0) * e
        ox, oy = dx * (e - 0.5) * 2, dy * (e - 0.5) * 2
        if cam == "shake" or (scene.sfx == "boom" and k < 0.25):
            amp = 14 * (1 - k * 4) if scene.sfx == "boom" else 6
            ox += math.sin(t * 61) * amp
            oy += math.cos(t * 47) * amp
        # лёгкое «дыхание» камеры
        ox += math.sin(t * 0.8) * 5
        oy += math.cos(t * 0.6) * 4
        return z, ox, oy

    def _warp(self, layer: np.ndarray, z: float, ox: float, oy: float, factor: float) -> np.ndarray:
        zz = 1 + (z - 1) * factor
        s = 1.0 / zz
        lh, lw = layer.shape[:2]
        cx, cy = lw / 2 - ox * factor, lh / 2 - oy * factor
        M = np.float32([[s, 0, cx - s * W / 2], [0, s, cy - s * H / 2]])
        return cv2.warpAffine(layer, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)

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
        sc, art = self.script.scenes[i], self.art[i]
        dur = max(0.01, sc.end - sc.start)
        lt = t - sc.start
        k = lt / dur
        z, ox, oy = self.camera(sc, k, t)
        frame = self._warp(art.layers["far"], z, ox, oy, PARALLAX["far"])[..., :3].copy()
        if "mid" in art.layers:
            frame = _comp(frame, self._warp(art.layers["mid"], z, ox, oy, PARALLAX["mid"]))
        # тёплое/цветное свечение сцены
        light = np.array(art.pal[6], np.float32) / 255
        pulse = 0.10 + 0.03 * math.sin(t * 1.7)
        frame += self._glow_mask() * light * pulse

        side = sc.character_side
        char_x = {"left": 320, "right": 760, "center": 540}[side]
        prop_x = {"left": 760, "right": 320, "center": 540}[side]
        has_char = sc.character_emotion is not None and not art.external

        # крупный текст
        if art.big is not None:
            a = back_out((lt - 0.15) / 0.35)
            if a > 0:
                # крупный текст в экранных координатах: камера не должна его обрезать
                frame = self._place(frame, art.big, W / 2, 360 + math.sin(t * 2) * 6, 0.6 + 0.4 * a,
                                    alpha=min(1, a))
        # предметы
        slots = [(prop_x, 700), (prop_x + (-150 if side == "left" else 150), 1000), (prop_x, 400)]
        if not has_char:
            slots = [(540, 860), (270, 560), (810, 600)]
        for j, img in enumerate(art.props):
            a = back_out((lt - 0.25 - j * 0.35) / 0.45)
            if a <= 0:
                continue
            x, y = slots[j]
            bob = math.sin(t * 2.4 + j) * 14
            ang = math.sin(t * 1.8 + j * 2) * 6
            sc_ = (1.35 if not has_char and j == 0 else 1.0) * a
            frame = self._place(frame, img, x, y + bob, sc_, ang, z, ox, oy, min(1, a * 1.5))
        if "near" in art.layers:
            frame = _comp(frame, self._warp(art.layers["near"], z, ox, oy, PARALLAX["near"]))
        # персонаж
        if has_char:
            look = 1.0 if side == "left" else (-1.0 if side == "right" else 0.0)
            img = self.char.draw(t, sc.character_emotion, sc.character_pose, self.talk_level(t), look,
                                 flip=(side == "right"))
            arr = _rgba(img)
            enter = ease(lt / 0.3) if i == 0 or self.script.scenes[i - 1].character_emotion is None else 1.0
            cy = H - 640 + (1 - enter) * 300
            frame = self._place(frame, arr, char_x, cy, 1.12, 0, z, ox, oy)
        if self.cfg.visuals.particles:
            frame = self._particles(frame, sc.setting, art, t)
        return frame

    _glow_cache = None

    def _glow_mask(self):
        if Animator._glow_cache is None:
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

    # -------------------------------------------------------------- full frame with transitions
    def frame(self, t: float) -> np.ndarray:
        scenes = self.script.scenes
        i = next((j for j, s in enumerate(scenes) if s.start <= t < s.end), len(scenes) - 1)
        cur = self.scene_frame(i, t)
        # переход в начале сцены i (из i-1) и в конце (в i+1)
        if i > 0 and t - scenes[i].start < TRANS / 2:
            prev = self.scene_frame(i - 1, t)
            k = 0.5 + (t - scenes[i].start) / TRANS
            cur = self._transition(prev, cur, k, scenes[i].transition)
        elif i + 1 < len(scenes) and scenes[i].end - t < TRANS / 2:
            nxt = self.scene_frame(i + 1, t)
            k = 0.5 - (scenes[i].end - t) / TRANS
            cur = self._transition(cur, nxt, k, scenes[i + 1].transition)
        out = cur * self.vignette
        if self.grain:
            g = self.grain[int(t * 24) % len(self.grain)]
            out = out + cv2.resize(g, (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
        return out

    @staticmethod
    def _transition(a: np.ndarray, b: np.ndarray, k: float, kind: str) -> np.ndarray:
        k = min(1.0, max(0.0, k))
        e = ease(k)
        if kind == "slide":
            off = int(e * W)
            out = np.empty_like(a)
            out[:, : W - off] = a[:, off:]
            out[:, W - off:] = b[:, :off]
            return out
        if kind == "whip":
            off = int(e * W)
            out = np.empty_like(a)
            out[:, : W - off] = a[:, off:]
            out[:, W - off:] = b[:, :off]
            blur = int(1 + 120 * math.sin(math.pi * k))
            return cv2.blur(out, (blur, 1)) if blur > 2 else out
        if kind == "zoom":
            s_a = 1 + 0.25 * e
            s_b = 0.85 + 0.15 * e
            A = cv2.warpAffine(a, cv2.getRotationMatrix2D((W / 2, H / 2), 0, s_a), (W, H), borderMode=cv2.BORDER_REFLECT)
            B = cv2.warpAffine(b, cv2.getRotationMatrix2D((W / 2, H / 2), 0, s_b), (W, H), borderMode=cv2.BORDER_REFLECT)
            return A * (1 - e) + B * e
        if kind == "flash":
            base = a if k < 0.5 else b
            return base + (1 - abs(k - 0.5) * 2) * 0.9
        return a * (1 - e) + b * e
