"""Voiceover (Gemini TTS) and audio listening (transcribe / review) through TrueFoundry.

Stdlib only, Python 3.9+. Secrets are read at runtime and never printed.

Key lookup, first match wins:
  TRUEFOUNDRY_API_KEY  environment, else the same name in ~/.hermes/.env
  GEMINI_API_KEY       optional direct-Gemini fallback, used only when no TrueFoundry key exists

Overrides (environment):
  LAUNCH_VIDEO_TTS_ACCOUNT  TrueFoundry TTS provider account   (default gemini-primary)
  LAUNCH_VIDEO_TTS_MODEL    TTS model                          (default gemini-3.8-flash-tts)
  LAUNCH_VIDEO_LISTEN_MODEL model for transcribe/review        (default gemini-group/gemini-3.5-flash)
  LAUNCH_VIDEO_TFY_BASE     gateway base URL                   (default https://<llm-gateway>.truefoundry.cloud)

CLI:
  python3 gemini.py tts "text" out.wav [voice]
  python3 gemini.py transcribe a.wav [b.wav ...]
  python3 gemini.py review mix.mp3 ["what to check"]
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import struct
import urllib.request

BASE = os.environ.get("LAUNCH_VIDEO_TFY_BASE", "https://<llm-gateway>.truefoundry.cloud").rstrip("/")
TTS_ACCOUNT = os.environ.get("LAUNCH_VIDEO_TTS_ACCOUNT", "gemini-primary")
TTS_MODEL = os.environ.get("LAUNCH_VIDEO_TTS_MODEL", "gemini-3.8-flash-tts")
LISTEN_MODEL = os.environ.get("LAUNCH_VIDEO_LISTEN_MODEL", "gemini-group/gemini-3.5-flash")
# Cloudflare in front of the gateway rejects Python's default User-Agent (error 1010).
UA = "launch-video/1.0 (+hermes)"
HERMES_ENV = os.path.expanduser("~/.hermes/.env")


def _from_env_file(name, path=None):
    try:
        with open(path or HERMES_ENV) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def tfy_key():
    return os.environ.get("TRUEFOUNDRY_API_KEY") or _from_env_file("TRUEFOUNDRY_API_KEY")


def _direct_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def backend():
    if tfy_key():
        return "truefoundry"
    if _direct_key():
        return "gemini"
    raise SystemExit("No key: set TRUEFOUNDRY_API_KEY (environment or ~/.hermes/.env), or GEMINI_API_KEY for direct Gemini.")


def _post(url, body, headers, timeout=600):
    h = {"Content-Type": "application/json", "User-Agent": UA}
    h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s from %s: %s" % (e.code, url.split("?")[0], e.read().decode(errors="replace")[:600]))


def _write_wav(path, pcm, rate=24000):
    """Wrap raw 16-bit mono PCM in a WAV header (no `wave` module: it drags in audioop)."""
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    with open(path, "wb") as fh:
        fh.write(header + b"data" + struct.pack("<I", len(pcm)) + pcm)


def tts(text, out_wav, voice="Charon"):
    """Synthesize `text` to a trimmed mono WAV. Plain text only: a style preamble makes lines much longer."""
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    if backend() == "truefoundry":
        url = "%s/api/llm/tts/%s/v1beta/models/%s:generateContent" % (BASE, TTS_ACCOUNT, TTS_MODEL)
        d = _post(url, body, {"x-tfy-api-key": tfy_key()})
    else:
        url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % TTS_MODEL
        d = _post(url, body, {"x-goog-api-key": _direct_key()})
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    raw = base64.b64decode(part["data"])
    mime = part.get("mimeType", "")
    rate = 24000
    if "rate=" in mime:
        rate = int(mime.split("rate=")[1].split(";")[0])
    tmp = out_wav + ".src.wav"
    if raw[:4] == b"RIFF":  # already a WAV container
        with open(tmp, "wb") as fh:
            fh.write(raw)
    else:  # raw 16-bit mono PCM (audio/L16;codec=pcm;rate=24000)
        _write_wav(tmp, raw, rate)
    # trim leading/trailing silence, normalise to 48 kHz mono
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af",
         "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
         "-ar", "48000", "-ac", "1", out_wav],
        check=True,
    )
    os.remove(tmp)
    return mime or "audio/wav"


def listen(path, instruction, model=None):
    """Send an audio file and an instruction to a Gemini model; return its text answer."""
    model = model or LISTEN_MODEL
    fmt = os.path.splitext(path)[1].lstrip(".").lower() or "wav"
    with open(path, "rb") as fh:
        data = base64.b64encode(fh.read()).decode()
    if backend() == "truefoundry":
        body = {"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "input_audio", "input_audio": {"data": data, "format": fmt}},
        ]}]}
        d = _post(BASE + "/api/llm/api/inference/openai/v1/chat/completions", body, {"Authorization": "Bearer " + tfy_key()})
        return (d["choices"][0]["message"]["content"] or "").strip()
    gmodel = model.split("/")[-1]
    mime = {"wav": "audio/wav", "mp3": "audio/mpeg"}.get(fmt, "audio/" + fmt)
    body = {"contents": [{"parts": [{"inlineData": {"mimeType": mime, "data": data}}, {"text": instruction}]}]}
    d = _post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % gmodel, body, {"x-goog-api-key": _direct_key()})
    return d["candidates"][0]["content"]["parts"][0]["text"].strip()


def transcribe(path):
    return listen(path, "Transcribe this audio exactly. Output only the words.")


REVIEW_PROMPT = (
    "You are an audio mixer reviewing the soundtrack of a short product video. Judge whether the "
    "voiceover is clearly intelligible over the music, whether the music ducks under speech, any "
    "clipping, abrupt cuts, or sound effects that are too loud or too quiet, and how the ending sounds. "
    "Give a short bullet list with timestamps for anything to fix."
)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "tts":
        print(tts(sys.argv[2], sys.argv[3], *(sys.argv[4:5] or [])))
    elif cmd == "transcribe":
        for p in sys.argv[2:]:
            print(os.path.basename(p), "->", transcribe(p))
    elif cmd == "review":
        print(listen(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else REVIEW_PROMPT))
    else:
        raise SystemExit(__doc__)
