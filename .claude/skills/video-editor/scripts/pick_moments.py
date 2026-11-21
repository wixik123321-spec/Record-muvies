"""Pick the key moments of a talking-head edit automatically: which words deserve a big treatment ("behind" words),
and which phrases want a B-roll picture, with search queries for licensed footage.

Usage: python -I pick_moments.py <words.json> <plan.json> [--every 15] [--apply-behind] [--out moments.json]
  words.json  transcribe_whisper.py output (or Scribe JSON) of the source the plan cuts from
Scores every spoken content word that the plan keeps:
  rarity (rarer in this transcript = more specific) x length x stress (held longer and louder than the speaker's
  median, measured on the source audio). Picks one per --every seconds, at least 8 s apart, only on single-person
  close-ups (crop clips without B-roll, split screen or card) that are not punched in (the head would hide
  the word), never inside a B-roll window.
--apply-behind writes them into the plan as "behind" words (red, then orange, yellow... one colour each).
B-roll suggestions: the best-scoring 2-3 word phrase of each kept sentence, as Commons search queries. Downloading
is still a download: show the user file, source, licence and size first.
English (word-spaced) transcripts; Thai needs word segmentation first.
"""
import argparse, json, math, pathlib, re, subprocess, sys
from collections import Counter
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from edit_plan import build_timeline
from word_captions import STOP

COLORS = [[255, 59, 59], [255, 159, 67], [255, 210, 0], [127, 216, 255], [180, 140, 255]]


def clean(t): return re.sub(r"[^\w'-]", "", t.lower())


# common verbs and fillers: fine to say, poor as a big word or an image search (the picker wants concrete nouns)
WEAK = set("""indeed want say said says even means mean ones one right going need needs perhaps tend tendency happen happens
happened come comes came along hour make makes made take takes took give gives look looks see seen use used try tried
keep keeps let lets put puts seem seems feel feels felt tell told ask asked work works call called find found
start started bit lot lots kind sort stuff thing things way ways time times people person yeah okay sure maybe""".split())


def weak(t): return t in WEAK or t.endswith(("ly", "ed", "ing")) and len(t) > 5


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words"); ap.add_argument("plan"); ap.add_argument("--every", type=float, default=15.0)
    ap.add_argument("--apply-behind", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    words = [w for w in json.load(open(a.words, encoding="utf-8"))["words"] if w.get("type", "word") == "word" and clean(w["text"])]
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    tl, total = build_timeline(plan)
    freq = Counter(clean(w["text"]) for w in words); N = len(words)
    src = next(c["src"] for c in plan["clips"] if not c.get("card"))
    srcp = str((pp.parent / src).resolve())
    # loudness of every word, from the source audio (8 kHz mono is plenty)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", srcp, "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], capture_output=True).stdout
    au = np.frombuffer(raw, np.float32)
    def rms(t0, t1):
        seg = au[int(t0 * 8000): int(t1 * 8000)]; return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
    durs = [w["end"] - w["start"] for w in words]; med_d = float(np.median(durs)) or 0.2
    louds = [rms(w["start"], w["end"]) for w in words]; med_l = float(np.median([l for l in louds if l > 0]) or 1e-3)
    full_w = max((c["crop"][2] for c in tl if c.get("crop")), default=0)   # punched-in pieces have a narrower crop
    cand = []
    for w, d, l in zip(words, durs, louds):
        t = clean(w["text"])
        if t in STOP or weak(t) or len(t) < 4 or t.isdigit(): continue
        c = next((c for c in tl if c.get("src") == src and c["in"] <= w["start"] < c["out"]), None)
        if not c or c.get("card") or c.get("fit") in ("stack", "blur") or not c.get("crop") or c.get("captions") is False: continue
        if c["crop"][2] < 0.9 * full_w: continue       # zoomed in: the head fills the width, a word behind it disappears
        tt = c["start"] + (w["start"] - c["in"]) / c["speed"]
        rel = (w["start"] - c["in"]) / c["speed"]
        if any(b["start"] - 0.3 < rel < b["end"] + 0.3 for b in c.get("broll", [])): continue
        rarity = math.log(N / freq[t]); stress = (d / med_d) ** 0.5 * (l / med_l) ** 0.5
        cand.append({"word": w["text"].strip(" ,.?!").upper(), "t": round(tt, 2), "score": round(rarity * len(t) ** 0.5 * stress, 2),
                     "clip_in": c["in"], "rel": round(rel, 2), "rel_end_max": round((c["out"] - c["in"]) / c["speed"], 2)})
    picks = []
    for x in sorted(cand, key=lambda x: -x["score"]):
        if len(picks) >= max(1, int(total // a.every)): break
        if all(abs(x["t"] - p["t"]) >= 8 for p in picks) and x["word"] not in [p["word"] for p in picks]: picks.append(x)
    picks.sort(key=lambda x: x["t"])
    # B-roll: per kept sentence (pause >= 0.35 s splits), the best 2-3 word content phrase
    sentences, cur = [], []
    kept = [w for w in words if any(c.get("src") == src and c["in"] <= w["start"] < c["out"] for c in tl)]
    for w in kept:
        if cur and (w["start"] - cur[-1]["end"] >= 0.35 or re.search(r"[.?!]$", cur[-1]["text"])): sentences.append(cur); cur = []
        cur.append(w)
    if cur: sentences.append(cur)
    broll = []
    for snt in sentences:
        cw = [w for w in snt if clean(w["text"]) not in STOP and not weak(clean(w["text"])) and len(clean(w["text"])) > 2]
        if not cw: continue
        best = max(range(len(cw)), key=lambda i: sum(math.log(N / freq[clean(x["text"])]) for x in cw[i:i + 2]))
        phrase = " ".join(clean(x["text"]) for x in cw[best:best + 2])
        broll.append({"phrase": phrase, "src_time": round(cw[best]["start"], 2), "query": f"{phrase} filetype:video|filetype:bitmap",
                      "sentence": " ".join(w["text"].strip() for w in snt)[:90]})
    out = {"behind": picks, "broll": broll}
    if a.out: json.dump(out, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("behind-word picks:")
    for p in picks: print(f"  {p['t']:6.2f}s  {p['word']:14s} score {p['score']}")
    print("B-roll phrases:")
    for b in broll: print(f"  {b['src_time']:7.2f}s  {b['phrase']:28s} | {b['sentence']}")
    if a.apply_behind:
        for k, p in enumerate(picks):
            c = next(c for c in plan["clips"] if c.get("in") == p["clip_in"] and not c.get("card"))
            s = max(0.0, p["rel"] - 0.1); e = min(p["rel_end_max"] - 0.05, s + 2.4)
            for b in c.get("broll", []):
                if b["start"] < e and b["end"] > s: e = min(e, b["start"] - 0.02)
            c.setdefault("behind", []).append({"text": p["word"], "start": round(s, 2), "end": round(e, 2), "color": COLORS[k % len(COLORS)],
                                               "repeat": 3 if k == 0 else 1, "y": 0.30})
        json.dump(plan, open(pp, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print("wrote behind words into", pp.name)
