"""Subject-aware reframing for vertical (or square) exports: per clip of an edit plan, find where the person is and add
a "crop" so the 9:16 frame follows them instead of the centre. No model download: it looks for skin-coloured pixels
that move (people talk and gesture; sets, shelves and tables stay still). A wide shot (two people alike, or a small person)
keeps the whole frame over a blurred fill (fit "blur") instead of guessing.

Usage: python -I reframe.py <plan.json> [--out plan_reframed.json] [--aspect 9:16] [--fps 3] [--sheet check.jpg]
  Only clips without a "crop" of their own are changed. Writes the plan with crops and a check sheet: every clip's
  middle frame with the chosen window drawn in. Look at it; move a wrong crop by hand (crop = [x, y, w, h] in source px).
Limits: a person standing still in front of a moving screen or crowd can lose to the motion; dark or strongly
coloured lighting can hide skin. Then set the crop by hand.
"""
import argparse, json, pathlib, subprocess, sys
import numpy as np

SW = 192                                     # analysis width
WINDOW = 0.32                                # crop width as a share of the source width (9:16 from 16:9); set from --aspect


def probe(path):
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", path],
                                  capture_output=True, text=True).stdout)["streams"][0]
    return s["width"], s["height"]


def frames(path, t0, t1, fps, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t0), "-t", str(max(0.2, t1 - t0)), "-i", path, "-vf", f"fps={fps},scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3).astype(np.float32)


def skin(f):
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b; cb = 128 - 0.169 * r - 0.331 * g + 0.5 * b; cr = 128 + 0.5 * r - 0.419 * g - 0.081 * b
    return (cr > 135) & (cr < 180) & (cb > 85) & (cb < 135) & (y > 40)


def subject_x(fr):
    """Horizontal centre (0..1) of the moving, skin-coloured subject; None if nothing found."""
    if len(fr) < 2: return None
    sk = np.mean([skin(f) for f in fr], axis=0)                          # how often a pixel is skin
    mv = np.mean(np.abs(np.diff(fr.mean(axis=3), axis=0)), axis=0)        # how much it changes
    score = sk * (0.3 + np.minimum(mv, 30) / 30)
    col = score.sum(axis=0); col = np.convolve(col, np.ones(9) / 9, "same")
    if col.max() < 1.0: return None
    # slide a window as wide as the vertical crop; crop only if one position holds most of the subject
    n = len(col); win = max(1, int(round(n * WINDOW))); cs = np.concatenate([[0.0], np.cumsum(col)])
    held = cs[win:] - cs[:-win]; k = int(np.argmax(held)); share = held[k] / cs[-1]
    if share < 0.65: return "wide"                 # two people apart, or a group: keep the whole frame
    seg = col[k:k + win]; xs = np.arange(k, k + win)
    return float((xs * seg).sum() / seg.sum() / n)


