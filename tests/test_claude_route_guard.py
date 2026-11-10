"""Tests that Claude Code can never be launched against the TrueFoundry gateway."""

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

TF_URL = "https://<llm-gateway>.truefoundry.cloud/api/llm"


class ClaudeRouteGuardTest(unittest.TestCase):
    """Claude Code on the TrueFoundry gateway bills every model as
    anthropic-primary at list price. Every executor=claude start that would
    route there must be refused; seatbelt and fireworks must not be."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.artifact_dir = Path(self._tmpdir.name)
        self.workdir = self.artifact_dir / "repo"
        self.workdir.mkdir()
        self.captured = []

    def _fake_run(self, cmd, timeout=None):
        self.captured.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def _start(self, env=None, **overrides):
        args = {
            "task_id": "t2-test-route-guard",
            "prompt": "reply PONG",
            "workdir": str(self.workdir),
            "executor": "claude",
        }
        args.update(overrides)
        env = {"FIREWORKS_API_KEY": "DUMMY_FW", "TFY_API_KEY": "DUMMY_TFY", **(env or {})}
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_artifact_dir", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "get_hermes_home", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "_session_state", return_value={"state": "working"}), \
             patch.object(claude_orchestrate, "_run", side_effect=self._fake_run), \
             patch.object(claude_orchestrate, "_seatbelt_headers", return_value="x-test: DUMMY"), \
             patch("time.sleep"), \
             patch.dict(os.environ, env, clear=True):
            return claude_orchestrate._start(args)

    def _launch_cmds(self):
        return [c for c in self.captured if c[:3] == ["tmux", "new-session", "-d"]]

    def assertRefused(self, res):
        self.assertFalse(res.get("ok"), res)
        err = res.get("error", "")
        self.assertIn("TrueFoundry", err)
        self.assertIn("seatbelt", err)
        self.assertIn("fireworks", err)
        self.assertEqual(self._launch_cmds(), [], "tmux must never be launched on a refused route")

    def test_truefoundry_provider_refused_for_every_model(self):
        for model in (None, "claude-group/claude-opus-5-5", "gemini-group/gemini-4-argon", "opus", "claude-sonnet-5"):
            with self.subTest(model=model):
                self.captured.clear()
                kw = {"model_provider": "truefoundry"}
                if model:
                    kw["model"] = model
                self.assertRefused(self._start(**kw))

    def test_opus_and_argon_models_never_route_to_truefoundry_via_other_providers(self):
        # The retired TF opus/argon branch is gone: with a non-TF provider these
        # model ids must never produce a launch pointing at truefoundry.cloud.
        for provider in ("seatbelt", "fireworks"):
            for model in ("claude-group/claude-opus-5-5", "gemini-group/gemini-4-argon"):
                with self.subTest(provider=provider, model=model):
                    self.captured.clear()
                    res = self._start(model_provider=provider, model=model)
                    for cmd in self._launch_cmds():
                        self.assertNotIn("truefoundry.cloud", cmd[-1])
                    self.assertFalse(res.get("ok") and any(TF_URL in c[-1] for c in self._launch_cmds()))

    def test_unknown_provider_still_rejected(self):
        res = self._start(model_provider="nonsense")
        self.assertFalse(res.get("ok"))
        self.assertEqual(self._launch_cmds(), [])

    def test_final_guard_refuses_truefoundry_url_in_composed_command(self):
        # Defense in depth: even if a branch composed a TF endpoint, the launch is refused.
        with patch.object(claude_orchestrate, "SEATBELT_BASE_URL", TF_URL):
            res = self._start(model_provider="seatbelt", model="opus")
        self.assertRefused(res)

    def test_brief_text_naming_truefoundry_does_not_trip_the_guard(self):
        res = self._start(model_provider="seatbelt", model="opus", prompt="document https://<llm-gateway>.truefoundry.cloud/api/llm billing")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(len(self._launch_cmds()), 1)

    def test_seatbelt_allowed(self):
        res = self._start(model_provider="seatbelt", model="opus")
        self.assertTrue(res.get("ok"), res)
        cmd = self._launch_cmds()[0][-1]
        self.assertIn(f"ANTHROPIC_BASE_URL={claude_orchestrate.SEATBELT_BASE_URL}", cmd)
        self.assertNotIn("truefoundry.cloud", cmd)

    def test_default_provider_is_seatbelt_and_allowed(self):
        res = self._start(model="sonnet")
        self.assertTrue(res.get("ok"), res)
        self.assertIn(claude_orchestrate.SEATBELT_BASE_URL, self._launch_cmds()[0][-1])

    def test_fireworks_allowed(self):
        res = self._start(model_provider="fireworks")
        self.assertTrue(res.get("ok"), res)
        cmd = self._launch_cmds()[0][-1]
        self.assertIn("ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference", cmd)
        self.assertIn("ANTHROPIC_MODEL=accounts/fireworks/models/kimi-k3p1-pro", cmd)
        self.assertIn("CLAUDE_CODE_SUBAGENT_MODEL=accounts/fireworks/models/kimi-k3p1-pro", cmd)
        self.assertIn("CLAUDE_CODE_AUTO_COMPACT_WINDOW=1048576", cmd)
        self.assertNotIn("glm-5p3", cmd)
        self.assertNotIn("truefoundry.cloud", cmd)

    def test_codex_truefoundry_unchanged(self):
        res = self._start(executor="codex", model="gpt-6-sol", model_provider="truefoundry")
        self.assertTrue(res.get("ok"), res)


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
