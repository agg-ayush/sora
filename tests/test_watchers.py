"""Tests for scripts/auth-canary.py.

Watermark-deduped cron watcher: silent on success, markdown on failure.
Exercises the query + dedup + emit contract end-to-end against a tmpdir
HERMES_HOME so no live state is touched.

Covers: silent when healthy, alerts when sessions started but output tokens
are 0, dedupes within the bucket, re-alerts after the bucket rolls.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _TmpHome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name) / ".hermes"
        self.home.mkdir(parents=True)
        self.state = Path(self._tmp.name) / "watcher-state"
        self._env = patch.dict(os.environ, {
            "HERMES_HOME": str(self.home),
            "WATCHER_STATE_DIR": str(self.state),
        })
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()


def _make_state_db(home: Path, *, sessions: int, output_tokens: int, age_s: int = 60) -> None:
    db = home / "state.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, started_at REAL NOT NULL)")
    con.execute("""CREATE TABLE session_model_usage (
        session_id TEXT, last_seen REAL, output_tokens INTEGER
    )""")
    now = time.time()
    for i in range(sessions):
        con.execute("INSERT INTO sessions VALUES (?,?)", (f"s-{i}", now - age_s))
        con.execute("INSERT INTO session_model_usage VALUES (?,?,?)",
                    (f"s-{i}", now - age_s, output_tokens))
    con.commit()
    con.close()


class AuthCanaryTest(_TmpHome):
    def setUp(self):
        super().setUp()
        self.mod = _load("auth_canary", REPO / "scripts" / "auth-canary.py")

    def _run(self) -> tuple[int, str]:
        buf = StringIO()
        with redirect_stdout(buf):
            rc = self.mod.main()
        return rc, buf.getvalue()

    def test_missing_db_returns_2(self):
        with patch.object(sys, "argv", ["auth-canary"]):
            rc = self.mod.main()
        self.assertEqual(rc, 2)

    def test_healthy_is_silent(self):
        _make_state_db(self.home, sessions=10, output_tokens=500)
        with patch.object(sys, "argv", ["auth-canary"]):
            rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_quiet_when_below_session_threshold(self):
        # 3 dead sessions < default threshold of 6 — not yet alarming
        _make_state_db(self.home, sessions=3, output_tokens=0)
        with patch.object(sys, "argv", ["auth-canary"]):
            rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_first_run_is_baseline_silent(self):
        # Watermark contract: first run records state but emits nothing.
        _make_state_db(self.home, sessions=10, output_tokens=0)
        with patch.object(sys, "argv", ["auth-canary"]):
            rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")

    def test_alerts_after_baseline_when_dead(self):
        _make_state_db(self.home, sessions=10, output_tokens=0)
        with patch.object(sys, "argv", ["auth-canary"]):
            self._run()  # baseline
        # Clear seen_ids so the current bucket looks new
        wm_file = self.state / "auth-canary.json"
        d = json.loads(wm_file.read_text())
        d["seen_ids"] = []
        wm_file.write_text(json.dumps(d))

        with patch.object(sys, "argv", ["auth-canary"]):
            rc, out = self._run()
        self.assertEqual(rc, 0)
        self.assertIn("Agents are running but no model is answering", out)
        self.assertIn("**0 output tokens**", out)

    def test_dedupes_within_same_window(self):
        _make_state_db(self.home, sessions=10, output_tokens=0)
        with patch.object(sys, "argv", ["auth-canary"]):
            self._run()  # baseline
        wm_file = self.state / "auth-canary.json"
        d = json.loads(wm_file.read_text())
        d["seen_ids"] = []
        wm_file.write_text(json.dumps(d))

        with patch.object(sys, "argv", ["auth-canary"]):
            rc1, out1 = self._run()
            rc2, out2 = self._run()
        self.assertIn("Agents are running", out1)
        self.assertEqual(out2, "")  # same bucket — already alerted


if __name__ == "__main__":
    unittest.main()
