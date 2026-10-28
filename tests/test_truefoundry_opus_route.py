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
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._workdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._workdir.cleanup)
        self.hermes_home = Path(self._tmpdir.name)
        self.artifact_dir = self.hermes_home / "tasks" / "t2-test-tf-route"
        self.workdir = self._workdir.name
        self.captured_cmds = []
        # Scripted pane contents: each capture-pane pops the head; the last
        # entry repeats. Empty list means the pane never shows anything.
        self.pane_texts = []
        self.launch_rc = 0
        self.handoff_ok = True
        self.handoffs = []
        self.pinned_claude = self.hermes_home / "claude-opus55-cli" / "node_modules" / ".bin" / "claude"
        self.pinned_claude.parent.mkdir(parents=True)
        self.pinned_claude.write_text("#!/bin/sh\n")
        os.chmod(self.pinned_claude, 0o755)

    def _fake_run(self, cmd, timeout=None):
        self.captured_cmds.append(cmd)
        out = ""
        if cmd[:2] == ["tmux", "capture-pane"] and self.pane_texts:
            out = self.pane_texts.pop(0) if len(self.pane_texts) > 1 else self.pane_texts[0]
        if cmd[:3] == ["tmux", "new-session", "-d"] and self.launch_rc:
            return subprocess.CompletedProcess(cmd, self.launch_rc, "", "boom")
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def _fake_handoff(self, fifo, secret, timeout=None):
        # Stands in for the shell reader: inspects the live FIFO, never blocks.
        fifo = Path(fifo)
        st = os.lstat(fifo)
        self.handoffs.append({
            "path": fifo,
            "is_fifo": stat.S_ISFIFO(st.st_mode),
            "mode": stat.S_IMODE(st.st_mode),
            "dir_mode": stat.S_IMODE(os.lstat(fifo.parent).st_mode),
            "secret": secret,
            "after_launch": any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds),
        })
        return self.handoff_ok

    def _start(self, env, **overrides):
        args = {
            "task_id": "t2-test-tf-route",
            "prompt": "reply PONG",
            "workdir": self.workdir,
            "executor": "claude",
            "model_provider": "truefoundry",
            "model": OPUS,
        }
        args.update(overrides)
        with patch.object(claude_orchestrate, "_session_exists", side_effect=[False] + [True] * 60), \
             patch.object(claude_orchestrate, "_artifact_dir", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "get_hermes_home", return_value=self.hermes_home), \
             patch.object(claude_orchestrate, "_run", side_effect=self._fake_run), \
             patch.object(claude_orchestrate, "_handoff_secret_via_fifo", side_effect=self._fake_handoff), \
             patch("time.sleep"), \
             patch.dict(os.environ, env, clear=True):
            return claude_orchestrate._start(args)

    def _ready_pane(self):
        self.pane_texts = ["⏵⏵ auto mode on ❯"]

    def _sent_keys(self):
        return [c for c in self.captured_cmds if c[:2] == ["tmux", "send-keys"]]

    def _shell_cmd(self):
        for cmd in self.captured_cmds:
            if cmd[:3] == ["tmux", "new-session", "-d"]:
                return cmd[-1]
        self.fail("no tmux new-session captured")

    def test_opus_route_injects_tf_auth_by_reference(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), {k: v for k, v in res.items() if k != "error"})
        cmd = self._shell_cmd()
        self.assertIn(f"export ANTHROPIC_BASE_URL={TF_URL}", cmd)
        self.assertIn(TOKEN_REF, cmd)
        self.assertIn(f"--model {OPUS}", cmd)

    def test_auth_export_precedes_env_scrub(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"))
        cmd = self._shell_cmd()
        # $TFY_API_KEY must be captured into ANTHROPIC_AUTH_TOKEN before the
        # scrub unsets TFY_API_KEY, or the session gets an empty token.
        self.assertLess(cmd.index(TOKEN_REF), cmd.index("unset GITHUB_TOKEN"))

    def test_opus_route_enables_subprocess_env_scrub(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("export CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1 && ", cmd)
        # Scrub must be exported before claude launches to affect the session.
        self.assertLess(cmd.index("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1"), cmd.index(f"--model {OPUS}"))

    def test_opus_route_grants_artifact_dir_and_literal_path_instruction(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        artifact_abs = self.artifact_dir.resolve().as_posix()
        self.assertIn(f"--add-dir {artifact_abs}", cmd)
        # Opus launches idle: the brief is NOT a positional arg (a startup
        # prompt drops auto mode to manual; --add-dir is variadic).
        self.assertNotIn("reply PONG", cmd)
        self.assertNotIn(" -- ", cmd)
        # The brief rides in plugin-owned prompt.md with full instructions.
        brief = (self.artifact_dir / "prompt.md").read_text()
        self.assertIn("reply PONG", brief)
        self.assertIn("with Bash redirects to those literal absolute paths", brief)
        self.assertIn("no shell variables, command substitutions, or the built-in Write tool", brief)
        self.assertIn(artifact_abs, brief)

    def test_opus_route_hands_off_brief_once_auto_mode_live(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        self.assertTrue(res.get("auto_mode_ready"))
        keys = self._sent_keys()
        prompt_md = (self.artifact_dir / "prompt.md").resolve().as_posix()
        self.assertIn(["tmux", "send-keys", "-t", "t2-test-tf-route", "-l",
                       f"Read {prompt_md} in full and execute it."], keys)
        self.assertEqual(keys[-1], ["tmux", "send-keys", "-t", "t2-test-tf-route", "Enter"])
        self.assertFalse(any("BTab" in c for c in keys))  # already auto: no cycling

    def test_opus_route_cycles_btab_manual_to_auto(self):
        # Scrub forces a manual start; Shift+Tab cycles
        # manual → acceptEdits → plan → auto.
        self.pane_texts = [
            "❯ manual mode on",
            "❯ ⏵⏵ accept edits on",
            "❯ ⏸ plan mode on",
            "❯ ⏵⏵ auto mode on",
        ]
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        self.assertTrue(res.get("auto_mode_ready"))
        keys = self._sent_keys()
        self.assertEqual(sum("BTab" in c for c in keys), 3)
        self.assertTrue(any("-l" in c for c in keys))  # brief handed over after auto

    def test_opus_route_fails_closed_when_auto_never_reached(self):
        self.pane_texts = ["❯ manual mode on"]  # BTab never reaches auto
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertFalse(res.get("ok"))
        self.assertIn("auto mode never came up", res.get("error", ""))
        keys = self._sent_keys()
        self.assertLessEqual(sum("BTab" in c for c in keys), 4)
        self.assertFalse(any("-l" in c for c in keys))  # brief never sent
        self.assertIn(["tmux", "kill-session", "-t", "t2-test-tf-route"], self.captured_cmds)

    def test_opus_route_uses_permission_mode_auto_not_bypass(self):
        # With the subprocess env scrub on, --dangerously-skip-permissions
        # still starts in manual mode and prompts for safe artifact writes.
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("--permission-mode auto", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)

    def _session_settings(self):
        return json.loads((self.artifact_dir / "deny-settings.json").read_text())

    def test_opus_route_disables_model_switch_on_flag(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        settings = self._session_settings()
        self.assertIs(settings["switchModelsOnFlag"], False)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["matcher"], "Bash")

    def test_other_routes_settings_have_no_model_switch_key(self):
        for kwargs, env in (
            ({"model": "some-other-model"}, {"TFY_API_KEY": "DUMMY"}),
            ({"model": None}, {"TFY_API_KEY": "DUMMY"}),
            ({"model": OPUS, "model_provider": "fireworks"}, {"TFY_API_KEY": "DUMMY", "FIREWORKS_API_KEY": "DUMMY2"}),
        ):
            res = self._start(env, **kwargs)
            self.assertTrue(res.get("ok"), res)
            settings = self._session_settings()
            self.assertNotIn("switchModelsOnFlag", settings)
            self.assertEqual(list(settings), ["hooks"])

    def test_opus_route_launches_pinned_executable(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn(f"&& {self.pinned_claude.as_posix()} --permission-mode auto", cmd)
        self.assertNotIn("&& claude ", cmd)

    def test_other_routes_keep_global_claude(self):
        res = self._start({"TFY_API_KEY": "DUMMY"}, model="some-other-model")
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("&& claude --dangerously-skip-permissions", cmd)
        self.assertNotIn("claude-opus55-cli", cmd)

    def test_opus_route_fails_closed_when_pinned_missing(self):
        self.pinned_claude.unlink()
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertFalse(res.get("ok"))
        self.assertIn("pinned claude executable", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_opus_route_fails_closed_when_pinned_not_executable(self):
        os.chmod(self.pinned_claude, 0o644)
        res = self._start({"TFY_API_KEY": "DUMMY"})
        self.assertFalse(res.get("ok"))
        self.assertIn("pinned claude executable", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_non_opus_routes_have_no_delimiter(self):
        for kwargs, env in (
            ({"model": "some-other-model"}, {"TFY_API_KEY": "DUMMY"}),
            ({"model": None}, {"TFY_API_KEY": "DUMMY"}),
            ({"model": OPUS, "model_provider": "fireworks"}, {"TFY_API_KEY": "DUMMY", "FIREWORKS_API_KEY": "DUMMY2"}),
        ):
            self.captured_cmds.clear()
            res = self._start(env, **kwargs)
            self.assertTrue(res.get("ok"), res)
            cmd = self._shell_cmd()
            self.assertNotIn("--add-dir", cmd)
            self.assertNotIn(" -- ", cmd)
            self.assertNotIn("--permission-mode auto", cmd)
            self.assertIn("--dangerously-skip-permissions", cmd)
            self.assertIn("reply PONG", cmd)  # positional prompt retained
            self.assertFalse(self._sent_keys())
            self.assertNotIn("auto_mode_ready", res)

    def test_opus_route_fails_closed_without_tfy_key(self):
        res = self._start({})
        self.assertFalse(res.get("ok"))
        self.assertIn("failing closed", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_no_truefoundry_api_key_fallback(self):
        res = self._start({"TRUEFOUNDRY_API_KEY": "DUMMY"})
        self.assertFalse(res.get("ok"))

    def test_other_truefoundry_model_unchanged(self):
        res = self._start({"TFY_API_KEY": "DUMMY"}, model="some-other-model")
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertNotIn("ANTHROPIC_BASE_URL", cmd)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", cmd)
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", cmd)
        self.assertIn("--model some-other-model", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("literal absolute paths", cmd)
        # Non-Opus: positional prompt retained, prompt.md stays the raw prompt.
        self.assertIn("reply PONG", cmd)
        self.assertEqual((self.artifact_dir / "prompt.md").read_text(), "reply PONG")
        self.assertFalse(self._sent_keys())

    def test_default_truefoundry_no_model_unchanged(self):
        res = self._start({"TFY_API_KEY": "DUMMY"}, model=None)
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertNotIn("ANTHROPIC_BASE_URL", cmd)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", cmd)
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("literal absolute paths", cmd)

    def test_fireworks_path_unchanged(self):
        res = self._start(
            {"TFY_API_KEY": "DUMMY", "FIREWORKS_API_KEY": "DUMMY2"},
            model=OPUS, model_provider="fireworks",
        )
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("https://api.fireworks.ai/inference", cmd)
        self.assertNotIn(TF_URL, cmd)
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", cmd)
        self.assertNotIn("--model", cmd)  # fireworks sets the model via env
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("literal absolute paths", cmd)

    def test_codex_executor_unchanged(self):
        with patch.object(claude_orchestrate, "_session_state", return_value={"state": "working"}), \
             patch("time.sleep"):
            res = self._start(
                {"TFY_API_KEY": "DUMMY"},
                executor="codex", model="gpt-6-sol", model_provider="truefoundry",
            )
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertNotIn("ANTHROPIC_BASE_URL", cmd)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", cmd)
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", cmd)
        self.assertIn("-m gpt-6-sol", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("literal absolute paths", cmd)

    # --- TFY_API_KEY FIFO handoff -------------------------------------------

    def _assert_secret_absent(self, res):
        for cmd in self.captured_cmds:
            for arg in cmd:
                self.assertNotIn(SECRET, arg)
        self.assertNotIn(SECRET, json.dumps(res))
        for path in self.hermes_home.rglob("*"):
            if path.is_file() and not path.is_symlink():
                self.assertNotIn(SECRET.encode(), path.read_bytes(), path)

    def _fifo_dir(self):
        return self.hermes_home / "cache" / "secret-handoff"

    def test_opus_route_no_literal_secret_anywhere(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("export TFY_API_KEY=", self._shell_cmd())
        self._assert_secret_absent(res)

    def test_opus_route_hands_secret_over_private_fifo_after_launch(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(len(self.handoffs), 1)
        h = self.handoffs[0]
        self.assertEqual(h["secret"], SECRET)
        self.assertTrue(h["after_launch"])
        self.assertTrue(h["is_fifo"])
        self.assertEqual(h["mode"] & 0o077, 0)
        self.assertEqual(h["dir_mode"], 0o700)
        self.assertEqual(h["path"].parent, self._fifo_dir().resolve())
        self.assertFalse(h["path"].is_relative_to(self.artifact_dir.resolve()))
        self.assertFalse(h["path"].is_relative_to(Path(self.workdir).resolve()))

    def test_opus_route_shell_reads_fifo_before_auth_and_scrub(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        read = f"IFS= read -r TFY_API_KEY < {shlex.quote(self.handoffs[0]['path'].as_posix())} && "
        self.assertTrue(cmd.startswith(read), cmd)
        self.assertLess(cmd.index(read), cmd.index(TOKEN_REF))
        self.assertLess(cmd.index(TOKEN_REF), cmd.index("unset TFY_API_KEY"))
        self.assertLess(cmd.index("unset TFY_API_KEY"), cmd.index(self.pinned_claude.as_posix()))

    def test_opus_route_unlinks_fifo_on_success(self):
        self._ready_pane()
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertTrue(res.get("ok"), res)
        self.assertFalse(os.path.lexists(self.handoffs[0]["path"]))
        self.assertEqual(list(self._fifo_dir().iterdir()), [])

    def test_opus_route_handoff_failure_kills_only_new_session_and_fails_closed(self):
        self._ready_pane()
        self.handoff_ok = False
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertFalse(res.get("ok"))
        self.assertIn("failing closed", res.get("error", ""))
        kills = [c for c in self.captured_cmds if c[:2] == ["tmux", "kill-session"]]
        self.assertEqual(kills, [["tmux", "kill-session", "-t", "=t2-test-tf-route"]])
        self.assertFalse(self._sent_keys())  # no brief, no mode cycling
        self.assertFalse(any(c[:2] == ["tmux", "pipe-pane"] for c in self.captured_cmds))
        self.assertFalse((self.artifact_dir / "meta.json").exists())
        self.assertFalse(os.path.lexists(self.handoffs[0]["path"]))
        self._assert_secret_absent(res)

    def test_opus_route_handoff_exception_fails_closed(self):
        self._ready_pane()
        with patch.object(self, "_fake_handoff", side_effect=RuntimeError("x")):
            res = self._start({"TFY_API_KEY": SECRET})
        self.assertFalse(res.get("ok"))
        self.assertIn(["tmux", "kill-session", "-t", "=t2-test-tf-route"], self.captured_cmds)
        self.assertEqual(list(self._fifo_dir().iterdir()), [])

    def test_opus_route_launch_failure_unlinks_fifo_without_handoff(self):
        self.launch_rc = 1
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertFalse(res.get("ok"))
        self.assertFalse(self.handoffs)
        self.assertEqual(list(self._fifo_dir().iterdir()), [])
        self._assert_secret_absent(res)

    def test_opus_route_fails_closed_on_unsafe_fifo_dir(self):
        self._fifo_dir().parent.mkdir(parents=True)
        self._fifo_dir().symlink_to(self.hermes_home)
        res = self._start({"TFY_API_KEY": SECRET})
        self.assertFalse(res.get("ok"))
        self.assertIn("failing closed", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_non_opus_routes_skip_fifo_handoff(self):
        for kwargs, env in (
            ({"model": "some-other-model"}, {"TFY_API_KEY": "DUMMY"}),
            ({"model": OPUS, "model_provider": "fireworks"}, {"TFY_API_KEY": "DUMMY", "FIREWORKS_API_KEY": "DUMMY2"}),
        ):
            self.captured_cmds.clear()
            res = self._start(env, **kwargs)
            self.assertTrue(res.get("ok"), res)
            self.assertFalse(self.handoffs)
            self.assertNotIn("read -r TFY_API_KEY", self._shell_cmd())
            self.assertIn("export TFY_API_KEY=DUMMY && ", self._shell_cmd())

    # --- seatbelt route -----------------------------------------------------

    FAKE_TFY = "DUMMYTFYKEY-12345678"
    FAKE_RC_TFY = "rc-prefix-12345678"  # shares the last 8 chars with FAKE_TFY
    FAKE_MAAT = "DUMMY-maat-token-abc"

    def _seatbelt_rc(self, tfy=None, maat=None, with_maat=True):
        home = self.hermes_home / "fakehome"
        home.mkdir(exist_ok=True)
        lines = [f"x-tfy-api-key: {tfy or self.FAKE_RC_TFY}"]
        if with_maat:
            lines.append(f"x-maat-token: {maat or self.FAKE_MAAT}'")
        body = "\n".join(lines)
        (home / ".zshrc").write_text(
            "# seatbelt_headers\nexport ANTHROPIC_CUSTOM_HEADERS=$'\n" + body + "\n"
        )
        (home / ".bashrc").write_text((home / ".zshrc").read_text())
        return home

    def _seatbelt_start(self, home, env=None, **overrides):
        kwargs = {"model_provider": "seatbelt", "model": "opus"}
        kwargs.update(overrides)
        with patch.object(claude_orchestrate, "_seatbelt_home", return_value=home):
            return self._start({"TFY_API_KEY": self.FAKE_TFY} if env is None else env, **kwargs)

    def test_seatbelt_opus_launch(self):
        res = self._seatbelt_start(self._seatbelt_rc())
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("export ANTHROPIC_BASE_URL=https://<model-gateway>", cmd)
        self.assertIn("export ANTHROPIC_AUTH_TOKEN=seatbelt", cmd)
        self.assertIn("export ANTHROPIC_DEFAULT_OPUS_MODEL='claude-teams-group/claude-opus-5-5[1m]'", cmd)
        self.assertIn("export ANTHROPIC_DEFAULT_SONNET_MODEL='claude-teams-group/claude-opus-5-5[1m]'", cmd)
        self.assertIn("ANTHROPIC_DEFAULT_HAIKU_MODEL=claude-teams-group/claude-haiku-4-5-20251001", cmd)
        self.assertIn("export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1", cmd)
        self.assertIn("export CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1", cmd)
        headers = f"x-tfy-api-key: {self.FAKE_RC_TFY}\nx-maat-token: {self.FAKE_MAAT}"
        self.assertIn(f"export ANTHROPIC_CUSTOM_HEADERS={shlex.quote(headers)}", cmd)
        self.assertNotIn("--model", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("read -r TFY_API_KEY", cmd)
        self.assertFalse(self.handoffs)
        # Ordering: unset API keys, then exports, then scrub, then claude.
        self.assertLess(cmd.index("unset ANTHROPIC_API_KEY"), cmd.index("ANTHROPIC_BASE_URL"))
        self.assertLess(cmd.index("ANTHROPIC_CUSTOM_HEADERS"), cmd.index("unset GITHUB_TOKEN"))
        self.assertNotIn("unset ANTHROPIC_CUSTOM_HEADERS", cmd)

    def test_seatbelt_sonnet_mapping(self):
        res = self._seatbelt_start(self._seatbelt_rc(), model="sonnet")
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("ANTHROPIC_DEFAULT_OPUS_MODEL='claude-teams-group/claude-sonnet-5-5[1m]'", cmd)
        self.assertNotIn("opus-5-5", cmd)

    def test_seatbelt_rejects_other_model(self):
        for model in ("k3", None, OPUS):
            res = self._seatbelt_start(self._seatbelt_rc(), model=model)
            self.assertFalse(res.get("ok"))
            self.assertIn("invalid model for seatbelt", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_seatbelt_rejects_codex_executor(self):
        res = self._seatbelt_start(self._seatbelt_rc(), executor="codex")
        self.assertFalse(res.get("ok"))
        self.assertIn("executor=claude", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_seatbelt_stale_rc_token_fails_closed(self):
        res = self._seatbelt_start(self._seatbelt_rc(tfy="rc-stale-00000000"))
        self.assertFalse(res.get("ok"))
        self.assertIn("stale", res.get("error", ""))
        self.assertIn("mismatch", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_seatbelt_missing_rc_or_header_fails_closed(self):
        empty_home = self.hermes_home / "emptyhome"
        empty_home.mkdir()
        res = self._seatbelt_start(empty_home)
        self.assertFalse(res.get("ok"))
        self.assertIn("not found", res.get("error", ""))
        res = self._seatbelt_start(self._seatbelt_rc(with_maat=False))
        self.assertFalse(res.get("ok"))
        self.assertIn("missing", res.get("error", ""))
        self.assertFalse(any(c[:3] == ["tmux", "new-session", "-d"] for c in self.captured_cmds))

    def test_seatbelt_requires_tfy_key(self):
        res = self._seatbelt_start(self._seatbelt_rc(), env={})
        self.assertFalse(res.get("ok"))
        self.assertIn("TFY_API_KEY", res.get("error", ""))

    def test_fireworks_route_uses_glm_not_kimi(self):
        res = self._start({"TFY_API_KEY": "DUMMY", "FIREWORKS_API_KEY": "DUMMY2"}, model_provider="fireworks")
        self.assertTrue(res.get("ok"), res)
        cmd = self._shell_cmd()
        self.assertIn("ANTHROPIC_MODEL=accounts/fireworks/models/glm-5p3", cmd)
        self.assertNotIn("kimi-k3", cmd)


class FifoSecretHandoffTest(unittest.TestCase):
    """Real FIFO transport, no _start harness."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.fifo = Path(self._tmpdir.name) / "h.fifo"
        os.mkfifo(self.fifo, 0o600)

    def test_writes_secret_line_to_reader_thread(self):
        got = []

        def reader():
            with open(self.fifo, "rb") as f:
                got.append(f.read())

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        self.assertTrue(claude_orchestrate._handoff_secret_via_fifo(self.fifo, SECRET, timeout=5))
        t.join(5)
        self.assertEqual(got, [SECRET.encode() + b"\n"])

    def test_posix_shell_read_receives_secret(self):
        # Shell only reports the length; the dummy secret never reaches stdout.
        proc = subprocess.Popen(
            ["sh", "-c", 'IFS= read -r TFY_API_KEY < "$1" && [ -n "$TFY_API_KEY" ] && printf %s "${#TFY_API_KEY}"', "sh", str(self.fifo)],
            stdout=subprocess.PIPE, text=True,
        )
        try:
            self.assertTrue(claude_orchestrate._handoff_secret_via_fifo(self.fifo, SECRET, timeout=5))
            out, _ = proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(out, str(len(SECRET)))

    def test_times_out_without_reader(self):
        t0 = time.monotonic()
        self.assertFalse(claude_orchestrate._handoff_secret_via_fifo(self.fifo, SECRET, timeout=0.2))
        self.assertLess(time.monotonic() - t0, 3)

    def test_missing_fifo_fails_fast(self):
        self.fifo.unlink()
        self.assertFalse(claude_orchestrate._handoff_secret_via_fifo(self.fifo, SECRET, timeout=5))

    def test_refuses_non_fifo_target(self):
        self.fifo.unlink()
        self.fifo.write_bytes(b"")
        self.assertFalse(claude_orchestrate._handoff_secret_via_fifo(self.fifo, SECRET, timeout=0.2))
        self.assertEqual(self.fifo.read_bytes(), b"")


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
        }
        args.update(overrides)
        with patch.object(claude_orchestrate, "_session_exists", return_value=False), \
             patch.object(claude_orchestrate, "_artifact_dir", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "get_hermes_home", return_value=self.artifact_dir), \
             patch.object(claude_orchestrate, "_session_state", return_value={"state": "working"}), \
             patch.object(claude_orchestrate, "_run", side_effect=self._fake_run), \
             patch("time.sleep"), \
             patch.dict(os.environ, {}, clear=True):
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
        res = self._start(worktree="wt1", executor="claude", model_provider="truefoundry", model=None)
        self.assertTrue(res.get("ok"), res)
        self.assertNotIn("trust_level", self._shell_cmd())


if __name__ == "__main__":
    unittest.main()
