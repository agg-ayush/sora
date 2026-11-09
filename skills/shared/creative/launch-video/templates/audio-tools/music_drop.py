"""Find and verify `music.dropSeconds` for a track: where the full beat drops in, snapped to the beat grid.

Usage: python3 music_drop.py public/music/mytrack.mp3 [--listen] [--window 0.25] [--search 30]

Prints, as seconds into the file:
  1. the biggest energy rises (RMS of the next second vs the previous second);
  2. each rise snapped to the nearest beat. The grid comes from cues/<stem>.music-cues.json next
     to the track (bundled tracks), else from a tempo estimated by onset autocorrelation (any
     other track; accurate to a few tens of ms, so confirm with --listen);
  3. the nearest strong cue to each rise (cue files only) and the sharpest 20 ms hit within 0.6s of that beat (the rise window lags the real hit,
     so the hit snapped to the grid is the suggested dropSeconds);
  4. with --listen: the first --search seconds sent to the TrueFoundry audio-understanding route
     (gemini.listen), asking for section changes and where the full beat comes in, also snapped.

A drop is trustworthy when an energy rise and the --listen answer agree within ~0.5s; use the
beat in the grid they both point at. Needs ffmpeg. Stdlib only, Python 3.9+.
"""
import array
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RATE = 8000


def decode(path, limit):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(limit), "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         stdout=subprocess.PIPE, check=True).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    return samples


def rms_series(samples, win):
    """[(time_s, rms_dB)] per `win` seconds."""
    n = int(RATE * win)
    series = []
    for i in range(0, len(samples) - n + 1, n):
        chunk = samples[i:i + n]
        ms = sum(x * x for x in chunk) / n
        series.append((i / RATE, 10 * math.log10(ms / 32768.0 ** 2) if ms > 0 else -120.0))
    return series


def energy_rises(series, win, count=4, min_db=2.0, min_gap=3.0):
    """Biggest rises: mean level of the next second minus the previous second."""
    k = max(1, int(round(1.0 / win)))
    rises = []
    for i in range(k, len(series) - k):
        before = sum(v for _, v in series[i - k:i]) / k
        after = sum(v for _, v in series[i:i + k]) / k
        rises.append((after - before, series[i][0]))
    rises.sort(reverse=True)
    picked = []
    for d, t in rises:
        if d < min_db or any(abs(t - p) < min_gap for _, p in picked):
            continue
        picked.append((d, t))
        if len(picked) == count:
            break
    return picked


def sharp_onset(samples, near, span=0.6):
    """Time of the sharpest 20 ms level jump within +-span s of `near` (pins a rise to its actual hit)."""
    ser = rms_series(samples, 0.02)
    best = None
    for i in range(5, len(ser) - 5):
        t = ser[i][0]
        if abs(t - near) > span:
            continue
        jump = sum(v for _, v in ser[i:i + 5]) / 5 - sum(v for _, v in ser[i - 5:i]) / 5
        if best is None or jump > best[0]:
            best = (jump, t)
    return best[1] if best else None


def estimate_grid(samples, limit):
    """(beat times, bpm) from onset autocorrelation: 100 Hz onset envelope, lag 0.3-0.75 s."""
    hop = RATE // 100
    env = []
    for i in range(0, len(samples) - hop + 1, hop):
        chunk = samples[i:i + hop]
        env.append(math.sqrt(sum(x * x for x in chunk) / hop))
    onset = [max(0.0, env[i] - env[i - 1]) for i in range(1, len(env))]
    n = len(onset)
    if n < 400:
        return [], 0.0
    mean = sum(onset) / n
    o = [x - mean for x in onset]

    def ac(lag):
        return sum(o[i] * o[i + lag] for i in range(n - lag)) / (n - lag)

    best_lag, best = 0, 0.0
    for lag in range(30, 76):
        s = ac(lag)
        if s > best:
            best, best_lag = s, lag
    if not best_lag:
        return [], 0.0
    # refine the period by parabolic interpolation, then pick the best-scoring phase
    a, b, c = ac(best_lag - 1), ac(best_lag), ac(best_lag + 1)
    den = a - 2 * b + c
    period = best_lag + (0.5 * (a - c) / den if den else 0.0)
    best_phase, best_score = 0.0, -1.0
    for p10 in range(int(period * 10)):
        phase = p10 / 10.0
        score, t = 0.0, phase
        while t < n - 1:
            score += onset[int(t)]
            t += period
        if score > best_score:
            best_score, best_phase = score, phase
    secs = period / 100.0
    t = (best_phase + 1) / 100.0  # onset[i] is the jump into env[i+1]
    beats = []
    while t < limit:
        beats.append(t)
        t += secs
    return beats, 60.0 / secs


