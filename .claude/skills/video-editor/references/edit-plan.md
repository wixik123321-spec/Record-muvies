# Edit plan: one JSON file per footage edit

`scripts/edit_plan.py plan.json` renders a whole edit (vlog, Short, interview cut, highlight reel, product clip) from one
file, so an edit is reproducible, easy to change, and needs no new code per genre. 2.5D photo animations keep their own
Pillow compositor (render it with `scripts/render_frames.py`) and can then be used as a clip in a plan.

Always: `--preview A B` first (half size, only A..B s), show it, then the full render. The script runs `qa_check.py`
on the result and writes `<out>.timeline.json`, `<out>.sheet.jpg` and `<out>.qa.json`; read the sheet before sending.

## Format
Paths are relative to the plan file. Times in seconds.

```json
{
 "output": {"path": "out.mp4", "size": [1080, 1920], "fps": 30, "target": "shorts", "fit": "blur", "crf": 19},
 "clips": [
  {"src": "a.mp4", "in": 2, "out": 12, "fit": "crop", "speed": 1.0, "volume_db": 0, "speech": true,
   "titles": [{"text": "เกียวโตยามค่ำ", "start": 0.3, "end": 3.0, "pos": "top", "size": 110}]},
  {"src": "b.mp4", "in": 5, "out": 13, "transition": {"type": "fade", "dur": 0.5}}
 ],
 "titles": [{"text": "line one\nline two", "start": 20, "end": 22.5, "pos": "center", "fade": 0.3, "color": [250, 240, 220]}],
 "audio": [
  {"src": "music.mp3", "role": "music", "start": 0, "end": 60, "in": 0, "loop": true, "fade_in": 1.5, "fade_out": 2.5},
  {"src": "vo/line01.mp3", "role": "voice", "start": 0.4},
  {"src": "whoosh.wav", "role": "sfx", "start": 9.4, "in": 0, "out": 1.2, "volume_db": -12}
 ],
 "music_mix": {"gap_db": -8, "under_db": -30},
 "subtitles": {"src": "subs.srt", "style": "FontName=Leelawadee UI,FontSize=16,...", "duck_from": true}
}
```

| Field | Meaning |
|---|---|
| `output.target` | loudness target: `youtube`/`shorts` -14 LUFS, `doc` -18.5, `master` -23 (or set `lufs`) |
| `output.fit` / `clip.fit` | `crop` (fill), `pad` (letterbox), `blur` (whole frame over a blurred fill; 16:9 footage in 9:16) |
| `clip.in/out` | source seconds; `speed` changes picture and sound (atempo keeps pitch) |
| `clip.crop` | `[x, y, w, h]` in source pixels, applied before `fit` (zoom on a screen area, follow a person; `screen_focus.py` and `reframe.py` write it) |
| `clip.filter` | extra ffmpeg filters before scaling, e.g. `eq=gamma=1.4:saturation=1.1` for a dark shot |
| `clip.transition` | on the incoming clip: any ffmpeg xfade name (`fade`, `dissolve`, `slideleft`, `wipeup`, `circleopen`...); omitted = hard cut |
| `clip.titles` | times relative to the clip; top-level `titles` use timeline time |
| title fields | `text` (`
` new line, `**word**` accent), `start`, `end`, `pos` top/center/bottom, `size` (ASS size = line height; Leelawadee glyphs look ~0.75 of it), `margin`, `anim` pop/punch/slide (`from` left/right)/rise/zoom/words (`word_step`), `underline`, `accent` (RGB hex), `fade`; with `items: [...]` it is a topic card (`dim`, `stagger`, `item_size`, `x`, `y`). Sizes shrink automatically so no line runs off the frame |
| `headline` | top-level `{"text", "tag", "start", "end", "size", "margin", "accent"}`: the topic stays on screen (pop entrance, accent underline, small grey tag line under it); default top band, size 4% of the height |
| `clip.broll` | list of `{"src", "start", "end", "in", "focus": [x, y], "region": [x, y, w, h], "pip": true}` in clip time: stock picture or footage full frame, the speaker in a circle bubble (`pip_pos` top-right by default, `pip_size` 0.36, `pip_face_y`). Stills get a slow push-in. `focus` keeps the subject in the 9:16 window; `region` cuts burned-in text and logos off the source first. Match each insert to the words it illustrates (`find` the phrase in the word timings) |
| `fit: "stack"` + `clip.stack` | split screen: two `[x, y, w, h]` crops of one source, top and bottom with a thin divider (`reframe.py --stack` writes them for two-shots). Captions move to the upper panel's lower part |
| `clip.behind` | `[{"text", "start", "end", "color": [r, g, b], "repeat": 3, "y": 0.30, "size"}]` in clip time: a huge Impact word (fit to 96% of the width, extra copies faint above and below) drawn **behind the person**: rembg `u2net_human_seg` masks each frame of that window and lays the person back on top. Use on 1-3 key words per clip, on close-ups; keep it clear of the headline band |
| card clip | `{"card": {"text", "bg", "size", "anim", "word_step", "accent"}, "in": 0, "out": seconds}`: text-only screen (quote, chapter, ending), words appear one by one; silent, no captions; a headline ends where the first card starts; QA does not count it as "black" |
| `clip.captions` | `false` = `word_captions.py` skips this clip (an intro shot under a topic card) |
| `clip.speech` | `false` for ambience-only clips (their sound is not treated as speech); `talk: [[a, b], ...]` marks speech inside a clip |
| `subtitles.src` | `.srt` (styled with `style`, QA-checked) or `.ass` (burned with its own style, e.g. `word_captions.py`) |
| `audio.role` | `voice` (ducks music), `music` (looped, loudness-matched to speech, ducked), `sfx` (placed as is) |
| `music_mix` | `gap_db` music level in gaps vs speech; `under_db` while speech plays. Vlog/stream: -8 / -30 (music off under talk). Narrated documentary: -8 / -11 (soft bed under the voice). See `music-rules.md` |

Speech times for ducking come from, in order: subtitle cues, voice tracks, clip `talk` spans; if none are given they are
detected from the clip and voice sound (100 ms energy, gaps under 0.5 s bridged). Music lowers 0.5 s before speech and
recovers 1.5 s after.

## Rendering rules it enforces (learned the hard way)
- Titles are an ASS track drawn by libass. ffmpeg `drawtext` and Pillow without raqm (`PIL.features.check("raqm")` is
  False on this machine) drop a Thai tone mark that sits on an upper vowel: ที่นี่ became ทีนี, นั่ง became นัง.
- Video is H.264 yuv420p **limited range** (`scale=out_range=tv`). Frames from JPEG/PNG are full range; encoded as is
  they come out `yuvj420p/pc`, which some players and uploads show washed out.
- Loudness is two-pass (measure, then linear gain); single-pass loudnorm landed 1.6 dB under target on a 21 s Short.
- A title that ends after the timeline is reported as a WARNING.

## Speed (24-core machine)
Footage plan, 21 s vertical Short with 3 clips, 2 transitions, 2 titles, music, sfx: 14 s including QA.
