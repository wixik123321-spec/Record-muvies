"""Runtime configuration for the Shorts pipeline.

Every option has a sensible default so the app runs with a single command;
all of them can be overridden from the command line (see ``cli.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CHANNEL_URL = "https://www.twitch.tv/kaicenat/videos?filter=archives&sort=time"
DEFAULT_TITLE_KEYWORDS = ("gta 6", "gta vi", "gta6", "gtavi", "gta")


@dataclass
class Config:
    # --- sources -----------------------------------------------------------
    channel_url: str = DEFAULT_CHANNEL_URL
    vod_urls: list[str] = field(default_factory=list)      # explicit VODs (skip listing)
    input_files: list[Path] = field(default_factory=list)  # local videos you own
    title_keywords: tuple[str, ...] = DEFAULT_TITLE_KEYWORDS
    max_vods: int = 3              # how many matching VODs to analyse at most
    scan_limit: int = 30           # how many recent archive entries to look at
    streamer_name: str = "Kai Cenat"
    game_name: str = "GTA 6"
    cookies_from_browser: str | None = None  # e.g. "chrome" for sub-only VODs you can watch

    # --- folders -----------------------------------------------------------
    output_dir: Path = Path("output/shorts")
    temp_dir: Path = Path("output/_tmp")
    keep_temp: bool = False

    # --- clip selection ----------------------------------------------------
    target_clips: int = 12
    min_clips: int = 10
    min_clip_seconds: float = 20.0
    max_clip_seconds: float = 60.0
    candidates_per_clip: float = 3.0   # candidates analysed per wanted clip
    min_gap_between_candidates: float = 75.0  # seconds, avoids duplicate events

    # --- speech recognition -------------------------------------------------
    whisper_model: str = "small.en"
    whisper_device: str = "auto"       # auto | cpu | cuda
    whisper_compute_type: str = "auto"  # auto | int8 | float16 ...
    language: str = "en"

    # --- AI ranking (Claude) -------------------------------------------------
    use_llm: bool = True               # auto-disabled when no Anthropic credentials
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"

    # --- editing -----------------------------------------------------------
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 20
    x264_preset: str = "medium"
    audio_bitrate: str = "192k"
    remove_pauses: bool = True
    max_pause: float = 0.7             # silent gaps longer than this get shortened
    keep_pause: float = 0.25           # ...down to this
    hook_teaser: bool = True           # 1-2 s cold open of the peak, then the full clip
    teaser_seconds: float = 1.8
    punch_zoom: float = 1.12           # zoom factor on peak reactions (1.0 = off)
    sfx_file: Path | None = None       # optional short "pop" played on zoom-ins
    sfx_volume: float = 0.25
    loudnorm: bool = True
    censor_words: tuple[str, ...] = ()  # words to mask in captions, e.g. ("fuck",)

    # --- subtitles ---------------------------------------------------------
    font_name: str = "Arial Black"
    font_size: int = 84
    max_words_per_caption: int = 3
    highlight_color: str = "#FFE600"   # active word
    emphasis_color: str = "#3CFF5A"    # important words

    # --- behaviour ---------------------------------------------------------
    overwrite: bool | None = None      # None = ask (or skip when not interactive)
    dry_run: bool = False              # analyse + rank only, do not render