def two_people(fr, W, H, OW, OH):
    """Split screen for a two-shot: one crop per person (left half, right half), each with the panel aspect W : H/2."""
    sk = np.mean([skin(f) for f in fr], axis=0); mv = np.mean(np.abs(np.diff(fr.mean(axis=3), axis=0)), axis=0)
    score = sk * (0.3 + np.minimum(mv, 30) / 30); h, w = score.shape; crops = []
    pa = OW / (OH / 2)                                   # panel aspect (1080 x 960 -> 1.125)
    for x0, x1 in ((0, w // 2), (w // 2, w)):
        part = score[:, x0:x1]; tot = part.sum()
        if tot < 1: return None
        ys, xs = np.mgrid[0:h, x0:x1]; cx = (xs * part).sum() / tot / w * W
        rows = part.sum(axis=1); cum = np.cumsum(rows) / rows.sum()
        head = float(np.searchsorted(cum, 0.08)) / h * H   # top of the skin mass = the face (hands and arms sit lower)
        cw = min(W / 2, H * pa) * 0.9; ch = cw / pa                 # a bit tighter than half the frame
        lift = 0.40 if not crops else 0.18     # top panel: head lower in the panel, clear of a headline band
        X = int(min(max(0, cx - cw / 2), W - cw)) // 2 * 2; Y = int(min(max(0, head - ch * lift), H - ch)) // 2 * 2
        crops.append([X, Y, int(cw) // 2 * 2, int(ch) // 2 * 2])
    return crops


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan"); ap.add_argument("--out"); ap.add_argument("--aspect"); ap.add_argument("--fps", type=float, default=3)
    ap.add_argument("--sheet")
    ap.add_argument("--stack", action="store_true", help="two-shots become a top/bottom split screen instead of the blur fit")
    ap.add_argument("--punch", type=float, default=0.0, help="alternate normal and this zoom (e.g. 1.3) inside close-ups, one camera = something changes every few seconds")
    ap.add_argument("--every", type=float, default=3.0, help="target seconds between punch-in changes (cut at the nearest pause in speech)")
    ap.add_argument("--words", help="word timings (transcribe_whisper.py / Scribe JSON) so punch cuts land in pauses, never inside a word")
    a = ap.parse_args()
    pp = pathlib.Path(a.plan).resolve(); plan = json.load(open(pp, encoding="utf-8"))
    OW, OH = plan["output"].get("size", [1080, 1920]); asp = eval(a.aspect.replace(":", "/")) if a.aspect else OW / OH
    tiles = []
    new = []                                   # split clips at camera cuts inside them (multi-camera interviews)
    for c in plan["clips"]:
        if c.get("crop") or c.get("card"): new.append(c); continue
        src = str((pp.parent / c["src"]).resolve()); W, H = probe(src); sh = round(SW * H / W)
        fr = frames(src, c["in"], c["out"], 6, SW, sh); cuts = []
        for i in range(1, len(fr)):
            h0 = np.histogram(fr[i - 1], 32, (0, 256))[0]; h1 = np.histogram(fr[i], 32, (0, 256))[0]
            if 0.5 * np.abs(h0 / h0.sum() - h1 / h1.sum()).sum() > 0.15:   # a cut measured 0.275 against a 0.006 baseline
                cuts.append(round(c["in"] + i / 6, 2))
        edges = [c["in"]] + [t for t in cuts if t - c["in"] > 0.5 and c["out"] - t > 0.5] + [c["out"]]
        for j, (t0, t1) in enumerate(zip(edges, edges[1:])):
            part = dict(c); part["in"], part["out"] = t0, t1
            if j: part.pop("transition", None); part.pop("titles", None)
            new.append(part)
    if len(new) != len(plan["clips"]): print(f"split at camera cuts: {len(plan['clips'])} -> {len(new)} clips")
    plan["clips"] = new
    for k, c in enumerate(plan["clips"]):
        if c.get("crop") or c.get("card"): continue
        src = str((pp.parent / c["src"]).resolve()); W, H = probe(src); sh = round(SW * H / W)
        cw = min(W, round(H * asp / 2) * 2); fr = frames(src, c["in"], c["out"], a.fps, SW, sh)
        globals()["WINDOW"] = cw / W
        x = subject_x(fr)
        if x == "wide" and a.stack:        # two people: split screen, one above the other
            st = two_people(fr, W, H, OW, OH)
            if st:
                c["fit"] = "stack"; c["stack"] = st; c.pop("crop", None)
                print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s two-shot -> split screen {st}"); continue
        if x == "wide":                    # keep the whole frame over a blurred fill rather than crop between people
            c["fit"] = "blur"; print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s wide shot -> blur fit"); continue
        cx = (x if x is not None else 0.5) * W
        X = int(min(max(0, cx - cw / 2), W - cw)) // 2 * 2
        c["crop"] = [X, 0, cw, H]; c["fit"] = "crop"
        print(f"clip {k + 1}: {c['in']:.1f}-{c['out']:.1f}s subject at {('%.2f' % x) if x is not None else 'not found (centre)'} -> crop x={X}")
        if a.sheet and len(fr):
            from PIL import Image, ImageDraw
            im = Image.fromarray(fr[len(fr) // 2].astype(np.uint8)).resize((384, round(384 * H / W))); d = ImageDraw.Draw(im); s = 384 / W
            d.rectangle((X * s, 0, (X + cw) * s, im.height - 1), outline=(255, 40, 40), width=3); d.text((4, 2), f"clip {k + 1}", fill=(255, 255, 0))
            tiles.append(im)
    if a.punch > 1.0:                        # punch-in: split close-ups at pauses, every other piece zoomed in
        words = json.load(open(a.words, encoding="utf-8"))["words"] if a.words else []
        gaps = sorted(((w1["end"] + w2["start"]) / 2) for w1, w2 in zip(words, words[1:]) if w2["start"] - w1["end"] >= 0.12)
        new, n_punch = [], 0
        for c in plan["clips"]:
            if not c.get("crop") or c.get("card") or c.get("fit") == "blur" or c["out"] - c["in"] < 2 * a.every * 0.8:
                new.append(c); continue
            cuts, t = [], c["in"] + a.every
            while t < c["out"] - a.every * 0.6:
                near = [g for g in gaps if abs(g - t) < a.every * 0.4 and c["in"] + 1.2 < g < c["out"] - 1.2]
                cut = min(near, key=lambda g: abs(g - t)) if near else (t if not words else None)
                if cut: cuts.append(round(cut, 3)); t = cut + a.every
                else: t += 0.5
            edges = [c["in"]] + cuts + [c["out"]]
            x, y, w, h = c["crop"]
            for j, (t0, t1) in enumerate(zip(edges, edges[1:])):
                part = dict(c); part["in"], part["out"] = t0, t1
                if j: part.pop("transition", None); part.pop("titles", None)
                if j % 2 == 1:                       # zoomed piece: same centre line
                    w2, h2 = int(w / a.punch) // 2 * 2, int(h / a.punch) // 2 * 2
                    part["crop"] = [x + (w - w2) // 2 // 2 * 2, y, w2, h2]; n_punch += 1   # anchored at the top: the face moves down, away from a headline
                new.append(part)
        plan["clips"] = new; print(f"punch-in: {n_punch} zoomed pieces at x{a.punch}, {len(new)} clips")
    out = a.out or str(pp.with_name(pp.stem + "_reframed.json"))
    json.dump(plan, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("wrote", out)
    if tiles:
        from PIL import Image
        cols = 4; rows = (len(tiles) + cols - 1) // cols; th = tiles[0].height; sheet = Image.new("RGB", (cols * 384, rows * th))
        for k, im in enumerate(tiles): sheet.paste(im, (k % cols * 384, k // cols * th))
        sheet.save(a.sheet, quality=85); print("sheet", a.sheet)
