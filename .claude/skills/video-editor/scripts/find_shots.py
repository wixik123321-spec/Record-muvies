"""Find usable shots in footage by picture alone (b-roll, product, event, silent footage): split into shots, score each
on sharpness, steadiness, exposure and length, and write a labelled contact sheet to pick from.

Usage: python -I find_shots.py <video> <out_prefix> [--fps 5] [--cut 0.35] [--min 1.5] [--top 24] [--window 4]
  -> <out_prefix>.json   shots [{id, start, end, dur, sharp, shake, motion, bright, score, best}] sorted by time
  -> <out_prefix>.jpg    the top shots (by score), one frame each at its sharpest moment, labelled "#id start-end score"
Scores are relative within the clip (percentiles), so compare shots of one source, not across sources.
- sharp   variance of a Laplacian on the frame (focus, detail); hand-held blur and focus hunting score low
- shake   frame-to-frame global movement (camera wobble); low is steadier
- motion  change inside the frame after removing global movement (hands, product moving); some is good for demos
- bright  mean luma; too dark or blown out scores low
Claude still has to look at the sheet: the score cannot tell a nice hero shot from a sharp shot of a table.
"""
import argparse, json, subprocess, sys
import numpy as np

W, H = 160, 90


def frames(path, fps):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    while True:
        b = p.stdout.read(W * H)
        if len(b) < W * H: break
        yield np.frombuffer(b, np.uint8).astype(np.float32)
    p.wait()


def lap_var(f):
    g = f.reshape(H, W); l = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(l.var())


def shift(a, b):
    """Global shift between two frames by phase correlation (pixels at 160x90)."""
    A = np.fft.fft2(a.reshape(H, W)); B = np.fft.fft2(b.reshape(H, W)); R = A * np.conj(B); R /= np.abs(R) + 1e-9
    r = np.abs(np.fft.ifft2(R)); y, x = np.unravel_index(np.argmax(r), r.shape)
    if y > H // 2: y -= H
    if x > W // 2: x -= W
    return float(np.hypot(x, y)), int(x), int(y)


def pct(v):
    v = np.asarray(v, float); return (np.argsort(np.argsort(v)) + 0.5) / len(v) if len(v) else v


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("out_prefix"); ap.add_argument("--fps", type=float, default=5)
    ap.add_argument("--cut", type=float, default=0.35, help="histogram distance that starts a new shot")
    ap.add_argument("--min", type=float, default=1.5, help="shortest shot kept, seconds"); ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--window", type=float, default=4.0, help="split shots longer than 2x this into moments of this length (one-take footage)")
    a = ap.parse_args()
    rows, prev, prev_h = [], None, None
    for i, f in enumerate(frames(a.video, a.fps)):
        h = np.histogram(f, 32, (0, 256))[0] / f.size
        cut = prev_h is not None and 0.5 * np.abs(h - prev_h).sum() > a.cut
        sh, dx, dy = shift(prev, f) if prev is not None else (0.0, 0, 0)
        if prev is not None:
            moved = np.roll(prev.reshape(H, W), (dy, dx), axis=(0, 1)).ravel(); mot = float(np.abs(f - moved)[W * 4:-W * 4].mean())
        else: mot = 0.0
        rows.append({"t": i / a.fps, "cut": bool(cut), "sharp": lap_var(f), "shake": sh, "motion": mot, "bright": float(f.mean())})
        prev, prev_h = f, h
    if not rows: sys.exit("no frames decoded")
    dur_total = len(rows) / a.fps
    bounds = [0] + [k for k, r in enumerate(rows) if r["cut"]] + [len(rows)]
    spans, win = [], int(a.window * a.fps)
    for s, e in zip(bounds, bounds[1:]):
        if win and e - s > 2 * win: spans += [(k, min(e, k + win)) for k in range(s, e, win) if min(e, k + win) - k >= win // 2]
        else: spans.append((s, e))
    shots = []
    for s, e in spans:
        seg = rows[s:e]; d = len(seg) / a.fps
        if d < a.min: continue
        sharp = np.array([r["sharp"] for r in seg]); best = seg[int(np.argmax(sharp))]["t"]
        shots.append({"start": round(seg[0]["t"], 2), "end": round(seg[-1]["t"] + 1 / a.fps, 2), "dur": round(d, 2),
                      "sharp": float(np.median(sharp)), "shake": float(np.median([r["shake"] for r in seg])),
                      "motion": float(np.median([r["motion"] for r in seg])), "bright": float(np.median([r["bright"] for r in seg])), "best": round(best, 2)})
    if not shots: sys.exit("no shot longer than --min")
    ps, pk = pct([s["sharp"] for s in shots]), pct([s["shake"] for s in shots])
    for k, s in enumerate(shots):
        expo = 1 - min(1.0, abs(s["bright"] - 120) / 100)
        s["id"] = k + 1; s["score"] = round(0.45 * ps[k] + 0.30 * (1 - pk[k]) + 0.15 * expo + 0.10 * min(1.0, s["dur"] / 6), 3)
        for key in ("sharp", "shake", "motion", "bright"): s[key] = round(s[key], 2)
    top = sorted(shots, key=lambda s: -s["score"])[: a.top]
    json.dump({"video": a.video, "duration": dur_total, "shots": shots}, open(a.out_prefix + ".json", "w", encoding="utf-8"), indent=1)
    # contact sheet of the top shots, labelled (drawn with Pillow: ASCII labels only)
    from PIL import Image, ImageDraw
    tiles = []
    for s in sorted(top, key=lambda s: s["start"]):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(s["best"]), "-i", a.video, "-frames:v", "1", "-vf", "scale=320:180",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        im = Image.frombytes("RGB", (320, 180), raw) if len(raw) == 320 * 180 * 3 else Image.new("RGB", (320, 180))
        d = ImageDraw.Draw(im); lab = f"#{s['id']} {s['start']:.0f}-{s['end']:.0f}s {s['score']:.2f}"
        d.rectangle((0, 0, 8 + 7 * len(lab), 16), fill=(0, 0, 0)); d.text((4, 2), lab, fill=(255, 255, 0)); tiles.append(im)
    cols = 6; rws = (len(tiles) + cols - 1) // cols; sheet = Image.new("RGB", (cols * 320, rws * 180))
    for k, im in enumerate(tiles): sheet.paste(im, (k % cols * 320, k // cols * 180))
    sheet.save(a.out_prefix + ".jpg", quality=85)
    print(f"{len(shots)} shots over {dur_total:.0f} s; top {len(top)} on {a.out_prefix}.jpg")
    for s in sorted(top, key=lambda s: -s["score"])[:10]:
        print(f"  #{s['id']:3d} {s['start']:7.1f}-{s['end']:7.1f}s  score {s['score']:.2f}  sharp {s['sharp']:.0f} shake {s['shake']:.1f} bright {s['bright']:.0f}")
