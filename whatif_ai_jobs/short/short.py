"""YouTube Shorts 9:16 (1080x1920, 30 fps): «Что если бы всем платили деньги просто так?»

python short.py          озвучка → таймкоды Whisper → рендер → сведение → short_final.mp4
python short.py --stills кадры для проверки (build/still_N.jpg)

Реальные фото (Wikimedia Commons / Flickr через Openverse, PD / CC0 / CC BY), цифры — из проверенных
источников длинного ролика (sources.md). Конец закольцован: последняя фраза-вопрос переходит в первую.
"""

from __future__ import annotations

import difflib
import json
import multiprocessing as mp
import re
import subprocess
import sys
import wave
import zlib
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
BUILD = HERE / "build"
sys.path.insert(0, str(PROJ))
sys.path.insert(0, str(PROJ.parent / "ai_shorts_ru"))
import render as R  # noqa: E402

W, H, FPS = 1080, 1920, 30
R.W, R.H = W, H                      # вспомогательные функции render.py работают в вертикальном кадре
LIB = PROJ / "assets" / "images"
OWN = HERE / "assets"
YELLOW = (255, 214, 64)

# (текст озвучки, фото, крупная надпись, подпись)
LINES = [
    ("Что если тебе каждый месяц платили бы деньги просто так?", OWN / "money_hand_0.jpg", "ДЕНЬГИ ПРОСТО ТАК?", "каждый месяц"),
    ("Без работы. Без условий.", LIB / "banknotes_1.jpg", "БЕЗ УСЛОВИЙ", "и без работы"),
    ("Это уже проверяли на реальных людях.", LIB / "crowd_0.jpg", "ЭКСПЕРИМЕНТ", "реальные люди · реальные деньги"),
    ("В Финляндии две тысячи безработных два года получали по пятьсот шестьдесят евро в месяц.",
     LIB / "helsinki_0.jpg", "560 €", "в месяц · Финляндия, 2017–2018"),
    ("Работать меньше они не стали, а стресса стало меньше.", LIB / "helsinki_1.jpg", "МЕНЬШЕ СТРЕССА", "а работы — не меньше"),
    ("В американском Стоктоне полная занятость выросла с двадцати восьми до сорока процентов.",
     LIB / "electrician_0.jpg", "28% → 40%", "полная занятость · Стоктон, США"),
    ("В Кении люди начали чаще открывать бизнес и копить.", OWN / "kenya_market_2.jpg", "+ БИЗНЕС", "Кения · GiveDirectly"),
    ("А тысяча американцев три года получали по тысяче долларов в месяц.", OWN / "dollars_0.jpg", "$1000",
     "в месяц · 3 года · 1000 человек"),
    ("И работали в среднем всего на час с небольшим в неделю меньше.", OWN / "office_worker_1.jpg", "−1,3 ЧАСА",
     "работы в неделю"),
    ("Выходит, деньги не делают нас ленивыми.", LIB / "programmer_1.jpg", "МИФ О ЛЕНИ", "не подтвердился"),
    ("А ты бы бросил работу? Пиши в комментариях.", OWN / "hammock_0.jpg", "А ТЫ?", "бросил бы работу?"),
]
KEY = ("деньг", "денег", "услови", "финлянд", "евро", "стресс", "стоктон", "процент", "кени", "бизнес",
       "доллар", "тысяч", "час", "ленив", "работ", "бросил")

PANEL = (60, 560, 960, 640)          # x, y, w, h — фото в рамке (в безопасной зоне Shorts)
XF = 0.22


# ------------------------------------------------------------------ voice + timing

def voice():
    from shorts_ru import tts
    SR = tts.SR
    eng = tts.VoskTTS("male_1", 1.04)
    parts, bounds, pos = [np.zeros(int(0.12 * SR), np.float32)], [], 0.12
    for i, (text, *_rest) in enumerate(LINES):
        x, _ = eng.synth(text, BUILD / "tmp.wav")
        x = tts.polish(x)
        bounds.append((pos, pos + len(x) / SR))
        gap = 0.0 if i == len(LINES) - 1 else 0.14
        parts += [x, np.zeros(int(gap * SR), np.float32)]
        pos += len(x) / SR + gap
    full = np.concatenate(parts + [np.zeros(int(0.35 * SR), np.float32)])
    tts._write_wav(BUILD / "voice.wav", full)
    (BUILD / "tmp.wav").unlink(missing_ok=True)
    print(f"озвучка: {len(full) / SR:.1f} с", flush=True)
    return bounds, len(full) / SR


