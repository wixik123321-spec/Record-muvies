"""Draw shaped Thai text into a Pillow image, even when Pillow has no raqm.

Without raqm Pillow does no Thai shaping, so a tone mark on an upper vowel vanishes
(นั่ง draws as นัง). This module keeps the compositor's Pillow pipeline (fades, pops,
glows) but gets the glyph shapes from libass through ffmpeg, which shapes Thai correctly:

    from thai_text import draw_text, textlength
    draw_text(layer, (x, y), txt, fonts.font("sans")[1], 84, fill=(250, 240, 220, 255),
              stroke_width=4, stroke_fill=(20, 14, 10, 255))

draw_text takes the same top-left (x, y) as ImageDraw.text with anchor "la" and lines the
libass glyphs up with where Pillow would have put them (ink centre and bottom).
With raqm available it simply calls ImageDraw.text. Masks are cached in memory and on disk
(.thai_text_cache next to the calling script), so each label costs two ffmpeg calls once.
"""
import pathlib as _pl, sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))   # python -I leaves the script folder off the path
from fonts import font as _font
import hashlib, os, pathlib, subprocess, tempfile, time
from PIL import Image, ImageChops, ImageDraw, ImageFont, features

RAQM = features.check("raqm")
CACHE = pathlib.Path(os.environ.get("THAI_TEXT_CACHE", ".thai_text_cache"))
_mem = {}


def _family(font_path):
    from fontTools.ttLib import TTFont
    tt = TTFont(font_path, lazy=True); name = tt["name"]
    fam = name.getDebugName(16) or name.getDebugName(1); sub = (name.getDebugName(17) or name.getDebugName(2) or "").lower()
    os2 = tt["OS/2"]; upm = tt["head"].unitsPerEm
    # libass sizes a font by winAscent + winDescent; Pillow sizes it by the em
    return fam, "bold" in sub, (os2.usWinAscent + os2.usWinDescent) / upm


def _render(txt, font_path, size, bord):
    """Grey mask (white text on black) from libass, cropped to the ink, plus its top-left in canvas pixels."""
    key = hashlib.sha1(f"{txt}|{font_path}|{size}|{bord}".encode()).hexdigest()[:16]
    if key in _mem: return _mem[key]
    png = CACHE / f"{key}.png"
    if not png.exists():
        fam, bold, k = _family(font_path)
        cw, ch = int(len(txt) * size * 1.2 + 400), int(size * 3 + 200)   # same canvas for every bord, so masks share a centre
        ass = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nScaledBorderAndShadow: yes\nWrapStyle: 2\n\n"
               "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
               "Style: T,%s,%.2f,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,&H00000000,%d,0,0,0,100,100,0,0,1,%d,0,5,0,0,0,1\n\n"
               "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
               "Dialogue: 0,0:00:00.00,0:00:05.00,T,,0,0,0,,{\\pos(%d,%d)}%s\n") % (cw, ch, fam, size * k, -1 if bold else 0, bord, cw // 2, ch // 2, txt)
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "t.ass").write_text(ass, encoding="utf-8")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={cw}x{ch}:d=1",
                            "-vf", "subtitles=t.ass:fontsdir='" + pathlib.Path(font_path).resolve().parent.as_posix().replace(':', chr(92) + ':') + "'", "-frames:v", "1", "-pix_fmt", "gray", "o.png"], cwd=td, check=True)
            with Image.open(pathlib.Path(td) / "o.png") as o: m = o.convert("L")   # this worker's own copy: no shared read
            tmp = CACHE / f"{key}.{os.getpid()}.png"; os.replace(pathlib.Path(td) / "o.png", tmp)
            try: os.replace(tmp, png)
            except OSError: tmp.unlink(missing_ok=True)   # another worker wrote (or is reading) it: Windows locks it
    else:
        for i in range(50):   # a parallel worker may be replacing the file right now
            try:
                with Image.open(png) as o: m = o.convert("L")
                break
            except OSError:
                if i == 49: raise
                time.sleep(0.05)
    bb = m.getbbox() or (0, 0, 1, 1)
    _mem[key] = (m.crop(bb), bb); return _mem[key]


def textlength(txt, font_path, size):
    return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(txt, font=ImageFont.truetype(font_path, size))


def draw_text(im, xy, txt, font_path, size, fill, stroke_width=0, stroke_fill=None):
    """Like ImageDraw.Draw(im).text(xy, txt, font, fill, stroke_width, stroke_fill), Thai shaped. im is RGBA."""
    f = ImageFont.truetype(font_path, size)
    if RAQM or not any("\u0e00" <= c <= "\u0e7f" for c in txt):
        ImageDraw.Draw(im).text(xy, txt, font=f, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill); return
    # where Pillow would put the ink: centre x and bottom (marks below the line are placed right even unshaped)
    fm, fb = _render(txt, font_path, size, 0)
    layers = [(fm, fill)]
    if stroke_width and stroke_fill is not None:
        sm, sb = _render(txt, font_path, size, stroke_width); layers = [(sm, stroke_fill), (fm, fill)]
    # line the fill mask up with Pillow's unstroked ink, the stroke mask around it with libass's own offset
    pl, _, pr, pb = ImageDraw.Draw(im).textbbox(xy, txt, font=f)
    ox, oy = (pl + pr) / 2 - (fb[0] + fb[2]) / 2, pb - fb[3]
    for m, col in layers:
        bb = fb if m is fm else _render(txt, font_path, size, stroke_width)[1]
        col = tuple(col) + (255,) * (4 - len(col))
        a = m.point(lambda v, k=col[3]: v * k // 255)
        solid = Image.new("RGBA", m.size, col[:3] + (0,)); solid.putalpha(a)
        im.alpha_composite(solid, (int(round(bb[0] + ox)), int(round(bb[1] + oy))))
