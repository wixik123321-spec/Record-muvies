# Genre recipes (tested 2026-11-20 on Wikimedia Commons CC clips)

User scores, round 1: product ad **7/10** ("shot choice OK, but the titles are flat and boring"), screen tutorial
**9.5/10** ("basic, nothing missing"), interview Short **9/10** ("cut very well, zooms follow the person"; wanted an
eye-catching topic list at the start instead of plain text). Round 2 (animated titles, topic card): pending.

## Titles must move (user rule, 2026-11-21)
Plain static text scored lowest. Every title gets an entrance (`"anim"` in edit plans: `pop`, `punch`, `slide`,
`rise`, `words`, `zoom`), key words in the accent colour (`**word**`), and an `underline` that draws itself for the
main titles; start each title on a beat or a cut. Clips that open on a topic should open with a **topic card**:
a heading plus 2-4 numbered items that slide in one by one over a dimmed frame (a title with `"items"`), 3-4 s, on an
intro shot whose captions are off (`"captions": false`). Still text only, never a box around the text.

Each recipe ends in an edit plan rendered by `scripts/edit_plan.py` and checked by `scripts/qa_check.py`. Test files and
plans were local (not published).

## Product / ad (15-60 s)
Source: 10 min one-take unboxing, tripod, no sound track at all (Steam Deck, CC BY 3.0). Result: 27 s, 16:9.
1. `find_shots.py src.mp4 shots --window 4` -> labelled sheet of the sharpest, steadiest moments (long one-take shots are
   split into 4 s moments). Read the sheet and pick a story: arrival -> box -> open -> hero object -> power on -> payoff.
2. Find the payoff by picture, not order: the game library was the most colourful frame (`signalstats` SATAVG peak at
   8:10), at the very end of a slow dark setup section.
3. `music_beats.py music.mp3` -> BPM and bar grid. Cut every clip to whole bars (Carefree 96 BPM: 2.5 s = one bar),
   start the music at its first beat (`"in": 0.615`) so timeline 0 is a beat, hard cuts, one short fade into the payoff.
4. Titles: one short line per story step, top, on the bar; the last clip carries the call to action.
5. Dark shots: per-clip `"filter": "eq=gamma=1.4..1.6:saturation=1.1"`; gamma lifts shadows grey, so keep them short.
6. Speed: a slow action (power-on) at 2x keeps a 2.5 s bar.
No sound in the source: music is the only track (`music_mix` 0/0), loudness -14 LUFS.

## Screen-recording tutorial
Source: 2 min silent screencast, 1366x768, tiny text (Wikipedia interlanguage links, CC BY-SA 4.0). Result: 75 s.
1. `screen_focus.py rec.mp4 focus --ignore <taskbar clock box>` finds where the screen changes and when nothing happens:
   - action boxes become 16:9 crops (at least 40% of the screen width, so text stays legible but context remains)
   - pointer-only movement counts as idle (`--pointer-px 250`); idle is fast-forwarded and never takes more than 2 s
     of screen time (`--idle-max`); short zooms (< 4 s) merge into a neighbour; 0.5-1 s idle slivers between actions
     stay at real time (they flickered)
2. Step titles go on the timeline (not per clip), 3.5 s each, bottom, because a step can start inside a 2 s fast-forward.
3. Soft music bed (`gap_db`/`under_db` -10), 0.25 s fades between crops.
QA reports "static picture" holds while the viewer reads a dialog: expected in tutorials, check they are not stalls.
If the recording is already edited (zooms, highlights, as "How to make links" was) do not re-zoom it.

## Interview / podcast -> vertical Short (30-60 s)
Source: 10 min edited 3-camera interview (Royal Society, CC BY 3.0). Result: 39 s 9:16.
1. Transcript with word times: `transcribe_whisper.py src out --lang en` (free, medium model, real time on CPU);
   Thai needs Creative Claw `transcribe` instead.
2. Read the segments and pick one thread: a hook question or a striking line first, then 3-4 answer pieces that build;
   snap each piece to word edges (-0.08 s / +0.12 s) so no word is clipped.
3. `reframe.py plan.json --sheet check.jpg` splits clips at camera cuts (histogram jump > 0.15; a cut measured 0.275 vs
   0.006 baseline) and crops each to the person (moving skin-coloured pixels). If no 9:16 window holds 65% of the subject
   (two-shot, group) the clip keeps the whole frame over a blurred fill. Center crops showed an empty table and studio
   lights; this fixed it without any model download.
4. `word_captions.py words.json plan.json caps.ass` -> 1-3 word captions, the spoken word in yellow, never across a cut;
   `"subtitles": {"src": "caps.ass"}` burns them with their own style. Hook title at the top for the first 3 s.
5. Music bed under speech at about -20 dB (`under_db`), -14 in gaps; target -14 LUFS.
6. Podcast-Short polish from the reference study (`references/podcast-shorts.md`): a persistent `headline` after the
   topic card, `reframe.py --punch 1.3 --every 3 --words words.json`, and `word_captions.py --style stack`.
7. Key moments: `pick_moments.py words.json plan.json --apply-behind --out moments.json` picks 1 behind-word per ~15 s
   (rare, stressed nouns on unzoomed close-ups) and lists one B-roll search phrase per sentence; review both, they are
   suggestions (it matched the hand-picked "DANGEROUS"; B-roll phrases like "flash floods", "heavier rainfall" were usable,
   "alert" or "humans live" were not).
8. B-roll: `find_broll.py search moments.json plan.json cands.json --context <topic>` lists free-licence Commons
   footage per phrase (no download); show the list with sizes, then `find_broll.py fetch cands.json plan.json --pick 1b 2a
   --dir broll` downloads only the approved files, appends credits and places each insert on its phrase.

## Pitfalls found while building these (fixed in the scripts)
- `xfade` after a `concat` failed ("Error reinitializing filters"): the inputs had different timebases. Every clip and
  join now ends with `settb=1/fps`. Retrying the same command did not help; isolating the filter did.
- Titles had no outline: unreadable on white web pages. ASS style now has a thick dark outline and soft shadow (user rule:
  text only, never a box).
- Wikimedia's file server answered 429 to every download with an anonymous User-Agent; with a contact URL in it
  (`name/version (https://repo-url)`, with the user's OK) all four files came at once. Never put an email in it.
- OpenCV here fails to import (built against numpy 1.x, numpy is 2.4): do not rely on cv2 without asking to fix it.
