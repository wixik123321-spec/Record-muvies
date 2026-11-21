"""Render a whole footage edit from one JSON edit plan: clips, transitions, titles, voice, music with ducking,
sound effects, subtitles, loudness, export, then run qa_check.py. The format is described in references/edit-plan.md.

Usage: python -I edit_plan.py <plan.json> [--preview A B] [--no-qa]
  --preview A B   render only timeline seconds A..B at half size (fast check before the full render)
Writes the output, <output>.timeline.json (where every clip, title and sound landed) and the QA report.

Design notes
- Video is assembled by one ffmpeg filter graph (trim, speed, fit, xfade/concat, title overlays, subtitles).
- Audio is mixed in numpy on the same timeline (clip sound, voice, music, effects), because ducking from known speech
  times beat a sidechain compressor in a listening test (references/music-rules.md).
- Titles are an ASS track burned with libass: ffmpeg drawtext and Pillow without raqm drop Thai tone marks that sit
  on an upper vowel (ที่ became ทีนี).
- Everything is encoded H.264 yuv420p limited range (scale=out_range=tv), AAC 192k, faststart.
"""
import argparse, json, pathlib, re, subprocess, sys, tempfile, wave
import numpy as np

SR = 48000
HERE = pathlib.Path(__file__).parent
TARGETS = {"youtube": -14.0, "shorts": -14.0, "doc": -18.5, "master": -23.0}
import pathlib as _pl, sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))   # python -I leaves the script folder off the path
from fonts import font as _font, ass_fontsdir
SANS, FONT = _font("sans")          # bundled Kanit Bold (assets/fonts), system fallback
HEAVY, HEAVY_FILE = _font("heavy")


# ---------- timeline -------------------------------------------------------------------------------------------
def build_timeline(plan):
    t, out = 0.0, []
    for k, c in enumerate(plan["clips"]):
        speed = float(c.get("speed", 1.0)); d = (float(c["out"]) - float(c["in"])) / speed
        tr = c.get("transition") if k else None; td = float(tr.get("dur", 0.5)) if tr else 0.0
        start = t - td
        out.append({"i": k, "start": round(start, 3), "end": round(start + d, 3), "dur": d, "speed": speed, "trans": tr, "tdur": td, **c})
        t = start + d
    return out, t


