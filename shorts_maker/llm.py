"""AI ranking, boundary refinement, caption correction and metadata with Claude.

All candidates are judged in ONE request so the model ranks them against
each other. The model only sees real transcripts and loudness data and is
told never to invent context; its proposed boundaries are validated and
clamped in code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

from pydantic import BaseModel, Field

from .audio_analysis import AudioProfile
from .config import Config
from .highlights import Candidate, excitement_summary
from .utils import log

SYSTEM_PROMPT = """You are a senior YouTube Shorts editor who cuts Twitch gaming streams.
You receive candidate moments from {streamer}'s {game} streams: a timestamped
transcript (seconds relative to the candidate window) and an audio-excitement curve
(higher = louder/hyped relative to the stream baseline; screams and laughter spike).

Judge each candidate as a standalone 20-60 second Short, rating 0-10 for:
entertainment, emotional reaction, unexpectedness, clarity of context (would a viewer
who never watched the stream understand it?), retention (does it hold attention to the
end?) and viral potential. Then give an overall score.

Prefer: very funny moments, unexpected events, big reactions (screaming, laughing),
crazy gameplay, weird NPC behaviour, good jokes and dramatic situations.
Penalise: boring stretches, long silence, no context, repetition, sponsor/ad reads,
"be right back" screens, and duplicates of another candidate's event (score the
weaker duplicate low and say so in `reason`).

Choose `start`/`end` (relative seconds within the window) so the clip contains the
full setup AND payoff, begins at the start of a sentence and ends after the reaction
lands; length 20-60 s (25-45 s is ideal).

Write metadata that is TRUE to the transcript. Never invent events, dialogue or
context that is not supported by the transcript. Titles: <= 60 characters, punchy,
may use one emoji. `short_name`: 2-5 words in Title_Case_With_Underscores for a
file name. `emphasis_words`: up to 8 single words from the transcript worth
highlighting in captions. Hashtags: 3-6, always include #Shorts."""


class CandidateScore(BaseModel):
    id: int
    entertainment: float
    emotional_reaction: float
    unexpectedness: float
    context_clarity: float
    retention: float
    viral_potential: float
    overall: float
    start: float = Field(description="clip start, seconds relative to the window")
    end: float = Field(description="clip end, seconds relative to the window")
    category: str
    title: str
    short_name: str
    description: str
    hashtags: list[str]
    emphasis_words: list[str]
    reason: str


class Ranking(BaseModel):
    candidates: list[CandidateScore]


class WordFix(BaseModel):
    index: int
    text: str


class CaptionFixes(BaseModel):
    fixes: list[WordFix]


def llm_available(cfg: Config) -> bool:
    if not cfg.use_llm:
        return False
    try:
        import anthropic  # noqa: F401  (availability check)
    except ImportError:
        log.warning("anthropic package missing - using heuristic ranking")
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    if shutil.which("ant"):  # an `ant auth login` profile also works
        try:
            out = subprocess.run(["ant", "auth", "status"], capture_output=True, text=True, timeout=10)
            if "(active)" in out.stdout:
                return True
        except Exception:  # noqa: BLE001
            pass
    log.warning("No Anthropic credentials found (ANTHROPIC_API_KEY) - using heuristic ranking")
    return False


def _client():
    import anthropic
    return anthropic.Anthropic(max_retries=4)


def _call(cfg: Config, prompt: str, schema, max_tokens: int = 32000):
    """One structured request with server-side refusal fallback enabled."""
    import anthropic

    client = _client()
    try:
        with client.beta.messages.stream(
            model=cfg.llm_model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT.format(streamer=cfg.streamer_name, game=cfg.game_name),
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={"effort": cfg.llm_effort},
            output_format=schema,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.RateLimitError as exc:
        log.warning("Claude rate limit: %s", exc.message)
        return None
    except anthropic.APIStatusError as exc:
        log.warning("Claude API error %s: %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning("Could not reach the Claude API")
        return None
    if msg.stop_reason in ("refusal", "max_tokens"):
        log.warning("Claude stopped early (%s)", msg.stop_reason)
        return None
    return msg.parsed_output


def _format_candidate(i: int, c: Candidate, profile: AudioProfile) -> str:
    lines, seg_start, buf = [], None, []
    for w in c.words:
        if seg_start is None:
            seg_start = w.start
        buf.append(w.clean)
        if w.clean.endswith((".", "!", "?")) or len(buf) >= 18:
            lines.append(f"[{seg_start - c.window_start:5.1f}] {' '.join(buf)}")
            seg_start, buf = None, []
    if buf:
        lines.append(f"[{seg_start - c.window_start:5.1f}] {' '.join(buf)}")
    transcript = "\n".join(lines) or "(no speech detected)"
    return (f"### Candidate {i}\nsource: {c.source.title}\n"
            f"window length: {c.window_end - c.window_start:.0f}s, "
            f"audio peak at {c.peak - c.window_start:.0f}s\n"
            f"excitement: {excitement_summary(c, profile)}\n"
            f"transcript:\n{transcript}\n")


def rank_with_llm(cands: list[Candidate], profiles: dict[str, AudioProfile], cfg: Config) -> bool:
    """Fill score/boundaries/metadata on each candidate. Returns False on failure."""
    body = "\n".join(_format_candidate(i, c, profiles[c.source.id]) for i, c in enumerate(cands))
    prompt = (f"Here are {len(cands)} candidate moments. Score every candidate "
              f"(use its number as `id`).\n\n{body}")
    log.info("Asking Claude (%s) to rank %d candidates…", cfg.llm_model, len(cands))
    result: Optional[Ranking] = _call(cfg, prompt, Ranking)
    if result is None:
        return False
    by_id = {r.id: r for r in result.candidates}
    for i, c in enumerate(cands):
        r = by_id.get(i)
        if r is None:
            c.score = 0.0
            continue
        c.scores = r.model_dump(include={"entertainment", "emotional_reaction", "unexpectedness",
                                          "context_clarity", "retention", "viral_potential"})
        c.score = float(r.overall)
        start = c.window_start + max(0.0, r.start)
        end = c.window_start + min(c.window_end - c.window_start, r.end)
        if cfg.min_clip_seconds <= end - start <= cfg.max_clip_seconds:
            c.start, c.end = start, end
        c.title, c.short_name, c.category = r.title.strip(), r.short_name.strip(), r.category
        c.description, c.reason = r.description.strip(), r.reason
        c.hashtags = [h if h.startswith("#") else f"#{h}" for h in r.hashtags]
        c.emphasis = [w.lower().strip(".,!?") for w in r.emphasis_words]
    return True


def fix_captions(c: Candidate, cfg: Config) -> None:
    """Correct obvious ASR errors word-by-word (timing is preserved)."""
    words = c.words_in()
    if not words:
        return
    numbered = " ".join(f"{i}:{w.clean}" for i, w in enumerate(words))
    prompt = ("These are speech-recognition words (index:word) from a gaming stream clip. "
              "Return fixes ONLY for obvious recognition errors, casing of names/places "
              "(e.g. GTA, Vice City, Lucia, Jason) and missing punctuation at the end of a word. "
              "Keep the speaker's slang and wording. Do not add, remove or merge words.\n\n"
              + numbered)
    result: Optional[CaptionFixes] = _call(cfg, prompt, CaptionFixes, max_tokens=16000)
    if not result:
        return
    for fx in result.fixes:
        if 0 <= fx.index < len(words) and fx.text.strip() and len(fx.text.split()) <= 2:
            words[fx.index].text = fx.text.strip()
