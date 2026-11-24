"""Музыка, звуковые эффекты и сведение.

Музыка генерируется процедурно (свои аккорды, пэды, бас, ритм) под настроение
ролика, поэтому никаких проблем с авторскими правами. Под голос музыка
автоматически приглушается (ducking по огибающей голоса). Свои треки можно
положить в папку и указать --music file.mp3.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from .utils import run

SR = 44100

MOODS = {  # (bpm, аккорды в полутонах от A, минор?, яркость фильтра, ритм)
    "mystery": (84, [0, -4, -7, -2], True, 1400, "soft"),
    "epic":    (96, [0, -4, -2, 3], True, 2600, "drums"),
    "calm":    (76, [3, -2, 0, -4], False, 1600, "none"),
    "tense":   (110, [0, 1, 0, -2], True, 1800, "pulse"),
    "upbeat":  (118, [3, -2, 0, 5], False, 3200, "drums"),
}


def _lp(x, f):
    return sosfilt(butter(2, f, "low", fs=SR, output="sos"), x)


def _hp(x, f):
    return sosfilt(butter(2, f, "high", fs=SR, output="sos"), x)


def _note(f, dur, kind="saw"):
    t = np.arange(int(dur * SR)) / SR
    if kind == "sine":
        return np.sin(2 * np.pi * f * t)
    if kind == "tri":
        return 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    x = np.zeros_like(t)
    for d in (-0.08, 0.0, 0.07):  # расстроенная пила (пэд)
        ff = f * 2 ** (d / 12)
        x += 2 * ((t * ff) % 1) - 1
    return x / 3


def music(mood: str, dur: float, seed: int = 0, fade_out: float = 1.5) -> np.ndarray:
    bpm, chords, minor, bright, rhythm = MOODS.get(mood, MOODS["mystery"])
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    root = 110.0  # A2
    third = 3 if minor else 4
    t0, ci = 0.0, 0
    while t0 < dur:
        semi = chords[ci % len(chords)]
        f = root * 2 ** (semi / 12)
        seg = int(min(bar, dur - t0) * SR)
        i0 = int(t0 * SR)
        env = np.ones(seg)
        a = min(seg, int(0.4 * SR))
        env[:a] = np.linspace(0, 1, a)
        env[-a:] *= np.linspace(1, 0.6, a)
        pad = sum(_note(f * 2 ** (iv / 12) * 2, seg / SR) for iv in (0, third, 7, 12)) / 4
        out[i0:i0 + seg] += pad[:seg] * env * 0.35
        bass = _note(f / 2, seg / SR, "tri")[:seg]
        out[i0:i0 + seg] += bass * env * 0.35
        # арпеджио-колокольчики
        for b in range(8):
            ts = i0 + int(b * beat / 2 * SR)
            if ts >= n or rng.random() < 0.35:
                continue
            iv = [0, third, 7, 12, 14][rng.integers(0, 5)]
            ln = int(0.45 * SR)
            tt = np.arange(ln) / SR
            bell = np.sin(2 * np.pi * f * 4 * 2 ** (iv / 12) * tt) * np.exp(-tt * 7)
            out[ts:ts + ln] += bell[: n - ts] * 0.12
        # ритм
        for b in range(4):
            ts = i0 + int(b * beat * SR)
            if ts >= n:
                continue
            if rhythm in ("drums", "pulse"):
                ln = int(0.25 * SR)
                tt = np.arange(ln) / SR
                kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
                out[ts:ts + ln] += kick[: n - ts] * (0.55 if rhythm == "drums" else 0.3)
            if rhythm == "drums" and b % 2 == 1:
                ln = int(0.18 * SR)
                sn = _hp(rng.standard_normal(ln), 1500) * np.exp(-np.arange(ln) / SR * 25)
                out[ts:ts + ln] += sn[: n - ts] * 0.18
            if rhythm in ("soft", "drums", "pulse"):
                for h in (0, 0.5):
                    th = ts + int(h * beat * SR)
                    ln = int(0.05 * SR)
                    if th < n:
                        hat = _hp(rng.standard_normal(ln), 6000) * np.exp(-np.arange(ln) / SR * 80)
                        out[th:th + ln] += hat[: n - th] * 0.05
        t0 += bar
        ci += 1
    out = _lp(out, bright)
    out /= np.max(np.abs(out)) + 1e-9
    fade = max(1, int(fade_out * SR))
    out[-fade:] *= np.linspace(1, 0, fade)
    out[: int(0.5 * SR)] *= np.linspace(0, 1, int(0.5 * SR))
    return out * 0.8


# ---------------------------------------------------------------------------

def sfx(name: str) -> np.ndarray:
    rng = np.random.default_rng(hash(name) % 1000)
    if name == "whoosh":
        ln = int(0.45 * SR)
        x = rng.standard_normal(ln)
        f = np.linspace(400, 3000, ln)
        y = np.zeros(ln)
        for s in range(0, ln, 1024):
            y[s:s + 1024] = sosfilt(butter(2, [f[s] * 0.6, f[s] * 1.4], "band", fs=SR, output="sos"), x[s:s + 1024])
        env = np.sin(np.linspace(0, np.pi, ln)) ** 2
        return y * env / (np.abs(y).max() + 1e-9) * 0.5
    if name == "pop":
        t = np.arange(int(0.12 * SR)) / SR
        return np.sin(2 * np.pi * (900 - 2500 * t) * t) * np.exp(-t * 40) * 0.5
    if name == "boom":
        t = np.arange(int(1.6 * SR)) / SR
        x = np.sin(2 * np.pi * np.cumsum(30 + 60 * np.exp(-t * 4)) / SR) * np.exp(-t * 2.2)
        x += _lp(rng.standard_normal(len(t)), 900) * np.exp(-t * 9) * 0.6
        return np.tanh(x * 1.5) * 0.8
    if name == "riser":
        t = np.arange(int(1.6 * SR)) / SR
        f = 200 * 2 ** (t * 2.2)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4 + _hp(rng.standard_normal(len(t)), 2000) * 0.2
        return x * (t / t[-1]) ** 2 * 0.6
    if name == "ding":
        t = np.arange(int(1.0 * SR)) / SR
        return (np.sin(2 * np.pi * 1760 * t) + 0.4 * np.sin(2 * np.pi * 2640 * t)) * np.exp(-t * 5) * 0.35
    if name == "click":
        t = np.arange(int(0.03 * SR)) / SR
        return _hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 200) * 0.4
    return np.zeros(1)


def envelope(voice: np.ndarray, fps: int) -> np.ndarray:
    """Громкость голоса по кадрам (0..1) — для движения губ."""
    hop = SR // fps
    n = len(voice) // hop
    rms = np.sqrt((voice[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    rms = rms / (np.percentile(rms, 95) + 1e-9)
    return np.clip(np.convolve(rms, [0.25, 0.5, 0.25], mode="same"), 0, 1)


def mix(voice: np.ndarray, script, cfg, out: Path, music_file: str | None = None) -> Path:
    cut = getattr(script, "ending", "normal") == "cut"
    n = len(voice) + (0 if cut else int(0.3 * SR))
    v = np.zeros(n)
    v[: len(voice)] = voice
    total = n / SR
    mix_ = v.copy()
    a = cfg.audio
    if a.music:
        if music_file:
            tmp = out.with_name("music_src.wav")
            run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", music_file, "-t", f"{total:.2f}",
                 "-ac", "1", "-ar", str(SR), str(tmp)])
            with wave.open(str(tmp)) as w:
                m = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        else:
            mood = script.mood if a.music_mood == "auto" else a.music_mood
            m = music(mood, total, seed=len(script.title), fade_out=0.03 if cut else 1.5)
        m = np.pad(m, (0, max(0, n - len(m))))[:n]
        # ducking: огибающая голоса, сглаженная (атака 50 мс, отпускание 400 мс)
        hop = 441
        c = np.cumsum(np.concatenate([[0.0], v ** 2]))
        lvl = np.sqrt(np.maximum(0, (c[hop:] - c[:-hop]) / hop))
        lvl = np.pad(lvl, (hop // 2, n - len(lvl) - hop // 2))
        talk = (lvl > 0.01).astype(np.float32)
        sm = np.zeros_like(talk)
        g = 0.0
        att, rel = 1 - np.exp(-1 / (0.05 * SR)), 1 - np.exp(-1 / (0.4 * SR))
        for i in range(0, n, hop):  # блоками для скорости
            target = talk[i]
            g += (target - g) * (1 - (1 - (att if target > g else rel)) ** hop)
            sm[i:i + hop] = g
        duck = 10 ** ((float(a.music_volume_db) + float(a.duck_db) * sm) / 20)
        mix_ += m * duck
    if a.sfx:
        for sc in script.scenes:
            if sc.sfx and sc.sfx != "none":
                x = sfx(sc.sfx)
                t = sc.start - (1.4 if sc.sfx == "riser" else 0.08)
                i = max(0, int(t * SR))
                mix_[i:i + len(x)] += x[: n - i] * 0.5
            for _ in sc.props[:1]:
                x = sfx("pop")
                i = int((sc.start + 0.3) * SR)
                mix_[i:i + len(x)] += x[: n - i] * 0.25
    mix_ = np.tanh(mix_ * 0.95)
    wav = out.with_suffix(".raw.wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix_, -1, 1) * 32767).astype("<i2").tobytes())
    # двухпроходная нормализация громкости: точное попадание в целевые LUFS
    target = float(a.loudness_lufs)
    first = run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af",
                 f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]).stderr
    import json as _json
    m = _json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af", af, "-ar", str(SR), "-ac", "2", str(out)])
    return out
