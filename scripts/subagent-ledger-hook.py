#!/usr/bin/env python3
"""subagent-ledger hook — log every delegation outcome to a JSONL ledger.

Fires on the `subagent_stop` shell-hook event (from tools/delegate_tool.py).
Payload arrives as JSON on stdin: parent_turn_id, child_session_id, child_role,
child_summary, child_status, duration_ms, plus model/task metadata.

Appends one line to ~/.hermes/tier_orchestrator/subagent_ledger.jsonl.
Never fails — a hook crash must not break the parent turn.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

LEDGER = Path.home() / ".hermes" / "tier_orchestrator" / "subagent_ledger.jsonl"


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "child_session_id": payload.get("child_session_id"),
        "child_role": payload.get("child_role"),
        "status": payload.get("child_status"),
        "duration_ms": payload.get("duration_ms"),
        "summary": (payload.get("child_summary") or "")[:200],
        "goal": (payload.get("goal") or payload.get("task") or "")[:120],
    }
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
