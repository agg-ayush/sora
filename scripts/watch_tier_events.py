#!/usr/bin/env python3
"""watch_tier_events — macOS notifications for tier task state changes.

Polls every kanban board DB for NEW task_events of kind review_requested or
blocked, and fires a native macOS notification for each one you haven't seen
yet. This surfaces "T2 raised a PR" (review) and "T2 needs you" (blocked) in
the terminal/Mac notification center — not buried in Telegram.

Watermark-deduped (same pattern as the other watchers). Silent on no new
events. Runs from a no_agent cron.

Config: reads ~/.hermes/scripts/watch_tier_events.json if present:
    {"boards": ["alpha-learn-content-gen", "learning-app"], "sound": true}
Defaults: every board dir under ~/.hermes/kanban/boards/, sound on.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

STATE = Path.home() / ".hermes" / "watcher-state" / "watch_tier_events.json"
BOARDS_ROOT = Path.home() / ".hermes" / "kanban" / "boards"
CONFIG = Path.home() / ".hermes" / "scripts" / "watch_tier_events.json"
# Events that mean "a T2 finished or needs you".
WATCH_KINDS = ("review_requested", "blocked")


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(STATE)


def _notify(title: str, body: str, sound: bool) -> None:
    safe_t = title.replace("\\", "\\\\").replace('"', '\\"')
    safe_b = body.replace("\\", "\\\\").replace('"', '\\"')[:220]
    sound_clause = ' sound name "Glass"' if sound else ""
    script = f'display notification "{safe_b}" with title "{safe_t}"{sound_clause}'
    subprocess_run = ["osascript", "-e", script]
    try:
        os.spawnvp(os.P_NOWAIT, "osascript", subprocess_run)
    except Exception:
        pass


def main() -> int:
    cfg = {}
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text())
        except Exception:
            cfg = {}
    sound = bool(cfg.get("sound", True))
    boards = cfg.get("boards") or sorted(p.name for p in BOARDS_ROOT.glob("*") if (p / "kanban.db").exists())

    state = _load_state()
    emitted = 0
    for board in boards:
        db = BOARDS_ROOT / board / "kanban.db"
        if not db.exists():
            continue
        last_seen = int(state.get(board, 0))
        try:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT e.id, e.task_id, e.kind, e.created_at, t.title "
                "FROM task_events e JOIN tasks t ON t.id = e.task_id "
                "WHERE e.kind IN ({}) AND e.created_at > ? "
                "ORDER BY e.created_at ASC".format(",".join("?" * len(WATCH_KINDS))),
                (*WATCH_KINDS, last_seen),
            ).fetchall()
            conn.close()
        except Exception:
            continue
        newest = last_seen
        for r in rows:
            newest = max(newest, int(r["created_at"]))
            kind = r["kind"]
            title_txt = (r["title"] or "").strip()[:80]
            if kind == "review_requested":
                _notify("T2 raised a PR", f"[{board}] {r['task_id']} — {title_txt}", sound)
            else:
                _notify("T2 blocked — needs you", f"[{board}] {r['task_id']} — {title_txt}", sound)
            emitted += 1
        if newest > last_seen:
            state[board] = newest
    if emitted == 0:
        return 0
    _save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
