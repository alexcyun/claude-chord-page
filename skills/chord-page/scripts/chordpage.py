#!/usr/bin/env python3
# Chord page pipeline (the chord-page skill, .claude/skills/chord-page/SKILL.md): turns a song's recording and lyrics into
# a karaoke chord page: chords over every line, a synth and the hosted recording to play along with, the isolated vocals
# to blend in, and a word-by-word highlighter wipe. It writes into the pdoom site (site/, the default), or with
# --standalone DIR a self-contained folder (index.html, karaoke.js, chordpage.css, the song's data and media/) that any
# static server can host.
#
#   python chordpage.py SONG.mp3 --slug my-song --title "My Song" --artist "Someone" --lyrics lyrics.txt
#                       [--yt YOUTUBE_ID | --whisper] [--stems DIR] [--work DIR] [--site SITE_DIR] [--explainer PAGE]
#                       [--released "Oct 2, 2026"] [--og media/og-x.png] [--permission " (shared with their permission)"]
#                       [--key Gm] [--capo N] [--no-media] [--standalone DIR]
#
# Stages, each cached in the work dir (delete a file there to redo that stage):
#   1. stems     demucs htdemucs splits the song into bass, drums, other and vocals (or --stems gives existing ones)
#   2. beats     beats tracked one by one on the drums stem (songs drift in tempo, so no fixed grid), downbeats from where
#                the harmony changes most often
#   3. chords    one chord per half bar from the bass and other stems (chroma against major, minor, 7 and m7b5 templates,
#                a small bonus for chords in the song's key), smoothed with Viterbi so chords change on strong beats
#   4. words     word start times: YouTube's word-timed auto-captions (--yt), or faster-whisper on the vocals (--whisper)
#   5. align     the lyrics' words matched to those words (difflib over the whole song); unmatched words interpolated
#   6. build     karaoke-SLUG.js, bars-SLUG.js, SLUG-chords.html (index.html, karaoke.js and chordpage.css with
#                --standalone) and (unless --no-media) media/SLUG-instrumental.mp3 and media/SLUG-vocals.mp3
# Then it prints a report: words matched, lines that matched poorly, how often the sung melody falls on the chord's notes
# (about 65% is good for a pop song; a single chord held all song scores about 55%), and the roughest stretches.
#
# Lyrics file: the sung lines in order, repeats written out, one per row; "[Section]" or "[Section | cue-id]" starts a
# section (cue-id: the note on the explainer page that "watch this part" links to). Blank rows are ignored.
import argparse, bisect, difflib, html, json, re, shutil, subprocess, sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent   # the skill's folder: templates and assets/
NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
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
    r = NOTES.index(key.rstrip("m")); n = lambda i: NOTES[(r + i) % 12]
    if key.endswith("m"):
        return {n(0) + "m", n(5) + "m", n(7) + "m", n(7), n(7) + "7", n(3), n(8), n(10), n(2) + "m7b5", n(2) + "m"}
    return {n(0), n(2) + "m", n(4) + "m", n(5), n(7), n(7) + "7", n(9) + "m", n(11) + "m7b5", n(2) + "7", n(4) + "7"}


def chords(st, work, bt, forced_key=None):
    f = work / "bars.json"
    if f.exists():
        cached = json.loads(f.read_text())
        if not forced_key or cached["key"] == forced_key: return cached   # a different --key decodes again
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
    if phase:   # beats before the first downbeat: a short bar of their own
        bars.insert(0, [round(float(b[0]), 2), ch[0]])
    end = round(float(b[-1] + np.median(np.diff(b))), 2)
    out = {"key": key, "bars": bars, "end": end}
    f.write_text(json.dumps(out)); return out