def srt_spans(path, offset=0.0):
    txt = open(path, encoding="utf-8-sig").read()
    def s(x): h, m, r = x.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(r)
    return [(s(a) + offset, s(b) + offset) for a, b in re.findall(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", txt)]


# ---------- titles (libass) -----------------------------------------------------------------------------------
def ass_time(t):
    t = max(0.0, t); return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


ACCENT = "FFD200"                       # default accent colour (RGB hex) for **marked** words, numbers and underlines


def bgr(rgb_hex): h = rgb_hex.upper().lstrip("#"); return h[4:6] + h[2:4] + h[0:2]


def text_width(text, size):
    """Rough rendered width in pixels (Pillow measure; Thai marks above/below take no width either way)."""
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(FONT, 100); asc, desc = f.getmetrics()
        em = size * 100 / (asc + desc)            # libass sizes a font by its full line height (ascent+descent = 1.34 em here)
        return ImageFont.truetype(FONT, max(1, int(em))).getlength(text)
    except Exception:
        return 0.55 * size * len(text)


def fit_size(size, lines, max_w):
    """Shrink a font size until the widest line fits max_w pixels (titles must never run off the frame)."""
    widest = max((text_width(l, size) for l in lines), default=0)
    return int(size * min(1.0, max_w / widest)) if widest else int(size)


def ass_text(text, accent):
    """Escape for ASS; **word** becomes the accent colour; newlines become \\N."""
    t = str(text).replace("{", "(").replace("}", ")")
    t = re.sub(r"\*\*(.+?)\*\*", lambda m: "{\\c&H%s&}%s{\\c&HDCF0FA&}" % (bgr(accent), m.group(1)), t)
    return t.replace("\n", "\\N")


def anim_tags(kind, dur_ms, fi):
    """Entrance animation (libass \\t transforms). All titles enter in ~0.3 s and leave with a fade."""
    if kind == "pop":     return "\\fscx40\\fscy40\\t(0,170,\\fscx112\\fscy112)\\t(170,300,\\fscx100\\fscy100)"
    if kind == "punch":   return "\\fscx135\\fscy135\\blur6\\t(0,160,\\fscx100\\fscy100\\blur0)"
    if kind == "rise":    return "\\frx70\\t(0,280,\\frx0)"
    if kind == "zoom":    return "\\fscx100\\fscy100\\t(0,%d,\\fscx108\\fscy108)" % dur_ms   # slow push for the whole hold
    return ""


def titles_ass(titles, W, H, path):
    """Titles as an ASS track burned by libass (shapes Thai correctly; Pillow without raqm and ffmpeg drawtext drop
    stacked marks). Text only, never in a box: thick dark outline + soft shadow (user rule).
    Per title: anim = none | pop | punch | slide | rise | zoom | words (one word after another);
    underline = true draws an accent line that grows under the text; **word** = accent colour.
    A title with "items" is a topic card: heading, then numbered items that slide in one by one, over a dimmed frame."""
    ol, sh = max(3, round(min(W, H) / 270)), max(2, round(min(W, H) / 400))
    head = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: T,{SANS},{round(H * 0.07)},&H00DCF0FA,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,{ol},{sh},8,40,40,{round(H * 0.09)},1",
        f"Style: S,{SANS},{round(H * 0.07)},&H00DCF0FA,&H000000FF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    rows = []

    def ev(layer, s, e, style, tags, text):
        rows.append(f"Dialogue: {layer},{ass_time(s)},{ass_time(e)},{style},,0,0,0,,{{{tags}}}{text}")

    def y_of(it, size, nlines):
        pos = it.get("pos", "top"); m = H * float(it.get("margin", 0.09)); block = size * 1.25 * nlines
        return round(m + block / 2) if pos == "top" else (round(H - m - block / 2) if pos == "bottom" else round(H * float(it.get("y", 0.5))))

    for it in titles:
        s, e = float(it["start"]), float(it["end"]); accent = it.get("accent", ACCENT)
        fi = int(float(it.get("fade", 0.25)) * 1000); size = int(it.get("size", round(H * 0.07)))
        if it.get("color"): r, g, b = it["color"]; base = "\\c&H%02X%02X%02X&" % (b, g, r)
        else: base = ""
        if "items" in it:                                            # ---- topic card
            dim = it.get("dim", 0.45)
            if dim:                                                  # dim the whole frame (not a box around text)
                a = "%02X" % int(255 * (1 - dim))
                ev(0, s, e, "S", f"\\an7\\pos(0,0)\\p1\\1c&H000000&\\1a&H{a}&\\fad({fi},{fi})", f"m 0 0 l {W} 0 {W} {H} 0 {H}")
            hs = int(it.get("size", round(H * 0.075))); n = len(it["items"]); isz = int(it.get("item_size", round(hs * 0.8)))
            plain = lambda t: re.sub(r"\*\*", "", str(t))
            hs = fit_size(hs, [plain(l) for l in str(it["text"]).split("\n")], W * 0.88)
            x_left = round(W * float(it.get("x", 0.12)))
            isz = fit_size(isz, ["0  " + plain(t) for t in it["items"]], W - x_left - W * 0.05)
            hl = str(it["text"]).count("\n") + 1; head_h = hs * 1.25 * hl
            gap = isz * 1.7; total_h = head_h + hs * 0.6 + gap * n; y0 = H * float(it.get("y", 0.5)) - total_h / 2
            ev(2, s, e, "T", f"\\an5\\pos({W // 2},{round(y0 + head_h / 2)})\\fs{hs}\\fad({fi},{fi}){base}" + anim_tags("pop", 0, fi), ass_text(it["text"], accent))
            lw = min(W * 0.8, max(text_width(re.sub(r"\*\*", "", l), hs) for l in str(it["text"]).split("\n")))
            ly = round(y0 + head_h + hs * 0.15)
            ev(2, s + 0.25, e, "S", f"\\an5\\pos({W // 2},{ly})\\p1\\1c&H{bgr(accent)}&\\fscx0\\t(0,350,\\fscx100)\\fad(0,{fi})",
               f"m 0 0 l {int(lw)} 0 {int(lw)} {max(4, hs // 14)} 0 {max(4, hs // 14)}")
            step = float(it.get("stagger", 0.45))
            for i, item in enumerate(it["items"]):
                ts = s + 0.55 + i * step; yy = round(y0 + head_h + hs * 0.6 + gap * (i + 0.5))
                num = "{\\c&H%s&\\fs%d}%d{\\c&HDCF0FA&\\fs%d}  " % (bgr(accent), int(isz * 1.25), i + 1, isz)
                ev(3, ts, e, "T", f"\\an4\\move({x_left - 140},{yy},{x_left},{yy},0,260)\\fs{isz}\\fad(200,{fi})", num + ass_text(item, accent))
            continue
        size = fit_size(size, [re.sub(r"\*\*", "", l) for l in str(it["text"]).split("\n")], W * 0.9)
        lines = str(it["text"]).count("\n") + 1; y = y_of(it, size, lines); x = W // 2; kind = it.get("anim", "none")
        dur_ms = int((e - s) * 1000)
        if kind == "words":                                          # one word after another (karaoke-style reveal)
            words = str(it["text"]).split(" "); step = int(float(it.get("word_step", 0.12)) * 1000); parts = []
            for i, w in enumerate(words):
                t0 = i * step
                parts.append("{\\alpha&HFF&\\t(%d,%d,\\alpha&H00&)}%s" % (t0, t0 + 120, ass_text(w, accent)))
            ev(1, s, e, "T", f"\\an5\\pos({x},{y})\\fs{size}\\fad(0,{fi}){base}", " ".join(parts))
        elif kind == "slide":
            dx = int(it.get("slide_px", W * 0.18)) * (1 if it.get("from", "left") == "left" else -1)
            ev(1, s, e, "T", f"\\an5\\move({x - dx},{y},{x},{y},0,280)\\fs{size}\\fad({fi},{fi}){base}", ass_text(it["text"], accent))
        else:
            ev(1, s, e, "T", f"\\an5\\pos({x},{y})\\fs{size}\\fad({fi},{fi}){base}" + anim_tags(kind, dur_ms, fi), ass_text(it["text"], accent))
        if it.get("underline"):
            first = re.sub(r"\*\*", "", str(it["text"]).split("\n")[-1]); lw = min(W * 0.9, text_width(first, size))
            ly = round(y + size * 1.25 * lines / 2 - size * 0.05); th = max(4, size // 14)
            ev(1, s + 0.2, e, "S", f"\\an5\\pos({x},{ly})\\p1\\1c&H{bgr(accent)}&\\fscx0\\t(0,300,\\fscx100)\\fad(0,{fi})",
               f"m 0 0 l {int(lw)} 0 {int(lw)} {th} 0 {th}")
    open(path, "w", encoding="utf-8").write(head + "\n" + "\n".join(rows) + "\n")


# ---------- video ----------------------------------------------------------------------------------------------
def fit_filter(fit, W, H, n=0, c=None):
    if fit == "crop": return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if fit == "pad": return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black"
    if fit == "stack":    # split screen: two crops of one source ([x, y, w, h] each, from reframe.py --stack), top and bottom
        (x1, y1, w1, h1), (x2, y2, w2, h2) = c["stack"]; hh = H // 2
        return (f"split[sa{n}][sb{n}];[sa{n}]crop={w1}:{h1}:{x1}:{y1},scale={W}:{hh}[st{n}];[sb{n}]crop={w2}:{h2}:{x2}:{y2},scale={W}:{H - hh}[sbm{n}];"
                f"[st{n}][sbm{n}]vstack,drawbox=x=0:y={hh - 3}:w={W}:h=6:color=white@0.9:t=fill")
    # blur: whole frame over a blurred, filled copy of itself (9:16 from 16:9 footage)
    return (f"split[ba{n}][bb{n}];[ba{n}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=30,eq=brightness=-0.08[bg{n}];"
            f"[bb{n}]scale={W}:{H}:force_original_aspect_ratio=decrease[fg{n}];[bg{n}][fg{n}]overlay=(W-w)/2:(H-h)/2")


def face_square(c, W, H):
    """Where the speaker's face is in the fitted frame, as (centre x, centre y, square side) for the bubble.
    Skin-coloured pixels: the face is the top of the skin mass (hands sit lower); the square is ~2.3 face widths so the
    whole head fits with a little air. Samples the clip during its B-roll windows (the bubble shows those moments)."""
    if c.get("fit") == "stack":
        (rx, ry, rw, rh) = c["stack"][1 if c.get("pip_panel", "bottom") == "bottom" else 0]; oy = H // 2 if c.get("pip_panel", "bottom") == "bottom" else 0; oh = H - H // 2
    else:
        (rx, ry, rw, rh) = c.get("crop") or [0, 0, 0, 0]; oy, oh = 0, H
    sw = 108
    region = f"crop={rw}:{rh}:{rx}:{ry}," if rw else ""
    sh = int(round(sw * (oh / W)))
    pts = []
    for b in c["broll"]:                                   # 6 frames over each B-roll window
        t0 = c["in"] + float(b["start"]) * c.get("speed", 1.0); d = (float(b["end"]) - float(b["start"])) * c.get("speed", 1.0)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.2f}", "-t", f"{d:.2f}", "-i", c["src"], "-vf",
                              f"fps={6 / max(d, 0.5):.3f},{region}scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        nfr = len(raw) // (sw * sh * 3)
        pts += [x.astype(np.float32) for x in np.frombuffer(raw[: nfr * sw * sh * 3], np.uint8).reshape(nfr, sh, sw, 3)]
    fallback = (W / 2, oy + oh * 0.3, W * 0.62)
    if len(pts) < 2: return fallback
    fr = np.array(pts); r, g, b = fr[..., 0], fr[..., 1], fr[..., 2]
    cb = 128 - 0.169 * r - 0.331 * g + 0.5 * b; cr = 128 + 0.5 * r - 0.419 * g - 0.081 * b; yl = 0.299 * r + 0.587 * g + 0.114 * b
    skin = ((cr > 135) & (cr < 180) & (cb > 85) & (cb < 135) & (yl > 40)).mean(axis=0)
    motion = np.abs(np.diff(fr.mean(axis=3), axis=0)).mean(axis=0)           # a face moves; wood shelves do not
    score = skin * (0.15 + np.minimum(motion, 20) / 20)
    m = score > max(0.15, 0.35 * score.max())
    ys, xs = np.nonzero(m)
    if len(ys) < 20: return fallback
    top = np.percentile(ys, 3); band = (ys < top + 0.22 * sh)               # the upper skin band = the face
    col = np.bincount(xs[band], minlength=sw).astype(float); col = np.convolve(col, np.ones(3) / 3, "same")
    pk = int(np.argmax(col)); a = b2 = pk
    while a > 0 and col[a - 1] > 0.2 * col[pk]: a -= 1            # the continuous run of columns around the peak:
    while b2 < sw - 1 and col[b2 + 1] > 0.2 * col[pk]: b2 += 1    # skin-coloured walls or arms further away do not count
    k = W / sw
    face_w = max(b2 - a + 1, sw * 0.10) * k; cx = (a + b2 + 1) / 2 * k
    rows = ys[band & (xs >= a) & (xs <= b2)]; ftop = float(np.percentile(rows, 2)) if len(rows) else top
    cy = oy + ftop * k + face_w * 0.62
    return cx, cy, min(W, face_w * 2.3)


def person_masks(c, crop_filter, W, H, fps, t0, dur, out_path):
    """Person mask video (grey, white = person) for clip time t0..t0+dur, same framing as the clip (crop + 9:16 fit).
    rembg u2net_human_seg (~176 MB model in ~/.rembg/models; ask before the first download), about 0.2 s per frame on CPU."""
    from rembg import new_session, remove
    from PIL import Image
    mw, mh = 360, int(round(360 * H / W)) // 2 * 2
    src_t = c["in"] + t0 * c.get("speed", 1.0)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src_t:.3f}", "-t", f"{dur * c.get('speed', 1.0):.3f}", "-i", c["src"],
                          "-vf", f"setpts=(PTS-STARTPTS)/{c.get('speed', 1.0)},{crop_filter}scale={mw}:{mh}:force_original_aspect_ratio=increase,crop={mw}:{mh},fps={fps}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    nfr = len(raw) // (mw * mh * 3); sess = new_session("u2net_human_seg"); masks = []
    for i in range(nfr):
        im = Image.frombytes("RGB", (mw, mh), raw[i * mw * mh * 3:(i + 1) * mw * mh * 3])
        masks.append(np.asarray(remove(im, session=sess, only_mask=True)).astype(np.uint8))
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{mw}x{mh}", "-r", str(fps), "-i", "-",
                            "-c:v", "ffv1", out_path], stdin=subprocess.PIPE)
    for m in masks: enc.stdin.write(m.tobytes())
    enc.stdin.close(); enc.wait()
    return nfr


