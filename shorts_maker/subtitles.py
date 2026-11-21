"""Animated word-by-word captions as an ASS subtitle file (rendered by libass).

Each caption shows 1-3 words. The word being spoken is coloured and "pops"
(scale animation); important words are always shown in the emphasis colour.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import Config
from .highlights import HYPE_TERMS
from .timeline import Piece, map_time
from .transcribe import Word

EMPHASIS_DEFAULT = {t for t in HYPE_TERMS if " " not in t} | {
    "gta", "cops", "money", "bank", "car", "gun", "jail", "never", "yes", "no", "dead",
}


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _censor(word: str, banned: tuple[str, ...]) -> str:
    low = re.sub(r"[^a-z]", "", word.lower())
    for b in banned:
        if b and low.startswith(b.lower()):
            core = re.sub(r"[A-Za-z]", "*", word)
            return word[0] + core[1:] if word else word
    return word


def _phrases(words: list[tuple[float, float, str]], max_words: int) -> list[list[tuple[float, float, str]]]:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w[0] - cur[-1][1] > 0.35
                    or len(" ".join(x[2] for x in cur + [w])) > 18):
            groups.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?,]$", w[2]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list[Word], pieces: list[Piece], cfg: Config, caption_y: int,
              emphasis: list[str], out: Path, clip_duration: float) -> int:
    """Write the .ass file; returns the number of caption events."""
    # map every word into output time (teaser words appear twice)
    timed: list[tuple[float, float, str]] = []
    for w in words:
        hits = map_time(w.start, pieces) or map_time((w.start + w.end) / 2, pieces)
        for t0 in hits:
            dur = max(0.12, min(w.end - w.start, 1.2))
            timed.append((t0, t0 + dur, w.clean))
    timed.sort()
    # words should not overlap after cuts
    for i in range(len(timed) - 1):
        if timed[i][1] > timed[i + 1][0]:
            timed[i] = (timed[i][0], timed[i + 1][0], timed[i][2])

    emph = {e.lower() for e in emphasis} | EMPHASIS_DEFAULT
    hi, em = _ass_color(cfg.highlight_color), _ass_color(cfg.emphasis_color)
    W, H = cfg.width, cfg.height

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{cfg.font_name},{cfg.font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,7,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    pos = f"\\an5\\pos({W // 2},{caption_y})"
    for group in _phrases(timed, cfg.max_words_per_caption):
        g_end = group[-1][1] + 0.15
        for i, (s, e, _) in enumerate(group):
            nxt = group[i + 1][0] if i + 1 < len(group) else g_end
            parts = []
            for j, (_, _, txt) in enumerate(group):
                word = _escape(_censor(txt, cfg.censor_words)).upper()
                key = re.sub(r"[^a-z']", "", txt.lower())
                if j == i:
                    parts.append(f"{{\\c{hi}\\fscx118\\fscy118\\t(0,90,\\fscx100\\fscy100)}}{word}{{\\r}}")
                elif key in emph:
                    parts.append(f"{{\\c{em}}}{word}{{\\r}}")
                else:
                    parts.append(word)
            intro = "\\fad(60,0)" if i == 0 else ""
            start, end = s, min(max(nxt, s + 0.1), clip_duration)
            if end > start:
                events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Cap,,0,0,0,,"
                              f"{{{pos}{intro}}}{' '.join(parts)}")
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return len(events)
