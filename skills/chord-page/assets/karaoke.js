// Chord sheet (*-chords.html, e.g. end-of-the-show-chords.html): draws KARAOKE (the page's karaoke-*.js) as chords over
// lyrics, Ultimate Guitar style, with transpose, a capo view in easy open shapes, text size, auto-scroll, chord diagrams and
// a player (synth or the recording, plus the vocals) with a karaoke wipe. Song-specific settings come from KARAOKE_SONG:
//   {key: "Gm", capo: 5 (0 hides the capo view), about: "a line under the key", explainer: "end-of-the-show" (page for
//    "watch this part" links; "" for none), instrumental: "media/….mp3", vocals: "media/….mp3" (either "" to hide it)}
// and the bar grid from BARS (the page's bars-*.js). New pages are made by the chord-page skill (.claude/skills/chord-page).
// KARAOKE = [{sec, cue, lines:[[text, [[charIndex, chord, songSeconds], …], songSeconds, [wordStart, …, lineEnd]], …]}, …];
// cue is the explainer note the section starts on, a chord past a line's words changes during a held note, the word times
// drive the highlighter wipe, and a line with no text is an instrumental row.
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
const SONG = Object.assign({key: "C", capo: 0, about: "", explainer: "", instrumental: "", vocals: ""}, window.KARAOKE_SONG);
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
  sheet.textContent = "";
  const cols = columns(sheet);
  let L = 0;
  for (const s of window.KARAOKE){
    const h = document.createElement("h2"); h.className = "csec";
    h.innerHTML = `<span>[${s.sec}]</span>` + (s.cue && SONG.explainer ? ` <a href="${SONG.explainer}#cue-${s.cue}">watch this part ↗</a>` : "");
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
        if (chords.length || !i) pre.append("\n");
        const ly = document.createElement("span"), o = line.indexOf(text, off); off = o + text.length;
        ly.className = "lyr"; ly.dataset.o = o; ly.dataset.t = text; ly.textContent = text; pre.append(ly);
      }
      sheet.append(pre);
    }); L++; }
  }
  $("tVal").textContent = shift > 6 ? shift - 12 : (shift > 0 ? "+" : "") + shift;
  $("capo").setAttribute("aria-pressed", capo());
  $("keyNote").textContent = capo() ? `Capo on fret ${SONG.capo}: these shapes sound in ${keyName(KEY)}, matching the recording.`
    : shift ? `Transposed to ${keyName(tr(KEY))}. The recording is in ${keyName(KEY)}` + (backing === "song" ? ", so pick Synth backing to hear this key." : ".")
    : `Original key: ${keyName(KEY)}.` + (SONG.about ? " " + SONG.about : "");
  diagrams(used);
  mark();
}

// Fretboard diagrams for the chords on screen, home chord first
function diagrams(list){
  const box = $("diagrams"), home = tr(KEY);
  list.sort((a, b) => (b === home) - (a === home));
  box.innerHTML = list.filter(c => SHAPES[c]).map(c => {
    const f = [...SHAPES[c]].map(x => x === "x" ? -1 : parseInt(x, 10)), played = f.filter(x => x > 0);
    const base = Math.max(...played) > 4 ? Math.min(...played) : 1, X = i => 7 + i * 8, Y = fr => 16 + (fr - base) * 11 + 5.5;
    let s = `<svg viewBox="0 0 56 74" width="56" height="74" aria-hidden="true">`;
    for (let i = 0; i < 6; i++) s += `<line x1="${X(i)}" y1="16" x2="${X(i)}" y2="60"/>`;
    for (let j = 0; j <= 4; j++) s += `<line x1="7" y1="${16 + j*11}" x2="47" y2="${16 + j*11}"${j === 0 && base === 1 ? ' class="nut"' : ""}/>`;
    if (base > 1) s += `<text x="50" y="25">${base}</text>`;
    // A barre: the lowest fret, held by the first finger from a bass string (low E or A) across to the highest
    const low = Math.min(...played), across = f.map((x, i) => x === low ? i : -1).filter(i => i >= 0);
    if (across.length > 1 && across[0] <= 1 && f.slice(across[0]).every(x => x >= low))
      s += `<rect class="dot" x="${X(across[0]) - 3.5}" y="${Y(low) - 3.5}" width="${X(across.at(-1)) - X(across[0]) + 7}" height="7" rx="3.5"/>`;
    f.forEach((x, i) => { s += x < 0 ? `<text x="${X(i) - 2.6}" y="11">×</text>` : x === 0 ? `<circle cx="${X(i)}" cy="8" r="2.6"/>` : `<circle class="dot" cx="${X(i)}" cy="${Y(x)}" r="3.4"/>`; });
    return `<figure class="cdiag">${s}</svg><figcaption>${c}</figcaption></figure>`;
  }).join("");
}