def behind_ass(items, W, H, path):
    """Huge words for the behind-the-person layer (Impact-like heavy caps, fit to the width, optional repeats)."""
    head = "\n".join(["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
        "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: B,{HEAVY},{round(H * 0.2)},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,2,0,1,0,0,5,0,0,0,1", "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"])
    rows = []
    for it in items:
        txt = str(it["text"]).upper(); s, e = float(it["start"]), float(it["end"])
        r, g, b = it.get("color", [255, 59, 59]); col = "&H%02X%02X%02X&" % (b, g, r)
        size = int(it.get("size", H * 0.2))
        try:                                    # fit the word to ~96% of the width (Impact sized by its line height)
            from PIL import ImageFont
            f = ImageFont.truetype(HEAVY_FILE, 100); asc, desc = f.getmetrics()
            wpx = ImageFont.truetype(HEAVY_FILE, int(size * 100 / (asc + desc))).getlength(txt)
            size = int(size * min(1.0, W * 0.96 / max(wpx, 1)))
        except Exception:
            pass
        reps = int(it.get("repeat", 1)); y0 = H * float(it.get("y", 0.30)); step = size * 0.82
        for k in range(reps):
            y = round(y0 + (k - (reps - 1) / 2) * step); alpha = "00" if k == reps // 2 else "70"   # middle copy solid, the others faint
            pop = r"\fscx120\fscy120\t(0,180,\fscx100\fscy100)" if k == reps // 2 else ""
            rows.append(rf"Dialogue: 0,{ass_time(s + 0.05 * k)},{ass_time(e)},B,,0,0,0,,{{\an5\pos({W // 2},{y})\fs{size}\c{col}\alpha&H{alpha}&\fad(80,150){pop}}}{txt}")
    open(path, "w", encoding="utf-8").write(head + "\n" + "\n".join(rows) + "\n")


