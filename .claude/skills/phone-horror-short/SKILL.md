---
name: phone-horror-short
description: Produce a finished vertical (9:16, 1080x1920, 30 fps) cinematic horror/thriller short told through phone text messages, such as creepy "message from an unknown number" or "text from my future self" stories, with a realistic messaging UI, dark bedroom scenes, camera moves, colour grading, film grain, original synthesized sound design and a seamless loop ending. Use this skill whenever the user wants to make a YouTube Short, TikTok or Reel from a screenplay or story idea in which a character receives or types messages, any scary or suspense short built around a phone screen, or a "text story" video. Use it even when they say "AI video", "generate the video" or "make the short" without naming a tool, and when no video-generation API is available, because this skill renders a real MP4 offline.
---

# Phone horror short

This skill turns a screenplay into an actual rendered MP4. It doesn't produce a shot list for someone else to film. The bundled engine `scripts/render_story.py` reads a `story.json` and renders the video offline with Python, OpenCV, Pillow, numpy and FFmpeg. Nothing is downloaded and no API key is needed.

What the engine draws:
- **Phone.** A dark-mode messaging app: a lock-screen notification banner, incoming and outgoing bubbles that pop in, the "…" typing indicator, text typed into the input field with the keyboard up and keys lighting, and a "Delivered" label. Message times are taken from the story, so on-screen text is always readable and spelled correctly. Video models usually garble on-screen text.
- **Room.** Procedural 2.5D plates of one consistent bedroom at night: a hooded character seen from behind, a warm desk lamp, a mirror, an LED clock at 23:50, a book with a key under it, cold light through the blinds, and the room behind the character with a door ajar. Every shot uses the same layout, so the character and room never change between shots.
- **Camera and look.** Push-ins, pans, handheld micro-movement, shake on vibration, a lamp that flickers on, a whip-pan turn, and a wrong mirror reflection that lags behind the real character, with a subtle warp and chromatic aberration. Grading has blue shadows and warm lamp highlights, plus a vignette and animated film grain.
- **Sound.** Everything is synthesized, so there is no copyright risk: a drone that follows a tension curve, room tone, phone vibration, a notification chime, key taps, a send whoosh, clock ticks, a light-switch click, breathing, a heartbeat, a reversed distorted whisper and a sub impact. Silences duck the drone, and the mix is normalised to −14 LUFS.

Be upfront about the look. The procedural plates are stylised: a silhouette in a moody, painted-looking room, not photorealistic people. If the user wants photoreal shots, the engine accepts external plates. See "Photoreal shots" below.

## Workflow

1. **Read the screenplay and plan the beats.** List every on-screen message (who sends it and the exact text) and every physical beat (vibration, a light switching, a look at an object, a turn). Keep the user's wording for the messages exactly.
2. **Write `story.json`** in a project folder. Start from `references/story_schema.md`, which has the full format, every shot type, and an annotated example. The guidelines below are why these videos work, so follow them:
   - **Hook in the first 2 seconds.** The first message should be readable on screen by about 1.5 s, for example as a lock-screen banner (`lock_until`).
   - **Leave time to read.** Keep each incoming message on screen for at least 0.8 s plus 0.3 s per word before cutting away. Typing speed should be 6–14 characters per second, and slower for a hesitant character.
   - **Cut away from the phone on every physical beat** (clock, object, lamp, mirror, turning around), then come back. Long phone stretches are fine for typing, but a room shot every 4–6 s keeps it cinematic.
   - **Darkness is a tool.** A lamp-off event leaves only the phone glow, and the lamp flickers back on.
   - **Shape the tension curve.** It should rise towards the scare, drop to near silence right before a reveal, and have a hit (`impact` plus `shake`) on the scare itself.
   - **Make the loop seamless.** End on the line the video opens with, cut to black, then a notification sound. The first frame then reads as the reply.
3. **Preview stills before the full render.** It takes about 15 s per frame:
   `python scripts/render_story.py story.json --out build --frame 12.5`
   Look at frames at the hook, at each message, and at the scare (open the PNG). Check that text is readable, nothing is cut off, and it isn't too dark. Tweak `zoom`, `center`, `offset_y`, `screen_brightness` and `exposure`.
4. **Render.** Rendering runs at about 2–3 frames/s on a 4-core CPU, so a 48 s short takes 5–10 minutes. Run it in the background:
   `python scripts/render_story.py story.json --out build`
   You can use `--preview` (10 fps, fast encode) for a rough timing check.
5. **Verify** with ffprobe: 1080x1920, H.264/AAC, the expected duration. Then look at `build/stills/contact_sheet.png`, which has one frame per shot, and listen for clipping (the mix is soft-limited).
6. **Deliver** `build/<name>.mp4`, the per-scene clips in `build/scenes/`, all sounds in `build/audio/`, `build/character_reference.png`, the `story.json`, and a short README with the one-line command to re-render.

## Photoreal shots (when a video/image generation service is available)

If the user has a generation service (e.g. a Runway, Kling, Luma, Veo or Sora key in an environment variable, or clips they made themselves), use it only for the visuals and keep everything else in this engine:

- Write one prompt per shot from the story, plus one character reference prompt, using `references/ai_prompts.md`. Ask for a **blank phone screen**, because the engine adds the text.
- Generate clips with the user's tool, using the reference image for consistency. Save them next to the story and set `"plate": "shots/03_clock.mp4"` on the matching shots. The engine still applies the camera move, grading, grain and sound.
- Never put API keys in files. Read them from environment variables.

If no service is available, say so plainly, render the procedural version, and also deliver `ai_prompts.md` so the user can upgrade shots later.

## Files

- `scripts/render_story.py`: the CLI. Takes a story and renders the video, scenes, audio, stills and reference image.
- `scripts/phone_ui.py`: the messaging UI, a pure function of time.
- `scripts/plates.py`: procedural room plates. Edit these to add a new location type.
- `scripts/sound.py`: the sound effect synthesizers and the WAV writer.
- `references/story_schema.md`: the story format and shot types. Read it before writing a story.
- `references/ai_prompts.md`: prompt templates for generating photoreal plates.

Requirements: Python 3.10+, `numpy`, `scipy`, `opencv-python-headless`, `Pillow`, and FFmpeg on PATH. Inter font if installed, otherwise DejaVu Sans.
