"""End-to-end smoke test on a synthetic "stream" (no network, no Whisper model).

Builds an 8-minute 1920x1080 video with a facecam overlay and periodic loud
"reactions", replaces Whisper with a fake transcriber, runs the full pipeline
and checks the exported Shorts.

    python tests/e2e_synthetic.py path/to/face.png
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shorts_maker import pipeline  # noqa: E402
from shorts_maker.config import Config  # noqa: E402
from shorts_maker.transcribe import Word  # noqa: E402
from shorts_maker.utils import ffprobe  # noqa: E402

DURATION = 480
PERIOD = 40  # a "reaction" every 40 s, at t = 20, 60, 100, ...

LINES = ["Okay chat we are driving to the bank right now.",
         "Wait wait wait, who is that guy?",
         "Bro he is following us!",
         "No way. NO WAY! Oh my god, the cops!",
         "Run run run, haha that was crazy!"]


class FakeTranscriber:
    def __init__(self, cfg):
        pass

    def transcribe(self, media, start, duration):
        words, t = [], start
        while t < start + duration - 1:
            k = int(t // PERIOD)
            phase = t - k * PERIOD
            line = LINES[3] if 19 <= phase < 23 else LINES[(int(t) // 7) % len(LINES)]
            for w in line.split():
                words.append(Word(t, t + 0.28, w))
                t += 0.33
            t += 0.9 if phase < 30 else 2.5  # long pauses after the reaction
        return words


def make_video(face: Path, out: Path) -> None:
    loud = f"if(between(mod(t\\,{PERIOD})\\,20\\,23)\\,0.8\\,0.05)"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={DURATION}",
        "-loop", "1", "-i", str(face),
        "-f", "lavfi", "-i", f"aevalsrc='{loud}*sin(2*PI*(300+200*sin(3*t))*t)"
                             f"+0.02*(random(0)-0.5)':s=48000:d={DURATION}",
        "-filter_complex", "[1:v]scale=320:320[f];[0:v][f]overlay=40:H-h-40:shortest=1[v]",
        "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-t", str(DURATION), str(out)], check=True)


def main() -> int:
    from shorts_maker.utils import setup_logging
    setup_logging()
    face = Path(sys.argv[1])
    work = Path(tempfile.mkdtemp(prefix="shorts_e2e_"))
    src = work / "stream.mp4"
    print("building synthetic stream…")
    make_video(face, src)

    pipeline.Transcriber = FakeTranscriber
    cfg = Config(input_files=[src], output_dir=work / "shorts", temp_dir=work / "tmp",
                 target_clips=4, min_clips=3, use_llm=False, x264_preset="ultrafast",
                 min_gap_between_candidates=30, overwrite=True, font_name="DejaVu Sans")
    rc = pipeline.run_pipeline(cfg)
    files = sorted((work / "shorts").glob("*.mp4"))
    print("exit code", rc, "files", [f.name for f in files])
    assert rc == 0 and len(files) == 4, "expected 4 clips"
    for f in files:
        info = ffprobe(f)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (v["width"], v["height"]) == (1080, 1920) and v["codec_name"] == "h264"
        assert 20 <= float(info["format"]["duration"]) <= 62, f.name
        assert f.with_suffix(".txt").exists()
    rows = list(csv.DictReader(open(work / "shorts" / "clips_manifest.csv", encoding="utf-8")))
    assert all(r["status"] == "ok" for r in rows), rows
    print("layouts:", {r["layout"] for r in rows}, "issues:", [r["issues"] for r in rows])
    print("OK ->", work / "shorts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
