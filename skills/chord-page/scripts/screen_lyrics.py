#!/usr/bin/env python3
# The lyrics a video prints on screen, read off its frames, for songs with no published lyrics (the chord-page skill's
# step 1; auto-captions mishear, the screen doesn't). macOS only: it reads the frames with the system's text recognition
# (screen_lyrics.swift, compiled on first use; needs Xcode's command line tools) and ffmpeg.
#
#   python screen_lyrics.py VIDEO.mp4 [--from 0.8] [--to 1.0] [--fps 2] [--all]
#
# Prints a timeline: the second each new piece of text appears in the band between --from and --to (shares of the
# frame's height from the top; the default is the bottom fifth, where karaoke-style lyrics sit) and the text. --all
# prints every band with its height, to find where a video puts its lyrics (a spoken intro typed at the top, a chorus
# hook in big letters mid-screen). A line shows up several times as it fills in word by word and the reader misreads the
# dim words: take the last, complete reading of each, and fix capitals and punctuation by eye from a frame or two
# (ffmpeg -ss SECONDS -i VIDEO -frames:v 1 frame.png). A 480p copy is enough: yt-dlp -f "bv*[height<=480]" URL
import argparse, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description="Read a video's on-screen lyrics off its frames (macOS)")
    ap.add_argument("video", type=Path); ap.add_argument("--from", dest="top", type=float, default=0.8)
    ap.add_argument("--to", dest="bottom", type=float, default=1.0); ap.add_argument("--fps", type=float, default=2)
    ap.add_argument("--all", action="store_true", help="every band, each piece of text with its height")
    args = ap.parse_args()
    if sys.platform != "darwin": sys.exit("screen_lyrics: macOS only (it uses the system's text recognition)")
    work = Path.home() / ".cache" / "chordpage"; work.mkdir(parents=True, exist_ok=True)
    reader = work / "screen_lyrics"
    if not reader.exists() or reader.stat().st_mtime < (HERE / "screen_lyrics.swift").stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(HERE / "screen_lyrics.swift"), "-o", str(reader)], check=True)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(args.video), "-vf", f"fps={args.fps}", "-q:v", "2", f"{tmp}/f%05d.jpg"], check=True)
        frames = sorted(Path(tmp).glob("f*.jpg"))
        out = subprocess.run([str(reader)] + [str(f) for f in frames], check=True, capture_output=True, text=True).stdout
    rows = {}
    for line in out.splitlines():
        f, y, text = line.split("\t", 2); y = float(y)
        if args.all or args.top <= y <= args.bottom: rows.setdefault(int(f[1:6]), []).append((y, text))
    prev = None
    for n in sorted(rows):
        r = sorted(rows[n])
        text = " / ".join(t for _, t in r); shown = " / ".join(f"{t} @{y:.2f}" for y, t in r) if args.all else text
        if text != prev: print(f"{(n - 1) / args.fps:7.1f}  {shown}")
        prev = text


if __name__ == "__main__":
    main()
