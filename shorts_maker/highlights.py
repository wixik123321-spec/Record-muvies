"""Candidate highlights: heuristic scoring, boundary selection, de-duplication."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .audio_analysis import AudioProfile
from .config import Config
from .sources import Source
from .transcribe import Word

# Words/phrases that tend to accompany reactions in English gaming streams.
HYPE_TERMS = [
    "no way", "oh my god", "what the", "bro", "yo", "wait", "run", "chat", "hell nah",
    "nah", "what", "why", "help", "stop", "go go", "let's go", "lets go", "crazy",
    "insane", "cops", "police", "dead", "died", "bruh", "ha ha", "haha", "lol",
    "oh no", "oh shit", "holy", "bro what", "ain't no way", "yooo", "ayo",
]
LAUGH_RE = re.compile(r"\b(ha){2,}|\bhaha|\(laugh|\[laugh|\blmao\b", re.I)
SENTENCE_END = re.compile(r"[.!?…]$")


@dataclass
class Candidate:
    source: Source
    peak: float
    window_start: float
    window_end: float
    words: list[Word] = field(default_factory=list)
    audio_score: float = 0.0
    # chosen boundaries (absolute source times)
    start: float = 0.0
    end: float = 0.0
    # ranking
    score: float = 0.0
    scores: dict = field(default_factory=dict)
    title: str = ""
    short_name: str = ""
    category: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    emphasis: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start

    def words_in(self, start: float | None = None, end: float | None = None) -> list[Word]:
        a = self.start if start is None else start
        b = self.end if end is None else end
        return [w for w in self.words if w.end > a and w.start < b]

    def text(self, start: float | None = None, end: float | None = None) -> str:
        return " ".join(w.clean for w in self.words_in(start, end))


def _sentence_starts(words: list[Word]) -> list[float]:
    starts = [words[0].start] if words else []
    for prev, cur in zip(words, words[1:]):
        if SENTENCE_END.search(prev.clean) or cur.start - prev.end > 0.7:
            starts.append(cur.start)
    return starts


def _sentence_ends(words: list[Word]) -> list[float]:
    ends = []
    for cur, nxt in zip(words, words[1:] + [None]):
        if nxt is None or SENTENCE_END.search(cur.clean) or nxt.start - cur.end > 0.7:
            ends.append(cur.end)
    return ends


def choose_boundaries(c: Candidate, cfg: Config, target: float = 35.0) -> tuple[float, float]:
    """Pick start/end that contain the setup and the payoff around the peak.

    End: the first sentence end at least ~4 s after the peak (the reaction
    plays out), start: a sentence start ``target`` seconds before the end.
    Both snap to speech boundaries so clips never cut mid-word.
    """
    lo, hi = cfg.min_clip_seconds, cfg.max_clip_seconds
    words = c.words
    if not words:
        return max(c.window_start, c.peak - target + 8), min(c.window_end, c.peak + 8)

    ends = [e for e in _sentence_ends(words) if e >= c.peak + 4] or [words[-1].end]
    end = min(ends[0], c.peak + 20) + 0.4
    starts = _sentence_starts(words)
    want = end - target
    valid = [s for s in starts if lo <= end - (s - 0.25) <= hi]
    start = min(valid, key=lambda s: abs(s - want)) - 0.25 if valid else end - target
    start = max(c.window_start, start)
    end = min(c.window_end, max(end, start + lo))
    return start, end


def heuristic_score(c: Candidate) -> float:
    """0-10 score from audio excitement + transcript signals (used without an LLM)."""
    text = c.text().lower()
    n_words = max(1, len(c.words_in()))
    hype = sum(text.count(t) for t in HYPE_TERMS)
    laughs = len(LAUGH_RE.findall(text))
    exclaims = text.count("!") + text.count("?")
    density = n_words / max(1.0, c.duration)  # words per second
    s = (
        3.0 * min(1.0, max(0.0, c.audio_score) / 4.0)
        + 2.5 * min(1.0, hype / 8)
        + 1.5 * min(1.0, laughs / 3)
        + 1.0 * min(1.0, exclaims / 6)
        + 2.0 * min(1.0, density / 2.5)
    )
    if n_words < 15:  # little context
        s -= 2.0
    return round(max(0.0, min(10.0, s)), 2)


def heuristic_metadata(c: Candidate, cfg: Config) -> None:
    """Fallback titles/descriptions when no LLM is available (truthful, from transcript)."""
    peak_words = [w.clean for w in c.words if abs(w.start - c.peak) < 3]
    quote = " ".join(peak_words[:6]).strip(" ,.")
    if quote:
        quote = re.sub(r"\s+", " ", quote).upper()
        c.title = f"\"{quote}\" 😂 {cfg.streamer_name} {cfg.game_name}"
    else:
        c.title = f"{cfg.streamer_name} Reacts in {cfg.game_name} 😂"
    key = re.sub(r"[^A-Za-z ]", "", " ".join(peak_words[:4])).title().replace(" ", "_")
    c.short_name = f"{cfg.streamer_name.split()[0]}_{key or 'Reaction'}"
    c.category = c.category or "reaction"
    c.description = (f"{cfg.streamer_name} {cfg.game_name} stream highlight.\n"
                     f"Full stream: {c.source.url}")
    tag = cfg.streamer_name.replace(" ", "")
    game = cfg.game_name.replace(" ", "")
    c.hashtags = [f"#{tag}", f"#{game}", "#Shorts", "#Twitch", "#Gaming"]


def dedupe(cands: list[Candidate], min_separation: float = 15.0) -> list[Candidate]:
    """Keep the best-scored candidate among overlapping/near-identical moments."""
    kept: list[Candidate] = []
    for c in sorted(cands, key=lambda x: x.score, reverse=True):
        clash = False
        for k in kept:
            if k.source.id != c.source.id:
                continue
            overlap = min(k.end, c.end) - max(k.start, c.start)
            if overlap > 0.3 * min(k.duration, c.duration) or abs(k.peak - c.peak) < min_separation:
                clash = True
                break
        if not clash:
            kept.append(c)
    return kept


def excitement_summary(c: Candidate, profile: AudioProfile) -> str:
    """Compact per-5s loudness curve for the LLM (relative seconds: excitement)."""
    parts = []
    t = c.window_start
    while t < c.window_end:
        a, b = int(t), int(min(len(profile.excitement), t + 5))
        if b > a:
            parts.append(f"{t - c.window_start:.0f}s:{profile.excitement[a:b].max():+.1f}")
        t += 5
    return " ".join(parts)
