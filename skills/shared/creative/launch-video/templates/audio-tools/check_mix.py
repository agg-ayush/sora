"""Final-render audio check: loudness, transcribe-back of the mix, drop alignment.

Usage: python3 audio-tools/check_mix.py out/video.mp4 [--no-listen]     (run from the project root)

1. loudness: integrated LUFS (target -17 +-2) and true peak (<= -1.0 dBTP) via ffmpeg ebur128;
2. transcribe-back: the mixed audio goes through the TrueFoundry transcription route and every
   line of audio-tools/vo.json (in scenes.json order) is word-diffed against it;
3. drop alignment: the reveal time (scenes.json title scene start + offsetFrames) vs the nearest
   sharp onset in the mix and, unless --no-listen, vs the median of 7 audio-understanding answers.
Exit status 1 if a check fails. Stdlib only, Python 3.9+; needs ffmpeg.
"""
import difflib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import music_drop  # noqa: E402

ROOT = os.path.join(HERE, "..")


def loudness(video):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         stderr=subprocess.PIPE, universal_newlines=True).stderr
    summary = err[err.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary).group(1))


def words(t):
    t = t.lower().replace("-", " ").replace("helpdesk", "help desk")
    return re.sub(r"[^a-z0-9' ]", " ", t).replace("'", "").split()


def reveal_seconds(table):
    fps, tr = table["fps"], table["transitionFrames"]
    start = 0
    for s in table["scenes"]:
        if s["id"] == table["reveal"]["scene"]:
            return (start + table["reveal"]["offsetFrames"]) / fps
        start += s["frames"] - tr
    raise SystemExit("reveal scene not found")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    video, ok = args[0], True
    listen = "--no-listen" not in sys.argv
    table = json.load(open(os.path.join(ROOT, "src/scenes.json")))
    lufs, tp = loudness(video)
    good = abs(lufs + 17) <= 2 and tp <= -1.0
    ok &= good
    print("loudness: %.1f LUFS (want -17 +-2), true peak %.1f dBTP (want <= -1.0): %s" % (lufs, tp, "ok" if good else "FAIL"))

    import gemini
    tmp = tempfile.mkdtemp()
    mix = os.path.join(tmp, "mix.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", mix], check=True)
    heard = gemini.listen(mix, "Transcribe all spoken words in this audio exactly, in order. Ignore music and sound effects. Output only the words.")
    lines = json.load(open(os.path.join(HERE, "vo.json")))["lines"]
    seen, order = set(), []
    for s in table["scenes"]:
        for vid, _ in s["vo"]:
            if vid not in seen:
                seen.add(vid)
                order.append(vid)
    exp = [w for k in order for w in words(lines[k])]
    got = words(heard)
    sm = difflib.SequenceMatcher(None, exp, got)
    diffs = [(op, exp[a:b], got[c:d]) for op, a, b, c, d in sm.get_opcodes() if op != "equal"]
    # digits vs spelled-out numbers are noise; anything else counts
    good = sm.ratio() >= 0.97
    ok &= good
    print("transcript: %d expected / %d heard words, match %.3f: %s" % (len(exp), len(got), sm.ratio(), "ok" if good else "FAIL"))
    for d in diffs:
        print("  %s %s -> %s" % d)

    reveal = reveal_seconds(table)
    limit = int(reveal + 10)
    samples = music_drop.decode(video, limit)
    onset = music_drop.sharp_onset(samples, reveal)
    rises = music_drop.energy_rises(music_drop.rms_series(samples, 0.25), 0.25, count=6, min_db=1.0, min_gap=1.0)
    rise = min(rises, key=lambda r: abs(r[1] - reveal))[1] if rises else None
    good = onset is not None and abs(onset - reveal) <= 0.15
    ok &= good
    print("drop: reveal %.2fs, sharpest onset %s, nearest energy rise %s: %s" % (
        reveal, "%.2fs (%+.2f)" % (onset, onset - reveal) if onset else "none", "%.2fs (%+.2f)" % (rise, rise - reveal) if rise else "none", "ok" if good else "FAIL"))
    if listen:
        clip = os.path.join(tmp, "head.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", str(limit), "-i", video, "-ac", "1", "-ar", "16000", clip], check=True)
        q = ("This is the first %d seconds of a product video soundtrack (voiceover plus a music bed). Timestamps are seconds from the start "
             "of this clip. Where does the music's full beat / drop come in (the biggest energy jump in the music)? "
             'Answer ONLY JSON: {"drop_at":<sec, 0.05 resolution>}' % limit)
        vals = []
        for _ in range(7):
            m = re.search(r'drop_at"?\s*:\s*([\d.]+)', gemini.listen(clip, q))
            if m:
                vals.append(float(m.group(1)))
        if vals:
            med = statistics.median(vals)
            good = abs(med - reveal) <= 0.25  # the model answers to ~0.1s and jitters run to run; the onset check above is the tight one
            ok &= good
            print("drop (listen, median of %d): %.2fs (%+.2f vs reveal): %s   answers %s" % (len(vals), med, med - reveal, "ok" if good else "FAIL", vals))
        else:
            print("drop (listen): no parsable answer")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
