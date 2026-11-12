#!/usr/bin/env python3
"""red-gate hook: block source edits until a failing (RED) test run is saved.

PreToolUse hook for Write, Edit, MultiEdit and NotebookEdit. Usage:
    red-gate.py <task-dir>
Payload arrives as JSON on stdin. The gate opens when <task-dir>/evidence has a
red-*.txt file that is non-empty and whose output shows a failing test.
Edits to test files, docs, config and anything under the task dir are always allowed.

Fails open: any error in the hook itself prints a warning and allows the edit.
Set HERMES_RED_GATE=off to disable.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte",
    ".go", ".rs", ".java", ".kt", ".rb", ".php", ".cs", ".swift", ".scala",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".sh",
}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
TEST_DIR_PARTS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "__mocks__", "fixtures", "testing"}
TEST_NAME = re.compile(r"(^test_.*\.py$|_test\.(py|go|rs|rb)$|\.(test|spec)\.[cm]?[jt]sx?$|^conftest\.py$|Test\.(java|kt)$|Tests?\.cs$)")
FAILURE = re.compile(
    r"(\b[1-9]\d* (failed|failing|failures?|errors?)\b"
    r"|\bFAILED\b|\bFAIL\b|AssertionError|AssertionFailed|\bnot ok\b"
    r"|Tests?:\s+[^\n]*\b[1-9]\d* failed"
    r"|[✗✕×]|\bFailures?: [1-9])"
)


def is_test_path(path: Path) -> bool:
    if TEST_NAME.search(path.name):
        return True
    return any(part.lower() in TEST_DIR_PARTS for part in path.parts[:-1])


def red_evidence(task_dir: Path) -> str | None:
    """Return the name of a red file that shows a failing test, else None."""
    for f in sorted((task_dir / "evidence").glob("red-*.txt")):
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        body = text.split("\n", 1)[1] if "\n" in text else ""
        if body.strip() and FAILURE.search(body):
            return f.name
    return None


def decide(payload: dict, task_dir: Path) -> str | None:
    """Return a denial reason, or None to allow."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not raw:
        return None
    path = Path(raw)
    if path.suffix.lower() not in CODE_EXT or is_test_path(path):
        return None
    try:
        path.resolve().relative_to(task_dir.resolve())
        return None
    except ValueError:
        pass
    if red_evidence(task_dir):
        return None
    return (
        "RED gate: no failing test run is saved yet. Write or change the tests from the design's "
        "verification table, run them on the unchanged code and save the output to "
        f"{task_dir}/evidence/red-<unit>.txt (first line the exact test command, then the raw runner "
        "output showing the failure). Then edit source."
    )


def main() -> int:
    if os.environ.get("HERMES_RED_GATE", "").lower() == "off" or len(sys.argv) < 2:
        return 0
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        reason = decide(payload if isinstance(payload, dict) else {}, Path(sys.argv[1]))
    except Exception as exc:  # noqa: BLE001
        print(f"red-gate hook error, allowing edit: {exc}", file=sys.stderr)
        return 0
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
