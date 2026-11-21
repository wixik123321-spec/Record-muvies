"""Transcribe locally with faster-whisper (free; good for English, NOT for Thai - use Creative Claw `transcribe` there).
Writes the same JSON shape as a Scribe diarization file, so align_script.py, edit plans and cut tools can read either.

Usage: python -I transcribe_whisper.py <media> <out_prefix> [--model medium] [--lang en] [--prompt "names, terms"]
  -> <out_prefix>.json  {"language", "duration", "words": [{"text", "start", "end", "type": "word", "prob"}],
                         "segments": [{"start", "end", "text"}]}
  -> <out_prefix>.srt   one cue per segment (check and split long ones before burning in)
Models already downloaded here: base.en, small, medium (Systran/faster-whisper-*). Downloading another model is a
download: ask first. medium on CPU runs roughly at real time to 2x real time.
"""
import argparse, json, sys


def ts(v):
    v = max(0.0, v); return "%02d:%02d:%02d,%03d" % (v // 3600, v % 3600 // 60, int(v % 60), round(v % 1 * 1000) % 1000)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media"); ap.add_argument("out_prefix"); ap.add_argument("--model", default="medium")
    ap.add_argument("--lang", default=None); ap.add_argument("--prompt", default=None)
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, info = model.transcribe(a.media, language=a.lang, word_timestamps=True, vad_filter=True, initial_prompt=a.prompt)
    words, segments = [], []
    for s in segs:
        segments.append({"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip()})
        for w in s.words or []:
            words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "type": "word", "prob": round(w.probability, 3)})
        print(f"{s.start:7.1f}-{s.end:7.1f} {s.text.strip()[:90]}", flush=True)
    json.dump({"language": info.language, "duration": info.duration, "words": words, "segments": segments},
              open(a.out_prefix + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    open(a.out_prefix + ".srt", "w", encoding="utf-8").write(
        "\n".join(f"{k + 1}\n{ts(s['start'])} --> {ts(s['end'])}\n{s['text']}\n" for k, s in enumerate(segments)))
    print(f"{len(segments)} segments, {len(words)} words, language {info.language}")
