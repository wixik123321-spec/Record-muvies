"""Render one Short with a single FFmpeg pass.

Graph: seek -> 30 fps -> 9:16 layout -> split into timeline pieces (trim,
punch zoom) -> concat -> burn animated ASS captions; audio is cut in sync,
optionally mixed with a light SFX on zoom-ins and loudness-normalised to
-14 LUFS (YouTube's playback target).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config
from .layout import Layout
from .timeline import Piece
from .utils import ToolError, log


def _even(v: float) -> int:
    return max(2, int(round(v)) // 2 * 2)


def render(src_path: Path, src_offset: float, pieces: list[Piece], layout: Layout,
           ass_path: Path, out_path: Path, cfg: Config) -> None:
    W, H, n = cfg.width, cfg.height, len(pieces)
    seek = max(0.0, min(p.start for p in pieces) - src_offset - 0.5)
    base = src_offset + seek  # source time of input t=0 after seeking

    g = [f"[0:v]fps={cfg.fps},setpts=PTS-STARTPTS[in]", layout.filter(W, H),
         f"[lay]split={n}" + "".join(f"[v{i}]" for i in range(n)),
         "[0:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS,"
         f"asplit={n}" + "".join(f"[a{i}]" for i in range(n))]
    concat_in = ""
    for i, p in enumerate(pieces):
        a, b = p.start - base, p.end - base
        zoom = ""
        if p.zoom > 1.0:
            zw, zh = _even(W * p.zoom), _even(H * p.zoom)
            zoom = f",scale={zw}:{zh}:flags=lanczos,crop={W}:{H}:{(zw - W) // 2}:{(zh - H) // 2}"
        g.append(f"[v{i}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS{zoom},setsar=1[pv{i}]")
        g.append(f"[a{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[pa{i}]")
        concat_in += f"[pv{i}][pa{i}]"
    g.append(f"{concat_in}concat=n={n}:v=1:a=1[cv][ca]")
    # bare file name: FFmpeg runs inside the subtitle folder (avoids Windows path escaping)
    g.append(f"[cv]subtitles={ass_path.name}[vout]")

    audio = "[ca]"
    if cfg.loudnorm:
        g.append("[ca]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[ln]")
        audio = "[ln]"

    inputs = ["-ss", f"{seek:.3f}", "-i", str(src_path.resolve())]
    sfx_times = []
    t = 0.0
    for prev, p in zip([None] + pieces, pieces):
        if p.zoom > 1.0 and (prev is None or prev.zoom == 1.0) and t > 0.3:
            sfx_times.append(t)
        t += p.duration
    if cfg.sfx_file and Path(cfg.sfx_file).exists() and sfx_times:
        inputs += ["-i", str(Path(cfg.sfx_file).resolve())]
        m = len(sfx_times)
        g.append(f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={cfg.sfx_volume},"
                 f"asplit={m}" + "".join(f"[s{i}]" for i in range(m)))
        for i, st in enumerate(sfx_times):
            ms = int(st * 1000)
            g.append(f"[s{i}]adelay={ms}|{ms}[sd{i}]")
        g.append(f"{audio}" + "".join(f"[sd{i}]" for i in range(m))
                 + f"amix=inputs={m + 1}:duration=first:normalize=0[mix]")
        audio = "[mix]"

    total = sum(p.duration for p in pieces)
    cmd = ["ffmpeg", "-y", "-v", "error", "-nostdin", *inputs,
           "-filter_complex", ";".join(g),
           "-map", "[vout]", "-map", audio,
           "-c:v", "libx264", "-preset", cfg.x264_preset, "-crf", str(cfg.crf),
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(cfg.fps),
           "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000",
           "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_path.resolve())]
    log.debug("ffmpeg graph: %s", ";".join(g))
    proc = subprocess.run(cmd, cwd=str(ass_path.parent), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ToolError(f"ffmpeg render failed:\n{proc.stderr[-2500:]}")

