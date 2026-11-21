"""Plan a screen-recording tutorial edit: find where on screen the action is (clicks, typing, dialogs) and when nothing
happens, then write edit-plan clips that zoom to the action and fast-forward idle stretches.

Usage: python -I screen_focus.py <recording> <out_prefix> [--fps 4] [--seg 2.0] [--idle-speed 4] [--idle-max 2] [--min-zoom 0.4]
                                 [--ignore x,y,w,h ...] [--aspect 16:9] [--min-clip 4]
  -> <out_prefix>.json        per-segment activity: {start, end, active, box [x, y, w, h] in source pixels}
  -> <out_prefix>_clips.json  "clips" for an edit plan: each with in/out, speed, and a "crop" region (16:9, at least
                              --min-zoom of the screen width) around the action; idle stretches merged and sped up
  -> <out_prefix>.jpg         sheet of segment frames with the chosen crop drawn in
--ignore masks areas that change by themselves (taskbar clock, blinking cursor in a corner, video thumbnails).
Changes are measured on a half-size grey copy; a pixel counts as changed above 12/255. Read the sheet: a wrong box
(e.g. a tooltip far from the real action) is fixed by editing the crop in the plan.
"""
import argparse, json, subprocess, sys
import numpy as np


def probe(path):
    out = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                                     "-of", "json", path], capture_output=True, text=True).stdout)
    return out["streams"][0]["width"], out["streams"][0]["height"], float(out["format"]["duration"])