def behind_chain(c, n, W, H, fps, first_input, cmd, crop_filter, tmp):
    """[bh{n}] (fitted clip) -> words drawn on it -> the person (mask) laid back on top -> [bhout{n}]."""
    items = c["behind"]; t0 = min(float(i["start"]) for i in items); t1 = max(float(i["end"]) for i in items)
    mpath = str(tmp / f"mask{n}.mkv"); person_masks(c, crop_filter, W, H, fps, t0, t1 - t0, mpath)
    try:                                                    # warn when the person covers most of the word's band
        mw, mh = 360, int(round(360 * H / W)) // 2 * 2
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", mpath, "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        m = np.frombuffer(raw, np.uint8).reshape(-1, mh, mw).mean(axis=0) > 127
        for it in items:
            y = float(it.get("y", 0.30)); band = m[int(mh * (y - 0.06)): int(mh * (y + 0.06))]
            cov = band.any(axis=0).mean() if band.size else 0
            if cov > 0.80: print(f"WARNING behind word '{it['text']}': the person covers {cov:.0%} of its band, most of it will be hidden (wider shot, or move 'y')")
    except Exception:
        pass
    apath = (tmp / f"behind{n}.ass").resolve().as_posix().replace(":", r"\:"); behind_ass(items, W, H, str(tmp / f"behind{n}.ass"))
    cmd += ["-i", mpath]; k = first_input
    return [f"[bh{n}]split[bhb{n}][bhf{n}]",
            f"[bhb{n}]ass='{apath}'{ass_fontsdir()}[bht{n}]",
            f"[{k}:v]scale={W}:{H},gblur=sigma=1.2,format=gray,setpts=PTS-STARTPTS[bhm{n}]",
            f"[bhf{n}]trim={t0}:{t1},setpts=PTS-STARTPTS[bhft{n}]",
            f"[bhft{n}][bhm{n}]alphamerge,setpts=PTS-STARTPTS+{t0}/TB[bhp{n}]",
            f"[bht{n}][bhp{n}]overlay=0:0:eof_action=pass:enable='between(t,{t0},{t1})'[bhout{n}]"], k + 1


