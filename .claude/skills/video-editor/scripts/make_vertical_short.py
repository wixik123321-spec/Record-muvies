"""Render a clip in 9:16, 16:9 or 1:1 with optional subtitles and music.

Usage: python -I make_vertical_short.py <window.mp4> <captions.vtt|-> <window_start_s> <skip_s> <len_s> <out.mp4> [lufs] [--music <file>] [--aspect <ratio>] [--framing <mode>]
Subtitles come from YouTube auto captions via vtt_to_srt.py (errors expected; check before publishing).
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile

sizes = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
parser = argparse.ArgumentParser(description="Export a clip with optional subtitles and music.")
parser.add_argument("window", type=pathlib.Path)
parser.add_argument("captions", help="source WebVTT file or - to skip subtitles")
parser.add_argument("window_start", type=float, help="window start in the source, in seconds")
parser.add_argument("skip", type=float, help="clip start within the window, in seconds")
parser.add_argument("length", type=float, help="clip length in seconds")
parser.add_argument("output", type=pathlib.Path)
parser.add_argument("lufs", type=float, nargs="?", default=-14)
parser.add_argument("--music", type=pathlib.Path, help="background music file")
parser.add_argument("--aspect", choices=sizes, default="9:16", help="output aspect ratio (default: 9:16)")
parser.add_argument("--framing", choices=("blur", "crop"), default="blur",
                    help="keep the full frame over a blurred background, or fill with a centered crop")
args = parser.parse_args()

window = args.window.resolve()
captions = pathlib.Path(args.captions).resolve() if args.captions != "-" else None
music = args.music.resolve() if args.music else None
out = args.output.resolve()
for source in (window, captions, music):
    if source is not None and (out == source or (out.exists() and source.exists() and out.samefile(source))):
        parser.error("The output must be a different file from each input.")

audio_probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index",
     "-of", "csv=p=0", str(window)],
    check=True, stdout=subprocess.PIPE, text=True,
)
has_audio = bool(audio_probe.stdout.strip())
if has_audio and music is not None and captions is None:
    parser.error("Provide WebVTT captions to keep music out of speech on a clip with an audio track.")

here = pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(dir=out.parent) as temp_dir:
    tmp = pathlib.Path(temp_dir)
    srt = tmp / "s.srt"
    width, height = sizes[args.aspect]
    square_pixels = "[0:v]scale=w='max(2,round(ih*dar/2)*2)':h=ih,setsar=1"
    cover = (f"scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,"
             f"crop={width}:{height}")
    if args.framing == "crop":
        filters = [f"{square_pixels},{cover},setsar=1[v0]"]
    else:
        filters = [
            f"{square_pixels},split=2[bg][fg]",
            f"[bg]{cover},setsar=1,boxblur=30:5[b]",
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2[f]",
            "[b][f]overlay=(W-w)/2:(H-h)/2[v0]",
        ]
    video = "[v0]"
    if captions is not None:
        subprocess.run(
            [sys.executable, "-I", str(here / "vtt_to_srt.py"), str(captions), str(args.window_start),
             str(args.skip), str(args.length), srt.name],
            check=True, cwd=tmp, stdout=subprocess.PIPE,
        )
        if srt.stat().st_size:
            filters.append("[v0]subtitles=s.srt:force_style='Alignment=2,FontSize=11,Bold=1,Outline=2,MarginV=70'[v]")
            video = "[v]"

    audio_args = []
    if has_audio:
        filters.append(f"[0:a]loudnorm=I={args.lufs}:TP=-2:LRA=11[a]")
        audio_args = ["-map", "[a]", "-c:a", "aac", "-b:a", "128k"]

    result = tmp / f"output{out.suffix}"
    rendered = tmp / "rendered.mp4" if music is not None else result
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(args.skip), "-t", str(args.length),
         "-i", str(window), "-filter_complex", ";".join(filters), "-map", video, *audio_args,
         "-c:v", "libx264", "-crf", "24", "-preset", "fast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(rendered)],
        check=True, cwd=tmp,
    )
    if music is not None:
        subprocess.run(
            [sys.executable, "-I", str(here / "add_music.py"), str(rendered), str(captions) if captions else "-",
             str(args.window_start + args.skip), str(music), str(result)],
            check=True,
        )
    result.replace(out)
print("wrote", out)