def fit_box(box, SW, SH, aspect, min_w, margin=0.08):
    x, y, w, h = box
    w2, h2 = w * (1 + 2 * margin) + 40, h * (1 + 2 * margin) + 40
    W = max(w2, h2 * aspect, min_w * SW); W = min(W, SW); H = W / aspect
    if H > SH: H = SH; W = H * aspect
    cx, cy = x + w / 2, y + h / 2
    X = min(max(0, cx - W / 2), SW - W); Y = min(max(0, cy - H / 2), SH - H)
    return [int(X) // 2 * 2, int(Y) // 2 * 2, int(W) // 2 * 2, int(H) // 2 * 2]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("out_prefix"); ap.add_argument("--fps", type=float, default=4)
    ap.add_argument("--seg", type=float, default=2.0); ap.add_argument("--idle-speed", type=float, default=4); ap.add_argument("--idle-max", type=float, default=2.0)
    ap.add_argument("--min-zoom", type=float, default=0.4); ap.add_argument("--ignore", nargs="*", default=[])
    ap.add_argument("--aspect", default="16:9"); ap.add_argument("--pointer-px", type=int, default=250, help="frames changing fewer half-size pixels than this count as idle (pointer only)")
    ap.add_argument("--min-clip", type=float, default=4.0, help="merge shorter zoom clips into a neighbour (viewers need time to read)")
    a = ap.parse_args()
    SW, SH, dur = probe(a.video); w, h = SW // 2, SH // 2; asp = eval(a.aspect.replace(":", "/"))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"fps={a.fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    mask_ignore = np.zeros((h, w), bool)
    for r in a.ignore:
        x, y, ww, hh = [int(v) // 2 for v in r.split(",")]; mask_ignore[y:y + hh, x:x + ww] = True
    prev, diffs = None, []
    while True:
        b = p.stdout.read(w * h)
        if len(b) < w * h: break
        f = np.frombuffer(b, np.uint8).reshape(h, w).astype(np.int16)
        diffs.append((np.abs(f - prev) > 12) & ~mask_ignore if prev is not None else np.zeros((h, w), bool)); prev = f
    p.wait()
    per = max(1, int(a.seg * a.fps)); segs = []
    for k in range(0, len(diffs), per):
        m = np.any(diffs[k:k + per], axis=0); n = int(m.sum()); t0 = k / a.fps; t1 = min(dur, (k + per) / a.fps)
        peak = max(int(d.sum()) for d in diffs[k:k + per])     # biggest single-frame change: a moving pointer alone stays small
        if n < 30 or peak < a.pointer_px: segs.append({"start": round(t0, 2), "end": round(t1, 2), "active": False, "box": None, "changed": n}); continue
        ys, xs = np.nonzero(m)
        # robust box: 2nd-98th percentile of changed pixels (one stray tooltip does not blow the box up)
        x0, x1 = np.percentile(xs, [2, 98]) * 2; y0, y1 = np.percentile(ys, [2, 98]) * 2
        full = n > 0.35 * w * h           # page change / scroll: show the whole screen
        segs.append({"start": round(t0, 2), "end": round(t1, 2), "active": True, "changed": n,
                     "box": [0, 0, SW, SH] if full else [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]})
    # merge into clips: idle runs -> one sped-up full-screen clip; active runs with similar crops -> one clip
    clips = []
    for s in segs:
        crop = fit_box(s["box"], SW, SH, asp, a.min_zoom) if s["active"] else [0, 0, SW, SH]
        speed = 1.0 if s["active"] else a.idle_speed
        if clips and clips[-1]["speed"] == speed and (speed != 1.0 or max(abs(u - v) for u, v in zip(clips[-1]["crop"], crop)) < 0.12 * SW):
            c = clips[-1]; c["out"] = s["end"]
            if speed == 1.0:                 # grow the crop to cover both segments
                x0 = min(c["crop"][0], crop[0]); y0 = min(c["crop"][1], crop[1])
                x1 = max(c["crop"][0] + c["crop"][2], crop[0] + crop[2]); y1 = max(c["crop"][1] + c["crop"][3], crop[1] + crop[3])
                c["crop"] = fit_box([x0, y0, x1 - x0, y1 - y0], SW, SH, asp, a.min_zoom, margin=0)
        else:
            clips.append({"in": s["start"], "out": s["end"], "speed": speed, "crop": crop})
    def union(c1, c2):
        x0 = min(c1[0], c2[0]); y0 = min(c1[1], c2[1]); x1 = max(c1[0] + c1[2], c2[0] + c2[2]); y1 = max(c1[1] + c1[3], c2[1] + c2[3])
        return fit_box([x0, y0, x1 - x0, y1 - y0], SW, SH, asp, a.min_zoom, margin=0)
    changed = True
    while changed:                          # fold short real-time clips into the neighbour whose crop is closest
        changed = False
        for k, c in enumerate(clips):
            if c["speed"] != 1.0 or c["out"] - c["in"] >= a.min_clip or len(clips) == 1: continue
            nb = [j for j in (k - 1, k + 1) if 0 <= j < len(clips) and clips[j]["speed"] == 1.0]
            if not nb:
                continue
            j = min(nb, key=lambda j: sum(abs(u - v) for u, v in zip(clips[j]["crop"], c["crop"])))
            o = clips[j]; o["in"] = min(o["in"], c["in"]); o["out"] = max(o["out"], c["out"]); o["crop"] = union(o["crop"], c["crop"])
            del clips[k]; changed = True; break
    for k, c in enumerate(clips):           # a short action between idle stretches: borrow time from the idle sides
        short = a.min_clip - (c["out"] - c["in"])
        if c["speed"] != 1.0 or short <= 0: continue
        for j, side in ((k - 1, "out"), (k + 1, "in")):
            if 0 <= j < len(clips) and clips[j]["speed"] != 1.0:
                o = clips[j]; take = min(short / 2, (o["out"] - o["in"]) - 0.5)
                if take <= 0: continue
                if side == "out": o["out"] -= take; c["in"] -= take
                else: o["in"] += take; c["out"] += take
    k = 1                                   # idle slivers under 2 s between two actions: keep them at real time in the earlier shot
    while k < len(clips) - 1:
        c = clips[k]
        if c["speed"] != 1.0 and c["out"] - c["in"] < 2.0 and clips[k - 1]["speed"] == 1.0:
            clips[k - 1]["out"] = c["out"]; del clips[k]
        else: k += 1
    for c in clips:                         # long waits (page loads) never take more than --idle-max seconds of screen time
        if c["speed"] != 1.0: c["speed"] = round(max(c["speed"], (c["out"] - c["in"]) / a.idle_max), 2)
    for k in range(len(clips) - 1, 0, -1):  # neighbours that now share a crop (or both idle) become one clip
        if clips[k]["speed"] == clips[k - 1]["speed"] and clips[k]["crop"] == clips[k - 1]["crop"]:
            clips[k - 1]["out"] = clips[k]["out"]; del clips[k]
    json.dump({"video": a.video, "size": [SW, SH], "duration": dur, "segments": segs}, open(a.out_prefix + ".json", "w"), indent=1)
    json.dump({"clips": [{"src": a.video, **c} for c in clips]}, open(a.out_prefix + "_clips.json", "w"), indent=1)
    from PIL import Image, ImageDraw
    tiles = []
    for c in clips[:30]:
        t = (c["in"] + c["out"]) / 2
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", a.video, "-frames:v", "1", "-vf", "scale=480:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        th = len(raw) // (480 * 3); im = Image.frombytes("RGB", (480, th), raw); d = ImageDraw.Draw(im); k = 480 / SW
        x, y, ww, hh = c["crop"]; d.rectangle((x * k, y * k, (x + ww) * k, (y + hh) * k), outline=(255, 40, 40), width=3)
        lab = f"{c['in']:.0f}-{c['out']:.0f}s x{c['speed']:g}"; d.rectangle((0, 0, 7 * len(lab) + 8, 15), fill=(0, 0, 0)); d.text((4, 2), lab, fill=(255, 255, 0))
        tiles.append(im)
    cols = 5; rows = (len(tiles) + cols - 1) // cols; th = tiles[0].height
    sheet = Image.new("RGB", (cols * 480, rows * th))
    for k, im in enumerate(tiles): sheet.paste(im, (k % cols * 480, k // cols * th))
    sheet.save(a.out_prefix + ".jpg", quality=85)
    act = sum(s["end"] - s["start"] for s in segs if s["active"])
    out_len = sum((c["out"] - c["in"]) / c["speed"] for c in clips)
    print(f"{len(segs)} segments, active {act:.0f} s of {dur:.0f} s; {len(clips)} clips, edited length about {out_len:.0f} s")
