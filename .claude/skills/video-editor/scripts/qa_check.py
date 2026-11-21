"""Automatic quality check of a finished video before it is sent to the user (Claude cannot listen, so measure).

Usage: python -I qa_check.py <video> [--subs subs.srt] [--target youtube|shorts|doc|master] [--sheet sheet.jpg] [--json report.json]
                                     [--fade 1.5]

Checks, each reported as PASS / WARN / FAIL:
  format     resolution, fps, H.264/yuv420p, audio present, faststart (moov before mdat)
  loudness   integrated LUFS against the target, true peak <= -1 dBTP, loudness range
  black      black stretches >= 0.5 s (fade-in/out at the very start and end are ignored)
  freeze     static picture >= 2.5 s (a stalled render, or a hold that should get a slow push)
  silence    audio below -50 dB for >= 3 s
  subtitles  overlaps, cues < 0.8 s or > 7 s, lines wider than 42 characters (Thai marks above/below count as 0), > 2 lines, faster than 20 characters/s,
             cues after the end of the video
  sheet      contact sheet of 12 frames across the clip, to look at before sending
Exit code 1 if any FAIL.

Targets (integrated LUFS, tolerance): youtube -14 +-1.5 (also TikTok/Reels/Shorts uploads), shorts -14 +-1.5,
doc -18.5 +-1.5 (narrated documentaries in this workspace), master -23 +-1 (broadcast EBU R128).
"""
import argparse, json, re, subprocess, sys, unicodedata

TARGETS = {"youtube": (-14, 1.5), "shorts": (-14, 1.5), "doc": (-18.5, 1.5), "master": (-23, 1.0)}
results = []


def report(check, status, msg):
    results.append({"check": check, "status": status, "detail": msg}); print(f"{status:4s}  {check:9s}  {msg}")


def ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stderr


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,color_range,r_frame_rate",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def check_format(path, info):
    v = [s for s in info["streams"] if s["codec_type"] == "video"]; a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not v: report("format", "FAIL", "no video stream"); return
    v = v[0]; num, den = map(int, v["r_frame_rate"].split("/")); fps = num / den if den else 0
    msg = f"{v['width']}x{v['height']} {fps:.2f} fps {v['codec_name']}/{v.get('pix_fmt')}, " + (f"audio {a[0]['codec_name']}" if a else "no audio")
    bad = []
    if v.get("pix_fmt") == "yuvj420p" or v.get("color_range") == "pc":
        bad.append("full-range video (JPEG/PNG frames): some players and uploads show it washed out; encode with -vf scale=out_range=tv,format=yuv420p")
    elif v["codec_name"] != "h264" or v.get("pix_fmt") != "yuv420p": bad.append("use H.264 yuv420p for players and uploads")
    if not a: bad.append("no audio stream")
    with open(path, "rb") as f: head = f.read(4 * 1024 * 1024)
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    if path.lower().endswith((".mp4", ".mov", ".m4v")) and (moov < 0 or (0 <= mdat < moov)): bad.append("not faststart (add -movflags +faststart)")
    report("format", "WARN" if bad else "PASS", msg + ("; " + "; ".join(bad) if bad else ""))


def check_loudness(path, target):
    e = ff(["-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summ = e[e.rfind("Summary:"):]
    I = float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ)[1]); lra = float(re.search(r"LRA:\s+([\d.]+) LU", summ)[1])
    tp = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ); tp = float(tp[1]) if tp and tp[1] != "-inf" else -99
    t, tol = TARGETS[target]; msg = f"{I:.1f} LUFS (target {t} +-{tol}), true peak {tp:.1f} dBTP, LRA {lra:.1f} LU"
    status = "PASS"
    if abs(I - t) > tol: status = "FAIL" if abs(I - t) > 2 * tol else "WARN"
    if tp > -1.0: status = "FAIL" if tp > 0 else ("WARN" if status == "PASS" else status); msg += " (peak too hot)"
    report("loudness", status, msg)


def spans(text, key_s, key_e):
    return [(float(a), float(b)) for a, b in zip(re.findall(key_s + r"\s*(-?[\d.]+)", text), re.findall(key_e + r"\s*(-?[\d.]+)", text))]


IGNORE = []


