"""Output verification, manifest and per-clip metadata files."""

from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from .config import Config
from .highlights import Candidate
from .utils import ffprobe, fmt_ts, log, twitch_time_param


def verify_mp4(path: Path, cfg: Config, expected: float) -> list[str]:
    """Return a list of problems (empty = OK). Decodes the whole file."""
    problems = []
    try:
        info = ffprobe(path)
    except Exception as exc:  # noqa: BLE001
        return [f"ffprobe failed: {exc}"]
    v = [s for s in info["streams"] if s.get("codec_type") == "video"]
    a = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    if not v or v[0].get("codec_name") != "h264":
        problems.append("video is not H.264")
    elif (int(v[0]["width"]), int(v[0]["height"])) != (cfg.width, cfg.height):
        problems.append(f"resolution {v[0]['width']}x{v[0]['height']}")
    if not a or a[0].get("codec_name") != "aac":
        problems.append("audio is not AAC")
    dur = float(info["format"].get("duration", 0))
    if abs(dur - expected) > 1.0:
        problems.append(f"duration {dur:.1f}s, expected {expected:.1f}s")
    dec = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True)
    if dec.returncode != 0 or dec.stderr.strip():
        problems.append("decode errors: " + dec.stderr.strip()[:300])
    return problems


def _ass_events(ass: Path) -> list[tuple[float, float]]:
    out = []
    for line in ass.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            f = line.split(",", 3)
            out.append((_parse_ts(f[1]), _parse_ts(f[2])))
    return out


def _parse_ts(s: str) -> float:
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def verify_captions(video: Path, ass: Path, caption_y: int, cfg: Config, duration: float) -> list[str]:
    """Events exist, lie inside the video, and visibly change pixels where drawn."""
    events = _ass_events(ass)
    if not events:
        return ["no caption events (no speech?)"]
    problems = []
    if any(e > duration + 0.2 or s < 0 for s, e in events):
        problems.append("caption timing outside the video")
    # pixel check: the caption band should contain many near-white pixels while a
    # caption is on screen
    s, e = events[len(events) // 2]
    t = (s + e) / 2
    band = (max(0, caption_y - cfg.font_size), min(cfg.height, caption_y + cfg.font_size))
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    if raw.returncode == 0 and len(raw.stdout) == cfg.width * cfg.height:
        img = np.frombuffer(raw.stdout, np.uint8).reshape(cfg.height, cfg.width)
        # the black caption outline is present whatever the text colour
        dark = float((img[band[0]:band[1]] < 20).mean())
        if dark < 0.005:
            problems.append("captions not clearly visible in sampled frame")
    return problems


def clip_filename(rank: int, c: Candidate, cfg: Config) -> str:
    name = c.short_name or c.title or "Highlight"
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:50] or "Highlight"
    game = cfg.game_name.replace(" ", "")
    if not name.lower().startswith(game.lower()) and "kai" not in name.lower():
        name = f"{game}_{name}"
    return f"{rank:02d}_{name}.mp4"


def vod_link(c: Candidate) -> str:
    url = c.source.url
    if "twitch.tv/videos/" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}t={twitch_time_param(c.start)}"
    return url


def write_clip_text(path: Path, c: Candidate) -> None:
    text = (f"TITLE:\n{c.title}\n\nDESCRIPTION:\n{c.description}\n\n"
            f"Source VOD: {vod_link(c)} (at {fmt_ts(c.start)})\n\n"
            f"HASHTAGS:\n{' '.join(c.hashtags)}\n")
    path.write_text(text, encoding="utf-8")


def write_manifest(rows: list[dict], out_dir: Path) -> None:
    if not rows:
        return
    fields = ["rank", "file", "status", "title", "score", "category", "duration_s",
              "source_title", "source_url", "vod_link", "start", "end", "layout",
              "description", "hashtags", "reason", "issues"]
    with open(out_dir / "clips_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(out_dir / "sources.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['file']}\t{r['vod_link']}\n")
    with open(out_dir / "youtube_metadata.txt", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"=== {r['file']} ===\nTitle: {r['title']}\n\n{r['description']}\n\n"
                    f"{r['hashtags']}\nSource: {r['vod_link']}\n\n")
    (out_dir / "clips_manifest.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
    log.info("Wrote clips_manifest.csv, sources.txt and youtube_metadata.txt")
