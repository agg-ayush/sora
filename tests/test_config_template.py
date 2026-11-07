"""config/config.yaml.template must stay secret-free, portable and in sync with env.template."""

import re
import unittest
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE = (_ROOT / "config" / "config.yaml.template").read_text()
_ENV = (_ROOT / "config" / "env.template").read_text()

_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9_-]{8,}",
    r"\btfy[-_][A-Za-z0-9_-]{8,}",
    r"\bmaat[-_][A-Za-z0-9_-]{8,}",
    r"\bghp_|github_pat_|xox[bp]-|eyJ[A-Za-z0-9]",
    r"(?:: |- )(?![^\s]*/)[A-Za-z0-9+=_-]{32,}\s*$",  # long bare token as a value (model paths contain '/')
    r"\b[0-9a-f]{24,}\b",
    r"\b\d{9,}\b",  # chat / user ids
]
_CRED_KEY = re.compile(r"api_key|token|authorization|secret|password|x-tfy|x-maat", re.I)


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, node


class ConfigTemplateTest(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load(_TEMPLATE)

    def test_no_secret_looking_literals(self):
        for lineno, line in enumerate(_TEMPLATE.splitlines(), 1):
            for pat in _SECRET_PATTERNS:
                self.assertIsNone(re.search(pat, line), f"line {lineno} matches {pat}: {line[:80]}")

    def test_credential_keys_are_env_references(self):
        allowed_literals = {"", "placeholder"}  # seatbelt dummy api_key, empty delegation api_key
        for path, value in _walk(self.cfg):
            if _CRED_KEY.search(path.rsplit("/", 1)[-1]) and not isinstance(value, (int, float, bool)):
                ok = re.fullmatch(r"\$\{[A-Z0-9_]+\}", str(value)) or str(value) in allowed_literals
                self.assertTrue(ok, f"{path} must be a ${{ENV}} reference")

    def test_no_machine_paths_or_chat_ids(self):
        self.assertNotRegex(_TEMPLATE, r"/Users/|/home/")
        for forbidden in ("platforms", "onboarding", "_left_core_installed", "update"):
            self.assertNotIn(forbidden, self.cfg)

    def test_env_template_lists_every_referenced_variable(self):
        referenced = set(re.findall(r"\$\{([A-Z0-9_]+)\}", _TEMPLATE))
        declared = set(re.findall(r"^([A-Z0-9_]+)=", _ENV, re.M))
        self.assertFalse(referenced - declared, f"missing from env.template: {sorted(referenced - declared)}")
        for line in _ENV.splitlines():
            if re.match(r"^(\w*(KEY|TOKEN|AUTHORIZATION|SECRET|PASSWORD)\w*)=.+", line):
                self.fail(f"env.template must hold names only: {line.split('=')[0]}")

    def test_current_routing(self):
        c = self.cfg
        self.assertEqual((c["model"]["provider"], c["model"]["default"]), ("seatbelt", "claude-teams-group/claude-opus-5-5"))
        self.assertEqual(
            [(f["provider"], f["model"]) for f in c["fallback_providers"]],
            [("fireworks", "accounts/fireworks/models/kimi-k3p1-pro"), ("truefoundry", "gemini-group/gemini-4-argon")],
        )
        self.assertEqual((c["delegation"]["provider"], c["delegation"]["model"]), ("seatbelt", "claude-teams-group/claude-sonnet-5-5"))
        vision = c["auxiliary"]["vision"]
        self.assertEqual((vision["provider"], vision["model"]), ("auto", ""))
        self.assertEqual(len(vision["fallback_chain"]), 2)
        self.assertEqual(c["auxiliary"]["web_extract"], {"provider": "seatbelt", "model": "claude-teams-group/claude-opus-5-5"})
        self.assertTrue(c["model_overrides"]["fireworks"]["accounts/fireworks/models/kimi-k3p1-pro"]["supports_vision"])
        self.assertEqual((c["session_reset"]["mode"], c["session_reset"]["idle_minutes"]), ("idle", 10080))


if __name__ == "__main__":
    unittest.main()
