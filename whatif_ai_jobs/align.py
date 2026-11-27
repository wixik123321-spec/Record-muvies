"""Этап 4а — таймкоды слов: faster-whisper (ru) по voiceover.wav, сопоставление со сценарием.

Распознанные слова сопоставляются с текстом сценария (difflib), поэтому в субтитрах всегда
исходный текст без ошибок распознавания, а время — реальное. Несопоставленные слова получают
время интерполяцией между соседями. Результат: build/timing.json и subtitles.srt.
"""

import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

CODE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("WHATIF_ROOT") or CODE).resolve()   # папка проекта (по умолчанию — эта)
sys.path.insert(0, str(CODE.parent / "ai_shorts_ru"))

END_HOLD = float(os.environ.get("END_HOLD", 9.0))   # конечная заставка держится после последних слов (под элементы YouTube)


def norm(w: str) -> str:
    return re.sub(r"[^\wё]", "", w.lower().replace("ё", "е"))


def main():
    from faster_whisper import WhisperModel
    data = json.loads((ROOT / "build" / "shots.json").read_text(encoding="utf-8"))
    shots = data["shots"]
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(ROOT / "voiceover.wav"), "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, np.float32)
    total = len(audio) / 16000
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language="ru", word_timestamps=True, beam_size=5, vad_filter=False)
    rec = [(norm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if norm(w.word)]
    print(f"распознано слов: {len(rec)}")

    script_words = []  # (shot_idx, word)
    for i, s in enumerate(shots):
        for w in s["text"].split():
            script_words.append((i, w))
    a = [norm(w) for _, w in script_words]
    b = [r[0] for r in rec]
    times = [None] * len(a)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    matched = 0
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            times[blk.a + k] = (rec[blk.b + k][1], rec[blk.b + k][2])
            matched += 1
    print(f"сопоставлено со сценарием: {matched}/{len(a)} слов ({matched / max(1, len(a)):.0%})")
    # интерполяция пропусков
    known = [k for k, t in enumerate(times) if t]
    for k in range(len(times)):
        if times[k] is None:
            prev = max([j for j in known if j < k], default=None)
            nxt = min([j for j in known if j > k], default=None)
            t0 = times[prev][1] if prev is not None else 0.0
            t1 = times[nxt][0] if nxt is not None else total
            n_gap = (nxt if nxt is not None else len(times)) - (prev if prev is not None else -1) - 1
            pos = k - (prev if prev is not None else -1)
            step = (t1 - t0) / (n_gap + 1)
            times[k] = (t0 + step * (pos - 0.5), t0 + step * (pos + 0.4))
    # монотонность
    for k in range(1, len(times)):
        s0, e0 = times[k - 1]
        s1, e1 = times[k]
        if s1 < e0 - 0.02:
            s1 = e0
        times[k] = (s1, max(e1, s1 + 0.06))

    words = [{"shot": i, "w": w, "s": round(t[0], 3), "e": round(t[1], 3)} for (i, w), t in zip(script_words, times)]
    line = []
    for i, s in enumerate(shots):
        ws = [w for w in words if w["shot"] == i]
        line.append({"id": s["id"], "start": ws[0]["s"], "end": ws[-1]["e"]})
    # кадр начинается чуть раньше своей строки и длится до начала следующей
    lead = 0.25
    for i, l in enumerate(line):
        l["shot_start"] = 0.0 if i == 0 else round(max(line[i - 1]["end"], l["start"] - lead), 3)
    for i, l in enumerate(line):
        l["shot_end"] = line[i + 1]["shot_start"] if i + 1 < len(line) else round(total + END_HOLD, 3)
    timing = {"duration": round(total + END_HOLD, 3), "voice_duration": round(total, 3), "match_ratio": matched / len(a),
              "lines": line, "words": words}
    (ROOT / "build" / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
    write_srt(shots, words)
    print(f"длительность видео: {timing['duration']:.1f} с")


def make_phrases(words):
    """Фразы субтитров по 1–2 строки (до ~7 слов), с разрывом на знаках препинания и паузах.
    Возвращает [(слова, начало, конец)] — одни и те же фразы в видео и в subtitles.srt."""
    phrases, cur = [], []
    for w in words:
        if cur and (len(cur) >= 7 or w["shot"] != cur[-1]["shot"] or w["s"] - cur[-1]["e"] > 0.5):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w["w"]) or (re.search(r"[,;:—]$", w["w"]) and len(cur) >= 4):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    out = []
    for n, ph in enumerate(phrases):
        end = min(ph[-1]["e"] + 0.4, phrases[n + 1][0]["s"]) if n + 1 < len(phrases) else ph[-1]["e"] + 0.8
        out.append((ph, ph[0]["s"], end))
    return out


def write_srt(shots, words):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    out = []
    for n, (ph, s, e) in enumerate(make_phrases(words), 1):
        out += [str(n), f"{ts(s)} --> {ts(e)}", " ".join(w["w"] for w in ph), ""]
    (ROOT / "subtitles.srt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