def broll_chain(c, n, W, H, fps, first_input, cmd):
    """B-roll over a clip (clip-relative start/end), the speaker kept in a circle bubble (P7 podcast style).
    Returns filter lines; appends inputs to cmd. Stills get a slow push-in; video B-roll is cut from 'in'."""
    lines, cur, k = [], f"v{n}raw", first_input
    lines.append(f"[{cur}]split[spk{n}][pipsrc{n}]"); cur = f"spk{n}"
    D = int(W * float(c.get("pip_size", 0.36))) // 2 * 2
    for j, b in enumerate(c["broll"]):
        s, e = float(b["start"]), float(b["end"]); d = e - s
        still = b["src"].lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        cmd += (["-loop", "1", "-t", f"{d:.3f}", "-i", b["src"]] if still else
                ["-reinit_filter", "0", "-ss", str(b.get("in", 0)), "-t", f"{d:.3f}", "-i", b["src"]])
        z = "scale=iw*1.12:ih*1.12,crop=iw/1.12:ih/1.12:(iw-ow)*t/%.3f:(ih-oh)*t/%.3f," % (d, d) if still else ""
        reg = "crop=%d:%d:%d:%d," % (b["region"][2], b["region"][3], b["region"][0], b["region"][1]) if b.get("region") else ""   # drop burned-in text / logos
        fx, fy = b.get("focus", [0.5, 0.5])            # what must stay in the 9:16 window (0-1 of the picture)
        cov = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:'min(max(iw*{fx}-ow/2,0),iw-ow)':'min(max(ih*{fy}-oh/2,0),ih-oh)',"
        lines.append(f"[{k}:v]{'' if still else 'setpts=PTS-STARTPTS,'}{reg}{cov}{z}"
                     f"fps={fps},format=yuv420p,setsar=1,setpts=PTS-STARTPTS+{s}/TB[br{n}_{j}]")
        lines.append(f"[{cur}][br{n}_{j}]overlay=0:0:eof_action=pass:enable='between(t,{s},{e})'[o{n}_{j}]"); cur = f"o{n}_{j}"; k += 1
    if any(b.get("pip", True) for b in c["broll"]):
        cx, cy, side = c.get("pip_box") or face_square(c, W, H)   # follow the face, not a fixed spot
        side = int(side) // 2 * 2; px0 = int(min(max(0, cx - side / 2), W - side)); py0 = int(min(max(0, cy - side / 2), H - side))
        lines.append(f"[pipsrc{n}]crop={side}:{side}:{px0}:{py0},scale={D}:{D},format=rgba,"
                     f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(hypot(X-{D}/2,Y-{D}/2),{D}/2-6),255,if(lte(hypot(X-{D}/2,Y-{D}/2),{D}/2),0,0))'[pc{n}]")
        lines.append(f"color=white:s={D}x{D}:r={fps},format=rgba,geq=r=255:g=255:b=255:a='if(lte(hypot(X-{D}/2,Y-{D}/2),{D}/2),255,0)'[ring{n}]")
        lines.append(f"[ring{n}][pc{n}]overlay=0:0:shortest=1[bub{n}]")
        pos = c.get("pip_pos", "top-right"); m = int(W * 0.05)   # top right, under a headline: captions live in the lower half
        px = m if "left" in pos else W - D - m; py = int(H * 0.15) if "top" in pos else int(H * 0.60)
        en = "+".join(f"between(t,{b['start']},{b['end']})" for b in c["broll"] if b.get("pip", True))
        lines.append(f"[{cur}][bub{n}]overlay={px}:{py}:enable='{en}'[pp{n}]"); cur = f"pp{n}"
    else:
        lines.append(f"[pipsrc{n}]nullsink")
    lines.append(f"[{cur}]null[v{n}]")
    return lines, k


