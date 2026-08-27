#!/usr/bin/env python3
"""dead-supervisor-alert — tell you when a T2 supervisor died mid-task.

The tier system already fails safely when a supervisor dies: kanban's TTL
expires the claim so the card returns to `ready`, and orphan-reaper cleans up
the tmux session. What neither does is say so. This script exists ONLY to
notify the human — it does not reclaim, release, or kill anything.

Two signatures, both meaning "a worker started this and stopped existing":

  * ABANDONED — `started_at` set, `completed_at` null, status back to a
    claimable state. The claim expired without the work finishing.
  * STALLED — still `running`, but the heartbeat stopped (30+ min). The plugin
    heartbeats a claim for as long as the session lives, so silence means the
    worker is gone while the claim has yet to lapse.

Unpushed commits in the task's worktree are reported too, because that is
where the real loss hides: the branch on origin looks complete while the last
commit never left the machine.

Watermark-deduped (same pattern as the other watchers): silent when nothing
new, markdown on findings. Runs from a no_agent cron.

    hermes cron create "every 10m" --name dead-supervisor-alert \
      --script dead-supervisor-alert.py --no-agent --deliver telegram
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _watermark import Watermark  # type: ignore

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
WORKTREE_ROOT = Path(os.environ.get("ORCHESTRATE_WORKTREES")
                     or Path.home() / ".orchestrate-worktrees")

# Statuses a card can hold while nobody is working it. A task that reached one
# of these after `started_at` was set had its claim expire rather than finish.
CLAIMABLE = ("ready", "triage", "backlog", "todo")


def board_dbs() -> list[tuple[str, Path]]:
    """(board_name, db_path) for every live board. Archived boards are skipped."""
    found: list[tuple[str, Path]] = []
    default = HERMES_HOME / "kanban.db"
    if default.exists():
        found.append(("default", default))
    boards = HERMES_HOME / "kanban" / "boards"
    if boards.is_dir():
        for d in sorted(boards.iterdir()):
            if d.name.startswith("_") or not (d / "kanban.db").exists():
                continue
            found.append((d.name, d / "kanban.db"))
    return found


def unpushed(branch: str | None) -> int:
    """Commits in the task's worktree that never reached origin, or -1 if unknown."""
    if not branch:
        return -1
    wt = WORKTREE_ROOT / branch
    if not (wt / ".git").exists():
        return -1
    try:
        proc = subprocess.run(
            ["git", "-C", str(wt), "rev-list", "--count", "@{upstream}..HEAD"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return -1
    if proc.returncode != 0:
        return -1
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return -1


def scan(db_path: Path, stale_cut: int) -> list[dict]:
    """Abandoned/stalled tasks on one board.

    A query error is raised rather than swallowed: this watcher exists to break
    a silence, so degrading to "no findings" on a schema change would reproduce
    the exact failure it is meant to catch.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"""
            SELECT id, title, status, started_at, last_heartbeat_at, branch_name
            FROM tasks
            WHERE completed_at IS NULL
              AND started_at IS NOT NULL
              AND ( status IN ({','.join('?' * len(CLAIMABLE))})
                    OR (status = 'running'
                        AND COALESCE(last_heartbeat_at, started_at) < ?) )
            """,
            (*CLAIMABLE, stale_cut),
        ).fetchall()
    finally:
        con.close()
    return [dict(r) for r in rows]


def main() -> int:
    p = argparse.ArgumentParser(description="Alert when a T2 supervisor dies mid-task.")
    p.add_argument("--stale-minutes", type=int, default=30,
                   help="Heartbeat silence before a running task counts as dead (default: 30)")
    args = p.parse_args()

    now = int(time.time())
    stale_cut = now - args.stale_minutes * 60

    boards = board_dbs()
    if not boards:
        print(f"dead-supervisor-alert: no kanban DB under {HERMES_HOME}", file=sys.stderr)
        return 2

    findings: list[dict] = []
    for name, db in boards:
        try:
            for row in scan(db, stale_cut):
                row["board"] = name
                # The heartbeat is part of the key so a task that dies, gets
                # retried and dies again alerts each time — while a card left
                # sitting in `ready` does not re-alert every 10 minutes.
                row["id_key"] = f"{name}:{row['id']}:{row.get('last_heartbeat_at') or 0}"
                findings.append(row)
        except sqlite3.Error as e:
            print(f"dead-supervisor-alert: cannot read board {name} ({e}) — schema changed?",
                  file=sys.stderr)
            return 2

    wm = Watermark.load("dead-supervisor-alert")
    fresh = wm.filter_new(findings, id_key="id_key")
    try:
        wm.save()
    except OSError as e:
        # Without a saved watermark every run re-alerts, which trains you to
        # mute the channel — the same silence, arrived at differently.
        print(f"dead-supervisor-alert: cannot save watermark: {e}", file=sys.stderr)
        return 2

    lines: list[str] = []
    for f in fresh:
        hb = f.get("last_heartbeat_at") or f.get("started_at") or now
        quiet = max(0, now - int(hb)) // 60
        kind = "stopped responding" if f["status"] == "running" else "was abandoned"
        lines.append(f"## Supervisor {kind}: {f['board']}/{f['id']}")
        lines.append(f"{(f.get('title') or '').strip()}")
        lines.append("")
        lines.append(f"- Status is `{f['status']}`, silent for {quiet} min.")
        branch = f.get("branch_name")
        ahead = unpushed(branch)
        if ahead > 0:
            lines.append(f"- **{ahead} commit(s) never pushed** in "
                         f"`{WORKTREE_ROOT}/{branch}` — push or lose them.")
        elif ahead == 0:
            lines.append(f"- Branch `{branch}` has nothing unpushed.")
        elif branch:
            # Never report "nothing unpushed" for a worktree we failed to read —
            # that is the reassurance this alert exists to avoid giving.
            lines.append(f"- Could not check `{WORKTREE_ROOT}/{branch}` for unpushed "
                         f"work (worktree gone?) — check it by hand.")
        lines.append("")

    if lines:
        sys.stdout.write("\n".join(lines).rstrip() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
