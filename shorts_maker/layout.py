"""Facecam detection and 9:16 layout planning with OpenCV.

Layouts (output 1080x1920):
* ``split``  - facecam detected in a small region: facecam on top, gameplay below.
* ``face``   - the camera fills a large part of the frame (just chatting / IRL):
               one 9:16 crop that follows the face horizontally.
* ``blur``   - no face found: gameplay centred over a blurred, zoomed copy.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .utils import log


@dataclass
class Layout:
    kind: str                          # split | face | blur
    src_w: int
    src_h: int
    cam: tuple[int, int, int, int] | None = None   # x, y, w, h crop for the facecam
    game: tuple[int, int, int, int] | None = None  # x, y, w, h crop for gameplay
    top_h: int = 0                     # height of the facecam panel (split)
    caption_y: int = 1300              # vertical centre for captions
    exact: bool = False                # facecam border found (not estimated)

    def filter(self, W: int, H: int) -> str:
        """FFmpeg filter chain: [in] -> [lay] (W x H, yuv420p)."""
        if self.kind == "split":
            cx, cy, cw, ch = self.cam
            gx, gy, gw, gh = self.game
            bottom = H - self.top_h
            return (f"[in]split=2[a][b];"
                    f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{self.top_h}:flags=lanczos,setsar=1[cam];"
                    f"[b]crop={gw}:{gh}:{gx}:{gy},scale={W}:{bottom}:flags=lanczos,setsar=1[game];"
                    f"[cam][game]vstack=inputs=2,format=yuv420p[lay]")
        if self.kind == "face":
            gx, gy, gw, gh = self.game
            return (f"[in]crop={gw}:{gh}:{gx}:{gy},scale={W}:{H}:flags=lanczos,"
                    f"setsar=1,format=yuv420p[lay]")
        gx, gy, gw, gh = self.game
        return (f"[in]split=2[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"boxblur=24:2,eq=brightness=-0.08[bg];"
                f"[b]crop={gw}:{gh}:{gx}:{gy},scale={W}:-2:flags=lanczos[fg];"
                f"[bg][fg]overlay=0:(H-h)/2,setsar=1,format=yuv420p[lay]")


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def _sample_frames(path: str, start: float, end: float, n: int = 30) -> list[np.ndarray]:
    cap = cv2.VideoCapture(path)
    frames = []
    try:
        for t in np.linspace(start, end, n):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
            ok, frame = cap.read()
            if ok and frame is not None:
                frames.append(frame)
    finally:
        cap.release()
    return frames


def _detect_faces(frames: list[np.ndarray]) -> list[tuple[int, int, int, int]]:
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    found = []
    for f in frames:
        gray = cv2.equalizeHist(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
        h = gray.shape[0]
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                         minSize=(max(24, h // 25), max(24, h // 25)))
        if len(faces):
            # biggest face in the frame
            found.append(tuple(int(v) for v in max(faces, key=lambda r: r[2] * r[3])))
    return found


def _facecam_box(frames: list[np.ndarray], face: tuple) -> tuple | None:
    """Find the webcam overlay rectangle around the face.

    Overlays are static while the game moves, so the per-pixel median of the
    sampled frames keeps the overlay's straight borders sharp. From the face
    we scan outwards for the strongest horizontal/vertical edge on each side.
    """
    fx, fy, fw, fh = (float(v) for v in face)
    med = np.median(np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]), axis=0)
    med = med.astype(np.float32)
    H, W = med.shape
    gy = np.abs(np.diff(med, axis=0))  # row edges
    gx = np.abs(np.diff(med, axis=1))  # column edges
    x0, x1 = int(max(0, fx - fw)), int(min(W - 1, fx + 2 * fw))
    y0, y1 = int(max(0, fy - fh * 0.5)), int(min(H - 1, fy + 1.5 * fh))

    def best(profile: np.ndarray, lo: int, hi: int, default: int) -> int:
        lo, hi = max(0, lo), min(len(profile), hi)
        if hi - lo < 3:
            return default
        seg = profile[lo:hi]
        i = int(np.argmax(seg))
        return lo + i if seg[i] > 3 * (np.median(profile) + 1) else default

    rows = gy[:, x0:x1].mean(axis=1)
    cols = gx[y0:y1, :].mean(axis=0)
    top = best(rows, int(fy - 3 * fh), int(fy - fh * 0.3), -1)
    bottom = best(rows, int(fy + fh * 1.3), int(fy + 4 * fh), -1)
    left = best(cols, int(fx - 4 * fw), int(fx - fw * 0.3), 0)
    right = best(cols, int(fx + fw * 1.3), int(fx + 5 * fw), -1)
    if min(top, bottom) < 0:
        return None
    y, h = top + 2, bottom - top - 3
    # webcams are 16:9; the horizontal borders are found more reliably than
    # the vertical ones (the room behind the streamer has vertical edges)
    w = min(W, h * 16 / 9)
    if right > 0 and right - w <= fx:
        x = max(0.0, right - w)
    else:
        x = float(left + 2)
    w = min(w, W - x)
    if not (x <= fx and fx + fw <= x + w):
        return None
    if h <= fh * 1.5 or w <= fw * 1.5 or not 0.9 <= w / h <= 2.4:
        return None
    log.debug("Facecam box: x=%d y=%d w=%d h=%d", x, y, w, h)
    return float(x), float(y), float(w), float(h)


def plan_layout(path: str, start: float, end: float, src_w: int, src_h: int,
                W: int = 1080, H: int = 1920) -> Layout:
    frames = _sample_frames(path, start, end)
    faces = _detect_faces(frames) if frames else []
    game_h = src_h
    if len(faces) >= max(3, len(frames) * 0.15):
        arr = np.array(faces, dtype=float)
        med = np.median(arr, axis=0)
        # faces must be in a consistent place (a fixed facecam, not random NPCs)
        consistent = np.mean(np.abs(arr[:, :2] - med[:2]) < med[2] * 0.6) > 0.6
        fx, fy, fw, fh = med
        area = (fw * fh) / (src_w * src_h)
        if consistent and area < 0.06:
            box = _facecam_box(frames, (fx, fy, fw, fh))
            if box is not None:
                cx, cy, cw, ch = box
                top_h = _even(min(H * 0.42, max(H * 0.28, W * ch / cw)))
                aspect = W / top_h
                # trim the box to the panel's aspect around the face
                if cw / ch > aspect:
                    new_w = ch * aspect
                    cx = np.clip(fx + fw / 2 - new_w / 2, cx, cx + cw - new_w)
                    cw = new_w
                else:
                    new_h = cw / aspect
                    cy = np.clip(fy + fh / 2 - new_h * 0.45, cy, cy + ch - new_h)
                    ch = new_h
            else:
                top_h = _even(H * 0.32)
                aspect = W / top_h
                ch = min(src_h, fh * 3.0)
                cw = min(src_w, ch * aspect)
                ch = cw / aspect
                cx = np.clip(fx + fw / 2 - cw / 2, 0, src_w - cw)
                cy = np.clip(fy + fh / 2 - ch * 0.45, 0, src_h - ch)
            g_aspect = W / (H - top_h)
            gw = min(src_w, game_h * g_aspect)
            gx = (src_w - gw) / 2
            log.info("Layout: facecam (split) at x=%d y=%d", fx, fy)
            return Layout("split", src_w, src_h,
                          cam=(_even(cx), _even(cy), _even(cw), _even(ch)),
                          game=(_even(gx), 0, _even(gw), _even(game_h)),
                          top_h=top_h, caption_y=top_h + 170, exact=box is not None)
        if consistent and area >= 0.06:
            gw = min(src_w, src_h * W / H)
            gx = np.clip(fx + fw / 2 - gw / 2, 0, src_w - gw)
            log.info("Layout: full camera (face crop)")
            return Layout("face", src_w, src_h, game=(_even(gx), 0, _even(gw), _even(src_h)),
                          caption_y=int(H * 0.72))
    # gameplay only: keep a 1:1-ish centre region big, blur the rest
    gw = min(src_w, src_h * 1.15)
    gx = (src_w - gw) / 2
    fg_h = int(W * src_h / gw)
    log.info("Layout: gameplay (blur background)")
    return Layout("blur", src_w, src_h, game=(_even(gx), 0, _even(gw), _even(src_h)),
                  caption_y=min(H - 260, (H + fg_h) // 2 + 150))
