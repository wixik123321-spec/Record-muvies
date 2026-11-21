"""Fonts by role, the same on every OS: the open-licence fonts bundled in assets/fonts (SIL OFL, licences next to
them), falling back to system fonts. libass (titles, captions, subtitles) finds the bundled files through
`ass_fontsdir()`; Pillow measures with `font(role)[1]`.

Roles:  sans          Kanit Bold          (Thai + Latin; fallback Leelawadee UI Bold, then DejaVu Sans Bold)
        serif_italic  Playfair Display Italic (fallback Georgia Italic)  - key words in mixed-type captions
        heavy         Anton               (fallback Impact)               - huge words behind the person
Set VIDEO_EDITOR_FONTS=system to prefer the system fonts (the look of edits made before 1.4).
Thai text must be shaped: libass does it; Pillow only with raqm, see thai_text.py.
"""
import os, pathlib

FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "fonts"
WIN = pathlib.Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
ROLES = {
    "sans": [("Kanit", FONT_DIR / "Kanit-Bold.ttf"), ("Leelawadee UI", WIN / "LeelaUIb.ttf"),
             ("DejaVu Sans", pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
             ("Arial", pathlib.Path("/Library/Fonts/Arial Bold.ttf"))],
    "serif_italic": [("Playfair Display", FONT_DIR / "PlayfairDisplay-Italic.ttf"), ("Georgia", WIN / "georgiai.ttf"),
                     ("DejaVu Serif", pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"))],
    "heavy": [("Anton", FONT_DIR / "Anton-Regular.ttf"), ("Impact", WIN / "impact.ttf"),
              ("DejaVu Sans", pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))],
}


def font(role):
    """(family name for ASS, file path for Pillow) of the first available font for a role."""
    opts = ROLES[role]
    if os.environ.get("VIDEO_EDITOR_FONTS") == "system": opts = opts[1:] + opts[:1]
    for fam, path in opts:
        if path.exists(): return fam, str(path)
    return opts[0][0], str(opts[0][1])                      # name only: libass will try the system


def ass_fontsdir():
    """Filter option that points libass at the bundled fonts, e.g. ass='x.ass':fontsdir='...'."""
    if not FONT_DIR.exists(): return ""
    return ":fontsdir='" + FONT_DIR.as_posix().replace(":", "\\:") + "'"


if __name__ == "__main__":
    for r in ROLES: print(r, font(r))
    print("fontsdir", ass_fontsdir())
