"""Find where the speaker's face is, so a 'fill the screen' crop can follow it."""
import statistics, tempfile
from pathlib import Path
from common import run

FPS = 2          # face samples per second
DEADZONE = 0.07  # the crop only moves once the face is this far (fraction of frame width) from the middle of the crop


def track_face(source, start, end):
    """Return {"x": [[t, x], ...], "y": y} with x, y as fractions of the frame (0..1) and t in seconds from the clip
    start, one keyframe a second. The crop stays still while the speaker sits roughly in place and glides when they
    move. Returns None if no face is found or OpenCV is not installed."""
    try:
        import cv2
    except ImportError:
        return None
    dur = end - start
    with tempfile.TemporaryDirectory() as t:
        run(["ffmpeg", "-y", "-ss", str(start), "-t", f"{dur:.2f}", "-i", str(source), "-vf", f"fps={FPS},scale=640:-2",
             "-q:v", "4", f"{t}/f%04d.jpg"])
        casc = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
                ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml")]
        pts = []
        for f in sorted(Path(t).glob("f*.jpg")):
            img = cv2.imread(str(f))
            if img is None:
                pts.append(None)
                continue
            h, w = img.shape[:2]
            gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            faces = []
            for c in casc:
                faces = c.detectMultiScale(gray, 1.1, 5, minSize=(int(w * 0.05), int(w * 0.05)))
                if len(faces):
                    break
            if len(faces):
                x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
                pts.append((float((x + fw / 2) / w), float((y + fh / 2) / h)))
            else:
                pts.append(None)
    seen = [p for p in pts if p]
    if len(seen) < 2:
        return None
    # fill gaps with the last known position, then smooth with a 2-second median
    xs, last = [], seen[0]
    for p in pts:
        last = p or last
        xs.append(last[0])
    sm = [statistics.median(xs[max(0, i - FPS):i + FPS + 1]) for i in range(len(xs))]
    # camera: stays put until the face drifts out of the dead zone, then moves to it
    cam, cams = sm[0], []
    for v in sm:
        if abs(v - cam) > DEADZONE:
            cam = v
        cams.append(cam)
    key = [[0.0, round(cams[0], 3)]]
    for s in range(1, int(dur) + 1):
        key.append([float(s), round(cams[min(len(cams) - 1, s * FPS)], 3)])
    return {"x": key, "y": round(statistics.median(p[1] for p in seen), 3)}


def x_expr(keys):
    """ffmpeg expression for x at time t: the first value plus one linear ramp per change, no nesting."""
    terms = [f"({b - a:.4f})*clip((t-{t1:.2f})/{t2 - t1:.2f},0,1)" for (t1, a), (t2, b) in zip(keys, keys[1:]) if abs(b - a) > 1e-3]
    return f"({keys[0][1]:.4f}" + "".join("+" + t for t in terms) + ")"


