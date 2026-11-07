"""hosts/<profile>/ must stay secret-free, portable, and installable by setup-hermes.sh."""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_HOSTS = _ROOT / "hosts"
sys.path.insert(0, str(_ROOT / "devbox"))
import host_profile  # noqa: E402

_PROFILES = sorted(p for p in _HOSTS.iterdir() if p.is_dir())
_TEXT_SUFFIXES = {".py", ".sh", ".json", ".yaml", ".yml", ".txt", ".service", ".timer", ".plist", ".template", ""}

_SECRET_PATTERNS = [
    r"\bsk-[A-Za-z0-9_-]{8,}",
    r"\btfy[-_][A-Za-z0-9_-]{8,}",
    r"\bmaat[-_][A-Za-z0-9_-]{8,}",
    r"\bghp_|github_pat_|xox[bpas]-|eyJ[A-Za-z0-9]",
    r"\bAKIA[0-9A-Z]{12,}",
    r"\b[0-9a-f]{32,}\b",
    r"(?<![A-Za-z0-9/+_.-])(?=[A-Za-z0-9+]*\d)(?=[A-Za-z0-9+]*[a-z])(?=[A-Za-z0-9+]*[A-Z])[A-Za-z0-9+]{40,}={0,2}(?![A-Za-z0-9/+])",  # long base64-ish blob (no path separators)
]
_CHAT_ID = re.compile(r"(?<![\w.-])-?\d{9,}\b")


def _files(*roots: Path):
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in _TEXT_SUFFIXES:
                yield p


class HostProfileTest(unittest.TestCase):
    def test_profiles_exist(self):
        self.assertEqual({p.name for p in _PROFILES} >= {"mac", "sora"}, True)

    def test_cron_jobs_parse_and_are_complete(self):
        for prof in _PROFILES:
            data = json.loads((prof / "cron-jobs.json").read_text())
            names = [j["name"] for j in data["jobs"]]
            self.assertEqual(len(names), len(set(names)), f"duplicate job name in {prof.name}")
            for j in data["jobs"]:
                self.assertTrue(j.get("name") and j.get("schedule"), j)
                self.assertTrue(j.get("script") or j.get("prompt"), f"{j['name']}: needs script or prompt")
                self.assertIsInstance(j.get("enabled"), bool, j["name"])
                self.assertFalse({"id", "last_run_at", "next_run_at", "last_status", "repeat"} & set(j), j["name"])
                if j.get("no_agent"):
                    self.assertTrue(j.get("script"), f"{j['name']}: no_agent needs a script")
                if j.get("script"):
                    shared = _ROOT / "scripts" / j["script"]
                    own = prof / "scripts" / j["script"]
                    self.assertTrue(shared.is_file() or own.is_file(), f"{prof.name}/{j['name']}: script {j['script']} not in repo")

    def test_mac_never_delivers_to_telegram(self):
        data = json.loads((_HOSTS / "mac" / "cron-jobs.json").read_text())
        for j in data["jobs"]:
            self.assertNotIn("telegram", j["deliver"], j["name"])
        over = yaml.safe_load((_HOSTS / "mac" / "config-overrides.yaml").read_text())
        self.assertNotIn("telegram", over.get("platforms") or {})
        self.assertIn("platforms/telegram", over["plugins"]["disabled"])
        wd = json.loads((_HOSTS / "mac" / "watchdog.json").read_text())
        self.assertTrue(wd["channel"].startswith("ssh:"))

    def test_config_overrides_and_watchdog_parse(self):
        for prof in _PROFILES:
            self.assertIsInstance(yaml.safe_load((prof / "config-overrides.yaml").read_text()), dict)
            self.assertIn("expect", json.loads((prof / "watchdog.json").read_text()))
            self.assertTrue((prof / "plugins.txt").is_file())

    def test_no_secret_patterns(self):
        for p in _files(_HOSTS, _ROOT / "config"):
            for lineno, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                for pat in _SECRET_PATTERNS:
                    m = re.search(pat, line)
                    if m and "${" not in m.group(0):
                        self.fail(f"{p.relative_to(_ROOT)}:{lineno} matches {pat}: {line.strip()[:80]}")

    def test_no_numeric_chat_ids(self):
        for p in _files(_HOSTS, _ROOT / "config", _ROOT / "scripts" / "watchdog.json.example", _ROOT / "scripts" / "aws-keep-hot-linux.sh"):
            for lineno, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                self.assertIsNone(_CHAT_ID.search(line), f"{p.relative_to(_ROOT)}:{lineno}: {line.strip()[:80]}")

    def test_no_machine_specific_home_paths(self):
        for p in _files(_HOSTS):
            ref = "reference" in p.parts
            text = p.read_text(errors="replace")
            self.assertNotRegex(text, r"/home/ubuntu|/Users/ayush", str(p.relative_to(_ROOT)) + (" (reference)" if ref else ""))

    def test_env_template_has_names_only_and_covers_host_vars(self):
        env = (_ROOT / "config" / "env.template").read_text()
        declared = set(re.findall(r"^([A-Z0-9_]+)=", env, re.M))
        for line in env.splitlines():
            if re.match(r"^\w*(KEY|TOKEN|AUTHORIZATION|SECRET|PASSWORD|CHAT|CHANNEL)\w*=.+", line):
                self.fail(f"env.template must hold names only: {line.split('=')[0]}")
        for name in ("TI_CONCERN_TELEGRAM_CHAT", "TELEGRAM_HOME_CHANNEL", "GOG_KEYRING_PASSWORD", "TI_HIRING_TRACKER_DOC_ID",
                     "GITHUB_TOKEN", "NOTION_API_KEY", "PARALLEL_API_KEY", "RECALL_API_KEY", "SDE_SCREENING_GOOGLE_CLIENT_ID"):
            self.assertIn(name, declared)
        for prof in _PROFILES:
            for ref in re.findall(r"\$\{([A-Z0-9_]+)\}", (prof / "config-overrides.yaml").read_text()):
                self.assertIn(ref, declared, f"{prof.name} override references undeclared ${{{ref}}}")

    def test_units_use_portable_paths(self):
        for p in (_HOSTS / "sora" / "systemd").rglob("*.service"):
            text = p.read_text()
            self.assertNotRegex(text, r"/home/|/Users/", p.name)
        for p in (_HOSTS / "mac" / "launchd").rglob("*.plist"):
            self.assertNotRegex(p.read_text(), r"/Users/", p.name)

    def test_shell_scripts_parse(self):
        for p in list(_HOSTS.rglob("*.sh")) + [_ROOT / "devbox" / "host-profile.sh", _ROOT / "devbox" / "setup-hermes.sh"]:
            r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{p}: {r.stderr}")

    def test_python_scripts_compile(self):
        for p in _HOSTS.rglob("*.py"):
            compile(p.read_text(), str(p), "exec")


