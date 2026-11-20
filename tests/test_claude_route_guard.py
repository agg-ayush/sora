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
    route there must be refused; the default Fireworks route must not be."""

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
             patch("time.sleep"), \
             patch.dict(os.environ, env, clear=True):
            return claude_orchestrate._start(args)

    def _launch_cmds(self):
        return [c for c in self.captured if c[:3] == ["tmux", "new-session", "-d"]]

    def _try_lock_file(self, path):
        fh = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0, os.SEEK_END)
                if fh.tell() == 0:
                    fh.write(b"\0")
                    fh.flush()
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fh
        except OSError:
            fh.close()
            return None

    def assertRefused(self, res):
        self.assertFalse(res.get("ok"), res)
        err = res.get("error", "")
        self.assertIn("TrueFoundry", err)
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

    def test_unsupported_fireworks_model_pins_are_refused_before_launch(self):
        for model in ("opus", "claude-group/claude-opus-5-5", "gemini-group/gemini-4-argon"):
            with self.subTest(model=model):
                res = self._start(model_provider="fireworks", model=model)
                self.assertFalse(res.get("ok"), res)
                self.assertIn("not supported", res["error"])
                self.assertEqual(self._launch_cmds(), [])
                self.assertFalse((self.artifact_dir / "status.md").exists())

    def test_fireworks_full_id_and_alias_share_the_effective_model(self):
        for model in (claude_orchestrate.FIREWORKS_MODEL, "k3p1"):
            with self.subTest(model=model):
                self.captured.clear()
                res = self._start(model_provider="fireworks", model=model)
                self.assertTrue(res.get("ok"), res)
                self.assertEqual(len(self._launch_cmds()), 1)
                self.assertIn(f"ANTHROPIC_MODEL={claude_orchestrate.FIREWORKS_MODEL}", self._launch_cmds()[0][-1])
                meta = json.loads((self.artifact_dir / "meta.json").read_text())
                self.assertEqual(meta["model"], claude_orchestrate.FIREWORKS_MODEL)

    def test_unknown_provider_still_rejected(self):
        for provider in ("nonsense", "seatbelt"):
            with self.subTest(provider=provider):
                res = self._start(model_provider=provider)
                self.assertFalse(res.get("ok"))
                self.assertEqual(self._launch_cmds(), [])

    def test_final_guard_refuses_truefoundry_url_in_composed_command(self):
        # Defense in depth: even if a branch composed a TF endpoint, the launch is refused.
        with patch.object(claude_orchestrate, "FIREWORKS_BASE_URL", TF_URL):
            res = self._start(model_provider="fireworks")
        self.assertRefused(res)

    def test_brief_text_naming_truefoundry_does_not_trip_the_guard(self):
        res = self._start(model_provider="fireworks", prompt="document https://<llm-gateway>.truefoundry.cloud/api/llm billing")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(len(self._launch_cmds()), 1)

    def test_default_provider_is_fireworks_kimi_k3p1(self):
        res = self._start()
        self.assertTrue(res.get("ok"), res)
        cmd = self._launch_cmds()[0][-1]
        self.assertIn(f"ANTHROPIC_BASE_URL={claude_orchestrate.FIREWORKS_BASE_URL}", cmd)
        self.assertIn(f"ANTHROPIC_MODEL={claude_orchestrate.FIREWORKS_MODEL}", cmd)
        self.assertNotIn("truefoundry.cloud", cmd)

    def test_fireworks_preseeds_isolated_session_dialog_state(self):
        res = self._start(model_provider="fireworks")
        self.assertTrue(res.get("ok"), res)
        state = json.loads((self.artifact_dir / "claude-k3-config" / ".claude.json").read_text())
        self.assertTrue(state["hasCompletedOnboarding"])
        self.assertTrue(state["bypassPermissionsModeAccepted"])
        self.assertTrue(state["projects"][str(self.workdir.resolve())]["hasTrustDialogAccepted"])

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

    def test_fireworks_scrubs_ambient_backup_keys_and_gateway_headers(self):
        res = self._start(env={
            "ANTHROPIC_API_KEY_BACKUP": "OLD_BACKUP",
            "BACKUP_ANTHROPIC_API_KEY": "OLDER_BACKUP",
            "ANTHROPIC_CUSTOM_HEADERS": "x-tfy-api-key: SECRET",
        })
        self.assertTrue(res.get("ok"), res)
        cmd = self._launch_cmds()[0][-1]
        self.assertIn("unset ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY ANTHROPIC_CUSTOM_HEADERS", cmd)
        self.assertNotIn("x-tfy-api-key: SECRET", cmd)
        self.assertNotIn("OLD_BACKUP", cmd)
        self.assertNotIn("OLDER_BACKUP", cmd)

    def test_codex_fireworks_is_rejected_without_artifacts(self):
        res = self._start(executor="codex", model="gpt-6-sol", model_provider="fireworks")
        self.assertFalse(res.get("ok"), res)
        self.assertIn("not supported", res["error"])
        self.assertEqual(self._launch_cmds(), [])
        self.assertFalse((self.artifact_dir / "status.md").exists())

    def test_missing_key_precedes_artifacts_and_worktree_then_retry_succeeds(self):
        subprocess.run(["git", "init", "-q"], cwd=self.workdir, check=True)
        missing = self._start(env={"FIREWORKS_API_KEY": ""}, worktree="retry-wt")
        self.assertFalse(missing.get("ok"), missing)
        self.assertIn("FIREWORKS_API_KEY", missing["error"])
        self.assertEqual(self.captured, [])
        self.assertFalse((self.artifact_dir / "status.md").exists())
        self.assertFalse((self.artifact_dir / "outcome.md").exists())
        self.assertFalse((self.artifact_dir.parent / claude_orchestrate.WORKTREES_DIRNAME).exists())

        with_key = self._start(env={"FIREWORKS_API_KEY": "DUMMY_FW"}, worktree="retry-wt")
        self.assertTrue(with_key.get("ok"), with_key)
        self.assertEqual(len(self._launch_cmds()), 1)
        self.assertEqual(json.loads((self.artifact_dir / "meta.json").read_text())["model"], claude_orchestrate.FIREWORKS_MODEL)

    def test_state_failure_precedes_worktree_then_retry_trusts_execution_dir(self):
        subprocess.run(["git", "init", "-q"], cwd=self.workdir, check=True)
        real_update = claude_orchestrate._update_k3_state
        attempted_paths = []

        def fail_once(k3_config, rundir, fireworks_key):
            attempted_paths.append(Path(rundir))
            if len(attempted_paths) == 1:
                return "K3 state is locked by another launch"
            return real_update(k3_config, rundir, fireworks_key)

        with patch.object(claude_orchestrate, "_update_k3_state", side_effect=fail_once):
            failed = self._start(worktree="retry-state-wt")
            self.assertFalse(failed.get("ok"), failed)
            self.assertIn("locked", failed["error"])
            self.assertEqual(self.captured, [])
            self.assertFalse((self.artifact_dir / "status.md").exists())
            self.assertFalse((self.artifact_dir / "outcome.md").exists())
            self.assertFalse((self.artifact_dir.parent / claude_orchestrate.WORKTREES_DIRNAME).exists())

            retried = self._start(worktree="retry-state-wt")
            self.assertTrue(retried.get("ok"), retried)

        expected = (self.workdir.parent / claude_orchestrate.WORKTREES_DIRNAME / "retry-state-wt").resolve()
        self.assertEqual(attempted_paths, [expected, expected])
        state = json.loads((self.artifact_dir / "claude-k3-config" / ".claude.json").read_text())
        self.assertEqual(set(state["projects"]), {str(expected)})
        self.assertTrue(state["projects"][str(expected)]["hasTrustDialogAccepted"])
        self.assertIn(f"cd {shlex.quote(str(expected))}", self._launch_cmds()[0][-1])

    def test_stale_k3_lock_file_is_reused_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            k3 = Path(tmp) / "claude-k3-config"
            k3.mkdir()
            lock_path = k3 / ".state-update.lock"
            lock_path.write_bytes(b"stale owner\n")
            with patch("time.sleep", side_effect=AssertionError("waited on a stale lock file")):
                self.assertIsNone(claude_orchestrate._update_k3_state(k3, "/repo/one", "DUMMY_FW"))
                first = json.loads((k3 / ".claude.json").read_text())
                self.assertIsNone(claude_orchestrate._update_k3_state(k3, "/repo/one", "DUMMY_FW"))
                self.assertEqual(json.loads((k3 / ".claude.json").read_text()), first)
            self.assertTrue(lock_path.exists())
            self.assertEqual(set(first["projects"]), {"/repo/one"})

    def test_k3_state_lock_is_held_through_atomic_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            k3 = Path(tmp) / "claude-k3-config"
            k3.mkdir()
            lock_path = k3 / ".state-update.lock"
            real_replace = os.replace

            def checked_replace(src, dst):
                probe = self._try_lock_file(lock_path)
                if probe is not None:
                    probe.close()
                self.assertIsNone(probe, "state lock was not held during os.replace")
                return real_replace(src, dst)

            with patch.object(claude_orchestrate.os, "replace", side_effect=checked_replace):
                self.assertIsNone(claude_orchestrate._update_k3_state(k3, "/repo", "DUMMY_FW"))
            probe = self._try_lock_file(lock_path)
            self.assertIsNotNone(probe, "state lock was not released after update")
            probe.close()

    def test_invalid_k3_state_is_refused_before_artifacts(self):
        for raw in ("{broken", json.dumps({"projects": None}), json.dumps({"customApiKeyResponses": {"approved": None}})):
            with self.subTest(state=raw):
                k3 = self.artifact_dir / "claude-k3-config"
                k3.mkdir(exist_ok=True)
                (k3 / ".claude.json").write_text(raw)
                res = self._start()
                self.assertFalse(res.get("ok"), res)
                self.assertIn("invalid K3 state", res["error"])
                self.assertFalse((self.artifact_dir / "status.md").exists())
                self.assertFalse((self.artifact_dir / "outcome.md").exists())

    def test_k3_updates_merge_distinct_project_trust_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            k3 = Path(tmp) / "claude-k3-config"
            self.assertIsNone(claude_orchestrate._update_k3_state(k3, "/repo/one", "DUMMY_FW"))
            self.assertIsNone(claude_orchestrate._update_k3_state(k3, "/repo/two", "DUMMY_FW"))
            state = json.loads((k3 / ".claude.json").read_text())
            self.assertEqual(set(state["projects"]), {"/repo/one", "/repo/two"})
            self.assertTrue(all(project["hasTrustDialogAccepted"] for project in state["projects"].values()))

    def test_codex_truefoundry_unchanged(self):
        for provider in (None, "truefoundry"):
            with self.subTest(provider=provider):
                kwargs = {"executor": "codex", "model": "gpt-6-sol"}
                if provider:
                    kwargs["model_provider"] = provider
                res = self._start(**kwargs)
                self.assertTrue(res.get("ok"), res)


class NativeClaudeStatusTest(unittest.TestCase):
    def test_active_k3_status_precedes_legacy_status_for_reused_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "claude-seatbelt-config" / "sessions"
            active = Path(tmp) / "claude-k3-config" / "sessions"
            legacy.mkdir(parents=True)
            active.mkdir(parents=True)
            (legacy / "legacy.json").write_text(json.dumps({"tmux": "t2-reused:1.0", "status": "idle"}))
            (active / "active.json").write_text(json.dumps({"tmux": "t2-reused:1.0", "status": "working"}))
            (legacy / "legacy-only.json").write_text(json.dumps({"tmux": "t2-legacy:1.0", "status": "idle"}))
            with patch.object(claude_orchestrate, "get_hermes_home", return_value=Path(tmp)):
                self.assertEqual(claude_orchestrate._native_claude_status("t2-reused"), "working")
                self.assertEqual(claude_orchestrate._native_claude_status("t2-legacy"), "idle")


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
        launch_env = {"FIREWORKS_API_KEY": "DUMMY_FW"} if args.get("executor") == "claude" else {}
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_artifact_dir", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "get_hermes_home", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "_session_state", return_value={"state": "working"}), \
             patch.object(claude_orchestrate, "_run", side_effect=self._fake_run), \
             patch("time.sleep"), \
             patch.dict(os.environ, launch_env, clear=True):
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
        res = self._start(worktree="wt1", executor="claude", model_provider="fireworks", model=None)
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("trust_level", self._shell_cmd())


if __name__ == "__main__":
    unittest.main()