def load_cues(path):
    """(beat times, strong cue times, tempo) from cues/<stem>.music-cues.json, or None."""
    stem = os.path.splitext(os.path.basename(path))[0]
    folder = os.path.dirname(os.path.abspath(path))
    for cand in (os.path.join(folder, "cues", stem + ".music-cues.json"), os.path.join(folder, stem + ".music-cues.json")):
        if os.path.exists(cand):
            with open(cand) as fh:
                d = json.load(fh)
            return [b["time"] for b in d["beats"]], [c["time"] for c in d.get("strongCues", [])], d.get("tempo")
    return None


def nearest(t, grid):
    return min(grid, key=lambda g: abs(g - t)) if grid else None


LISTEN_PROMPT = (
    "This is the first %d seconds of a royalty-free music track that will sit under a product video. "
    "Listen and report, with timestamps in seconds from the start of this clip: (1) each section change "
    "(intro, build, main groove...), and (2) the single moment where the FULL beat (kick and snare/claps "
    "with the main groove) first comes in. Answer ONLY with JSON, no prose: "
    '{"sections":[{"start":<sec>,"what":"<short>"}],"full_beat_drops_in":<sec>,"drums_first_enter":<sec>,"notes":"<short>"}'
)


def listen_check(path, limit):
    """Ask the TrueFoundry audio-understanding route; returns (parsed dict or None, raw text)."""
    import gemini  # same folder; stdlib only
    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", str(limit), "-i", path, "-ac", "1", "-ar", "16000", wav], check=True)
        text = gemini.listen(wav, LISTEN_PROMPT % limit)
    finally:
        os.remove(wav)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return (json.loads(m.group(0)) if m else None), text
    except ValueError:
        return None, text


def main():
    args = sys.argv[1:]
    listen = False
    opts = {"--window": 0.25, "--search": 30.0}
    pos = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--listen":
            listen = True
        elif a in opts and i + 1 < len(args):
            opts[a] = float(args[i + 1])
            i += 1
        elif a.startswith("-"):
            raise SystemExit(__doc__)
        else:
            pos.append(a)
        i += 1
    if not pos:
        raise SystemExit(__doc__)
    path = pos[0]
    if len(pos) > 1:  # legacy positionals: window seconds, search seconds
        opts["--window"] = float(pos[1])
    if len(pos) > 2:
        opts["--search"] = float(pos[2])
    win, limit = opts["--window"], opts["--search"]

    samples = decode(path, limit)
    series = rms_series(samples, win)
    if not series:
        raise SystemExit("no audio analysed")
    first = next((t for t, v in series if v > -45), None)
    print("first audible: %s" % ("%.2fs" % first if first is not None else "none in window"))

    cues = load_cues(path)
    if cues:
        grid, strong, tempo = cues
        print("beat grid: cues file (%.1f BPM, %d beats)" % (tempo or 0, len(grid)))
    else:
        grid, bpm = estimate_grid(samples, limit)
        strong = []
        if grid:
            print("beat grid: no cues file; estimated %.1f BPM from onset autocorrelation (approximate: confirm with --listen)" % bpm)
        else:
            print("beat grid: none (no cues file, tempo estimate failed); candidates below are raw, not beat-snapped")

    picked = energy_rises(series, win)
    for d, t in picked:
        line = "energy rise +%.1f dB at %.2fs" % (d, t)
        b = nearest(t, grid)
        if b is not None:
            line += "  -> beat %.2fs (%+.2fs)" % (b, b - t)
        s = nearest(t, strong)
        if s is not None:
            line += "  strong cue %.2fs (%+.2fs)" % (s, s - t)
        o = sharp_onset(samples, b if b is not None else t)
        if o is not None:
            line += "  sharpest hit %.2fs" % o
            bo = nearest(o, grid)
            if bo is not None:  # trust the hit only when it is close to the rise's own beat
                line += " => dropSeconds %.2f" % (bo if abs(bo - b) <= 0.15 else b)
        print(line)
    if not picked:
        print("no clear drop; use the first audible moment, or a beat from the cue file")

    if listen:
        parsed, text = listen_check(path, int(limit))
        print("--listen (gemini audio check):")
        if not parsed:
            print("  unparsed answer: " + text[:400])
        else:
            for sec in parsed.get("sections", []):
                print("  section %s: %s" % (sec.get("start"), sec.get("what")))
            for key in ("full_beat_drops_in", "drums_first_enter"):
                v = parsed.get(key)
                if isinstance(v, (int, float)):
                    b = nearest(v, grid)
                    print("  %s: %.2fs%s" % (key, v, "  -> beat %.2fs (%+.2fs)" % (b, b - v) if b is not None else ""))
            if parsed.get("notes"):
                print("  notes: %s" % parsed["notes"])
            v = parsed.get("full_beat_drops_in")
            if picked and isinstance(v, (int, float)):
                near = min(picked, key=lambda p: abs(p[1] - v))
                print("  nearest energy rise to the listen answer: %.2fs (%+.2fs apart)" % (near[1], near[1] - v))


if __name__ == "__main__":
    main()
