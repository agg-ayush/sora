#!/usr/bin/env python3
"""auth-canary — alert when agents are running but no model is answering.

Sessions keep starting but the window's output tokens are exactly zero. Output
tokens are produced only by a model that actually answered, so N sessions and
no output means every call is failing — an expired gateway JWT, a revoked key,
a model name the gateway won't route. The logs still look busy, which is what
makes this worth alarming on: `hermes doctor` is green, the gateway is up, and
no work is being done.

This is the canary half of colleague's cost-guard.py with the ceiling/budget
check dropped — we don't gate spend here, we only want to know when the auth
layer has silently died.

Watermark-deduped (same pattern as the other watchers): silent on success,
markdown on failure. Runs from a no_agent cron.

    hermes cron create "every 15m" --name auth-canary \
      --script auth-canary.py --no-agent --deliver telegram
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _watermark import Watermark  # type: ignore

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
STATE_DB = HERMES_HOME / "state.db"


def _query(db: sqlite3.Connection, sql: str, cutoff: float) -> int:
    row = db.execute(sql, (cutoff,)).fetchone()
    return int(row[0] or 0)


def main() -> int:
    p = argparse.ArgumentParser(description="Alert when sessions run but no model answers.")
    p.add_argument("--window", type=int, default=60,
                   help="Canary window in minutes (default: 60)")
    p.add_argument("--sessions", type=int, default=6,
                   help="Sessions started with zero output before alarming (default: 6)")
    args = p.parse_args()

    if not STATE_DB.exists():
        print(f"auth-canary: no session DB at {STATE_DB}", file=sys.stderr)
        return 2

    try:
        db = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    except sqlite3.Error as e:
        print(f"auth-canary: cannot open {STATE_DB}: {e}", file=sys.stderr)
        return 2

    now = time.time()
    try:
        cut = now - args.window * 60
        started = _query(db, "SELECT COUNT(*) FROM sessions WHERE started_at >= ?", cut)
        produced = _query(db, "SELECT COALESCE(SUM(output_tokens), 0) "
                              "FROM session_model_usage WHERE last_seen >= ?", cut)
    except sqlite3.Error as e:
        # A schema change upstream must not degrade to "no alerts" — that is
        # the silent failure this script exists to prevent.
        print(f"auth-canary: session store query failed ({e}) — schema changed?",
              file=sys.stderr)
        return 2
    finally:
        db.close()

    dead = started >= args.sessions and produced == 0

    # Watermark dedup: while the outage persists we alert once per window
    # rollover (the id key is the hour bucket), not every cron tick. When the
    # outage clears, nothing is emitted and the next outage alerts fresh.
    wm = Watermark.load("auth-canary")
    findings = []
    if dead:
        bucket = int(now // (args.window * 60))
        findings.append({
            "id": f"dead-{bucket}",
            "started": started,
            "window": args.window,
        })
    fresh = wm.filter_new(findings, id_key="id")
    try:
        wm.save()
    except OSError as e:
        # Without a saved watermark every run re-alerts, which trains you to
        # mute the channel — the same silence, arrived at differently.
        print(f"auth-canary: cannot save watermark: {e}", file=sys.stderr)
        return 2

    if not fresh:
        return 0

    f = fresh[0]
    sys.stdout.write(
        f"## Agents are running but no model is answering\n"
        f"{f['started']} sessions started in the last {f['window']}m and produced "
        f"**0 output tokens**. Every model call is failing — check the gateway JWT "
        f"(`hermes doctor`, then the `hermes-gateway-jwt` keychain item).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
