"""Этап 2 — озвучка → voiceover.mp3 (+ voiceover.wav), нормализация до -16 LUFS.

Источники голоса:
  python voice.py vosk [--speed 0.92]           офлайн-голос Vosk (male_1), по строкам
  python voice.py files DIR                      готовые куски по разделам (например, из ElevenLabs):
                                                 DIR/01_hook.mp3, 02_day1.mp3, ... в порядке разделов
Между строками — 0.35 с, между разделами — 0.6 с тишины.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("WHATIF_ROOT") or CODE).resolve()   # папка проекта (по умолчанию — эта)
sys.path.insert(0, str(CODE.parent / "ai_shorts_ru"))
from shorts_ru import tts  # noqa: E402

SR = tts.SR
LINE_GAP, SECTION_GAP = 0.35, 0.6


def load_shots():
    return json.loads((ROOT / "build" / "shots.json").read_text(encoding="utf-8"))


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def finish(sections: list[np.ndarray], names: list[str]):
    out = ROOT / "build"
    parts = []
    for i, x in enumerate(sections):
        tts._write_wav(out / f"voice_section_{i + 1:02d}_{names[i]}.wav", x)
        parts += [x, np.zeros(int(SECTION_GAP * SR), np.float32)]
    full = np.concatenate([np.zeros(int(0.3 * SR), np.float32)] + parts)
    raw = out / "voiceover_raw.wav"
    tts._write_wav(raw, full)
    # двухпроходная нормализация громкости голоса до -16 LUFS
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af",
                            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", af, "-ar", str(SR), "-ac", "1",
                    str(ROOT / "voiceover.wav")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(ROOT / "voiceover.wav"), "-c:a", "libmp3lame",
                    "-b:a", "192k", str(ROOT / "voiceover.mp3")], check=True)
    dur = len(full) / SR
    print(f"voiceover.mp3: {dur:.1f} с ({dur / 60:.2f} мин)")
    return dur


def from_vosk(speed: float, voice: str = "male_1"):
    data = load_shots()
    engine = tts.VoskTTS(voice, speed)
    sections, names = [], []
    for sec, _, _ in data["sections"]:
        lines = [s for s in data["shots"] if s["section"] == sec]
        chunks = []
        for j, s in enumerate(lines):
            tmp = ROOT / "build" / "tmp_line.wav"
            x, _ = engine.synth(s["text"], tmp)
            x = tts.polish(x)
            chunks.append(x)
            gap = LINE_GAP + (0.25 if s["visual"] == "card" else 0.0)  # после заставки раздела — чуть дольше
            if j < len(lines) - 1:
                chunks.append(np.zeros(int(gap * SR), np.float32))
            print(f"  {s['id']:3d} {len(x) / SR:5.1f} с  {s['text'][:60]}", flush=True)
        sections.append(np.concatenate(chunks))
        names.append(sec)
    (ROOT / "build" / "tmp_line.wav").unlink(missing_ok=True)
    return finish(sections, names)


def from_files(folder: Path):
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".mp3", ".wav"))
    data = load_shots()
    if len(files) != len(data["sections"]):
        raise SystemExit(f"Ожидалось {len(data['sections'])} файлов (по разделам), найдено {len(files)}")
    return finish([decode(f) for f in files], [s[0] for s in data["sections"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["vosk", "files"])
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--speed", type=float, default=0.92)
    a = ap.parse_args()
    if a.source == "vosk":
        from_vosk(a.speed)
    else:
        from_files(Path(a.folder))
