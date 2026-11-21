#!/usr/bin/env python3
"""Render a phone-message horror short from a story file.

    python render_story.py story.json --out build/

Produces (inside --out):
  <name>.mp4                 final 1080x1920 30 fps H.264/AAC video
  scenes/scene_XX_<name>.mp4 each screenplay scene as its own clip
  audio/*.wav                every synthesized sound effect, the music bed and the full mix
  character_reference.png    a graded still of the character/room used in every shot
  stills/contact_sheet.png   one frame per shot, for quick review

A shot can use real footage or an AI-generated clip instead of the procedural
plate by setting "plate": "path/to/clip.mp4" (or an image) in the story.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plates as P  # noqa: E402
import sound as S  # noqa: E402
from phone_ui import Message, PhoneState, PhoneUI, phone_body  # noqa: E402

W, H = 1080, 1920


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, k):
    return a + (b - a) * k


class Story:
    def __init__(self, path: Path):
        self.path = path
        self.d = json.loads(path.read_text(encoding="utf-8"))
        self.fps = self.d.get("fps", 30)
        self.duration = float(self.d["duration"])
        self.shots = sorted(self.d["shots"], key=lambda s: s["start"])
        self.events = sorted(self.d.get("events", []), key=lambda e: e["t"])
        ph = self.d["phone"]
        self.phone = PhoneState(
            contact=ph.get("contact", "Unknown"), clock=ph.get("clock", "23:50"),
            lock_until=ph.get("lock_until", 0.0),
            messages=[Message(m["t"], m["from"], m["text"], m.get("typing", 1.2), m.get("status", ""))
                      for m in ph["messages"]])

    def shot_at(self, t: float) -> dict:
        cur = self.shots[0]
        for s in self.shots:
            if s["start"] <= t:
                cur = s
        return cur

    def lamp(self, t: float) -> float:
        """Lamp brightness 0..1 with a short flicker when switched on."""
        state, since = self.d.get("lamp_initial", 1.0), -99.0
        for e in self.events:
            if e["type"] == "lamp" and e["t"] <= t:
                state, since = (1.0 if e["state"] == "on" else 0.0), e["t"]
        dt = t - since
        if state == 1.0 and dt < 0.35:
            return [0.0, 0.7, 0.15, 1.0, 0.6, 1.0][min(5, int(dt / 0.06))]
        return state

    def shake(self, t: float) -> float:
        amt = 0.0
        for e in self.events:
            if e["type"] in ("shake", "vibrate") and 0 <= t - e["t"] < 0.9:
                amt += e.get("amount", 1.0) * math.exp(-(t - e["t"]) * 4)
        for m in self.phone.messages:
            if m.side == "them" and 0 <= t - m.t < 0.8:
                amt += 0.6 * math.exp(-(t - m.t) * 5)
        return amt


# --------------------------------------------------------------------------
# camera

def handheld(t: float, amp: float = 1.0) -> tuple[float, float, float]:
    x = (math.sin(t * 0.9 + 1.3) * 0.6 + math.sin(t * 2.3 + 0.2) * 0.3 + math.sin(t * 5.1) * 0.1) * 4 * amp
    y = (math.sin(t * 0.7 + 2.1) * 0.6 + math.sin(t * 1.9 + 4.0) * 0.3 + math.sin(t * 4.7) * 0.1) * 4 * amp
    r = (math.sin(t * 0.5 + 0.7) * 0.7 + math.sin(t * 1.7) * 0.3) * 0.12 * amp
    return x, y, r


def camera(plate: np.ndarray, zoom: float, center: tuple[float, float], t: float,
           shake: float = 0.0, hand: float = 1.0) -> np.ndarray:
    ph, pw = plate.shape[:2]
    hx, hy, hr = handheld(t, hand)
    if shake:
        hx += math.sin(t * 90) * 6 * shake
        hy += math.cos(t * 77) * 4 * shake
    # output->plate: scale so that zoom=1 shows the full plate width
    s = pw / W / zoom
    cx, cy = center[0] * pw + hx, center[1] * ph + hy
    a = math.radians(hr)
    ca, sa = math.cos(a) * s, math.sin(a) * s
    M = np.array([[ca, -sa, cx - ca * W / 2 + sa * H / 2],
                  [sa, ca, cy - sa * W / 2 - ca * H / 2]], np.float32)
    return cv2.warpAffine(plate, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT)


def composite(base: np.ndarray, layer: np.ndarray) -> np.ndarray:
    a = layer[..., 3:4]
    return base * (1 - a) + layer[..., :3] * a


def chromatic(img: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0.01:
        return img
    out = img.copy()
    for ch, k in ((0, 1 + 0.004 * amount), (2, 1 - 0.004 * amount)):
        M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, k)
        out[..., ch] = cv2.warpAffine(img[..., ch], M, (W, H), borderMode=cv2.BORDER_REFLECT)
    return out


class Grader:
    """Dark blue/teal shadows, warm lamp highlights, gentle filmic roll-off, vignette."""

    def __init__(self, exposure: float = 1.25):
        self.exposure = exposure
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((x - W / 2) / (W * 0.62)) ** 2 + ((y - H / 2) / (H * 0.62)) ** 2)
        self.vig = np.clip(1.08 - d ** 2.2 * 0.75, 0.25, 1.0)[..., None].astype(np.float32)

    def __call__(self, lin: np.ndarray) -> np.ndarray:
        x = np.clip(lin * self.exposure, 0, None)
        x = x / (1 + x * 0.35)                        # highlight roll-off
        y = np.power(np.clip(x, 0, 1), 1 / 2.2)
        lum = y.mean(axis=2, keepdims=True)
        shadows = (1 - lum) ** 3
        y = y + shadows * np.array([-0.012, 0.0, 0.03], np.float32)   # blue shadows
        y = y + lum ** 2 * np.array([0.02, 0.005, -0.02], np.float32)  # warm highlights
        y = lum + (y - lum) * 0.85                     # slightly muted saturation
        return np.clip(y * self.vig, 0, 1)


# --------------------------------------------------------------------------

class Renderer:
    def __init__(self, story: Story, base_dir: Path):
        self.st = story
        self.base = base_dir
        self.ui = PhoneUI(story.phone)
        self.grade = Grader(story.d.get("exposure", 1.25))
        self.cache: dict = {}
        self.ext: dict = {}

    def plate(self, key: str):
        if key not in self.cache:
            t0 = time.time()
            self.cache[key] = {
                "room_on": lambda: P.room_plate(1.0, 0.6),
                "room_off": lambda: P.room_plate(0.0, 1.0),
                "behind_on": lambda: P.behind_plate(1.0),
                "behind_off": lambda: P.behind_plate(0.0),
                "clock": P.clock_plate,
                "desk": P.desk_closeup_plates,
                "mirror": P.mirror_plates,
            }[key]()
            print(f"  plate {key} ({time.time() - t0:.1f}s)", flush=True)
        return self.cache[key]

    def external(self, path: str, t_local: float) -> np.ndarray:
        """Frame from a user/AI-supplied clip or still (sRGB) converted to linear."""
        p = (self.base / path).resolve()
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            if p not in self.ext:
                im = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
                self.ext[p] = cv2.resize(im, (P.PW, P.PH), interpolation=cv2.INTER_AREA) ** 2.2
            return self.ext[p]
        cap = self.ext.get(p)
        if cap is None:
            cap = self.ext[p] = cv2.VideoCapture(str(p))
        cap.set(cv2.CAP_PROP_POS_MSEC, t_local * 1000)
        ok, fr = cap.read()
        if not ok:
            return np.zeros((P.PH, P.PW, 3), np.float32)
        fr = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        return cv2.resize(fr, (P.PW, P.PH), interpolation=cv2.INTER_AREA) ** 2.2

    def room(self, which: str, lamp: float) -> np.ndarray:
        on, off = self.plate(f"{which}_on"), self.plate(f"{which}_off")
        return off + (on - off) * lamp

    # ------------------------------------------------------------------
    def phone_frame(self, t: float, shot: dict, k: float) -> np.ndarray:
        lamp = self.st.lamp(t)
        bg = self.room("room", lamp)
        bg_view = camera(bg, 1.35, (0.40, 0.50), t, hand=0.6)
        bg_view = cv2.GaussianBlur(bg_view, (0, 0), 28) * 0.55
        screen = self.ui.render(t)
        body = phone_body(screen, shot.get("phone_scale", 0.86))
        rgba = np.asarray(body, np.float32) / 255
        rgba[..., :3] = rgba[..., :3] ** 2.2  # to linear
        brightness = shot.get("screen_brightness", 0.8) * (1.25 if lamp < 0.3 else 1.0)
        rgba[..., :3] *= brightness
        tilt = lerp(*shot.get("tilt", [-3.0, -1.5]), k)
        ph, pw = rgba.shape[:2]
        hx, hy, hr = handheld(t * 1.3, shot.get("hand", 1.6))
        sh = self.st.shake(t)
        hx += math.sin(t * 95) * 5 * sh
        zoom = lerp(*shot.get("zoom", [1.0, 1.04]), ease(k))
        M = cv2.getRotationMatrix2D((pw / 2, ph / 2), tilt + hr, zoom)
        M[0, 2] += W / 2 - pw / 2 + hx
        M[1, 2] += H / 2 - ph / 2 + hy + shot.get("offset_y", 60)
        layer = cv2.warpAffine(rgba, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        glow = cv2.GaussianBlur(layer[..., 3], (0, 0), 60)[..., None] * P.PHONE * 0.05 * brightness
        frame = bg_view + glow
        return composite(frame, layer)

    def frame(self, t: float) -> np.ndarray:
        st = self.st
        shot = st.shot_at(t)
        dur = shot["end"] - shot["start"]
        tl = t - shot["start"]
        k = tl / dur if dur > 0 else 0
        z = lerp(*shot.get("zoom", [1.0, 1.05]), ease(k))
        c0, c1 = shot.get("center", [[0.5, 0.5], [0.5, 0.5]])
        center = (lerp(c0[0], c1[0], ease(k)), lerp(c0[1], c1[1], ease(k)))
        kind = shot["type"]
        lamp = st.lamp(t)
        sh = st.shake(t)
        hand = shot.get("hand", 1.0)

        if "plate" in shot:
            img = camera(self.external(shot["plate"], tl), z, center, t, sh, hand)
            if kind == "phone_overlay":
                img = composite(img, self.phone_frame_layer(t))
        elif kind == "room":
            img = camera(self.room("room", lamp), z, center, t, sh, hand)
        elif kind == "behind":
            img = camera(self.room("behind", lamp), z, center, t, sh, hand)
        elif kind == "phone":
            img = self.phone_frame(t, shot, k)
        elif kind == "clock":
            img = camera(self.plate("clock"), z, center, t, sh, hand)
            blink = 1.0 if (t % 1.0) < 0.5 else 0.93
            img = img * blink
        elif kind == "book":
            base, book = self.plate("desk")
            a, b = shot.get("lift", [0.3, 0.8])
            lift = ease((k - a) / max(0.01, b - a))
            M = cv2.getRotationMatrix2D((P.PW * 0.5, P.PH * 0.5), 9 * lift, 1 - 0.12 * lift)
            M[0, 2] += P.PW * 0.08 * lift
            M[1, 2] -= P.PH * 0.95 * lift
            moved = cv2.warpAffine(book, M, (P.PW, P.PH), borderValue=(0, 0, 0, 0))
            shadow = cv2.GaussianBlur(moved[..., 3], (0, 0), 25 + 40 * lift)[..., None] * (0.7 - 0.5 * lift)
            plate = composite(base * (1 - shadow), moved)
            img = camera(plate, z, center, t, sh, hand)
        elif kind == "mirror":
            base, refl = self.plate("mirror")
            # the real character sways a little; the reflection follows late, then drifts wrong
            sway = math.sin(t * 1.3) * 6
            lag = math.sin((t - 0.9) * 1.3) * 6 + max(0.0, k - 0.55) * 30
            tilt = max(0.0, k - 0.6) * 6.0
            Mr = cv2.getRotationMatrix2D((P.PW * 0.56, P.PH * 0.40), tilt, 1.0)
            Mr[0, 2] += lag
            refl_m = cv2.warpAffine(refl, Mr, (P.PW, P.PH), borderValue=(0, 0, 0, 0))
            Mb = np.float32([[1, 0, sway * 0.4], [0, 1, 0]])
            plate = cv2.warpAffine(base, Mb, (P.PW, P.PH), borderMode=cv2.BORDER_REFLECT)
            plate = composite(plate, refl_m)
            img = camera(plate, z, center, t, sh, hand)
            if shot.get("warp", True):
                yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
                amp = 2.5 * ease((k - 0.4) / 0.6)
                mx = xx + np.sin(yy / 47 + t * 3) * amp
                img = cv2.remap(img, mx, yy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            img = chromatic(img, lerp(*shot.get("ca", [0.0, 1.0]), ease(k)))
        elif kind == "turn":
            a, b = shot.get("whip", [0.0, 0.5])
            w = ease((k - a) / max(0.01, b - a))
            src = camera(self.room("room", lamp), z, center, t, sh, hand)
            dst = camera(self.room("behind", lamp), z, center, t, sh, hand)
            off = int(w * W)
            img = np.zeros_like(src)
            img[:, : W - off] = src[:, off:]
            if off:
                img[:, W - off:] = dst[:, :off]
            blur = int(1 + 140 * math.sin(math.pi * w))
            if blur > 2:
                img = cv2.blur(img, (blur, 1))
        else:  # black
            img = np.zeros((H, W, 3), np.float32)

        # fades
        fi, fo = shot.get("fade_in", 0.0), shot.get("fade_out", 0.0)
        g = 1.0
        if fi and tl < fi:
            g *= ease(tl / fi)
        if fo and dur - tl < fo:
            g *= ease((dur - tl) / fo)
        return self.grade(img * g)

    def phone_frame_layer(self, t):  # pragma: no cover - used with external plates
        screen = phone_body(self.ui.render(t), 0.86)
        rgba = np.asarray(screen, np.float32) / 255
        out = np.zeros((H, W, 4), np.float32)
        ph, pw = rgba.shape[:2]
        y0, x0 = (H - ph) // 2, (W - pw) // 2
        out[y0:y0 + ph, x0:x0 + pw] = rgba
        out[..., :3] = out[..., :3] ** 2.2 * 0.55
        return out


# --------------------------------------------------------------------------
# audio

def build_audio(st: Story, ui: PhoneUI, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = st.duration + 0.5
    n = int(dur * S.SR)
    mix = np.zeros(n)

    def add(x, t, gain=1.0):
        i = int(t * S.SR)
        if i >= n:
            return
        x = x[: n - i]
        mix[i:i + len(x)] += x * gain

    a = st.d.get("audio", {})
    tension = a.get("tension", [[0, 0.2], [st.duration, 0.8]])
    tt = np.array([p[0] for p in tension])
    tv = np.array([p[1] for p in tension])
    curve = np.interp(np.linspace(0, dur, 400), tt, tv)
    drone = S.drone(dur, curve)
    env = np.ones(n)
    for s0, s1 in a.get("silence", []):
        i0, i1 = int(s0 * S.SR), int(s1 * S.SR)
        ramp = int(0.25 * S.SR)
        env[i0:i1] = 0.04
        env[max(0, i0 - ramp):i0] = np.minimum(env[max(0, i0 - ramp):i0], np.linspace(1, 0.04, i0 - max(0, i0 - ramp)))
        env[i1:i1 + ramp] = np.minimum(env[i1:i1 + ramp], np.linspace(0.04, 1, len(env[i1:i1 + ramp])))
    mix += drone[:n] * 0.32 * env
    mix += S.room_tone(dur) * 1.0
    if a.get("heartbeat"):
        h0, h1 = a["heartbeat"]
        add(S.pulse_heartbeat(h1 - h0), h0, 0.5)

    lib = {k: f() for k, f in S.LIBRARY.items()}
    for name, x in lib.items():
        S.write_wav(out_dir / f"sfx_{name}.wav", x)
    S.write_wav(out_dir / "music_drone.wav", S._norm(drone, 0.8))

    # automatic phone sounds
    for m in st.phone.messages:
        if m.side == "them" and m.text:
            add(lib["vibration"], m.t - 0.05, 0.55)
        if m.side == "me":
            add(lib["send"], m.t, 0.6)
    for i, kt in enumerate(ui.key_times()):
        add(S.key_tap(i), kt, 1.0)
    # explicit cues
    for e in st.events:
        if e["type"] == "sfx":
            add(lib[e["name"]] if e["name"] in lib else S.LIBRARY[e["name"]](), e["t"], e.get("gain", 1.0))
        elif e["type"] == "vibrate":
            add(lib["vibration"], e["t"], e.get("gain", 0.6))
        elif e["type"] == "lamp":
            add(lib["switch"], e["t"], 0.8)
        elif e["type"] == "ticks":
            t = e["t"]
            i = 0
            while t < e["end"]:
                add(S.tick(i % 2 == 1), t, e.get("gain", 0.6))
                t += 1.0
                i += 1

    mix = np.tanh(mix * 1.1) * 0.9
    mix = mix[: int(st.duration * S.SR)]
    path = out_dir / "full_mix.wav"
    S.write_wav(path, mix)
    return path


# --------------------------------------------------------------------------

def render(story_path: Path, out: Path, preview: bool = False) -> Path:
    st = Story(story_path)
    out.mkdir(parents=True, exist_ok=True)
    name = st.d.get("output_name", story_path.stem)
    r = Renderer(st, story_path.parent)
    print("Synthesizing audio…", flush=True)
    audio = build_audio(st, r.ui, out / "audio")

    fps = st.fps if not preview else 10
    total = int(st.duration * fps)
    video_tmp = out / f"{name}.video.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-vf", "noise=alls=7:allf=t+u",
           "-c:v", "libx264", "-preset", "ultrafast" if preview else "slow", "-crf", "23", "-tune", "grain",
           "-pix_fmt", "yuv420p", str(video_tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    print(f"Rendering {total} frames…", flush=True)
    t0 = time.time()
    stills = {}
    for i in range(total):
        t = i / fps
        img = r.frame(t)
        frame8 = (img * 255 + 0.5).astype(np.uint8)
        proc.stdin.write(frame8.tobytes())
        shot = st.shot_at(t)
        mid = (shot["start"] + shot["end"]) / 2
        if abs(t - mid) < 0.5 / fps + 1e-6 and id(shot) not in stills:
            stills[id(shot)] = frame8
        if i % (fps * 2) == 0:
            el = time.time() - t0
            eta = el / max(1, i) * (total - i)
            print(f"  {t:5.1f}s / {st.duration:.0f}s  ({el:.0f}s elapsed, ~{eta:.0f}s left)", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg video encode failed")

    final = out / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video_tmp), "-i", str(audio),
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                    str(final)], check=True)
    video_tmp.unlink(missing_ok=True)

    # per-scene clips
    sc_dir = out / "scenes"
    sc_dir.mkdir(exist_ok=True)
    for i, sc in enumerate(st.d.get("scenes", []), 1):
        slug = "".join(ch if ch.isalnum() else "_" for ch in sc["name"]).strip("_").lower()
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(sc["start"]), "-i", str(final),
                        "-t", str(sc["end"] - sc["start"]), "-c:v", "libx264", "-crf", "23", "-tune", "grain",
                        "-preset", "medium", "-c:a", "aac", "-b:a", "192k",
                        str(sc_dir / f"scene_{i:02d}_{slug}.mp4")], check=True)

    # stills: contact sheet + character reference
    st_dir = out / "stills"
    st_dir.mkdir(exist_ok=True)
    thumbs = [cv2.resize(f, (216, 384)) for f in stills.values()]
    if thumbs:
        cols = 8
        rows = [np.concatenate(thumbs[i:i + cols] + [np.zeros_like(thumbs[0])] * (cols - len(thumbs[i:i + cols])), 1)
                for i in range(0, len(thumbs), cols)]
        Image.fromarray(np.concatenate(rows, 0)).save(st_dir / "contact_sheet.png")
    ref_t = st.d.get("character_reference_time", 3.5)
    Image.fromarray((r.frame(ref_t) * 255).astype(np.uint8)).save(out / "character_reference.png")
    print(f"Done: {final}", flush=True)
    return final


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("story", type=Path)
    ap.add_argument("--out", type=Path, default=Path("build"))
    ap.add_argument("--preview", action="store_true", help="10 fps fast draft")
    ap.add_argument("--frame", type=float, help="render one frame at this time to <out>/frame.png")
    a = ap.parse_args()
    if a.frame is not None:
        st = Story(a.story)
        a.out.mkdir(parents=True, exist_ok=True)
        img = Renderer(st, a.story.parent).frame(a.frame)
        Image.fromarray((img * 255).astype(np.uint8)).save(a.out / "frame.png")
        print(a.out / "frame.png")
        return
    render(a.story, a.out, a.preview)


if __name__ == "__main__":
    main()
