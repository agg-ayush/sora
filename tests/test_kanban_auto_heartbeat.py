"""Tests for the kanban auto-heartbeat wiring in the claude_orchestrate plugin.

The structural fix: a >TTL blocking `wait` starves the kanban claim because the
supervisor's event loop is blocked inside the call. The heartbeat therefore has
to come from inside the plugin's own blocking loop. tmux-spawned sessions never
get a worker_pid from the dispatcher, so the reclaimer's pid-alive extension
doesn't protect them.

Verifies:
1. _start persists kanban_task_id/kanban_board to meta.json when passed.
2. _maybe_kanban_heartbeat shells out to `hermes kanban [--board b] heartbeat`
   for a kanban-linked session, and is a no-op for unlinked sessions.
3. Throttling: a second call within _KANBAN_HB_MIN_INTERVAL does not shell out;
   force=True bypasses the throttle.
4. Never raises: a failing heartbeat CLI must not break the plugin action.
5. _gate triggers a forced heartbeat for a linked session.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Load the plugin from the REPO working tree (not the live install), so this
# test validates changes before they are synced live.
_plugin_path = Path(__file__).resolve().parent.parent / "plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate", _plugin_path)
assert _spec and _spec.loader
claude_orchestrate = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate"] = claude_orchestrate
_spec.loader.exec_module(claude_orchestrate)


def _completed(rc: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


class KanbanAutoHeartbeatTest(unittest.TestCase):
    def setUp(self):
        claude_orchestrate._kanban_hb_last.clear()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tasks_root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_meta(self, task_id: str, meta: dict) -> None:
        d = self.tasks_root / task_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    def test_noop_when_session_not_linked(self):
        """Unlinked session (no kanban_task_id in meta) never shells out."""
        self._write_meta("t-unlinked", {"task_id": "t-unlinked"})
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run") as mock_run:
            claude_orchestrate._maybe_kanban_heartbeat("t-unlinked")
            mock_run.assert_not_called()

    def test_noop_when_meta_missing(self):
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run") as mock_run:
            claude_orchestrate._maybe_kanban_heartbeat("t-no-meta")
            mock_run.assert_not_called()

    def test_heartbeats_linked_session_with_board(self):
        self._write_meta("t-linked", {
            "task_id": "t-linked",
            "kanban_task_id": "KB-123",
            "kanban_board": "myboard",
        })
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", return_value=_completed(0)) as mock_run:
            claude_orchestrate._maybe_kanban_heartbeat("t-linked", force=True)
            mock_run.assert_called_once_with([
                "hermes", "kanban", "--board", "myboard",
                "heartbeat", "KB-123", "--note", "auto-heartbeat: supervised session active",
            ])

    def test_heartbeats_linked_session_without_board(self):
        self._write_meta("t-linked-nb", {
            "task_id": "t-linked-nb",
            "kanban_task_id": "KB-9",
        })
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", return_value=_completed(0)) as mock_run:
            claude_orchestrate._maybe_kanban_heartbeat("t-linked-nb", force=True)
            mock_run.assert_called_once_with([
                "hermes", "kanban",
                "heartbeat", "KB-9", "--note", "auto-heartbeat: supervised session active",
            ])

    def test_throttled_within_min_interval(self):
        self._write_meta("t-throttle", {
            "task_id": "t-throttle", "kanban_task_id": "KB-1",
        })
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", return_value=_completed(0)) as mock_run:
            claude_orchestrate._maybe_kanban_heartbeat("t-throttle")
            self.assertEqual(mock_run.call_count, 1)
            # Immediate second call is throttled.
            claude_orchestrate._maybe_kanban_heartbeat("t-throttle")
            self.assertEqual(mock_run.call_count, 1)
            # force=True bypasses the throttle.
            claude_orchestrate._maybe_kanban_heartbeat("t-throttle", force=True)
            self.assertEqual(mock_run.call_count, 2)

    def test_failed_heartbeat_not_recorded_and_never_raises(self):
        self._write_meta("t-fail", {"task_id": "t-fail", "kanban_task_id": "KB-2"})
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", return_value=_completed(1, stderr="boom")) as mock_run:
            # Must not raise.
            claude_orchestrate._maybe_kanban_heartbeat("t-fail", force=True)
            # Failed heartbeat must NOT update the throttle stamp — a retry on
            # the next loop iteration is allowed immediately.
            self.assertNotIn("t-fail", claude_orchestrate._kanban_hb_last)
            claude_orchestrate._maybe_kanban_heartbeat("t-fail")
            self.assertEqual(mock_run.call_count, 2)

    def test_run_raising_is_swallowed(self):
        self._write_meta("t-raise", {"task_id": "t-raise", "kanban_task_id": "KB-3"})
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", side_effect=OSError("no hermes")):
            claude_orchestrate._maybe_kanban_heartbeat("t-raise", force=True)  # no raise

    def test_gate_forces_heartbeat_for_linked_session(self):
        """_gate heartbeats (forced) before computing the composite verdict."""
        self._write_meta("t-gate", {
            "task_id": "t-gate", "kanban_task_id": "KB-77", "kanban_board": "b1",
            "phase": "3",
        })
        calls = []
        def fake_run(cmd, timeout=None):
            calls.append(cmd)
            return _completed(0)
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", side_effect=fake_run), \
             patch.object(claude_orchestrate, "_check_impl_complete",
                          return_value={"result": "skipped", "evidence": "stub"}), \
             patch.object(claude_orchestrate, "doom_loop_active", return_value=False):
            out = claude_orchestrate._gate({"task_id": "t-gate"})
            self.assertTrue(out["ok"])
        hb_calls = [c for c in calls if c[:2] == ["hermes", "kanban"]]
        # The gate makes 2 kanban calls: the heartbeat + the design-doc
        # attachments check. Both are expected.
        self.assertEqual(len(hb_calls), 2)
        self.assertIn("KB-77", hb_calls[0])
        self.assertIn("--board", hb_calls[0])

    def test_schema_declares_kanban_params(self):
        props = claude_orchestrate.CLAUDE_ORCHESTRATE_SCHEMA["parameters"]["properties"]
        self.assertIn("kanban_task_id", props)
        self.assertIn("kanban_board", props)
        self.assertEqual(props["kanban_task_id"]["type"], "string")
        self.assertEqual(props["kanban_board"]["type"], "string")

    def test_start_persists_linkage_to_meta(self):
        """_start writes kanban_task_id/kanban_board into meta.json when passed,
        and omits the keys entirely when not passed."""
        def fake_run(cmd, timeout=None):
            return _completed(0)
        with patch.object(claude_orchestrate, "_tasks_root", return_value=self.tasks_root), \
             patch.object(claude_orchestrate, "_run", side_effect=fake_run), \
             patch.object(claude_orchestrate, "_seatbelt_headers", return_value="x-tfy-api-key: DUMMY\nx-maat-token: DUMMY"), \
             patch.dict(os.environ, {"TFY_API_KEY": "DUMMY_TFY"}, clear=False), \
             patch.object(claude_orchestrate, "_session_exists", return_value=False):
            out = claude_orchestrate._start({
                "task_id": "t-start-link", "prompt": "x", "workdir": "/tmp",
                "model_provider": "seatbelt", "model": "opus",
                "kanban_task_id": "KB-55", "kanban_board": "boardz",
            })
            self.assertTrue(out["ok"], out)
            meta = json.loads((self.tasks_root / "t-start-link" / "meta.json").read_text())
            self.assertEqual(meta["kanban_task_id"], "KB-55")
            self.assertEqual(meta["kanban_board"], "boardz")

            out2 = claude_orchestrate._start({
                "task_id": "t-start-nolink", "prompt": "x", "workdir": "/tmp",
                "model_provider": "seatbelt", "model": "opus",
            })
            self.assertTrue(out2["ok"], out2)
            meta2 = json.loads((self.tasks_root / "t-start-nolink" / "meta.json").read_text())
            self.assertNotIn("kanban_task_id", meta2)
            self.assertNotIn("kanban_board", meta2)


if __name__ == "__main__":
    unittest.main()
