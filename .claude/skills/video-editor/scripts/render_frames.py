"""Render a Pillow compositor's frames on every CPU core, then (optionally) encode the video with safe settings.

The compositor is any .py file with a function render(t) -> PIL.Image (t in seconds); its module level loads assets
once per worker, and its `if __name__ == "__main__":` block is not run.

Usage
  python -I render_frames.py <compositor.py> <frames_dir> --end 136.88 [--start 0] [--fps 24] [--workers N]
                             [--func render] [--time-map v2_map.json] [--quality 92]
                             [--encode out.mp4 --audio mix.wav [--subs subs.srt] [--sub-style "FontName=..."] [--lufs -18.5]]
  --time-map  frames sit on the NEW timeline and the compositor is called with to_old(t) (see retime.py)
  --encode    H.264 yuv420p limited range (JPEG frames are full range; without scale=out_range=tv some players and
              uploads show the picture washed out), AAC 192k, loudnorm, faststart. Writes a 720p copy next to it with --720p.
Frames are numbered from 1 (f_0001.jpg) whatever --start is, so the encode starts at --start in the audio.
"""
import argparse, importlib.util, multiprocessing as mp, os, pathlib, re, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))   # python -I leaves the script folder off the path

_mod = _fn = _map = None


def _init(path, func, map_path):
    global _mod, _fn, _map
    sys.path.insert(0, str(pathlib.Path(path).parent)); os.chdir(pathlib.Path(path).parent)
    spec = importlib.util.spec_from_file_location("compositor", path); _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod); _fn = getattr(_mod, func)
    if map_path:
        sys.path.insert(0, str(pathlib.Path(__file__).parent)); from retime import load_map
        _map = load_map(map_path)[0]


def _work(job):
    out, quality, fps, i0, idx = job
    for i in idx:
        t = i / fps; im = _fn(_map(t) if _map else t)
        im.convert("RGB").save(os.path.join(out, f"f_{i - i0 + 1:04d}.jpg"), quality=quality)
    return len(idx)


def encode(a, i0):
    vf = "scale=out_range=tv,format=yuv420p"
    if a.subs:
        style = f":force_style='{a.sub_style}'" if a.sub_style else ""
        subs = pathlib.Path(a.subs).resolve()
        if i0:                                      # partial range: move cues to the clip's own clock
            off = i0 / a.fps
            def shift(m):
                v = max(0.0, int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000 - off)
                return "%02d:%02d:%02d,%03d" % (v // 3600, v % 3600 // 60, int(v % 60), round(v % 1 * 1000) % 1000)
            subs_shift = pathlib.Path(a.encode).with_suffix(".shifted.srt")
            subs_shift.write_text(re.sub(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", shift, subs.read_text(encoding="utf-8-sig")), encoding="utf-8")
            subs = subs_shift
        sub = subs.as_posix().replace(":", r"\:")
        from fonts import ass_fontsdir
        vf = f"subtitles='{sub}'{style}{ass_fontsdir()}," + vf
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(a.fps), "-i", str(pathlib.Path(a.frames_dir) / "f_%04d.jpg")]
    if a.audio: cmd += ["-ss", f"{i0 / a.fps:.3f}", "-i", a.audio]
    cmd += ["-vf", vf, "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-color_range", "tv"]
    if a.audio: cmd += ["-af", f"loudnorm=I={a.lufs}:TP=-2", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    subprocess.run(cmd + ["-movflags", "+faststart", a.encode], check=True)
    if a.p720:
        small = str(pathlib.Path(a.encode).with_name(pathlib.Path(a.encode).stem + "_720p.mp4"))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", a.encode, "-vf", "scale=1280:-2,format=yuv420p",
                        "-c:v", "libx264", "-crf", "23", "-color_range", "tv", "-c:a", "copy", "-movflags", "+faststart", small], check=True)
        print("wrote", small)
    print("wrote", a.encode)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("compositor"); ap.add_argument("frames_dir")
    ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--fps", type=int, default=24); ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--func", default="render"); ap.add_argument("--time-map"); ap.add_argument("--quality", type=int, default=92)
    ap.add_argument("--encode"); ap.add_argument("--audio"); ap.add_argument("--subs"); ap.add_argument("--sub-style")
    ap.add_argument("--lufs", type=float, default=-14.0); ap.add_argument("--720p", dest="p720", action="store_true")
    a = ap.parse_args()
    comp = str(pathlib.Path(a.compositor).resolve()); out = str(pathlib.Path(a.frames_dir).resolve()); os.makedirs(out, exist_ok=True)
    tmap = str(pathlib.Path(a.time_map).resolve()) if a.time_map else None
    for k in ("audio", "subs", "encode"):
        if getattr(a, k): setattr(a, k, str(pathlib.Path(getattr(a, k)).resolve()))
    i0, i1 = int(round(a.start * a.fps)), int(round(a.end * a.fps)); frames = list(range(i0, i1)); chunk = a.fps   # one second per job
    jobs = [(out, a.quality, a.fps, i0, frames[k:k + chunk]) for k in range(0, len(frames), chunk)]
    t0 = time.time(); done = 0
    with mp.get_context("spawn").Pool(a.workers, initializer=_init, initargs=(comp, a.func, tmap)) as pool:
        for n in pool.imap_unordered(_work, jobs):
            done += n
            if done % (a.fps * 20) < n or done == len(frames):
                el = time.time() - t0; print(f"{done}/{len(frames)} frames, {el:.0f} s, about {el / done * (len(frames) - done):.0f} s left", flush=True)
    print(f"rendered {len(frames)} frames with {a.workers} workers in {time.time() - t0:.0f} s")
    if a.encode: encode(a, i0)
