"""Add a music bed to a finished short, ducked from caption timestamps (the "v3" method in references/music-rules.md).

Usage: python -I add_music.py <short.mp4> <captions.vtt|-> <clip_start_in_source_s> <music.mp3> <out.mp4> [bed_db] [depth_db]
For a source without audio, pass - for captions. Music becomes the soundtrack at -14 LUFS, looping if needed.
The options below apply when mixing with source audio.
 bed_db   level of the music in gaps, relative to the speech loudness (default -8)
 depth_db extra drop while someone speaks (default 30: music is effectively off while someone talks; use 4 only for a deliberate music-under-talk test, where 10 dB under speech was audible and 20 dB was not)
The music is loudness-matched first (-14 LUFS), then scaled by bed_db. It lowers 0.5s before speech and recovers 1.5s after it.
"""
import json, pathlib, re, subprocess, sys, tempfile

short, vtt, start, music, out = sys.argv[1:6]
bed_db = float(sys.argv[6]) if len(sys.argv) > 6 else -8.0
depth_db = float(sys.argv[7]) if len(sys.argv) > 7 else 30.0
start = float(start)
LEAD, REL = 0.5, 1.5


probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index:format=duration",
     "-of", "json", short],
    capture_output=True, text=True, check=True,
)
source = json.loads(probe.stdout)
length = float(source["format"]["duration"])
has_audio = bool(source["streams"])
if has_audio and vtt == "-":
    sys.exit("Captions are required to duck music under source audio.")
caption_text = pathlib.Path(vtt).read_text(encoding="utf-8") if has_audio else ""
cues = []
for m in re.finditer(r"(?:(\d+):)?(\d+):([\d.]+)[ \t]+-->[ \t]+(?:(\d+):)?(\d+):([\d.]+)", caption_text):
    a = int(m[1] or 0) * 3600 + int(m[2]) * 60 + float(m[3]) - start
    b = int(m[4] or 0) * 3600 + int(m[5]) * 60 + float(m[6]) - start
    if b > 0 and a < length:
        cues.append((max(a, 0), min(b, length)))
cues.sort()
iv = []
for a, b in cues:
    if iv and a - iv[-1][1] < 2:
        iv[-1][1] = max(iv[-1][1], b)
    else:
        iv.append([a, b])

hi = 10 ** (bed_db / 20)
lo = hi * 10 ** (-depth_db / 20)
bumps = [f"clip(min((t-{a - LEAD:.2f})/0.4,({b + REL:.2f}-t)/{REL}),0,1)" for a, b in iv]
mx = bumps[0] if bumps else "0"
for b in bumps[1:]:
    mx = f"max({mx},{b})"
expr = f"{hi:.5f}-({hi - lo:.5f})*{mx}"

if has_audio:
    graph = (f"[1:a]atrim=0:{length},asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-2:LRA=7,volume='{expr}':eval=frame,"
             f"afade=t=in:d=1.5,afade=t=out:st={max(0, length - 3):.2f}:d=3[m];"
             f"[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-2:LRA=11[a]")
    music_input = ["-i", music]
else:
    fade_in = min(1.5, length / 4)
    fade_out = min(3, length / 3)
    graph = (f"[1:a]asetpts=N/SR/TB,atrim=duration={length},loudnorm=I=-14:TP=-2:LRA=7,"
             f"afade=t=in:d={fade_in:.6f},afade=t=out:st={length - fade_out:.6f}:d={fade_out:.6f}[a]")
    music_input = ["-stream_loop", "-1", "-i", music]

with tempfile.TemporaryDirectory() as temp_dir:
    graph_path = pathlib.Path(temp_dir) / "music.txt"
    graph_path.write_text(graph, encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", short, *music_input,
                        "-/filter_complex", str(graph_path), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out], capture_output=True, text=True)
if r.returncode:
    sys.exit(r.stderr[-500:])
covered = sum(b - a for a, b in iv)
print(f"wrote {out}: speech intervals {len(iv)}, speech {covered:.0f}s of {length:.0f}s, gaps {length - covered:.0f}s")
