"""Realistic dark-mode messaging UI rendered with Pillow.

The phone state is a pure function of time: given the story's message list,
``PhoneUI.render(t)`` returns the screen image at time ``t`` (lock-screen
notification, chat thread, typing indicator, text being typed in the input
field with the keyboard up, sent/delivered states).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCREEN_W, SCREEN_H = 1000, 2166  # ~19.5:9 phone screen

BG = (0, 0, 0)
INCOMING = (38, 38, 41)
OUTGOING = (10, 132, 255)
TEXT = (245, 245, 247)
MUTED = (142, 142, 147)
SEPARATOR = (40, 40, 44)


@lru_cache(maxsize=None)
def font(size: int, weight: str = "Medium") -> ImageFont.FreeTypeFont:
    for pattern in (f"Inter:style={weight}", "Inter", "DejaVu Sans"):
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", pattern],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
            if path:
                return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default(size)


@dataclass
class Message:
    t: float                 # time the bubble appears
    side: str                # "them" | "me"
    text: str
    typing: float = 1.2      # them: seconds of "…" before; me: seconds spent typing
    status: str = ""         # e.g. "Delivered" under the last outgoing bubble


@dataclass
class PhoneState:
    contact: str = "Unknown"
    clock: str = "23:50"
    messages: list[Message] = field(default_factory=list)
    lock_until: float = 0.0  # before this time, show the lock screen with a notification


def _wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if f.getlength(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def _ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


class PhoneUI:
    def __init__(self, state: PhoneState):
        self.s = state
        self.f_msg = font(46, "Regular")
        self.f_small = font(30, "Medium")
        self.f_name = font(36, "SemiBold")
        self.f_status = font(34, "SemiBold")
        self.f_key = font(44, "Regular")

    # ------------------------------------------------------------------
    def typed_text(self, t: float) -> tuple[str, Message | None]:
        """Text currently in the input field (outgoing message being typed)."""
        for m in self.s.messages:
            if m.side == "me" and m.t - m.typing <= t < m.t:
                frac = (t - (m.t - m.typing)) / max(0.01, m.typing - 0.25)
                n = int(len(m.text) * min(1.0, frac))
                return m.text[:n], m
        return "", None

    def key_times(self) -> list[float]:
        """Times of each simulated key press (for typing sounds)."""
        out = []
        for m in self.s.messages:
            if m.side == "me":
                start, dur = m.t - m.typing, max(0.01, m.typing - 0.25)
                out += [start + dur * (i + 1) / len(m.text) for i in range(len(m.text))
                        if m.text[i] != " " or i % 2]
        return out

    # ------------------------------------------------------------------
    def _status_bar(self, d: ImageDraw.ImageDraw, color=TEXT) -> None:
        d.text((95, 52), self.s.clock, font=self.f_status, fill=color)
        x = SCREEN_W - 95
        # battery
        d.rounded_rectangle((x - 62, 58, x, 88), radius=8, outline=color, width=3)
        d.rectangle((x - 57, 63, x - 25, 83), fill=color)
        d.rounded_rectangle((x + 3, 67, x + 7, 79), radius=2, fill=color)
        # signal bars
        for i in range(4):
            h = 10 + i * 6
            d.rounded_rectangle((x - 140 + i * 12, 88 - h, x - 132 + i * 12, 88), radius=2,
                                fill=color if i < 3 else (90, 90, 94))
        # dynamic island
        d.rounded_rectangle((SCREEN_W / 2 - 125, 30, SCREEN_W / 2 + 125, 104), radius=37, fill=(0, 0, 0))

    def _lock_screen(self, t: float) -> Image.Image:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), (6, 8, 14))
        d = ImageDraw.Draw(img)
        # subtle wallpaper gradient
        for y in range(0, SCREEN_H, 6):
            v = int(10 + 14 * (y / SCREEN_H))
            d.rectangle((0, y, SCREEN_W, y + 6), fill=(v // 2, v // 2 + 1, v + 6))
        self._status_bar(d)
        d.text((SCREEN_W / 2, 330), "Saturday, 14 November", font=font(40, "Medium"),
               fill=(220, 220, 228), anchor="mm")
        d.text((SCREEN_W / 2, 500), self.s.clock, font=font(250, "SemiBold"),
               fill=(232, 232, 240), anchor="mm")
        first = next((m for m in self.s.messages if m.side == "them"), None)
        if first and t >= first.t:
            k = _ease_out((t - first.t) / 0.35)
            y0 = 760 - (1 - k) * 60
            card = Image.new("RGBA", (SCREEN_W - 70, 230), (0, 0, 0, 0))
            cd = ImageDraw.Draw(card)
            cd.rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius=44,
                                 fill=(52, 52, 58, int(225 * k)))
            cd.rounded_rectangle((32, 36, 108, 112), radius=20, fill=(48, 209, 88, int(255 * k)))
            cd.ellipse((50, 54, 90, 94), outline=(255, 255, 255, int(255 * k)), width=6)
            cd.text((130, 40), self.s.contact, font=self.f_name, fill=(255, 255, 255, int(255 * k)))
            cd.text((card.width - 40, 44), "now", font=self.f_small, fill=(170, 170, 176, int(255 * k)),
                    anchor="ra")
            lines = _wrap(first.text, font(38, "Regular"), card.width - 170)
            for i, ln in enumerate(lines[:2]):
                cd.text((130, 92 + i * 48), ln, font=font(38, "Regular"),
                        fill=(235, 235, 240, int(255 * k)))
            img.paste(card, (35, int(y0)), card)
        # bottom affordances
        d.rounded_rectangle((SCREEN_W / 2 - 140, SCREEN_H - 32, SCREEN_W / 2 + 140, SCREEN_H - 22),
                            radius=5, fill=(230, 230, 235))
        return img

    def _keyboard(self, d: ImageDraw.ImageDraw, top: int, pressed: str | None) -> None:
        d.rectangle((0, top, SCREEN_W, SCREEN_H), fill=(28, 28, 30))
        rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
        kw, kh, gap = 86, 116, 12
        y = top + 22
        for r, row in enumerate(rows):
            x = (SCREEN_W - (len(row) * kw + (len(row) - 1) * gap)) / 2
            for ch in row:
                hit = pressed == ch
                d.rounded_rectangle((x, y, x + kw, y + kh), radius=12,
                                    fill=(140, 140, 146) if hit else (70, 70, 74))
                d.text((x + kw / 2, y + kh / 2), ch, font=self.f_key, fill=TEXT, anchor="mm")
                x += kw + gap
            y += kh + 26
        d.rounded_rectangle((40, y, 200, y + kh), radius=12, fill=(50, 50, 54))
        d.text((120, y + kh / 2), "123", font=self.f_small, fill=TEXT, anchor="mm")
        d.rounded_rectangle((220, y, SCREEN_W - 220, y + kh), radius=12,
                            fill=(140, 140, 146) if pressed == " " else (70, 70, 74))
        d.text((SCREEN_W / 2, y + kh / 2), "space", font=self.f_small, fill=TEXT, anchor="mm")
        d.rounded_rectangle((SCREEN_W - 200, y, SCREEN_W - 40, y + kh), radius=12, fill=(50, 50, 54))
        d.text((SCREEN_W - 120, y + kh / 2), "return", font=self.f_small, fill=TEXT, anchor="mm")

    def _bubble(self, img: Image.Image, msg: Message, bottom: int, appear: float) -> int:
        """Draw one bubble ending at ``bottom``; returns its top y."""
        maxw = int(SCREEN_W * 0.68)
        lines = _wrap(msg.text, self.f_msg, maxw - 70)
        lh = 60
        w = int(max(self.f_msg.getlength(ln) for ln in lines)) + 70
        h = len(lines) * lh + 38
        top = bottom - h
        k = _ease_out(appear / 0.22)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        color = OUTGOING if msg.side == "me" else INCOMING
        ld.rounded_rectangle((0, 0, w - 1, h - 1), radius=44, fill=color + (255,))
        for i, ln in enumerate(lines):
            ld.text((35, 18 + i * lh), ln, font=self.f_msg, fill=TEXT)
        if k < 1:
            s = 0.6 + 0.4 * k
            layer = layer.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
            a = layer.getchannel("A").point(lambda v: int(v * k))
            layer.putalpha(a)
        x = SCREEN_W - 40 - layer.width if msg.side == "me" else 40
        img.paste(layer, (x, bottom - layer.height), layer)
        return top

    def _chat(self, t: float) -> Image.Image:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG)
        d = ImageDraw.Draw(img)
        typed, typing_msg = self.typed_text(t)
        kb_top = SCREEN_H - 860 if typing_msg else SCREEN_H
        input_top = kb_top - 150 if typing_msg else SCREEN_H - 190
        # messages (newest at bottom)
        visible = [m for m in self.s.messages if m.t <= t]
        bottom = input_top - 30
        typing_them = next((m for m in self.s.messages
                            if m.side == "them" and m.t - m.typing <= t < m.t and m.t > self.s.lock_until), None)
        if typing_them:
            w, h = 170, 100
            d.rounded_rectangle((40, bottom - h, 40 + w, bottom), radius=44, fill=INCOMING)
            for i in range(3):
                ph = (t * 3 - i * 0.25) % 1.0
                c = int(110 + 120 * max(0.0, 1 - abs(ph - 0.3) * 3))
                d.ellipse((72 + i * 38, bottom - 62, 96 + i * 38, bottom - 38), fill=(c, c, c + 4))
            bottom -= h + 22
        last_me = max((i for i, m in enumerate(visible) if m.side == "me"), default=None)
        for i in range(len(visible) - 1, -1, -1):
            m = visible[i]
            if i == last_me and m.status:
                d.text((SCREEN_W - 50, bottom - 2), m.status, font=self.f_small, fill=MUTED, anchor="rb")
                bottom -= 44
            top = self._bubble(img, m, bottom, t - m.t)
            same_side_next = i > 0 and visible[i - 1].side == m.side
            bottom = top - (10 if same_side_next else 30)
            if bottom < 260:
                break
        # header
        d.rectangle((0, 0, SCREEN_W, 250), fill=(18, 18, 20))
        d.line((0, 250, SCREEN_W, 250), fill=SEPARATOR, width=2)
        self._status_bar(d)
        d.text((50, 175), "‹", font=font(90, "Regular"), fill=OUTGOING, anchor="lm")
        d.ellipse((SCREEN_W / 2 - 44, 118, SCREEN_W / 2 + 44, 206), fill=(99, 99, 104))
        d.text((SCREEN_W / 2, 162), "?", font=font(52, "SemiBold"), fill=(230, 230, 235), anchor="mm")
        d.text((SCREEN_W / 2, 232), self.s.contact, font=self.f_small, fill=TEXT, anchor="mm")
        # input bar
        d.rectangle((0, input_top, SCREEN_W, kb_top), fill=(18, 18, 20))
        d.rounded_rectangle((110, input_top + 30, SCREEN_W - 40, input_top + 120), radius=45,
                            outline=(58, 58, 62), width=3)
        d.ellipse((30, input_top + 40, 92, input_top + 102), fill=(58, 58, 62))
        d.text((61, input_top + 70), "+", font=font(54, "Regular"), fill=(200, 200, 205), anchor="mm")
        if typed:
            shown = typed
            while self.f_msg.getlength(shown) > SCREEN_W - 260:
                shown = shown[1:]
            d.text((145, input_top + 75), shown, font=self.f_msg, fill=TEXT, anchor="lm")
            cx = 145 + self.f_msg.getlength(shown) + 6
            if int(t * 2.5) % 2 == 0:
                d.rectangle((cx, input_top + 48, cx + 4, input_top + 104), fill=OUTGOING)
            d.ellipse((SCREEN_W - 120, input_top + 40, SCREEN_W - 50, input_top + 110), fill=OUTGOING)
            d.text((SCREEN_W - 85, input_top + 75), "↑", font=font(44, "SemiBold"), fill=TEXT, anchor="mm")
        else:
            d.text((145, input_top + 75), "Text Message", font=self.f_msg, fill=(90, 90, 96), anchor="lm")
        if typing_msg:
            pressed = typed[-1].lower() if typed and (t * 12) % 1 < 0.5 else None
            self._keyboard(d, kb_top, pressed)
        d.rounded_rectangle((SCREEN_W / 2 - 140, SCREEN_H - 32, SCREEN_W / 2 + 140, SCREEN_H - 22),
                            radius=5, fill=(230, 230, 235))
        return img

    def render(self, t: float) -> Image.Image:
        return self._lock_screen(t) if t < self.s.lock_until else self._chat(t)


def phone_body(screen: Image.Image, scale: float = 1.0) -> Image.Image:
    """Put the screen inside a phone with bezel, rounded corners and glass sheen."""
    bez = 34
    W, H = screen.width + 2 * bez, screen.height + 2 * bez
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=150, fill=(22, 22, 26, 255))
    d.rounded_rectangle((3, 3, W - 4, H - 4), radius=147, outline=(70, 72, 80, 255), width=4)
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, screen.width - 1, screen.height - 1), radius=118, fill=255)
    body.paste(screen, (bez, bez), mask)
    # glass sheen: faint diagonal gradient
    sheen = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(sheen)
    sd.polygon([(0, H * 0.05), (W, -H * 0.15), (W, H * 0.12), (0, H * 0.32)], fill=22)
    sheen = sheen.filter(ImageFilter.GaussianBlur(60))
    white = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    white.putalpha(sheen)
    body = Image.alpha_composite(body, white)
    if scale != 1.0:
        body = body.resize((int(W * scale), int(H * scale)), Image.LANCZOS)
    return body
