"""Suggest `music.dropSeconds` for any track, without listening: find where the energy jumps.

Usage: python3 music_drop.py public/music/mytrack.mp3 [window_seconds=0.25] [search_seconds=45]

Prints the first audible moment and the biggest energy rises (candidate beat drops), as seconds
into the file. Pick one and set it as `music.dropSeconds` in src/scenes.json so it lands on the
title reveal. For the bundled tracks use their cues/*.music-cues.json instead. Needs ffmpeg.
"""
import array
import math
import subprocess
import sys


def rms_series(path, win, limit):
    """[(time_s, rms_dB)] per `win` seconds, from raw 8 kHz mono PCM decoded by ffmpeg."""
    rate = 8000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(limit), "-i", path, "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    n = int(rate * win)
    series = []
    for i in range(0, len(samples) - n + 1, n):
        chunk = samples[i:i + n]
        ms = sum(x * x for x in chunk) / n
        series.append((i / rate, 10 * math.log10(ms / 32768.0 ** 2) if ms > 0 else -120.0))
    return series


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    win = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    limit = float(sys.argv[3]) if len(sys.argv) > 3 else 45
    s = rms_series(path, win, limit)
    if not s:
        raise SystemExit("no audio analysed")
    first = next((t for t, v in s if v > -45), None)
    print("first audible: %s" % ("%.2fs" % first if first is not None else "none in window"))
    # energy rise: mean level of the next second vs the previous second
    k = max(1, int(round(1.0 / win)))
    rises = []
    for i in range(k, len(s) - k):
        before = sum(v for _, v in s[i - k:i]) / k
        after = sum(v for _, v in s[i:i + k]) / k
        rises.append((after - before, s[i][0]))
    rises.sort(reverse=True)
    picked = []
    for d, t in rises:
        if d < 2.0 or any(abs(t - p) < 3 for _, p in picked):
            continue
        picked.append((d, t))
        if len(picked) == 4:
            break
    for d, t in picked:
        print("energy rise +%.1f dB at %.2fs" % (d, t))
    if not picked:
        print("no clear drop; use the first audible moment, or a beat from the cue file")


if __name__ == "__main__":
    main()
