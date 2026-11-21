"""Regression tests for the video-editor skill. No downloads, no copyrighted media: every fixture is generated with
ffmpeg (test patterns, tones, flite speech when the build has it). Each test guards a bug that cost a render round.

Usage: python -I tests/run_tests.py [-k name] [--keep]
Exit code 1 if any test fails. About a minute on a laptop.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, time, traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent; SC = ROOT / "scripts"
sys.path.insert(0, str(SC))
PY = [sys.executable, "-I"]
TESTS = []


def test(fn): TESTS.append(fn); return fn


def ff(*args): subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def probe(path, entries="format=duration"):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)


def has_flite():
    return "enable-libflite" in subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"], capture_output=True, text=True).stdout


def make_clip(path, dur, color="testsrc2", size="1280x720", speech=None):
    """A test-pattern video with sound: flite speech if available, else a tone that pulses like speech."""
    a = (f"flite=text='{speech}':voice=slt" if speech and has_flite() else
         f"sine=f=220:d={dur},volume='if(lt(mod(t,1),0.6),1,0.05)':eval=frame")
    ff("-f", "lavfi", "-i", f"{color}=s={size}:r=25:d={dur}", "-f", "lavfi", "-i", a, "-t", dur, "-shortest" if not speech else "-t", dur,
       "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path)


# ---------------------------------------------------------------------------------------------------------------
@test
def fonts_resolve(tmp):
    from fonts import font, ROLES
    for r in ROLES:
        fam, path = font(r); assert pathlib.Path(path).exists(), f"{r}: {path} missing"


@test
def retime_roundtrip(tmp):
    """retime.py: the map is monotonic and to_new(to_old(t)) == t at every anchor."""
    from retime import _interp
    new = [0, 1.4, 8.7, 9.5, 17.2, 30]; old = [0, 1.4, 7.8, 8.7, 14.3, 25]
    for t in new: assert abs(_interp(_interp(t, new, old), old, new) - t) < 1e-6
    assert all(_interp(a, new, old) <= _interp(b, new, old) for a, b in zip(new, new[1:]))


@test
def music_beats_bpm(tmp):
    """music_beats.py finds 120 BPM in a click track."""
    wav = tmp / "click.wav"
    ff("-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,0.5),0.02),sin(2*PI*1000*t),0)':s=44100:d=20", wav)
    out = subprocess.run(PY + [SC / "music_beats.py", wav, "--dur", "20"], capture_output=True, text=True, check=True).stdout
    bpm = float(re.search(r"([\d.]+) BPM", out)[1]); assert abs(bpm - 120) < 2.5 or abs(bpm - 60) < 1.5, out


@test
def edit_plan_render(tmp):
    """edit_plan.py: cuts, xfade after concat (the timebase bug), Thai title, card, still B-roll with bubble, music;
    output length == timeline, limited range, loudness on target, QA PASS."""
    for k, c in enumerate(("testsrc2", "smptebars", "rgbtestsrc")): make_clip(tmp / f"c{k}.mp4", 4, c, speech="This is a test of the editor.")
    ff("-f", "lavfi", "-i", "mandelbrot=s=1600x900", "-frames:v", "1", tmp / "still.jpg")
    ff("-f", "lavfi", "-i", "sine=f=330:d=30", tmp / "music.wav")
    plan = {"output": {"path": "out.mp4", "size": [720, 1280], "fps": 25, "target": "shorts"},
            "clips": [{"src": "c0.mp4", "in": 0, "out": 3, "titles": [{"text": "ที่นี่ **น้ำท่วม**", "start": 0.2, "end": 2.5, "anim": "pop", "underline": True}]},
                      {"src": "c1.mp4", "in": 0.5, "out": 3.5},
                      {"src": "c2.mp4", "in": 0, "out": 3, "transition": {"type": "fade", "dur": 0.4},
                       "broll": [{"src": "still.jpg", "start": 0.5, "end": 2.0}]},
                      {"card": {"text": "Card **text**"}, "in": 0, "out": 2.0, "transition": {"type": "fade", "dur": 0.3}}],
            "headline": {"text": "Headline\n**two lines**"}, "audio": [{"src": "music.wav", "role": "music", "start": 0}],
            "music_mix": {"gap_db": -8, "under_db": -20}}
    json.dump(plan, open(tmp / "plan.json", "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run(PY + [SC / "edit_plan.py", tmp / "plan.json"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    tl = json.load(open(tmp / "out.mp4.timeline.json"))["duration"]
    d = float(probe(tmp / "out.mp4")["format"]["duration"]); assert abs(d - tl) < 0.25, (d, tl)
    v = probe(tmp / "out.mp4", "stream=pix_fmt,color_range")["streams"][0]; assert v["pix_fmt"] == "yuv420p", v
    qa = json.load(open(tmp / "out.mp4.qa.json"))
    fails = [x for x in qa["results"] if x["status"] == "FAIL"]; assert not fails, fails
    loud = next(x for x in qa["results"] if x["check"] == "loudness"); assert loud["status"] == "PASS", loud


@test
def qa_flags_full_range(tmp):
    """qa_check.py warns about full-range (yuvj420p) video, the bug every early render had."""
    ff("-f", "lavfi", "-i", "testsrc2=s=320x240:d=2", "-f", "lavfi", "-i", "sine=d=2", "-pix_fmt", "yuvj420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", tmp / "full.mp4")
    out = subprocess.run(PY + [SC / "qa_check.py", tmp / "full.mp4"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    assert "full-range" in out, out


@test
def thai_marks_drawn(tmp):
    """libass with the bundled font draws the tone mark on an upper vowel: 'ที่' must differ from 'ที'."""
    from edit_plan import titles_ass, ass_fontsdir
    imgs = []
    for k, txt in enumerate(("ที่", "ที")):
        titles_ass([{"text": txt, "start": 0, "end": 2, "pos": "center", "size": 300}], 400, 400, tmp / f"t{k}.ass")
        ff("-f", "lavfi", "-i", "color=black:s=400x400:d=2", "-ss", "1", "-vf", f"ass='{(tmp / f't{k}.ass').as_posix().replace(':', chr(92) + ':')}'{ass_fontsdir()}",
           "-frames:v", "1", "-pix_fmt", "gray", "-f", "rawvideo", tmp / f"t{k}.raw")
        imgs.append((tmp / f"t{k}.raw").read_bytes())
    diff = sum(1 for a, b in zip(*imgs) if abs(a - b) > 60); assert diff > 300, f"only {diff} pixels differ: tone mark missing"


@test
def word_captions_fit(tmp):
    """word_captions.py --style stack --type mix: no line runs off a 9:16 frame (the 'dangerous' overflow)."""
    make_clip(tmp / "s.mp4", 6, speech="x")
    words = {"words": [{"text": t, "start": 0.3 + i * 0.45, "end": 0.3 + i * 0.45 + 0.4, "type": "word"}
                       for i, t in enumerate("Some extraordinarily dangerous incomprehensible places nevertheless".split())]}
    json.dump(words, open(tmp / "w.json", "w"))
    plan = {"output": {"size": [1080, 1920]}, "clips": [{"src": "s.mp4", "in": 0, "out": 6}]}
    json.dump(plan, open(tmp / "p.json", "w"))
    subprocess.run(PY + [SC / "word_captions.py", tmp / "w.json", tmp / "p.json", tmp / "c.ass", "--style", "stack", "--type", "mix"], check=True, capture_output=True)
    from word_captions import width_font
    from fonts import font
    for line in open(tmp / "c.ass", encoding="utf-8"):
        if not line.startswith("Dialogue"): continue
        x = int(re.search(r"\\pos\((-?\d+),", line)[1]); fs = int(re.search(r"\\fs(\d+)", line)[1]); txt = line.rsplit("}", 1)[1].strip()
        path = font("serif_italic")[1] if "\\fn" in line else font("sans")[1]
        assert x >= -2 and x + width_font(txt, fs, path) <= 1080 + 4, (x, fs, txt)


@test
def align_script_lines(tmp):
    """align_script.py finds every script line in a character-timed transcript and keeps them in order."""
    lines = ["the first line here", "and then a second one", "finally the third"]
    t, words = 0.5, []
    for ln in lines:
        for ch in ln.replace(" ", ""):
            words.append({"text": ch, "start": round(t, 2), "end": round(t + 0.08, 2), "type": "word"}); t += 0.08
        t += 0.6
    json.dump({"words": words}, open(tmp / "tr.json", "w")); json.dump(lines, open(tmp / "lines.json", "w"))
    subprocess.run(PY + [SC / "align_script.py", tmp / "tr.json", tmp / "lines.json", tmp / "al"], check=True, capture_output=True)
    tm = json.load(open(tmp / "al_timing.json", encoding="utf-8"))
    assert len(tm) == 3 and all(a["end"] <= b["start"] for a, b in zip(tm, tm[1:])), tm


@test
def screen_focus_zoom(tmp):
    """screen_focus.py: a box that moves in the top-right quarter -> a crop there; a still stretch -> fast-forward."""
    ff("-f", "lavfi", "-i", "color=c=0xe8e8e8:s=1280x720:d=12:r=25",
       "-vf", "drawbox=x='900+40*sin(t*3)':y=120:w=160:h=90:color=red:t=fill:enable='lt(t,5)'", "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp / "scr.mp4")
    subprocess.run(PY + [SC / "screen_focus.py", tmp / "scr.mp4", tmp / "f"], check=True, capture_output=True)
    clips = json.load(open(tmp / "f_clips.json"))["clips"]
    act = [c for c in clips if c["speed"] == 1.0]; idle = [c for c in clips if c["speed"] > 1.0]
    assert act and idle, clips
    x, y, w, h = act[0]["crop"]; assert x + w / 2 > 640 and y + h / 2 < 360, act[0]["crop"]


@test
def find_shots_prefers_sharp(tmp):
    """find_shots.py scores a sharp, steady moment above a blurred one."""
    ff("-f", "lavfi", "-i", "testsrc2=s=640x360:d=6:r=25", "-vf", "gblur=sigma=12:enable='gte(t,3)'",
       "-c:v", "libx264", "-pix_fmt", "yuv420p", tmp / "sh.mp4")
    subprocess.run(PY + [SC / "find_shots.py", tmp / "sh.mp4", tmp / "shots", "--window", "1.5", "--min", "1"], check=True, capture_output=True)
    shots = json.load(open(tmp / "shots.json"))["shots"]
    early = max(s["score"] for s in shots if s["end"] <= 3.1); late = max(s["score"] for s in shots if s["start"] >= 3)
    assert early > late, (early, late)


# ---------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("-k"); ap.add_argument("--keep", action="store_true"); a = ap.parse_args()
    base = pathlib.Path(tempfile.mkdtemp(prefix="ve_tests_")); failed = 0
    for fn in TESTS:
        if a.k and a.k not in fn.__name__: continue
        d = base / fn.__name__; d.mkdir(); t0 = time.time()
        try:
            import os; cwd = os.getcwd(); os.chdir(d); fn(d); os.chdir(cwd)
            print(f"PASS  {fn.__name__:26s} {time.time() - t0:5.1f}s")
        except Exception as e:
            os.chdir(cwd); failed += 1
            print(f"FAIL  {fn.__name__:26s} {time.time() - t0:5.1f}s  {type(e).__name__}: {str(e)[:300]}")
            if a.keep: traceback.print_exc()
    if not a.keep: shutil.rmtree(base, ignore_errors=True)
    else: print("fixtures kept in", base)
    print(f"\n{len([f for f in TESTS if not a.k or a.k in f.__name__]) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
