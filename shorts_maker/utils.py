"""Small shared helpers: logging, subprocess wrappers, ffprobe, audio decoding."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger("shorts")


class ToolError(RuntimeError):
    """An external tool (ffmpeg/ffprobe/yt-dlp) failed."""


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def require_binaries(*names: str) -> None:
    missing = [n for n in names if shutil.which(n) is None]
    if missing:
        raise SystemExit(
            f"Missing required program(s): {', '.join(missing)}. "
            "Install FFmpeg (https://ffmpeg.org/download.html) and make sure it is on PATH."
        )


def run(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess:
    log.debug("run: %s", " ".join(map(str, cmd)))
    proc = subprocess.run(cmd, capture_output=capture, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:]
        raise ToolError(f"{Path(cmd[0]).name} failed ({proc.returncode}):\n{tail}")
    return proc


def ffprobe(path: Path) -> dict:
    out = run(["ffprobe", "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", str(path)]).stdout
    return json.loads(out)


def media_duration(path: Path) -> float:
    return float(ffprobe(path)["format"].get("duration", 0.0))


def video_size(path: Path) -> tuple[int, int]:
    for s in ffprobe(path)["streams"]:
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise ToolError(f"No video stream in {path}")


def read_audio(path: Path, start: float = 0.0, duration: float | None = None,
               sr: int = 16000) -> np.ndarray:
    """Decode a slice of any media file to mono float32 PCM at ``sr`` Hz."""
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise ToolError(proc.stderr.decode(errors="ignore")[-1500:])
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def slugify(text: str, max_len: int = 48) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return (text[:max_len].rstrip("_")) or "Clip"


def fmt_ts(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def twitch_time_param(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m}m{s}s"
