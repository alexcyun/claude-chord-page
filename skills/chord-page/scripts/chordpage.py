#!/usr/bin/env python3
# Chord page pipeline (the chord-page skill, see its SKILL.md): turns a song's recording and lyrics into a karaoke chord
# page: chords over every line, a synth and the hosted recording to play along with, the isolated vocals to blend in, and
# a word-by-word highlighter wipe. --out DIR gets a self-contained folder (index.html, karaoke.js, chordpage.css, the
# song's data and media/) that any static server can host.
#
#   python chordpage.py SONG.mp3 --slug my-song --title "My Song" --artist "Someone" --lyrics lyrics.txt --out DIR
#                       [--yt YOUTUBE_ID] [--whisper] [--stems DIR] [--work DIR] [--released "Oct 2, 2026"]
#                       [--permission " (shared with their permission)" | --own] [--key Gm] [--capo N] [--phase N]
#                       [--no-media] [--about "the line under the key"] [--half-time] [--evidence]
#
# Stages, each cached in the work dir (delete a file there to redo that stage):
#   1. stems     demucs htdemucs splits the song into bass, drums, other and vocals (or --stems gives existing ones)
#   2. beats     beats tracked one by one on the drums stem (songs drift in tempo, so no fixed grid), downbeats from where
#                the harmony changes most often
#   3. chords    one chord per half bar from the bass and other stems (chroma against major, minor, 7 and m7b5 templates,
#                a small bonus for chords in the song's key), smoothed with Viterbi so chords change on strong beats
#   4. words     word start times: YouTube's word-timed auto-captions (--yt), faster-whisper on the vocals (--whisper),
#                or both (the captions first, whisper's for what they didn't hear)
#   5. align     the lyrics' words matched to those words (difflib over the whole song); misheard words take the times of
#                what was heard in their place, and words left out go on the sung notes between (stage 6's), a note per
#                syllable, or are spread evenly where there are too few
#   6. melody    the sung notes, tracked on the vocals stem with pyin and cut into notes where the pitch holds steady
#   7. build     index.html, karaoke.js, chordpage.css, karaoke-SLUG.js, bars-SLUG.js, melody-SLUG.js and (unless
#                --no-media) media/SLUG-instrumental.mp3 and media/SLUG-vocals.mp3
# A page that already exists gets its melody with --melody-only: the vocals stem as the input, then only stage 6, the
# melody file and its script tag on the page (its other files are left as they are):
#   python chordpage.py VOCALS.mp3 --melody-only --slug my-song [--out DIR]
# Then it prints a report: words matched, lines that matched poorly, how often the sung melody falls on the chord's notes
# (about 65% is good for a pop song; a single chord held all song scores about 55%, and so does a rap), and the roughest
# stretches. --evidence adds each bar's bass and backing notes, for judging a chord that strays from the song's loop.
#
# Lyrics file: the sung lines in order, repeats written out, one per row; "[Section]" starts a section. Blank rows are
# ignored.
import argparse, bisect, difflib, html, json, re, shutil, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent   # the skill's folder: the template and assets/
NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
def pc(root): return ({"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[root[0]] + root[1:].count("#") - root[1:].count("b")) % 12
def spell(c, key):
    # A chord as song books write it in this key: sharps in G, D, A, E, B and F# major and Em, Bm, F#m, C#m and G#m
    # (C#m's V is G#, not Ab), flats elsewhere. Decoding uses NOTES' names; this is for what the page prints
    sharp = pc(key.rstrip("m")) in ([4, 11, 6, 1, 8] if key.endswith("m") else [7, 2, 9, 4, 11, 6])
    m = re.match(r"([A-G][b#]?)(.*)", c); return (SHARPS if sharp else NOTES)[pc(m[1])] + m[2]
QUAL = {"": ([0, 4, 7], 0), "m": ([0, 3, 7], 0), "7": ([0, 4, 7, 10], .06), "m7b5": ([0, 3, 6, 10], .06)}


def log(*a): print(*a, file=sys.stderr, flush=True)


# ---------- 1. stems ----------
def stems(args, work):
    if args.stems:
        d = Path(args.stems)
    else:
        d = work / "stems"
        if not (d / "vocals.wav").exists():
            log("stems: running demucs (a few minutes on a laptop CPU)…")
            subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "-o", str(work / "demucs"), str(args.mp3)], check=True)
            src = next((work / "demucs" / "htdemucs").iterdir())
            d.mkdir(exist_ok=True)
            for f in src.iterdir(): f.rename(d / f.name)
    for n in ["bass", "drums", "other", "vocals"]:
        if not (d / f"{n}.wav").exists(): sys.exit(f"stems: no {n}.wav in {d}")
    return d


# ---------- 2. beats ----------
def beats(st, work):
    f = work / "beats.json"
    if f.exists(): return json.loads(f.read_text())
    import numpy as np, librosa
    sr, hop = 22050, 128
    dr, _ = librosa.load(st / "drums.wav", sr=sr)
    env = librosa.onset.onset_strength(y=dr, sr=sr, hop_length=hop)
    guess = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=env, sr=sr, hop_length=hop))[0])
    _, b = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop, start_bpm=guess, tightness=400, units="time", trim=False)
    d = np.diff(b)
    out = {"beats": [round(float(x), 3) for x in b], "bpm": [round(60 / float(np.percentile(d, 90)), 1), round(60 / float(np.median(d)), 1), round(60 / float(np.percentile(d, 10)), 1)]}
    f.write_text(json.dumps(out)); return out


# ---------- 3. chords ----------
def in_key(key):
    # Chords that belong (diatonic, plus the major V and V7 of a minor key), which get a small bonus
    r = pc(key.rstrip("m")); n = lambda i: NOTES[(r + i) % 12]
    if key.endswith("m"):
        return {n(0) + "m", n(5) + "m", n(7) + "m", n(7), n(7) + "7", n(3), n(8), n(10), n(2) + "m7b5", n(2) + "m"}
    return {n(0), n(2) + "m", n(4) + "m", n(5), n(7), n(7) + "7", n(9) + "m", n(11) + "m7b5", n(2) + "7", n(4) + "7"}


