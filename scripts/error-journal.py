#!/usr/bin/env python3
"""Error journal for the tier orchestrator — JSONL ledger + threshold-based
auto-promotion to candidate skills + prompt-injection helper.

Borrowed from sentinel's learning/error_journal.py + learning/skillbook.py,
adapted to a single-file CLI with zero external deps.

Storage:
  journal:     ~/.hermes/tier_orchestrator/error_journal.jsonl
  auto skills: ~/.hermes/tier_orchestrator/auto_skills/<error_type>.md

Commands:
  record  <task_id> <agent_type> <error_type> <signal_trace> <what_should_have_happened>
  inject  <agent_type>
  patterns [--threshold N]
  promote [--threshold N]
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_DIR = Path.home() / ".hermes" / "tier_orchestrator"
JOURNAL_PATH = JOURNAL_DIR / "error_journal.jsonl"
AUTO_SKILLS_DIR = JOURNAL_DIR / "auto_skills"

DEFAULT_THRESHOLD = 3
ENV_THRESHOLD = "TIER_ERROR_PROMOTE_THRESHOLD"

AUTO_PROMOTED_HEADER = "[auto-promoted, needs-review]"

# ---------------------------------------------------------------------------
# Journal primitives
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    AUTO_SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def append_entry(
    task_id: str,
    agent_type: str,
    error_type: str,
    signal_trace: str,
    what_should_have_happened: str,
    prompt_snippet: str = "",
) -> dict:
    """Append one failure entry to the JSONL journal."""
    _ensure_dirs()
    entry = {
        "timestamp": _now(),
        "task_id": task_id,
        "agent_type": agent_type,
        "error_type": error_type,
        "signal_trace": signal_trace,
        "what_should_have_happened": what_should_have_happened,
        "prompt_snippet": prompt_snippet[:500],
    }
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_entries() -> list[dict]:
    """Read every journal entry (skip malformed lines)."""
    if not JOURNAL_PATH.exists():
        return []
    entries: list[dict] = []
    for line in JOURNAL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _threshold() -> int:
    raw = os.environ.get(ENV_THRESHOLD, "")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_THRESHOLD


def count_error_types(agent_type: str | None = None) -> Counter:
    entries = read_entries()
    if agent_type:
        entries = [e for e in entries if e.get("agent_type") == agent_type]
    return Counter(e.get("error_type", "unknown") for e in entries)

# ---------------------------------------------------------------------------
# Auto-promotion (threshold check on read)
# ---------------------------------------------------------------------------

def patterns_above_threshold(
    threshold: int | None = None,
) -> list[dict]:
    """Return error_types occurring >= threshold, with representative details."""
    thr = threshold if threshold is not None else _threshold()
    entries = read_entries()
    by_type: dict[str, list[dict]] = {}
    for e in entries:
        et = e.get("error_type", "unknown")
        by_type.setdefault(et, []).append(e)

    results = []
    for et, occurrences in by_type.items():
        if len(occurrences) < thr:
            continue
        latest = occurrences[-1]
        results.append(
            {
                "error_type": et,
                "count": len(occurrences),
                "agent_types": sorted(
                    {o.get("agent_type", "unknown") for o in occurrences}
                ),
                "latest_signal_trace": latest.get("signal_trace", ""),
                "latest_fix": latest.get("what_should_have_happened", ""),
                "first_seen": occurrences[0].get("timestamp", ""),
                "last_seen": latest.get("timestamp", ""),
            }
        )
    return sorted(results, key=lambda r: r["count"], reverse=True)


def _skill_path(error_type: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in error_type)
    return AUTO_SKILLS_DIR / f"{safe}.md"


def promote_patterns(threshold: int | None = None) -> list[Path]:
    """Write candidate-skill files for every error_type above threshold.

    Idempotent: rewrites the file each time so counts/fixes stay fresh.
    Returns list of paths written.
    """
    _ensure_dirs()
    written: list[Path] = []
    for p in patterns_above_threshold(threshold):
        path = _skill_path(p["error_type"])
        agents = ", ".join(p["agent_types"])
        body = f"""{AUTO_PROMOTED_HEADER}