# ---------- 4. words ----------
def words(args, st, work):
    f = work / "asr.json"
    if f.exists(): return json.loads(f.read_text())
    out = []
    if args.yt:
        subprocess.run([sys.executable, "-m", "yt_dlp", "--skip-download", "--write-auto-subs", "--sub-langs", "en", "--sub-format", "json3",
                        "-o", str(work / "yt"), f"https://www.youtube.com/watch?v={args.yt}"], check=True)
        got = sorted(work.glob("yt.*.json3"))   # named by the track found: en, en-US, en-orig, …
        if not got: sys.exit("words: YouTube has no English auto-captions for this video; try --whisper")
        d = json.loads(got[0].read_text())
        for e in d["events"]:
            for s in e.get("segs", []):
                w = s["utf8"].strip()
                if w and not w.startswith("["): out.append([round((e["tStartMs"] + s.get("tOffsetMs", 0)) / 1000, 2), w])
    elif args.whisper:
        from faster_whisper import WhisperModel
        log("words: transcribing the vocals with faster-whisper…")
        segs, _ = WhisperModel(args.whisper_model, compute_type="int8").transcribe(str(st / "vocals.wav"), word_timestamps=True, language="en")
        for s in segs:
            for w in s.words or []: out.append([round(w.start, 2), w.word.strip()])
    else:
        sys.exit("words: pass --yt YOUTUBE_ID (word-timed auto-captions) or --whisper (needs faster-whisper)")
    f.write_text(json.dumps(out)); return out


# ---------- 5. align ----------
def read_lyrics(path):
    secs = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if not line: continue
        m = re.fullmatch(r"\[([^\]|]+?)\s*(?:\|\s*([\w-]+))?\s*\]", line)
        if m: secs.append({"sec": m[1].strip(), "cue": m[2], "lines": []}); continue
        if not secs: secs.append({"sec": "Verse", "cue": None, "lines": []})
        secs[-1]["lines"].append(line)
    return secs


def align(secs, asr):
    norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower().replace("’", "'"))
    flat = [(si, li, m.start(), m.group()) for si, s in enumerate(secs) for li, l in enumerate(s["lines"]) for m in re.finditer(r"\S+", l)]
    sm = difflib.SequenceMatcher(None, [norm(w) for *_, w in flat], [norm(w) for _, w in asr], autojunk=False)
    times = [None] * len(flat)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n): times[a + k] = asr[b + k][0]
    matched = sum(t is not None for t in times)
    # Unmatched words: spread between the nearest matched words on either side, by word count
    known = [i for i, t in enumerate(times) if t is not None]
    if not known: sys.exit("align: no lyric words matched the transcript; check the lyrics or the transcript source")
    for i in range(len(times)):
        if times[i] is None:
            lo = max([k for k in known if k < i], default=None); hi = min([k for k in known if k > i], default=None)
            if lo is None: times[i] = max(0.05 * (i + 1), times[hi] - 0.3 * (hi - i))
            elif hi is None: times[i] = times[lo] + 0.3 * (i - lo)
            else: times[i] = times[lo] + (times[hi] - times[lo]) * (i - lo) / (hi - lo)
    for i in range(1, len(times)): times[i] = max(times[i], times[i - 1] + 0.05)
    per, hits, kset = {}, {}, set(known)
    for i, ((si, li, at, w), t) in enumerate(zip(flat, times)):
        per.setdefault((si, li), []).append((at, w, t))      # (character index, word, start time) per word
        hits.setdefault((si, li), []).append(i in kset)       # whether each word matched the transcript
    return per, hits, matched, len(flat)


# ---------- 6. build ----------
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
        m = re.match(r"([A-G][b#]?)(.*)", c); return NOTES[(NOTES.index(m[1]) - k) % 12] + m[2]
    score = [(sum(shift(c, k) in OPEN for c in chord_list) - (0.5 if k else 0), -k) for k in range(8)]
    return -max(score)[1]