def chords(st, work, bt, forced_key=None, forced_phase=None):
    f = work / "bars.json"
    if f.exists():
        cached = json.loads(f.read_text())   # a different --key or --phase decodes again, as does a cache from before phases
        if "phase" in cached and (not forced_key or cached["key"] == forced_key) and (forced_phase is None or cached["phase"] == forced_phase):
            return cached
    import numpy as np, librosa
    sr, hop = 22050, 512
    b = np.array(bt["beats"])
    oth, _ = librosa.load(st / "other.wav", sr=sr); bas, _ = librosa.load(st / "bass.wav", sr=sr)
    Co = librosa.feature.chroma_cqt(y=oth, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C3"), n_octaves=4)
    Cb = librosa.feature.chroma_cqt(y=bas, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=3)
    fr = librosa.time_to_frames(b, sr=sr, hop_length=hop); fr = np.append(fr, fr[-1] + int(np.median(np.diff(fr))))
    sync = lambda C: np.array([C[:, fr[i]:max(fr[i] + 1, fr[i + 1])].mean(1) for i in range(len(b))])
    O, B = sync(Co), sync(Cb)
    On = O / (np.linalg.norm(O, axis=1, keepdims=True) + 1e-9); Bn = B / (B.sum(1, keepdims=True) + 1e-9)
    # Downbeats: the beat (mod 4) where the harmony changes most
    nov = np.r_[0, np.linalg.norm(np.diff(np.c_[On, Bn], axis=0), axis=1)]
    phase = int(np.argmax([nov[k::4].mean() for k in range(4)]))
    # The bass alone, as a check: a bass that changes most on another beat can mean that guess is a beat off (Perduta's
    # song: harmony and bass together picked the beat after the bass's changes, so every chord came a beat late). Only a
    # check, not the choice: there the bass won by 8%, too close to trust on its own, and decoding the chords on each grid
    # and scoring them against the bass or counting bass note changes didn't separate the two beats either. The melody did
    # (the report's grid check), but it can't choose alone: the OG P(doom) song's melody leads each change by three beats
    nb = np.r_[0, np.linalg.norm(np.diff(Bn, axis=0), axis=1)]
    bn = [float(nb[k::4].mean()) for k in range(4)]
    if forced_phase is not None: phase = forced_phase % 4
    bass_phase = int(np.argmax(bn)); bass_margin = round(bn[bass_phase] / max(1e-9, bn[phase]) - 1, 2)   # over the downbeats used
    LB, T, R, P0 = [], [], [], []
    for r in range(12):
        for q, (iv, p) in QUAL.items():
            v = np.zeros(12); v[[(r + k) % 12 for k in iv]] = 1
            T.append(v / np.linalg.norm(v)); LB.append(NOTES[r] + q); R.append(r); P0.append(p)
    T, R, P0 = np.array(T), np.array(R), np.array(P0)
    cost = np.roll(np.array([0.05, 0.8, 0.3, 0.8]), phase)   # changing chord is cheapest on a downbeat, then mid-bar
    def decode(P):
        Sc = On @ T.T + 0.9 * Bn[:, R] - P
        n, K = Sc.shape
        d = Sc[0].copy(); bp = np.zeros((n, K), int)
        for i in range(1, n):
            c = cost[i % 4]; cand = d[:, None] - c * (1 - np.eye(K)); bp[i] = cand.argmax(0); d = cand.max(0) + Sc[i]
        p = [int(d.argmax())]
        for i in range(n - 1, 0, -1): p.append(int(bp[i][p[-1]]))
        return [LB[k] for k in p[::-1]]
    # The key: decode once with no preference, then pick the key whose chords cover the most beats, with extra weight on
    # its home chord and on the final chord (averaged pitches mislead: a minor song's V chord and melody can outweigh i)
    ch = decode(P0)
    def fit(k): return sum(c in in_key(k) for c in ch) + 0.5 * sum(c == k for c in ch) + 8 * (ch[-1] == k)
    key = forced_key or max([n + q for n in NOTES for q in ("", "m")], key=fit)
    ch = decode(P0 - np.array([.04 if l in in_key(key) else 0 for l in LB]))
    n = len(ch)
    bars = []
    for s in range(phase, n, 4):
        h1 = ch[s]; h2 = ch[s + 2] if s + 2 < n else h1
        bars.append([round(float(b[s]), 2), h1] + ([h2] if h2 != h1 else []))
    if phase:   # beats before the first downbeat: a pickup bar of their own, a full bar long, since the player times its
        # count-in by the bar's length (a 0.5 s bar gave four clicks in 0.5 s); one the song's start would cut under half a
        # bar is left out, and the count-in uses the first full bar
        bar = float(b[phase + 4] - b[phase]) if phase + 4 < n else 4 * float(np.median(np.diff(b)))
        if b[phase] - bar > -bar / 2: bars.insert(0, [round(max(0.0, float(b[phase]) - bar), 2), ch[0]])
    end = round(float(b[-1] + np.median(np.diff(b))), 2)
    out = {"key": key, "bars": bars, "end": end, "phase": phase, "bass_phase": bass_phase, "bass_margin": bass_margin}
    f.write_text(json.dumps(out)); return out


def evidence(st, ch):
    # --evidence: what each bar's chord was read from, a row per bar: the decoded chord, then for each half bar the bass
    # stem's strongest note (in brackets when the bass is nearly silent there) and the backing's three strongest. Use it
    # to judge a stray chord before changing it in bars.json: a bar whose notes are a cluster (C, C#, D) is a riser or
    # an effect, not a chord, and a major third over a power chord (G# over E and B) is its overtone, not E major
    import numpy as np, librosa
    sr, hop = 22050, 512
    oth, _ = librosa.load(st / "other.wav", sr=sr); bas, _ = librosa.load(st / "bass.wav", sr=sr)
    Co = librosa.feature.chroma_cqt(y=oth, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C3"), n_octaves=4)
    Cb = librosa.feature.chroma_cqt(y=bas, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("C1"), n_octaves=3)
    rb = librosa.feature.rms(y=bas, hop_length=hop)[0]; quiet = 0.15 * np.percentile(rb, 95)
    bars = ch["bars"]
    log("\nbar   time  chord        bass  backing      | bass  backing")
    for i, b in enumerate(bars):
        t0, t1 = b[0], bars[i + 1][0] if i + 1 < len(bars) else ch["end"]; cells = []
        for a, z in ((t0, (t0 + t1) / 2), ((t0 + t1) / 2, t1)):
            f = librosa.time_to_frames([a, z], sr=sr, hop_length=hop); f[1] = max(f[0] + 1, f[1])
            n = NOTES[int(Cb[:, f[0]:f[1]].mean(1).argmax())]
            n = f"({n})" if rb[f[0]:f[1]].mean() < quiet else f" {n} "
            cells.append(f"{n:5} {' '.join(NOTES[k] for k in np.argsort(Co[:, f[0]:f[1]].mean(1))[::-1][:3]):12}")
        log(f"{i:3} {t0:6.1f}  {b[1] + ('/' + b[2] if len(b) > 2 else ''):12} {cells[0]} | {cells[1]}")


# ---------- 4. words ----------
def words(args, st, work):
    # One transcript, or two when both --yt and --whisper are given: the captions first, then whisper's, which align()
    # uses for the words the captions didn't hear (captions often drop a shouted or doubled chorus line whole). Each has
    # its own cache, asr.json for the captions and asr-whisper.json for whisper, so a later run with other flags never
    # reads one as the other; with neither flag, whichever are cached are used
    yt, wh = args.yt or (not args.whisper and (work / "asr.json").exists()), args.whisper or (not args.yt and (work / "asr-whisper.json").exists())
    if not (yt or wh): sys.exit("words: pass --yt YOUTUBE_ID (word-timed auto-captions), --whisper (needs faster-whisper), or both")
    got = []
    if yt: got.append(transcript(args, st, work / "asr.json", "yt"))
    if wh: got.append(joined(transcript(args, st, work / "asr-whisper.json", "whisper")))
    return got


def transcript(args, st, f, kind):
    if f.exists(): return json.loads(f.read_text())
    out, work = [], f.parent
    if kind == "yt":
        if not args.yt: sys.exit("words: no cached captions; pass --yt YOUTUBE_ID")
        subprocess.run([sys.executable, "-m", "yt_dlp", "--skip-download", "--write-auto-subs", "--sub-langs", "en", "--sub-format", "json3",
                        "-o", str(work / "yt"), f"https://www.youtube.com/watch?v={args.yt}"], check=True)
        got = sorted(work.glob("yt.*.json3"))   # named by the track found: en, en-US, en-orig, …
        if not got: sys.exit("words: YouTube has no English auto-captions for this video; try --whisper")
        d = json.loads(got[0].read_text())
        for e in d["events"]:
            for s in e.get("segs", []):
                w = s["utf8"].strip()
                if w and not w.startswith("["): out.append([round((e["tStartMs"] + s.get("tOffsetMs", 0)) / 1000, 2), w])
    else:
        from faster_whisper import WhisperModel
        import librosa
        log("words: transcribing the vocals with faster-whisper (the first run downloads its model)…")
        v, _ = librosa.load(st / "vocals.wav", sr=16000)   # as samples, not a path: its own file reading breaks with newer PyAV
        segs, _ = WhisperModel(args.whisper_model, compute_type="int8").transcribe(v, word_timestamps=True, language="en")
        for s in segs:
            for w in s.words or []: out.append([round(w.start, 2), w.word.strip()])
    f.write_text(json.dumps(out)); return out


def joined(asr):
    # For whisper's transcript only (a caption's leading dash is a speaker change, not a word piece). Whisper splits some
    # sung words into pieces, the later ones starting with a hyphen ("pee", "-dum" for "P(doom)"): one word to the lyrics,
    # so join them, or each piece takes a lyric word and every word after slips by one
    out = []
    for t, w in asr:
        if out and w.startswith("-") and len(w) > 1: out[-1] = [out[-1][0], out[-1][1] + w[1:]]
        else: out.append([t, w])
    return out


# ---------- 5. align ----------
def read_lyrics(path):
    secs = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line: continue
        m = re.fullmatch(r"\[([^\]|]+?)\s*(?:\|\s*([\w-]+))?\s*\]", line)
        if m:
            secs.append({"sec": m[1].strip(), "lines": []})
            continue
        if not secs: secs.append({"sec": "Verse", "lines": []})
        secs[-1]["lines"].append(line)
    return secs


def norm(w): return re.sub(r"[^a-z0-9]", "", w.lower().replace("’", "'"))


def align(secs, asr, more=None):
    # the transcript's [music] and [applause] aren't words, nor are its speaker marks (">>") and note signs
    heard = lambda tr: [a for a in tr if norm(a[1]) and not re.search(r"\[\w+\]", a[1])]
    flat = [(si, li, m.start(), m.group()) for si, s in enumerate(secs) for li, l in enumerate(s["lines"]) for m in re.finditer(r"\S+", l)]
    # A dash or other mark standing alone ("ten years – all by itself") is drawn with the words but isn't one: it's left
    # out of the matching and the counts, and sits between the words around it
    real = [i for i, f in enumerate(flat) if norm(f[3])]
    times, exact = [None] * len(flat), set()
    def shares(ws, count=syllables):
        n = [count(w) for w in ws]; tot = sum(n); return [sum(n[:k]) / tot for k in range(len(n))]
    def between(i, t):   # only a time that falls between those already known on either side
        lo = max((times[j] for j in range(i) if times[j] is not None), default=-1e9)
        hi = min((times[j] for j in range(i + 1, len(times)) if times[j] is not None), default=1e9)
        return lo < t < hi
    # Each transcript in turn (the captions, then whisper's if both were given) times the words still without a time:
    # first the words it heard right, then the ones it misheard ("up in my bedroom" for "upping my P(doom)"), which
    # still have the misheard words' times: a run of lyrics between matches takes the times of the transcript's words
    # in its place, by syllable position (each lyric word takes the heard word starting nearest the same share of the
    # run's syllables; a second lyric word landing on the same heard word, like "thousand" on "100,000", is left for
    # the sung notes). So a line the captions dropped whole (a shouted chorus hook) comes from the second transcript
    # captions shout some lines in capitals ("THE SPOKE COMPUTES"), which syllables() would spell out letter by letter
    said = lambda w: syllables(w.lower() if w.isupper() and re.search(r"[AEIOUY]", w) else w)
    for tr in [heard(asr)] + ([heard(more)] if more else []):
        sm = difflib.SequenceMatcher(None, [norm(flat[i][3]) for i in real], [norm(w) for _, w in tr], autojunk=False)
        for a, b, n in sm.get_matching_blocks():
            for k in range(n):
                i = real[a + k]
                if times[i] is None and between(i, tr[b + k][0]): times[i] = tr[b + k][0]; exact.add(i)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "replace": continue
            # only where about as much was heard as is sung: a few heard words standing in for two lines ("you bottomed
            # out on a" for a chorus hook and the start of the next line) would squeeze them all into one moment
            if not 0.6 <= sum(said(w) for _, w in tr[j1:j2]) / sum(syllables(flat[i][3]) for i in real[i1:i2]) <= 1 / 0.6: continue
            got = shares([w for _, w in tr[j1:j2]], said); used = set()
            for k, f in zip(real[i1:i2], shares([flat[i][3] for i in real[i1:i2]])):
                h = min(range(len(got)), key=lambda x: abs(got[x] - f))
                if h not in used and times[k] is None and between(k, tr[j1 + h][0]): times[k] = tr[j1 + h][0]; used.add(h)
    matched = len(exact)
    timed = [t is not None for t in times]
    # Words the transcript left out: spread between the nearest timed words on either side, by word count (snap() later
    # moves them onto the sung notes where it can)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known: sys.exit("align: no lyric words matched the transcript; check the lyrics or the transcript source")
    for i in range(len(times)):
        if times[i] is None:
            lo = max([k for k in known if k < i], default=None); hi = min([k for k in known if k > i], default=None)
            if lo is None: times[i] = max(0.05 * (i + 1), times[hi] - 0.3 * (hi - i))
            elif hi is None: times[i] = times[lo] + 0.3 * (i - lo)
            else: times[i] = times[lo] + (times[hi] - times[lo]) * (i - lo) / (hi - lo)
    for i in range(1, len(times)): times[i] = max(times[i], times[i - 1] + 0.05)
    per, hits, kset = {}, {}, {}
    for i, ((si, li, at, w), t) in enumerate(zip(flat, times)):
        per.setdefault((si, li), []).append((at, w, t))      # (character index, word, start time) per word
        if norm(w): hits.setdefault((si, li), []).append(i in exact)   # whether each word matched the transcript
        kset.setdefault((si, li), []).append(timed[i] or not norm(w))  # whether the transcript timed it (matched or misheard)
    return per, hits, matched, len(real), kset


def syllables(w):
    # A rough count, for placing words on sung notes: a capital not starting a word ("AGI", the "GPT" of "ChatGPT", the
    # "P" of "P(doom)") is a letter of its own, as is each letter of a word with no vowels ("cdr"), a number is one or
    # two, and the rest one per group of vowels (a silent final e doesn't count)
    w = re.sub(r"['’][a-z]+", "", w)   # a contraction's tail ('ll, 'm, 's) adds none
    n, rest = 0, w
    for m in re.findall(r"[A-Z]+(?![a-z])", w): n += len(m)
    rest = re.sub(r"[A-Z]+(?![a-z])", " ", w)
    n += sum(1 if len(d) == 1 else 2 for d in re.findall(r"\d+", rest))
    for part in re.findall(r"[A-Za-z]+", rest):
        p = part.lower(); v = len(re.findall(r"[aeiouy]+", p)) or len(p)   # no vowels ("cdr"): spelled out
        if v > 1 and p.endswith("e") and not p.endswith("le"): v -= 1
        n += v
    return max(1, n)


def snap(per, timed, mel):
    # Words the transcript left out were spread evenly between the timed words around them, which goes wrong when the
    # singer stretches a word or the next timed word is lines away. Put them on the sung notes instead: each takes as many
    # note starts as it has syllables, after the notes of the word before them (counted from the note nearest its time,
    # since a transcript runs a little early or late), and all must fit before the next timed word. Notes under 0.12 s are
    # slides between notes, not syllables. A run with too few notes keeps its even spread. Returns how many words moved
    keys = sorted(per); words = [(k, j) for k in keys for j in range(len(per[k]))]
    ok = [timed[k][j] for k, j in words]; t = [per[k][j][2] for k, j in words]
    starts = [s for s, d, _ in mel if d >= 0.12]; moved = 0
    i = 0
    while i < len(words):
        if ok[i]: i += 1; continue
        e = i
        while e < len(words) and not ok[e]: e += 1
        if i > 0 and e < len(words):
            a, b = t[i - 1], t[e]
            prev = syllables(per[words[i - 1][0]][words[i - 1][1]][1])
            near = [x for x, s in enumerate(starts) if abs(s - a) <= 0.25 and s < b - 0.1]
            if near: j = min(near, key=lambda x: abs(starts[x] - a)); on = [s for s in starts[j + prev:] if s < b - 0.1]
            else: on = [s for s in starts if a + 0.1 < s < b - 0.1][prev - 1:]
            need = [syllables(per[k][j][1]) for k, j in words[i:e]]
            if len(on) >= sum(need):
                pos = 0
                for n, x in zip(need, range(i, e)): t[x] = on[pos]; pos += n
                moved += e - i
        i = e
    for x, (k, j) in enumerate(words):   # a mark standing alone goes just before the word after it
        if not norm(per[k][j][1]) and 0 < x < len(words) - 1: t[x] = max(t[x - 1] + 0.05, t[x + 1] - 0.05)
    for x, (k, j) in enumerate(words):
        at, w, _ = per[k][j]; per[k][j] = (at, w, round(t[x], 2))
    return moved


# ---------- 6. melody ----------
def melody(vocals, work):
    # The sung notes as [start, seconds, MIDI note]. pyin tracks the pitch every 10 ms; its voicing probability runs low
    # on processed vocals (reverb, doubled takes), so frames count as sung by its voiced flag and loudness instead. A note
    # runs while the pitch stays within 0.6 semitones of the note so far (vibrato stays inside it) and ends where it
    # leaves for 40 ms or the singing stops; shorter than 70 ms is a slide or a consonant, not a note. Same notes across a
    # tiny gap join, a note under 0.1 s touching a longer one is the slide into or out of it and joins it, and a note about
    # an octave (10 semitones or more) away from its neighbors is a tracking slip, moved back; a real leap of a sixth stays.
    # The pitch track is cached (pitch.npz, with the file it came from: a different or changed vocals file tracks again),
    # so changing how notes are cut reruns in a second
    import numpy as np
    f, st = work / "pitch.npz", Path(vocals).stat()
    source = f"{Path(vocals).resolve()}|{st.st_size}|{int(st.st_mtime)}"
    cached = np.load(f) if f.exists() else None
    if cached is not None and "source" in cached and str(cached["source"]) == source: m = cached["midi"]
    else:
        import librosa
        log("melody: tracking the sung pitch (a minute or two)…")
        v, _ = librosa.load(vocals, sr=16000)
        f0, vf, _ = librosa.pyin(v, fmin=70, fmax=1000, sr=16000, hop_length=160, frame_length=2048)
        rms = librosa.feature.rms(y=v, frame_length=2048, hop_length=160)[0][:len(f0)]
        ok = vf & (rms > 0.1 * np.percentile(rms, 95))
        m = np.full(len(f0), np.nan); m[ok] = librosa.hz_to_midi(f0[ok])
        np.savez_compressed(f, midi=m, source=source)
    s, tol, need, shortest = 0.01, 0.6, 4, 7   # 10 ms frames
    ok = ~np.isnan(m); sm = m.copy()
    for i in np.flatnonzero(ok): sm[i] = np.nanmedian(m[max(0, i - 2):i + 3])
    raw, cur, dev = [], None, 0
    def close(end):
        if cur and end - cur[0] >= shortest: raw.append([cur[0], end, float(np.median(cur[1]))])
    for i in range(len(sm)):
        if not ok[i]:
            close(i); cur, dev = None, 0; continue
        if cur is None: cur, dev = [i, [sm[i]]], 0; continue
        if abs(sm[i] - np.median(cur[1][-20:])) > tol:
            dev += 1
            if dev >= need: close(i - dev + 1); cur, dev = [i - dev + 1, list(sm[i - dev + 1:i + 1])], 0
        else: dev = 0; cur[1].append(sm[i])
    close(len(sm))
    notes = []
    for a, b, p in raw:
        n = [a * s, (b - a) * s, int(round(p))]
        if notes and notes[-1][2] == n[2] and n[0] - sum(notes[-1][:2]) <= 0.06: notes[-1][1] = sum(n[:2]) - notes[-1][0]
        else: notes.append(n)
    touch = lambda x, y: abs(y[0] - sum(x[:2])) <= 0.05   # x ends where y starts
    i = 0
    while i < len(notes):
        n, prev, nxt = notes[i], notes[i - 1] if i else None, notes[i + 1] if i + 1 < len(notes) else None
        into = [x for x in (prev, nxt) if x and x[1] > n[1] and (touch(x, n) if x is prev else touch(n, x))]
        if n[1] < 0.1 and into:
            x = max(into, key=lambda x: x[1])
            if x is prev: x[1] = sum(n[:2]) - x[0]
            else: x[1] = sum(x[:2]) - n[0]; x[0] = n[0]
            notes.pop(i)
        else: i += 1
    P = [n[2] for n in notes]
    for i, n in enumerate(notes):
        near = P[max(0, i - 4):i] + P[i + 1:i + 5]
        if len(near) >= 3:
            mid = float(np.median(near))
            while n[2] - mid >= 10: n[2] -= 12
            while mid - n[2] >= 10: n[2] += 12
    return [[round(a, 2), round(d, 2), p] for a, d, p in notes]


def melody_js(notes, K, title, page_name):
    # The notes sung during a line (from just before its first word to its end; ad-libs between lines and stem bleed in
    # the instrumentals are left out), with the range the contour is drawn across: most of the notes, not the odd outlier
    spans = [(l[3][0] - 0.25, l[3][-1]) for s in K for l in s["lines"] if len(l) > 3 and l[3]]
    keep = [n for n in notes if any(a <= n[0] < b for a, b in spans)]
    P = sorted(n[2] for n in keep) or [60]
    lo, hi = P[len(P) * 3 // 100], P[min(len(P) - 1, len(P) * 97 // 100)]
    if hi - lo < 7: lo, hi = (lo + hi) // 2 - 4, (lo + hi) // 2 + 4
    sung = sum(b - a for a, b in spans) or 1
    covered = sum(min(n[1], b - n[0]) for n in keep for a, b in spans if a <= n[0] < b)
    js = (f"// The sung melody of “{title}” ({page_name}), drawn by karaoke.js as a contour over the words: one\n"
          f"// [song seconds, seconds, MIDI note] per note, tracked on the vocals stem by the chord-page skill (pyin), not\n"
          f"// transcribed by ear.\n"
          f"// lo and hi are the range the contour spans; notes past them sit at its edge.\n"
          f"window.MELODY = {{lo:{lo}, hi:{hi}, notes:[{','.join(json.dumps(n, separators=(',', ':')) for n in keep)}]}};\n")
    return js, {"notes": len(keep), "lo": lo, "hi": hi, "covered": covered / sung}


def note_name(m): return f"{NOTES[m % 12]}{m // 12 - 1}"


# ---------- 7. build ----------
def place(text, ws, end, changes, chord_at):
    # Chords over a line: the chord sounding when it starts (or one changing in its first 0.8 s) on its first word, then
    # each change over the word being sung when it happens; a change during the held last note goes past the words
    start = ws[0][2]
    inside = [(s, c) for s, c in changes if start < s < end - 0.3]
    out = []
    if inside and inside[0][0] - start <= 0.8:
        s0, c0 = inside.pop(0); out.append([0, c0, round(s0, 2)])
    else:
        out.append([0, chord_at(start + 0.05), round(start, 2)])
    last_start = ws[-1][2]
    for s, c in inside:
        if c == out[-1][1]: continue
        k = max(i for i, (_, _, t) in enumerate(ws) if t <= s + 0.15) if any(t <= s + 0.15 for *_, t in ws) else 0
        if k == len(ws) - 1 and s - last_start > 0.6: at = max(len(text) + 2, out[-1][0] + len(out[-1][1]) + 2)
        else:
            at = ws[k][0]
            if at <= out[-1][0]:
                nxt = [w[0] for w in ws if w[0] > out[-1][0] + len(out[-1][1])]
                at = nxt[0] if nxt else max(len(text) + 2, out[-1][0] + len(out[-1][1]) + 2)
        out.append([at, c, round(s, 2)])
    return out


def easy_capo(chord_list):
    # The capo fret (0 to 7) that turns the most playing time into open shapes a beginner knows
    OPEN = {"C", "D", "Dm", "E", "Em", "G", "A", "Am", "C7", "D7", "E7", "G7", "A7", "B7", "Am7b5", "Em7b5", "Dm7b5", "F"}
    def shift(c, k):
        m = re.match(r"([A-G][b#]?)(.*)", c); return NOTES[(pc(m[1]) - k) % 12] + m[2]
    score = [(sum(shift(c, k) in OPEN for c in chord_list) - (0.5 if k else 0), -k) for k in range(8)]
    return -max(score)[1]


def common_loop(bars, starts):
    # The most frequent run of four chords starting where a sung line does (so it reads as a phrase, not a slice across
    # two), for the line under the key. A chord held for several bars counts once, so a song that changes every two
    # bars reads "Eb, Bb, Cm, Ab", not "Eb, Bb, Bb, Cm". A line belongs to the bar line nearest its start, so one sung on a
    # pickup counts from the bar it leads into (Perduta's pickups gave "G#, C#m, A, E" for its C#m, A, E, G# loop)
    seq, runs = [b[1] for b in bars], {}
    first = sorted({min(range(len(bars)), key=lambda i: abs(bars[i][0] - t)) for t in starts})
    for i in first:
        r = []
        for c in seq[i:]:
            if len(r) == 4: break
            if not r or c != r[-1]: r.append(c)
        r = tuple(r)
        if len(r) == 4 and len(set(r)) > 1: runs[r] = runs.get(r, 0) + 1
    if not runs: return ""
    r, n = max(runs.items(), key=lambda x: x[1])
    return f"The most common run of chords: {', '.join(r)}." if n >= 3 else ""


# Blocks between marker lines, each marker alone on its line in the file's own comment syntax: drop() takes a block out,
# unwrap() keeps it and takes out just its markers
MARKS = {".html": "<!-- {} -->", ".md": "<!-- {} -->", ".js": "// <{}>", ".css": "/* <{}> */", ".py": "# <{}>", ".swift": "// <{}>"}
def _line(kind, name): return rf"^[ \t]*{re.escape(MARKS[kind].format(name))}[ \t]*\n"
def drop(text, kind, name):
    # Markers must alternate open, close: an unclosed block would swallow shared code up to the next block's close
    o, c = _line(kind, name), _line(kind, "/" + name)
    closes = [bool(re.fullmatch(c, m, flags=re.M)) for m in re.findall(f"{o}|{c}", text, flags=re.M)]
    if closes != [False, True] * (len(closes) // 2) or len(closes) % 2: sys.exit(f"cut: unbalanced {name} markers in a {kind} file")
    # A block between blank lines takes one of them with it
    return re.sub(rf"(?<=\n\n){o}[\s\S]*?{c}\n|{o}[\s\S]*?{c}", "", text, flags=re.M)
def unwrap(text, kind, name):
    return re.sub(f"(?:{_line(kind, name)}|{_line(kind, '/' + name)})", "", text, flags=re.M)
def cut(text, kind):
    # A file as a page folder of its own gets it: any site blocks dropped
    text = unwrap(drop(text, kind, "site"), kind, "standalone")
    return text
def cut_template(mode):
    # One template for both modes: keep this mode's blocks (site or standalone) and drop the other's
    tpl = (SKILL / "template.html").read_text()
    if mode == "standalone": return cut(tpl, ".html")
    return unwrap(drop(tpl, ".html", "standalone"), ".html", "site")


def build(args, st, bt, ch, secs, per, hits, mel):
    dest = args.out
    slug = args.slug; dest.mkdir(parents=True, exist_ok=True)
    k = args.key or ch["key"]; key = spell(k, k)
    bars, end = [[b[0]] + [spell(c, key) for c in b[1:]] for b in ch["bars"]], ch["end"]
    beats = bt["beats"]
    ev = []
    for i, b in enumerate(bars):
        t0, t1 = b[0], (bars[i + 1][0] if i + 1 < len(bars) else end)
        for t, c in [(t0, b[1])] + ([((t0 + t1) / 2, b[2])] if len(b) > 2 else []):
            if not ev or ev[-1][1] != c: ev.append((round(t, 2), c))
    chord_at = lambda t: [c for s, c in ev if s <= t + 1e-6][-1] if any(s <= t for s, _ in ev) else ev[0][1]
    def bar_len(t):   # four beats' length where t falls
        i = min(max(bisect.bisect(beats, t) - 1, 0), len(beats) - 2); return 4 * (beats[i + 1] - beats[i])
    def instr(a, z):
        seg = [(max(s, a), c) for s, c in ev if s < z - 0.3 and (s >= a or s == max([x for x, _ in ev if x <= a], default=s))]
        out, col = [], 0
        for s, c in seg: out.append([col, c, round(s, 2)]); col += len(c) + 3
        return out
    # Every line's word times and end
    flat = []
    for si, s in enumerate(secs):
        for li, text in enumerate(s["lines"]):
            ws = per[(si, li)]
            flat.append((si, li, text, ws))
    K = []
    if flat and flat[0][3][0][2] - (bars[0][0]) >= 3 * bar_len(bars[0][0]):
        K.append({"sec": "Intro", "lines": [["", instr(bars[0][0], flat[0][3][0][2] - 0.3), bars[0][0], None]]})
    for n, (si, li, text, ws) in enumerate(flat):
        nxt = flat[n + 1][3][0][2] if n + 1 < len(flat) else end
        last = ws[-1][2]; bl = bar_len(last)
        line_end = min(nxt, last + min(3, max(0.4, nxt - last - 0.1)))
        chords = place(text, ws, line_end, ev, chord_at)
        if li == 0:
            K.append({"sec": secs[si]["sec"], "lines": []})
        # a short gap (a held note, a breath): its changes go on the end of the line's chord row, past the words
        if nxt - line_end < 3 * bl:
            col = max(len(text) + 2, chords[-1][0] + len(chords[-1][1]) + 2)
            for s, c in ev:
                if line_end - 0.3 <= s < nxt - 0.3 and c != chords[-1][1]: chords.append([col, c, round(s, 2)]); col += len(c) + 2
        K[-1]["lines"].append([text, chords, round(ws[0][2], 2), [round(t, 2) for *_, t in ws] + [round(max(line_end, last + 0.25), 2)]])
        if nxt - line_end >= 3 * bl:
            K.append({"sec": "Outro" if n + 1 == len(flat) else "Instrumental", "lines": [["", instr(line_end, nxt), round(line_end, 2), None]]})
            if n + 1 < len(flat) and flat[n + 1][1] != 0:   # the section carries on after the break
                K.append({"sec": secs[flat[n + 1][0]]["sec"] + " (cont.)", "lines": []})
    for s in K:
        for l in s["lines"]:
            if l[3] is None: l.pop()
    capo = args.capo if args.capo is not None else easy_capo([b[1] for b in bars])
    media = {"instrumental": "", "vocals": ""}
    if not args.no_media:
        (dest / "media").mkdir(exist_ok=True)
        media = {"instrumental": f"media/{slug}-instrumental.mp3", "vocals": f"media/{slug}-vocals.mp3"}
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st / "bass.wav"), "-i", str(st / "drums.wav"), "-i", str(st / "other.wav"),
                        "-filter_complex", "amix=inputs=3:normalize=0,alimiter=limit=0.95", "-b:a", "160k",
                        "-metadata", f"title={args.title} (instrumental)", "-metadata", f"artist={args.artist}", str(dest / media["instrumental"])], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st / "vocals.wav"), "-af", "alimiter=limit=0.95", "-b:a", "128k",
                        "-metadata", f"title={args.title} (vocals)", "-metadata", f"artist={args.artist}", str(dest / media["vocals"])], check=True)
    song = {"key": key, "capo": capo, "about": args.about if args.about is not None else common_loop(bars, [ws[0][2] for *_, ws in flat]), **media}
    page_name, used_by = "index.html", "Used by karaoke.js"
    js = (f"// Karaoke chords for “{args.title}” ({page_name}, drawn by karaoke.js), made by the chord-page skill from\n"
          f"// the recording: chords read from its stems on a tracked beat grid, line and word times from the transcript\n"
          f"// matched to the lyrics. See karaoke.js for the shapes of KARAOKE_SONG and KARAOKE.\n"
          f"window.KARAOKE_SONG = {json.dumps(song, ensure_ascii=False)};\nwindow.KARAOKE = [\n" +
          ",\n".join(json.dumps(s, ensure_ascii=False, separators=(", ", ": ")) for s in K) + "\n];\n")
    (dest / f"karaoke-{slug}.js").write_text(js)
    mjs, mstat = melody_js(mel, K, args.title, page_name)
    (dest / f"melody-{slug}.js").write_text(mjs)
    lo, mid, hi = bt["bpm"]
    (dest / f"bars-{slug}.js").write_text(
        f"// Bars for “{args.title}”: one [song seconds, chord, second-half chord?] per bar, read from the recording by the\n"
        f"// chord-page skill (about {mid:.0f} BPM). {used_by}.\n"
        f"window.BARS = {{bpm:{mid:.0f}, end:{end}, bars:[{','.join(json.dumps(b, separators=(', ', ':')) for b in bars)}]}};\n")
    key_name = re.sub(r"^([A-G][b#]?)(m?)$", lambda m: m[1] + (" minor" if m[2] else " major"), key)
    tempo = f"About {mid:.0f} BPM" + (f" (it drifts from {lo:.0f} to {hi:.0f})" if hi - lo >= 2 else "") + ", 4/4"
    felt = mid
    if args.half_time:   # the beat tracker counted twice as fast as the song is felt: say so, and keep its finer grid
        felt = mid / 2; tempo = f"About {felt:.0f} BPM, 4/4 (the chords are counted in double time, {mid:.0f})"
    not_ours, permission, mode = "Not", args.permission, "standalone"
    fill = {"TITLE": args.title, "ARTIST": args.artist, "SLUG": slug, "KEY_NAME": key_name, "BACK_LINK": "",
            "TEMPO": tempo, "TEMPO_SHORT": f"about {felt:.0f} BPM", "RELEASED": f", {args.released}" if args.released else "",
            "CREDIT": f"Song, recording and lyrics by {args.artist}." if args.own else
                not_ours + f" affiliated with {args.artist}. The song, its recording and its "
                "lyrics belong to their creator" + (permission if permission is not None else
                (" (the lyrics are shared with their permission)" if args.no_media else " (the recording, vocals and lyrics are shared with their permission)")) + ".",
            "METHOD": ("How these were made: the recording was split into stems to set the vocals and drums aside, and its beats were "
                       "tracked one by one, since songs drift in tempo. Each half bar of the bass and backing was matched to the closest "
                       "chord, and the lyrics were matched word by word to a transcript, so every chord sits over the word being sung when "
                       "it changes. It’s a close reading of the recording, not the artist’s own chart, so trust your ear where they disagree. "
                       "Play plays these chords on the song’s own timing: Synth is a simple keyboard and bass in whatever key the sheet is in"
                       + ("." if args.no_media else "; Recording is the song with its vocals taken out. Vocals start turned up, so you "
                          "sing along with the original singer; turn them down to sing it yourself."))}
    tpl = cut_template(mode)
    if args.out:
        # A folder of its own, with the skill's copies of the player and its styles
        for f in ["karaoke.js", "chordpage.css"]: (dest / f).write_text(cut((SKILL / "assets" / f).read_text(), Path(f).suffix))
    # Everything from the command line is escaped; the tabs, the back link and the script tags are HTML on purpose
    raw = {"TOPNAV", "BACK_LINK", "NOTES_SCRIPTS"}
    page = re.sub(r"\{\{(\w+)\}\}", lambda m: fill[m[1]] if m[1] in raw else html.escape(fill[m[1]]), tpl)
    (dest / page_name).write_text(page)
    return K, capo, key, mstat



