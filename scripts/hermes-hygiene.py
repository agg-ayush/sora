#!/usr/bin/env python3
"""hermes-hygiene — weekly storage + health maintenance for the tier system.

Runs the maintenance the tier system's growth patterns need and that nothing
else reclaims:

  * ``hermes checkpoints prune``  — worktree checkpoints outlive the tmux
    sessions the orphan-reaper kills, so they accumulate unbounded.
  * ``hermes sessions optimize-storage`` — VACUUM + FTS rebuild. Session
    auto-archive soft-hides rows but never shrinks the file.
  * ``hermes doctor``            — surfaces WAL/disk/dependency problems.

Designed for a ``no_agent`` cron: prints ONLY when something was reclaimed or
doctor found an issue; silent otherwise.

Thresholds are deliberately conservative — this deletes derived artifacts
(checkpoints, index pages), never session history.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Only VACUUM when the DB has grown past this — the rebuild is expensive.
VACUUM_ABOVE_MB = 750
STATE_DB = Path.home() / ".hermes" / "state.db"


def hermes(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    exe = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    try:
        return subprocess.run(
            [exe, *args], capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001 — a broken hermes must not crash the cron
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def db_size_mb() -> float:
    try:
        return STATE_DB.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def prune_checkpoints() -> str | None:
    """Drop orphaned/stale worktree checkpoints. Returns a line if it reclaimed."""
    r = hermes("checkpoints", "prune", "-f", timeout=300)
    if r.returncode != 0:
        return f"checkpoints prune failed: {(r.stderr or r.stdout).strip()[:120]}"
    m = re.search(r"Bytes reclaimed:\s*([\d.]+)\s*(\w+)", r.stdout)
    if not m:
        return None
    amount, unit = float(m.group(1)), m.group(2)
    if unit.upper().startswith("B") or amount == 0:
        return None
    return f"checkpoints: reclaimed {amount:.1f} {unit}"


def optimize_sessions() -> str | None:
    """VACUUM + FTS rebuild, but only once the DB is actually large."""
    before = db_size_mb()
    if before < VACUUM_ABOVE_MB:
        return None
    # The command prompts interactively; feed it a confirmation.
    exe = shutil.which("hermes") or str(Path.home() / ".local" / "bin" / "hermes")
    try:
        subprocess.run(
            [exe, "sessions", "optimize-storage"], input="y\n",
            capture_output=True, text=True, timeout=1800,
        )
    except Exception as exc:  # noqa: BLE001
        return f"sessions optimize-storage failed: {exc}"
    after = db_size_mb()
    if after >= before - 1:
        return None
    return f"state.db: {before:.0f} MB -> {after:.0f} MB (reclaimed {before - after:.0f} MB)"


def doctor_issues() -> str | None:
    """Report doctor's failures/warnings, not its full output."""
    r = hermes("doctor", timeout=300)
    bad = [
        ln.strip() for ln in (r.stdout or "").splitlines()
        if ln.lstrip().startswith(("✗", "⚠"))
    ]
    if not bad:
        return None
    return "doctor:\n" + "\n".join(f"    {ln}" for ln in bad[:8])


def main() -> int:
    lines = [ln for ln in (prune_checkpoints(), optimize_sessions(), doctor_issues()) if ln]
    if lines:
        print(f"[hermes-hygiene {time.strftime('%Y-%m-%d %H:%M')}]")
        for ln in lines:
            print(f"  - {ln}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
