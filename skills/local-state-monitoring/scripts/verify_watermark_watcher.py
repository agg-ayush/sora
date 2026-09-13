#!/usr/bin/env python3
"""Template harness for verifying a watermark-dedup watchdog script.

Copy this into a tmp file, point SCRIPTS/PY/SCRIPT_NAME at your target,
replace the fixture builder(s) and finding-string assertions for your
data source, run it, then delete the copy — this is a disposable
verification tool, not a deliverable to ship alongside the watcher.

Generalizes the pattern: subprocess-invoke the real CLI against a fixture
DB in a tmpdir HERMES_HOME, assert the watermark-dedup contract (silent
baseline, alert on new finding via seen_ids reset, dedup on repeat, exit
codes on missing source), clean up in `finally`.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path("/absolute/path/to/scripts")          # <-- set this
PY = "/usr/bin/python3"                               # <-- pin interpreter if repo needs a newer one
SCRIPT_NAME = "my-watchdog.py"                        # <-- set this
WATERMARK_NAME = "my-watchdog"                        # <-- must match the script's --name / state filename

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def run(env: dict, *args: str) -> tuple[int, str, str]:
    e = dict(os.environ); e.update(env)
    p = subprocess.run([PY, str(SCRIPTS / SCRIPT_NAME), *args],
                       capture_output=True, text=True, env=e, timeout=30)
    return p.returncode, p.stdout, p.stderr


def reset_watermark(state_dir: Path, name: str) -> None:
    """Clear only seen_ids so the next run treats current state as new,
    without disturbing other watermark fields (last-run timestamp, bucket)."""
    p = state_dir / f"{name}.json"
    if p.exists():
        d = json.loads(p.read_text())
        d["seen_ids"] = []
        p.write_text(json.dumps(d))


# --- Fixture builder: SWAP THIS for your actual data source ---
def make_fixture_db(db_path: Path, rows: list[tuple], schema_sql: str) -> None:
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.execute(schema_sql)
    con.executemany(
        f"INSERT INTO t VALUES ({','.join('?' * len(rows[0]))})" if rows else "",
        rows,
    )
    con.commit(); con.close()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="watchdog-verify-"))
    try:
        home = tmp / ".hermes"; home.mkdir(parents=True)
        state = tmp / "watcher-state"
        env = {"HERMES_HOME": str(home), "WATCHER_STATE_DIR": str(state)}

        # 1. Missing source -> non-zero exit + stderr
        rc, _, err = run(env)
        check("missing source -> non-zero exit", rc != 0 and err.strip() != "", f"rc={rc} err={err!r}")

        # 2. Build healthy fixture, expect silent exit 0
        # make_fixture_db(home / "state.db", [...], "CREATE TABLE t (...)")
        # rc, out, _ = run(env)
        # check("healthy -> silent", rc == 0 and out == "")

        # 3. Build unhealthy fixture, fresh watermark -> still silent (baseline)
        # (state / f"{WATERMARK_NAME}.json").unlink(missing_ok=True)
        # rc, out, _ = run(env)
        # check("first run on unhealthy state is baseline-silent", rc == 0 and out == "")

        # 4. Reset seen_ids only -> alert fires
        # reset_watermark(state, WATERMARK_NAME)
        # rc, out, _ = run(env)
        # check("alert fires after baseline", rc == 0 and "<expected finding text>" in out)

        # 5. Re-run unchanged -> dedup, silent again
        # rc, out, _ = run(env)
        # check("repeat finding dedupes", rc == 0 and out == "")

        print()
        if failures:
            print(f"FAILED: {len(failures)}: {failures}")
            return 1
        print("All checks passed (ad-hoc verification, not a suite green).")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
