# Prompts for photoreal plates (optional)

Use these prompts with any image or video generator the user has access to
(Runway, Kling, Luma, Veo, Sora, Midjourney and so on). Generate the
**character reference image first**, then use it as the image or character
reference in every shot so the face, clothes, room and light stay the same.

Rules that make the plates work with the engine:
- 9:16 vertical, at least 1080x1920, 5–10 s per clip, slow or no camera motion.
  The engine adds its own push-in and handheld movement.
- **The phone screen must be blank or turned away.** The engine draws the messages.
- No text, logos or watermarks. Dark, low-key lighting, because the grade darkens further.
- Save the files as `shots/<NN>_<type>.mp4` and set `"plate"` on the matching shot.

## Character reference (image)

> Photorealistic cinematic still, vertical 9:16. A tired young adult in a
> plain dark charcoal hoodie sits at a small wooden desk in a dark bedroom at
> night, holding a smartphone with a blank glowing screen. One warm desk lamp
> on the left is the only key light. Dark blue-gray walls, a tall dark-framed
> mirror on the wall, a red LED clock reading 23:50, a closed dark red book on
> the desk. Shallow depth of field, 35mm lens, subtle film grain, muted blue
> shadows, warm highlights, realistic skin, anxious expression. No text, no logos.

## Shot prompts (adapt per story)

| shot | prompt |
|---|---|
| room wide | Same person and bedroom as the reference, seen from behind over the shoulder, hood up, looking down at a phone. Lamp on, slow push-in, still and quiet. |
| phone in hand | Close-up of the same hands holding the phone, **screen blank and evenly lit**, room softly out of focus behind, slight handheld movement. |
| clock | Macro shot of a red LED alarm clock showing 23:50 on the dark wooden desk, glossy reflection, lamp bokeh behind. |
| book and key | Top-down close-up: a hand slowly lifts a dark red book from the desk, revealing a small brass key underneath. |
| lamp off | The same over-the-shoulder shot. The hand switches the desk lamp off and the room falls into darkness, lit only by the phone glow. |
| lamp on, empty room | Wide shot. The lamp flickers back on and the bedroom is empty and still. |
| mirror | Slow dolly towards the tall mirror. The person stands facing the mirror, but the reflection shows the back of their head. Subtle, uncanny, no monster. |
| turn | The person spins around fast to face the camera. Behind them is only the empty dark room and a door left ajar. |
| typing | Close-up over the shoulder of thumbs typing on the phone, screen blank, room dark. |