def common_loop(bars, starts):
    # The most frequent run of four bars starting where a sung line does (so it reads as a phrase, not a slice across
    # two), for the line under the key
    seq, runs = [b[1] for b in bars], {}
    first = sorted({max(0, max((i for i, b in enumerate(bars) if b[0] <= t + 0.6), default=0)) for t in starts})
    for i in first:
        r = tuple(seq[i:i + 4])
        if len(r) == 4 and len(set(r)) > 1: runs[r] = runs.get(r, 0) + 1
    if not runs: return ""
    r, n = max(runs.items(), key=lambda x: x[1])
    return f"The most common run of chords: {', '.join(r)}." if n >= 3 else ""


def build(args, st, bt, ch, secs, per, hits):
    site = Path(args.standalone or args.site); slug = args.slug; site.mkdir(parents=True, exist_ok=True)
    bars, end = ch["bars"], ch["end"]
    key = args.key or ch["key"]
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
        K.append({"sec": "Intro", "cue": None, "lines": [["", instr(bars[0][0], flat[0][3][0][2] - 0.3), bars[0][0], None]]})
    for n, (si, li, text, ws) in enumerate(flat):
        nxt = flat[n + 1][3][0][2] if n + 1 < len(flat) else end
        last = ws[-1][2]; bl = bar_len(last)
        line_end = min(nxt, last + min(3, max(0.4, nxt - last - 0.1)))
        chords = place(text, ws, line_end, ev, chord_at)
        if li == 0: K.append({"sec": secs[si]["sec"], "cue": secs[si]["cue"], "lines": []})
        # a short gap (a held note, a breath): its changes go on the end of the line's chord row, past the words
        if nxt - line_end < 3 * bl:
            col = max(len(text) + 2, chords[-1][0] + len(chords[-1][1]) + 2)
            for s, c in ev:
                if line_end - 0.3 <= s < nxt - 0.3 and c != chords[-1][1]: chords.append([col, c, round(s, 2)]); col += len(c) + 2
        K[-1]["lines"].append([text, chords, round(ws[0][2], 2), [round(t, 2) for *_, t in ws] + [round(max(line_end, last + 0.25), 2)]])
        if nxt - line_end >= 3 * bl:
            K.append({"sec": "Outro" if n + 1 == len(flat) else "Instrumental", "cue": None, "lines": [["", instr(line_end, nxt), round(line_end, 2), None]]})
            if n + 1 < len(flat) and flat[n + 1][1] != 0:   # the section carries on after the break
                K.append({"sec": secs[flat[n + 1][0]]["sec"] + " (cont.)", "cue": None, "lines": []})
    for s in K:
        for l in s["lines"]:
            if l[3] is None: l.pop()
    capo = args.capo if args.capo is not None else easy_capo([b[1] for b in bars])
    media = {"instrumental": "", "vocals": ""}
    if not args.no_media:
        (site / "media").mkdir(exist_ok=True)
        media = {"instrumental": f"media/{slug}-instrumental.mp3", "vocals": f"media/{slug}-vocals.mp3"}
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st / "bass.wav"), "-i", str(st / "drums.wav"), "-i", str(st / "other.wav"),
                        "-filter_complex", "amix=inputs=3:normalize=0,alimiter=limit=0.95", "-b:a", "160k",
                        "-metadata", f"title={args.title} (instrumental)", "-metadata", f"artist={args.artist}", str(site / media["instrumental"])], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(st / "vocals.wav"), "-af", "alimiter=limit=0.95", "-b:a", "128k",
                        "-metadata", f"title={args.title} (vocals)", "-metadata", f"artist={args.artist}", str(site / media["vocals"])], check=True)
    song = {"key": key, "capo": capo, "explainer": "" if args.standalone else args.explainer, "about": common_loop(bars, [ws[0][2] for *_, ws in flat]), **media}
    page_name = "index.html" if args.standalone else f"{slug}-chords.html"
    js = (f"// Karaoke chords for “{args.title}” ({page_name}, drawn by karaoke.js), made by the chord-page skill from\n"
          f"// the recording: chords read from its stems on a tracked beat grid, line and word times from the transcript\n"
          f"// matched to the lyrics. See karaoke.js for the shapes of KARAOKE_SONG and KARAOKE.\n"
          f"window.KARAOKE_SONG = {json.dumps(song, ensure_ascii=False)};\nwindow.KARAOKE = [\n" +
          ",\n".join(json.dumps(s, ensure_ascii=False, separators=(", ", ": ")) for s in K) + "\n];\n")
    (site / f"karaoke-{slug}.js").write_text(js)
    lo, mid, hi = bt["bpm"]
    (site / f"bars-{slug}.js").write_text(
        f"// Bars for “{args.title}”: one [song seconds, chord, second-half chord?] per bar, read from the recording by the\n"
        f"// chord-page skill (about {mid:.0f} BPM). Used by karaoke.js (and an explainer's play-along strip, if it has one).\n"
        f"window.BARS = {{bpm:{mid:.0f}, end:{end}, bars:[{','.join(json.dumps(b, separators=(', ', ':')) for b in bars)}]}};\n")
    key_name = re.sub(r"^([A-G][b#]?)(m?)$", lambda m: m[1] + (" minor" if m[2] else " major"), key)
    tempo = f"About {mid:.0f} BPM" + (f" (it drifts from {lo:.0f} to {hi:.0f})" if hi - lo >= 2 else "") + ", 4/4"
    fill = {"TITLE": args.title, "ARTIST": args.artist, "SLUG": slug, "OG_IMAGE": args.og, "KEY_NAME": key_name,
            "TEMPO": tempo, "TEMPO_SHORT": f"about {mid:.0f} BPM", "RELEASED": f", {args.released}" if args.released else "",
            "EXPLAINER_LINK": f' <a href="{html.escape(args.explainer)}">Back to the explainer</a>.' if args.explainer else "",
            "PERMISSION": args.permission if args.permission is not None else
                (" (the lyrics are shared with their permission)" if args.no_media else " (the recording, vocals and lyrics are shared with their permission)"),
            "METHOD": ("How these were made: the recording was split into stems to set the vocals and drums aside, and its beats were "
                       "tracked one by one, since songs drift in tempo. Each half bar of the bass and backing was matched to the closest "
                       "chord, and the lyrics were matched word by word to a transcript, so every chord sits over the word being sung when "
                       "it changes. It’s a close reading of the recording, not the artist’s own chart, so trust your ear where they disagree. "
                       "Play plays these chords on the song’s own timing: Synth is a simple keyboard and bass in whatever key the sheet is "
                       "in; Recording is the song with its vocals taken out. Turn up Vocals to sing along with the original singer.")}
    if args.standalone:
        # A folder of its own: the standalone template (no site tabs, feedback or analytics) and the skill's copies of the
        # player and its styles
        tpl = (SKILL / "standalone.html").read_text()
        for f in ["karaoke.js", "chordpage.css"]: shutil.copy(SKILL / "assets" / f, site / f)
    else:
        # The site's page, with its tabs (its explainer's tab current, if it has one)
        tpl = (SKILL / "template.html").read_text()
        nav = re.search(r'<nav class="topnav"[\s\S]*?</nav>', (site / "index.html").read_text())[0].replace(' aria-current="page"', "")
        if args.explainer: nav = nav.replace(f'<a href="{args.explainer}" data-song>', f'<a href="{args.explainer}" data-song aria-current="page">')
        fill["TOPNAV"] = nav
    # Everything from the command line is escaped; the tabs and the explainer link are HTML on purpose
    raw = {"TOPNAV", "EXPLAINER_LINK"}
    page = re.sub(r"\{\{(\w+)\}\}", lambda m: fill[m[1]] if m[1] in raw else html.escape(fill[m[1]]), tpl)
    (site / page_name).write_text(page)
    return K, capo, key


