"""Check that this machine can run the video-editor skill, and say how to fix what is missing.

Usage: python -I doctor.py [--quick]
Checks: ffmpeg/ffprobe on PATH with libass + harfbuzz (Thai shaping), libx264, flite (test speech); Python 3.10+;
packages (numpy, Pillow required; fontTools for thai_text; faster-whisper, rembg, onnxruntime optional);
bundled fonts; models already downloaded (Whisper, rembg human seg). Nothing is installed or downloaded here:
installing or downloading is the user's call (ask first), the fix lines are printed for them.
Exit code 1 if something required is missing.
"""
import importlib, os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
rows, bad = [], False


def row(status, what, detail="", fix=""):
    global bad
    bad |= status == "MISS"
    rows.append((status, what, detail, fix))


def ffmpeg_checks():
    ff = shutil.which("ffmpeg"); fp = shutil.which("ffprobe")
    if not ff or not fp:
        row("MISS", "ffmpeg + ffprobe", "not on PATH", "install ffmpeg 6+ (Windows: gyan.dev full build; macOS: brew install ffmpeg; Linux: apt install ffmpeg)"); return
    v = subprocess.run([ff, "-hide_banner", "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    conf = subprocess.run([ff, "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout
    row("OK", "ffmpeg", v[:60])
    for lib, need, why in [("libass", True, "titles and captions"), ("libharfbuzz", False, "drawtext shaping only (libass shapes titles itself)"),
                           ("libx264", True, "H.264 export"), ("libfreetype", True, "text"), ("libflite", False, "offline test speech in tests/")]:
        ok = f"enable-{lib}" in conf
        row("OK" if ok else ("MISS" if need else "warn"), f"  {lib}", why, "" if ok else "use a full ffmpeg build")


def py_checks():
    row("OK" if sys.version_info >= (3, 10) else "MISS", "python", sys.version.split()[0], "" if sys.version_info >= (3, 10) else "Python 3.10+")
    for mod, need, why, pipname in [("numpy", True, "audio and image maths", "numpy"), ("PIL", True, "frames, measuring text", "Pillow"),
                                    ("fontTools", False, "thai_text.py (Thai in Pillow without raqm)", "fonttools"),
                                    ("faster_whisper", False, "free local transcripts (English)", "faster-whisper"),
                                    ("rembg", False, "cut-outs, words behind the person", "rembg[cpu]"),
                                    ("onnxruntime", False, "rembg backend", "onnxruntime")]:
        try:
            m = importlib.import_module(mod); row("OK", f"  {pipname}", getattr(m, "__version__", "") + " - " + why)
        except Exception as e:
            row("MISS" if need else "warn", f"  {pipname}", why + (f" ({type(e).__name__})" if not isinstance(e, ImportError) else ""), f"pip install {pipname}")
    try:
        from PIL import features
        row("OK" if features.check("raqm") else "info", "  Pillow raqm", "Thai shaping in Pillow" if features.check("raqm") else "absent: Thai in Pillow goes through thai_text.py (libass)")
    except Exception:
        pass


def asset_checks():
    sys.path.insert(0, str(HERE)); from fonts import ROLES, font, FONT_DIR
    for r in ROLES:
        fam, path = font(r); bundled = str(FONT_DIR) in path
        row("OK" if pathlib.Path(path).exists() else "warn", f"font {r}", f"{fam} ({'bundled' if bundled else 'system'})",
            "" if pathlib.Path(path).exists() else "restore assets/fonts from the repository")
    hf = pathlib.Path.home() / ".cache" / "huggingface" / "hub"
    wh = sorted(p.name.replace("models--Systran--faster-whisper-", "") for p in hf.glob("models--Systran--faster-whisper-*")) if hf.exists() else []
    row("OK" if wh else "info", "whisper models", ", ".join(wh) or "none downloaded (first transcript downloads one: ask first)")
    rb = [p for p in [pathlib.Path.home() / ".rembg" / "models" / "u2net_human_seg" / "u2net_human_seg.onnx", pathlib.Path.home() / ".u2net" / "u2net_human_seg.onnx"] if p.exists()]
    row("OK" if rb else "info", "rembg human model", f"{rb[0]}" if rb else "not downloaded (~176 MB on first 'behind' use: ask first)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ffmpeg_checks(); py_checks(); asset_checks()
    for s, w, d, f in rows:
        print(f"{s:5s} {w:22s} {d}" + (f"\n      fix: {f}" if f and s in ('MISS', 'warn') else ""))
    print("\nRESULT", "MISSING REQUIRED PIECES" if bad else "ready")
    sys.exit(1 if bad else 0)
