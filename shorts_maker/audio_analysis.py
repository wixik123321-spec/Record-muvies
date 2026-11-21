"""Audio excitement analysis over a whole VOD.

The audio is streamed through FFmpeg (8 kHz mono) so an 8-hour stream never
has to fit in memory. For every second we compute loudness and short-burst
energy; "excitement" is how much louder/burstier a moment is than the
surrounding few minutes (screams, laughter and hype spike above the local
baseline, while a constantly loud stream does not).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .utils import ToolError, log

SR = 8000


@dataclass
class AudioProfile:
    loudness_db: np.ndarray   # per second
    burst_db: np.ndarray      # loudest 100 ms block in each second
    excitement: np.ndarray    # per second, roughly z-score units

    @property
    def duration(self) -> float:
        return float(len(self.loudness_db))

    def mean_db(self, start: float, end: float) -> float:
        a, b = int(max(0, start)), int(min(len(self.loudness_db), np.ceil(end)))
        return float(self.loudness_db[a:b].mean()) if b > a else -90.0

    def peak_time(self, start: float, end: float) -> float:
        a, b = int(max(0, start)), int(min(len(self.excitement), np.ceil(end)))
        if b <= a:
            return start
        return a + float(np.argmax(self.excitement[a:b])) + 0.5


def _db(x: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.sqrt(np.maximum(x, 1e-12)))


def _rolling_median(x: np.ndarray, window: int) -> np.ndarray:
    if len(x) == 0:
        return x
    window = max(3, min(window, len(x)))
    # coarse but fast: median over blocks, then interpolate
    step = max(1, window // 6)
    centers = np.arange(0, len(x), step)
    med = np.array([np.median(x[max(0, c - window // 2): c + window // 2 + 1]) for c in centers])
    return np.interp(np.arange(len(x)), centers, med)


def analyse_audio(path: Path, progress=None) -> AudioProfile:
    """Stream ``path`` and build a per-second excitement profile."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-vn",
           "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    loud, burst = [], []
    chunk = SR * 2  # one second of s16
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(chunk * 60)
        if not buf:
            break
        samples = np.frombuffer(buf[: len(buf) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768
        n = len(samples) // SR
        if n == 0:
            continue
        sec = samples[: n * SR].reshape(n, SR)
        loud.extend(_db((sec ** 2).mean(axis=1)))
        blocks = sec.reshape(n, 10, SR // 10)
        burst.extend(_db((blocks ** 2).mean(axis=2)).max(axis=1))
        if progress:
            progress(len(loud))
    proc.wait()
    if proc.returncode != 0:
        raise ToolError((proc.stderr.read() if proc.stderr else b"").decode(errors="ignore")[-1500:])

    loud_a = np.asarray(loud, dtype=np.float32)
    burst_a = np.asarray(burst, dtype=np.float32)
    if len(loud_a) == 0:
        raise ToolError(f"No audio decoded from {path}")

    base = _rolling_median(loud_a, 300)              # 5-minute local baseline
    spread = np.median(np.abs(loud_a - base)) + 1.0  # robust scale (dB)
    z_loud = (loud_a - base) / spread
    z_burst = (burst_a - _rolling_median(burst_a, 300)) / spread
    raw = 0.6 * z_loud + 0.4 * z_burst
    kernel = np.ones(3) / 3
    excitement = np.convolve(raw, kernel, mode="same")
    # silence is never exciting
    excitement[loud_a < -55] = -5
    log.info("Audio analysed: %.1f min", len(loud_a) / 60)
    return AudioProfile(loud_a, burst_a, excitement.astype(np.float32))


def pick_peaks(profile: AudioProfile, count: int, min_gap: float,
               edge: float = 45.0) -> list[float]:
    """Highest-excitement seconds, at least ``min_gap`` apart (non-max suppression)."""
    exc = profile.excitement.copy()
    n = len(exc)
    lo, hi = int(min(edge, n * 0.1)), int(max(n - 15, n * 0.9))
    exc[:lo] = -np.inf
    exc[hi:] = -np.inf
    peaks: list[float] = []
    for idx in np.argsort(exc)[::-1]:
        if not np.isfinite(exc[idx]):
            break
        t = float(idx) + 0.5
        if all(abs(t - p) >= min_gap for p in peaks):
            peaks.append(t)
            if len(peaks) >= count:
                break
    return sorted(peaks)
