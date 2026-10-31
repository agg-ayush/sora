"""Tests for the truefoundry Opus review-route auth injection in _start."""

import importlib.util
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Import the repo's plugin directly (not the installed ~/.hermes copy).
_plugin_path = Path(__file__).resolve().parent.parent / "plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate", _plugin_path)
assert _spec and _spec.loader
claude_orchestrate = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate"] = claude_orchestrate
_spec.loader.exec_module(claude_orchestrate)

OPUS = "claude-group/claude-opus-5-5"
TF_URL = "https://<llm-gateway>.truefoundry.cloud/api/llm"
TOKEN_REF = 'export ANTHROPIC_AUTH_TOKEN="$TFY_API_KEY"'
SECRET = "DUMMY-tfy-secret-7f3e9a"


class TruefoundryOpusRouteTest(unittest.TestCase):
    """Claude-via-TF is retired: anthropic-primary billing. The route must
    fail closed for every claude request, and the default provider is
    seatbelt (primary) with fireworks as the GLM fallback."""

    def _base_args(self, **overrides):
        args = {
            "task_id": "t2-test-tf-reject",
            "prompt": "reply PONG",
            "workdir": "/tmp",
            "executor": "claude",
        }
        args.update(overrides)
        return args

    def test_tf_claude_rejected(self):
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_tasks_root", return_value=Path("/tmp")):
            res = claude_orchestrate._start(self._base_args(model_provider="truefoundry", model="claude-group/claude-opus-5-5"))
            self.assertFalse(res.get("ok"))
            self.assertIn("anthropic-primary", res.get("error", ""))

    def test_tf_claude_rejected_without_model(self):
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_tasks_root", return_value=Path("/tmp")):
            res = claude_orchestrate._start(self._base_args(model_provider="truefoundry"))
            self.assertFalse(res.get("ok"))
            self.assertIn("anthropic-primary", res.get("error", ""))

    def test_tf_claude_rejected_for_argon_too(self):
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_tasks_root", return_value=Path("/tmp")):
            res = claude_orchestrate._start(self._base_args(model_provider="truefoundry", model="gemini-group/gemini-4-argon"))
            self.assertFalse(res.get("ok"))
            self.assertIn("anthropic-primary", res.get("error", ""))

    def test_default_provider_is_seatbelt(self):
        # omitted model_provider resolves to seatbelt, not truefoundry
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_tasks_root", return_value=Path("/tmp")):
            res = claude_orchestrate._start(self._base_args(model="opus"))
            # seatbelt path proceeds past provider validation (fails later on
            # header lookup in a test env, but NOT with the anthropic-primary error)
            self.assertNotIn("anthropic-primary", res.get("error", ""))


class CodexWorktreeTrustTest(unittest.TestCase):
    """The gpt-6-sol codex trust override applies to exactly the generated
    worktree path, and to nothing else."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.artifact_dir = Path(self._tmpdir.name)
        self.workdir = self.artifact_dir / "repo"
        self.workdir.mkdir()
        self.captured_cmds = []

    def _fake_run(self, cmd, timeout=None):
        self.captured_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def _start(self, **overrides):
        args = {
            "task_id": "t2-test-codex-trust",
            "prompt": "reply PONG",
            "workdir": str(self.workdir),
            "executor": "codex",
            "model": "gpt-6-sol",
            "model_provider": "truefoundry",
        }
        args.update(overrides)
        seatbelt_env = {"TFY_API_KEY": "DUMMY_TFY"} if args.get("model_provider") == "seatbelt" else {}
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_artifact_dir", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "get_hermes_home", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "_session_state", return_value={"state": "working"}), \
             patch.object(claude_orchestrate, "_run", side_effect=self._fake_run), \
             patch.object(claude_orchestrate, "_seatbelt_headers", return_value="x-tfy-api-key: DUMMY\nx-maat-token: DUMMY"), \
             patch("time.sleep"), \
             patch.dict(os.environ, seatbelt_env, clear=True):
            return claude_orchestrate._start(args)

    def _shell_cmd(self):
        for cmd in self.captured_cmds:
            if cmd[:3] == ["tmux", "new-session", "-d"]:
                return cmd[-1]
        self.fail("no tmux new-session captured")

    def _expected_worktree(self):
        return (Path(self.workdir).parent / claude_orchestrate.WORKTREES_DIRNAME / "wt1").resolve()

    def test_worktree_sol_gets_exact_trust_override(self):
        res = self._start(worktree="wt1")
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        expected = f'projects={{"{self._expected_worktree()}"={{trust_level="trusted"}}}}'
        self.assertIn(f" -c '{expected}'", cmd)
        self.assertIn("-m gpt-6-sol", cmd)

    def test_no_override_without_worktree(self):
        res = self._start()
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("trust_level", self._shell_cmd())

    def test_no_override_for_other_model(self):
        res = self._start(worktree="wt1", model="gpt-5.6-terra")
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("trust_level", self._shell_cmd())

    def test_no_override_for_claude_executor(self):
        res = self._start(worktree="wt1", executor="claude", model_provider="seatbelt", model="opus")
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("trust_level", self._shell_cmd())


if __name__ == "__main__":
    unittest.main()
