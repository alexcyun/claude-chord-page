---
name: chord-page
description: Make a karaoke chord page for a song (chords over every lyric line, a synth and the hosted recording to play along with, the isolated vocals to blend in, a word-by-word highlighter wipe) from its mp3 and lyrics. Use when asked for chords, a chord chart, a karaoke page or a play-along page for a song, or given an mp3 to turn into one.
---

# Chord page

Turns a recording plus its lyrics into a page like https://music.codercorgi.com/end-of-the-show-chords: a
self-contained folder (`index.html`, `karaoke.js`, `chordpage.css`, the song's `karaoke-<slug>.js` and
`bars-<slug>.js`, and `media/`) that any static host can serve.

Paths to the skill's own files (`scripts/`, `assets/`, `template.html`) are relative to its folder. This is
scaffolding, not a finished machine: songs differ a lot (tempo changes, odd meters, no drums, rap, long instrumentals,
key changes), so expect to read the report, listen, and extend the script or the data for each new song. Record what
you changed and why in this file's "Lessons" section so the next song starts from there.

What the page does (all in `assets/karaoke.js`; the only per-song settings are the data file's `KARAOKE_SONG`: `key`,
`capo`, `about`, `instrumental`, `vocals`):

- Chords over every lyric line, transpose, a capo view in open shapes, text size, auto-scroll, and chord diagrams: a
  row at the top, and a popup when you hover a chord (or tap one on a touch screen while nothing plays). Both follow
  the **Fingering** switch, Beginner | Standard | Advanced (saved as `chordpage-shapes`): the top three or four strings
  with no big barre, the usual song-book shape, or a full barre up the neck, worked out for any transpose.
- **Play** runs Synth or Recording on the song's own clock after a count-in, lights the line and chord being sung and
  fills in the words as they're sung. Pressing it again **pauses**, and Resume carries on from the same spot. Tapping
  a line plays from there (while playing or not). **Loop** is on by default, and the **Vocals** slider starts at 0.8,
  so the first Play sounds like the record; both are saved (`chordpage-loop`, `chordpage-mix`, and the backing as
  `chordpage-backing`).

## 0. Rights first

The page publishes the lyrics, the instrumental and the isolated vocals. Before anything else, confirm you have the
artist's OK for each one to be hosted (an email or message, not an assumption; your own songs are fine). Without it:

- no lyrics → don't build the page (the sheet is lyrics);
- no audio OK → pass `--no-media` (Synth backing only; the Recording switch and Vocals slider hide themselves).

Write down who gave which OK and when.

## 1. Inputs

