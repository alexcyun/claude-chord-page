# chord-page

A Claude Code skill that turns a song's recording and lyrics into a karaoke chord page: chords over every lyric line,
Ultimate Guitar style, with a player you can sing or play along with. See it on a real song:
https://music.codercorgi.com/end-of-the-show-chords

## What it makes

A folder you can host anywhere:

```
out/my-song/
  index.html               the page
  karaoke.js               the player (shared by every song)
  chordpage.css            its styles, light and dark
  karaoke-my-song.js       the song: lyrics, chords over them, a time for every word
  bars-my-song.js          the bar grid: one or two chords per bar, on the song's own clock
  melody-my-song.js        the sung melody: a start, a length and a pitch per note
  media/my-song-instrumental.mp3   the recording without its vocals
  media/my-song-vocals.mp3         the vocals on their own
```

The page has chords over every line, transpose, a capo view in open shapes, text size, auto-scroll and chord diagrams:
a row at the top, and a popup when you hover a chord (or tap one on a phone while nothing is playing). A **Fingering**
switch picks the shapes, in any key: **Beginner** (the chord's notes on the top three or four strings, no big barre),
**Standard** (the usual song-book shape) or **Advanced** (a full barre up the neck).
**Play** runs a backing on the song's own timing, after a count-in: **Synth** (a small Web Audio keyboard and bass, in
whatever key you transpose to) or **Recording** (the instrumental). A **Vocals** slider blends in the original singer.
While it plays, the line being sung lights up and fills in word by word. Between the chords and the words, a **Melody**
contour draws each sung note as a dash, as high as its pitch and as wide as the words it's sung over, filling in as
it's sung (hover one for the note's name; the Melody button hides it). Pressing Play again **pauses**, and
**Resume** picks up from the same spot. Tap any line to play from there. **Loop** repeats the song. Loop starts on and
Vocals at 0.8, so the first Play sounds like the record; the page remembers your choices.

How it gets there (`skills/chord-page/scripts/chordpage.py`):

1. **Stems**: demucs splits the song into bass, drums, other and vocals.
2. **Beats**: tracked one by one on the drums, since real songs drift in tempo; downbeats from where the harmony
   changes most.
3. **Chords**: one per half bar from the bass and other stems, matched against major, minor, 7 and m7b5 templates with
   a small bonus for chords in the key, and smoothed (Viterbi) so changes land on strong beats. The key comes from the
   decoded chords; the capo from whichever fret gives the most open shapes.
4. **Words**: start times from YouTube's word-timed auto-captions (`--yt`) or faster-whisper on the vocals stem
   (`--whisper`), matched word by word to your lyrics (the transcript only gives timing, so mishearings don't matter).
5. **Melody**: the sung pitch tracked on the vocals stem (librosa's pyin) and cut into notes where it holds steady.
   A page made before this stage existed gets one with `--melody-only`, from its vocals stem.
6. **Build**: each chord over the word being sung when it changes, a change during a held note past the line's words,
   instrumental stretches as rows of chords.

It then reports how many words matched (aim for 90%+), lines that matched poorly, and how often the sung melody lands
on the chord's notes (about 65% is typical for pop; about 55% means no better than one chord held all song), and how
much of the sung lines' time the melody's notes cover (70% or more is good).

This is scaffolding, not a finished machine. The chord reading is a close reading, not the artist's chart: expect to
listen and fix things, and to extend the script for songs it doesn't fit yet (odd meters, no drums, key changes, chord
types beyond major, minor, 7 and m7b5). `skills/chord-page/SKILL.md` lists the usual fixes and keeps a Lessons list
per song; add to it.

## Rights first

The page publishes the song's lyrics, and with media, its instrumental and isolated vocals. Only build and host it
with the artist's OK for each of those (an email or message, not an assumption), or for your own songs. With an OK for
the lyrics but not the audio, pass `--no-media`: the page keeps the Synth backing and hides Recording and Vocals.

## Install

In Claude Code:

```
/plugin marketplace add alexcyun/claude-chord-page
/plugin install chord-page@chord-page
```

Then ask for it in plain words ("make a chord page for this song: ~/Music/song.mp3, lyrics in lyrics.txt, it's on
YouTube at …"), or run the script yourself.

### Environment (once)

Python 3.12 through [uv](https://docs.astral.sh/uv/), and ffmpeg on your PATH (`brew install ffmpeg` on a Mac):

```bash
uv venv ~/.cache/chordpage/venv -p 3.12
VIRTUAL_ENV=~/.cache/chordpage/venv uv pip install "demucs==4.0.1" "numpy<2" "librosa<0.12" "numba<0.62" soundfile yt-dlp
```

For `--yt`, also install deno (`brew install deno`): yt-dlp uses it for YouTube and warns that working without a
JavaScript runtime is deprecated. demucs pulls in torch (about 1 GB) and takes a few minutes per song on a laptop CPU. Keep demucs at 4.0.1: 4.1 needs
`sphn`, which has no wheel for some Macs and fails to build. Keep numpy below 2: on Macs where torch stops at 2.2, demucs fails with "Numpy is not available". For `--whisper`, also `uv pip install faster-whisper`.

## Run it yourself

The lyrics file has the sung lines in order, repeats written out, one per row, with `[Verse 1]`, `[Chorus]` and so on
starting sections. Take the words from the artist or the video's on-screen lyrics, not auto-captions. The path below is
from a clone of this repo; an installed plugin's copy is under `~/.claude/plugins/cache/chord-page/`.

```bash
~/.cache/chordpage/venv/bin/python skills/chord-page/scripts/chordpage.py song.mp3 \
  --slug my-song --title "My Song" --artist "The Artist" --lyrics lyrics.txt \
  --yt YOUTUBE_VIDEO_ID --out out/my-song
```

Options: `--own` when the song is yours (the footer credits you instead of disclaiming the artist); `--whisper`
instead of `--yt`; `--key Gm` and `--capo 3` to override what it picks; `--released "Oct 2, 2026"`
for the credits; `--no-media` to leave the audio out; `--stems DIR` to reuse a demucs output. Each stage caches in
`~/.cache/chordpage/<slug>/`: delete `bars.json` there to redo the chords, `asr.json` to redo the words. Use a new
folder per song (it refuses one that holds another song).

## Serve it

```bash
npx serve out/my-song
```

Use a server that answers byte-range requests (`npx serve` does; `python -m http.server` doesn't), or the Recording
backing and Vocals can't jump to a line. Any static host works for sharing it (Vercel, Netlify, GitHub Pages).

## Extend it

Everything is plain files: `assets/karaoke.js` (the player, chord shapes and synth), `assets/chordpage.css` (the look;
theme tokens at the top), `template.html` (the page) and `scripts/chordpage.py` (the pipeline; each stage is a
function, described at the top of the file). A new chord type goes in `QUAL` in the script and in `QUAL` and `SHAPES`
in `karaoke.js`.

The skill comes from the [P(doom) songs site](https://music.codercorgi.com), whose chord pages it makes. This repo is
a copy, synced from there with the site's own parts left out, so changes made here directly are overwritten on the
next sync; send them back as an issue or a patch instead.
