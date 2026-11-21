# Record-muvies: Twitch VOD → YouTube Shorts

`shorts_maker` is a Python app that finds the best moments in Twitch VODs (by
default Kai Cenat's GTA 6 streams), cuts them into **10–12 vertical 1080×1920
Shorts** with animated captions, and writes titles, descriptions and hashtags
for each one.

```
python -m shorts_maker
```

That one command lists the channel's archive, picks the GTA 6 VODs, analyses
them, and saves the finished MP4s to `output/shorts/`.

> **Rights:** use this only on videos you're allowed to download and reupload,
> such as your own streams or a streamer's footage with their permission. Many
> streamers allow clipping, but check before you post. The app doesn't
> get around subscriber-only or deleted VODs. It skips them.

---

## What it does

| Step | How |
|---|---|
| 1. Find VODs | `yt-dlp` lists `twitch.tv/<channel>/videos?filter=archives` and keeps VODs whose **title** contains *GTA 6 / GTA VI / GTA* (default: the 3 most recent). Unavailable, private or restricted VODs are skipped. |
| 2. Download only what's needed | Downloads the **audio-only** version of each VOD for analysis (an 8-hour stream is about 0.5 GB instead of tens of GB), then downloads **only the selected time ranges** in up to 1080p. The exact start of each piece is found by audio cross-correlation, so captions stay in sync. |
| 3. Find candidate moments | Streams the audio through FFmpeg and scores every second by loudness and short bursts relative to the previous 5 minutes. Screams, laughter and hype stand out from the stream's normal level. About 36 peaks are kept, at least 75 s apart. |
| 4. Transcribe | **faster-whisper** (`small.en` by default) transcribes a 75 s window around each peak, with word-level timestamps. |
| 5. Rank with AI | **Claude** (`claude-opus-5-5`) sees all candidates at once (transcript and loudness curve) and scores each one for entertainment, emotional reaction, unexpectedness, context clarity, retention and viral potential. It picks start and end points that include the setup and the payoff, writes a title and metadata, and marks duplicates. It's told never to invent context. Without an API key, a heuristic ranking is used instead (loudness, hype words, laughter, speech density). |
| 6. Pick clips | Removes overlaps and duplicates, then keeps the top 12 clips of 20–60 s each. |
| 7. Edit | **OpenCV** finds the facecam. **split** layout: facecam on top, gameplay below. **face** layout: full-camera streams get a crop that follows the face. **blur** layout: gameplay over a blurred background. The editor removes silent pauses (only when the audio is really quiet, so gameplay sound effects stay), adds a 1.12× punch-in zoom on the 1–2 strongest reactions, and adds a 1.8 s cold-open teaser of the peak before the full clip. An optional quiet SFX can play on zoom-ins. Audio is normalised to −14 LUFS. |
| 8. Captions | ASS subtitles burned in by libass: 1–3 words at a time, large uppercase text with a thick outline. The word being spoken turns yellow and pops; important words are green. Captions sit below the facecam so they don't cover the face. Claude fixes obvious recognition errors word by word, so timing isn't affected. |
| 9. Export and check | H.264 High / AAC 48 kHz, 30 fps, CRF 20, `+faststart`. Each file is fully decoded, its streams, resolution and duration are checked, and caption timing and visibility are tested on a frame. A clip that fails is reported and the batch continues. |

## Output

```
output/shorts/
├── 01_Kai_Cops_Chase_Chaos.mp4
├── 01_Kai_Cops_Chase_Chaos.txt     # title, description, hashtags, source VOD link with timestamp
├── 02_GTA6_Crazy_NPC_Moment.mp4
├── …
├── clips_manifest.csv              # rank, file, title, score, category, duration, VOD link, times, layout, …
├── clips_manifest.json
├── sources.txt                     # file → source VOD URL (?t=1h23m45s)
└── youtube_metadata.txt            # all titles/descriptions/hashtags in one place
```

Existing finished clips are never overwritten silently. The app asks first, or
skips them when it isn't running in an interactive terminal. Pass `--overwrite`
or `--no-overwrite` to decide in advance. Temporary files in `output/_tmp/` are
deleted once all clips succeed (`--keep-temp` keeps them).

---

## Installation

1. **Python 3.10+**
2. **FFmpeg** (with libass, which standard builds include) on your `PATH`:
   - Windows: `winget install Gyan.FFmpeg`
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
3. Python packages:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. **AI ranking (recommended):** set an Anthropic API key (or run `ant auth login`):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...        # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
   ```
   Without a key the app still works, using heuristic ranking and titles built
   from the transcript.
5. A caption font: *Arial Black* is the default (pre-installed on Windows and macOS).
   Any font works with `--font "Montserrat Black"`, for example.

The first run downloads the Whisper model (~500 MB for `small.en`). An NVIDIA
GPU is used automatically if one is available.

## Usage

```bash
# Default: Kai Cenat archive, GTA 6 VODs, 12 Shorts
python -m shorts_maker

# Specific VODs
python -m shorts_maker --vod https://www.twitch.tv/videos/1234567890 --vod https://www.twitch.tv/videos/1234567891

# Your own local recordings (no download)
python -m shorts_maker --input stream1.mp4 --input stream2.mkv

# Rank only (see what it would cut), then render
python -m shorts_maker --dry-run
```

Useful options (`python -m shorts_maker --help` lists them all):

| Option | Meaning |
|---|---|
| `--clips 12` / `--min-clips 10` | how many Shorts to make / warn below this |
| `--max-vods 3` | how many matching VODs to analyse |
| `--title-keyword "gta"` | title filter (repeatable); `--title-keyword ""` accepts any VOD |
| `--whisper-model medium.en` | more accurate captions (slower); `base.en` is faster |
| `--device cuda` | force the GPU |
| `--no-llm` | heuristic ranking only |
| `--no-teaser` / `--no-zoom` / `--keep-pauses` | turn off individual editing effects |
| `--sfx pop.wav` | quiet sound effect on zoom-ins (bring your own licensed file) |
| `--censor fuck --censor shit` | mask words in captions (the audio is unchanged) |
| `--cookies-from-browser chrome` | use your Twitch login for VODs your account may watch |
| `--overwrite` / `--no-overwrite` | what to do with existing clips |
| `-v` | debug logging, including the FFmpeg graph |

### Time and cost (rough)

For 3 VODs of 6–8 hours each on a typical laptop CPU: audio download takes
about 5–10 minutes, loudness analysis about 1 minute per VOD, transcribing
around 36 windows with `small.en` about 10–20 minutes (much faster on a GPU),
and rendering about 1 minute per clip. Claude is called once for ranking,
plus one small call per clip to fix captions.

## Tests

`tests/e2e_synthetic.py` builds an artificial 8-minute "stream" with a
facecam and loud reactions, replaces Whisper with a fake transcriber, runs the
whole pipeline offline and checks the exported Shorts:

```bash
python tests/e2e_synthetic.py path/to/any_face_photo.png
```

## Project layout

```
shorts_maker/
  cli.py             command line → Config
  config.py          all settings and defaults
  pipeline.py        orchestration, progress, error handling, overwrite checks
  sources.py         yt-dlp listing, audio-only download, range download, audio alignment
  audio_analysis.py  streaming loudness/excitement profile and peak picking
  transcribe.py      faster-whisper word timestamps
  highlights.py      candidates, boundaries (setup → payoff), heuristic score, de-duplication
  llm.py             Claude ranking, metadata and caption correction (structured output)
  layout.py          facecam detection and 9:16 layouts
  timeline.py        teaser, pause removal, punch-in zooms
  subtitles.py       animated word-by-word ASS captions
  editor.py          single-pass FFmpeg render
  export.py          verification, manifest, metadata files
```
