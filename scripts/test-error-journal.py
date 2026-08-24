#!/usr/bin/env python3
"""End-to-end test for the tier-orchestrator error journal.

Uses a temp HOME so it never touches the real ~/.hermes/tier_orchestrator.

Covers:
  1. record appends a well-formed JSONL entry
  2. patterns below threshold are NOT promoted
  3. crossing the threshold (default 3) auto-promotes to a candidate skill
  4. the candidate file carries the [auto-promoted, needs-review] marker
  5. inject returns a markdown block naming the rule for the right agent_type
  6. inject respects agent_type filtering (other agents don't see the rule)
  7. TIER_ERROR_PROMOTE_THRESHOLD env var overrides the default
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path.home() / ".hermes" / "scripts" / "error-journal.py"

PASS = "PASS"
FAIL = "FAIL"


def _load_module(home: Path):
    """Import error-journal.py as a module with HOME pointed at the tempdir."""
    journal_dir = home / ".hermes" / "tier_orchestrator"
    spec = importlib.util.spec_from_file_location("error_journal", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Patch the paths before exec so _ensure_dirs uses the temp home
    spec.loader.exec_module(mod)
    mod.JOURNAL_DIR = journal_dir
    mod.JOURNAL_PATH = journal_dir / "error_journal.jsonl"
    mod.AUTO_SKILLS_DIR = journal_dir / "auto_skills"
    return mod


def _record(mod, task_id: str, agent: str, etype: str, sig: str, fix: str) -> dict:
    return mod.append_entry(
        task_id=task_id,
        agent_type=agent,
        error_type=etype,
        signal_trace=sig,
        what_should_have_happened=fix,
    )


def check(name: str, cond: bool, detail: str = "") -> bool:
    status = PASS if cond else FAIL
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return cond


def main() -> int:
    if not SCRIPT.exists():
        print(f"error: {SCRIPT} not found", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="ej-test-"))
    try:
        mod = _load_module(tmp)
        ok = True

        print("1. record + JSONL shape")
        e = _record(mod, "task-1", "claude", "test_failure",
                    "test_foo AssertionError: expected 3 got 4",
                    "Update the expected count to 4")
        ok &= check("append_entry returns dict", isinstance(e, dict))
        ok &= check("journal file exists", mod.JOURNAL_PATH.exists())
        lines = mod.JOURNAL_PATH.read_text().strip().splitlines()
        ok &= check("one JSONL line", len(lines) == 1)
        parsed = json.loads(lines[0])
        for field in ("timestamp", "task_id", "agent_type", "error_type",
                      "signal_trace", "what_should_have_happened", "prompt_snippet"):
            ok &= check(f"field {field!r} present", field in parsed)

        print("2. below threshold → no promotion, no inject output")
        pats = mod.patterns_above_threshold()
        ok &= check("no patterns at threshold yet", len(pats) == 0)
        written = mod.promote_patterns()
        ok &= check("promote writes nothing", len(written) == 0)
        ok &= check("inject empty for claude", mod.build_prompt_injection("claude") == "")

        print("3. cross threshold → auto-promote")
        _record(mod, "task-2", "claude", "test_failure",
                "test_bar AssertionError: off-by-one",
                "Fix off-by-one in the counter")
        _record(mod, "task-3", "claude", "test_failure",
                "test_baz AssertionError: expected 5 got 6",
                "Fix the loop bound")
        pats = mod.patterns_above_threshold()
        ok &= check("one pattern above threshold", len(pats) == 1, f"got {pats}")
        ok &= check("count == 3", pats[0]["count"] == 3)
        ok &= check("error_type == test_failure", pats[0]["error_type"] == "test_failure")
        written = mod.promote_patterns()
        ok &= check("promote wrote one file", len(written) == 1)
        skill_file = mod.AUTO_SKILLS_DIR / "test_failure.md"
        ok &= check("candidate skill file exists", skill_file.exists())
        body = skill_file.read_text()
        ok &= check("carries [auto-promoted, needs-review] marker",
                    "[auto-promoted, needs-review]" in body)
        ok &= check("contains latest fix", "Fix the loop bound" in body)

        print("4. inject returns markdown block for matching agent")
        block = mod.build_prompt_injection("claude")
        ok &= check("non-empty inject", len(block) > 0)
        ok &= check("mentions error type", "test_failure" in block)
        ok &= check("mentions count 3", "3x" in block)
        ok &= check("contains the fix text", "Fix the loop bound" in block)
        ok &= check("starts with markdown heading", block.startswith("## "))

        print("5. inject filters by agent_type")
        ok &= check("other agent gets empty", mod.build_prompt_injection("codex") == "")

        print("6. env-var threshold override")
        # Record 1 more for a different error_type, then drop threshold to 1
        _record(mod, "task-4", "claude", "auth_expired",
                "401 on gateway", "Refresh the token before retry")
        os.environ["TIER_ERROR_PROMOTE_THRESHOLD"] = "1"
        try:
            pats = mod.patterns_above_threshold()
            etypes = {p["error_type"] for p in pats}
            ok &= check("threshold=1 surfaces auth_expired", "auth_expired" in etypes)
            ok &= check("threshold=1 keeps test_failure", "test_failure" in etypes)
        finally:
            del os.environ["TIER_ERROR_PROMOTE_THRESHOLD"]

        print("7. CLI end-to-end (subprocess with HOME override)")
        env = dict(os.environ, HOME=str(tmp))
        r = subprocess.run(
            ["python3", str(SCRIPT), "inject", "claude"],
            capture_output=True, text=True, env=env,
        )
        ok &= check("cli inject exit 0", r.returncode == 0, r.stderr)
        ok &= check("cli inject has rule", "test_failure" in r.stdout)

        r = subprocess.run(
            ["python3", str(SCRIPT), "patterns"],
            capture_output=True, text=True, env=env,
        )
        ok &= check("cli patterns exit 0", r.returncode == 0, r.stderr)
        out = json.loads(r.stdout)
        ok &= check("cli patterns is a list", isinstance(out, list))

        print()
        if ok:
            print("ALL CHECKS PASSED")
            return 0
        print("SOME CHECKS FAILED")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