def norm(w):
    return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


def align(bounds):
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(BUILD / "voice.wav"), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(
        audio, language="ru", word_timestamps=True, beam_size=5)
    rec = [(norm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if norm(w.word)]
    words = [(i, w) for i, (t, *_r) in enumerate(LINES) for w in t.split()]
    times = [None] * len(words)
    sm = difflib.SequenceMatcher(a=[norm(w) for _, w in words], b=[r[0] for r in rec], autojunk=False)
    for b in sm.get_matching_blocks():
        for k in range(b.size):
            times[b.a + k] = (rec[b.b + k][1], rec[b.b + k][2])
    print(f"Whisper: сопоставлено {sum(t is not None for t in times)}/{len(words)} слов", flush=True)
    out = []
    for li, (s, e) in enumerate(bounds):            # границы строк точные (из синтеза), слова — Whisper
        idx = [k for k, (i, _) in enumerate(words) if i == li]
        n = len(idx)
        for j, k in enumerate(idx):
            t = times[k]
            if t is None or not (s - 0.3 <= t[0] <= e + 0.3):
                t = (s + (e - s) * j / n, s + (e - s) * (j + 1) / n)
            out.append({"line": li, "w": words[k][1], "s": max(s, t[0]), "e": min(e + 0.05, max(t[1], t[0] + 0.08))})
    for a, b in zip(out, out[1:]):                   # монотонность
        if b["s"] < a["s"]:
            b["s"] = a["s"] + 0.02
    return out


# ------------------------------------------------------------------ visuals

@lru_cache(maxsize=4)
def background(path):
    im = Image.open(path).convert("RGB")
    sc = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1))
    l, t = (im.width - W) // 2, (im.height - H) // 2
    a = np.asarray(im.crop((l, t, l + W, t + H))).astype(np.float32)
    small = cv2.resize(a, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 6)
    a = cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR)
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    a = (a * 0.4 + lum[..., None] * 0.6) * 0.38 + np.array((10, 6, 34), np.float32)
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    a += np.exp(-((y - 0.95) / 0.25) ** 2) * np.array((70, 20, 120), np.float32) * 0.5
    return np.clip(a, 0, 255).astype(np.uint8)


@lru_cache(maxsize=4)
def panel_src(path):
    _, _, pw, ph = PANEL
    return R.graded(str(path), int(pw * 1.14), int(ph * 1.14))


@lru_cache(maxsize=1)
def panel_mask():
    _, _, pw, ph = PANEL
    m = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, pw - 1, ph - 1), 34, fill=255)
    return np.asarray(m)


def headline(d, big, sub, u, col):
    e = R.ease(u / 0.35)
    f = R.F("Black", 132)
    lines = R.wrap(f, big, 900)
    while (len(lines) > 2 or max(R.text_w(f, l) for l in lines) > 940) and f.size > 70:
        f = R.F("Black", f.size - 8)
        lines = R.wrap(f, big, 900)
    lh = int(f.size * 1.05)
    y0 = 420 - lh * (len(lines) - 1) - 40
    pop = 1.0 + 0.10 * (1 - e)
    for k, ln in enumerate(lines):
        fs = R.F("Black", max(10, int(f.size * pop)))
        d.text((W / 2, y0 + k * lh), ln, font=fs, fill=(*col, int(255 * e)), anchor="mm",
               stroke_width=6, stroke_fill=(8, 6, 22))
    es = R.ease(R.prog(u, 0.25, 0.6))
    d.text((W / 2, y0 + len(lines) * lh - lh / 2 + 52), sub, font=R.F("Bold", 44), fill=(*R.WHITE, int(235 * es)),
           anchor="mm", stroke_width=4, stroke_fill=(8, 6, 22))


