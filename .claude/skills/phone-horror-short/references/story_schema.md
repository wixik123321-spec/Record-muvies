# story.json format

Times are in seconds from the start of the video. A complete example is
`projects/message_from_future/story.json` in the repository. It's the 48 s
"I Received a Message From My Future Self" short.

```jsonc
{
  "title": "…",
  "output_name": "my_short",          // final file is build/my_short.mp4
  "duration": 48.0,
  "fps": 30,
  "exposure": 1.25,                   // overall brightness before grading (1.0–1.6)
  "lamp_initial": 1.0,                // 1 = desk lamp on at the start
  "character_reference_time": 4.6,    // frame saved as character_reference.png

  "scenes": [ {"name": "1 The First Message", "start": 0, "end": 5}, … ],  // exported as separate clips

  "phone": {
    "contact": "Unknown",             // name in the chat header / notification
    "clock": "23:50",                 // status-bar and lock-screen time
    "lock_until": 5.0,                // before this, the phone shows the lock screen + banner of the first incoming message
    "messages": [
      {"t": 0.4, "from": "them", "text": "…", "typing": 0},     // typing = seconds of "…" indicator before it appears
      {"t": 6.4, "from": "me",   "text": "…", "typing": 1.2},   // typing = seconds spent typing it in the input field (ends at t, then it sends)
      {"t": 46.0, "from": "me", "text": "…", "typing": 4.2, "status": "Delivered"}
    ]
  },

  "shots": [ … ],                     // see below; each shot runs from its start to the next one
  "events": [ … ],                    // lamp switches, sound effects, shakes
  "audio": {
    "tension": [[0, 0.15], [29.4, 1.0], [34.4, 0.2]],   // 0..1 curve for the drone (filter opens, dissonance grows)
    "silence": [[34.6, 36.2]],                          // windows where music drops out
    "heartbeat": [27.0, 33.0]                           // optional accelerating heartbeat
  }
}
```

Sounds that are added automatically: a vibration for every incoming message, a
key tap for every typed character, and a send whoosh for every outgoing message.

## Shots

Common fields: `start`, `end`, `type`, `zoom: [from, to]` (1.0 = the full
plate width), `center: [[x, y], [x, y]]` (plate coordinates 0–1, where the
camera looks), `hand` (handheld amount, 0–2), `fade_in` and `fade_out` (seconds),
and `plate` (optional path to a clip or image that replaces the procedural
background).

| type | what it shows | extra fields |
|---|---|---|
| `room` | Over-the-shoulder wide shot: the character from behind at the desk, with the lamp, mirror, clock and book. It follows the lamp state. | |
| `phone` | Close-up of the phone in hand over the blurred room. Shows the lock screen or the chat at that moment. | `tilt: [deg, deg]`, `offset_y` (px; negative moves the phone up to show the keyboard and input field), `screen_brightness` (0.8) |
| `clock` | Macro shot of the LED clock (23:50) with a glossy reflection. The colon blinks. | |
| `book` | Desk close-up. The book lifts away and reveals the key. | `lift: [k0, k1]`, the fraction of the shot during which the book lifts |
| `mirror` | Towards the mirror. The real character is in the foreground and the reflection shows the back of their head. The reflection lags, then drifts and tilts. | `ca: [from, to]` (chromatic aberration), `warp` (true) |
| `turn` | Whip pan from the desk to the room behind, with motion blur. | `whip: [k0, k1]` |
| `behind` | The room behind the character: a dark door ajar and the bed edge. Empty. | |
| `black` | Black frame. | |

Plate coordinates: the character's head is around x 0.36, y 0.50. The mirror
spans x 0.50–0.88 and y 0.10–0.47. The lamp is at x 0.16, and the clock at x 0.70–0.88, y 0.6.

## Events

```jsonc
{"t": 19.6, "type": "lamp", "state": "off"}            // also plays the switch click; "on" flickers on
{"t": 29.4, "type": "sfx", "name": "impact", "gain": 1.0}
{"t": 29.4, "type": "shake", "amount": 0.6}            // camera shake
{"t": 0.35, "type": "vibrate"}                          // extra buzz (incoming messages buzz automatically)
{"t": 10.6, "type": "ticks", "end": 12.6, "gain": 0.7} // clock ticking each second
```

Sound effect names: `vibration`, `notification`, `send`, `tick`, `switch`,
`breathing`, `rustle`, `whisper`, `impact`.

## Pacing checklist

- The first message is readable by about 1.5 s.
- Every incoming message stays on screen for at least 0.8 s + 0.3 s per word.
- Cut to a room, clock or object shot for every physical action in the script.
- The scare gets an `impact` and a `shake`, then a near-silence window.
- Loop: the last thing typed is the first message, followed by black and a notification.
