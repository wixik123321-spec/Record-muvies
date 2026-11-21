"""Procedural 2.5D "plates" for a dark bedroom at night.

Each plate is a float32 RGB image in [0, 1], rendered larger than the output
frame so the camera can push in and drift. The scene is built from soft
shapes and light falloff (no textures from the internet), which gives a
moody, painterly-cinematic look. When real footage or AI-generated shots are
available, the renderer uses those instead (see ``plate`` in the story file).

All plates share one layout, so the character, lamp, mirror, clock and book
stay consistent from shot to shot.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

PW, PH = 1260, 2240  # plate size (overscan for 1080x1920 output)

WARM = np.array([1.0, 0.62, 0.30], np.float32)
COLD = np.array([0.35, 0.50, 0.85], np.float32)
PHONE = np.array([0.55, 0.70, 1.0], np.float32)
LED = np.array([1.0, 0.12, 0.08], np.float32)


def _grid():
    y, x = np.mgrid[0:PH, 0:PW].astype(np.float32)
    return x / PW, y / PH


X, Y = _grid()


def radial(cx, cy, r, power=2.0, aspect=1.0):
    d = np.sqrt(((X - cx) / aspect) ** 2 + (Y - cy) ** 2 * (PH / PW) ** 2) / r
    return np.clip(1 - d, 0, 1) ** power


def soft(mask: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(mask, (0, 0), sigma)


def poly_mask(points, blur=1.5) -> np.ndarray:
    m = np.zeros((PH, PW), np.float32)
    pts = np.array([[x * PW, y * PH] for x, y in points], np.int32)
    cv2.fillPoly(m, [pts], 1.0, lineType=cv2.LINE_AA)
    return soft(m, blur) if blur else m


def ellipse_mask(cx, cy, rx, ry, angle=0, blur=1.5) -> np.ndarray:
    m = np.zeros((PH, PW), np.float32)
    cv2.ellipse(m, (int(cx * PW), int(cy * PH)), (int(rx * PW), int(ry * PH)), angle, 0, 360, 1.0,
                -1, lineType=cv2.LINE_AA)
    return soft(m, blur) if blur else m


def rect_mask(x0, y0, x1, y1, radius=0.0, blur=1.5) -> np.ndarray:
    m = np.zeros((PH, PW), np.float32)
    p0, p1 = (int(x0 * PW), int(y0 * PH)), (int(x1 * PW), int(y1 * PH))
    if radius <= 0:
        cv2.rectangle(m, p0, p1, 1.0, -1)
    else:
        r = int(radius * PW)
        cv2.rectangle(m, (p0[0] + r, p0[1]), (p1[0] - r, p1[1]), 1.0, -1)
        cv2.rectangle(m, (p0[0], p0[1] + r), (p1[0], p1[1] - r), 1.0, -1)
        for cx, cy in ((p0[0] + r, p0[1] + r), (p1[0] - r, p0[1] + r), (p0[0] + r, p1[1] - r),
                       (p1[0] - r, p1[1] - r)):
            cv2.circle(m, (cx, cy), r, 1.0, -1, lineType=cv2.LINE_AA)
    return soft(m, blur) if blur else m


def over(img, mask, color):
    color = np.asarray(color, np.float32)
    m = mask[..., None]
    return img * (1 - m) + (color if color.ndim == 1 else color) * m


def noise(seed=0, scale=3.0, amount=0.02):
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((PH, PW)).astype(np.float32)
    return soft(n, scale) * amount * scale


# --------------------------------------------------------------------------
# the character (seen from behind, hood up)

# right half of a hooded, seated person seen from behind (units: hood width)
_PROFILE = [(0.0, 0.0), (0.22, 0.02), (0.38, 0.10), (0.48, 0.24), (0.52, 0.42), (0.50, 0.60),
            (0.45, 0.76), (0.47, 0.90), (0.62, 1.00), (0.92, 1.09), (1.22, 1.18), (1.42, 1.31),
            (1.55, 1.52), (1.61, 1.85), (1.66, 2.6), (1.70, 4.0)]


def _catmull(points, n=12):
    pts = [points[0]] + points + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (np.array(p, np.float32) for p in pts[i - 1:i + 3])
        for t in np.linspace(0, 1, n, endpoint=False):
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(points[-1], np.float32))
    return out


def figure_mask(cx=0.36, top=0.47, s=1.0, tilt=0.0) -> np.ndarray:
    """Hooded person seen from behind, as one smooth outline (pixel-true proportions)."""
    unit = 0.30 * PW * s
    right = _catmull(_PROFILE)
    left = [(-x, y) for x, y in reversed(right)]
    ang = np.deg2rad(tilt)
    pts = []
    for x, y in right + left:
        # tilt only the head part a little
        if y < 0.95 and tilt:
            x, y = x * np.cos(ang) - (y - 0.95) * np.sin(ang), x * np.sin(ang) + (y - 0.95) * np.cos(ang) + 0.95
        pts.append([cx * PW + x * unit, top * PH + y * unit])
    m = np.zeros((PH, PW), np.float32)
    cv2.fillPoly(m, [np.array(pts, np.int32)], 1.0, lineType=cv2.LINE_AA)
    return soft(m, 1.6)


def shade_figure(img, mask, key_dir=(-1, -0.3), key_color=WARM, key=0.0, phone=0.0, cold=0.08):
    """Dark hoodie: near-black fabric, rim light toward the lamp, phone glow halo."""
    fabric = np.array([0.010, 0.011, 0.016], np.float32)
    grad = (1 - Y) * 0.012
    body = fabric + grad[..., None] * np.array([0.6, 0.7, 1.0], np.float32)
    body = body + noise(5, 14, 0.0015)[..., None]
    out = img * (1 - mask[..., None]) + body * mask[..., None]
    dx, dy = int(key_dir[0] * 10), int(key_dir[1] * 10)
    shifted = np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    rim = np.clip(mask - shifted, 0, 1)
    rim = soft(rim, 3) * mask
    out += rim[..., None] * key_color * key * 1.6
    shifted_c = np.roll(mask, -8, axis=1)
    rim_c = soft(np.clip(mask - shifted_c, 0, 1), 3) * mask
    out += rim_c[..., None] * COLD * cold
    return out


# --------------------------------------------------------------------------

@dataclass
class Room:
    """Shared layout so every shot shows the same room."""
    lamp_x: float = 0.16
    mirror: tuple = (0.50, 0.10, 0.88, 0.47)   # x0, y0, x1, y1
    desk_y: float = 0.62
    clock: tuple = (0.70, 0.585, 0.88, 0.625)
    book: tuple = (0.50, 0.632, 0.66, 0.655)


ROOM = Room()


def _wall():
    base = np.array([0.035, 0.045, 0.07], np.float32)
    img = np.ones((PH, PW, 3), np.float32) * base
    img *= (0.75 + 0.35 * (1 - np.abs(X - 0.5) * 1.4))[..., None]
    img += noise(1, 8, 0.004)[..., None]
    # cold window light through blinds on the right wall
    stripes = (np.sin((Y * 30 - X * 9) * np.pi) > 0.2).astype(np.float32)
    win = soft(stripes * (X > 0.6) * (Y < 0.56) * (Y > 0.06), 9)
    win *= radial(0.95, 0.25, 0.6, 1.2)
    img += win[..., None] * COLD * 0.04
    return img


def _desk(img):
    top = ROOM.desk_y
    surface = poly_mask([(-0.05, top), (1.05, top), (1.1, top + 0.17), (-0.1, top + 0.17)], blur=1)
    wood = np.array([0.055, 0.038, 0.03], np.float32)
    grain = soft(np.sin(X * 140 + np.sin(X * 9) * 3).astype(np.float32), 2) * 0.004
    img = over(img, surface, wood + grain[..., None])
    front = poly_mask([(-0.1, top + 0.17), (1.1, top + 0.17), (1.1, 1.1), (-0.1, 1.1)], blur=1)
    img = over(img, front, np.array([0.018, 0.014, 0.014], np.float32))
    edge = soft(np.exp(-((Y - top) * PH / 2.5) ** 2), 1)
    img += edge[..., None] * np.array([0.05, 0.04, 0.035], np.float32)
    return img


def _mirror(img, reflection=None, lamp=1.0):
    x0, y0, x1, y1 = ROOM.mirror
    frame = rect_mask(x0 - 0.02, y0 - 0.012, x1 + 0.02, y1 + 0.012, radius=0.01, blur=1)
    img = over(img, frame, np.array([0.03, 0.022, 0.018], np.float32))
    glass = rect_mask(x0, y0, x1, y1, blur=1)
    inner = np.ones_like(img) * np.array([0.02, 0.026, 0.04], np.float32)
    # reflected lamp glow and window, mirrored
    inner += radial(x1 - 0.05, y1 - 0.02, 0.35, 2.5)[..., None] * WARM * 0.10 * lamp
    inner += radial(x0 + 0.04, y0 + 0.08, 0.25, 2)[..., None] * COLD * 0.04
    if reflection is not None:
        inner = reflection(inner)
    # glass sheen
    sheen = poly_mask([(x0 + 0.05, y0), (x0 + 0.14, y0), (x0 + 0.02, y1), (x0 - 0.02, y1)], blur=25)
    inner += sheen[..., None] * 0.025
    img = img * (1 - glass[..., None]) + inner * glass[..., None]
    rim = soft(rect_mask(x0, y0, x1, y1, blur=0) - rect_mask(x0 + 0.004, y0 + 0.003, x1 - 0.004,
                                                              y1 - 0.003, blur=0), 1)
    img += np.clip(rim, 0, 1)[..., None] * WARM * 0.06 * lamp
    return img


def _lamp(img, on: float):
    lx = ROOM.lamp_x
    shade = poly_mask([(lx - 0.07, 0.44), (lx + 0.07, 0.44), (lx + 0.11, 0.52), (lx - 0.11, 0.52)], blur=1.5)
    stem = rect_mask(lx - 0.006, 0.52, lx + 0.006, ROOM.desk_y + 0.025, blur=1)
    base = ellipse_mask(lx, ROOM.desk_y + 0.028, 0.065, 0.008, blur=1.5)
    metal = np.array([0.05, 0.045, 0.045], np.float32)
    img = over(img, stem, metal)
    img = over(img, base, metal * 1.2)
    shade_col = np.array([0.08, 0.06, 0.05], np.float32) + WARM * 0.75 * on
    img = over(img, shade, shade_col)
    if on > 0:
        glow = radial(lx, 0.52, 0.55, 2.2) * 0.55 + radial(lx, 0.52, 0.18, 1.5) * 0.6
        pool = radial(lx + 0.05, ROOM.desk_y + 0.04, 0.45, 1.8, aspect=1.8) * (Y > ROOM.desk_y)
        up = radial(lx, 0.30, 0.4, 2.0) * (Y < 0.44) * 0.35
        img = img * (1 + (glow + pool * 1.6 + up)[..., None] * WARM * 3.2 * on)
        img += (glow * 0.5 + pool * 0.5 + up * 0.3)[..., None] * WARM * 0.12 * on
        hot = ellipse_mask(lx, 0.522, 0.1, 0.006, blur=4)
        img += hot[..., None] * WARM * 1.4 * on
    return img


def _clock(img, lit=1.0):
    x0, y0, x1, y1 = ROOM.clock
    body = rect_mask(x0, y0, x1, y1, radius=0.008, blur=1)
    img = over(img, body, np.array([0.012, 0.012, 0.014], np.float32))
    digits = np.zeros((PH, PW), np.float32)
    cx, cy = int((x0 + x1) / 2 * PW), int((y0 + y1) / 2 * PH)
    cv2.putText(digits, "23:50", (cx - 82, cy + 18), cv2.FONT_HERSHEY_DUPLEX, 1.5, 1.0, 4, cv2.LINE_AA)
    img += soft(digits, 1)[..., None] * LED * 0.95 * lit
    img += soft(digits, 14)[..., None] * LED * 0.9 * lit
    return img


def _book(img):
    x0, y0, x1, y1 = ROOM.book
    cover = poly_mask([(x0, y0), (x1, y0), (x1 + 0.01, y1), (x0 - 0.01, y1)], blur=1)
    img = over(img, cover, np.array([0.07, 0.025, 0.025], np.float32))
    pages = rect_mask(x0 - 0.008, y1, x1 + 0.008, y1 + 0.006, blur=1)
    return over(img, pages, np.array([0.12, 0.11, 0.095], np.float32))


def room_plate(lamp: float = 1.0, phone_glow: float = 0.6, figure: bool = True,
               mirror_reflection=None) -> np.ndarray:
    img = _wall()
    img = _mirror(img, mirror_reflection, lamp=max(lamp, 0.15))
    img = _desk(img)
    img = _book(img)
    img = _clock(img)
    img = _lamp(img, lamp)
    # ambient level: almost black when the lamp is off
    img *= 0.28 + 0.72 * lamp
    if figure:
        fm = figure_mask()
        halo = radial(0.36, 0.50, 0.32, 2.2) * phone_glow
        img += halo[..., None] * PHONE * 0.10
        img = shade_figure(img, fm, key=lamp * 0.9, cold=0.05 + 0.05 * phone_glow)
    return np.clip(img, 0, 1)


def dark_room_plate(phone_glow: float = 1.0) -> np.ndarray:
    return room_plate(lamp=0.0, phone_glow=phone_glow)


def behind_plate(lamp: float = 1.0) -> np.ndarray:
    """The room behind the character: dark door ajar, edge of the bed. Empty."""
    img = _wall()[:, ::-1].copy()
    door = rect_mask(0.30, 0.18, 0.62, 0.86, blur=1)
    img = over(img, door, np.array([0.03, 0.03, 0.035], np.float32))
    gap = rect_mask(0.555, 0.19, 0.60, 0.85, blur=2)
    img = over(img, gap, np.array([0.0, 0.0, 0.0], np.float32))
    bed = poly_mask([(-0.1, 0.72), (0.28, 0.70), (0.32, 1.1), (-0.1, 1.1)], blur=2)
    img = over(img, bed, np.array([0.05, 0.055, 0.07], np.float32))
    floor = poly_mask([(-0.1, 0.86), (1.1, 0.86), (1.1, 1.1), (-0.1, 1.1)], blur=3)
    img = over(img, floor * 0.8, np.array([0.025, 0.02, 0.02], np.float32))
    img *= (1 + radial(0.05, 0.6, 0.9, 2)[..., None] * WARM * 1.6 * lamp)
    return np.clip(img * (0.3 + 0.7 * lamp), 0, 1)


def clock_plate() -> np.ndarray:
    img = np.ones((PH, PW, 3), np.float32) * np.array([0.01, 0.012, 0.02], np.float32)
    img += radial(0.15, 0.35, 0.5, 2)[..., None] * WARM * 0.08  # lamp bokeh behind
    for bx, by, br in ((0.12, 0.30, 0.06), (0.25, 0.22, 0.035), (0.85, 0.18, 0.04)):
        img += ellipse_mask(bx, by, br, br * PW / PH, blur=18)[..., None] * WARM * 0.08
    desk = poly_mask([(-0.1, 0.62), (1.1, 0.62), (1.1, 1.1), (-0.1, 1.1)], blur=2)
    img = over(img, desk, np.array([0.03, 0.022, 0.018], np.float32))
    body = rect_mask(0.08, 0.40, 0.92, 0.63, radius=0.04, blur=1.5)
    img = over(img, body, np.array([0.012, 0.012, 0.015], np.float32))
    face = rect_mask(0.12, 0.43, 0.88, 0.60, radius=0.02, blur=1.5)
    img = over(img, face, np.array([0.02, 0.006, 0.006], np.float32))
    digits = np.zeros((PH, PW), np.float32)
    cv2.putText(digits, "23:50", (int(0.155 * PW), int(0.565 * PH)), cv2.FONT_HERSHEY_DUPLEX,
                6.8, 1.0, 22, cv2.LINE_AA)
    img += soft(digits, 2)[..., None] * LED * 1.1
    img += soft(digits, 30)[..., None] * LED * 0.7
    # reflection on glossy desk
    refl = np.flipud(soft(digits, 10))
    shift = int((0.565 * 2 - 1.0) * PH) + int(0.11 * PH)
    refl = np.roll(refl, shift, axis=0) * (Y > 0.63)
    img += refl[..., None] * LED * 0.12
    return np.clip(img, 0, 1)


def desk_closeup_plates() -> tuple[np.ndarray, np.ndarray]:
    """(base with key, RGBA book layer) for the key-under-the-book shot."""
    img = np.ones((PH, PW, 3), np.float32) * np.array([0.05, 0.034, 0.026], np.float32)
    grain = soft(np.sin(X * 160 + np.sin(Y * 6) * 2.5).astype(np.float32), 3) * 0.5 + 0.5
    img += (grain * 0.008)[..., None] * np.array([1, 0.7, 0.5], np.float32)
    img *= (1 + radial(0.1, 0.1, 1.1, 1.6)[..., None] * WARM * 2.0)
    # the key
    key = np.zeros((PH, PW), np.float32)
    cx, cy = int(0.42 * PW), int(0.55 * PH)
    cv2.circle(key, (cx, cy), 70, 1.0, 26, cv2.LINE_AA)
    cv2.rectangle(key, (cx + 60, cy - 16), (cx + 420, cy + 16), 1.0, -1)
    for i, h in enumerate((60, 40, 70, 45)):
        x = cx + 260 + i * 38
        cv2.rectangle(key, (x, cy + 10), (x + 26, cy + h), 1.0, -1)
    key = soft(key, 1.5)
    metal = np.array([0.55, 0.45, 0.30], np.float32)
    shine = np.clip(np.sin(X * 30 + Y * 12) * 0.5 + 0.6, 0, 1)
    shadow = soft(np.roll(np.roll(key, 14, 0), 10, 1), 10)
    img *= (1 - shadow[..., None] * 0.6)
    img = img * (1 - key[..., None]) + key[..., None] * metal * (0.5 + 0.7 * shine[..., None]) * 0.7
    # book layer
    book = np.zeros((PH, PW, 4), np.float32)
    bm = poly_mask([(0.12, 0.33), (0.92, 0.30), (0.98, 0.78), (0.08, 0.80)], blur=1.5)
    col = np.array([0.045, 0.018, 0.016], np.float32) + noise(7, 2, 0.01)[..., None]
    col *= (1 + radial(0.2, 0.3, 0.9, 1.5)[..., None] * 2.5)
    pages = poly_mask([(0.08, 0.80), (0.98, 0.78), (0.98, 0.80), (0.08, 0.825)], blur=1)
    col = col * (1 - pages[..., None]) + pages[..., None] * np.array([0.20, 0.18, 0.15], np.float32)
    book[..., :3] = col
    book[..., 3] = np.clip(bm + pages, 0, 1)
    return np.clip(img, 0, 1), book


def mirror_plates() -> tuple[np.ndarray, np.ndarray]:
    """(room toward the mirror with the real character in front, RGBA reflection layer).

    The reflection is the wrong one: it shows the *back* of the character's
    head (hood, no face) even though the character is facing the mirror.
    """
    img = _wall()
    x0, y0, x1, y1 = 0.18, 0.08, 0.86, 0.80
    frame = rect_mask(x0 - 0.03, y0 - 0.017, x1 + 0.03, y1 + 0.017, radius=0.01, blur=1)
    img = over(img, frame, np.array([0.035, 0.025, 0.02], np.float32))
    glass = rect_mask(x0, y0, x1, y1, blur=1)
    inner = np.ones_like(img) * np.array([0.022, 0.028, 0.045], np.float32)
    inner += radial(0.25, 0.6, 0.55, 2.0)[..., None] * WARM * 0.12  # lamp seen in the mirror
    inner += noise(3, 10, 0.004)[..., None]
    img = img * (1 - glass[..., None]) + inner * glass[..., None]
    img *= (1 + radial(0.0, 0.7, 0.9, 1.8)[..., None] * WARM * 1.8)
    # the real character, close to camera, bottom-left, facing the mirror
    fm = figure_mask(cx=0.30, top=0.62, s=1.25)
    img = shade_figure(img, fm, key=0.8)
    # reflection layer: the same hooded back, smaller (further away), inside the glass
    refl = np.zeros((PH, PW, 4), np.float32)
    fade = np.clip((0.78 - Y) / 0.22, 0, 1)
    rm = figure_mask(cx=0.56, top=0.30, s=0.70) * glass * fade
    shaded = shade_figure(np.zeros_like(img), rm, key=0.55, cold=0.05)
    shaded = shaded * 0.85 + inner * 0.15
    refl[..., :3] = shaded
    refl[..., 3] = rm
    return np.clip(img, 0, 1), refl


def mirror_glass_box() -> tuple[float, float, float, float]:
    return 0.18, 0.08, 0.86, 0.80