function stopScroll(){ if (!timer) return; clearInterval(timer); timer = null; $("scroll").setAttribute("aria-pressed", "false"); $("scroll").textContent = "▶ Auto-scroll"; }
$("scroll").onclick = () => {
  if (timer) return stopScroll();
  stopPlay();
  $("scroll").setAttribute("aria-pressed", "true"); $("scroll").textContent = "⏸ Stop";
  let carry = 0;
  timer = setInterval(() => { carry += $("speed").value * 0.25; const px = Math.floor(carry); carry -= px; scrollBy(0, px);
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 2) stopScroll(); }, 40);
};
addEventListener("wheel", stopScroll, {passive: true});
addEventListener("touchstart", stopScroll, {passive: true});

// Play, with a choice of backing (saved as pdoom-backing) and a mix of band and vocals (saved as pdoom-mix). Synth: a small
// Web Audio band (bass on beats 1 and 3, a soft keyboard on every beat) plays the song's chords on the song's own clock
// (BARS, the page's bars-*.js: the recording's bar lines, tempo drift and instrumental gaps) after a four-click count-in; it
// sounds in the sheet's key, so it follows transpose (the capo view sounds in the recording's key). Recording: the
// song with its vocals removed (SONG.instrumental, hosted only with the artist's permission), started a bar before the line
// as its count-in; always in the recording's key. With either, the isolated vocals (SONG.vocals, same) can play along in step, and the Mix sliders set the band's and the vocals' volume. The line and chord being
// sung light up and stay in view (a scroll, touch or scrolling key pauses that for a few seconds). Play starts from the
// first line on screen; tapping a line while it plays jumps there.
const BARS = window.BARS.bars, BAR_END = window.BARS.end, LINES = [];
for (const s of window.KARAOKE) for (const [text, chords, at, words] of s.lines)
  LINES.push({at, times: chords.map(c => c[2]), words, idx: [...text.matchAll(/\S+/g)].map(m => m.index), len: text.length});
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
const QUAL = {"": [0, 4, 7], m: [0, 3, 7], "7": [0, 4, 7, 10], m7: [0, 3, 7, 10], m7b5: [0, 3, 6, 10]};
let ac = null, play = null, followAfter = 0, song = null, vox = null, gBand = null, gVox = null;
const BACKING_KEY = "pdoom-backing", MIX_KEY = "pdoom-mix", LOOP_KEY = "pdoom-loop";
// Loop (saved as pdoom-loop): at the end of the song, Play starts again from the first line instead of stopping
let loop = false;
try { loop = localStorage.getItem(LOOP_KEY) === "1"; } catch {}
const ended = () => loop ? startPlay(0) : stopPlay();
let backing = "synth";
const mix = {band: 1, vocals: 0};
try {
  if (localStorage.getItem(BACKING_KEY) === "song") backing = "song";
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
// back into step whenever they drift more than 0.15 s. Turned down to nothing, they don't play (or download)
function syncVox(t, start){
  if (!(mix.vocals > 0) || !play){ if (vox && !vox.paused) vox.pause(); return; }
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
  sheet.querySelectorAll(".cline.playing, b.on").forEach(el => el.classList.remove("playing", "on"));
  if (!cur){ if (play) play.lyrs = []; return; }
  sheet.querySelectorAll(`[data-l="${cur.line}"]`).forEach(el => el.classList.add("playing"));
  play.lyrs = [...sheet.querySelectorAll(".cline.playing .lyr")];   // the wipe's spans, for paint()
  if (cur.k >= 0) sheet.querySelector(`[data-c="${cur.line}:${cur.k}"]`)?.classList.add("on");
}
function frame(){
  if (!play) return;
  const t = clock();
  syncVox(t);
  if (!play.song){ const ahead = t + (document.hidden ? 1.5 : 0.25); while (play.k < BARS.length && BARS[play.k][0] < ahead) bar(play.k++); }
  // The line being sung: the last one started (a line's pickup counts), or during the count-in the one it starts on; its
  // chord: the last one reached
  const line = Math.max(play.start, LINES.findLastIndex(l => l.at - 0.1 <= t)), k = LINES[line].times.findLastIndex(x => x <= t + 0.05);
  if (line !== play.cur?.line || k !== play.cur?.k){
    const moved = line !== play.cur?.line;
    play.cur = {line, k}; mark();
    if (moved && performance.now() > followAfter){
      const el = $("sheet").querySelector(`[data-l="${line}"]`);
      scrollTo({top: el.getBoundingClientRect().top + scrollY - innerHeight * 0.35,
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
    }
  }
  if (t > BAR_END) return ended();
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
// playback: it ends when that playback does (a restart starts its own)
function paint(p){
  if (play !== p) return;
  if (p.cur){
    const x = sungTo(LINES[p.cur.line], clock());
    for (const el of p.lyrs || []) el.style.setProperty("--w", Math.max(0, Math.min(el.dataset.t.length, x - el.dataset.o)) + "ch");
  }
  requestAnimationFrame(() => paint(p));
}
function startPlay(line){
  stopPlay(); stopScroll();
  const lead = ac?.state === "running" ? 0.1 : 0.35;  // a context that's still starting up gets longer before the first click
  audio();
  if (backing === "song") return startSong(line);
  const out = ac.createGain(), lp = ac.createBiquadFilter(); lp.frequency.value = 2600;
  out.connect(lp).connect(gBand);
  // Start half a beat before the line (its pickup), after four clicks at the tempo there
  const from = Math.max(0, LINES[line].at - 0.25), k = Math.max(0, BARS.findLastIndex(b => b[0] <= from));
  const beat = ((BARS[k + 1]?.[0] ?? BAR_END) - BARS[k][0]) / 4, off = ac.currentTime + lead + 4 * beat - from;
  for (let i = 0; i < 4; i++) tone(out, i ? 84 : 91, from - (4 - i) * beat + off, 0.08, "sine", 0.15);
  play = {out, off, from, k, start: line, cur: null, tick: setInterval(frame, 25)}; paint(play);
  syncVox(clock(), true);
  document.body.classList.add("playing");
  $("play").setAttribute("aria-pressed", "true"); $("play").textContent = "■ Stop";
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
  song.play().catch(() => { if (play === p) stopPlay(); });
  syncVox(0, true);
  document.body.classList.add("playing");
  $("play").setAttribute("aria-pressed", "true"); $("play").textContent = "■ Stop";
}
function stopPlay(){
  if (!play) return;
  const {out, tick} = play; play = null; clearInterval(tick);
  if (out){ out.gain.setTargetAtTime(0, ac.currentTime, 0.02); setTimeout(() => out.disconnect(), 300); }
  song?.pause(); vox?.pause();
  document.body.classList.remove("playing"); mark();
  $("play").setAttribute("aria-pressed", "false"); $("play").textContent = "▶ Play";
}
// Backing: switching while playing carries on from the line being sung
function setBacking(b){
  backing = b;
  try { localStorage.setItem(BACKING_KEY, b); } catch {}
  $("bSynth").setAttribute("aria-pressed", b === "synth"); $("bSong").setAttribute("aria-pressed", b === "song");
  if (play) startPlay(play.cur?.line ?? play.start);
  render();
}
// Mix: the band (synth or recording) and the vocals, each 0–100
for (const [id, key] of [["vBand", "band"], ["vVox", "vocals"]]){
  $(id).value = Math.round(mix[key] * 100);
  $(id).oninput = () => {
    mix[key] = $(id).value / 100; setGains();
    try { localStorage.setItem(MIX_KEY, JSON.stringify(mix)); } catch {}
    if (play) syncVox(clock(), true);
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
  if (play) return stopPlay();
  const lines = [...$("sheet").querySelectorAll("pre[data-l]")], top = $("chordbar").getBoundingClientRect().bottom;
  startPlay(+(lines.find(el => el.getBoundingClientRect().bottom > Math.max(0, top)) || lines[0]).dataset.l);
};
$("sheet").addEventListener("click", e => {
  const pre = e.target.closest("pre[data-l]");
  if (play && pre && !getSelection().toString()) startPlay(+pre.dataset.l);
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
if (!SONG.instrumental){ $("bSong").closest(".seg").hidden = true; backing = "synth"; }
if (!SONG.vocals) $("vVox").closest("label").hidden = true;
const setSize = d => { size = Math.min(26, Math.max(11, size + d)); document.documentElement.style.setProperty("--csize", size + "px"); render(); };
$("fUp").onclick = () => setSize(2);
$("fDown").onclick = () => setSize(-2);
$("diag").onclick = () => { const on = $("diagrams").hidden; $("diagrams").hidden = !on; $("diag").setAttribute("aria-pressed", on); };
// Re-wrap when the sheet's width changes (rotation, resizing), and once the mono font has loaded
let lastW = 0;
new ResizeObserver(() => { const w = $("sheet").clientWidth; if (w !== lastW){ lastW = w; render(); } }).observe($("sheet"));
document.fonts?.ready.then(render);
$("bSynth").setAttribute("aria-pressed", backing === "synth"); $("bSong").setAttribute("aria-pressed", backing === "song");
render();
})();