def render_video(plan, tl, total, W, H, fps, tmp, a0, a1):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]; fg = []
    for c in tl:                                            # clip inputs first: input k = clip k
        if c.get("card"):                                   # text-only card: a plain background, the text is a title
            cmd += ["-f", "lavfi", "-t", f"{c['out'] - c['in']:.3f}", "-i", f"color=c={c['card'].get('bg', 'black')}:s={W}x{H}:r={fps}"]
        else:
            cmd += ["-reinit_filter", "0", "-ss", f"{c['in']}", "-t", f"{c['out'] - c['in']:.3f}", "-i", c["src"]]   # VP9 webm can change frame params mid-stream
    n_in = len(tl)
    for n, c in enumerate(tl):
        fit = c.get("fit", plan["output"].get("fit", "crop"))
        extra = (f"crop={c['crop'][2]}:{c['crop'][3]}:{c['crop'][0]}:{c['crop'][1]}," if c.get("crop") and fit != "stack" else "")   # [x, y, w, h] in source pixels (zoom)
        extra += (c["filter"] + ",") if c.get("filter") else ""          # e.g. "eq=gamma=1.4:saturation=1.1" for a dark shot
        label = f"v{n}raw" if c.get("broll") else f"v{n}"
        if c.get("behind"):                                   # huge words behind the person: person mask over a text layer
            fg.append(f"[{n}:v]setpts=(PTS-STARTPTS)/{c['speed']},{extra}{fit_filter(fit, W, H, n, c)},fps={fps},format=yuv420p,setsar=1,settb=1/{fps}[bh{n}]")
            lines, n_in = behind_chain(c, n, W, H, fps, n_in, cmd, extra, tmp); fg += lines
            fg.append(f"[bhout{n}]null[{label}]")
        else:
            fg.append(f"[{n}:v]setpts=(PTS-STARTPTS)/{c['speed']},{extra}{fit_filter(fit, W, H, n, c)},fps={fps},format=yuv420p,setsar=1,settb=1/{fps}[{label}]")
        if c.get("broll"):
            for b in c["broll"]:
                if not pathlib.Path(b["src"]).is_absolute(): b["src"] = str((pathlib.Path(plan["_base"]) / b["src"]).resolve())
            lines, n_in = broll_chain(c, n, W, H, fps, n_in, cmd); fg += lines
            fg[-1] = fg[-1].replace(f"null[v{n}]", f"settb=1/{fps}[v{n}]")
    n = n_in
    acc = "v0"; acc_len = tl[0]["dur"]
    for c in tl[1:]:
        k = c["i"]; out = f"x{k}"
        if c["trans"]:
            ty = c["trans"].get("type", "fade")
            fg.append(f"[{acc}][v{k}]xfade=transition={ty}:duration={c['tdur']:.3f}:offset={acc_len - c['tdur']:.3f},settb=1/{fps}[{out}]")
            acc_len += c["dur"] - c["tdur"]
        else:
            fg.append(f"[{acc}][v{k}]concat=n=2:v=1:a=0,settb=1/{fps}[{out}]"); acc_len += c["dur"]   # xfade needs equal timebases
        acc = out
    titles = []
    for c in tl:                                            # titles given per clip use clip time
        for it in c.get("titles", []): titles.append({**it, "start": c["start"] + it["start"], "end": c["start"] + it["end"]})
    titles += plan.get("titles", [])
    hl = plan.get("headline")                       # topic that stays on screen the whole clip (podcast Shorts)
    if hl:
        first_card = min((c["start"] for c in tl if c.get("card") and c["start"] > float(hl.get("start", 0.0))), default=total)
        hs, he = float(hl.get("start", 0.0)), float(hl.get("end", first_card))   # a text card takes the whole screen
        size = int(hl.get("size", round(H * 0.04))); m = float(hl.get("margin", 0.03))   # top band, above the face
        titles.append({"text": hl["text"], "start": hs, "end": he, "pos": "top", "margin": m, "size": size, "anim": "pop",
                       "underline": True, "accent": hl.get("accent", ACCENT), "fade": 0.2})
        if hl.get("tag"):
            lines = str(hl["text"]).count("\n") + 1
            titles.append({"text": hl["tag"], "start": hs + 0.3, "end": he, "pos": "top", "size": int(size * 0.42), "fade": 0.2,
                           "margin": m + (size * 1.25 * lines + size * 0.35) / H, "color": [235, 235, 235]})
    warn = [f"title '{it['text'][:20]}' ends at {it['end']:.2f} s, after the {total:.2f} s timeline" for it in titles if it["end"] > total + 0.01]
    for w in warn: print("WARNING", w)
    tail = []
    if titles:
        ap_ = tmp / "titles.ass"; titles_ass(titles, W, H, ap_)
        tail.append(f"ass='{ap_.resolve().as_posix().replace(':', chr(92) + ':')}'" + ass_fontsdir())
    sub = plan.get("subtitles")
    if sub:
        p = pathlib.Path(sub["src"]).resolve().as_posix().replace(":", r"\:")
        if sub["src"].lower().endswith(".ass"):          # styled captions (word_captions.py): keep their own style
            tail.append(f"ass='{p}'" + ass_fontsdir()); sub = None
    if sub:
        style = sub.get("style", f"FontName={SANS},FontSize={16 if W >= H else 11},Bold=1,Outline=1.2,Shadow=1,MarginV={22 if W >= H else 60}")
        tail.append(f"subtitles='{p}':force_style='{style}'" + ass_fontsdir())
    if a0 is not None: tail.append(f"trim={a0}:{a1},setpts=PTS-STARTPTS,scale=iw/2:-2")
    tail.append("scale=out_range=tv,format=yuv420p")
    fg.append(f"[{acc}]{','.join(tail)}[vout]")
    out = tmp / "video.mp4"
    subprocess.run(cmd + ["-filter_complex", ";".join(fg), "-map", "[vout]", "-c:v", "libx264", "-crf", str(plan["output"].get("crf", 19)),
                          "-preset", "medium", "-color_range", "tv", "-an", str(out)], check=True)
    return out


