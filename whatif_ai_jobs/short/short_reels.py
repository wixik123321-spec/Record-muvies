"""Shorts в «рилс-стиле»: фото на весь экран, быстрые склейки с «ударом» камеры,
по одному слову в центре кадра (белый жирный курсив с чёрной обводкой, строчные буквы).

SHORT_ROOT=папка python short_reels.py            озвучка → Whisper → рендер → short_final.mp4
SHORT_ROOT=папка python short_reels.py --stills   кадры для проверки
SHORT_ROOT=папка python short_reels.py --cover ФОТО_СВЕРХУ ФОТО_СНИЗУ "СЛОВО1" "СЛОВО2" "подпись"
Конфиг short_config.py: LINES = [(текст, [(фото, fx, fy, зум), ...]), ...], STRESS, MOOD, SPEED.
Озвучка, выравнивание и сведение — из short.py.
"""

import json
import multiprocessing as mp
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import short as S  # noqa: E402  (загружает short_config.py из SHORT_ROOT)

R = S.R
W, H, FPS = S.W, S.H, S.FPS
BUILD = S.BUILD


@lru_cache(maxsize=6)
def source(path: str, fx: float, fy: float, zoom: float) -> np.ndarray:
    """Вырезать область 9:16 вокруг фокуса (с запасом под движение), натуральная цветокоррекция."""
    im = Image.open(path).convert("RGB")
    cw = min(im.width, im.height * 9 / 16) / zoom
    ch = cw * 16 / 9
    cx = min(max(fx * im.width, cw / 2), im.width - cw / 2)
    cy = min(max(fy * im.height, ch / 2), im.height - ch / 2)
    crop = im.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2)))
    crop = crop.resize((int(W * 1.12), int(H * 1.12)), Image.LANCZOS)
    a = np.asarray(crop).astype(np.float32) / 255
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    a = lum[..., None] + (a - lum[..., None]) * 1.12            # чуть сочнее цвет
    a = np.clip((a - 0.5) * 1.07 + 0.5, 0, 1)                    # и контраст
    hh, ww = a.shape[:2]
    yv = np.linspace(-1, 1, hh, dtype=np.float32)[:, None]
    xv = np.linspace(-1, 1, ww, dtype=np.float32)[None, :]
    a *= (1 - 0.22 * np.clip(xv ** 2 * 0.6 + yv ** 2 * 0.5 - 0.25, 0, 1))[..., None]   # мягкая виньетка
    return (np.clip(a, 0, 1) * 255).astype(np.uint8)


def shot(src: np.ndarray, u: float, dur: float, seed: int) -> np.ndarray:
    sh, sw = src.shape[:2]
    p = min(1.0, max(0.0, u / max(dur, 0.1)))
    z = 1.0 + 0.07 * p + 0.06 * max(0.0, 1 - u / 0.18) ** 2      # плавный наезд + «удар» на склейке
    vw = sw / z
    vh = vw * H / W
    dx = (np.random.default_rng(seed).uniform(-1, 1)) * (sw - vw) * 0.3 * (p - 0.5)
    cx, cy = sw / 2 + dx, sh / 2
    s = W / vw
    M = np.array([[s, 0, -(cx - vw / 2) * s], [0, s, -(cy - vh / 2) * s]], np.float32)
    return cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


