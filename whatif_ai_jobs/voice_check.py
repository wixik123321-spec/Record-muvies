"""Проверка озвучки: распознать voiceover.wav (faster-whisper, ru) и сравнить со сценарием.

Показывает места, где распознанный текст расходится со сценарием, — кандидаты на неразборчивое
или неверное произношение. Расхождения из-за чисел/латиницы/имён Whisper пишет по-своему, их видно сразу.
WHATIF_ROOT=папка python voice_check.py   →  build/voice_check.txt
"""
import difflib
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("WHATIF_ROOT") or CODE).resolve()


def norm(w):
    return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


def main():
    from faster_whisper import WhisperModel
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ROOT / "voiceover.wav"), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    segs, _ = WhisperModel("small", device="cpu", compute_type="int8").transcribe(
        audio, language="ru", word_timestamps=True, beam_size=5)
    rec = [(w.word.strip(), w.start) for s in segs for w in (s.words or []) if norm(w.word)]
    shots = json.loads((ROOT / "build" / "shots.json").read_text(encoding="utf-8"))["shots"]
    script = [w for s in shots for w in s["text"].split()]
    a, b = [norm(w) for w in script], [norm(w) for w, _ in rec]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out, same = [], 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            same += i2 - i1
            continue
        t = rec[j1][1] if j1 < len(rec) else (rec[-1][1] if rec else 0)
        out.append(f"{int(t // 60)}:{t % 60:04.1f}  сценарий: {' '.join(script[i1:i2]) or '—'}  |  слышно: "
                   f"{' '.join(w for w, _ in rec[j1:j2]) or '—'}")
    head = f"совпало слов: {same}/{len(script)} ({same / len(script):.1%}); расхождений: {len(out)}"
    (ROOT / "build" / "voice_check.txt").write_text(head + "\n" + "\n".join(out), encoding="utf-8")
    print(head)
    print("\n".join(out))


if __name__ == "__main__":
    main()