# ---------- report ----------
def report(st, ch, K, matched, total, hits, secs):
    import numpy as np, librosa
    log(f"\nwords matched to the transcript: {matched}/{total} ({100 * matched / max(1, total):.0f}%)")
    weak = [(secs[si]["sec"], secs[si]["lines"][li]) for (si, li), h in hits.items() if sum(h) / len(h) < 0.6]
    for s, l in weak[:12]: log(f"  weak line [{s}]: {l}")
    # How often the sung melody falls on the chord's notes
    v, sr = librosa.load(st / "vocals.wav", sr=16000)
    f0, vf, vp = librosa.pyin(v, fmin=80, fmax=900, sr=sr, hop_length=320, frame_length=1280)
    t = librosa.times_like(f0, sr=sr, hop_length=320); ok = vf & (vp > 0.6)
    pc = (np.round(librosa.hz_to_midi(f0[ok])) % 12).astype(int); tt = t[ok]
    bars = ch["bars"]; starts = np.array([b[0] for b in bars])
    def tones(c):
        m = re.match(r"([A-G][b#]?)(.*)", c); r = NOTES.index(m[1]); return {(r + i) % 12 for i in QUAL.get(m[2], QUAL[""])[0]}
    hit = []
    for x, p in zip(tt, pc):
        i = np.searchsorted(starts, x, side="right") - 1
        if i < 0: continue
        b = bars[i]; nxt = bars[i + 1][0] if i + 1 < len(bars) else ch["end"]
        c = b[2] if len(b) > 2 and x >= (b[0] + nxt) / 2 else b[1]
        hit.append(p in tones(c))
    log(f"melody on chord notes: {100 * np.mean(hit):.0f}% (about 65% is typical; one chord held all song scores about 55%)")


