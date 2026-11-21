"""Build short-form captions (2-4 words at a time, current word highlighted) from word timings, for the parts of a
source that an edit keeps. Output is an .ass file for edit_plan.py ("subtitles": {"src": "caps.ass"}) or ffmpeg ass=.

Usage: python -I word_captions.py <words.json> <plan.json> <out.ass> [--max-words 3] [--max-chars 18] [--size 0.055]
                                  [--pos 0.70] [--hi FFD200] [--upper]
  words.json  transcribe_whisper.py output, or a Scribe diarization JSON ({"words": [{text, start, end}]})
  plan.json   the edit plan; captions are made for clips whose "src" matches --src (default: the first clip's src),
              mapped onto the timeline exactly as edit_plan.py lays clips out (speed and transitions included)
  --pos       caption centre height as a fraction of the frame (0.70 = lower third on 9:16, above the UI of Shorts/Reels)
A new caption starts after --max-words, at a pause >= 0.35 s, or after . , ? ! ; a caption never crosses a cut.
Thai has no spaces: Scribe returns characters, so for Thai make normal subtitles with align_script.py instead.
"""
import argparse, json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from edit_plan import build_timeline, ass_time, text_width   # same layout rules as the renderer


STOP = set("""a an the and or but so to of in on at by for with from as is are was were be been am it its it's this that these those
i you he she we they me him her us them my your his our their do does did not no yes if then than just very really
can could would should will shall may might must have has had what which who whom when where why how all some any
there here up out about into over also too more most such only own same both each few other because while
actually really basically literally kind sort like going gonna know think mean yeah thing things something
we're you're they're it's that's don't can't i'm get got make made way lot right okay yeah well""".split())


PALETTE = ["FFD200", "FF5DA2", "7FD8FF", "B48CFF", "FF9F43"]   # accent colours cycled per phrase (P15-P17 style)
from fonts import font as _font
SANS, SANS_FILE = _font("sans"); _SF, _SFILE = _font("serif_italic")
SERIF = (_SF, _SFILE, _SFILE)   # bold comes from 1 when the font has no bold italic file


def width_font(text, size, path):
    """Rendered width for any font file, sized the way libass sizes it (by ascent + descent)."""
    from PIL import ImageFont
    try:
        f = ImageFont.truetype(path, 100); asc, desc = f.getmetrics()
        return ImageFont.truetype(path, max(1, int(size * 100 / (asc + desc)))).getlength(text)
    except Exception:
        return text_width(text, size)


def stack_rows(caps, W, H, a, cap_pos, cap_end):
    """Word stack (P3-P5 podcast style): each phrase builds word by word into lines; a line is the small connecting
    words plus one big content word; the most important word of the phrase is biggest and in the accent colour.
    --type mix (P11, P13, P15-P17): key word in bold italic serif with a colour that changes per phrase, small words in
    italic serif, other content words heavy sans; numbers and money in red (P18)."""
    big = round(H * a.size * (1.55 if W < H else 1.7)); small = round(big * 0.58); top = round(big * 1.2)
    hi = a.hi.upper(); hi_bgr = hi[4:6] + hi[2:4] + hi[0:2]; rows = []
    mix = getattr(a, "type", "sans") == "mix"
    for k, cap in enumerate(caps):
        clean = lambda t: re.sub(r"[^\w'’-]", "", t.lower())
        content = [i for i, (_, _, t) in enumerate(cap) if clean(t) and clean(t) not in STOP]
        star = max(content, key=lambda i: (len(clean(cap[i][2])) - (3 if clean(cap[i][2]).endswith('ly') else 0), i)) if content else None   # longest content word, later wins ties
        lines, cur = [], []
        for i, (_, _, t) in enumerate(cap):
            cur.append(i)
            if i in content or len(cur) >= 3: lines.append(cur); cur = []
        if cur: lines.append(cur)
        size = lambda i: top if i == star else (big if i in content else small)
        acc = PALETTE[k % len(PALETTE)] if mix else hi; acc_bgr = acc[4:6] + acc[2:4] + acc[0:2]
        def font_of(i):
            if not mix: return ("", SANS_FILE)
            if i == star: return (f"\\fn{SERIF[0]}\\b1\\i1", SERIF[1])
            if i not in content: return (f"\\fn{SERIF[0]}\\b0\\i1", SERIF[2])
            return ("", SANS_FILE)
        lh = [max(size(i) for i in ln) * 0.95 for ln in lines]
        pos = cap_pos[k] if cap_pos[k] is not None else a.pos + 0.05
        floor = 0.27 if cap_pos[k] is not None else 0.45
        block = sum(lh); y = min(max(H * pos - block / 2, H * floor), H * 0.95 - block)   # a little lower than pop captions: under the chest print
        end_all = cap[-1][1]; nxt = caps[k + 1][0][0] if k + 1 < len(caps) else end_all + 0.6; hold = min(nxt, end_all + 0.5, cap_end[k])
        for ln, h in zip(lines, lh):
            y += h; txts = [cap[i][2].upper() if a.upper else cap[i][2] for i in ln]
            ws = [width_font(t, size(i), font_of(i)[1]) for t, i in zip(txts, ln)]
            gap = small * 0.28; fit = min(1.0, W * 0.9 / (sum(ws) + gap * (len(ln) - 1)))   # never run off the frame
            ws = [w * fit for w in ws]; gap *= fit; sz = {i: int(size(i) * fit) for i in ln}
            x = (W - (sum(ws) + gap * (len(ln) - 1))) / 2
            for i, w, raw in zip(ln, ws, txts):
                s0 = cap[i][0] - 0.03; t = esc(raw)
                if re.search(r"[0-9$%฿€£]", raw): col = r"\c&H3B3BFF&"              # numbers and money in red
                elif i == star: col = rf"\c&H{acc_bgr}&"
                else: col = ""
                pop = r"\fscx60\fscy60\t(0,110,\fscx108\fscy108)\t(110,190,\fscx100\fscy100)"
                rows.append(rf"Dialogue: 0,{ass_time(s0)},{ass_time(hold)},C,,0,0,0,,{{\an1\pos({round(x)},{round(y)}){font_of(i)[0]}\fs{sz[i]}\bord{max(4, sz[i] // 9)}\shad{max(2, sz[i] // 16)}{col}\fad(60,120){pop}}}{t}")
                x += w + gap
    return rows


