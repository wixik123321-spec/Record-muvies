"""Finding and downloading source material with yt-dlp.

Strategy (to avoid downloading whole 8-hour VODs in 1080p):
1. list the channel's archive and keep VODs whose title matches the game keywords;
2. download only the *audio-only* rendition of each VOD for analysis;
3. after ranking, download only the selected time ranges in video quality.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Config
from .utils import log, read_audio

try:  # imported lazily so local-file mode works without yt-dlp
    import yt_dlp
    from yt_dlp.utils import DownloadError, download_range_func
except ImportError:  # pragma: no cover
    yt_dlp = None


@dataclass
class Source:
    """One long video we analyse (a Twitch VOD or a local file)."""
    id: str
    url: str                  # public URL (or file path for local files)
    title: str
    audio_path: Path | None = None   # file used for analysis
    local_video: Path | None = None  # set for local files: cut directly from it
    duration: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class SourceClip:
    """Downloaded video covering a highlight. ``offset`` = source time at file t=0."""
    path: Path
    offset: float


def _ydl_opts(cfg: Config, **extra) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "retries": 5,
            "fragment_retries": 10, "concurrent_fragment_downloads": 4}
    if cfg.cookies_from_browser:
        opts["cookiesfrombrowser"] = (cfg.cookies_from_browser,)
    opts.update(extra)
    return opts


def _ffmpeg_proxy_setup() -> list[str]:
    """Let FFmpeg (used for range downloads) work behind an HTTPS proxy.

    FFmpeg reads ``http_proxy`` only, and needs a CA file when the proxy
    re-signs TLS. Returns extra FFmpeg input arguments.
    """
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy and not os.environ.get("http_proxy"):
        os.environ["http_proxy"] = proxy
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ["-ca_file", ca] if proxy and ca and Path(ca).exists() else []


def _require_ytdlp() -> None:
    if yt_dlp is None:
        raise SystemExit("yt-dlp is not installed: pip install -r requirements.txt")


def list_vods(cfg: Config) -> list[Source]:
    """Return VODs to analyse: explicit URLs, or matching titles from the channel."""
    _require_ytdlp()
    if cfg.vod_urls:
        return [Source(id=f"vod{i}", url=u, title=u) for i, u in enumerate(cfg.vod_urls, 1)]

    log.info("Listing archive VODs: %s", cfg.channel_url)
    opts = _ydl_opts(cfg, extract_flat="in_playlist", playlistend=cfg.scan_limit)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(cfg.channel_url, download=False)
    entries = [e for e in (info or {}).get("entries") or [] if e]
    keys = [k.lower() for k in cfg.title_keywords]
    picked: list[Source] = []
    for e in entries:
        title = (e.get("title") or "").strip()
        if keys and not any(k in title.lower() for k in keys):
            continue
        url = e.get("url") or e.get("webpage_url") or f"https://www.twitch.tv/videos/{e.get('id')}"
        picked.append(Source(id=str(e.get("id") or len(picked)), url=url, title=title,
                             duration=float(e.get("duration") or 0)))
        if len(picked) >= cfg.max_vods:
            break
    log.info("Scanned %d archive entries, %d match %s", len(entries), len(picked), cfg.game_name)
    if not picked:
        log.warning("No VOD titles matched %s. Pass --vod URL to choose VODs explicitly, "
                    "or --title-keyword '' to accept any title.", list(cfg.title_keywords))
    return picked


def download_audio(src: Source, cfg: Config) -> bool:
    """Download the audio-only rendition used for analysis. Returns False to skip."""
    _require_ytdlp()
    out_dir = cfg.temp_dir / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = _ydl_opts(cfg, format="bestaudio/worst", outtmpl=str(out_dir / f"{src.id}.%(ext)s"))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(src.url, download=True)
            path = Path(ydl.prepare_filename(info))
    except DownloadError as exc:
        log.warning("Skipping VOD %s (unavailable/private/restricted): %s", src.url, exc)
        return False
    src.audio_path = path
    src.title = info.get("title") or src.title
    src.id = str(info.get("id") or src.id)
    src.url = info.get("webpage_url") or src.url
    src.duration = float(info.get("duration") or 0)
    log.info("Audio ready for '%s' (%.0f min)", src.title, src.duration / 60)
    return True


def local_source(path: Path, index: int) -> Source:
    return Source(id=f"local{index}_{path.stem}", url=str(path.resolve()), title=path.stem,
                  audio_path=path, local_video=path)


def fetch_clip(src: Source, start: float, end: float, cfg: Config, pad: float = 8.0) -> SourceClip:
    """Make the video for [start, end] available locally (download only that range)."""
    if src.local_video is not None:
        return SourceClip(path=src.local_video, offset=0.0)

    _require_ytdlp()
    a, b = max(0.0, start - pad), end + pad
    out_dir = cfg.temp_dir / "video"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{src.id}_{int(a)}_{int(b)}.mp4"
    if not out.exists():
        opts = _ydl_opts(
            cfg,
            format="bv*[height<=1080]+ba/b[height<=1080]/b",
            outtmpl=str(out.with_suffix(".%(ext)s")),
            download_ranges=download_range_func(None, [(a, b)]),
            merge_output_format="mp4",
        )
        ff_in = _ffmpeg_proxy_setup()
        if ff_in:
            opts["external_downloader_args"] = {"ffmpeg_i": ff_in}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([src.url])
        if not out.exists():  # yt-dlp may pick another container
            cands = sorted(out_dir.glob(out.stem + ".*"))
            if not cands:
                raise RuntimeError("yt-dlp produced no file")
            out = cands[0]
    # HLS range downloads snap to segment boundaries: measure the real offset
    offset = align_offset(src.audio_path, out, guess=a) if src.audio_path else a
    return SourceClip(path=out, offset=offset)


def _envelope(x: np.ndarray, sr: int, rate: int = 100) -> np.ndarray:
    hop = sr // rate
    n = len(x) // hop
    env = np.abs(x[: n * hop]).reshape(n, hop).mean(axis=1)
    env = np.diff(env, prepend=env[:1])  # onset-like, robust to gain differences
    return (env - env.mean()) / (env.std() + 1e-9)


def align_offset(reference_audio: Path, clip: Path, guess: float, search: float = 20.0) -> float:
    """Find the source time of the clip's first sample by audio cross-correlation."""
    sr, rate = 8000, 100
    try:
        clip_audio = read_audio(clip, 0, 40, sr)
        ref_start = max(0.0, guess - search)
        ref_audio = read_audio(reference_audio, ref_start, 40 + 2 * search, sr)
        a, r = _envelope(clip_audio, sr, rate), _envelope(ref_audio, sr, rate)
        if len(a) < rate * 5 or len(r) < len(a):
            return guess
        corr = np.correlate(r, a, mode="valid")
        best = int(np.argmax(corr))
        quality = corr[best] / len(a)
        if quality < 0.2:
            log.debug("Low alignment confidence (%.2f); using requested start", quality)
            return guess
        return ref_start + best / rate
    except Exception as exc:  # noqa: BLE001 - alignment is best effort
        log.debug("Alignment failed (%s); using requested start", exc)
        return guess
