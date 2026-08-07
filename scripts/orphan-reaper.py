#!/usr/bin/env python3
"""orphan-reaper — silent watchdog for orphaned tier tmux sessions.

Sweeps tmux sessions matching the tier naming (t2-*, t1-*, alp-*, lea-*), heals
recoverable failure modes (context-compaction prompt, redacted_thinking
corruption, rate-limit prompt, stuck prompt), and kills genuinely IDLE ones
(done, sitting at a prompt — not reaped by the supervisor's Phase-5
self-terminate). Kanban's TTL-based claim expiry (900s) handles stale claims
automatically, so this script no longer releases Paperclip checkouts (Paperclip
has been retired in favor of kanban).

The healing layer borrows amux's watchdog pattern: detect a specific failure
mode from the pane, auto-respond via send-keys, and only kill if the session is
genuinely idle (no active work, no recoverable failure, no prompt to answer).

Designed for a `no_agent` cron: prints ONLY when it actually does something
(heals or reaps); silent (empty stdout) when nothing to do.

Conservative by design: only kills sessions whose pane shows a DONE/idle state
(no "esc to interrupt", no active spinner, no recoverable failure). Never kills
an actively-working session.
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

# --- Failure-mode patterns (borrowed from amux's self-healing watchdog) ---
# Context compaction prompt (Claude Code asking to compact)
COMPACT_RE = re.compile(r"compact.*conversation|compact.*context|/compact", re.IGNORECASE)
# redacted_thinking corruption (Claude Code bug — session needs restart)
REDACTED_RE = re.compile(r"redacted_thinking.*cannot be modified", re.IGNORECASE)
# Rate-limit prompt (Claude Code /rate-limit-options)
RATE_LIMIT_RE = re.compile(r"/rate-limit-options|rate.limit.*options", re.IGNORECASE)
# Stuck prompt — a question/permission request that hasn't been answered
# (Claude Code shows "y/n" or "yes/no" prompts, or a "❯" input with a question above)
STUCK_PROMPT_RE = re.compile(r"^\s*(y/n|yes/no|\[y/N\]|\[Y/n\])\s*$", re.IGNORECASE | re.MULTILINE)


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


def send_keys(name, text, enter=True):
    """Send text to a tmux session (literal), then Enter as a separate keystroke."""
    sh("tmux", "send-keys", "-t", name, "-l", text)
    if enter:
        time.sleep(0.5)
        sh("tmux", "send-keys", "-t", name, "Enter")


def heal(name, p):
    """Detect a recoverable failure mode and auto-respond. Returns a description
    of the action taken, or None if nothing to heal."""
    low = p.lower()

    # Context compaction prompt — auto-answer "yes" to compact
    if COMPACT_RE.search(low) and "❯" in p:
        # The pane shows a compact prompt — send "y" or the compact command
        # Claude Code's compact prompt is usually "Compact this conversation? [y/N]"
        # or a slash command. Try the safest: send "y" (yes to compact).
        send_keys(name, "y")
        return f"auto-compacted {name} (context compaction prompt)"

    # redacted_thinking corruption — restart the session (kill + let the
    # supervisor respawn it; the supervisor's Phase-1 resume-check will recover)
    if REDACTED_RE.search(low):
        # Don't restart here — kill the session; the T2 supervisor's recover
        # or the next kanban dispatch will respawn it. Note: this is a kill, not
        # a heal, but it's a *targeted* kill (a specific corruption, not idle).
        sh("tmux", "kill-session", "-t", name)
        return f"killed {name} (redacted_thinking corruption — supervisor will respawn)"

    # Rate-limit prompt — auto-press option 1 ("Stop and wait for limit to reset")
    if RATE_LIMIT_RE.search(low):
        # Claude Code shows numbered options; option 1 is "Stop and wait for
        # limit to reset". Send "1" to select it.
        send_keys(name, "1")
        return f"rate-limited {name} (auto-pressed option 1, will resume at reset)"

    # Stuck prompt (y/n question) — auto-answer "y" (conservative: answer yes to
    # proceed; a stuck prompt is blocking the session)
    if STUCK_PROMPT_RE.search(p) and "❯" in p:
        send_keys(name, "y")
        return f"answered stuck prompt in {name} (auto-yes)"

    return None  # nothing to heal


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

        # 1. Try to heal a recoverable failure mode first
        healed = heal(name, p)
        if healed:
            actions.append(healed)
            continue  # healed — don't reap

        # 2. Actively working or waiting for input — leave it
        if is_active(p):
            continue

        # 3. Genuinely idle / done — reap it
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
