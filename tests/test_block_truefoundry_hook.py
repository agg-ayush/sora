"""Tests for the Claude Code managed hook that blocks the TrueFoundry gateway."""

import json
import os
import subprocess
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "config" / "claude-code" / "block-truefoundry-hook.sh"
SETTINGS = HOOK.parent / "managed-settings.json"
TF = "https://<llm-gateway>.truefoundry.cloud/api/llm"


def run_hook(mode="prompt", **env):
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update(env)
    return subprocess.run(["sh", str(HOOK), mode], env=base, capture_output=True, text=True, timeout=10)


class BlockTruefoundryHookTest(unittest.TestCase):
    def test_truefoundry_blocks_prompt(self):
        r = run_hook(ANTHROPIC_BASE_URL=TF)
        self.assertEqual(r.returncode, 2)
        self.assertIn("TrueFoundry", r.stderr)
        self.assertIn("seatbelt", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_case_insensitive_and_other_base_url_vars(self):
        for var in ("ANTHROPIC_BASE_URL", "ANTHROPIC_BEDROCK_BASE_URL", "ANTHROPIC_VERTEX_BASE_URL"):
            with self.subTest(var=var):
                self.assertEqual(run_hook(**{var: "https://TrueFoundry.example/x"}).returncode, 2)

    def test_session_start_emits_stop_json(self):
        r = run_hook("session", ANTHROPIC_BASE_URL=TF)
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)
        self.assertIs(out["continue"], False)
        self.assertIn("TrueFoundry", out["stopReason"])

    def test_allowed_endpoints_are_silent(self):
        for url in ("https://<model-gateway>", "https://api.fireworks.ai/inference", None):
            for mode in ("prompt", "session"):
                with self.subTest(url=url, mode=mode):
                    env = {"ANTHROPIC_BASE_URL": url} if url else {}
                    r = run_hook(mode, **env)
                    self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_other_variables_mentioning_truefoundry_do_not_block(self):
        r = run_hook(TFY_BASE="https://<llm-gateway>.truefoundry.cloud", ANTHROPIC_BASE_URL="https://<model-gateway>")
        self.assertEqual(r.returncode, 0)

    def test_fails_open_without_tools(self):
        # No PATH at all: grep/env are missing, so nothing can match; must still exit 0 quietly.
        r = subprocess.run(["/bin/sh", str(HOOK), "prompt"], env={"ANTHROPIC_BASE_URL": TF, "PATH": "/nonexistent"},
                           capture_output=True, text=True, timeout=10)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_scrubbed_env_falls_back_to_parent_process(self):
        # The hook's own env is empty; its parent (a non-platform process, like
        # Claude Code itself) carries the endpoint. Apple platform binaries such
        # as /bin/bash hide their environment, so the parent here is Python.
        import sys
        code = (
            "import subprocess,sys;"
            f"r=subprocess.run(['env','-i','PATH='+__import__('os').environ['PATH'],'sh',{str(HOOK)!r},'prompt'],capture_output=True);"
            "print('rc=%d'%r.returncode)"
        )
        for url, want in ((TF, "rc=2"), ("https://<model-gateway>", "rc=0")):
            with self.subTest(url=url):
                r = subprocess.run([sys.executable, "-c", code], env={"PATH": os.environ.get("PATH", ""), "ANTHROPIC_BASE_URL": url},
                                   capture_output=True, text=True, timeout=20)
                self.assertIn(want, r.stdout, r.stderr)

    def test_managed_settings_contains_only_the_two_hooks(self):
        cfg = json.loads(SETTINGS.read_text())
        self.assertEqual(set(cfg), {"hooks"})
        self.assertEqual(set(cfg["hooks"]), {"SessionStart", "UserPromptSubmit"})
        self.assertIn("__HOOK_PATH__", json.dumps(cfg))


if __name__ == "__main__":
    unittest.main()
