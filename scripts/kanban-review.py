#!/usr/bin/env python3
"""kanban-review — drive kanban task transitions the CLI doesn't expose.

Kanban has first-class `review` and `done` statuses, but the CLI has gaps for a
tmux-driven tier flow: no verb sets `review`, and `hermes kanban complete` refuses
a task already in `review` (it only accepts running|ready). This helper does the
minimal state transitions + audit events the dispatcher would, WITHOUT patching
core (kanban_db.py gets overwritten on `hermes update`).

Tier-flow statuses:
  running  → T2 implementing / testing / gating
  review   → PR is up, awaiting the human's CODE REVIEW
  blocked  → awaiting the human's manual INPUT (`hermes kanban block`)
  done     → merged (terminal)

Transitions this supports:
  running -> review   (T2: PR up)          kanban-review <id> --to review
  review  -> running  (reviewer sent back) kanban-review <id> --to running
  review  -> done     (merged; CLI can't)  kanban-review <id> --to done [--result ...]
  running -> done     (fallback)           kanban-review <id> --to done

Usage:
  kanban-review <task_id> --to {review|running|done} [--board <slug>]
                [--reason "..."] [--result "..."]

Back-compat: no --to and no --revert  => review;  --revert => running.

Exit codes: 0 ok, 1 task not found / wrong source state, 2 usage error.
"""
import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

HERMES = Path.home() / ".hermes"

# Allowed source states for each destination (guards against nonsense transitions).
_ALLOWED_SOURCES = {
    "review": {"running"},
    "running": {"review"},           # revert
    "done": {"review", "running", "archived"},   # merge-complete (CLI complete only does running|ready; archived = fix a mis-archive)
}
_EVENT = {
    "review": "moved_to_review",
    "running": "review_reverted",
    "done": "completed",
}


def _db_path(board: Optional[str]) -> Path:
    """Resolve the kanban DB for a board. Default board is top-level;
    named boards have their own DB under boards/<slug>/kanban.db."""
    if board and board != "default":
        p = HERMES / "kanban" / "boards" / board / "kanban.db"
        if p.exists():
            return p
    return HERMES / "kanban.db"


def main() -> int:
    ap = argparse.ArgumentParser(prog="kanban-review")
    ap.add_argument("task_id")
    ap.add_argument("--board", default=None)
    ap.add_argument("--to", choices=["review", "running", "done"], default=None,
                    help="destination status")
    ap.add_argument("--reason", default="")
    ap.add_argument("--result", default="", help="result text (for --to done)")
    ap.add_argument("--revert", action="store_true",
                    help="back-compat: review -> running")
    args = ap.parse_args()

    dst = args.to or ("running" if args.revert else "review")
    allowed = _ALLOWED_SOURCES[dst]

    db = _db_path(args.board)
    if not db.exists():
        print(f"kanban DB not found for board {args.board or 'default'}: {db}", file=sys.stderr)
        return 1

    now = int(time.time())
    con = sqlite3.connect(str(db))
    try:
        con.execute("PRAGMA journal_mode=WAL")
        row = con.execute("SELECT status FROM tasks WHERE id=?", (args.task_id,)).fetchone()
        if row is None:
            print(f"task {args.task_id} not found on board {args.board or 'default'}", file=sys.stderr)
            return 1
        src = row[0]
        if src == dst:
            print(f"{args.task_id}: already '{dst}' — no-op")
            return 0
        if src not in allowed:
            print(f"task {args.task_id} is '{src}', cannot move to '{dst}' "
                  f"(allowed from: {sorted(allowed)})", file=sys.stderr)
            return 1

        if dst == "done":
            con.execute(
                "UPDATE tasks SET status='done', completed_at=?, "
                "result=COALESCE(NULLIF(?, ''), result), claim_lock=NULL, claim_expires=NULL "
                "WHERE id=? AND status=?",
                (now, args.result, args.task_id, src),
            )
        else:
            con.execute(
                "UPDATE tasks SET status=? WHERE id=? AND status=?",
                (dst, args.task_id, src),
            )
        con.execute(
            "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?,?,?,?)",
            (args.task_id, _EVENT[dst],
             json.dumps({"from": src, "to": dst, "reason": args.reason, "result": args.result}), now),
        )
        con.commit()
    finally:
        con.close()

    tail = args.reason or args.result
    print(f"{args.task_id}: {src} -> {dst}" + (f" ({tail})" if tail else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
