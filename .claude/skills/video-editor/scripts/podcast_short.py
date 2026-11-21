"""One command from a long talk/podcast/interview video to a vertical Short, with three approval gates.

Usage (rerun the same command after each gate; finished steps are not redone, state lives in <workdir>/state.json):
  python -I podcast_short.py <source.mp4> <workdir> --title "Why do we live\\n**where it floods?**" [--tag "Guest · Show"]
         [--topics "item 1" "item 2" "item 3"] [--context flood] [--music bed.mp3] [--length 40] [--lang en]
         [--words words.json] [--size 1080x1920]
  gate 1 segments  -> prints the picked lines;          approve with --ok-segments   (or give --segments a-b c-d ...)
  gate 2 B-roll    -> prints licensed candidates + MB;  approve with --broll-pick 1a 2b (downloads) or --no-broll
  gate 3 preview   -> renders the first 12 s at half size; approve with --final for the full render + QA
Steps: transcript (Whisper, English; for Thai pass --words from Creative Claw `transcribe`) -> segments (best 30-60 s
thread by word rarity and stress, fillers dropped, cut on word edges) -> plan (topic card intro, headline, music bed) ->
reframe (split at camera cuts, follow the person, split screen for two-shots, punch-in every ~3 s) -> key words behind
the person (pick_moments) -> B-roll search/fetch (find_broll) -> word-stack captions in mixed type -> render.
Everything it decides is in <workdir>/plan.json: edit it between runs to override any choice.
"""
import argparse, json, math, pathlib, re, subprocess, sys
from collections import Counter

HERE = pathlib.Path(__file__).parent
PY = [sys.executable, "-I"]


def run(args, **kw):
    print("  $", " ".join(str(a) for a in args[2:5]), "...", flush=True)
    return subprocess.run(PY + [str(a) for a in args[2:]] if False else [str(a) for a in args], check=True, **kw)


def script(name): return [sys.executable, "-I", str(HERE / name)]


def clean(t): return re.sub(r"[^\w'-]", "", t.lower())


