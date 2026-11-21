# How podcast Shorts are cut (study of 9 reference clips, 2026-11-21)

Source: 9 vertical TikTok clips the user chose as good examples (576x1024, 25-136 s): five Thai podcast Shorts, three
editors' "before / after" breakdowns, one English kinetic-typography edit. Local folder, not redistributed.
Measured: scene cuts (`scdet`), loudness, frames every 2 s and every 0.25 s.

## The grammar they share
1. **Hook first, topic always visible.** Either a big styled hook title for the first 2-4 s ("รักษาคนที่บ้าน
   ยากที่สุดจริงไหม?") or a **persistent headline** that stays the whole clip (top third, 2 lines, bold, one accent
   underline, small episode tag under it: "ค่าใช้จ่ายแฝงของการผ่อน 0%"). Nobody opens on a plain subtitle.
2. **Something changes every 2-4 s.** Median shot 2.2 s (two-camera talk, 48 shots in 136 s), 2.8-4.6 s for
   single-guest clips. With one camera the change is a **punch-in**: alternate wide (100%) and close (120-140%) on
   sentence or phrase boundaries, sometimes a slow push-in during a hold. With two people: cut to whoever speaks,
   cut to the listener's reaction for laughs and pauses.
3. **Captions are the main graphic, not a subtitle strip.** Three styles, from simple to premium:
   - *Plain line* (P1): one short line, white bold with outline, lower third. Cheapest; scored as basic.
   - *Word stack* (P3, P4, P5 - all from one channel): words **appear one by one and pile into a stacked block**
     (2-4 lines), placed in the **empty space beside the head**, never over the face. Size carries meaning: the key
     word is 2-3x bigger than the connecting words ("ผ่านช่วง / **เวลา** / ที่ต้อง / **เลือก**"). White, heavy font,
     soft shadow; a word that is about to be said can sit dimmed (grey) until it is spoken. The block clears at the
     end of the phrase and the next builds from empty.
   - *Word pop* (P8): 1-2 words at a time, small, in negative space next to the speaker, key words in yellow.
4. **Key words get pictures.** About every 5-10 s a key noun becomes a visual: stock footage or image full-frame
   with the speaker in a **circle picture-in-picture** (P7: Formula 1 car, Titanic, Marconi), an icon / logo row
   (P6: Google, Microsoft, Apple, Nvidia...), a simple graph, or a short motion-graphic scene with the word as a
   label (P8: "Rest" with a 3D figure, "The 4 R's"). The cut back to the speaker is a hard cut or a 0.3 s dissolve.
5. **Two speakers on one screen.** 16:9 two-camera sources become 9:16 **split screen**: speaker A top, speaker B
   bottom (P7), or alternate full-frame close-ups (P1).
6. **Look.** A consistent grade per channel (warm skin, cooler or teal background in P6), brand logo small in a corner,
   no letterbox bars. P9 (premium) mixes two fonts (italic serif + heavy sans) and two accent colours per phrase.
7. **Sound.** Integrated loudness -12 to -22 LUFS (median about -17); speech forward, music low or none under talk.
   The last ~3 s of every file is TikTok's own end card (not part of the edit).

## What our skill already does / what is missing
| Pattern | Status in the skill |
|---|---|
| Hook / topic card at start | done: topic card (`titles` with `items`), animated titles |
| Persistent headline | done (v3): plan `"headline": {"text", "tag", "start"}`, top band 3-12% of the height, above the face |
| Cut to the speaker, reframe to 9:16 | done: `reframe.py` (crop to person, blur fit for two-shots) |
| Punch-in zoom on one camera | done (v3): `reframe.py --punch 1.3 --every 3 --words words.json` cuts at pauses, zoom anchored at the top so the face moves down |
| Word captions | basic: `word_captions.py` (1-3 words, highlighted word, fixed place) |
| Word-stack kinetic captions | done (v4): `word_captions.py --style stack` (English: stop words small, longest content word big + accent; Thai needs word segmentation first) |
| B-roll with speaker circle PiP | done (v5): clip `"broll": [{src, start, end, in, focus, region, pip}]`, bubble top right under the headline |
| Icon / logo / graph inserts | missing (logos are trademarks: only when the topic is about those companies) |
| Split screen two speakers | done (v5): `reframe.py --stack` -> `fit: "stack"`, one panel per person framed on the head |
| Grade + logo | partial: per-clip `filter`; no channel preset or logo slot |