# ---------- report ----------
def report(st, ch, K, matched, total, hits, secs, mstat):
    import numpy as np, librosa
    log(f"\nwords matched to the transcript: {matched}/{total} ({100 * matched / max(1, total):.0f}%)")
    weak = [(secs[si]["sec"], secs[si]["lines"][li]) for (si, li), h in hits.items() if sum(h) / len(h) < 0.6]
    for s, l in weak[:12]: log(f"  weak line [{s}]: {l}")
    # How often the sung melody falls on the chord's notes
    v, sr = librosa.load(st / "vocals.wav", sr=16000)
    f0, vf, vp = librosa.pyin(v, fmin=80, fmax=900, sr=sr, hop_length=320, frame_length=1280)
    t = librosa.times_like(f0, sr=sr, hop_length=320); ok = vf & (vp > 0.6)
    pcs = (np.round(librosa.hz_to_midi(f0[ok])) % 12).astype(int); tt = t[ok]
    bars = ch["bars"]; starts = np.array([b[0] for b in bars])
    def tones(c):
        m = re.match(r"([A-G][b#]?)(.*)", c); r = pc(m[1]); return {(r + i) % 12 for i in QUAL.get(m[2], QUAL[""])[0]}
    def score(d):   # the share of sung frames on the notes of the chord d seconds later
        hit = []
        for x, p in zip(tt, pcs):
            i = np.searchsorted(starts, x + d, side="right") - 1
            if i < 0: continue
            b = bars[i]; nxt = bars[i + 1][0] if i + 1 < len(bars) else ch["end"]
            c = b[2] if len(b) > 2 and x + d >= (b[0] + nxt) / 2 else b[1]
            hit.append(p in tones(c))
        return float(np.mean(hit)) if hit else 0.0
    now = score(0)
    log(f"melody on chord notes: {100 * now:.0f}% (about 65% is typical; one chord held all song scores about 55%)")
    # Grid check: the melody against the chords a beat later and earlier. Clearly better a beat later means the chords
    # come a beat late (the downbeats should be a beat earlier); a melody that leads its changes can also do this, so
    # it's a hint to weigh with the bass check, not a verdict
    phase = ch.get("phase")
    if phase is not None and len(starts) > 1:
        beat = float(np.median(np.diff(starts))) / 4
        for d, to in ((beat, phase - 1), (-beat, phase + 1)):
            later = score(d)
            if later - now > 0.04:
                log(f"grid check: the melody fits better with every chord moved a beat {'earlier' if d > 0 else 'later'} ({100 * later:.0f}%); "
                    f"if the bass check agrees or the chords sound a beat off, rerun with --phase {to % 4}")
    log_melody(mstat)


