#!/usr/bin/env python3
"""orphan-reaper — silent watchdog for orphaned tier tmux sessions.

Sweeps tmux sessions matching the tier naming (t2-*, t1-*, alp-*, lea-*) and kills
IDLE ones (done, sitting at a prompt — not reaped by the supervisor's Phase-5
self-terminate). Kanban's TTL-based claim expiry (900s) handles stale claims
automatically, so this script no longer releases Paperclip checkouts (Paperclip
has been retired in favor of kanban).

Designed for a `no_agent` cron: prints ONLY when it actually reaps something
(stdout is delivered verbatim); silent (empty stdout) when nothing to do.

Conservative by design: only touches sessions whose pane shows a DONE/idle state
(no "esc to interrupt", no active spinner). Never kills an actively-working session.
"""
import json
import re
import subprocess
import time
from pathlib import Path

TASKS = Path.home() / ".hermes" / "tasks"
# session-name prefixes we own (tier supervisors + plugin worker sessions)
PREFIXES = ("t2-", "t1-", "alp-", "lea-")
# pane markers that mean "actively working" — never reap these
ACTIVE_MARKERS = ("esc to interrupt",)


def sh(*args, timeout=15):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return subprocess.CompletedProcess(args, 1, "", "timeout")


def tmux_sessions():
    r = sh("tmux", "ls")
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        name = line.split(":", 1)[0].strip()
        if name and any(name.startswith(p) for p in PREFIXES):
            out.append(name)
    return out


def pane(name):
    r = sh("tmux", "capture-pane", "-t", name, "-p")
    return r.stdout if r.returncode == 0 else ""


def is_active(p):
    """True if the session is actively working OR waiting for input (alive, not idle)."""
    low = p.lower()
    if any(m in low for m in ACTIVE_MARKERS):
        return True  # actively working (spinner + "esc to interrupt")
    # A session at a prompt waiting for a steer (needs_input) is NOT idle —
    # killing it would lose the in-flight T2 conversation. Detect the Hermes/Claude
    # input prompt marker. This mirrors the plugin's _session_state() logic.
    lines = [l for l in p.splitlines() if l.strip()]
    if lines and "❯" in lines[-1]:
        return True  # at a prompt, waiting for steer — alive
    return False


def main():
    actions = []
    for name in tmux_sessions():
        p = pane(name)
        if not p.strip():
            continue
        if is_active(p):
            continue  # actively working — leave it
        # IDLE / done session → reap it
        sh("tmux", "kill-session", "-t", name)
        actions.append(f"reaped idle session {name}")

    # NOTE: kanban's TTL-based claim expiry (900s) handles stale claims from
    # dead sessions automatically — no manual release needed (Paperclip retired).

    if actions:
        print(f"[orphan-reaper {time.strftime('%Y-%m-%d %H:%M')}] {len(actions)} action(s):")
        for a in actions:
            print(f"  - {a}")
    # else: silent (empty stdout) — nothing to report


if __name__ == "__main__":
    main()
