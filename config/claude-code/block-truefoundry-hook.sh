#!/bin/sh
# Claude Code managed hook: refuse to run Claude Code against the TrueFoundry
# LLM gateway (pay-per-token anthropic-primary billing). Seatbelt, Fireworks
# and Anthropic direct login are untouched.
#
# Usage: block-truefoundry-hook.sh [prompt|session]
#   prompt  (UserPromptSubmit): exit 2 + stderr message blocks the prompt.
#   session (SessionStart):     prints {"continue": false, "stopReason": ...}.
#
# FAIL OPEN: any error, missing tool or unreadable env exits 0 silently. Only a
# positive match on a TrueFoundry endpoint blocks.

mode="${1:-prompt}"
MSG="Claude Code must not run on the TrueFoundry gateway (pay-per-token anthropic-primary billing). Use claude_orchestrate with model_provider=seatbelt (or fireworks as fallback)."

is_tf() { # stdin: text. Positive TrueFoundry endpoint match only.
  grep -Eiq '(ANTHROPIC_(BEDROCK_|VERTEX_)?BASE_URL)=[^[:space:]]*truefoundry' 2>/dev/null
}

hit=0

# 1. Own environment (normal case: hooks inherit Claude Code's env).
if env 2>/dev/null | is_tf; then hit=1; fi

# 2. Fallback if the hook env was scrubbed: read the environment of up to 3
#    ancestors (Claude Code itself is one of them). Linux: /proc/<pid>/environ.
#    macOS: kern.procargs2 via python3 (separates argv from env, so prompt text in
#    a command line can never match). Any failure falls through to allow.
darwin_env_match() { # $1 = pid; prints parent pid, exit 0 if env matches
  python3 - "$1" 2>/dev/null <<'PY'
import ctypes, ctypes.util, re, struct, subprocess, sys
pid = int(sys.argv[1])
libc = ctypes.CDLL(ctypes.util.find_library("c"))
mib = (ctypes.c_int * 3)(1, 49, pid)
size = ctypes.c_size_t(0)
if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
    sys.exit(3)
buf = ctypes.create_string_buffer(size.value)
if libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
    sys.exit(3)
raw = buf.raw[:size.value]
argc = struct.unpack("i", raw[:4])[0]
parts = raw[4:].split(b"\0")
i = 1
while i < len(parts) and parts[i] == b"":
    i += 1
env = [p for p in parts[i + argc:] if p]
pat = re.compile(rb"^ANTHROPIC_(BEDROCK_|VERTEX_)?BASE_URL=.*truefoundry", re.I)
ppid = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
print(ppid)
sys.exit(0 if any(pat.match(e) for e in env) else 1)
PY
}

if [ "$hit" = 0 ]; then
  pid="${PPID:-}"
  n=0
  while [ -n "$pid" ] && [ "$pid" -gt 1 ] 2>/dev/null && [ "$n" -lt 3 ]; do
    if [ -r "/proc/$pid/environ" ]; then
      if tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | is_tf; then hit=1; break; fi
      pid="$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null)"
    elif [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
      out="$(darwin_env_match "$pid")"; rc=$?
      if [ "$rc" = 0 ]; then hit=1; break; fi
      [ "$rc" = 1 ] || break
      pid="$out"
    else
      break
    fi
    n=$((n + 1))
  done
fi

[ "$hit" = 1 ] || exit 0

case "$mode" in
  session)
    printf '{"continue": false, "stopReason": "%s"}\n' "$MSG"
    exit 0
    ;;
  *)
    printf '%s\n' "$MSG" >&2
    exit 2
    ;;
esac