def find_facecam(source, start, end, samples=24):
    """Find a streamer's webcam overlay: the small fixed box with a face in it.

    Returns {"x", "y", "w", "h"} as fractions of the frame, or None. The face must sit in the same
    spot in most sampled frames (a fixed facecam, not people in the gameplay) and be small. The box
    border is found from the median of the frames: the overlay is static while the game moves, so its
    straight top and bottom edges stay sharp there. Webcams are 16:9, so the width follows the height.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    dur = max(1.0, end - start)
    with tempfile.TemporaryDirectory() as t:
        run(["ffmpeg", "-y", "-ss", str(start), "-t", f"{dur:.2f}", "-i", str(source), "-vf",
             f"fps={samples / dur:.4f},scale='min(1920,iw)':-2", "-q:v", "3", f"{t}/f%04d.jpg"])
        frames = [cv2.imread(str(f)) for f in sorted(Path(t).glob("f*.jpg"))]
    frames = [f for f in frames if f is not None]
    if len(frames) < 3:
        return None
    H, W = frames[0].shape[:2]
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    # every face in every frame; the facecam is the spot where a face shows up again and again
    # (gameplay characters and cutscenes move around, the webcam does not)
    found = []
    for i, f in enumerate(frames):
        g = cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
        for b in casc.detectMultiScale(g, 1.1, 6, minSize=(H // 25, H // 25)):
            found.append((i, *map(float, b)))
    if not found:
        return None
    cell = W / 12
    bins = {}
    for i, x, y, w, h in found:
        key = (int((x + w / 2) // cell), int((y + h / 2) // cell))
        bins.setdefault(key, {})[i] = (x, y, w, h)
    def weight(k_v):
        # webcam overlays sit near a side of the frame; a face-like spot in the middle of the
        # gameplay (a parked car, a poster) can recur too, so side positions count a bit more
        (bx, _), v = k_v
        cx = (bx + 0.5) * cell / W
        return len(v) * (1.6 if cx < 0.3 or cx > 0.7 else 1.0)
    ranked = [v for _, v in sorted(bins.items(), key=weight, reverse=True)]
    med = np.median(np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]), axis=0).astype(np.float32)
    fallback = None
    for cand in ranked[:3]:
        if len(cand) < max(3, len(frames) * 0.15):
            break
        box = _box_around(cand, med, W, H)
        if box is None:
            continue
        if box["exact"]:
            return box
        fallback = fallback or box
    return fallback


def _box_around(cand, med, W, H):
    """Webcam rectangle around one recurring face position (pixel boxes in ``cand``), or None."""
    import numpy as np
    arr = np.array(list(cand.values()), dtype=float)
    fx, fy, fw, fh = np.median(arr, axis=0)
    if np.mean(np.abs(arr[:, :2] - (fx, fy)) < fw * 0.6) < 0.6 or fw * fh / (W * H) > 0.06:
        return None  # wandering faces or a full-screen camera: not a facecam overlay
    rows = np.abs(np.diff(med, axis=0))[:, int(max(0, fx - fw)):int(min(W - 1, fx + 2 * fw))].mean(axis=1)
    cols = np.abs(np.diff(med, axis=1))[int(max(0, fy - fh / 2)):int(min(H - 1, fy + 1.5 * fh)), :].mean(axis=0)

    def edge(profile, a, b):
        """Strongest straight line between rows/columns a and b (a static overlay border)."""
        lo, hi = max(0, int(min(a, b))), min(len(profile), int(max(a, b)))
        if hi - lo < 3:
            return None
        i = lo + int(np.argmax(profile[lo:hi]))
        return i if profile[i] > 3 * (np.median(profile) + 1) else None

    top, bottom = edge(rows, fy - 3 * fh, fy - 0.3 * fh), edge(rows, fy + 1.3 * fh, fy + 4 * fh)
    exact = top is not None and bottom is not None and 2.2 * fh <= bottom - top <= 4.5 * fh
    if not exact:
        h = min(H, fh * 3.2)
        w = min(W, h * 16 / 9)
        x = min(max(0, fx + fw / 2 - w / 2), W - w)
        y = min(max(0, fy + fh / 2 - h * 0.45), H - h)
    else:
        y, h = top + 2, bottom - top - 3
        w = min(W, h * 16 / 9)
        right = edge(cols, fx + 1.3 * fw, fx + 5 * fw)
        left = edge(cols, fx - 4 * fw, fx - 0.3 * fw)
        if right is not None and right - w <= fx:
            x = max(0.0, right - w)
        elif left is not None:
            x = left + 2
        else:
            x = min(max(0, fx + fw / 2 - w / 2), W - w)
        w = min(w, W - x)
    return {"x": round(float(x / W), 4), "y": round(float(y / H), 4), "w": round(float(w / W), 4),
            "h": round(float(h / H), 4), "exact": bool(exact)}


def facecam_for_video(source, clips, cache_path):
    """One facecam box for the whole video: look in several clips and keep the box found most often.

    The webcam stays in one place for a whole stream, so this is cached in facecam.json; edit that
    file (fractions of the frame) to correct it by hand.
    """
    import json
    cache = Path(cache_path)
    if cache.exists():
        return json.loads(cache.read_text())
    votes = {}
    for c in clips[:6]:
        box = find_facecam(source, float(c["start"]), float(c["end"]))
        if box:
            key = tuple(round(box[k] / 0.02) for k in ("x", "y", "w", "h"))
            votes.setdefault(key, []).append(box)
    if not votes:
        return None
    best = max(votes.values(), key=lambda v: (sum(b["exact"] for b in v), len(v)))
    box = best[0]
    cache.write_text(json.dumps(box, indent=2))
    return box
