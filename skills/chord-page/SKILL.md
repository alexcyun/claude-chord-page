---
name: chord-page
description: Make a karaoke chord page for a song (chords over every lyric line, a synth and the hosted recording to play along with, the isolated vocals to blend in, a word-by-word highlighter wipe, the sung melody as a contour over the words and as a scrolling pitch lane with an optional mic) from its mp3 and lyrics. Use when asked for chords, a chord chart, a karaoke page or a play-along page for a song, or given an mp3 to turn into one.
---

# Chord page

Turns a recording plus its lyrics into a page like https://music.codercorgi.com/end-of-the-show-chords: a
self-contained folder (`index.html`, `karaoke.js`, `chordpage.css`, the song's `karaoke-<slug>.js`,
`bars-<slug>.js` and `melody-<slug>.js`, and `media/`) that any static host can serve.

Paths to the skill's own files (`scripts/`, `assets/`, `template.html`) are relative to its folder. This is
scaffolding, not a finished machine: songs differ a lot (tempo changes, odd meters, no drums, rap, long instrumentals,
key changes), so expect to read the report, listen, and extend the script or the data for each new song. Record what
you changed and why in this file's "Lessons" section so the next song starts from there.

What the page does (all in `assets/karaoke.js`; the only per-song settings are the data file's `KARAOKE_SONG`: `key`,
`capo`, `about`, `instrumental`, `vocals`):

- **Melody contour**, for singing it yourself or a cappella: between the chords and the words, a dash per sung note, as
  high as its pitch within the song's range and as wide as the words it's sung over, so it lines up with the wipe and
  fills in highlighter yellow as the note is sung. Hovering a dash names the note (in the sheet's key, so it follows
  transpose). A **Melody** toggle shows or hides it (saved as `chordpage-melody`, on by default); it hides itself on a page
  with no melody file. The notes come from the vocals stem, so they're a reading of the recording, like the chords.
- **Pitch lane**, SingStar style, from the same notes: while Play runs (or pauses), a strip pinned in the toolbar (on
  phones too, with Listen and Mix) scrolls the notes right to left past a "now" line, each a bar as high as its pitch
  and as long as it's held, with the words underneath and the note being sung in highlighter yellow. It follows the
  song's clock, so it holds still on pause and jumps with a line tap, a loop or a backing change; its pitches follow
  transpose with Synth and are the recording's with Recording. A **Pitch lane** toggle (saved as `chordpage-lane`, on by
  default) shows or hides it, and it hides itself with no melody file. Its **Mic** button (opt-in, never saved) shows
  the pitch you sing as a dot and a trail at the now line (YIN pitch detection on the page's own audio graph, in any
  octave), lighting each note you sing within a semitone of. Nothing is recorded or sent; it stops when Play stops or
  the page is hidden, and asks for headphones, since a mic near speakers hears the backing.

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

Write down who gave which OK and when. If the repo's notes say the artist hasn't been asked, ask the user what they
hold before building: it decides which page you make.

## 1. Inputs