def log_melody(m):
    log(f"melody: {m['notes']} notes across {note_name(m['lo'])}–{note_name(m['hi'])}, covering {100 * m['covered']:.0f}% of the sung lines' time "
        "(70% or more is good; much less means the vocals stem is hard to track, so check it by ear)")


def melody_only(args, work):
    # A page made before melodies (or one whose melody should be redone; delete pitch.npz in the work dir to track the
    # pitch again too): its lines come from its karaoke-SLUG.js, the notes from the vocals stem given as the input
    dest = args.out
    data = dest / f"karaoke-{args.slug}.js"
    if not data.exists(): sys.exit(f"--melody-only: no {data}; make the page first")
    src = data.read_text()
    K = json.loads(re.search(r"window\.KARAOKE = (\[[\s\S]*\]);", src)[1])
    page = dest / "index.html"
    if not page.exists(): sys.exit(f"--melody-only: no {page}; make the page first")
    title = args.title or (re.match(r"// Karaoke chords for [“\"](.+?)[”\"]", src) or [None, args.slug])[1]
    # The page needs the melody's script tag and the Melody toggle (a page made before melodies has neither); both are
    # worked out before anything is written, so a page this can't patch is left as it was
    html_ = page.read_text(); tag = f'<script src="melody-{args.slug}.js"></script>'
    if tag not in html_:
        anchor = f'<script src="karaoke-{args.slug}.js"></script>'
        if anchor not in html_: sys.exit(f"--melody-only: {page} doesn't load karaoke-{args.slug}.js; add {tag} before it by hand")
        html_ = html_.replace(anchor, tag + "\n" + anchor)
    if 'id="tMelody"' not in html_:
        diag = re.search(r'<button class="minibtn" id="diag"[^>]*>[^<]*</button>', html_)
        if not diag: sys.exit(f"--melody-only: {page} has no Chord diagrams button to put the Melody toggle beside; rebuild the page")
        html_ = html_.replace(diag[0], diag[0] + '<button class="minibtn" id="tMelody" aria-pressed="false" hidden>Melody</button>')
    mjs, mstat = melody_js(melody(args.mp3, work), K, title, page.name)
    (dest / f"melody-{args.slug}.js").write_text(mjs)
    page.write_text(html_)
    if args.out:
        # A page folder has its own copies of the player and its styles, which may predate melodies: refresh them
        for f in ["karaoke.js", "chordpage.css"]: (dest / f).write_text(cut((SKILL / "assets" / f).read_text(), Path(f).suffix))
    log(f"built: {dest}/melody-{args.slug}.js"); log_melody(mstat)


