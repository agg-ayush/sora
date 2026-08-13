"""Tests for the doom-loop circuit breaker in claude_orchestrate plugin.

Verifies:
1. fingerprint normalizes whitespace/case.
2. observe_action trips the breaker on 3 identical calls.
3. doom_loop_active / breaker_open_for report the trip.
4. Global cooldown blocks the same fingerprint across tasks.
5. clear_doom_task resets the per-task ring.
"""

import time
import unittest
from unittest.mock import patch

# Import the plugin module directly.
import importlib.util
import sys
from pathlib import Path

_plugin_path = Path.home() / ".hermes" / "plugins" / "claude-orchestrate" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate", _plugin_path)
assert _spec and _spec.loader
claude_orchestrate = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate"] = claude_orchestrate
_spec.loader.exec_module(claude_orchestrate)


class DoomLoopBreakerTest(unittest.TestCase):
    def setUp(self):
        # Reset in-memory state between tests.
        claude_orchestrate._doom_rings.clear()
        claude_orchestrate._breakers.clear()

    def test_fingerprint_normalizes_whitespace_and_case(self):
        fp1 = claude_orchestrate.doom_fingerprint("Bash", "git status")
        fp2 = claude_orchestrate.doom_fingerprint("Bash", "  git   status  ")
        fp3 = claude_orchestrate.doom_fingerprint("Bash", "GIT STATUS")
        self.assertEqual(fp1, fp2)
        self.assertEqual(fp2, fp3)

    def test_fingerprint_truncates_long_args(self):
        long_args = "x" * 500
        fp = claude_orchestrate.doom_fingerprint("Read", long_args)
        self.assertEqual(len(fp), 12)

    def test_trips_on_3_identical_calls(self):
        task = "t2-test-doom"
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertTrue(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertTrue(claude_orchestrate.doom_loop_active(task))
        self.assertTrue(claude_orchestrate.breaker_open_for("Bash", "git status"))

    def test_does_not_trip_on_2_identical_calls(self):
        task = "t2-test-doom2"
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertFalse(claude_orchestrate.doom_loop_active(task))
        self.assertFalse(claude_orchestrate.breaker_open_for("Bash", "git status"))

    def test_does_not_trip_on_varied_calls(self):
        task = "t2-test-doom3"
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git diff"))
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))
        self.assertFalse(claude_orchestrate.doom_loop_active(task))

    def test_global_breaker_blocks_same_fingerprint_across_tasks(self):
        task_a = "t2-test-a"
        task_b = "t2-test-b"
        # Trip in task A
        claude_orchestrate.observe_action(task_a, "Read", "/etc/passwd")
        claude_orchestrate.observe_action(task_a, "Read", "/etc/passwd")
        claude_orchestrate.observe_action(task_a, "Read", "/etc/passwd")
        # Same fingerprint is blocked for task B
        self.assertTrue(claude_orchestrate.breaker_open_for("Read", "/etc/passwd"))
        # But task B's own ring is clean (no doom_loop yet)
        self.assertFalse(claude_orchestrate.doom_loop_active(task_b))

    def test_breaker_cooldown_expires(self):
        task = "t2-test-cooldown"
        claude_orchestrate.observe_action(task, "Bash", "git status")
        claude_orchestrate.observe_action(task, "Bash", "git status")
        claude_orchestrate.observe_action(task, "Bash", "git status")
        self.assertTrue(claude_orchestrate.doom_loop_active(task))
        # Simulate time passing beyond cooldown
        with patch.object(claude_orchestrate, "_now_ts", return_value=time.time() + 301):
            self.assertFalse(claude_orchestrate.doom_loop_active(task))
            self.assertFalse(claude_orchestrate.breaker_open_for("Bash", "git status"))

    def test_clear_doom_task_resets_ring(self):
        task = "t2-test-clear"
        claude_orchestrate.observe_action(task, "Bash", "git status")
        claude_orchestrate.observe_action(task, "Bash", "git status")
        claude_orchestrate.observe_action(task, "Bash", "git status")
        self.assertTrue(claude_orchestrate.doom_loop_active(task))
        claude_orchestrate.clear_doom_task(task)
        # Ring is cleared; task breaker remains open (cooldown still active)
        self.assertTrue(claude_orchestrate.doom_loop_active(task))
        self.assertFalse(claude_orchestrate.observe_action(task, "Bash", "git status"))

    def test_session_state_reports_doom_loop(self):
        task = "t2-test-state"
        # Manually trip the breaker for this task
        claude_orchestrate._trip_breaker(f"task:{task}")
        state = claude_orchestrate._session_state(task)
        self.assertTrue(state["doom_loop"])
        # The session is also treated as stalled (if not done/needs_input)
        if state["state"] not in ("done", "needs_input", "exited"):
            self.assertEqual(state["state"], "stalled")

    def test_status_includes_doom_loop_key(self):
        task = "t2-test-status"
        result = claude_orchestrate._status({"task_id": task})
        self.assertIn("doom_loop", result)

    def test_gate_includes_doom_loop_key(self):
        task = "t2-test-gate"
        result = claude_orchestrate._gate({"task_id": task})
        self.assertIn("doom_loop", result)


if __name__ == "__main__":
    unittest.main()