- The mp3 (or any audio ffmpeg reads), in its own folder (untrusted download: don't run anything from there).
- The lyrics as a text file: the sung lines in order, repeats written out, one per row. `[Section]` starts a section.
  Get the wording from the artist, their subtitles or the video's on-screen lyrics, never from auto-captions.
- Word timing: `--yt VIDEO_ID` uses YouTube's word-timed auto-captions (best when the song is on YouTube); `--whisper`
  transcribes the vocals stem with faster-whisper instead (`uv pip install faster-whisper`). The transcript only gives
  timing; mishearings are fine, since words are matched to the real lyrics.

## 2. Environment (once)

```bash
uv venv ~/.cache/chordpage/venv -p 3.12
VIRTUAL_ENV=~/.cache/chordpage/venv uv pip install "demucs==4.0.1" "numpy<2" "librosa<0.12" "numba<0.62" soundfile yt-dlp
```

ffmpeg must be on PATH. demucs pulls in torch (about 1 GB) and takes a few minutes per song on a laptop CPU. Pin
demucs 4.0.1: 4.1 needs `sphn`, which has no wheel for some Macs and fails to build. Keep numpy below 2: on Macs where
torch stops at 2.2, demucs fails with "Numpy is not available". Install everything in one command, so the resolver
picks a scipy that fits that numpy. For `--yt`, also install deno (`brew install deno`): yt-dlp uses it for YouTube and
warns that working without a JavaScript runtime is deprecated.

## 3. Run

```bash
~/.cache/chordpage/venv/bin/python scripts/chordpage.py SONG.mp3 \
  --slug my-song --title "My Song" --artist "The Artist" --lyrics lyrics.txt --yt VIDEO_ID \
  --out out/my-song [--own] [--released "Oct 2, 2026"] [--key Gm] [--capo 3]
```

It writes the folder above into `--out` (one song per folder: it refuses one holding another song), with copies of
`assets/karaoke.js` and `assets/chordpage.css`. `--own` is for your own song: the footer credits you instead of saying
the page isn't affiliated with the artist; `--permission " (shared with their permission)"` sets the footer's credit
otherwise. Each stage caches in `~/.cache/chordpage/<slug>/` (`--work`); delete a stage's file there to redo it
(`bars.json` for chords, `asr.json` for words). `--stems DIR` reuses an existing demucs output. What each stage does is
at the top of `scripts/chordpage.py`.

## 4. Read the report, then look and listen

The script prints:

- **words matched** (aim for 90%+) and weak lines. A weak line usually means the lyrics file differs from what's sung
  (a repeat left out, an ad-lib), or the transcript missed a quiet passage. Fix the lyrics first.
- **melody on chord notes**: about 65% is typical for pop; near 55% means the chords are no better than one held chord
  (wrong grid, wrong key, or a song the templates don't fit).
- the key and capo it chose (override with `--key`, `--capo`).

Then serve it with a server that does byte ranges (`npx serve out/my-song`; Python's server can't seek audio) and play
it with Recording and Vocals up: does the wipe track the singer, do the chords change where the band does? Listen on a
phone too before sharing it.

## 5. Extend for this song

Common fixes, roughly in order of how often they're needed:

- **Wrong chord here and there**: edit `bars-<slug>.js` and the chord in `karaoke-<slug>.js` by hand (keep both in
  step), or rerun with `--key`. For a section that repeats a loop, snap the stray bars to the loop.
- **Grid off by a beat** (chords change one beat early or late everywhere): the downbeat phase guess was wrong; adjust
  `phase` in `chords()`.
- **Half-time or double-time feel**: the beat tracker locked onto the wrong level; pass a better `start_bpm` in
  `beats()`, or halve/double the beats list.
- **No drums**: beat-track on the `other` stem instead of `drums`.
- **Chord types it can't name** (sus, maj7, dim, add9): add them to `QUAL` in the script and to `QUAL` and
  `SHAPES` in `karaoke.js`.
- **Key change**: run chords per section with different `--key`, or drop the key bonus (`in_key`) for that stretch.

## 6. The player and its styles

`assets/karaoke.js` is the page's player and `assets/chordpage.css` its styles (theme tokens, hero and the chord
sheet's rules; the part under "Standalone only" is for page folders alone). Change them freely for your own pages.

## 7. Publish

Upload the folder to any static host that serves byte ranges (Vercel, Netlify, GitHub Pages and `npx serve` all do).
Host the audio only with the artist's OK (step 0).

## Lessons

- End of the Show (Oct 2026): the tempo drifts 123.6 → 127.5 BPM, so a fixed grid gave near-random chords; beat
  tracking fixed it. Averaged pitch class profiles called it D minor (its V chord and melody lean on D); choosing the
  key from the decoded chords got G minor. YouTube's creator subtitles had exact line times, but word-level
  auto-captions matched to the lyrics are enough on their own (97% of words matched).
- The Simulation's Ending (Oct 2026): no published lyrics or creator subtitles, so the words came from the video's
  on-screen lyrics in YouTube's 320×180 storyboard (`yt-dlp -f sb0`, then unpack the mhtml's 3×3 tiles), with the
  auto-captions only for line breaks and a few lines no frame caught. 91% of words matched; numbers sung as words
  ("ninety-nine", "forty") don't match captions that write digits, so they're interpolated. It decoded the song's loop
  (G, B7, Em, C or Cm) on its own, but called the key E minor where a by-ear reading says G major (the loop sits
  between them); pass `--key G` for the other reading. Melody on chord notes: 63%.