def main():
    ap = argparse.ArgumentParser(description="Make a karaoke chord page from a recording and its lyrics")
    ap.add_argument("mp3", type=Path); ap.add_argument("--slug", required=True); ap.add_argument("--title")
    ap.add_argument("--artist"); ap.add_argument("--lyrics", type=Path)
    ap.add_argument("--melody-only", action="store_true", help="for a page already made: the input is its vocals stem, and only the melody is added")
    ap.add_argument("--yt"); ap.add_argument("--whisper", action="store_true"); ap.add_argument("--whisper-model", default="small.en")
    ap.add_argument("--stems"); ap.add_argument("--work", type=Path); ap.add_argument("--released", default="")
    ap.add_argument("--out", "--standalone", dest="out", type=Path, metavar="DIR", help="the folder to write the page into, one song per folder")
    credit = ap.add_mutually_exclusive_group()
    credit.add_argument("--permission", help="the footer's credit, e.g. ' (shared with their permission)'; the default fits --no-media")
    ap.add_argument("--key"); ap.add_argument("--capo", type=int)
    ap.add_argument("--phase", type=int, choices=range(4), help="which beat (0-3, counting from the first tracked beat) the bars start on, when the guess is a beat off")
    ap.add_argument("--no-media", action="store_true")
    ap.add_argument("--about", help="the line under the key, in place of the most common run of chords the script finds")
    ap.add_argument("--half-time", action="store_true", help="the song is felt at half the tracked tempo (rap, half-time drums): the page says so")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--evidence", action="store_true", help="also print each bar's bass and backing notes, for checking stray chords")
    credit.add_argument("--own", action="store_true", help="the song is yours: the footer credits you instead of disclaiming the artist")
    args = ap.parse_args()
    if not args.melody_only:
        for a in ["title", "artist", "lyrics"]:
            if not getattr(args, a): ap.error(f"--{a} is required")
    if args.out:
        # One song per folder: its page is index.html, so a folder holding another song's data would be overwritten
        other = [f.name for f in args.out.glob("karaoke-*.js") if f.name != f"karaoke-{args.slug}.js"]
        if other: sys.exit(f"--out: {args.out} already holds another song ({other[0]}); use an empty folder per song")
    elif not hasattr(args, "site"): sys.exit("--out DIR: the folder to write the page into")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.slug): sys.exit("--slug: lowercase words joined by hyphens, e.g. my-song")
    work = args.work or Path.home() / ".cache" / "chordpage" / args.slug; work.mkdir(parents=True, exist_ok=True)
    if args.melody_only: return melody_only(args, work)
    st = stems(args, work); log("stems:", st)
    bt = beats(st, work); log(f"beats: {len(bt['beats'])}, tempo {bt['bpm'][1]} BPM (from {bt['bpm'][0]} to {bt['bpm'][2]})")
    ch = chords(st, work, bt, args.key, args.phase); log(f"chords: {len(ch['bars'])} bars, key {ch['key']}, downbeats on beat {ch.get('phase')} of 4")
    if ch.get("bass_phase") is not None and ch["bass_phase"] != ch["phase"]:
        log(f"chords: the bass changes most often on beat {ch['bass_phase']} of 4 (by {100 * ch.get('bass_margin', 0):.0f}% over the "
            f"downbeats); if the report's grid check agrees or the chords sound a beat off, rerun with --phase {ch['bass_phase']}")
    asr = words(args, st, work); log("words: " + " and ".join(str(len(a)) for a in asr) + " from the transcript" + ("s" if len(asr) > 1 else ""))
    secs = read_lyrics(args.lyrics)
    per, hits, matched, total, timed = align(secs, *asr)
    mel = melody(st / "vocals.wav", work); log(f"melody: {len(mel)} notes")
    log(f"words: {snap(per, timed, mel)} the transcript left out placed on sung notes")
    K, capo, key, mstat = build(args, st, bt, ch, secs, per, hits, mel)
    if args.out: log(f"built: {args.out}/index.html (key {key}, capo {capo}); serve it with: npx serve {args.out}")
    if not args.no_report: report(st, ch, K, matched, total, hits, secs, mstat)
    if args.evidence: evidence(st, ch)


if __name__ == "__main__":
    main()