def main():
    ap = argparse.ArgumentParser(description="Make a karaoke chord page from a recording and its lyrics")
    ap.add_argument("mp3", type=Path); ap.add_argument("--slug", required=True); ap.add_argument("--title", required=True)
    ap.add_argument("--artist", required=True); ap.add_argument("--lyrics", required=True, type=Path)
    ap.add_argument("--yt"); ap.add_argument("--whisper", action="store_true"); ap.add_argument("--whisper-model", default="small.en")
    ap.add_argument("--stems"); ap.add_argument("--work", type=Path); ap.add_argument("--site", default="site")
    ap.add_argument("--explainer", default=""); ap.add_argument("--released", default=""); ap.add_argument("--og", default="media/og-lineage.png")
    ap.add_argument("--permission", help="the footer's credit, e.g. ' (shared with their permission)'; the default fits --no-media")
    ap.add_argument("--key"); ap.add_argument("--capo", type=int); ap.add_argument("--no-media", action="store_true")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--standalone", type=Path, metavar="DIR", help="write a self-contained page folder here instead of into the site")
    args = ap.parse_args()
    if not args.standalone and not (Path(args.site) / "index.html").exists():
        sys.exit(f"--site: no {args.site}/index.html; outside the pdoom repo, pass --standalone DIR for a page folder of its own")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", args.slug): sys.exit("--slug: lowercase words joined by hyphens, e.g. my-song")
    work = args.work or Path.home() / ".cache" / "chordpage" / args.slug; work.mkdir(parents=True, exist_ok=True)
    st = stems(args, work); log("stems:", st)
    bt = beats(st, work); log(f"beats: {len(bt['beats'])}, tempo {bt['bpm'][1]} BPM (from {bt['bpm'][0]} to {bt['bpm'][2]})")
    ch = chords(st, work, bt, args.key); log(f"chords: {len(ch['bars'])} bars, key {ch['key']}")
    asr = words(args, st, work); log(f"words: {len(asr)} from the transcript")
    secs = read_lyrics(args.lyrics)
    per, hits, matched, total = align(secs, asr)
    K, capo, key = build(args, st, bt, ch, secs, per, hits)
    if args.standalone: log(f"built: {args.standalone}/index.html (key {key}, capo {capo}); serve it with: npx serve {args.standalone}")
    else: log(f"built: {args.site}/{args.slug}-chords.html, karaoke-{args.slug}.js, bars-{args.slug}.js (key {key}, capo {capo})")
    if not args.no_report: report(st, ch, K, matched, total, hits, secs)


if __name__ == "__main__":
    main()
