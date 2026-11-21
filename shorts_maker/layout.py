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


def _sample_frames(path: str, start: float, end: float, n: int = 14) -> list[np.ndarray]:
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


def plan_layout(path: str, start: float, end: float, src_w: int, src_h: int,
                W: int = 1080, H: int = 1920) -> Layout:
    frames = _sample_frames(path, start, end)
    faces = _detect_faces(frames) if frames else []
    game_h = src_h
    if len(faces) >= max(3, len(frames) * 0.3):
        arr = np.array(faces, dtype=float)
        med = np.median(arr, axis=0)
        # faces must be in a consistent place (a fixed facecam, not random NPCs)
        consistent = np.mean(np.abs(arr[:, :2] - med[:2]) < med[2] * 0.6) > 0.6
        fx, fy, fw, fh = med
        area = (fw * fh) / (src_w * src_h)
        if consistent and area < 0.06:
            top_h = _even(H * 0.36)
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
                          top_h=top_h, caption_y=top_h + 170)
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
