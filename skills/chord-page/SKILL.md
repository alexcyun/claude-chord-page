---
name: chord-page
description: Make a karaoke chord page for a song (chords over every lyric line, a synth and the hosted recording to play along with, the isolated vocals to blend in, a word-by-word highlighter wipe) from its mp3 and lyrics. Use when asked for chords, a chord chart, a karaoke page or a play-along page for a song, or given an mp3 to turn into one.
---

# Chord page

Turns a recording plus its lyrics into a page like https://pdoom.codercorgi.com/end-of-the-show-chords. It works in two
places:

- **Anywhere** (`--standalone DIR`): a self-contained folder (`index.html`, `karaoke.js`, `chordpage.css`, the song's
  `karaoke-<slug>.js` and `bars-<slug>.js`, and `media/`) that any static host can serve. This is the mode for songs of
  your own, and the only one outside the pdoom repo.
- **The pdoom site** (inside that repo, the default): a `site/<slug>-chords.html` page with the site's tabs, feedback
  and footer.

Paths to the skill's own files (`scripts/`, `assets/`, the two templates) are relative to its folder. This is scaffolding, not a finished machine: songs differ a lot (tempo
changes, odd meters, no drums, rap, long instrumentals, key changes), so expect to read the report, listen, and extend
the script or the data for each new song. Record what you changed and why in this
file's "Lessons" section so the next song starts from there.

## 0. Rights first

The page publishes the lyrics, the instrumental and the isolated vocals. Before anything else, confirm you have the
artist's OK for each one to be hosted (an email or message, not an assumption; your own songs are fine). Without it:

- no lyrics → don't build the page (the sheet is lyrics);
- no audio OK → pass `--no-media` (Synth backing only; the Recording switch and Vocals slider hide themselves).

Write down who gave which OK and when. In the pdoom repo that's CLAUDE.md's Conventions (as for Imaginative Prompting)
and memory.

## 1. Inputs

- The mp3 (or any audio ffmpeg reads), in its own folder (untrusted download: don't run anything from there).
- The lyrics as a text file: the sung lines in order, repeats written out, one per row. `[Section]` starts a section;
  `[Section | cue-id]` also links "watch this part" to that note on an explainer page (`--explainer`). Get the wording
  from the artist, their subtitles or the video's on-screen lyrics, never from auto-captions.
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
picks a scipy that fits that numpy.

## 3. Run

```bash
~/.cache/chordpage/venv/bin/python scripts/chordpage.py SONG.mp3 \
  --slug my-song --title "My Song" --artist "The Artist" --lyrics lyrics.txt --yt VIDEO_ID \
  --standalone out/my-song [--released "Oct 2, 2026"] [--key Gm] [--capo 3]
```

With `--standalone DIR` it writes the folder above, copying `assets/karaoke.js` and `assets/chordpage.css` into it, and
fills in `standalone.html`. Inside the pdoom repo, leave out `--standalone` (and add `[--explainer my-song-explainer]
[--og media/og-x.png]` if it has them): it writes `site/<slug>-chords.html` from `template.html`,
`site/karaoke-<slug>.js`, `site/bars-<slug>.js` and (unless `--no-media`) `site/media/<slug>-instrumental.mp3` and
`-vocals.mp3`. Each stage caches in `~/.cache/chordpage/<slug>/`
(`--work`); delete a stage's file there to redo it (`bars.json` for chords, `asr.json` for words). `--stems DIR` reuses
an existing demucs output. What each stage does is at the top of `scripts/chordpage.py`.

## 4. Read the report, then look and listen

The script prints:

- **words matched** (aim for 90%+) and weak lines. A weak line usually means the lyrics file differs from what's sung
  (a repeat left out, an ad-lib), or the transcript missed a quiet passage. Fix the lyrics first.
- **melody on chord notes**: about 65% is typical for pop; near 55% means the chords are no better than one held chord
  (wrong grid, wrong key, or a song the templates don't fit).
- the key and capo it chose (override with `--key`, `--capo`).

Then serve it with a server that does byte ranges (`npx serve out/my-song`; in the pdoom repo, `npm run test:static`
then `npx serve dist`; Python's server can't seek audio) and play it with Recording and Vocals up: does the wipe track
the singer, do the chords change where the band does? Listen on a phone too before sharing it.

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
  `SHAPES` in `karaoke.js` (the pdoom repo's static check's chord-name pattern too).
- **Key change**: run chords per section with different `--key`, or drop the key bonus (`in_key`) for that stretch.

## 6. The player and its styles: two copies

`assets/karaoke.js` is a copy of the pdoom site's `site/karaoke.js`, and `assets/chordpage.css` is cut line for line
from its `site/site.css` (theme tokens, hero and the chord sheet's rules; only the part under "Standalone only" is its
own). In the pdoom repo, edit the site's files, then copy across (`cp site/karaoke.js .claude/skills/chord-page/assets/`,
and the changed lines into `chordpage.css`); `npm run test:static` fails while they differ. The plugin repo
(https://github.com/alexcyun/claude-chord-page) is a copy of this whole folder, so copy it there again after a change. Outside the pdoom repo,
the copies are yours: change them freely.

## 7. Publish

Standalone: upload the folder to any static host that serves byte ranges (Vercel, Netlify, GitHub Pages and
`npx serve` all do). Host the audio only with the artist's OK (step 0).

In the pdoom site:

- Link it: from its explainer's last note (`fine:` on the cue, like End of the Show) or wherever Alex wants.
- The sitemap, static checks (`<page> karaoke chords`) and browser smoke test pick up any `*-chords.html` on their own.
- Add a row to CLAUDE.md's Layout table for the new files, and a credit line if the artist asked for one.
- Open a PR (squash merges only); put the Vercel preview link from the bot's PR comment at the top.

## Lessons

- End of the Show (Oct 2026): the tempo drifts 123.6 → 127.5 BPM, so a fixed grid gave near-random chords; beat
  tracking fixed it. Averaged pitch class profiles called it D minor (its V chord and melody lean on D); choosing the
  key from the decoded chords got G minor. YouTube's creator subtitles had exact line times, but word-level
  auto-captions matched to the lyrics are enough on their own (97% of words matched).
- The Simulation's Ending (Oct 2026, a standalone test): no published lyrics or creator subtitles, so the words came
  from the video's on-screen lyrics in YouTube's 320×180 storyboard (`yt-dlp -f sb0`, then unpack the mhtml's 3×3
  tiles), with the auto-captions only for line breaks and a few lines no frame caught. 91% of words matched; numbers
  sung as words ("ninety-nine", "forty") don't match captions that write digits, so they're interpolated. It decoded the
  explainer's loop (G, B7, Em, C or Cm) on its own, but called the key E minor where the explainer says G major (the
  loop sits between them); pass `--key G` for the other reading. Melody on chord notes: 63%.