class HelperTest(unittest.TestCase):
    def test_create_args_paused_job(self):
        a = host_profile.build_create_args(
            {"name": "x", "schedule": "every 5m", "script": "s.py", "no_agent": True, "prompt": "p", "deliver": "origin", "enabled": False}
        )
        self.assertEqual(a[:4], ["cron", "create", "every 5m", "p"])
        self.assertIn("--paused", a)
        self.assertIn("--no-agent", a)

    def test_create_args_agent_job_with_skills_and_workdir(self):
        a = host_profile.build_create_args(
            {"name": "y", "schedule": "0 * * * *", "prompt": "do it", "deliver": "local", "enabled": True,
             "skills": ["gog-cli"], "workdir": "$HOME/ti-hiring"}
        )
        self.assertNotIn("--paused", a)
        self.assertEqual(a[a.index("--skill") + 1], "gog-cli")
        self.assertNotIn("$HOME", a[a.index("--workdir") + 1])

    def test_deep_merge_replaces_lists_and_merges_dicts(self):
        out = host_profile.deep_merge({"a": {"b": 1, "c": [1]}, "k": 1}, {"a": {"c": [2]}, "n": 3})
        self.assertEqual(out, {"a": {"b": 1, "c": [2]}, "k": 1, "n": 3})

    def test_existing_jobs_are_never_recreated(self):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="    Name:      orphan-reaper\n    Name:      auth-canary\n", stderr="")

        jobs = _HOSTS / "mac" / "cron-jobs.json"
        host_profile.install_cron_jobs(jobs, True, run=run)
        creates = [c for c in calls if "create" in c]
        created_names = {c[c.index("--name") + 1] for c in creates}
        self.assertFalse({"orphan-reaper", "auth-canary"} & created_names)

    def test_mac_refuses_telegram_override(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "config.yaml"
            cfg.write_text("agent: {max_turns: 1}\n")
            ov = Path(d) / "config-overrides.yaml"
            ov.write_text("platforms:\n  telegram:\n    enabled: true\n")
            self.assertEqual(host_profile.apply_overrides(cfg, ov, True), 1)
            self.assertEqual(cfg.read_text(), "agent: {max_turns: 1}\n")


if __name__ == "__main__":
    unittest.main()