# ---------- audio ----------------------------------------------------------------------------------------------
def decode(src, ss=None, t=None, speed=1.0):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", str(ss)] if ss is not None else []) + (["-t", str(t)] if t is not None else []) + ["-i", src]
    af = []
    s = speed
    while s > 2.0: af.append("atempo=2.0"); s /= 2.0
    while s < 0.5: af.append("atempo=0.5"); s /= 0.5
    if abs(s - 1) > 1e-6: af.append(f"atempo={s}")
    r = subprocess.run(cmd + (["-af", ",".join(af)] if af else []) + ["-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).astype(np.float64) if r.stdout else np.zeros((0, 2))


def db(x): return 10 ** (x / 20)
def rms(x): return float(np.sqrt(np.mean(x ** 2)) + 1e-9) if len(x) else 1e-9


def place(bus, x, start, gain=1.0, fin=0.0, fout=0.0):
    i = int(round(start * SR)); x = x * gain
    if fin > 0: k = min(len(x), int(fin * SR)); x[:k] *= np.linspace(0, 1, k)[:, None]
    if fout > 0: k = min(len(x), int(fout * SR)); x[len(x) - k:] *= np.linspace(1, 0, k)[:, None]
    if i < 0: x = x[-i:]; i = 0
    j = min(len(bus), i + len(x)); bus[i:j] += x[: j - i]


def render_audio(plan, tl, total, tmp):
    N = int(total * SR) + 1; speech = np.zeros((N, 2)); other = np.zeros((N, 2))
    talk = []
    for c in tl:                                            # clip sound, with the same overlap as the picture transition
        if c.get("card"): continue                          # cards are silent (music carries them)
        g = db(float(c.get("volume_db", 0))); x = decode(c["src"], c["in"], c["out"] - c["in"], c["speed"])
        edge = max(0.01, c["tdur"]); nxt = next((d for d in tl if d["i"] == c["i"] + 1), None)
        fout = max(0.01, nxt["tdur"]) if nxt else 0.01
        place(speech if c.get("speech", True) else other, x, c["start"], g, edge, fout)
        if c.get("speech", False) and c.get("talk"): talk += [(c["start"] + a, c["start"] + b) for a, b in c["talk"]]
    music_items = []
    for a in plan.get("audio", []):
        role = a.get("role", "sfx")
        if role == "music": music_items.append(a); continue
        x = decode(a["src"], a.get("in"), (a["out"] - a.get("in", 0)) if "out" in a else None)
        place(speech if role == "voice" else other, x, float(a["start"]), db(float(a.get("volume_db", 0))), float(a.get("fade_in", 0.01)), float(a.get("fade_out", 0.01)))
        if role == "voice": talk.append((float(a["start"]), float(a["start"]) + len(x) / SR))
    if plan.get("subtitles", {}).get("duck_from", True) and plan.get("subtitles"): talk += srt_spans(plan["subtitles"]["src"])
    if not talk and np.abs(speech).max() > 0:              # no speech times given: detect them from the clip/voice sound
        hop = int(0.1 * SR); e = np.sqrt(np.mean(speech[: len(speech) // hop * hop].reshape(-1, hop, 2) ** 2, axis=(1, 2))) + 1e-9
        lev = 20 * np.log10(e); thr = max(-45.0, np.percentile(lev, 90) - 18); on = lev > thr; k = 0
        while k < len(on):
            if on[k]:
                j = k
                while j < len(on) and on[j:j + 5].any(): j += 1          # bridge gaps under 0.5 s
                if j - k >= 3: talk.append((k * 0.1, j * 0.1))
                k = j
            k += 1
    mask = np.zeros(N)
    for a, b in talk: mask[max(0, int((a - 0.5) * SR)): min(N, int((b + 1.5) * SR))] = 1   # lower 0.5 s before speech, back 1.5 s after
    if mask.any():
        k = int(0.4 * SR); c = np.concatenate([[0.0], np.cumsum(mask)]); idx = np.arange(N)
        mask = (c[np.clip(idx + k // 2, 0, N)] - c[np.clip(idx - k // 2, 0, N)]) / k
    sp_level = rms(speech[mask > 0.5]) if (mask > 0.5).any() else db(-20)
    music = np.zeros((N, 2))
    for m in music_items:
        x = decode(m["src"], m.get("in")); s0 = float(m.get("start", 0)); e0 = float(m.get("end", total))
        need = int((e0 - s0) * SR)
        if len(x) and m.get("loop", True) and len(x) < need: x = np.tile(x, (need // len(x) + 1, 1))
        x = x[:need]; x = x / rms(x) * sp_level
        place(music, x, s0, 1.0, float(m.get("fade_in", 1.5)), float(m.get("fade_out", 2.5)))
    mm = (plan.get("music_mix") or {})
    gap_db = float(mm.get("gap_db", -8)); under_db = float(mm.get("under_db", -30))   # vlog default: off under speech
    env = db(under_db) * mask + db(gap_db) * (1 - mask)
    mix = speech + other + music * env[:, None]
    peak = np.abs(mix).max()
    if peak > 0.95: mix *= 0.95 / peak
    path = tmp / "mix.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    return path, talk


def loudnorm_filter(wav, lufs, ss=None, t=None):
    """Two-pass loudnorm: measure the mix, then apply a linear gain to hit the target (single pass landed ~1.5 dB low)."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats"] + (["-ss", str(ss), "-t", str(t)] if ss is not None else []) + ["-i", str(wav),
           "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = json.loads(e[e.rindex("{"): e.rindex("}") + 1])
    return (f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")


# ---------- main -----------------------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--preview", nargs=2, type=float); ap.add_argument("--no-qa", action="store_true")
    a = ap.parse_args()
    plan_path = pathlib.Path(a.plan).resolve(); base = plan_path.parent
    plan = json.load(open(plan_path, encoding="utf-8"))
    plan["_base"] = str(base)
    def rp(p): return str((base / p).resolve()) if p else p
    for c in plan["clips"]:
        if c.get("card"):                                   # {"card": {"text", "bg", "size", "anim"}, "in": 0, "out": seconds}
            c.setdefault("src", "card"); c.setdefault("in", 0.0); c["speech"] = False; c["captions"] = False
            c.setdefault("titles", []).append({"text": c["card"]["text"], "start": 0.15, "end": float(c["out"]) - float(c["in"]) - 0.1,
                "pos": "center", "anim": c["card"].get("anim", "words"), "size": c["card"].get("size", 110), "word_step": c["card"].get("word_step", 0.14),
                "accent": c["card"].get("accent", ACCENT)})
        else:
            c["src"] = rp(c["src"])
    for x in plan.get("audio", []): x["src"] = rp(x["src"])
    if plan.get("subtitles"): plan["subtitles"]["src"] = rp(plan["subtitles"]["src"])
    o = plan["output"]; W, H = o.get("size", [1920, 1080]); fps = o.get("fps", 30)
    target = o.get("target", "youtube"); lufs = float(o.get("lufs", TARGETS[target]))
    out = rp(o["path"]) if not a.preview else rp(str(pathlib.Path(o["path"]).with_name(pathlib.Path(o["path"]).stem + f"_preview_{a.preview[0]:g}-{a.preview[1]:g}.mp4")))
    tl, total = build_timeline(plan)
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        a0, a1 = (a.preview if a.preview else (None, None))
        video = render_video(plan, tl, total, W, H, fps, tmp, a0, a1)
        mix, talk = render_audio(plan, tl, total, tmp)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
        cmd += (["-ss", str(a0), "-t", str(a1 - a0)] if a.preview else []) + ["-i", str(mix)]
        subprocess.run(cmd + ["-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", loudnorm_filter(mix, lufs, a0, (a1 - a0) if a.preview else None), "-ar", "48000",
                              "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    json.dump({"duration": round(total, 3), "clips": [{k: c[k] for k in ("i", "src", "in", "out", "start", "end", "speed")} for c in tl],
               "speech": [[round(x, 2), round(y, 2)] for x, y in sorted(talk)]},
              open(out + ".timeline.json", "w", encoding="utf-8"), indent=1)
    print(f"wrote {out} ({total:.2f} s timeline)")
    if not a.no_qa:
        qa = [sys.executable, "-I", str(HERE / "qa_check.py"), out, "--target", target, "--sheet", out + ".sheet.jpg", "--json", out + ".qa.json"]
        cards = [f"{c['start']:.2f}:{c['end']:.2f}" for c in tl if c.get("card")]
        if cards and not a.preview: qa += ["--cards"] + cards
        if plan.get("subtitles") and plan["subtitles"]["src"].lower().endswith(".srt") and not a.preview: qa += ["--subs", plan["subtitles"]["src"]]
        subprocess.run(qa)