class Caps:
    """Субтитры для Shorts: 1–3 слова, КАПСОМ, звучащее слово — жёлтым, ключевые — голубым."""

    def __init__(self, words):
        self.ph = []
        cur = []
        for w in words:
            if cur and (len(cur) >= 3 or w["line"] != cur[-1]["line"] or len(" ".join(x["w"] for x in cur + [w])) > 18):
                self.ph.append(cur)
                cur = []
            cur.append(w)
            if re.search(r"[.!?,]$", w["w"]):
                self.ph.append(cur)
                cur = []
        if cur:
            self.ph.append(cur)
        self.f = R.F("Black", 92)

    def draw(self, fr, t):
        for k, ph in enumerate(self.ph):
            end = self.ph[k + 1][0]["s"] if k + 1 < len(self.ph) else ph[-1]["e"] + 0.4
            if ph[0]["s"] - 0.04 <= t < min(end, ph[-1]["e"] + 0.5):
                break
        else:
            return
        words = [re.sub(r"[.,!?]$", "", w["w"]).upper() for w in ph]
        sp = R.text_w(self.f, " ")
        ws = [R.text_w(self.f, w) for w in words]
        lw = sum(ws) + sp * (len(ws) - 1)
        scale = min(1.0, 920 / lw)
        f = R.F("Black", int(92 * scale))
        ws = [R.text_w(f, w) for w in words]
        lw = sum(ws) + sp * scale * (len(ws) - 1)
        im = Image.new("RGBA", (W, 170), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        x = (W - lw) / 2
        for w, wd, src in zip(words, ws, ph):
            n = norm(src["w"])
            col = YELLOW if src["s"] - 0.03 <= t < src["e"] + 0.05 else (
                R.KW if any(n.startswith(k) for k in KEY) or re.search(r"\d", w) else R.WHITE)
            dr.text((x + 4, 58), w, font=f, fill=(0, 0, 0, 170))
            dr.text((x, 52), w, font=f, fill=col, stroke_width=7, stroke_fill=(6, 6, 18))
            x += wd + sp * scale
        age = t - (ph[0]["s"] - 0.04)
        s = 0.86 + 0.14 * R.ease(age / 0.12)
        if s < 0.995:
            im = im.resize((int(W * s), int(170 * s)), Image.BILINEAR)
        R.blend(fr, np.asarray(im), (W - im.width) // 2, 1395 - im.height // 2, R.clip01(age / 0.08))


class Short:
    def __init__(self):
        tm = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
        self.bounds, self.dur, self.words = tm["bounds"], tm["duration"], tm["words"]
        self.starts = [0.0] + [self.bounds[i][0] - 0.06 for i in range(1, len(LINES))]
        self.caps = Caps(self.words)

    def line_frame(self, i, t):
        text, path, big, sub = LINES[i]
        u = t - self.starts[i]
        end = self.starts[i + 1] if i + 1 < len(LINES) else self.dur
        dur = end - self.starts[i]
        fr = background(str(path)).copy()
        x, y, pw, ph = PANEL
        punch = 1 + 0.035 * (1 - R.ease(u / 0.3))       # лёгкий «удар» камеры на смене кадра
        img = R.kenburns(panel_src(str(path)), u, dur, zlib.crc32(f"s{i}".encode()), pw, ph)
        if punch > 1.001:
            M = cv2.getRotationMatrix2D((pw / 2, ph / 2), 0, punch)
            img = cv2.warpAffine(img, M, (pw, ph), borderMode=cv2.BORDER_REFLECT)
        R.blend(fr, np.dstack([img, panel_mask()]), x, y)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        col = R.RED if i in (0, 10) else (R.GREEN if big.startswith("+") or "→" in big else R.CYAN)
        d.rounded_rectangle((x - 5, y - 5, x + pw + 5, y + ph + 5), 38, outline=(*col, 230), width=5)
        headline(d, big, sub, u, col if i not in (0, 10) else R.WHITE)
        if i == 0:   # плашка «ЧТО ЕСЛИ?»
            e = R.ease(u / 0.3)
            d.rounded_rectangle((x + 26, y + 26, x + 26 + 330, y + 26 + 72), 14, fill=(*YELLOW, int(255 * e)))
            d.text((x + 26 + 165, y + 62), "ЧТО ЕСЛИ?", font=R.F("Black", 46), fill=(10, 8, 20, int(255 * e)), anchor="mm")
        return R.compose(fr, lay, glow=0.7)

    def frame(self, t):
        import bisect
        i = max(0, bisect.bisect_right(self.starts, t) - 1)
        fr = self.line_frame(i, t)
        if i + 1 < len(LINES) and t > self.starts[i + 1] - XF:
            a = (t - (self.starts[i + 1] - XF)) / XF
            fr = cv2.addWeighted(fr, 1 - a, self.line_frame(i + 1, t), a, 0)
        fr = np.ascontiguousarray(fr)
        self.caps.draw(fr, t)
        # тонкая полоска прогресса сверху
        p = t / self.dur
        fr[0:8, :int(W * p)] = (np.array(R.CYAN) * 0.9).astype(np.uint8)
        return fr


def _chunk(job):
    cv2.setNumThreads(1)
    R.W, R.H = W, H
    s = Short()
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                          "-pix_fmt", "yuv420p", "-threads", "1", job["out"]], stdin=subprocess.PIPE)
    for f in range(job["f0"], job["f1"]):
        p.stdin.write(s.frame(f / FPS).tobytes())
    p.stdin.close()
    p.wait()
    return job["out"]