# Candidate skill: {p['error_type']}

- **Occurrences:** {p['count']}
- **Agent types affected:** {agents}
- **First seen:** {p['first_seen']}
- **Last seen:** {p['last_seen']}

## Signal trace (what was misread)
{p['latest_signal_trace']}

## What should have happened
{p['latest_fix']}

## Rule
When working as any of ({agents}), avoid the `{p['error_type']}` pattern:
{p['latest_fix']}
"""
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def load_active_rules(agent_type: str | None = None) -> list[dict]:
    """Read promoted candidate skills and return their rule blocks.

    Only patterns that are at/above threshold are returned. If agent_type is
    given, only patterns observed for that agent are included.
    """
    rules: list[dict] = []
    for p in patterns_above_threshold():
        if agent_type and agent_type not in p["agent_types"]:
            continue
        rules.append(p)
    return rules

# ---------------------------------------------------------------------------
# Prompt injection (sentinel: skillbook.build_prompt_injection)
# ---------------------------------------------------------------------------

def build_prompt_injection(agent_type: str) -> str:
    """Return a markdown block of active auto-promoted rules for *agent_type*.

    Empty string when nothing is above threshold. Prepended to a T3 spawn
    prompt so past mistakes are visible before work begins.
    """
    rules = load_active_rules(agent_type)
    if not rules:
        return ""

    lines = [
        "## Learned Rules (auto-promoted from past T3 failures — follow strictly)",
        "",
    ]
    for r in rules:
        lines.append(
            f"**[{r['error_type']} — seen {r['count']}x]** "
            f"{r['latest_fix']}"
        )
    lines.append("")
    lines.append(
        "These rules were earned through repeated failures. "
        "They carry MORE weight than static instructions."
    )
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = __doc__.strip()


def _cmd_record(argv: list[str]) -> int:
    if len(argv) < 5:
        print(
            "usage: record <task_id> <agent_type> <error_type> "
            "<signal_trace> <what_should_have_happened> [prompt_snippet]",
            file=sys.stderr,
        )
        return 2
    entry = append_entry(
        task_id=argv[0],
        agent_type=argv[1],
        error_type=argv[2],
        signal_trace=argv[3],
        what_should_have_happened=argv[4],
        prompt_snippet=argv[5] if len(argv) > 5 else "",
    )
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def _cmd_inject(argv: list[str]) -> int:
    if not argv:
        print("usage: inject <agent_type>", file=sys.stderr)
        return 2
    block = build_prompt_injection(argv[0])
    if block:
        print(block)
    return 0


def _cmd_patterns(argv: list[str]) -> int:
    thr: int | None = None
    if "--threshold" in argv:
        i = argv.index("--threshold")
        try:
            thr = int(argv[i + 1])
        except (IndexError, ValueError):
            print("error: --threshold requires an int", file=sys.stderr)
            return 2
    results = patterns_above_threshold(thr)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def _cmd_promote(argv: list[str]) -> int:
    thr: int | None = None
    if "--threshold" in argv:
        i = argv.index("--threshold")
        try:
            thr = int(argv[i + 1])
        except (IndexError, ValueError):
            print("error: --threshold requires an int", file=sys.stderr)
            return 2
    written = promote_patterns(thr)
    for p in written:
        print(p)
    return 0


_COMMANDS = {
    "record": _cmd_record,
    "inject": _cmd_inject,
    "patterns": _cmd_patterns,
    "promote": _cmd_promote,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help"}:
        print(_USAGE)
        return 0 if argv else 2
    cmd = argv[0]
    handler = _COMMANDS.get(cmd)
    if handler is None:
        print(f"unknown command: {cmd}\n\n{_USAGE}", file=sys.stderr)
        return 2
    return handler(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