@lru_cache(maxsize=64)
def word_img(word: str) -> np.ndarray:
    f = R.F("BlackItalic", 118)
    while f.getlength(word) > 980 and f.size > 60:
        f = R.F("BlackItalic", f.size - 6)
    tw = int(f.getlength(word)) + 60
    im = Image.new("RGBA", (tw, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((tw / 2 + 4, 116), word, font=f, fill=(0, 0, 0, 150), anchor="mm", stroke_width=12, stroke_fill=(0, 0, 0, 150))
    d.text((tw / 2, 110), word, font=f, fill=(255, 255, 255), anchor="mm", stroke_width=11, stroke_fill=(0, 0, 0))
    return np.asarray(im)


class Reels:
    def __init__(self):
        tm = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
        self.bounds, self.dur, self.words = tm["bounds"], tm["duration"], tm["words"]
        starts = [0.0] + [self.bounds[i][0] - 0.05 for i in range(1, len(S.LINES))]
        self.cuts = []  # (начало, конец, фото, fx, fy, зум, seed)
        for i, (_t, photos) in enumerate(S.LINES):
            a = starts[i]
            b = starts[i + 1] if i + 1 < len(S.LINES) else self.dur
            n = len(photos)
            for k, (path, fx, fy, zoom) in enumerate(photos):
                self.cuts.append((a + (b - a) * k / n, a + (b - a) * (k + 1) / n, str(path), fx, fy, zoom, i * 10 + k))

    def frame(self, t):
        c = next((c for c in self.cuts if c[0] <= t < c[1]), self.cuts[-1])
        a, b, path, fx, fy, zoom, seed = c
        fr = np.ascontiguousarray(shot(source(path, fx, fy, zoom), t - a, b - a, seed))
        # текущее слово по центру
        cur = None
        for k, w in enumerate(self.words):
            nxt = self.words[k + 1]["s"] if k + 1 < len(self.words) else w["e"] + 0.5
            if w["s"] - 0.03 <= t < min(nxt, w["e"] + 0.45):
                cur = w
                break
        if cur:
            word = re.sub(r"[^\wёЁ-]", "", cur["w"]).lower()
            if word:
                img = word_img(word)
                age = t - (cur["s"] - 0.03)
                sc = 0.86 + 0.14 * R.ease(age / 0.09)
                if sc < 0.995:
                    img = np.asarray(Image.fromarray(img).resize((max(1, int(img.shape[1] * sc)),
                                                                  max(1, int(img.shape[0] * sc))), Image.BILINEAR))
                R.blend(fr, img, (W - img.shape[1]) // 2, 1060 - img.shape[0] // 2, 1.0)
        return fr


def _chunk(job):
    cv2.setNumThreads(1)
    R.W, R.H = W, H
    r = Reels()
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                          "-pix_fmt", "yuv420p", "-threads", "1", job["out"]], stdin=subprocess.PIPE)
    for f in range(job["f0"], job["f1"]):
        p.stdin.write(r.frame(f / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return job["out"]


def cover(top, bottom, w1, w2, sub, out):
    """Обложка: две половины (фото сверху/снизу), слова в стиле роликов и подпись-плашка."""
    R.W, R.H = W, H
    canvas = np.zeros((H, W, 3), np.uint8)
    for k, spec in enumerate((top, bottom)):
        path, fx, fy = spec
        im = Image.open(path).convert("RGB")
        tw, th = W, H // 2
        sc = max(tw / im.width, th / im.height)
        im = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.LANCZOS)
        x0 = int(min(max(fx * im.width - tw / 2, 0), im.width - tw))
        y0 = int(min(max(fy * im.height - th / 2, 0), im.height - th))
        canvas[k * th:(k + 1) * th] = np.asarray(im.crop((x0, y0, x0 + tw, y0 + th)))
    img = Image.fromarray(canvas).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.rectangle((0, H // 2 - 6, W, H // 2 + 6), fill=(255, 255, 255, 255))
    for word, yc in ((w1, H // 4 + 40), (w2, 3 * H // 4 - 40)):
        f = R.F("BlackItalic", 230)
        while f.getlength(word) > 980:
            f = R.F("BlackItalic", f.size - 10)
        d.text((W / 2 + 6, yc + 8), word, font=f, fill=(0, 0, 0, 160), anchor="mm", stroke_width=16, stroke_fill=(0, 0, 0, 160))
        d.text((W / 2, yc), word, font=f, fill=(255, 255, 255), anchor="mm", stroke_width=14, stroke_fill=(0, 0, 0))
    fb = R.F("Black", 58)
    bw = d.textlength(sub, font=fb) + 70
    d.rounded_rectangle((W / 2 - bw / 2, H // 2 - 58, W / 2 + bw / 2, H // 2 + 58), 22, fill=(255, 214, 40, 255),
                        outline=(0, 0, 0, 255), width=6)
    d.text((W / 2, H // 2), sub, font=fb, fill=(10, 8, 20), anchor="mm")
    img.convert("RGB").save(out)
    print(out)


def main():
    if "--cover" in sys.argv:
        i = sys.argv.index("--cover")
        a = sys.argv[i + 1:]
        cover((a[0], float(a[1]), float(a[2])), (a[3], float(a[4]), float(a[5])), a[6], a[7], a[8], a[9])
        return
    BUILD.mkdir(exist_ok=True)
    bounds, dur = S.voice()
    words = S.align(bounds)
    (BUILD / "timing.json").write_text(json.dumps({"bounds": bounds, "duration": dur, "words": words},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    if "--stills" in sys.argv:
        r = Reels()
        for k, c in enumerate(r.cuts):
            Image.fromarray(r.frame((c[0] + c[1]) / 2)).save(BUILD / f"still_{k + 1:02d}.jpg", quality=88)
        return
    S.mix(dur)
    total = int(dur * FPS)
    step = total // 4 + 1
    jobs = [{"f0": f0, "f1": min(total, f0 + step), "out": str(BUILD / f"seg_{k}.mp4")}
            for k, f0 in enumerate(range(0, total, step))]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("spawn")) as ex:
        list(ex.map(_chunk, jobs))
    (BUILD / "list.txt").write_text("".join(f"file '{Path(j['out']).name}'\n" for j in jobs))
    out = S.HERE / "short_final.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "list.txt"),
                    "-i", str(BUILD / "mix.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(f"готово: {out} ({dur:.1f} с)", flush=True)


if __name__ == "__main__":
    main()