# ------------------------------------------------------------------ audio

def mix(dur):
    from shorts_ru import audio
    SR = audio.SR
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(BUILD / "voice.wav"), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    v = np.frombuffer(raw, np.float32).astype(np.float64)
    n = int(dur * SR)
    v = np.pad(v, (0, max(0, n - len(v))))[:n]
    m = audio.music("tense", dur + 0.2, seed=7, fade_out=0.05)[:n]
    m = np.pad(m, (0, n - len(m)))
    speech = np.abs(v) > 0.01
    gain = np.sqrt(np.mean(v[speech] ** 2)) / (np.sqrt(np.mean(m ** 2)) + 1e-9) * 10 ** (-18 / 20)
    out = v + m * gain
    tm = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
    pop = audio.sfx("pop")
    for s, _e in tm["bounds"][1:]:
        j = int((s - 0.05) * SR)
        out[j:j + len(pop)] += pop[: n - j] * 0.22
    wh = audio.sfx("whoosh")
    out[: len(wh)] += wh[:n] * 0.25
    out = np.tanh(out * 0.97)
    with wave.open(str(BUILD / "mix_raw.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(out, -1, 1) * 32767).astype("<i2").tobytes())
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(BUILD / "mix_raw.wav"), "-af",
                            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    mm = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I=-14:TP=-1.5:LRA=11:measured_I={mm['input_i']}:measured_TP={mm['input_tp']}:"
          f"measured_LRA={mm['input_lra']}:measured_thresh={mm['input_thresh']}:offset={mm['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(BUILD / "mix_raw.wav"), "-af", af, "-ar", "48000", "-ac", "2",
                    str(BUILD / "mix.wav")], check=True)


def main():
    BUILD.mkdir(exist_ok=True)
    bounds, dur = voice()
    words = align(bounds)
    (BUILD / "timing.json").write_text(json.dumps({"bounds": bounds, "duration": dur, "words": words},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    if "--stills" in sys.argv:
        s = Short()
        for i in range(len(LINES)):
            t = (s.starts[i] + (s.starts[i + 1] if i + 1 < len(LINES) else s.dur)) / 2
            Image.fromarray(s.frame(t)).save(BUILD / f"still_{i + 1:02d}.jpg", quality=88)
        return
    mix(dur)
    total = int(dur * FPS)
    step = total // 4 + 1
    jobs = [{"f0": f0, "f1": min(total, f0 + step), "out": str(BUILD / f"seg_{k}.mp4")}
            for k, f0 in enumerate(range(0, total, step))]
    with ProcessPoolExecutor(4, mp_context=mp.get_context("spawn")) as ex:
        list(ex.map(_chunk, jobs))
    (BUILD / "list.txt").write_text("".join(f"file '{Path(j['out']).name}'\n" for j in jobs))
    out = HERE / "short_final.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "list.txt"),
                    "-i", str(BUILD / "mix.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print(f"готово: {out} ({dur:.1f} с)", flush=True)


if __name__ == "__main__":
    main()