def pick_segments(words, length, stop, topic=()):
    """Sentences (pause >= 0.5 s or end punctuation) scored by content-word rarity; the best window of consecutive
    sentences near the target length, then the weakest sentences dropped until it fits. Returns [(start, end, text)]."""
    sents, cur = [], []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] >= 0.5 or re.search(r"[.?!]$", cur[-1]["text"].strip())): sents.append(cur); cur = []
        cur.append(w)
    if cur: sents.append(cur)
    freq = Counter(clean(w["text"]) for w in words); N = len(words)
    def score(s):
        cw = [clean(w["text"]) for w in s if clean(w["text"]) and clean(w["text"]) not in stop and len(clean(w["text"])) > 3]
        on_topic = 1.6 if any(any(t.startswith(x) for x in topic) for t in cw) else 1.0      # flood, floods, flooding...
        return on_topic * sum(math.log(N / freq[t]) for t in cw) / max(1.5, s[-1]["end"] - s[0]["start"]) * min(1.0, len(cw) / 3)
    S = [(s[0]["start"], s[-1]["end"], " ".join(w["text"].strip() for w in s), score(s)) for s in sents]
    # the interviewer's turn: a question plus up to 2 lines just before it (gap < 0.8 s); no speaker labels needed
    host = set()
    for k, (s0, e0, t, _) in enumerate(S):
        if t.rstrip().endswith("?"):
            host.add(k); j = k
            while j > 0 and k - j < 2 and S[j][0] - S[j - 1][1] < 0.8 and not S[j - 1][2].rstrip().endswith("?"): j -= 1; host.add(j)
    for k, (s0, e0, t, _) in enumerate(S):                # sign-offs are the host too ("thank you so much for...")
        if re.search(r"(thank you|thanks (so much|for)|welcome to|my (next )?guest)", t.lower()):
            for j in range(k, min(len(S), k + 3)):
                if j == k or S[j][0] - S[j - 1][1] < 0.8: host.add(j)
                else: break
    CONNECT = ("and", "but", "so", "those", "that", "it", "they", "which", "because", "or", "then", "also", "yeah")
    weak_start = lambda k: S[k][2].split()[0].lower().strip(",.") in CONNECT if S[k][2].split() else True
    best, bi, bj = -1, 0, 0
    for i in range(len(S)):
        if i in host or weak_start(i): continue           # start on the guest, on a line that stands on its own
        tot, j = 0.0, i
        while j < len(S) and S[j][1] - S[i][0] < length * 1.6 and j not in host:
            tot += S[j][3] * (S[j][1] - S[j][0]); j += 1
            span = S[j - 1][1] - S[i][0]
            if span >= length * 0.9 and tot / span > best: best, bi, bj = tot / span, i, j
    win = list(S[bi:bj])
    while sum(e - s for s, e, _, _ in win) > length * 1.15 and len(win) > 2:   # drop the weakest inner sentences
        k = min(range(1, len(win)), key=lambda k: win[k][3]); win.pop(k)
    return [(round(s - 0.08, 2), round(e + 0.12, 2), t) for s, e, t, _ in win]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source"); ap.add_argument("workdir"); ap.add_argument("--title", required=True); ap.add_argument("--tag", default="")
    ap.add_argument("--topics", nargs="*", default=[]); ap.add_argument("--context", default=""); ap.add_argument("--music")
    ap.add_argument("--length", type=float, default=40); ap.add_argument("--lang", default="en"); ap.add_argument("--words")
    ap.add_argument("--size", default="1080x1920"); ap.add_argument("--segments", nargs="*")
    ap.add_argument("--ok-segments", action="store_true"); ap.add_argument("--broll-pick", nargs="*"); ap.add_argument("--no-broll", action="store_true")
    ap.add_argument("--final", action="store_true")
    a = ap.parse_args()
    a.title = a.title.replace("\\n", "\n"); a.topics = [t.replace("\\n", "\n") for t in a.topics]   # a typed \n is two characters
    wd = pathlib.Path(a.workdir).resolve(); wd.mkdir(parents=True, exist_ok=True); src = pathlib.Path(a.source).resolve()
    st_path = wd / "state.json"; st = json.load(open(st_path)) if st_path.exists() else {}
    def save(): json.dump(st, open(st_path, "w"), indent=1)
    W, H = map(int, a.size.split("x"))
    # 1 transcript
    words_path = pathlib.Path(a.words).resolve() if a.words else wd / "words.json"
    if not words_path.exists():
        print("[1/8] transcript (Whisper medium, local)")
        subprocess.run(script("transcribe_whisper.py") + [str(src), str(wd / "words"), "--lang", a.lang], check=True)
    words = [w for w in json.load(open(words_path, encoding="utf-8"))["words"] if w.get("type", "word") == "word"]
    sys.path.insert(0, str(HERE)); from word_captions import STOP
    # 2 segments (gate 1)
    if a.segments: st["segments"] = [[float(x) for x in s.split("-")] for s in a.segments]; st["segments_ok"] = True
    if "segments" not in st:
        topic = tuple(clean(x)[:5] for x in (a.context + " " + re.sub(r"\*|\n", " ", a.title)).split() if len(clean(x)) > 3 and clean(x) not in STOP)
        segs = pick_segments(words, a.length, STOP, topic); st["segments"] = [[s, e] for s, e, _ in segs]; st["segment_text"] = [t for _, _, t in segs]; save()
    if not st.get("segments_ok"):
        if a.ok_segments: st["segments_ok"] = True; save()
        else:
            print(f"\n[gate 1] picked {len(st['segments'])} pieces, {sum(e - s for s, e in st['segments']):.1f} s:")
            for (s, e), t in zip(st["segments"], st.get("segment_text", [""] * 99)): print(f"  {s:7.2f}-{e:7.2f}  {t[:110]}")
            print("approve: rerun with --ok-segments   or choose: --segments 266.6-272.6 281.8-288.1 ..."); sys.exit(0)
    plan_p = wd / "plan.json"
    # 3 plan
    if not st.get("plan"):
        rel = lambda p: str(pathlib.Path(p).resolve()).replace("\\", "/")
        clips = [{"src": rel(src), "in": s, "out": e, "fit": "crop", **({"transition": {"type": "fade", "dur": 0.12}} if k else {})}
                 for k, (s, e) in enumerate(st["segments"])]
        plan = {"output": {"path": "short.mp4", "size": [W, H], "fps": 25, "target": "shorts"}, "clips": clips,
                "headline": {"text": a.title, "tag": a.tag, "start": 3.4 if a.topics else 0.0},
                "music_mix": {"gap_db": -8, "under_db": -20}, "audio": [], "titles": []}
        if a.topics:                                     # 3.4 s intro: the first piece slowed down under a topic card
            s0 = st["segments"][0][0]
            plan["clips"].insert(0, {"src": rel(src), "in": s0, "out": s0 + 1.75, "speed": 0.5, "volume_db": -90, "speech": False, "captions": False, "fit": "crop"})
            plan["clips"][1]["transition"] = {"type": "fade", "dur": 0.3}
            plan["titles"].append({"text": a.title, "items": a.topics, "start": 0.0, "end": 3.4, "dim": 0.5})
        if a.music: plan["audio"].append({"src": rel(a.music), "role": "music", "start": 0, "fade_out": 2.0})
        json.dump(plan, open(plan_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False); st["plan"] = True; save()
    # 4 reframe
    if not st.get("reframe"):
        print("[4/8] reframe: camera cuts, follow the person, split screen, punch-in")
        subprocess.run(script("reframe.py") + [str(plan_p), "--out", str(plan_p), "--stack", "--punch", "1.3", "--every", "3", "--words", str(words_path),
                                               "--sheet", str(wd / "reframe_check.jpg")], check=True)
        st["reframe"] = True; save()
    # 5 key words behind the person
    if not st.get("moments"):
        print("[5/8] key words")
        subprocess.run(script("pick_moments.py") + [str(words_path), str(plan_p), "--apply-behind", "--out", str(wd / "moments.json")], check=True)
        st["moments"] = True; save()
    # 6 B-roll (gate 2)
    if not st.get("broll") and not a.no_broll:
        cands = wd / "broll_candidates.json"
        if not cands.exists():
            print("[6/8] B-roll search (metadata only)")
            subprocess.run(script("find_broll.py") + ["search", str(wd / "moments.json"), str(plan_p), str(cands), "--context", a.context], check=True)
        if a.broll_pick is None:
            print("\n[gate 2] approve downloads: rerun with --broll-pick 1a 2b ... (sizes above), or --no-broll"); sys.exit(0)
        if a.broll_pick:
            subprocess.run(script("find_broll.py") + ["fetch", str(cands), str(plan_p), "--pick"] + a.broll_pick + ["--dir", str(wd / "broll")], check=True)
        st["broll"] = True; save()
    # 7 captions
    if not st.get("captions"):
        print("[7/8] captions (word stack, mixed type)")
        subprocess.run(script("word_captions.py") + [str(words_path), str(plan_p), str(wd / "caps.ass"), "--style", "stack", "--type", "mix"], check=True)
        plan = json.load(open(plan_p, encoding="utf-8")); plan["subtitles"] = {"src": str(wd / "caps.ass").replace("\\", "/")}
        json.dump(plan, open(plan_p, "w", encoding="utf-8"), indent=1, ensure_ascii=False); st["captions"] = True; save()
    # 8 preview (gate 3) / final
    if not a.final:
        print("[8/8] preview: first 12 s at half size")
        subprocess.run(script("edit_plan.py") + [str(plan_p), "--preview", "0", "12"], check=True)
        print(f"\n[gate 3] look at {wd / 'short_preview_0-12.mp4'}; approve with --final (full render + QA), or edit plan.json and rerun"); sys.exit(0)
    print("[final] full render + QA")
    subprocess.run(script("edit_plan.py") + [str(plan_p)], check=True)
    print(f"\ndone: {wd / 'short.mp4'} (sheet: short.mp4.sheet.jpg, QA: short.mp4.qa.json)")
