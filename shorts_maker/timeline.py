"""Build the edit decision list for one Short.

A timeline is a list of :class:`Piece` (source intervals played in order,
each with a zoom factor). It implements: hook teaser, pause removal and
punch-in zooms on the strongest reactions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio_analysis import AudioProfile
from .config import Config
from .highlights import Candidate


@dataclass
class Piece:
    start: float   # source time
    end: float
    zoom: float = 1.0
    teaser: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start


def _quiet_gaps(c: Candidate, profile: AudioProfile, cfg: Config) -> list[tuple[float, float]]:
    """Silent stretches between words that can be shortened."""
    words = c.words_in()
    clip_db = profile.mean_db(c.start, c.end)
    edges = [(a.end, b.start) for a, b in zip(words, words[1:])]
    # only truly quiet stretches (no loud gameplay), longest first
    quiet = sorted((e for e in edges if e[1] - e[0] > cfg.max_pause
                    and profile.mean_db(*e) < clip_db - 8),
                   key=lambda e: e[1] - e[0], reverse=True)
    # never trim more than 20% of the clip or below the minimum length
    budget = min(0.2 * c.duration, max(0.0, c.duration - cfg.min_clip_seconds))
    keep = cfg.keep_pause / 2
    gaps = []
    for a, b in quiet:
        cut = (b - a) - cfg.keep_pause
        if cut <= 0 or cut > budget:
            continue
        budget -= cut
        gaps.append((a + keep, b - keep))
    return gaps


def _reaction_times(c: Candidate, profile: AudioProfile, max_n: int = 2) -> list[float]:
    a, b = int(c.start), int(c.end)
    exc = profile.excitement[a:b]
    if len(exc) == 0:
        return []
    thr = max(1.5, float(np.percentile(exc, 90)))
    times = []
    for i in np.argsort(exc)[::-1]:
        t = a + float(i)
        if exc[i] < thr or len(times) >= max_n:
            break
        if all(abs(t - x) > 6 for x in times):
            times.append(t)
    return sorted(times)


def build_timeline(c: Candidate, profile: AudioProfile, cfg: Config) -> list[Piece]:
    # 1) keep everything except shortened silent gaps
    spans = [(c.start, c.end)]
    if cfg.remove_pauses:
        for g0, g1 in _quiet_gaps(c, profile, cfg):
            new = []
            for s0, s1 in spans:
                if g1 <= s0 or g0 >= s1:
                    new.append((s0, s1))
                    continue
                if g0 > s0:
                    new.append((s0, g0))
                if g1 < s1:
                    new.append((g1, s1))
            spans = new
    spans = [s for s in spans if s[1] - s[0] > 0.15]

    # 2) split spans around reaction moments for punch-in zoom
    pieces: list[Piece] = []
    zooms = [(t - 0.3, t + 2.2) for t in _reaction_times(c, profile)] if cfg.punch_zoom > 1.0 else []
    for s0, s1 in spans:
        cuts = sorted({s0, s1, *[x for z in zooms for x in z if s0 < x < s1]})
        for a, b in zip(cuts, cuts[1:]):
            mid = (a + b) / 2
            z = cfg.punch_zoom if any(z0 <= mid <= z1 for z0, z1 in zooms) else 1.0
            if b - a > 0.05:
                pieces.append(Piece(a, b, z))

    # 3) hook: open with the peak reaction, then play the clip from its setup
    if cfg.hook_teaser and c.peak - c.start > 8:
        t0 = max(c.start, c.peak - 0.4)
        t1 = min(c.end, t0 + cfg.teaser_seconds)
        pieces.insert(0, Piece(t0, t1, cfg.punch_zoom if cfg.punch_zoom > 1 else 1.0, teaser=True))
    return pieces


def map_time(t: float, pieces: list[Piece]) -> list[float]:
    """Output times at which source time ``t`` is shown (teaser can repeat it)."""
    out, offset = [], 0.0
    for p in pieces:
        if p.start <= t < p.end:
            out.append(offset + (t - p.start))
        offset += p.duration
    return out


def total_duration(pieces: list[Piece]) -> float:
    return sum(p.duration for p in pieces)
