"""Time a known script against a transcript with character/word timings (ElevenLabs Scribe through Creative Claw
`transcribe`, or any JSON with words [{text, start, end}]), then cut subtitles on the real timings.

Usage: python -I align_script.py <transcript.json> <script_lines.json|script.txt> <out_prefix> [--max-width 40] [--offset 0]
  transcript.json  Scribe diarization JSON (diarization_url of the transcribe result; Thai comes back one character per
                   entry) or any {"words": [{"text", "start", "end"}]}
  script           JSON list of lines, or a text file with one line per row (the subtitle text; spaces mark split points)
Writes <out_prefix>_timing.json ([{n, start, end, text}], same format as line_timing.json) and <out_prefix>.srt.
Prints per-line times and the character error rate between script and transcript (it includes real deviations
from the script, such as a false start or a misread number, so read the transcript text for those).

Ayutthaya test (130 s, Thai, phone recording): all 17 lines found, starts within 0.08 s of hand-tuned times
(median 0.03 s); Whisper small with the script as a prompt had found 11 of 17.
"""
import argparse, difflib, json, pathlib, sys, unicodedata


def chars_with_times(tr):
    out = []
    for w in tr["words"]:
        if w.get("type", "word") != "word": continue
        t = w["text"].replace(" ", ""); n = len(t)
        for k, c in enumerate(t):
            out.append((c, w["start"] + (w["end"] - w["start"]) * k / n, w["start"] + (w["end"] - w["start"]) * (k + 1) / n))
    return out


def width(s): return sum(1 for ch in s if unicodedata.category(ch) != "Mn")


def ts(v):
    v = max(0.0, v); return "%02d:%02d:%02d,%03d" % (v // 3600, v % 3600 // 60, int(v % 60), round(v % 1 * 1000) % 1000)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript"); ap.add_argument("script"); ap.add_argument("out_prefix")
    ap.add_argument("--max-width", type=int, default=40); ap.add_argument("--offset", type=float, default=0.0)
    a = ap.parse_args()
    tr = json.load(open(a.transcript, encoding="utf-8"))
    p = pathlib.Path(a.script)
    lines = json.load(open(p, encoding="utf-8")) if p.suffix == ".json" else [l.strip() for l in open(p, encoding="utf-8") if l.strip()]
    ch = chars_with_times(tr); hyp = "".join(c for c, _, _ in ch)
    ref, owner, pos = "", [], []          # pos: (line, index of the char inside the line text)
    for i, l in enumerate(lines):
        for j, c in enumerate(l):
            if c != " ": ref += c; owner.append(i); pos.append((i, j))
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    t_of = {}                              # (line, char index) -> (start, end)
    for x, y, n in sm.get_matching_blocks():
        for k in range(n): t_of[pos[x + k]] = ch[y + k][1:]
    err = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")
    timing, cues, missing = [], [], []
    for i, l in enumerate(lines):
        hits = sorted(v for (li, _), v in t_of.items() if li == i)
        if not hits: missing.append(i + 1); continue
        s, e = hits[0][0] + a.offset, max(h[1] for h in hits) + a.offset
        timing.append({"n": i + 1, "start": round(s, 3), "end": round(e, 3), "text": l})
        # subtitle pieces: split at spaces, <= max-width visible characters, timed by the real characters inside them
        pieces, cur, cur_idx = [], "", []
        idx = 0
        for word in l.split(" "):
            w_idx = list(range(idx, idx + len(word))); idx += len(word) + 1
            if cur and width(cur) + 1 + width(word) > a.max_width: pieces.append((cur, cur_idx)); cur, cur_idx = word, w_idx
            else: cur = (cur + " " + word).strip(); cur_idx = cur_idx + w_idx
        pieces.append((cur, cur_idx))
        prev_end = s
        for k, (txt, ids) in enumerate(pieces):
            tt = [t_of[(i, j)] for j in ids if (i, j) in t_of]
            p0 = (tt[0][0] + a.offset) if tt else prev_end
            p1 = (max(x[1] for x in tt) + a.offset) if tt else p0 + 1.0
            p0 = max(p0, prev_end)
            cues.append([p0, p1, txt]); prev_end = p1
    for k in range(len(cues) - 1):        # hold each cue until the next one when the gap is short, at least 0.8 s on screen
        nxt = cues[k + 1][0]
        if nxt - cues[k][1] < 0.6: cues[k][1] = nxt
        cues[k][1] = min(max(cues[k][1], cues[k][0] + 0.8), nxt)
    cues[-1][1] = max(cues[-1][1], cues[-1][0] + 0.8)
    json.dump(timing, open(a.out_prefix + "_timing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(a.out_prefix + ".srt", "w", encoding="utf-8").write("\n".join(f"{k + 1}\n{ts(s)} --> {ts(e)}\n{t}\n" for k, (s, e, t) in enumerate(cues)))
    for t in timing: print(f"{t['n']:2d} {t['start']:7.2f}-{t['end']:7.2f}  {t['text'][:40]}")
    print(f"{len(timing)}/{len(lines)} lines timed, {len(cues)} subtitle cues, CER {100 * err / max(1, len(ref)):.1f}% (script vs transcript)")
    if missing: print("NOT FOUND in the transcript: lines", missing)