def esc(t): return t.replace("{", "(").replace("}", ")").replace("\\", "/")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words"); ap.add_argument("plan"); ap.add_argument("out"); ap.add_argument("--src")
    ap.add_argument("--max-words", type=int, default=3); ap.add_argument("--max-chars", type=int, default=18)
    ap.add_argument("--size", type=float, default=0.055); ap.add_argument("--pos", type=float, default=0.70)
    ap.add_argument("--hi", default="FFD200"); ap.add_argument("--upper", action="store_true")
    ap.add_argument("--style", choices=["pop", "stack"], default="pop", help="pop: 1-3 words, spoken word highlighted; stack: words pile up into a block, key words big")
    ap.add_argument("--type", choices=["sans", "mix"], default="sans", help="stack: mix = italic serif + heavy sans, accent colour per phrase, numbers in red")
    ap.add_argument("--stack-words", type=int, default=6, help="stack: most words in one block before it clears")
    a = ap.parse_args()
    words = [w for w in json.load(open(a.words, encoding="utf-8"))["words"] if w.get("type", "word") == "word" and w["text"].strip()]
    plan = json.load(open(a.plan, encoding="utf-8")); W, H = plan["output"].get("size", [1920, 1080])
    tl, total = build_timeline(plan); src = a.src or next(c["src"] for c in plan["clips"] if not c.get("card"))
    caps, cap_pos, cap_end = [], [], []
    for c in tl:
        if c.get("src") != src or c.get("captions") is False: continue      # e.g. an intro shot under a topic card
        inside = [w for w in words if w["start"] >= c["in"] - 0.05 and w["end"] <= c["out"] + 0.05]
        group = []
        def flush():
            if group:
                caps.append([(c["start"] + (w["start"] - c["in"]) / c["speed"], c["start"] + (w["end"] - c["in"]) / c["speed"], w["text"].strip()) for w in group])
                cap_end.append(c["end"])                                        # never past the end of its clip (cards, cuts)
                cap_pos.append(0.40 if c.get("fit") == "stack" else None)   # split screen: over the upper panel's lower part (the listener), the speaker's face is just below the middle line
        for w in inside:
            txt = w["text"].strip(); chars = sum(len(x["text"].strip()) + 1 for x in group) + len(txt)
            limit = (len(group) >= a.stack_words) if a.style == "stack" else (len(group) >= a.max_words or chars > a.max_chars)
            if group and (limit or w["start"] - group[-1]["end"] >= 0.35):
                flush(); group = []
            group.append(w)
            if re.search(r"[.,?!;:]$", txt): flush(); group = []
        flush()
    fs = round(H * a.size) if W < H else round(H * a.size * 1.2); y = round(H * a.pos)
    hi = a.hi.upper(); hi_bgr = hi[4:6] + hi[2:4] + hi[0:2]
    head = "\n".join(["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: C,{SANS},{fs},&H00FFFFFF,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{max(3, fs // 14)},{max(2, fs // 24)},5,60,60,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    rows = []
    if a.style == "stack":
        rows = stack_rows(caps, W, H, a, cap_pos, cap_end)
        caps_for_pop = []
    else:
        caps_for_pop = caps
    for k, cap in enumerate(caps_for_pop):
        end_all = cap[-1][1]
        nxt = caps[k + 1][0][0] if k + 1 < len(caps) else end_all + 0.6
        hold = min(nxt, end_all + 0.4, cap_end[k])          # stay up a moment after the last word, never over the next caption or past the clip
        for i, (s, e, _) in enumerate(cap):                 # one event per word: that word in the highlight colour
            e2 = cap[i + 1][0] if i + 1 < len(cap) else hold
            parts = []
            for j, (_, _, t) in enumerate(cap):
                t = esc(t.upper() if a.upper else t)
                parts.append(f"{{\\c&H{hi_bgr}&}}{t}{{\\c&HFFFFFF&}}" if j == i else t)
            rows.append(f"Dialogue: 0,{ass_time(s if i else s - 0.05)},{ass_time(e2)},C,,0,0,0,,{{\\pos({W // 2},{y})}}" + " ".join(parts))
    open(a.out, "w", encoding="utf-8").write(head + "\n" + "\n".join(rows) + "\n")
    print(f"{len(caps)} captions, {sum(len(c) for c in caps)} words -> {a.out}")
