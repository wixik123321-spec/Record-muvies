"""Original, synthesized horror sound design (no samples, no copyrighted audio).

Every sound is generated with numpy at 48 kHz, so the soundtrack is fully
royalty-free and reproducible from a seed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _bp(x, lo, hi, order=4):
    return sosfilt(butter(order, [lo, hi], btype="band", fs=SR, output="sos"), x)


def _lp(x, f, order=4):
    return sosfilt(butter(order, f, btype="low", fs=SR, output="sos"), x)


def _hp(x, f, order=4):
    return sosfilt(butter(order, f, btype="high", fs=SR, output="sos"), x)


def _env(n, attack, release, curve=3.0):
    a, r = int(attack * SR), int(release * SR)
    e = np.ones(n)
    if a:
        e[:a] = np.linspace(0, 1, a) ** 2
    if r:
        e[-r:] *= np.linspace(1, 0, r) ** curve
    return e


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def reverb(x: np.ndarray, decay: float = 1.6, mix: float = 0.35, seed: int = 3) -> np.ndarray:
    """Small dark room / hall: exponentially decaying filtered noise IR."""
    rng = np.random.default_rng(seed)
    n = int(decay * SR)
    ir = rng.standard_normal(n) * np.exp(-np.linspace(0, 7, n))
    ir = _lp(ir, 4500)
    ir /= np.sqrt(np.sum(ir ** 2))
    out = fftconvolve(x, ir) * mix
    out[: len(x)] += x * (1 - mix)
    return out


# --- individual effects --------------------------------------------------

def vibration(pulses: int = 2, seed: int = 1) -> np.ndarray:
    """Phone buzzing on a wooden desk: motor hum + rattle."""
    rng = np.random.default_rng(seed)
    pulse = 0.38
    gap = 0.16
    out = np.zeros(int((pulse + gap) * pulses * SR))
    t = _t(pulse)
    for p in range(pulses):
        f = 165 + rng.uniform(-4, 4)
        hum = np.sign(np.sin(2 * np.pi * f * t)) * 0.5 + np.sin(2 * np.pi * f * t)
        rattle = _bp(rng.standard_normal(len(t)), 900, 3800) * (0.5 + 0.5 * np.sin(2 * np.pi * f * t))
        body = _lp(hum, 900) * 0.8 + rattle * 0.35
        body *= _env(len(t), 0.01, 0.06)
        s = int(p * (pulse + gap) * SR)
        out[s:s + len(t)] += body
    return _norm(out, 0.8)


def notification() -> np.ndarray:
    """Soft two-note chime (original)."""
    out = np.zeros(int(0.9 * SR))
    for start, f in ((0.0, 1318.5), (0.11, 1975.5)):
        t = _t(0.7)
        tone = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
                + 0.12 * np.sin(2 * np.pi * 3.01 * f * t))
        tone *= np.exp(-t * 7) * _env(len(t), 0.003, 0.05)
        s = int(start * SR)
        out[s:s + len(t)] += tone
    return _norm(reverb(out, 0.9, 0.25)[: int(1.4 * SR)], 0.55)


def send_whoosh() -> np.ndarray:
    t = _t(0.25)
    sweep = np.sin(2 * np.pi * np.cumsum(np.linspace(500, 1400, len(t))) / SR)
    return _norm(sweep * np.exp(-t * 14) * _env(len(t), 0.004, 0.05), 0.35)


def key_tap(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _t(0.035)
    click = _bp(rng.standard_normal(len(t)), 2000, 7000) * np.exp(-t * 180)
    return _norm(click, rng.uniform(0.12, 0.2))


def tick(tock: bool = False) -> np.ndarray:
    rng = np.random.default_rng(7 if tock else 8)
    t = _t(0.06)
    f = 2600 if tock else 3100
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 120) + _hp(rng.standard_normal(len(t)), 3000) * np.exp(-t * 300) * 0.4
    return _norm(reverb(x, 0.4, 0.2), 0.3)


def switch_click() -> np.ndarray:
    rng = np.random.default_rng(11)
    t = _t(0.12)
    x = _bp(rng.standard_normal(len(t)), 1200, 6000) * np.exp(-t * 90)
    x[int(0.012 * SR):] += _bp(rng.standard_normal(len(t) - int(0.012 * SR)), 300, 2500) * np.exp(-t[: len(t) - int(0.012 * SR)] * 140) * 0.8
    return _norm(reverb(x, 0.5, 0.2), 0.6)


def breathing(cycles: int = 3, seed: int = 5) -> np.ndarray:
    """Slow, shaky breathing: band-passed noise with breath envelopes."""
    rng = np.random.default_rng(seed)
    parts = []
    for i in range(cycles):
        inhale, exhale = rng.uniform(1.0, 1.3), rng.uniform(1.3, 1.7)
        for dur, (lo, hi), g in ((inhale, (700, 2600), 0.5), (exhale, (350, 1800), 0.8)):
            n = int(dur * SR)
            env = np.sin(np.linspace(0, np.pi, n)) ** 1.6
            shake = 1 + 0.25 * np.sin(2 * np.pi * rng.uniform(5, 8) * _t(dur))
            parts.append(_bp(rng.standard_normal(n), lo, hi) * env * shake * g)
        parts.append(np.zeros(int(0.25 * SR)))
    return _norm(np.concatenate(parts), 0.35)


def rustle(seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _t(0.7)
    x = _bp(rng.standard_normal(len(t)), 1500, 8000)
    x *= np.abs(_lp(rng.standard_normal(len(t)), 25)) * 4
    return _norm(x * _env(len(t), 0.08, 0.3), 0.25)


def whisper(seed: int = 13) -> np.ndarray:
    """Unintelligible, distorted, reversed whisper texture."""
    rng = np.random.default_rng(seed)
    dur = 1.6
    t = _t(dur)
    noise = rng.standard_normal(len(t))
    # moving formants give a speech-like quality without words
    out = np.zeros(len(t))
    for base, rate in ((700, 3.1), (1300, 4.3), (2500, 5.7)):
        f = base * (1 + 0.35 * np.sin(2 * np.pi * rate * t + rng.uniform(0, 6)))
        seg = np.zeros(len(t))
        hop = int(0.02 * SR)
        for s in range(0, len(t) - hop, hop):
            c = float(f[s])
            seg[s:s + hop] = _bp(noise[s:s + hop * 3], c * 0.8, c * 1.2, 2)[:hop]
        out += seg
    syll = np.clip(np.sin(2 * np.pi * 3.7 * t) * 1.5, 0, 1) ** 2
    out *= syll * _env(len(t), 0.15, 0.4)
    out = out[::-1]  # reversed
    out = np.tanh(out / (np.std(out) + 1e-9) * 1.8)  # distortion
    return _norm(reverb(out, 2.4, 0.55), 0.45)


def impact() -> np.ndarray:
    """Deep cinematic hit: sub drop + noise burst + long tail."""
    rng = np.random.default_rng(17)
    dur = 4.0
    t = _t(dur)
    f = 70 * np.exp(-t * 0.9) + 26
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 0.9)
    burst = _lp(rng.standard_normal(len(t)), 1800) * np.exp(-t * 9)
    x = sub * 1.0 + burst * 0.5
    x = np.tanh(x * 1.6)
    return _norm(reverb(x, 3.0, 0.4)[: int(5 * SR)], 0.95)


def drone(dur: float, tension: np.ndarray | None = None, seed: int = 21) -> np.ndarray:
    """Low evolving drone; ``tension`` (0..1 per sample) opens filter and adds dissonance."""
    rng = np.random.default_rng(seed)
    t = _t(dur)
    n = len(t)
    ten = np.ones(n) * 0.3 if tension is None else np.interp(np.arange(n), np.linspace(0, n, len(tension)), tension)
    base = 55.0
    x = np.zeros(n)
    for k, (ratio, amp) in enumerate(((1, 1), (1.005, 0.8), (1.5, 0.35), (2.0, 0.3), (2.997, 0.15))):
        lfo = 1 + 0.002 * np.sin(2 * np.pi * rng.uniform(0.05, 0.15) * t + k)
        x += amp * np.sin(2 * np.pi * base * ratio * np.cumsum(lfo) / SR)
    # dissonant minor-second cluster that fades in with tension
    cluster = np.sin(2 * np.pi * base * 2 * 1.0595 * t) + np.sin(2 * np.pi * base * 4 * 1.0595 * t) * 0.4
    x += cluster * ten ** 2 * 0.8
    air = _bp(rng.standard_normal(n), 120, 900) * 0.25
    x = x * 0.6 + air
    # tension slowly opens a low-pass (computed in blocks)
    out = np.zeros(n)
    block = SR // 4
    for s in range(0, n, block):
        c = 180 + 1400 * float(ten[s])
        out[s:s + block] = _lp(x[max(0, s - 2048): s + block], c, 2)[-len(x[s:s + block]):]
    out *= 0.6 + 0.6 * ten
    return out


def room_tone(dur: float, seed: int = 31) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = _lp(rng.standard_normal(int(dur * SR)), 300) + _bp(rng.standard_normal(int(dur * SR)), 2000, 6000) * 0.05
    return x / (np.std(x) + 1e-9) * 0.02


def pulse_heartbeat(dur: float) -> np.ndarray:
    t = _t(0.25)
    beat = np.sin(2 * np.pi * 52 * t) * np.exp(-t * 18)
    out = np.zeros(int(dur * SR))
    period = 0.95
    s = 0.0
    while s < dur - 0.6:
        for off, g in ((0, 1), (0.28, 0.6)):
            i = int((s + off) * SR)
            out[i:i + len(beat)] += beat[: len(out) - i] * g
        s += period
        period = max(0.62, period * 0.97)
    return _norm(out, 0.5)


LIBRARY = {
    "vibration": vibration, "notification": notification, "send": send_whoosh,
    "tick": tick, "switch": switch_click, "breathing": breathing, "rustle": rustle,
    "whisper": whisper, "impact": impact,
}


def write_wav(path: Path, x: np.ndarray) -> None:
    x = np.clip(x, -1, 1)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