## Versions built from this study (interview Short, Royal Society clip)
| Version | What changed | Picture changes / 10 s | Notes |
|---|---|---|---|
| v2 | topic card intro + 1-3 word captions | 1.7 | user score 9/10 (before the study) |
| v3 | + persistent headline + punch-in 1.3x every ~3 s at pauses | 2.4 | first headline covered the guest's hair: moved to the top band, smaller; punch anchored at the top |
| v4 | + word-stack captions | 2.4 | first pick of key word was "actually": filler adverbs are stop words now; small words were lost on a printed T-shirt: 0.58 of the big size with a heavier outline |
| v5 | + 5 B-roll inserts with the speaker in a circle bubble (10.5 s, 25% of the clip) + split screen on two-shots | 4.7 | bubble first covered the captions (moved top right under the headline); a still was cropped to the empty road (B-roll `focus`); Zhengzhou footage had burned-in Chinese captions (`region` crop); split-screen top panel put the host's head under the headline (top panel framed lower); captions over the guest's face on split screens (they sit over the listener's torso there) |
| v6 | speaker bubble follows the face (skin + motion, ~2.3 face widths) instead of a fixed square | 4.7 | the fixed square showed only eyes and forehead on close-ups (user caught it); skin alone picked a wooden bookshelf on the split screen, motion fixed it |
| v7 | word stack in mixed type: key word bold italic serif (Georgia) in a colour that changes per phrase, small words italic serif, numbers red | 4.7 | long serif words ran off the frame: each line now shrinks to 90% of the width |
| v8 | + two huge words behind the person ("DANGEROUS" x3 in red, "WARMING" in orange) on the key lines | 4.7 | needs the u2net_human_seg model (176 MB, user approved, saved in ~/.rembg/models); masks for 2 x ~2 s took seconds, whole render 66 s |
| v9 | behind-words and B-roll phrases picked by `pick_moments.py` instead of by hand, + a black ending card | 4.7 | first picks: "INDEED" (loud filler) and "BUILD" on a punched-in shot where the head hid it: fillers/verbs penalised, zoomed pieces skipped, render warns when the person covers >80% of the word band; the headline stayed over the card (now ends where a card starts); the last caption spilled onto the card (captions end with their clip) |
| v10 | B-roll found by `find_broll.py` (search -> user approves files and sizes -> fetch places them) instead of by hand | 4.7 | literal searches ("humans live") found junk: every search now carries a topic word (`--context flood`) and only phrases whose results contain their words are kept; 3 of 7 phrases qualified, all three inserts fit their lines |
Reference pace for single-guest clips: a picture change every 2.8-4.6 s (v3/v4: every ~4.2 s). Comparison video:
`genres/interview/compare_v2_v3_v4.mp4` (local).

## Second batch (12 more clips, 2026-11-22): what it added
Pace: two-camera and B-roll-heavy edits change picture every 1.4-3.2 s (P11 1.4 s, P15 2.4 s, P17 2.5 s);
single-camera talks 4-5 s. Loudness ran louder than the first batch: -9 to -22 LUFS, most around -14.
- **Mixed type** (P11, P13, P15-P17): one phrase mixes a bold italic serif and a heavy sans; key words change colour
  (pink, yellow, sky blue, purple, orange). Built as `word_captions.py --style stack --type mix` (v7).
- **Huge word behind the person** (P11 "BRUTAL", P20 "DEPENDENT", "PROPERTY"): the speaker is cut out and drawn over
  a giant word. Built (v8): clip `"behind": [{"text", "start", "end", "color", "repeat", "y"}]` in edit plans.
- **Text-only black cards** between segments, often a quote in two fonts (P15-P17), and a closing title card with a
  chrome/serif treatment (P20).
- **Numbers and money in red** (P18 "$1,500,000"); single big caps word per beat (P21); B&W letterbox with one
  serif caps word at a time (P19) as a minimal premium look.
- **Thai stage talk** (P14): four-colour stacked words (green, blue, yellow, red) with outline, then plain lines.
- **B-roll from films and animation** (P15-P17, P12) is common in these edits but is copyrighted: the skill uses only
  licensed footage (Commons, the user's own, generated).
- **Lifestyle cutaways** (P10): the hosts re-shot on location (basketball court, garden) cut between studio lines;
  a black "3 things to know" title card as a chapter break; quick whip-blur transitions.

## One command: `scripts/podcast_short.py`
```
python -I scripts/podcast_short.py talk.mp4 work --title "Who gets warned
**before the flood?**" --tag "Guest · Show"
       --topics "item 1" "item 2" "item 3" --context flood --music bed.mp3 [--words words.json] [--length 40]
```
Runs transcript -> segment pick -> plan (topic card, headline, music) -> reframe (camera cuts, follow the person, split
screen, punch-in) -> behind-words -> B-roll search -> captions -> preview, stopping at three gates; rerun the same command
with `--ok-segments` (or `--segments a-b ...`), `--broll-pick 1a 2b` (or `--no-broll`), then `--final`. All choices
are in `work/plan.json`. Write the title and topics **after** gate 1, to match the lines it picked.

First run (Royal Society interview, 10 min): picked a self-contained 36 s answer on flood warnings for poorer countries
(367-405 s), 2 behind-words (BANGLADESH, INFRASTRUCTURE), 2 approved B-roll stills, final render 59 s, QA pass.
What it took to get there (all fixed): the first segment pick started mid-answer ("Those ones that...") and included
the host's questions -> lines before a "?" and sign-offs ("thank you so much") count as the host, a piece may not open
on a connecting word; the next pick was a fine answer on heat and health, off the title's topic -> sentences with the
topic or title words score 1.6x; a phrase search found nothing for "partners mozambique" -> one-word fallback searches;
a typed "
" in the title was two characters, so the headline underline crossed the text -> converted on input.
Still weak: long behind-words (INFRASTRUCTURE) get half hidden by the head, and a B-roll title match can still be a
poor picture ("Often flooded" was a dry field): the gate is where a person says no.
