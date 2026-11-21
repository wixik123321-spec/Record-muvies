"""Swap the narration of a finished edit without re-tuning it: lay out new per-line voice files, then map times
between the new timeline and the old one (piecewise linear, anchors at every line start and end).

Usage
  python -I retime.py lay <old_timing.json> <lines_dir> <out_prefix> [--lead 1.4] [--pause 0.8]
                          [--section-pause 1.2] [--section-after 2,6,10,14] [--tail 2.6] [--old-dur 124.5]
      old_timing.json: [{"n", "start", "end", "text"}, ...] tuned to the old voice (keep it, e.g. line_timing_user.json)
      lines_dir: one audio file per line matching --pattern (default line*), sorted by name (line01.mp3, ...),
                 same count as old_timing.json; samples like sample_1-3.mp3 in the same folder are ignored
      writes <out_prefix>_timing.json (same format, new times), <out_prefix>_map.json (anchors) and <out_prefix>_voice.wav
      (the lines placed on the new timeline, mono 44.1 kHz, no processing)
  python -I retime.py map <out_prefix>_map.json <seconds> [--to old|new]     print one mapped time (default: new -> old)

In code (compositor, effects, music bed), keep every cue on the OLD timeline and convert:
  from retime import load_map; to_old, to_new, new_dur = load_map("v2_map.json")
  frame on the new timeline: render(to_old(i / FPS));  effect cue: at to_new(t_old);  music section: to_new(start), to_new(end)
"""
import argparse, json, pathlib, subprocess, sys, wave

SR = 44100


def _interp(x, xs, ys):
    if x <= xs[0]: return ys[0]
    for k in range(1, len(xs)):
        if x <= xs[k]:
            return ys[k - 1] + (ys[k] - ys[k - 1]) * (x - xs[k - 1]) / (xs[k] - xs[k - 1])
    return ys[-1]


def load_map(path):
    m = json.load(open(path, encoding="utf-8")); new, old = m["new"], m["old"]
    return (lambda t: _interp(t, new, old)), (lambda t: _interp(t, old, new)), new[-1]


def _decode(path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(float) / 32768


def lay(a):
    import numpy as np
    old = json.load(open(a.old_timing, encoding="utf-8"))
    files = sorted(p for p in pathlib.Path(a.lines_dir).glob(a.pattern) if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"))
    if len(files) != len(old):
        sys.exit(f"{len(files)} audio files but {len(old)} lines in {a.old_timing}")
    section_after = {int(x) for x in a.section_after.split(",") if x}
    clips, lines, t = [], [], a.lead
    for ln, f in zip(old, files):
        x = _decode(f); d = len(x) / SR; clips.append((t, x))
        lines.append({"n": ln["n"], "start": round(t, 3), "end": round(t + d, 3), "text": ln["text"], "file": f.name})
        t += d + (a.section_pause if ln["n"] in section_after else a.pause)
    new_dur = lines[-1]["end"] + a.tail
    old_dur = a.old_dur if a.old_dur else old[-1]["end"] + a.tail
    anchors = {"new": [0.0] + [v for ln in lines for v in (ln["start"], ln["end"])] + [round(new_dur, 3)],
               "old": [0.0] + [v for ln in old for v in (ln["start"], ln["end"])] + [old_dur]}
    p = a.out_prefix
    json.dump(lines, open(f"{p}_timing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(anchors, open(f"{p}_map.json", "w", encoding="utf-8"), indent=1)
    voice = np.zeros(int(new_dur * SR) + 1)
    for s, x in clips:
        i = int(s * SR); voice[i:i + len(x)] += x[: len(voice) - i]
    with wave.open(f"{p}_voice.wav", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(voice, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"new duration {new_dur:.2f} s (old {old_dur:.2f} s)")
    for o, n in zip(old, lines):
        print(f"line {n['n']:2d}: old {o['start']:7.2f}-{o['end']:7.2f}  new {n['start']:7.2f}-{n['end']:7.2f}  "
              f"stretch {(n['end'] - n['start']) / (o['end'] - o['start']):.2f}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("lay"); l.add_argument("old_timing"); l.add_argument("lines_dir"); l.add_argument("out_prefix")
    l.add_argument("--lead", type=float, default=1.4); l.add_argument("--pause", type=float, default=0.8)
    l.add_argument("--section-pause", type=float, default=1.2); l.add_argument("--section-after", default="")
    l.add_argument("--tail", type=float, default=2.6); l.add_argument("--pattern", default="line*"); l.add_argument("--old-dur", type=float, default=None)
    m = sub.add_parser("map"); m.add_argument("map_json"); m.add_argument("seconds", type=float)
    m.add_argument("--to", choices=["old", "new"], default="old")
    a = ap.parse_args()
    if a.cmd == "lay":
        lay(a)
    else:
        to_old, to_new, _ = load_map(a.map_json)
        print(f"{(to_old if a.to == 'old' else to_new)(a.seconds):.3f}")