- The mp3 (or any audio ffmpeg reads), in its own folder (untrusted download: don't run anything from there). If the
  page will sit beside a video (word times from `--yt`, or a site that plays the video in step), check the mp3 is the
  video's audio: same length to the tenth of a second, and a cross-correlation of the two at the start, middle and end
  that peaks at zero offset. If it's offset, pad or trim the mp3 to the video's clock before anything else.
- The lyrics as a text file: the sung lines in order, repeats written out, one per row. `[Section]` starts a section.
  Get the wording from the artist, their subtitles or the video's on-screen lyrics, never from auto-captions. A lone
  dash between words ("ten years – all by itself") is fine: it's drawn, not timed as a word.
- No published lyrics, but the video prints them? `scripts/screen_lyrics.py VIDEO.mp4` (macOS) reads them off the
  frames, two a second, and prints when each piece of text appears; `--all` shows every part of the screen with its
  height, for a spoken intro typed at the top or a hook in big letters mid-screen. YouTube's storyboard has a frame
  only every five seconds, which misses lines; a 480p copy of the video (about 10 MB) catches every one. Take each
  line's last, complete reading, set capitals and punctuation by eye from a frame, and keep the screen's spelling.
  Text on screen that nobody sings (names floating by in an instrumental) isn't a line: check the vocals stem is
  silent there.
- Word timing: `--yt VIDEO_ID` uses YouTube's word-timed auto-captions (best when the song is on YouTube); `--whisper`
  transcribes the vocals stem with faster-whisper instead. Pass **both** when you can: the captions time the words
  first, and whisper's transcript fills in what they didn't hear (captions often drop a shouted or doubled chorus hook
  whole, and whisper on the bare vocals hears it). The transcripts only give timing; mishearings are fine, since words
  are matched to the real lyrics.

## 2. Environment (once)

```bash
uv venv ~/.cache/chordpage/venv -p 3.12 --managed-python
VIRTUAL_ENV=~/.cache/chordpage/venv uv pip install "demucs==4.0.1" "torch<2.9" "torchaudio<2.9" "numpy<2" "librosa<0.12" "numba<0.62" soundfile "yt-dlp[default]" faster-whisper
```

First check it still works (`~/.cache/chordpage/venv/bin/python -c "import demucs, librosa"` and `which ffmpeg`): a
venv built on a Homebrew Python dies when that Python is upgraded or removed, which is why this one uses uv's own
(`--managed-python`). If it's dead, move it aside and make it again.

ffmpeg must be on PATH (`brew install ffmpeg`). demucs pulls in torch (about 1 GB) and takes a few minutes per song on
a laptop CPU. The pins, each from a failure:

- demucs 4.0.1: 4.1 needs `sphn`, which has no wheel for some Macs and fails to build.
- torch and torchaudio below 2.9: from 2.9 torchaudio saves files through torchcodec, which isn't installed, so demucs
  splits the whole song and then fails writing the stems ("TorchCodec is required").
- numpy below 2: on Macs where torch stops at 2.2, demucs fails with "Numpy is not available". Install everything in
  one command, so the resolver picks a scipy that fits that numpy.
- `yt-dlp[default]`, plus deno (`brew install deno`): YouTube now needs a JavaScript runtime and yt-dlp's solver
  scripts (the `[default]` extra) to hand over anything but captions. Without them it warns "n challenge solving
  failed" and formats go missing.
- faster-whisper 1.2 can't open a file with PyAV 16 (it passes an argument PyAV dropped), so the script hands it the
  samples instead; no `av` pin needed.
- faster-whisper's first run downloads its model (about 500 MB for `small.en`, which can take ten minutes): run it in
  the background.

## 3. Run

```bash
~/.cache/chordpage/venv/bin/python scripts/chordpage.py SONG.mp3 \
  --slug my-song --title "My Song" --artist "The Artist" --lyrics lyrics.txt --yt VIDEO_ID \
  --whisper --out out/my-song [--own] [--released "Oct 2, 2026"] [--key Gm] [--capo 3] [--phase N] [--about "…"] [--half-time] [--evidence]
```

It writes the folder above into `--out` (one song per folder: it refuses one holding another song), with copies of
`assets/karaoke.js` and `assets/chordpage.css`. `--own` is for your own song: the footer credits you instead of saying
the page isn't affiliated with the artist; `--permission " (shared with their permission)"` sets the footer's credit
otherwise. Each stage caches in `~/.cache/chordpage/<slug>/` (`--work`); delete a stage's file there to redo it
(`bars.json` for chords, `asr.json` for the captions and `asr-whisper.json` for whisper's words (a run with neither
`--yt` nor `--whisper` reuses whichever are cached; a work dir from before Nov 2026 may hold whisper's words in
`asr.json`, which now reads as captions: rename it to `asr-whisper.json`), `pitch.npz` for the melody's pitch track).
`--stems DIR` reuses an existing demucs output. What each stage does is at the top of `scripts/chordpage.py`.
`--about` sets the line under the key (by default the most common run of four chords, which reads wrong for a song
whose verse and chorus loop differently), `--half-time` says the song is felt at half the tracked tempo (see 5), and
`--evidence` prints what each bar's chord was read from (see 4).

Everything the page needs should come out of the command, so a rerun doesn't lose work: fix chords in the cached
`bars.json` (keep the decoded one beside it as `bars.decoded.json`) and words in the lyrics file, not in the written
data files, which every run overwrites. Settle `--key` and `--phase` first: a run with a different one decodes again
and replaces `bars.json`, hand fixes and all (copy them back from your own record of them).

A page made before melodies existed gets one without touching its other files: pass its vocals stem (the hosted
`media/<slug>-vocals.mp3` will do) and `--melody-only`. It reads the page's lines from its `karaoke-<slug>.js`, writes
`melody-<slug>.js` and adds its script tag before the data file's:

```bash
~/.cache/chordpage/venv/bin/python scripts/chordpage.py out/my-song/media/my-song-vocals.mp3 --melody-only --slug my-song --out out/my-song
```

## 4. Read the report, then look and listen

The script prints:

- **words matched** (aim for 90%+; misheard words still take the misheard words' times, and words the transcript left
  out go on the sung notes) and weak lines. A weak line usually means the lyrics file differs from what's sung
  (a repeat left out, an ad-lib), or the transcript missed a passage: add the other transcript (`--yt` and `--whisper`
  together). A hook both transcripts mishear the same way every time ("thus spoke compute" as "the spoke computes")
  stays on the weak list and is still timed right. Then check the times themselves, not just the score: list each
  line's word times from `karaoke-<slug>.js` and look for a line squeezed into a fraction of a second or starting
  seconds early (an ad-lib's notes), and compare a few against when the video prints the words.
- **melody on chord notes**: about 65% is typical for sung pop; near 55% means the chords are no better than one held
  chord (wrong grid, wrong key, or a song the templates don't fit), or that there's little melody to score: a rap
  scores 55 to 57% with good chords. Then judge the chords from `--evidence` instead: a row per bar with the decoded
  chord, the bass stem's note and the backing's three strongest notes for each half bar. A bar that departs from the
  song's loop is real if its notes spell a chord (D and A with a D in the bass), a riser or effect if they're a
  cluster (C, C#, D), and a major third over a root and fifth (G# over E and B) is a power chord's overtone, so E
  there is Em in a minor song.
- the key and capo it chose (override with `--key`, `--capo`).
- **melody**: how many notes, their range, and how much of the sung lines' time they cover (70% or more is good; much
  less means the vocals stem is hard to track: heavy effects, harmonies, or a lot of the band left in it).

Then serve it with a server that does byte ranges (`npx serve out/my-song`; Python's server can't seek audio) and play
it with Recording and Vocals up: does the wipe track the singer, do the chords change where the band does? Listen on a
phone too before sharing it.

## 5. Extend for this song

Common fixes, roughly in order of how often they're needed:

- **Wrong chord here and there**: edit `bars-<slug>.js` and the chord in `karaoke-<slug>.js` by hand (keep both in
  step), or rerun with `--key`. For a section that repeats a loop, snap the stray bars to the loop.
- **Grid off by a beat** (chords change one beat early or late everywhere): the downbeat guess was wrong; rerun with
  `--phase N` (0 to 3, the beat the bars start on). Two checks name the `--phase` to try: the bass check (where the
  bass changes most often, with its margin) and the report's grid check (the melody scored against every chord moved a
  beat either way). Trust them when they agree; either alone can mislead (a melody that leads its changes trips the grid
  check), so the run never switches on its own.
- **Half-time or double-time feel**: the beat tracker locked onto the wrong level. Check where the kick and snare fall
  over each pair of tracked bars (the drums stem's energy below 120 Hz and from 180 Hz to 2.5 kHz at each beat): a
  snare on every fourth tracked beat, not every second, means the song is felt at half the tracked tempo (rap and
  half-time drums do this, and a line of lyrics then lasts two tracked bars). If the chords change inside the short
  bars (Am for two beats, B7 for two), keep the finer grid, since a bar holds only two chords, and pass `--half-time`
  so the page states the felt tempo. Otherwise pass a better `start_bpm` in `beats()`, or halve the beats list.
- **No drums**: beat-track on the `other` stem instead of `drums`.
- **Chord types it can't name** (sus, maj7, dim, add9): add them to `QUAL` in the script and to `QUAL` and
  `SHAPES` in `karaoke.js`.
- **Key change**: run chords per section with different `--key`, or drop the key bonus (`in_key`) for that stretch.
- **Melody too busy or too sparse**: tune how `melody()` cuts the pitch track into notes (`tol`, how far the pitch may
  wander inside a note; `need`, how long it must leave before a new note starts; `shortest`), then rerun: the pitch
  track is cached, so it takes seconds. Specks are usually slides between notes; gaps are frames pyin didn't call
  voiced (a breathy or heavily processed vocal).

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
  auto-captions matched to the lyrics are enough on their own (97% of words matched). Its melody came later
  (`--melody-only` on the hosted vocals stem, which found the page by its data file, since it predates the
  `<slug>-chords.html` name): the Simulation's voicing fix carried over unchanged, 832 notes across C3–F4, 73% covered,
  59% on chord notes, almost all in G minor's scale and only 3 octave jumps.
- The Simulation's Ending (Oct 2026): no published lyrics or creator subtitles, so the words came from the video's
  on-screen lyrics in YouTube's 320×180 storyboard (`yt-dlp -f sb0`, then unpack the mhtml's 3×3 tiles), with the
  auto-captions only for line breaks and a few lines no frame caught. 91% of words matched; numbers sung as words
  ("ninety-nine", "forty") don't match captions that write digits, so they're interpolated. It decoded the song's loop
  (G, B7, Em, C or Cm) on its own, but called the key E minor where a by-ear reading says G major (the loop sits
  between them); pass `--key G` for the other reading. Melody on chord notes: 63%. Its melody contour came later
  (`--melody-only` on the hosted vocals stem): pyin's voicing probability sat around 0.1 even mid-line on these Suno
  vocals, so gating on it kept only 14% of the sung time; its voiced flag plus a loudness floor kept 76%. Notes under
  0.1 s touching a longer one were slides, folded into it (709 notes to 648, 70% covered, range G3–B4).
- I'm Upping My P(doom), Claude-Pop (Oct 2026): a Suno song at a steady 132 BPM, each chord held two bars. The bass stem changed exactly on the decoded grid, yet melody on chord notes scored 54%, the "no better than one chord" mark: the melody leads into each change about three beats early, so scoring it against chords shifted 1.4 s earlier gave 63%. Before trusting a low score, print the bass stem's pitch class per beat and score a few grid shifts. The loop summary under the key used to count bars ("Eb, Bb, Bb, Cm"); it now counts chord changes. The two-beat chord before each chorus decoded as Dm7b5 over a D bass, but the backing there is a chromatic riser (D, C#, Eb, E), so it's written Bb (Bb/D). To check chord qualities, average the `other` stem's CQT from C3 up, in dB, over every half bar of each chord: it showed Fm7 where the decoder said Fm, and the loop voiced as maj7 chords (a stray tritone, like A over Eb, is the maj7's overtone). Edit the cached `bars.json` and rerun into a scratch `--site` copy to re-place the chords over the words, then carry over hand fixes. Words matched only 78%: the captions heard "upping my P(doom)" as "up in my bedroom" and "Shinigami eyes" as "shining got me high", and unmatched words used to be spread evenly to the next match, so "Shinigami eyes" ran five seconds too long. Now a misheard run takes the times of the words heard in its place (by syllable share), and words the captions left out go on the sung notes' starts, a note per syllable; the captions' `[music]` markers are dropped. It was first built with `--no-media` while only the lyrics were OK'd; when the audio was cleared, the two mp3s were encoded from the cached stems with `build()`'s ffmpeg commands and named in `KARAOKE_SONG`, since a rerun rewrites the data files and would drop hand fixes.
- Upping My P(doom), Patryk Perduta (Nov 2026): YouTube's bot check blocked downloads from a cloud machine, so the
  mp3 came from the requester and the words from `--whisper` (82% matched; every line still landed inside the
  independently timed line windows). Whisper writes "P(doom)" as two pieces, "pee" and "-dum", so each piece took a lyric word and every word after
  a P(doom) run slipped by one; `joined()` now merges a hyphen-led piece into the word before (`--whisper` only). The
  downbeat guess (harmony and bass together) was a beat late: the bass changed on the last beat of every bar, and the
  melody scored 51% on the grid against 58% a beat later; `--phase 0` fixed both (the score now peaks unshifted). The run
  now prints both checks and they agreed, but neither is safe to act on alone: the bass won by only 8%, and decoding the
  chords on each grid and scoring them against the bass, or counting bass note changes per beat, didn't separate the two
  beats at all. Key C#m, so the page spells its V chord G#, not Ab: the generator spells chords by key
  (`spell()`), and the player respells by the key on screen, so transposing to D minor gives flats again. The loop
  summary now counts each line from the bar line nearest its start, so a pickup counts from the bar it leads into ("C#m,
  A, E, G#", not "G#, C#m, A, E"). On a fresh
  install, torch and torchaudio 2.9 broke demucs (saving needs `torchcodec`) and PyAV 16 broke faster-whisper
  (`metadata_errors`); pin `torch<2.9 torchaudio<2.9` and, for `--whisper`, `av<16`.
- Pitch lane and mic (Oct 2026): a MediaStream made by another AudioContext reads as silence in the Claude desktop
  app's browser pane, so to test the mic path there, stub the page's `createMediaStreamSource` to return an oscillator
  in the same context. YIN finds a sung pitch to well under a cent in about 1 ms per 2048-sample reading, so a reading
  every 30 ms costs nothing on a phone. Mic timing (the backing's output latency plus the mic's) can only be judged on
  a real phone with headphones.
