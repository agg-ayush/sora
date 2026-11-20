"""K3 setup preserves isolated Claude session state while pinning Fireworks defaults."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "setup-claude-k3.sh"
MODEL = "accounts/fireworks/models/kimi-k3p1-pro"


class K3SetupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        self.hermes = self.home / ".hermes"
        self.hermes.mkdir()
        (self.hermes / ".env").write_text("FIREWORKS_API_KEY=DUMMY\n")
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        claude = bin_dir / "claude"
        claude.write_text("#!/bin/sh\nexit 0\n")
        claude.chmod(0o755)
        self.env = {**os.environ, "HERMES_HOME": str(self.hermes), "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"}
        self.k3 = self.hermes / "claude-k3-config"

    def run_setup(self):
        return subprocess.run(["bash", str(SCRIPT)], env=self.env, capture_output=True, text=True, timeout=30)

    def test_existing_state_and_plugins_survive_repeated_setup(self):
        self.k3.mkdir()
        state = {
            "hasCompletedOnboarding": True,
            "projects": {"/repo": {"hasTrustDialogAccepted": True}},
            "customApiKeyResponses": {"approved": ["existing-key"]},
            "otherSessionState": {"keep": True},
        }
        (self.k3 / ".claude.json").write_text(json.dumps(state))
        (self.k3 / "settings.json").write_text(json.dumps({
            "model": "old-model",
            "enabledPlugins": {"demo@market": True},
            "env": {
                "KEEP": "yes",
                "ANTHROPIC_BASE_URL": "https://legacy.invalid",
                "ANTHROPIC_CUSTOM_HEADERS": "x-legacy: secret",
                "ANTHROPIC_API_KEY_BACKUP": "OLD_BACKUP",
            },
        }))

        first = self.run_setup()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        first_state = json.loads((self.k3 / ".claude.json").read_text())
        first_settings = json.loads((self.k3 / "settings.json").read_text())
        self.assertEqual(first_state, {**state, "env": {}})
        self.assertEqual(first_settings, {
            "model": MODEL,
            "enabledPlugins": {"demo@market": True},
            "env": {"KEEP": "yes"},
        })

        second = self.run_setup()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(json.loads((self.k3 / ".claude.json").read_text()), first_state)
        self.assertEqual(json.loads((self.k3 / "settings.json").read_text()), first_settings)

    def test_linked_shared_rules_and_skills_are_not_overwritten(self):
        shared = self.home / ".claude"
        shared_skills = shared / "skills"
        shared_skills.mkdir(parents=True)
        shared_rules = shared / "CLAUDE.md"
        shared_rules.write_text("custom shared rules\n")
        shared_skill = shared_skills / "SKILL.md"
        shared_skill.write_text("custom shared skill\n")
        self.k3.mkdir()
        (self.k3 / "CLAUDE.md").symlink_to(shared_rules)
        (self.k3 / "skills").symlink_to(shared_skills, target_is_directory=True)
        (self.hermes / "skills" / "demo").mkdir(parents=True)
        (self.hermes / "skills" / "demo" / "SKILL.md").write_text("replacement skill\n")

        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(shared_rules.read_text(), "custom shared rules\n")
        self.assertEqual(shared_skill.read_text(), "custom shared skill\n")

    def test_invalid_existing_json_is_not_replaced(self):
        self.k3.mkdir()
        state_path = self.k3 / ".claude.json"
        state_path.write_text("{broken")
        result = self.run_setup()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid JSON", result.stderr)
        self.assertEqual(state_path.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
