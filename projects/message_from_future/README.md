# I Received a Message From My Future Self

This is a 48-second vertical horror short (1080×1920, 30 fps, H.264/AAC), rendered entirely
offline by the `phone-horror-short` skill (`.claude/skills/phone-horror-short/`).

```bash
pip install numpy scipy opencv-python-headless pillow   # + FFmpeg on PATH
./render.sh                # full render → build/
./render.sh --preview      # fast 10 fps draft
python3 ../../.claude/skills/phone-horror-short/scripts/render_story.py story.json --out build --frame 29.5   # one still
```

## Output (`build/`, not committed to git)

| File | What it is |
|---|---|
| `message_from_future.mp4` | final video |
| `scenes/scene_01…05_*.mp4` | the five screenplay scenes as separate clips |
| `audio/full_mix.wav`, `audio/music_drone.wav`, `audio/sfx_*.wav` | the soundtrack, the music bed and every sound effect, all synthesized (no copyrighted audio) |
| `character_reference.png` | the character and room still used by every shot |
| `stills/contact_sheet.png` | one frame per shot |

## How it is made

- **`story.json`** is the whole screenplay as data: messages with exact timings, shots,
  camera moves, lamp switches, sound cues and the tension curve.
- **Visuals** are procedural 2.5D plates. They show one consistent dark bedroom with a hooded
  character from behind, a desk lamp, a mirror, a red LED clock at 23:50, and a book with a key.
  On top of the plates go camera push-ins, handheld motion, vibration shake, a flickering lamp,
  the whip-pan turn, and a mirror reflection that shows the back of the head and lags behind
  the character (with subtle warp and chromatic aberration). Grading uses blue shadows and warm
  highlights, plus a vignette and film grain.
- **Phone messages** are drawn as a realistic dark-mode messaging app: lock-screen banner,
  typing indicator, live typing with keyboard, and "Delivered". All text is sharp and readable.
- **Loop:** the video ends with the character typing the first message, a cut to black and a
  notification. The first frame then answers it.

## Making it photorealistic

No AI video or image generation service was available when this was made, so the room
and character are stylized silhouettes rather than real people. To upgrade:

1. Generate the character reference and the shots with the prompts in `ai_prompts.md`
   (Runway, Kling, Luma, Veo, Sora…). Keep phone screens blank.
2. Save the clips in `shots/` and add `"plate": "shots/01_room.mp4"` to the matching
   shots in `story.json`.
3. Run `./render.sh` again. Messages, grading, grain and sound are applied on top.

Keep any API keys in environment variables, never in these files.
