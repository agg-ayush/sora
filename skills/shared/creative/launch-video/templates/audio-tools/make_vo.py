"""Generate every VO clip in vo.json -> public/vo/<id>.wav + durations.json.

Plain-text TTS through TrueFoundry (see gemini.py), loudness-normalised, then transcribed
back; retries a clip (up to 4x) if the transcript has words not in the script.
Usage: python3 make_vo.py            # all clips
       python3 make_vo.py hook intro  # only these ids
       python3 make_vo.py --silent    # no API calls: silent stand-ins for clips that don't exist
                                      # yet (length from durations.json, else ~3 words/s), so the
                                      # project previews and renders before the voice is recorded
"""
import json
import os
import re
import struct
import subprocess
import sys

import gemini

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "../public/vo")
os.makedirs(OUT, exist_ok=True)

cfg = json.load(open(os.path.join(HERE, "vo.json")))
dur_path = os.path.join(OUT, "durations.json")
durs = json.load(open(dur_path)) if os.path.exists(dur_path) else {}
silent = "--silent" in sys.argv
ids = [a for a in sys.argv[1:] if not a.startswith("--")] or list(cfg["lines"])


def words(t):
    t = t.lower().replace("helpdesk", "help desk").replace("chat gpt", "chatgpt")
    t = t.replace("-", " ")
    return re.sub(r"[^a-z0-9 ]", " ", t).split()


if silent:
    rate = 8000
    for k in ids:
        out = os.path.join(OUT, f"{k}.wav")
        if os.path.exists(out):
            continue
        secs = durs.get(k) or max(1.0, len(cfg["lines"][k].split()) / 3.0)
        pcm = b"\x00\x00" * int(secs * rate)
        hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        with open(out, "wb") as fh:
            fh.write(hdr + b"data" + struct.pack("<I", len(pcm)) + pcm)
        durs[k] = round(secs, 3)
        print("silent stand-in:", k, durs[k])
    json.dump(durs, open(dur_path, "w"), indent=1)
    sys.exit(0)

for k in ids:
    text = cfg["lines"][k]
    want = set(words(text))
    out = os.path.join(OUT, f"{k}.wav")
    for attempt in range(4):
        raw = out + ".raw.wav"
        gemini.tts(text, raw, cfg.get("voice", "Charon"))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", "loudnorm=I=-16:TP=-1.5:LRA=7", "-ar", "48000", out], check=True)
        os.remove(raw)
        heard = gemini.transcribe(out)
        extra = [w for w in words(heard) if w not in want]
        print(f"{k} try{attempt}: {heard!r} extra={extra}")
        if not extra:
            break
    if extra:
        print(f"WARNING {k}: transcript still differs after 4 tries; rephrase the line in vo.json")
    durs[k] = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]))

json.dump(durs, open(dur_path, "w"), indent=1)
print("durations:", durs)
