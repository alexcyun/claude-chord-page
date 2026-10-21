// Chord sheet: draws KARAOKE (the page's karaoke-*.js) as chords over lyrics, Ultimate Guitar style, with transpose, a
// capo view in easy open shapes, text size, auto-scroll, chord diagrams and a player (synth or the recording, plus the
// vocals) with a karaoke wipe. Pages are made by the chord-page skill. Song-specific settings come from KARAOKE_SONG:
//   {key: "Gm", capo: 5 (0 hides the capo view), about: "a line under the key", instrumental: "media/….mp3",
//    vocals: "media/….mp3" (either "" to hide it)}
// and the bar grid from BARS (the page's bars-*.js), and, if the page has one, the sung melody from MELODY (its melody-*.js):
//   {lo, hi (the MIDI range the contour spans), notes: [[songSeconds, seconds, midiNote], …]}
// KARAOKE = [{sec, lines:[[text, [[charIndex, chord, songSeconds], …], songSeconds, [wordStart, …, lineEnd]], …]}, …];
// a chord past a line's words changes during a held note, the word times drive the highlighter wipe, and a line with no
// text is an instrumental row.
(function(){
const $ = id => document.getElementById(id);
const NOTES = ["C","C#","D","Eb","E","F","F#","G","Ab","A","Bb","B"];
// Standard shapes, low E to high e (x = not played); every major and minor chord, so any transpose has a diagram
const SHAPES = {C:"x32010","C#":"x46664",D:"xx0232",Eb:"x68886",E:"022100",F:"133211","F#":"244322",G:"320003",Ab:"466544",A:"x02220",Bb:"x13331",B:"x24442",
  Cm:"x35543","C#m":"x46654",Dm:"xx0231",Ebm:"x68876",Em:"022000",Fm:"133111","F#m":"244222",Gm:"355333",Abm:"466444",Am:"x02210",Bbm:"x13321",Bm:"x24432",
  C7:"x32310",D7:"xx0212",E7:"020100",F7:"131211",G7:"320001",A7:"x02020",B7:"x21202",Bb7:"x13131",Eb7:"x68686","C#7":"x46464","F#7":"242322",Ab7:"464544"};
// Half-diminished (m7b5) for every root, which the choruses use (Am7b5): a movable shape rooted on the A string, or on the
// D string where that would sit past the 8th fret
NOTES.forEach((n, pc) => { const a = (pc + 3) % 12, d = (pc + 10) % 12;
  SHAPES[n + "m7b5"] = a <= 8 ? `x${a}${a + 1}${a}${a + 1}x` : `xx${d}${d + 1}${d + 1}${d + 1}`; });
const SONG = Object.assign({key: "C", capo: 0, about: "", instrumental: "", vocals: ""}, window.KARAOKE_SONG);
const KEY = SONG.key, keyName = k => k.replace(/^([A-G][b#]?)(m?)$/, (_, r, m) => r + (m ? " minor" : " major"));
let shift = 0, capoOn = false, size = 16, timer = null;
const tr = ch => ch.replace(/^([A-G][b#]?)/, r => NOTES[(NOTES.indexOf(r) + shift + 12) % 12]);
// Capo view: shapes SONG.capo semitones down (capo 5 turns Gm into Dm), which the capo brings back up. Its own switch, so
// transposing to the same shapes still sounds in the key it says
const capo = () => capoOn;

// How many characters of the sheet's mono text fit on one row, so long lines can wrap (phones)
function columns(sheet){
  const probe = document.createElement("pre"); probe.className = "cline"; probe.style.cssText = "position:absolute;visibility:hidden";
  probe.textContent = "0".repeat(40); sheet.append(probe);
  const ch = probe.getBoundingClientRect().width / 40, cs = getComputedStyle(sheet); probe.remove();
  return Math.max(16, Math.floor((sheet.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)) / ch));
}
// A line too long for the row splits, Ultimate Guitar style, each piece with the chords over its own words: after a
// sentence or clause end if one falls past a third of the row, else after the last word that fits. Chords past the words
// (changes during a held note) move left as far as they need to end inside the row, staying past the words
function fit(chords, len, cols){
  let lim = cols;
  return chords.slice().reverse().map(([at, c, ...r]) => {
    if (at >= len) at = Math.max(len ? len + 1 : 0, Math.min(at, lim - tr(c).length));
    lim = at - 1; return [at, c, ...r];
  }).reverse();
}
function wrap(text, chords, cols){
  if (text.length <= cols) return [[text, fit(chords, text.length, cols)]];
  let cut = 0;
  for (const re of [/[.?!:;”"]\s/g, /,\s/g, /\s/g]){
    for (const m of text.matchAll(re)) if (m.index + m[0].length <= cols) cut = m.index + m[0].length;
    if (cut > cols / 3) break;
  }
  if (!cut) cut = cols;
  const rest = text.slice(cut).replace(/^\s+/, ""), skip = text.length - cut - rest.length;
  return [[text.slice(0, cut).trimEnd(), chords.filter(([at]) => at < cut)],
    ...wrap(rest, chords.filter(([at]) => at >= cut).map(([at, c]) => [Math.max(0, at - cut - skip), c]), cols)];
}
function render(){
  const used = [], sheet = $("sheet");
  hidePop();
  sheet.textContent = "";
  const cols = columns(sheet);
  let L = 0;
  for (const s of window.KARAOKE){
    const h = document.createElement("h2"); h.className = "csec";
    // Built as nodes, not HTML: section names and links come from each song's data
    const label = document.createElement("span"); label.textContent = `[${s.sec}]`; h.append(label);
    sheet.append(h);
    for (const [line, lineChords] of s.lines){ let k = 0, off = 0; wrap(line, lineChords, cols).forEach(([text, chords], i, all) => {
      // Chord row: each chord at its character; a chord that would run into the one before moves right one space past it.
      // data-l (the line's number on the sheet) and data-c (line:chord) let the player light up what it's playing
      const pre = document.createElement("pre"); pre.className = "cline" + (i < all.length - 1 ? " cont" : ""); pre.dataset.l = L;
      let col = 0;
      for (const [at, c] of chords){ const name = tr(c); if (!used.includes(name)) used.push(name);
        const b = document.createElement("b"); b.textContent = name; b.dataset.c = L + ":" + k++;
        pre.append(" ".repeat(Math.max(col ? 1 : 0, at - col)), b); col = Math.max(col + (col ? 1 : 0), at) + name.length; }
      // A wrapped piece with no chord of its own is a plain lyric row, with no empty chord row above it
      // The words sit in a span that carries the highlighter wipe (::after, a copy of the words in data-t, so find-in-page
      // sees them once); data-o is where this piece starts in the whole line
      if (text){
        const o = line.indexOf(text, off); off = o + text.length;
        // The melody's contour, when it's on, is a row of its own that starts on a new line, so it takes the newline's place
        if (melOn()) pre.append(melRow(LINES[L], o, text.length));
        else if (chords.length || !i) pre.append("\n");
        const ly = document.createElement("span");
        ly.className = "lyr"; ly.dataset.o = o; ly.dataset.t = text; ly.textContent = text; pre.append(ly);
      }
      sheet.append(pre);
    }); L++; }
  }
  sheet.style.setProperty("--melh", MEL ? Math.min(2.4, Math.max(1.2, (MEL.hi - MEL.lo) * 0.14 + 0.2)) + "em" : "");
  $("tVal").textContent = shift > 6 ? shift - 12 : (shift > 0 ? "+" : "") + shift;
  $("capo").setAttribute("aria-pressed", capo());
  $("keyNote").textContent = capo() ? `Capo on fret ${SONG.capo}: these shapes sound in ${keyName(KEY)}, matching the recording.`
    : shift ? `Transposed to ${keyName(tr(KEY))}. The recording is in ${keyName(KEY)}` + (mode() !== "synth" ? ", so pick Synth backing to hear this key." : ".")
    : `Original key: ${keyName(KEY)}.` + (SONG.about ? " " + SONG.about : "");
  diagrams(used);
  mark();
}

// ---------- Chord shapes ----------
// Every chord has three shapes by skill level (saved as chordpage-shapes; the same choice drives the diagram row and the popup
// that opens when you hover a chord, or tap one on a touch screen):
//   Beginner: the chord's notes on the top three strings (four for 7ths), the closest to the nut, with no big barre
//   Standard: the usual song-book shape (SHAPES above)
//   Advanced: a full barre shape further up the neck (E, A or D shape), the nearest one that isn't the Standard shape
const LEVELS = [["easy", "Beginner", "Top strings only, no big barre"], ["std", "Standard", "The usual shape"], ["adv", "Advanced", "Full barre shape up the neck"]];
const OPEN_PC = [4, 9, 2, 7, 11, 4];   // the open strings, low E to high e, as notes (E = 4)
// Movable barre shapes, low E to high e, as frets above the barre (-1 = not played); `root` is the open string's note
const BARRE = [
  {root: 4, "": [0, 2, 2, 1, 0, 0], m: [0, 2, 2, 0, 0, 0], "7": [0, 2, 0, 1, 0, 0], m7: [0, 2, 0, 0, 0, 0]},                     // E shape
  {root: 9, "": [-1, 0, 2, 2, 2, 0], m: [-1, 0, 2, 2, 1, 0], "7": [-1, 0, 2, 0, 2, 0], m7: [-1, 0, 2, 0, 1, 0], m7b5: [-1, 0, 1, 0, 1, -1]},   // A shape
  {root: 2, m7b5: [-1, -1, 0, 1, 1, 1]}];                                                                                        // D shape
const fretsOf = s => typeof s === "string" ? [...s].map(x => x === "x" ? -1 : +x) : s;
const perms = a => a.length < 2 ? [a] : a.flatMap((x, i) => perms([...a.slice(0, i), ...a.slice(i + 1)]).map(p => [x, ...p]));
// The Beginner shape: every way to put the chord's notes on the top strings, each at its first fret or an octave up, keeping
// those within four frets (open strings only low down), and the one nearest the nut with the fewest fingers wins
const lessThan = (a, b) => { const i = a.findIndex((x, k) => x !== b[k]); return i >= 0 && a[i] < b[i]; };
function easyShape(pc, q){
  const tones = QUAL[q].map(i => (pc + i) % 12), strs = tones.length > 3 ? [2, 3, 4, 5] : [3, 4, 5];
  let best = null;
  for (const p of perms(tones)){
    let combos = [[]];
    p.forEach((n, j) => { const f = (n - OPEN_PC[strs[j]] + 12) % 12; combos = combos.flatMap(c => (f ? [f, f + 12] : [0, 12]).map(x => [...c, x])); });
    for (const c of combos){
      const fr = c.filter(x => x > 0), hi = fr.length ? Math.max(...fr) : 0, lo = fr.length ? Math.min(...fr) : 0;
      if (hi - lo > 3 || (hi > 4 && c.includes(0))) continue;
      const score = [hi, fr.length, c.reduce((a, b) => a + b)];
      if (!best || lessThan(score, best.score)) best = {score, c};
    }
  }
  return best && [...Array(6 - strs.length).fill(-1), ...best.c];
}
const shapeCache = {};
function shapesFor(name){
  if (name in shapeCache) return shapeCache[name];
  const m = name.match(/^([A-G][b#]?)(m7b5|m7|m|7)?$/), std = SHAPES[name] && fretsOf(SHAPES[name]);
  if (!m || !std) return shapeCache[name] = null;
  const pc = NOTES.indexOf(m[1]), q = m[2] || "", key = std.join();
  const forms = BARRE.filter(b => q in b).map(b => { let f = (pc - b.root + 12) % 12 || 12; return b[q].map(x => x < 0 ? -1 : f + x); })
    .filter(s => s.join() !== key).sort((a, b) => Math.min(...a.filter(x => x > 0)) - Math.min(...b.filter(x => x > 0)));
  return shapeCache[name] = {easy: easyShape(pc, q) || std, std, adv: forms[0] || std};
}
let shapeLevel = "std";
try { const s = localStorage.getItem("chordpage-shapes"); if (LEVELS.some(l => l[0] === s)) shapeLevel = s; } catch {}

// One fretboard: frets low E to high e (-1 muted, 0 open), the first fret shown labeled when it isn't the nut
function diagramSVG(f){
  const played = f.filter(x => x > 0);
  const base = Math.max(0, ...played) > 4 ? Math.min(...played) : 1, X = i => 7 + i * 8, Y = fr => 16 + (fr - base) * 11 + 5.5;
  let s = `<svg viewBox="0 0 62 74" width="62" height="74" aria-hidden="true">`;
  for (let i = 0; i < 6; i++) s += `<line x1="${X(i)}" y1="16" x2="${X(i)}" y2="60"/>`;
  for (let j = 0; j <= 4; j++) s += `<line x1="7" y1="${16 + j*11}" x2="47" y2="${16 + j*11}"${j === 0 && base === 1 ? ' class="nut"' : ""}/>`;
  if (base > 1) s += `<text x="53" y="25">${base}</text>`;
  // A barre: the lowest fret held across two or more strings with nothing lower in between, from a bass string or across
  // neighboring strings (not over a higher fret, which takes separate fingers: D's xx0232)
  const low = Math.min(...played), across = f.map((x, i) => x === low ? i : -1).filter(i => i >= 0);
  if (across.length > 1 && (across[0] <= 1 || across.every((x, k) => !k || x === across[k - 1] + 1)) && f.slice(across[0]).every(x => x >= low))
    s += `<rect class="dot" x="${X(across[0]) - 3.5}" y="${Y(low) - 3.5}" width="${X(across.at(-1)) - X(across[0]) + 7}" height="7" rx="3.5"/>`;
  f.forEach((x, i) => { s += x < 0 ? `<text x="${X(i) - 2.6}" y="11">×</text>` : x === 0 ? `<circle cx="${X(i)}" cy="8" r="2.6"/>` : `<circle class="dot" cx="${X(i)}" cy="${Y(x)}" r="3.4"/>`; });
  return s + "</svg>";
}
// Diagrams for the chords on screen, home chord first, at the chosen level
let onScreen = [];
function diagrams(list){
  const box = $("diagrams"), home = tr(KEY);
  onScreen = list.sort((a, b) => (b === home) - (a === home));
  box.innerHTML = onScreen.filter(c => shapesFor(c)).map(c => `<figure class="cdiag">${diagramSVG(shapesFor(c)[shapeLevel])}<figcaption>${c}</figcaption></figure>`).join("");
}
function setShapeLevel(l){
  shapeLevel = l;
  try { localStorage.setItem("chordpage-shapes", l); } catch {}
  document.querySelectorAll("[data-shape]").forEach(b => b.setAttribute("aria-pressed", b.dataset.shape === l));
  diagrams(onScreen); if (popFor) fillPop();
}
document.querySelectorAll("[data-shape]").forEach(b => { b.onclick = () => setShapeLevel(b.dataset.shape); });

// The chord popup: hover a chord (or tap one on a touch screen when nothing is playing) for its shape at the chosen level
// and a switch to the other two. It stays while the pointer is on it, and goes on scrolling, Esc or a tap elsewhere
const pop = document.createElement("div");
pop.id = "cpop"; pop.className = "cpop"; pop.hidden = true; pop.setAttribute("role", "group"); pop.setAttribute("aria-label", "Chord shape");
document.body.append(pop);
let popFor = null, popTimer = 0, popY = 0;
function fillPop(){
  const name = popFor.textContent, sh = shapesFor(name), lv = LEVELS.find(l => l[0] === shapeLevel);
  pop.innerHTML = `<div class="cpname">${name}</div><figure class="cdiag">${diagramSVG(sh[shapeLevel])}</figure>`
    + `<span class="seg">${LEVELS.map(([id, label]) => `<button class="minibtn" data-shape="${id}" aria-pressed="${id === shapeLevel}">${label}</button>`).join("")}</span>`
    + `<p>${lv[2]}</p>`;
  pop.querySelectorAll("[data-shape]").forEach(b => { b.onclick = () => setShapeLevel(b.dataset.shape); });
  place();
}
// Under the chord, or above it where there's no room, kept on screen
function place(){
  const r = popFor.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
  pop.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + "px";
  pop.style.top = (r.bottom + 6 + h > innerHeight - 8 && r.top - 6 - h > 8 ? r.top - 6 - h : r.bottom + 6) + "px";
}
function showPop(b){
  clearTimeout(popTimer);
  if (popFor === b && !pop.hidden) return;
  if (!shapesFor(b.textContent)) return;
  popFor = b; popY = scrollY; pop.hidden = false; fillPop();
}
const hidePop = () => { clearTimeout(popTimer); pop.hidden = true; popFor = null; };
const hideSoon = () => { clearTimeout(popTimer); popTimer = setTimeout(hidePop, 160); };
const chordAt = e => e.target.closest?.(".cline b");
// Hover is for a mouse only: a tap on a touch screen also fires emulated mouse events, which would open the popup that the
// tap's click then closes again
$("sheet").addEventListener("pointerover", e => { const b = chordAt(e); if (b && e.pointerType === "mouse") showPop(b); });
$("sheet").addEventListener("pointerout", e => { if (chordAt(e) && e.pointerType === "mouse") hideSoon(); });
pop.addEventListener("mouseenter", () => clearTimeout(popTimer));
pop.addEventListener("mouseleave", hideSoon);
addEventListener("scroll", () => { if (!pop.hidden && Math.abs(scrollY - popY) > 4) hidePop(); }, {passive: true});
$("sheet").addEventListener("scroll", hidePop, {passive: true});   // a long line scrolling sideways
addEventListener("keydown", e => { if (e.key === "Escape") hidePop(); });
const touchOnly = matchMedia("(hover: none)");
// A tap on a chord opens (or closes) its popup, unless the song is playing, when a tap jumps to that line; a tap anywhere else closes it
document.addEventListener("click", e => {
  const b = chordAt(e);
  if (b && (e.pointerType ? e.pointerType !== "mouse" : touchOnly.matches) && (!play || play.paused)){ popFor === b && !pop.hidden ? hidePop() : showPop(b); e.stopPropagation(); }
  else if (!pop.contains(e.target)) hidePop();
}, true);

function stopScroll(){ if (!timer) return; clearInterval(timer); timer = null; $("scroll").setAttribute("aria-pressed", "false"); $("scroll").textContent = "▶ Auto-scroll"; }
$("scroll").onclick = () => {
  if (timer) return stopScroll();
  pausePlay();
  $("scroll").setAttribute("aria-pressed", "true"); $("scroll").textContent = "⏸ Pause";
  let carry = 0;
  timer = setInterval(() => { carry += $("speed").value * 0.25; const px = Math.floor(carry); carry -= px; scrollBy(0, px);
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) stopScroll(); }, 40);
};
addEventListener("wheel", stopScroll, {passive: true});
addEventListener("touchstart", stopScroll, {passive: true});

// Play, with a choice of backing (saved as chordpage-backing) and a mix of band and vocals (saved as chordpage-mix). Synth: a small
// Web Audio band (bass on beats 1 and 3, a soft keyboard on every beat) plays the song's chords on the song's own clock
// (BARS, the page's bars-*.js: the recording's bar lines, tempo drift and instrumental gaps) after a four-click count-in; it
// sounds in the sheet's key, so it follows transpose (the capo view sounds in the recording's key). Recording: the song
// with its vocals removed (SONG.instrumental, hosted only with the artist's permission), started a bar before the line as
// its count-in; always in the recording's key. With either, the isolated vocals (SONG.vocals, same) can play along in
// step, and the Mix sliders set the band's and the vocals' volume. The line and chord being
// sung light up and stay in view (a scroll, touch or scrolling key pauses that for a few seconds). Play starts from the
// first line on screen; tapping a line while it plays jumps there.
const BARS = window.BARS.bars, BAR_END = window.BARS.end, LINES = [];
for (const s of window.KARAOKE) for (const [text, chords, at, words] of s.lines)
  LINES.push({at, times: chords.map(c => c[2]), words, idx: [...text.matchAll(/\S+/g)].map(m => m.index), len: text.length, notes: []});
// How far through its words a line is sung at song time t, in characters: each word's start time (the line's 4th entry,
// from YouTube's word-timed captions matched to the lyrics, and its end) is a point, and the wipe runs straight between
// them, so a held note fills slowly and a quick run fills fast
function sungTo(L, t){
  const w = L.words; if (!w || t <= w[0]) return 0;
  for (let k = 0; k < L.idx.length; k++) if (t < w[k + 1]){
    const c0 = L.idx[k], c1 = L.idx[k + 1] ?? L.len; return c0 + (c1 - c0) * (t - w[k]) / (w[k + 1] - w[k]);
  }
  return L.len;
}
// The melody: each note belongs to the line being sung when it starts and spans the characters its words are sung over
// (by sungTo, so the contour keeps step with the wipe). Drawn as a dash per note between the chords and the words, as high
// as its pitch within the song's range, filling in highlighter yellow as it's sung; its title is the note's name as
// sung: in the transposed key, or the recording's in the capo view (whose chord names are shapes, not pitches). The Melody toggle shows or hides it (saved as chordpage-melody, on unless turned off)
const MEL = window.MELODY?.notes?.length ? window.MELODY : null;
if (MEL) for (const [t, dur, m] of MEL.notes){
  const L = LINES[LINES.findLastIndex(l => l.at - 0.3 <= t)];
  if (!L?.words || t >= L.words.at(-1)) continue;
  const a = sungTo(L, t);
  L.notes.push({t, m, a, b: Math.min(Math.max(sungTo(L, t + dur), a + 0.8), Math.max(L.len, a + 0.8))});
}
const MELODY_KEY = "chordpage-melody";
let melodyOn = true;
try { melodyOn = localStorage.getItem(MELODY_KEY) !== "0"; } catch {}
const melOn = () => melodyOn && !!MEL;
const signed = s => s > 6 ? s - 12 : s;
const noteName = m => NOTES[(m % 12 + 12) % 12] + (Math.floor(m / 12) - 1);
// One wrapped piece's row of dashes: the piece runs from character o of its line for len characters
function melRow(L, o, len){
  const row = document.createElement("span"); row.className = "mel"; row.setAttribute("aria-hidden", "true");
  const y = m => Math.min(1, Math.max(0, (m - MEL.lo) / Math.max(1, MEL.hi - MEL.lo))).toFixed(3);
  for (const n of L.notes) if (n.a < o + len && n.b > o){
    const a = Math.max(n.a, o) - o, w = Math.min(n.b, o + len + 1) - o - a;
    const d = document.createElement("i"); d.dataset.t = n.t; d.title = noteName(n.m + (capo() ? 0 : signed(shift)));
    d.style.cssText = `--a:${a.toFixed(2)};--n:${w.toFixed(2)};--y:${y(n.m)}`; row.append(d);
  }
  return row;
}
const QUAL = {"": [0, 4, 7], m: [0, 3, 7], "7": [0, 4, 7, 10], m7: [0, 3, 7, 10], m7b5: [0, 3, 6, 10]};
let ac = null, play = null, followAfter = 0, song = null, vox = null, gBand = null, gVox = null;
const BACKING_KEY = "chordpage-backing", MIX_KEY = "chordpage-mix", LOOP_KEY = "chordpage-loop";
// The backings and their buttons
const BACKINGS = {synth: "bSynth", song: "bSong"};
// Loop (saved as chordpage-loop): at the end of the song, Play starts again from the first line instead of stopping
let loop = true;
try { loop = localStorage.getItem(LOOP_KEY) !== "0"; } catch {}
const ended = () => loop ? startPlay(0) : stopPlay();
let backing = "synth";
const mix = {band: 1, vocals: 0.8};
try {
  const b = localStorage.getItem(BACKING_KEY); if (Object.hasOwn(BACKINGS, b)) backing = b;
  const saved = JSON.parse(localStorage.getItem(MIX_KEY)) || {};
  for (const key in mix) if (Number.isFinite(saved[key])) mix[key] = Math.min(1, Math.max(0, saved[key]));
} catch {}
// One audio graph, started on the first Play: the synth and the recording go through the band's gain, the vocals through
// their own (iOS ignores an audio element's volume, so the gains live here). A slider's square sets the gain, which feels
// even across its travel
function audio(){
  // iOS mutes Web Audio under the silent switch unless the page says it's playback, like a music player
  if (navigator.audioSession) navigator.audioSession.type = "playback";
  if (!ac){
    ac = new (window.AudioContext || window.webkitAudioContext)();
    gBand = ac.createGain(); gVox = ac.createGain(); gBand.connect(ac.destination); gVox.connect(ac.destination); setGains();
  }
  ac.resume();
}
function setGains(){ if (ac){ gBand.gain.value = mix.band ** 2; gVox.gain.value = mix.vocals ** 2; } }
const track = (src, gain) => { const a = Object.assign(new Audio(src), {preload: "auto"}); ac.createMediaElementSource(a).connect(gain); return a; };
// The vocals follow the backing's clock: started (inside the click, so phones allow it) when they're turned up, and moved
// back into step whenever they drift more than 0.15 s. Turned down to nothing, or with no vocals file (a page without
// media), they don't play (or download)
function syncVox(t, start){
  if (!SONG.vocals || !(mix.vocals > 0) || !play || play.paused){ if (vox && !vox.paused) vox.pause(); return; }
  vox ||= track(SONG.vocals, gVox);
  const target = play.song ? song.currentTime : t;
  // Not time yet (the synth's count-in, the recording loading, seeking or waiting for data): wait, but still call play()
  // if this is the click, since phones only let an element start from a click once it has
  if (target < 0 || (play.song && (song.paused || song.seeking || song.readyState < 3))){
    if (start) vox.play().catch(() => {}); else if (!vox.paused) vox.pause();
    return;
  }
  // Out of step: seek, but not again while a seek is still landing (a slow connection would never catch up), and aim a
  // little ahead when the vocals have to load, so they land where the backing will be
  if (!vox.seeking && Math.abs(vox.currentTime - target) > 0.15) vox.currentTime = target + (vox.readyState < 3 ? 0.2 : 0);
  if (vox.paused) vox.play().catch(() => {});
}
const sounding = () => capo() ? 0 : shift;
const hz = midi => 440 * 2 ** ((midi - 69) / 12);
const near = (pc, lo) => lo + ((pc - lo) % 12 + 12) % 12;   // the pitch class pc in the octave from MIDI note lo up
function tone(out, midi, t, dur, type, vol){
  const o = ac.createOscillator(), g = ac.createGain(); o.type = type; o.frequency.value = hz(midi);
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + 0.008); g.gain.exponentialRampToValueAtTime(0.0005, t + dur);
  o.connect(g).connect(out); o.start(t); o.stop(t + dur + 0.05);
}
// One bar of BARS: four beats spread over its length, the second-half chord (if any) from beat 3. Song time s plays at
// audio time s + play.off; beats before play.from are skipped (playing from mid-bar)
function bar(k){
  const [t0, c1, c2] = BARS[k], len = (BARS[k + 1]?.[0] ?? BAR_END) - t0, beat = len / 4;
  for (let b = 0; b < 4; b++){
    const st = t0 + b * beat; if (st < play.from - 0.01) continue;
    const [, root, q] = (b < 2 || !c2 ? c1 : c2).match(/^([A-G][b#]?)(.*)$/), pc = NOTES.indexOf(root) + sounding(), t = st + play.off;
    (QUAL[q] || QUAL[""]).forEach(iv => tone(play.out, near(pc + iv, 55), t, beat * 0.95, "triangle", b ? 0.045 : 0.07));
    if (b % 2 === 0) tone(play.out, near(pc, 40), t, beat * 1.8, "sine", 0.32);
  }
}
function mark(){
  const sheet = $("sheet"), cur = play?.cur;
  sheet.querySelectorAll(".cline.playing .lyr").forEach(el => el.style.removeProperty("--w"));
  sheet.querySelectorAll(".mel i.sung").forEach(el => el.classList.remove("sung"));
  sheet.querySelectorAll(".cline.playing, b.on").forEach(el => el.classList.remove("playing", "on"));
  if (!cur){ if (play) play.lyrs = play.mels = []; return; }
  sheet.querySelectorAll(`[data-l="${cur.line}"]`).forEach(el => el.classList.add("playing"));
  play.lyrs = [...sheet.querySelectorAll(".cline.playing .lyr")];   // the wipe's spans, for paint()
  play.mels = [...sheet.querySelectorAll(".cline.playing .mel i")];  // and the melody's dashes
  if (cur.k >= 0) sheet.querySelector(`[data-c="${cur.line}:${cur.k}"]`)?.classList.add("on");
  if (play.paused) wipe(play);   // a sheet redrawn while paused (text size, Melody) keeps the wipe where it stopped
}
function frame(){
  if (!play) return;
  const t = clock();
  syncVox(t);
  // Once the line Play started on is reached, any line can be the one sung
  if (play.start && t >= LINES[play.start].at - 0.1) play.start = 0;
  if (play.out){ const ahead = t + (document.hidden ? 1.5 : 0.25); while (play.k < BARS.length && BARS[play.k][0] < ahead) bar(play.k++); }
  // The line being sung: the last one started (a line's pickup counts), or during the count-in the one it starts on; its
  // chord: the last one reached
  const line = Math.max(play.start, LINES.findLastIndex(l => l.at - 0.1 <= t)), k = LINES[line].times.findLastIndex(x => x <= t + 0.05);
  if (line !== play.cur?.line || k !== play.cur?.k){
    const moved = line !== play.cur?.line;
    play.cur = {line, k}; mark();
    if (moved && performance.now() > followAfter){
      // The line goes a third of the way down
      const el = $("sheet").querySelector(`[data-l="${line}"]`);
      let at = innerHeight * 0.35;
      scrollTo({top: el.getBoundingClientRect().top + scrollY - at,
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    }
  }
  if (t > BAR_END && (play.out || play.song)) return ended();
}
// Song time now. The recording's currentTime can update only a few times a second, so between updates it runs on the wall
// clock, which keeps the wipe smooth
let lastCT = -1, lastWall = 0;
function clock(){
  if (!play.song) return ac.currentTime - play.off;
  const ct = song.currentTime, w = performance.now() / 1000;
  if (ct !== lastCT){ lastCT = ct; lastWall = w; }
  return song.paused ? ct : ct + Math.min(0.3, w - lastWall);
}
// The highlighter wipe: every animation frame, the line being sung is filled up to the word being sung. One loop per
// playback: it ends when that playback does or pauses (a restart or resume starts its own)
function paint(p, tok = p.paintTok = {}){
  if (play !== p || p.paintTok !== tok || p.paused) return;
  wipe(p);
  requestAnimationFrame(() => paint(p, tok));
}
function wipe(p){
  if (!p.cur) return;
  const t = clock(), x = sungTo(LINES[p.cur.line], t);
  for (const el of p.lyrs || []) el.style.setProperty("--w", Math.max(0, Math.min(el.dataset.t.length, x - el.dataset.o)) + "ch");
  for (const el of p.mels || []) el.classList.toggle("sung", t >= el.dataset.t - 0.02);
}
function startPlay(line){
  stopPlay(); stopScroll();
  const lead = ac?.state === "running" ? 0.1 : 0.35;  // a context that's still starting up gets longer before the first click
  audio();
  if (mode() === "song") return startSong(line);
  const out = ac.createGain(), lp = ac.createBiquadFilter(); lp.frequency.value = 2600;
  out.connect(lp).connect(gBand);
  // Start half a beat before the line (its pickup), after four clicks at the tempo there
  const from = Math.max(0, LINES[line].at - 0.25), k = Math.max(0, BARS.findLastIndex(b => b[0] <= from));
  const beat = ((BARS[k + 1]?.[0] ?? BAR_END) - BARS[k][0]) / 4, off = ac.currentTime + lead + 4 * beat - from;
  for (let i = 0; i < 4; i++) tone(out, i ? 84 : 91, from - (4 - i) * beat + off, 0.08, "sine", 0.15);
  play = {out, off, from, k, start: line, cur: null, tick: setInterval(frame, 25)}; paint(play);
  syncVox(clock(), true);
  playingUI(true);
}
// The recording, from a bar before the line (the music is its own count-in); its clock is the song's, so no offset
function startSong(line){
  song ||= track(SONG.instrumental, gBand);
  const from = Math.max(0, LINES[line].at - 0.25), k = Math.max(0, BARS.findLastIndex(b => b[0] <= from));
  const bar = (BARS[k + 1]?.[0] ?? BAR_END) - BARS[k][0];
  // Safari ignores a seek before the file's length is known, so a first play seeks once it is
  const seek = () => { song.currentTime = Math.max(0, from - bar); };
  if (song.readyState) seek(); else song.addEventListener("loadedmetadata", seek, {once: true});
  const p = play = {song: true, start: line, cur: null, tick: setInterval(frame, 25)}; paint(p);
  song.onended = ended;
  song.play().catch(() => { if (play === p && !p.paused) stopPlay(); });
  syncVox(0, true);
  playingUI(true);
}
// Pause keeps the place: the synth's clock (and the notes queued on it) freeze with its audio context, the recording and
// vocals just pause, and Resume carries on from there. Stop (below) is for the backing changing or the song ending
function pausePlay(){
  if (!play || play.paused) return;
  play.paused = true; clearInterval(play.tick);
  if (play.out) ac.suspend();
  song?.pause(); vox?.pause();
  playingUI(true, true);
}
function resumePlay(){
  if (!play?.paused) return;
  stopScroll();   // Play follows the line itself
  const p = play; p.paused = false;
  if (p.out) ac.resume();
  if (p.song) song.play().catch(() => { if (play === p && !p.paused) stopPlay(); });
  p.tick = setInterval(frame, 25); paint(p);
  syncVox(clock(), true);
  playingUI(true, false);
}
function stopPlay(){
  if (!play) return;
  const {out, tick} = play; play = null; clearInterval(tick);
  if (out){ out.gain.setTargetAtTime(0, ac.currentTime, 0.02); setTimeout(() => out.disconnect(), 300); }
  song?.pause(); vox?.pause();
  playingUI(false); mark();
}
function playingUI(on, paused){
  document.body.classList.toggle("playing", on);
  document.body.classList.toggle("paused", !!paused);
  $("play").setAttribute("aria-pressed", on && !paused); $("play").textContent = on ? (paused ? "▶ Resume" : "⏸ Pause") : "▶ Play";
}
// Backing: switching while playing carries on from the line being sung
function setBacking(b){
  backing = b;
  try { localStorage.setItem(BACKING_KEY, b); } catch {}
  backingButtons();
  if (play){ const was = play.paused; startPlay(play.cur?.line ?? play.start); if (was) pausePlay(); }   // a paused song stays paused
  render();
}
// The backing in use: the saved choice, unless this page can't have it (Recording needs a hosted recording)
function mode(){
  return backing === "song" && !SONG.instrumental ? "synth" : backing;
}
function backingButtons(){
  const m = mode();
  for (const [b, id] of Object.entries(BACKINGS)) $(id).setAttribute("aria-pressed", m === b);
}

// Mix: the band (synth or recording) and the vocals, each 0–100
for (const [id, key] of [["vBand", "band"], ["vVox", "vocals"]]){
  $(id).value = Math.round(mix[key] * 100);
  $(id).oninput = () => {
    mix[key] = $(id).value / 100; setGains();
    try { localStorage.setItem(MIX_KEY, JSON.stringify(mix)); } catch {}
    if (play && !play.paused) syncVox(clock(), true);
  };
}
$("loop").onclick = () => {
  loop = !loop; $("loop").setAttribute("aria-pressed", loop);
  try { localStorage.setItem(LOOP_KEY, loop ? "1" : "0"); } catch {}
};
$("loop").setAttribute("aria-pressed", loop);
$("bSynth").onclick = () => setBacking("synth");
$("bSong").onclick = () => setBacking("song");
$("play").onclick = () => {
  if (play) return play.paused ? resumePlay() : pausePlay();
  const lines = [...$("sheet").querySelectorAll("pre[data-l]")], top = $("chordbar").getBoundingClientRect().bottom;
  startPlay(+(lines.find(el => el.getBoundingClientRect().bottom > Math.max(0, top)) || lines[0]).dataset.l);
};
$("sheet").addEventListener("click", e => {
  const pre = e.target.closest("pre[data-l]");
  if (pre && !getSelection().toString()) startPlay(+pre.dataset.l);
});
const hold = () => { followAfter = performance.now() + 4000; };
addEventListener("wheel", hold, {passive: true});
addEventListener("touchstart", hold, {passive: true});
addEventListener("keydown", e => { if (/^(Arrow(Up|Down)|Page(Up|Down)|Home|End| )$/.test(e.key)) hold(); });
$("tUp").onclick = () => { shift = (shift + 1) % 12; capoOn = false; render(); };
$("tDown").onclick = () => { shift = (shift + 11) % 12; capoOn = false; render(); };
$("capo").onclick = () => { capoOn = !capoOn; shift = capoOn ? (12 - SONG.capo) % 12 : 0; render(); };
// Controls this song has nothing for: no capo view, no hosted recording, no hosted vocals
$("capo").textContent = "Capo " + SONG.capo; $("capo").closest(".cgrp").hidden = !SONG.capo;

if (!SONG.vocals) $("vVox").closest("label").hidden = true;
$("bSong").hidden = !SONG.instrumental; $("bSong").closest(".seg").hidden = $("bSong").hidden;
const setSize = d => { size = Math.min(26, Math.max(11, size + d)); document.documentElement.style.setProperty("--csize", size + "px"); render(); };
$("fUp").onclick = () => setSize(2);
$("fDown").onclick = () => setSize(-2);
$("tMelody").hidden = !MEL; $("tMelody").setAttribute("aria-pressed", melodyOn);
$("tMelody").onclick = () => {
  melodyOn = !melodyOn; $("tMelody").setAttribute("aria-pressed", melodyOn);
  try { localStorage.setItem(MELODY_KEY, melodyOn ? "1" : "0"); } catch {}
  render();
};
$("diag").onclick = () => { const on = $("diagrams").hidden; $("diagrams").hidden = !on; $("diag").setAttribute("aria-pressed", on); };
// Re-wrap when the sheet's width changes (rotation, resizing), and once the mono font has loaded
let lastW = 0;
new ResizeObserver(() => { const w = $("sheet").clientWidth; if (w !== lastW){ lastW = w; render(); } }).observe($("sheet"));
document.fonts?.ready.then(render);
document.querySelectorAll("[data-shape]").forEach(b => b.setAttribute("aria-pressed", b.dataset.shape === shapeLevel));
backingButtons();
render();
})();