def check_picture(path, dur, fade):
    e = ff(["-i", path, "-an", "-vf", "fps=12,scale=320:-2,blackdetect=d=0.5:pic_th=0.97,freezedetect=n=0.003:d=2.5", "-f", "null", "-"])
    blacks = [(a, b) for a, b in spans(e, "black_start:", "black_end:") if not (a <= fade or b >= dur - fade)
              and not any(a >= x - 0.5 and b <= y + 0.5 for x, y in IGNORE)]    # deliberate text cards on black
    report("black", "WARN" if blacks else "PASS", ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in blacks) or "none inside the clip")
    starts = [float(x) for x in re.findall(r"freeze_start:\s*([\d.]+)", e)]; ends = [float(x) for x in re.findall(r"freeze_end:\s*([\d.]+)", e)]
    fr = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
    report("freeze", "WARN" if fr else "PASS", ("static picture " + ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in fr) + ": intended hold, or a stalled shot? look at it") if fr else "none >= 2.5 s")


def check_silence(path):
    e = ff(["-i", path, "-vn", "-af", "silencedetect=noise=-50dB:d=3", "-f", "null", "-"])
    s = spans(e, "silence_start:", "silence_end:")
    report("silence", "WARN" if s else "PASS", ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in s) or "no gap >= 3 s below -50 dB")


def width(line):
    """Visible width: Thai vowels and tone marks above/below a consonant (category Mn) take no space."""
    return sum(1 for ch in line if unicodedata.category(ch) != "Mn")


def srt_time(x):
    h, m, s = x.replace(",", ".").split(":"); return int(h) * 3600 + int(m) * 60 + float(s)


def check_subs(path, dur):
    blocks = [b for b in re.split(r"\n\s*\n", open(path, encoding="utf-8-sig").read().strip()) if "-->" in b]
    cues = []
    for b in blocks:
        lines = b.strip().splitlines(); i = next(k for k, l in enumerate(lines) if "-->" in l)
        a, c = [srt_time(x.strip().split()[0]) for x in lines[i].split("-->")]; cues.append((a, c, lines[i + 1:]))
    issues = []
    for k, (a, b, txt) in enumerate(cues):
        chars = sum(width(l) for l in txt); d = b - a; tag = f"#{k + 1} {a:.1f}s"
        if k and a < cues[k - 1][1] - 0.01: issues.append(f"{tag} overlaps the previous cue")
        if d < 0.8: issues.append(f"{tag} only {d:.2f} s on screen")
        if d > 7: issues.append(f"{tag} {d:.1f} s on screen (split it)")
        if len(txt) > 2: issues.append(f"{tag} {len(txt)} lines")
        if any(width(l) > 42 for l in txt): issues.append(f"{tag} line over 42 characters")
        if d > 0 and chars / d > 20: issues.append(f"{tag} {chars / d:.0f} characters/s (hard to read)")
        if b > dur + 0.05: issues.append(f"{tag} ends after the video")
    report("subtitles", "WARN" if issues else "PASS", f"{len(cues)} cues" + ("; " + "; ".join(issues[:8]) + (f"; +{len(issues) - 8} more" if len(issues) > 8 else "") if issues else ""))


def sheet(path, dur, out):
    step = max(dur / 12, 0.5)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vf", f"fps=1/{step:.3f},scale=480:-2,tile=4x3", "-frames:v", "1", out], check=True)
    report("sheet", "PASS", f"{out} (one frame every {step:.1f} s): look at it before sending")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("--subs"); ap.add_argument("--target", choices=TARGETS, default="youtube")
    ap.add_argument("--sheet"); ap.add_argument("--json"); ap.add_argument("--fade", type=float, default=1.5)
    ap.add_argument("--cards", nargs="*", default=[], help="a:b spans that are intended text cards on a dark background (not 'black')")
    a = ap.parse_args()
    IGNORE.extend(tuple(map(float, x.split(":"))) for x in a.cards)
    info = probe(a.video); dur = float(info["format"]["duration"])
    print(f"QA {a.video} ({dur:.1f} s)")
    check_format(a.video, info)
    if any(s["codec_type"] == "audio" for s in info["streams"]):
        check_loudness(a.video, a.target); check_silence(a.video)
    check_picture(a.video, dur, a.fade)
    if a.subs: check_subs(a.subs, dur)
    if a.sheet: sheet(a.video, dur, a.sheet)
    if a.json: json.dump({"video": a.video, "duration": dur, "results": results}, open(a.json, "w", encoding="utf-8"), indent=1)
    worst = "FAIL" if any(r["status"] == "FAIL" for r in results) else "WARN" if any(r["status"] == "WARN" for r in results) else "PASS"
    print("RESULT", worst); sys.exit(1 if worst == "FAIL" else 0)
