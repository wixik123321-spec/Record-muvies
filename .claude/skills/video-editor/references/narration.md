# Narration: the user's own voice or an AI voice

Learned on the Ayutthaya clip (17 Thai lines, 2.5D photo animation). v1.1 used the user's phone recording, which they found poor even after cleanup; v2 used an AI voice and the user called it "ดูดีมาก" and asked to publish it.

## Which voice
| Source | When | Cost |
|---|---|---|
| User's own recording | They want their voice, or have a good mic | free; needs the cleanup chain below |
| AI voice through Creative Claw (ElevenLabs v4) | Best quality; used for Ayutthaya v2 | credits (17 lines: 35 credits) |
| edge-tts (`edge_tts`, Microsoft) | Free fallback, no account | free; flatter delivery |

- Thai AI voices that fit calm storytelling (ElevenLabs v4, found with Creative Claw `search_voices` language Thai): **Ohm** `tKtPl8obOBs5uPMei6yN` (male, relaxed narrator, chosen by the user), Songkran `xYmBpJREC3WfqEFpbPvO`, Patinya `weRAVUYgqjjfUEEu5BsB`, Mali `7XW5JhaNn90bnFojQ5DA` (female). A script that says "ครับ" needs a male voice.
- edge-tts Thai voices: `th-TH-NiwatNeural` (male), `th-TH-PremwadeeNeural` (female).
- Creative Claw needs sign-in first (`/mcp` in Claude Code, or the plugin's Connectors tab). If its tools are missing, stop and say so; do not switch to another service without asking.

## Workflow (AI voice)
1. Write the script as one line per sentence group in `script_lines.json` (subtitle text) and keep the visual notes in `script.md`.
2. Make a **spoken** copy of each line for the voice only. Write years and numbers as Thai words so they are read right: `พ.ศ. 1893` -> `พอศอ หนึ่งพันแปดร้อยเก้าสิบสาม`, `417 ปี` -> `สี่ร้อยสิบเจ็ดปี`. Subtitles keep the digits.
3. Check the balance and the estimate (`get_credits_balance`, `estimate_generation`) and tell the user the cost before any paid generation.
4. Generate **one file per line** (`eleven/line01.mp3` ...), not one long take: each line can be redone alone and the layout below needs line boundaries. Pass `extras.language_code: "th"` and keep `timestamps` on (word timings come back with each job; keep the job IDs, `check_job` returns them again).
5. Audition the first 3 lines joined with the planned pauses and get the user's approval before the rest.
6. v4 delivery tags that worked: `...` for a held pause inside a line, `[curious]` before a question, `[laughs]` before a joke ("ลองไปยืน [laughs] เอ๊ย ลองไปนั่ง"). Do not copy tags to other models (v2 reads them aloud).
7. Lay the lines out with `scripts/retime.py lay` (below): lead-in 1.4 s, 0.8 s between lines, 1.2 s where the story changes section, 2.6 s tail.

## Processing
- AI voice is clean: **no** noise reduction, gate, EQ or de-esser. Only loudness: `loudnorm=I=-18:TP=-2:LRA=7`.
- User recording (phone, no mic), the chain that the user approved: `highpass=f=90,lowpass=f=11000,afftdn=nf=-25:nr=18,agate=threshold=0.015:ratio=3:attack=5:release=180,equalizer=f=250:t=q:w=1.2:g=-3,equalizer=f=3200:t=q:w=1.0:g=3,deesser=i=0.4,acompressor=threshold=-22dB:ratio=3:attack=8:release=120:makeup=4,loudnorm=I=-18:TP=-2:LRA=7`.
- The music-bed rule still applies (`music-rules.md`): soft music under the whole narration, ~11 dB under the voice. With AI lines the gaps are short (0.8-1.2 s), so the bed only rises ~1 dB in pauses; that was fine.

## Swapping the voice of a finished edit
Tune visuals, effects and music to the first voice, then keep every cue on that **old** timeline and map it:
```bash
python -I scripts/retime.py lay line_timing_user.json eleven v2 --section-after 2,6,10,14 --old-dur 124.5
```
This writes `v2_timing.json` (new line times, same format), `v2_map.json` (anchors at every line start and end) and `v2_voice.wav`. In the compositor render frame `i` as `shot(to_old(i / FPS))`; place effect cues at `to_new(t_old)`; map music section bounds with `to_new`. Rebuild subtitles from the new line times. On Ayutthaya, lines stretched 0.8-1.45x, the clip grew from 124.5 s to 136.9 s, and every title, effect and music change still landed on its words with no hand tuning. Preview a 20 s stretch first (old 42-62 s became new 51.4-71.8 s).

## Timing a recorded narration (Thai included)
1. Upload the recording to Creative Claw (`get_upload_url`, PUT the file, `confirm_upload`) and run `transcribe` with `language_code: "th"`. About 2 credits for 2 minutes (Scribe, 44 credits/hour); tell the user first. The uploaded file gets a public CDN link in their Creative Claw workspace; say so when the recording is private.
2. Download the `diarization_url` JSON (per-character times for Thai) and run
   `python -I scripts/align_script.py scribe_diar.json script_lines.json narr` -> `narr_timing.json` + `narr.srt`.
3. Read the transcript text against the script: it shows what was really said. On Ayutthaya it caught a false start ("เมืองถูกล้อมไปด้วย..."), a stutter (สถา-สถาปนา) and a misread number (417 read as "สี่ร้อยสี่สิบเจ็ด"), which matter for a re-record or a subtitle fix.

Result on the 130 s Ayutthaya recording: 17/17 lines, starts within 0.08 s of the hand-tuned times (median 0.03 s), subtitles with no QA warnings (the old character-share split had 3). Whisper small had found 11 of 17 lines.

