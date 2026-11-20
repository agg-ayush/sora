"""hermes-state manifest, classification and the audit unclassified walk."""

import contextlib
import errno
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "scripts" / "hermes-state.py"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_MANIFEST = _ROOT / "config" / "state-manifest.yaml"

_ORIG_PATH = os.environ.get("PATH", "")
CLASSES = {"repo-managed", "personal-state", "secret", "history", "host-local", "platform-specific"}
ROOTS = {"hermes", "claude", "smem"}
PLATFORMS = {"mac", "linux", "wsl", "sora", "gateway"}


def _load():
    spec = importlib.util.spec_from_file_location("hermes_state_under_test", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_state_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class Sandbox:
    """A throwaway HOME with the three roots and a way to run `main` against it."""

    def __init__(self, case: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()
        self.hermes = self.home / ".hermes"
        self.claude = self.home / ".claude"
        self.smem = self.home / ".smem"
        self.hermes.mkdir()
        self.claude.mkdir()
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.orig_path = _ORIG_PATH
        self.mod = _load()
        env = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "HERMES_HOME": str(self.hermes),
                "HERMES_HOST_PROFILE": "mac",
                "PATH": str(self.bin),
                "GPG_STUB_LOG": str(self.home / "gpg.log"),
                "GPG_STUB_CAPTURE": str(self.home / "gpg.stdin"),
            },
        )
        env.start()
        case.addCleanup(env.stop)

    def root(self, name: str) -> Path:
        return {"hermes": self.hermes, "claude": self.claude, "smem": self.smem}[name]

    def populate(self, root: str, names, sockets=()):
        base = self.root(root)
        base.mkdir(exist_ok=True)
        for name in names:
            path = base / name
            if name in sockets:
                prev = os.getcwd()
                os.chdir(base)
                try:
                    s = socket.socket(socket.AF_UNIX)
                    s.bind(name)
                    s.close()
                finally:
                    os.chdir(prev)
            else:
                path.touch()

    def stub(self, name: str, text: str):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{text}\n")
        path.chmod(0o755)

    def gpg_stub(self):
        script = textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, os, sys
            argv = sys.argv[1:]
            decrypt = "--decrypt" in argv
            out = None if decrypt else argv[argv.index("--output") + 1]
            entry = {{"argv": argv, "mode": "decrypt" if decrypt else "encrypt"}}
            if out is not None:
                entry["out_exists"] = os.path.lexists(out)
            log = os.environ["GPG_STUB_LOG"]
            with open(log, "a") as f:
                f.write(json.dumps(entry) + "\\n")
            if decrypt:
                n = sum(1 for ln in open(log) if json.loads(ln)["mode"] == "decrypt") - 1
                if os.environ.get("GPG_STUB_DEC_FAIL_EARLY"):
                    sys.exit(2)
                with open(argv[argv.index("--decrypt") + 1], "rb") as f:
                    data = f.read()
                view, off = memoryview(data), 0
                try:
                    while off < len(data):
                        off += os.write(1, view[off : off + 65536])
                except BrokenPipeError:
                    sys.exit(2)
                exits = os.environ.get("GPG_STUB_DEC_EXITS", "").split(",")
                sys.exit(int(exits[n]) if n < len(exits) and exits[n] else 0)
            data = sys.stdin.buffer.read()
            with open(os.environ["GPG_STUB_CAPTURE"], "wb") as f:
                f.write(data)
            with open(out, "wb") as f:
                f.write(data)
            sys.exit(int(os.environ.get("GPG_STUB_EXIT", "0")))
            """
        )
        path = self.bin / "gpg"
        path.write_text(script)
        path.chmod(0o755)

    def link_tool(self, name: str):
        real = shutil.which(name, path=self.orig_path)
        if real is None:
            raise unittest.SkipTest(f"{name} not installed")
        (self.bin / name).symlink_to(real)

    def gpg_log(self):
        log = self.home / "gpg.log"
        return [json.loads(ln) for ln in log.read_text().splitlines()] if log.exists() else []

    def run_sub(self, *argv, stdin=subprocess.DEVNULL):
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), *argv],
            env=dict(os.environ),
            capture_output=True,
            text=True,
            check=False, timeout=30,
            cwd=self.home,
            stdin=stdin,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.mod.main(list(argv))
        return code, out.getvalue(), err.getvalue()


def _fixture(root: str):
    lines = (_FIXTURES / f"mac-{root}-entries.txt").read_text().splitlines()
    return [ln for ln in lines if ln]


def _write(path: Path, text: str) -> Path:
    path.write_text(textwrap.dedent(text))
    return path


class ManifestSchemaTest(unittest.TestCase):
    def test_manifest_schema_and_classes(self):
        import yaml

        data = yaml.safe_load(_MANIFEST.read_text())
        self.assertEqual(data["version"], 1)
        self.assertTrue(data["rules"])
        for rule in data["rules"]:
            self.assertIn(rule["class"], CLASSES, rule)
            self.assertIn(rule["root"], ROOTS, rule)
            self.assertTrue(rule["match"], rule)
            if rule["class"] == "platform-specific":
                self.assertIn(rule.get("platform"), PLATFORMS, rule)
            else:
                self.assertNotIn("carry", rule, rule)
                self.assertNotIn("platform", rule, rule)
        for skip in data["restore_skip"]:
            self.assertIn(skip["root"], ROOTS, skip)
            self.assertTrue(skip["match"], skip)
        for items in data["fingerprint_platform"].values():
            for tag in items.values():
                tags = tag if isinstance(tag, list) else [tag]
                self.assertTrue(tags and set(tags) <= PLATFORMS, tag)

    def test_loader_rejects_bad_class_root_and_platform(self):
        sb = Sandbox(self)
        base = "version: 1\nrules:\n  - {root: %s, match: x, class: %s%s}\n"
        for root, cls, extra in [
            ("hermes", "personal", ""),
            ("home", "secret", ""),
            ("hermes", "platform-specific", ""),
            ("hermes", "platform-specific", ", platform: macos"),
            ("hermes", "secret", ", carry: true"),
        ]:
            path = Path(tempfile.mkdtemp(dir=sb.home)) / "m.yaml"
            path.write_text(base % (root, cls, extra))
            code, _out, err = sb.run("--manifest", str(path), "audit")
            self.assertEqual(code, 2, (root, cls, extra, err))
            self.assertIn("manifest", err)
            self.assertNotIn("Traceback", err)


class SeedTest(unittest.TestCase):
    def _classify(self, sb, root, name):
        manifest = sb.mod.load_manifest(_MANIFEST)
        rule = sb.mod.classify(manifest, root, name)
        return rule["class"] if rule else None

    def test_seed_covers_live_mac_entries(self):
        sb = Sandbox(self)
        sb.populate("hermes", _fixture("hermes"), sockets={"gateway.sock"})
        sb.populate("claude", _fixture("claude"))
        sb.populate("smem", _fixture("smem"))
        code, out, err = sb.run("audit")
        self.assertEqual(code, 0, out + err)
        expect = {
            ("hermes", "state-staging"): "host-local",
            ("hermes", "state-restore-backups"): "host-local",
            ("smem", "sessions"): "host-local",
            ("hermes", "agent-hooks"): "repo-managed",
            ("smem", "spool"): "history",
            ("hermes", "backups"): "secret",
            ("hermes", ".curator_backups"): "secret",
            ("hermes", "state-snapshots"): "secret",
        }
        for (root, name), cls in expect.items():
            self.assertEqual(self._classify(sb, root, name), cls, (root, name))
        for name in (
            "gateway.sock",
            "config.yaml.orig-20260718T221805Z",
            ".provider_models_cache_usqtpr2j.tmp",
            "hermes.db",
            "kanban.db.init.lock",
            "state.db-wal",
            "tasks",
            "watcher-state",
            "secrets",
            "claude-opus55-cli",
        ):
            self.assertIn(name, _fixture("hermes"))
        self.assertIn("settings.json.bak-20260722_151032", _fixture("claude"))
        self.assertTrue({"smem.db", "smem.db-wal", "smem.db-shm", "sessions", "spool", "config.json", ".gitignore"} <= set(_fixture("smem")))

    def test_seed_secret_rules_precede_wider_rules(self):
        sb = Sandbox(self)
        for root, name in [
            ("hermes", "config.yaml.bak-x"),
            ("hermes", ".env.pre-migration-backup-x"),
            ("claude", "settings.json.bak"),
        ]:
            self.assertEqual(self._classify(sb, root, name), "secret", (root, name))


class AuditTest(unittest.TestCase):
    def test_unclassified_entry_exits_1_and_is_named(self):
        sb = Sandbox(self)
        sb.populate("hermes", _fixture("hermes"), sockets={"gateway.sock"})
        sb.populate("claude", _fixture("claude"))
        sb.populate("smem", _fixture("smem"))
        (sb.hermes / "newthing").mkdir()
        (sb.hermes / "zz.json").touch()
        (sb.smem / "newstore").mkdir()
        code, out, err = sb.run("audit")
        self.assertEqual(code, 1, out + err)
        for expected in ("hermes/newthing", "hermes/zz.json", "smem/newstore"):
            self.assertIn(expected, out)
        (sb.hermes / "newthing").rmdir()
        (sb.hermes / "zz.json").unlink()
        (sb.smem / "newstore").rmdir()
        self.assertEqual(sb.run("audit")[0], 0)

    def test_absent_smem_root_is_silent(self):
        sb = Sandbox(self)
        sb.populate("hermes", _fixture("hermes"), sockets={"gateway.sock"})
        sb.populate("claude", _fixture("claude"))
        self.assertFalse(sb.smem.exists())
        code, out, err = sb.run("audit")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(err, "")
        self.assertNotIn("smem", out)

    def test_first_match_wins_and_missing_manifest_exits_2(self):
        sb = Sandbox(self)
        sb.populate("hermes", ["foo.txt"])
        for first, second in (("secret", "personal-state"), ("personal-state", "secret")):
            path = _write(
                sb.home / f"{first}.yaml",
                f"""\
                version: 1
                rules:
                  - {{root: hermes, match: "foo.*", class: {first}}}
                  - {{root: hermes, match: "foo.*", class: {second}}}
                """,
            )
            self.assertEqual(sb.run("--manifest", str(path), "audit")[0], 0)
            manifest = sb.mod.load_manifest(path)
            self.assertEqual(sb.mod.classify(manifest, "hermes", "foo.txt")["class"], first)
        code, _out, err = sb.run("--manifest", str(sb.home / "absent.yaml"), "audit")
        self.assertEqual(code, 2)
        self.assertIn("manifest", err)

    def test_audit_without_yaml_exits_2(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shim = Path(tmp.name) / "shim"
        shim.mkdir()
        (shim / "sitecustomize.py").write_text(
            textwrap.dedent(
                """\
                import sys
                class _Block:
                    def find_spec(self, name, path=None, target=None):
                        if name == "yaml" or name.startswith("yaml."):
                            raise ImportError("blocked for test")
                        return None
                sys.meta_path.insert(0, _Block())
                """
            )
        )
        home = Path(tmp.name) / "home"
        (home / ".hermes").mkdir(parents=True)
        env = {**os.environ, "HOME": str(home), "HERMES_HOME": str(home / ".hermes"), "PYTHONPATH": str(shim)}
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "audit"],
            env=env,
            capture_output=True,
            text=True,
            check=False, timeout=60,
            cwd=tmp.name,
        )
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertIn("venv/bin/python", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_unexpected_exception_exits_2(self):
        sb = Sandbox(self)
        sb.populate("hermes", _fixture("hermes"), sockets={"gateway.sock"})
        sb.populate("claude", _fixture("claude"))
        with mock.patch.object(sb.mod, "build_fingerprint", side_effect=RuntimeError("boom")):
            code, out, err = sb.run("audit", "--json")
        self.assertEqual(code, 2)
        self.assertIn("hermes-state: internal error: RuntimeError", err)
        self.assertNotIn("{", out)
        self.assertNotIn("Traceback", err)


def _audit_json(sb, *extra):
    import json

    code, out, err = sb.run("audit", "--json", *extra)
    assert code in (0, 1), (code, err)
    return json.loads(out), out + err


class FingerprintTest(unittest.TestCase):
    def test_fingerprint_names_only_no_secret_values(self):
        sb = Sandbox(self)
        _write(
            sb.hermes / "config.yaml",
            """\
            mcp_servers:
              x:
                headers:
                  Authorization: SENTINEL-TOKEN
            """,
        )
        (sb.hermes / ".env").write_text("OTHER=SENTINEL-ENV\n")
        (sb.hermes / "claude-k3-config").mkdir()
        (sb.hermes / "claude-k3-config" / "settings.json").write_text('{"env": {"K": "SENTINEL-SET"}}')
        (sb.home / ".claude.json").write_text('{"mcpServers": {"y": {"env": {"K": "SENTINEL-CJ"}}}}')
        (sb.claude / "settings.json").write_text('{"env": {"K": "SENTINEL-SET"}}')
        fp, text = _audit_json(sb)
        self.assertEqual(fp["mcp_servers"], ["x"])
        self.assertEqual(fp["claude_mcp_servers"], ["y"])
        self.assertNotIn("SENTINEL-", text)
        _code, out, err = sb.run("audit")
        self.assertNotIn("SENTINEL-", out + err)

    def test_fingerprint_fields_from_fixtures(self):
        import json

        sb = Sandbox(self)
        skills = sb.hermes / "skills"
        for rel in ("cat/one", "two"):
            (skills / rel).mkdir(parents=True)
            (skills / rel / "SKILL.md").write_text("x")
        ext = sb.hermes / "ext" / "linked"
        ext.mkdir(parents=True)
        (ext / "SKILL.md").write_text("x")
        (skills / "linked").symlink_to("../ext/linked")
        (skills / "loop").symlink_to("..")
        plugins = sb.hermes / "plugins"
        (plugins / "a").mkdir(parents=True)
        (plugins / "a.bak-20261105").mkdir()
        (plugins / "b").symlink_to(sb.hermes / "ext")
        (plugins / "notes.txt").write_text("x")
        _write(
            sb.hermes / "config.yaml",
            """\
            plugins:
              enabled: [p1, platforms/telegram]
              disabled: [p2]
            mcp_servers: {s1: {}, s2: {}}
            model:
              aliases: {fast: {}, deep: {}}
            memory:
              provider: synapse-mem
            """,
        )
        (sb.hermes / "cron").mkdir()
        (sb.hermes / "cron" / "jobs.json").write_text(json.dumps({"jobs": [{"name": "j1"}, {"name": "j2"}]}))
        (sb.claude / "settings.json").write_text(json.dumps({"enabledPlugins": {"on@m": True, "off@m": False, "local@m": False}}))
        (sb.claude / "settings.local.json").write_text(json.dumps({"enabledPlugins": {"local@m": True}}))
        legacy_config = sb.hermes / "claude-seatbelt-config"
        legacy_config.mkdir()
        (legacy_config / "settings.json").write_text(json.dumps({"enabledPlugins": {"legacy@m": True}}))
        k3_config = sb.hermes / "claude-k3-config"
        k3_config.mkdir()
        (k3_config / "settings.json").write_text(json.dumps({"enabledPlugins": {"k3@m": True}}))
        sb.stub("hermes", "echo 'hermes 9.9.9'")
        fp, _ = _audit_json(sb)
        self.assertEqual(fp["skills"]["count"], 3)
        self.assertEqual(fp["skills"]["names"], ["cat/one", "linked", "two"])
        self.assertEqual(fp["hermes_plugins"]["installed"], ["a", "b"])
        self.assertEqual(fp["hermes_plugins"]["enabled"], ["p1", "platforms/telegram"])
        self.assertEqual(fp["hermes_plugins"]["disabled"], ["p2"])
        self.assertEqual(fp["mcp_servers"], ["s1", "s2"])
        self.assertEqual(fp["model_aliases"], ["deep", "fast"])
        self.assertEqual(fp["memory_provider"], "synapse-mem")
        self.assertEqual(fp["cron_jobs"], ["j1", "j2"])
        self.assertEqual(fp["claude_plugins"], ["local@m", "on@m"])
        self.assertEqual(fp["claude_plugins_legacy_config"], ["legacy@m"])
        self.assertEqual(fp["claude_plugins_k3_config"], ["k3@m"])
        self.assertEqual(fp["versions"]["hermes"], "hermes 9.9.9")
        self.assertIsNone(fp["versions"]["claude"])
        self.assertTrue(any("claude" in w for w in fp["warnings"]))

    def test_audit_text_prints_fingerprint_fields(self):
        sb = Sandbox(self)
        skill = sb.hermes / "skills" / "alpha"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("x")
        (sb.hermes / "plugins" / "inst-plugin").mkdir(parents=True)
        _write(
            sb.hermes / "config.yaml",
            """\
            plugins:
              enabled: [en-plugin]
              disabled: [dis-plugin]
            mcp_servers:
              mcp-one:
                headers: {Authorization: SENTINEL-TOKEN}
            model:
              aliases: {alias-one: {}}
            memory:
              provider: prov-one
            """,
        )
        (sb.hermes / "cron").mkdir()
        (sb.hermes / "cron" / "jobs.json").write_text('{"jobs": [{"name": "job-one"}]}')
        (sb.claude / "settings.json").write_text('{"enabledPlugins": {"cl-plugin@m": true}, "env": {"K": "SENTINEL-SET"}}')
        legacy_config = sb.hermes / "claude-seatbelt-config"
        legacy_config.mkdir()
        (legacy_config / "settings.json").write_text('{"enabledPlugins": {"legacy-plugin@m": true}}')
        k3_config = sb.hermes / "claude-k3-config"
        k3_config.mkdir()
        (k3_config / "settings.json").write_text('{"enabledPlugins": {"k3-plugin@m": true}}')
        (sb.home / ".claude.json").write_text('{"mcpServers": {"cj-one": {"env": {"K": "SENTINEL-CJ"}}}}')
        sb.stub("hermes", "echo 'hermes 9.9.9'")
        code, out, err = sb.run("audit")
        self.assertIn(code, (0, 1))
        for needle in (
            "alpha",
            "inst-plugin",
            "en-plugin",
            "dis-plugin",
            "mcp-one",
            "alias-one",
            "prov-one",
            "job-one",
            "cl-plugin@m",
            "legacy-plugin@m",
            "k3-plugin@m",
            "cj-one",
            "hermes 9.9.9",
            "mac",
        ):
            self.assertIn(needle, out)
        self.assertNotIn("SENTINEL-", out + err)

    def test_unreadable_source_gives_null_and_warning(self):
        sb = Sandbox(self)
        (sb.hermes / "config.yaml").write_text("a: [unclosed\n")
        fp, _ = _audit_json(sb)
        self.assertIsNone(fp["mcp_servers"])
        self.assertIsNone(fp["hermes_plugins"]["enabled"])
        self.assertTrue(any("config.yaml" in w for w in fp["warnings"]))

    def test_gateway_detection_mac_with_plist_not_telegram_host(self):
        token = "SENTINEL-TG-TOKEN"
        sb = Sandbox(self)
        plist = sb.home / "Library" / "LaunchAgents" / "ai.hermes.gateway.plist"
        plist.parent.mkdir(parents=True)
        plist.touch()
        fp, text = _audit_json(sb)
        self.assertEqual(fp["platforms"], ["mac"])

        unit = sb.home / ".config" / "systemd" / "user" / "hermes-gateway.service"
        unit.parent.mkdir(parents=True)
        unit.touch()
        (sb.hermes / ".env").write_text(f"TELEGRAM_BOT_TOKEN={token}\n")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            fp, text = _audit_json(sb)
        self.assertEqual(fp["platforms"], ["gateway", "linux", "wsl"])
        self.assertNotIn(token, text)

        (sb.hermes / ".env").unlink()
        _write(sb.hermes / "config.yaml", "platforms:\n  telegram:\n    enabled: true\n")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            fp, _ = _audit_json(sb)
        self.assertIn("gateway", fp["platforms"])

        unit.unlink()
        plist.unlink()
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            fp, _ = _audit_json(sb)
        self.assertEqual(fp["platforms"], ["linux", "wsl"])
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "sora"}):
            fp, _ = _audit_json(sb)
        self.assertEqual(fp["platforms"], ["gateway", "linux", "sora"])

    def test_env_parser_edge_cases(self):
        sb = Sandbox(self)
        key = "TELEGRAM_BOT_TOKEN"
        cases = [
            ("export TELEGRAM_BOT_TOKEN=x", True),
            ('TELEGRAM_BOT_TOKEN=""', False),
            ("TELEGRAM_BOT_TOKEN=''", False),
            ("TELEGRAM_BOT_TOKEN= # later", False),
            ("TELEGRAM_BOT_TOKEN=x # c", True),
            ("# TELEGRAM_BOT_TOKEN=x", None),
            ("  TELEGRAM_BOT_TOKEN=x", True),
            ('TELEGRAM_BOT_TOKEN="a#b"', True),
            ("TELEGRAM_BOT_TOKEN=x\nTELEGRAM_BOT_TOKEN=", False),
            ("1BAD=x", None),
        ]
        for text, expected in cases:
            parsed = sb.mod.parse_env(text)
            self.assertEqual(parsed.get(key), expected, text)
            if text.startswith("1BAD"):
                self.assertNotIn("1BAD", parsed)
        parsed = sb.mod.parse_env("K=SENTINEL-VALUE\n")
        self.assertEqual(parsed, {"K": True})


def _fp(**over):
    base = {
        "schema": 1,
        "host": "h",
        "home": "/home/x",
        "platforms": ["mac"],
        "unclassified": [],
        "warnings": [],
        "skills": {"count": 0, "names": []},
        "hermes_plugins": {"enabled": [], "disabled": [], "installed": []},
        "claude_plugins": [],
        "claude_plugins_legacy_config": [],
        "claude_plugins_k3_config": [],
        "claude_mcp_servers": [],
        "mcp_servers": [],
        "model_aliases": [],
        "cron_jobs": [],
        "memory_provider": "p",
        "versions": {"hermes": "1", "claude": "1"},
    }
    for key, value in over.items():
        if key in ("skills", "hermes_plugins"):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def _compare(self, a, b, manifest=None):
        import json

        pa, pb = self.sb.home / "a.json", self.sb.home / "b.json"
        pa.write_text(json.dumps(a))
        pb.write_text(json.dumps(b))
        head = ["--manifest", str(manifest)] if manifest else []
        return self.sb.run(*head, "compare", str(pa), str(pb))

    def _manifest(self, tags: str):
        return _write(
            self.sb.home / "m.yaml",
            "version: 1\nrules:\n  - {root: hermes, match: x, class: host-local}\nfingerprint_platform:\n" + tags,
        )

    def test_compare_lists_both_sides(self):
        a = _fp(skills={"names": ["a"], "count": 1})
        b = _fp(skills={"names": ["b"], "count": 1})
        code, out, err = self._compare(a, b)
        self.assertEqual(code, 1, err)
        self.assertIn("skills.names", out)
        self.assertRegex(out, r"only A:.*\ba\b")
        self.assertRegex(out, r"only B:.*\bb\b")
        self.assertEqual(self._compare(a, a)[0], 0)
        v = _fp(versions={"hermes": "2", "claude": "3"}, skills={"count": 9})
        code, out, _ = self._compare(_fp(), v)
        self.assertEqual(code, 0)
        self.assertIn("informational:", out)

    def test_compare_platforms_only_difference_exit_0(self):
        a = _fp(platforms=["gateway", "linux", "sora"], unclassified=[{"root": "hermes", "name": "new1"}])
        b = _fp(platforms=["gateway", "linux", "wsl"], unclassified=[{"root": "hermes", "name": "new2"}])
        code, out, _ = self._compare(a, b)
        self.assertEqual(code, 0)
        info = out[out.index("informational:") :]
        self.assertIn("platforms", info)
        self.assertIn("unclassified", info)
        self.assertIn("sora", info)
        self.assertIn("new1", info)

    def test_compare_platform_expected_not_a_difference(self):
        m = self._manifest("  cron_jobs:\n    telegram-digest: gateway\n    wsl-only: [mac, wsl]\n")
        gw = _fp(platforms=["gateway", "linux", "sora"], cron_jobs=["telegram-digest"])
        mac = _fp(platforms=["mac"])
        code, out, _ = self._compare(gw, mac, m)
        self.assertEqual(code, 0, out)
        self.assertIn("platform-expected:", out)
        self.assertIn("telegram-digest", out)
        gw2 = _fp(platforms=["gateway", "linux", "wsl"])
        self.assertEqual(self._compare(gw, gw2, m)[0], 1)
        wsl = _fp(platforms=["linux", "wsl"], cron_jobs=["wsl-only"])
        sora = _fp(platforms=["gateway", "linux", "sora"])
        self.assertEqual(self._compare(wsl, sora, m)[0], 0)
        wsl2 = _fp(platforms=["linux", "wsl"])
        code, out, _ = self._compare(wsl, wsl2, m)
        self.assertEqual(code, 1)
        self.assertIn("wsl-only", out)

    def test_compare_sora_vs_wsl_gateway_profile_jobs(self):
        seed = _MANIFEST
        jobs = ["sora-host-liveness", "sora-aws-keep-hot", "ti-hiring-afk-supervisor", "hermes-hygiene"]
        a = _fp(platforms=["gateway", "linux", "sora"], cron_jobs=sorted(jobs))
        b = _fp(platforms=["gateway", "linux", "wsl"], cron_jobs=["hermes-hygiene"])
        self.assertEqual(self._compare(a, b, seed)[0], 0)
        b2 = _fp(platforms=["gateway", "linux", "wsl"], cron_jobs=[])
        code, out, _ = self._compare(a, b2, seed)
        self.assertEqual(code, 1)
        self.assertIn("hermes-hygiene", out.split("platform-expected:")[0])
        mac = _fp(platforms=["mac"], hermes_plugins={"disabled": ["claude-code-identity", "platforms/telegram"]})
        sora = _fp(platforms=["gateway", "linux", "sora"], hermes_plugins={"enabled": ["platforms/telegram"]})
        code, out, _ = self._compare(mac, sora, seed)
        self.assertEqual(code, 1)
        diff, _, expected = out.partition("platform-expected:")
        self.assertIn("claude-code-identity", diff)
        self.assertNotIn("platforms/telegram", diff)
        self.assertEqual(expected.count("platforms/telegram"), 2)

    def test_compare_reads_legacy_isolated_plugin_field(self):
        old = _fp()
        del old["claude_plugins_legacy_config"]
        old["claude_plugins_seatbelt"] = ["legacy@m"]
        self.assertEqual(self._compare(old, _fp(claude_plugins_legacy_config=["legacy@m"]))[0], 0)
        code, out, _ = self._compare(old, _fp(claude_plugins_legacy_config=["new@m"]))
        self.assertEqual(code, 1)
        self.assertIn("claude_plugins_legacy_config", out)
        self.assertIn("legacy@m", out)
        self.assertIn("new@m", out)

    def test_compare_null_set_is_unknown_and_bad_input_exits_2(self):
        code, out, _ = self._compare(_fp(mcp_servers=None), _fp(mcp_servers=["a"]))
        self.assertEqual(code, 0)
        self.assertIn("unknown", out)
        code, out, _ = self._compare(_fp(memory_provider="x"), _fp(memory_provider="y"))
        self.assertEqual(code, 1)
        self.assertIn("memory_provider", out)
        bad = self.sb.home / "bad.json"
        bad.write_text("{not json")
        good = self.sb.home / "good.json"
        good.write_text('{"schema": 1}')
        for args in ((bad, good), (good, self.sb.home / "missing.json")):
            code, out, err = self.sb.run("compare", str(args[0]), str(args[1]))
            self.assertEqual(code, 2)
            self.assertNotIn("Traceback", err)
        wrong = self.sb.home / "wrong.json"
        wrong.write_text('{"schema": 1, "mcp_servers": "a"}')
        self.assertEqual(self.sb.run("compare", str(wrong), str(good))[0], 2)


def _read_bundle(path):
    """Ordered (name, bytes) members of a captured tar stream."""
    members = []
    with tarfile.open(path, mode="r|") as tar:
        for info in tar:
            f = tar.extractfile(info)
            members.append((info.name, f.read() if f else b""))
    return members


def _bundle_json(members):
    assert members[0][0] == "bundle.json", members[0][0]
    return json.loads(members[0][1])


def _wal_db(path, value="walrow"):
    conn = sqlite3.connect(path)
    conn.execute("pragma journal_mode=wal")
    conn.execute("create table t(v)")
    conn.commit()
    conn.execute("insert into t values (?)", (value,))
    conn.commit()
    return conn


def _db_values(data: bytes, tmpdir: Path):
    path = tmpdir / "extracted.db"
    path.write_bytes(data)
    conn = sqlite3.connect(path)
    try:
        return [r[0] for r in conn.execute("select v from t")]
    finally:
        conn.close()


class ExportTestBase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)
        self.sb.gpg_stub()
        self.out_dir = self.sb.home / "out"
        self.out_dir.mkdir()
        self.out = self.out_dir / "b.gpg"
        tmpd = self.sb.home / "tmpd"
        tmpd.mkdir()
        patch = mock.patch.dict(os.environ, {"TMPDIR": str(tmpd)})
        patch.start()
        self.addCleanup(patch.stop)
        tp = mock.patch.object(tempfile, "tempdir", str(tmpd))
        tp.start()
        self.addCleanup(tp.stop)
        self.tmpd = tmpd

    def export(self, *extra, out=None):
        return self.sb.run("export", "--out", str(out or self.out), *extra)

    def captured(self):
        return _read_bundle(self.sb.home / "gpg.stdin")

    def base_tree(self):
        sb = self.sb
        for rel, text in {
            "memories/m.md": "mem",
            "skills/foo/SKILL.md": "skill",
        }.items():
            path = sb.hermes / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


class ExportContentTest(ExportTestBase):
    def test_export_excludes_nested_settings_env_and_backups(self):
        sb = self.sb
        files = {
            sb.hermes / ".env": "K=SENTINEL-ENV",
            sb.hermes / "auth.json": "SENTINEL-AUTH",
            sb.hermes / "mcp-tokens" / "t.json": "SENTINEL-MCP",
            sb.hermes / "config.yaml": "k: SENTINEL-CFG",
            sb.hermes / "config.yaml.bak-x": "k: SENTINEL-BAK",
            sb.hermes / "claude-k3-config" / "settings.json": '{"env": {"K": "SENTINEL-SET"}}',
            sb.hermes / "claude-k3-config" / "backups" / ".claude.json.backup.1": "SENTINEL-CJB",
            sb.hermes / "claude-k3-config" / ".credentials.json": "SENTINEL-CRED",
            sb.hermes / ".curator_backups" / "blobs" / ("a1" * 32): "API_KEY=SENTINEL-BLOB",
            sb.hermes / "state-snapshots" / "s" / "config.yaml": "k: SENTINEL-SNAP",
            sb.hermes / "skills" / "foo" / "data.tar.gz": "SENTINEL-TARGZ",
            sb.hermes / "skills" / "foo" / "SKILL.md": "skill",
            sb.claude / "settings.json.bak": "SENTINEL-CLBAK",
        }
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        zpath = sb.hermes / "backups" / "x.zip"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
            z.writestr(".env", "SENTINEL-ZIP")
        secret_rel = [
            "hermes/.env",
            "hermes/auth.json",
            "hermes/mcp-tokens/t.json",
            "hermes/config.yaml",
            "hermes/config.yaml.bak-x",
            "hermes/claude-k3-config/settings.json",
            "hermes/claude-k3-config/backups/.claude.json.backup.1",
            "hermes/claude-k3-config/.credentials.json",
            "hermes/backups/x.zip",
            "hermes/.curator_backups/blobs/" + "a1" * 32,
            "hermes/state-snapshots/s/config.yaml",
            "hermes/skills/foo/data.tar.gz",
            "claude/settings.json.bak",
        ]
        code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        raw = (sb.home / "gpg.stdin").read_bytes()
        self.assertNotIn(b"SENTINEL", raw)
        paths = {e["path"] for e in _bundle_json(self.captured())["entries"]}
        self.assertIn("hermes/skills/foo/SKILL.md", paths)
        for rel in secret_rel:
            self.assertNotIn(rel, paths, rel)
        self.out.unlink()
        (self.out_dir / "b.gpg.sha256").unlink()
        code, _out, err = self.export("--include-secrets")
        self.assertEqual(code, 0, err)
        paths = {e["path"] for e in _bundle_json(self.captured())["entries"]}
        for rel in secret_rel:
            self.assertIn(rel, paths, rel)
        self.assertIn(b"SENTINEL-ZIP", (sb.home / "gpg.stdin").read_bytes())

    def test_export_nested_and_empty_sqlite(self):
        sb = self.sb
        (sb.hermes / "cron").mkdir()
        (sb.hermes / "synapse").mkdir()
        conns = [
            _wal_db(sb.hermes / "state.db", "r-state"),
            _wal_db(sb.hermes / "cron" / "executions.db", "r-cron"),
            _wal_db(sb.hermes / "synapse" / "store", "r-store"),
        ]
        for c in conns:
            self.addCleanup(c.close)
        (sb.hermes / "hermes.db").touch()
        code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        members = self.captured()
        entries = {e["path"]: e for e in _bundle_json(members)["entries"]}
        data = dict(members)
        for rel, value in (
            ("hermes/state.db", "r-state"),
            ("hermes/cron/executions.db", "r-cron"),
            ("hermes/synapse/store", "r-store"),
        ):
            self.assertEqual(entries[rel]["type"], "sqlite", rel)
            self.assertEqual(_db_values(data[rel], self.tmpd), [value])
        self.assertEqual(entries["hermes/hermes.db"]["type"], "file")
        for name in data:
            self.assertFalse(name.endswith(("-wal", "-shm", "-journal")), name)
        for rel in entries:
            self.assertFalse(rel.endswith(("-wal", "-shm", "-journal")), rel)

    def test_export_smem_store(self):
        sb = self.sb
        sb.smem.mkdir()
        conn = _wal_db(sb.smem / "smem.db")
        self.addCleanup(conn.close)
        (sb.smem / "sessions").mkdir()
        (sb.smem / "sessions" / "123").write_text("x" * 37)
        (sb.smem / "spool").mkdir()
        (sb.smem / "spool" / "1.json").write_text("{}")
        (sb.smem / "config.json").write_text(json.dumps({"home": str(sb.home)}))
        code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        members = self.captured()
        entries = {e["path"]: e for e in _bundle_json(members)["entries"]}
        self.assertEqual(entries["smem/smem.db"]["type"], "sqlite")
        self.assertEqual(entries["smem/spool/1.json"]["class"], "history")
        self.assertIn("smem/config.json", entries)
        self.assertEqual(_db_values(dict(members)["smem/smem.db"], self.tmpd), ["walrow"])
        for path in entries:
            self.assertFalse(path.startswith("smem/sessions"), path)
            self.assertFalse(path.endswith(("smem.db-wal", "smem.db-shm")), path)
        self.assertEqual(_bundle_json(members)["roots_present"], ["hermes", "claude", "smem"])

    def test_export_links_sockets_locks(self):
        sb = self.sb
        self.base_tree()
        (sb.hermes / "skills" / "link").symlink_to(_ROOT / "scripts")
        (sb.hermes / "skills" / "foo" / "n.lock").touch()
        (sb.hermes / "skills" / "foo" / "p.pid").touch()
        prev = os.getcwd()
        os.chdir(sb.hermes / "skills" / "foo")
        try:
            s = socket.socket(socket.AF_UNIX)
            s.bind("s.sock")
            s.close()
        finally:
            os.chdir(prev)
        sb.populate("hermes", ["gateway.pid", "x.lock"])
        code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        members = self.captured()
        entries = {e["path"]: e for e in _bundle_json(members)["entries"]}
        link = entries["hermes/skills/link"]
        self.assertEqual(link["type"], "link")
        self.assertEqual(link["link_target"], str(_ROOT / "scripts"))
        names = {n for n, _ in members}
        self.assertFalse([n for n in names if n.startswith("hermes/skills/link")])
        for gone in ("n.lock", "p.pid", "s.sock", "gateway.pid", "x.lock"):
            self.assertFalse([p for p in entries if p.endswith(gone)], gone)
        self.assertTrue(all(isinstance(e["mode"], int) for e in entries.values()))

    def test_export_gpg_invocation_and_sha(self):
        self.base_tree()
        code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        (log,) = self.sb.gpg_log()
        argv = log["argv"]
        self.assertIn("--symmetric", argv)
        self.assertEqual(argv[argv.index("--cipher-algo") + 1], "AES256")
        self.assertFalse([a for a in argv if a.startswith("--passphrase")])
        self.assertNotIn("--batch", argv)
        members = self.captured()
        self.assertEqual(members[0][0], "bundle.json")
        self.assertNotIn("sha256", members[0][1].decode())
        names = [n for n, _ in members]
        entries = _bundle_json(members)["entries"]
        for e in entries:
            if e["type"] in ("file", "sqlite"):
                i = names.index(e["path"])
                self.assertEqual(names[i + 1], f"digests/{e['seq']}.json")
                digest = json.loads(members[i + 1][1])
                self.assertEqual(digest["sha256"], hashlib.sha256(members[i][1]).hexdigest())
        sha = (self.out_dir / "b.gpg.sha256").read_text()
        self.assertEqual(sha, f"{hashlib.sha256(self.out.read_bytes()).hexdigest()}  b.gpg\n")
        rc, help_out, _ = self.sb.run_sub("export", "--help")
        self.assertEqual(rc, 0)
        self.assertNotIn("passphrase", help_out.lower())


class ExportStreamTest(ExportTestBase):
    def _entry_digest(self, members, path):
        names = [n for n, _ in members]
        entries = {e["path"]: e for e in _bundle_json(members)["entries"]}
        seq = entries[path]["seq"]
        return json.loads(dict(members)[f"digests/{seq}.json"]), names

    def test_export_live_file_appended_during_stream(self):
        sb = self.sb
        target = sb.claude / "projects" / "p" / "s.jsonl"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"line1\nline2\n")

        def hook(path):
            if str(path).endswith("s.jsonl"):
                with open(path, "ab") as f:
                    f.write(b"appended\n")

        with mock.patch.object(sb.mod, "_after_fstat", hook):
            code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        members = self.captured()
        data = dict(members)["claude/projects/p/s.jsonl"]
        self.assertEqual(data, b"line1\nline2\n")
        digest, _ = self._entry_digest(members, "claude/projects/p/s.jsonl")
        self.assertEqual((digest["size"], digest["valid"]), (12, 12))
        self.assertEqual(digest["sha256"], hashlib.sha256(b"line1\nline2\n").hexdigest())

    def test_export_file_truncated_during_stream(self):
        sb = self.sb
        hist = sb.claude / "history.jsonl"
        hist.write_bytes(b"0123456789")
        (sb.hermes / "sessions").mkdir()
        (sb.hermes / "sessions" / "x.json").write_text("{}")
        (sb.hermes / "sessions" / "keep.json").write_text("{}")

        def after_fstat(path):
            if str(path).endswith("history.jsonl"):
                os.truncate(path, 5)

        def before_open(path):
            if str(path).endswith("sessions/x.json"):
                os.unlink(path)

        with mock.patch.object(sb.mod, "_after_fstat", after_fstat), mock.patch.object(sb.mod, "_before_open", before_open):
            code, _out, err = self.export()
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        members = self.captured()
        digest, _ = self._entry_digest(members, "claude/history.jsonl")
        self.assertEqual((digest["size"], digest["valid"]), (10, 5))
        self.assertEqual(digest["sha256"], hashlib.sha256(b"01234").hexdigest())
        self.assertEqual(dict(members)["claude/history.jsonl"], b"01234" + b"\0" * 5)
        vanished, names = self._entry_digest(members, "hermes/sessions/x.json")
        self.assertTrue(vanished.get("missing"))
        self.assertNotIn("hermes/sessions/x.json", names)
        self.assertIn("hermes/sessions/keep.json", names)


class ExportRefusalTest(ExportTestBase):
    def _assert_no_outputs(self):
        for suffix in ("", ".partial", ".sha256"):
            self.assertFalse(os.path.lexists(f"{self.out}{suffix}"), suffix)

    def _assert_no_final(self):
        self.assertFalse(self.out.exists())
        self.assertFalse(os.path.lexists(f"{self.out}.sha256"))

    def test_export_refusals_and_staging_sweep(self):
        sb = self.sb
        self.base_tree()
        (sb.hermes / "newthing").mkdir()
        code, out, err = self.export()
        self.assertEqual(code, 1)
        self.assertIn("hermes/newthing", out + err)
        self.assertEqual(sb.gpg_log(), [])
        (sb.hermes / "newthing").rmdir()
        with mock.patch.dict(os.environ, {"GPG_STUB_EXIT": "1"}):
            code, out, err = self.export()
        self.assertEqual(code, 2)
        self._assert_no_outputs()
        staging = sb.hermes / "state-staging"
        self.assertEqual(os.listdir(staging) if staging.exists() else [], [])
        self.out.write_text("existing")
        code, out, err = self.export()
        self.assertEqual(code, 1)
        self.assertEqual(self.out.read_text(), "existing")
        self.assertFalse(os.path.lexists(f"{self.out}.partial"))
        self.assertFalse(os.path.lexists(f"{self.out}.sha256"))
        self.out.unlink()
        staging.mkdir(exist_ok=True)
        old, recent = staging / "old", staging / "recent"
        old.mkdir()
        recent.mkdir()
        for path, age in ((old, 2 * 86400), (recent, 3600)):
            t = time.time() - age
            os.utime(path, (t, t))
        code, out, err = self.export()
        self.assertEqual(code, 0, err)
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertEqual(sorted(os.listdir(staging)), ["recent"])
        self.assertEqual(os.listdir(self.tmpd), [])

    def test_export_refuses_out_under_a_root(self):
        sb = self.sb
        self.base_tree()
        sb.smem.mkdir()
        (sb.smem / "config.json").write_text("{}")
        (sb.claude / "downloads").mkdir()
        link = sb.home / "link"
        link.symlink_to(sb.smem)
        for out in (sb.hermes / "b.gpg", sb.claude / "downloads" / "b.gpg", link / "b.gpg"):
            code, _so, err = self.export(out=out)
            self.assertEqual(code, 1, (out, err))
            self.assertEqual(sb.gpg_log(), [])
        for root in (sb.hermes, sb.claude, sb.smem):
            self.assertEqual(list(root.rglob("b.gpg*")), [])
        code, _so, err = self.export(out=self.out)
        self.assertEqual(code, 0, err)

    def test_export_removes_stale_partial_on_retry(self):
        sb = self.sb
        self.base_tree()
        partial = Path(f"{self.out}.partial")
        partial.write_bytes(b"junk")
        code, out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 0, err)
        self.assertIn(f"note: removed stale {self.out}.partial", out)
        (log,) = sb.gpg_log()
        self.assertFalse(log["out_exists"])
        self.assertEqual(self.captured()[0][0], "bundle.json")
        sha = (self.out_dir / "b.gpg.sha256").read_text()
        self.assertIn(hashlib.sha256(self.out.read_bytes()).hexdigest(), sha)
        self.out.unlink()
        (self.out_dir / "b.gpg.sha256").unlink()
        victim = sb.home / "victim"
        victim.write_bytes(b"known bytes")
        partial.symlink_to(victim)
        code, out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 0, err)
        self.assertIn("note: removed stale", out)
        self.assertEqual(victim.read_bytes(), b"known bytes")
        self.assertEqual(len(sb.gpg_log()), 2)
        self.assertFalse(sb.gpg_log()[1]["out_exists"])

    def test_export_concurrent_same_out_refused(self):
        sb = self.sb
        self.base_tree()
        lock = Path(f"{self.out}.lock")
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT, 0o600)
        held = [fd]
        self.addCleanup(lambda: [os.close(f) for f in held])
        fcntl.flock(fd, fcntl.LOCK_EX)
        partial = Path(f"{self.out}.partial")
        partial.write_bytes(b"live partial")
        os.utime(partial, (1_000_000, 1_000_000))
        code, out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 1, err)
        self.assertIn(f"export to {self.out} already running", err)
        self.assertEqual(sb.gpg_log(), [])
        self.assertEqual(partial.read_bytes(), b"live partial")
        self.assertEqual(int(partial.stat().st_mtime), 1_000_000)
        self._assert_no_final()
        os.close(fd)
        held.clear()
        code, out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 0, err)
        self.assertIn("note: removed stale", out)

    def test_export_lock_link_dir_and_unsupported(self):
        sb = self.sb
        self.base_tree()
        lock = Path(f"{self.out}.lock")
        victim = sb.home / "victim"
        victim.write_bytes(b"known")
        lock.symlink_to(victim)
        code, _out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 1, err)
        self.assertIn("refusing link at", err)
        self.assertEqual(victim.read_bytes(), b"known")
        self.assertEqual(sb.gpg_log(), [])
        lock.unlink()
        lock.mkdir()
        partial = Path(f"{self.out}.partial")
        partial.write_bytes(b"keep")
        os.utime(partial, (1_000_000, 1_000_000))
        code, _out, err = sb.run_sub("export", "--out", str(self.out))
        self.assertEqual(code, 1, err)
        self.assertIn(f"cannot lock {self.out}.lock (EISDIR); choose an --out on a local filesystem", err)
        self.assertEqual(sb.gpg_log(), [])
        self.assertEqual((partial.read_bytes(), int(partial.stat().st_mtime)), (b"keep", 1_000_000))
        self._assert_no_final()
        lock.rmdir()
        with mock.patch.object(sb.mod.fcntl, "flock", side_effect=OSError(errno.ENOTSUP, "patched")):
            code, _out, e = self.export()
        self.assertEqual(code, 1)
        self.assertIn(f"cannot lock {self.out}.lock ({errno.errorcode[errno.ENOTSUP]}); choose an --out on a local filesystem", e)
        self.assertEqual(sb.gpg_log(), [])
        self.assertEqual(partial.read_bytes(), b"keep")
        self._assert_no_final()

    def test_export_lock_parent_missing(self):
        sb = self.sb
        self.base_tree()
        before = sorted(os.listdir(sb.home))
        missing = sb.home / "missing"
        code, _out, err = sb.run_sub("export", "--out", str(missing / "b.gpg"))
        self.assertEqual(code, 1, err)
        self.assertIn(f"--out parent does not exist: {missing}", err)
        self.assertNotIn("choose an --out on a local filesystem", err)
        self.assertEqual(sb.gpg_log(), [])
        self.assertFalse(missing.exists())
        self.assertEqual(sorted(os.listdir(sb.home)), before)

    def test_missing_gpg_message(self):
        self.base_tree()
        (self.sb.bin / "gpg").unlink()
        code, _out, err = self.export()
        self.assertEqual(code, 2)
        self.assertIn("sudo apt-get install gnupg", err)
        self.assertNotIn("Traceback", err)


_MISSING = object()


class Bundle:
    """Builds a bundle tar the way export lays it out, with knobs for tampering."""

    def __init__(self, source_home="/Users/olduser", platforms=("mac",), schema=1):
        self.source_home = source_home
        self.platforms = list(platforms)
        self.schema = schema
        self.entries = []
        self.data = {}
        self.tamper = set()
        self.vanish = set()
        self.shrunk = {}
        self.extra_members = []
        self.entry_overrides = None

    def _add(self, path, type, data=b"", cls="personal-state", mode=0o644, platform=None, target=None):
        seq = len(self.entries)
        entry = {"seq": seq, "root": path.split("/")[0], "path": path, "class": cls, "type": type, "mode": mode}
        if platform:
            entry["platform"] = platform
        if target is not None:
            entry["link_target"] = target
        self.entries.append(entry)
        self.data[seq] = data
        return self

    def dir(self, path, mode=0o755, **kw):
        return self._add(path, "dir", mode=mode, **kw)

    def file(self, path, data, mode=0o644, **kw):
        return self._add(path, "file", data if isinstance(data, bytes) else data.encode(), mode=mode, **kw)

    def sqlite(self, path, data, mode=0o644, **kw):
        return self._add(path, "sqlite", data, mode=mode, **kw)

    def link(self, path, target, **kw):
        return self._add(path, "link", mode=0o777, target=target, **kw)

    def seq(self, path):
        return next(e["seq"] for e in self.entries if e["path"] == path)

    def write(self, out: Path, bad_sha=False, write_sha=True, gz=False):
        meta = {
            "schema": self.schema,
            "created": "2026-01-01T00:00:00+00:00",
            "source_home": self.source_home,
            "source_platforms": self.platforms,
            "include_secrets": True,
            "roots_present": ["hermes", "claude", "smem"],
            "source_fingerprint": {},
            "entries": self.entries,
        }
        if self.schema is _MISSING:
            del meta["schema"]
        with tarfile.open(out, "w:gz" if gz else "w") as tar:
            _tar_bytes(tar, "bundle.json", json.dumps(meta).encode())
            for e in self.entries:
                if e["type"] not in ("file", "sqlite"):
                    continue
                data = self.data[e["seq"]]
                valid = self.shrunk.get(e["seq"], len(data))
                digest = {"seq": e["seq"], "path": e["path"], "size": len(data), "valid": valid,
                          "sha256": hashlib.sha256(data[:valid]).hexdigest()}
                if e["seq"] in self.vanish:
                    digest.update(size=0, valid=0, sha256=None, missing=True)
                else:
                    _tar_bytes(tar, e["path"], data)
                    if e["seq"] in self.tamper:
                        digest["sha256"] = "0" * 64
                _tar_bytes(tar, f"digests/{e['seq']}.json", json.dumps(digest).encode())
            for name, data in self.extra_members:
                _tar_bytes(tar, name, data)
        if write_sha:
            digest = hashlib.sha256(out.read_bytes()).hexdigest()
            Path(f"{out}.sha256").write_text(f"{'1' * 64 if bad_sha else digest}  {out.name}\n")
        return out


def _tar_bytes(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _db_bytes(tmpdir: Path, *values):
    path = tmpdir / f"mk{len(os.listdir(tmpdir))}.db"
    conn = sqlite3.connect(path)
    conn.execute("create table t(v)")
    conn.executemany("insert into t values (?)", [(v,) for v in values])
    conn.commit()
    conn.close()
    return path.read_bytes()


def _listing(sb, extra=()):
    """type, mtime, content hash and link target for everything under HOME except the sandbox's own files."""
    skip = {"bin", "bundles", "gpg.log", "gpg.stdin", ".gnupg", "tmpd"}
    out = {}
    bases = [sb.home, *extra]
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            if base == sb.home and dirpath == str(sb.home):
                dirnames[:] = [d for d in dirnames if d not in skip]
                filenames = [f for f in filenames if f not in skip]
            for name in dirnames + filenames:
                path = os.path.join(dirpath, name)
                st = os.lstat(path)
                if stat_islnk(st):
                    out[path] = ("link", os.readlink(path))
                elif os.path.isdir(path):
                    out[path] = ("dir", st.st_mtime_ns, st.st_mode)
                elif os.path.isfile(path):
                    out[path] = ("file", st.st_mtime_ns, hashlib.sha256(Path(path).read_bytes()).hexdigest())
                else:
                    out[path] = ("special", st.st_ino)
    return out


def stat_islnk(st):
    import stat as _stat

    return _stat.S_ISLNK(st.st_mode)


class RestoreBase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)
        self.sb.gpg_stub()
        (self.sb.home / "bundles").mkdir()
        self.F = self.sb.home / "bundles" / "b.gpg"
        self.outside = self.sb.home.parent / f"{self.sb.home.name}-outside"
        self.outside.mkdir()
        self.addCleanup(shutil.rmtree, self.outside, True)

    def make_tmp(self):
        d = self.sb.home / "mk"
        d.mkdir(exist_ok=True)
        return d

    def restore(self, *extra, sub=False):
        run = self.sb.run_sub if sub else self.sb.run
        return run("restore", "--from", str(self.F), *extra)

    def put(self, root, rel, data="x", mode=None):
        path = self.sb.root(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        if mode is not None:
            os.chmod(path, mode)
        return path

    def backups(self):
        base = self.sb.hermes / "state-restore-backups"
        return sorted(os.listdir(base)) if base.exists() else []

    def backup_path(self, rel, root="hermes"):
        (ts,) = self.backups()[-1:]
        return self.sb.hermes / "state-restore-backups" / ts / root / rel

    def run_thread(self, *argv):
        result = {}

        def target():
            result["r"] = self.sb.run(*argv)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(30)
        if t.is_alive():
            self.fail("restore blocked")
        return result["r"]

    def bind_socket(self, directory: Path, name: str):
        prev = os.getcwd()
        os.chdir(directory)
        try:
            s = socket.socket(socket.AF_UNIX)
            s.bind(name)
            s.close()
        finally:
            os.chdir(prev)


class RewriteUnitTest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)

    def rw(self, text):
        return self.sb.mod.rewrite_home(text, "/Users/olduser", "/home/new")

    def test_rewrite_boundaries(self):
        for src, want in [
            ("PATH=/Users/olduser/bin:/Users/olduser/.local/bin", "PATH=/home/new/bin:/home/new/.local/bin"),
            ("cd /Users/olduser", "cd /home/new"),
            ("cd /Users/olduser\n", "cd /home/new\n"),
            ("(/Users/olduser)", "(/home/new)"),
            ('"/Users/olduser"', '"/home/new"'),
            ("/Users/olduserx", "/Users/olduserx"),
            ("/mnt/c/Users/olduser/x", "/mnt/c/Users/olduser/x"),
            ("/Users/olduser.bak", "/Users/olduser.bak"),
        ]:
            self.assertEqual(self.rw(src), want, src)

    def test_rewrite_file_url_boundary(self):
        for src, want in [
            ("file:///Users/olduser/x", "file:///home/new/x"),
            ("FILE:///Users/olduser", "FILE:///home/new"),
            ("//Users/olduser/x", "//Users/olduser/x"),
            ("file:///Users/olduserx", "file:///Users/olduserx"),
            ("http://h/Users/olduser", "http://h/Users/olduser"),
        ]:
            self.assertEqual(self.rw(src), want, src)

    def test_restore_skip_segment_matcher(self):
        m = self.sb.mod.match_segments
        for rule, path, want in [
            ("agent-hooks/**", "agent-hooks", True),
            ("agent-hooks/**", "agent-hooks/red-gate.py", True),
            ("agent-hooks/**", "agent-hooks/a/b", True),
            ("agent-hooks/**", "agent-hooksx", False),
            ("agent-hooks/**", "agent-hooks.bak/x", False),
            ("skills/devops/aws-devfactory-operations/**", "skills/devops/aws-devfactory-operations", True),
            ("scripts/*", "scripts/a.py", True),
            ("scripts/*", "scripts/a/b", False),
            ("scripts/*", "scripts", False),
            ("plugins/claude-orchestrate", "plugins/claude-orchestrate", True),
            ("plugins/claude-orchestrate", "plugins/claude-orchestrate/x", False),
        ]:
            self.assertEqual(m(rule, path), want, (rule, path))

    def test_restore_skip_parses_all_setup_cp_lines(self):
        sb = self.sb
        text = (_ROOT / "devbox" / "setup-hermes.sh").read_text()
        block = re.search(r"COMMON_SCRIPTS=\(\n(.*?)\n\)", text, re.DOTALL).group(1).split()
        collected = set()
        for m in re.finditer(r'cp (?:-R )?"\$REPO_DIR/([^"]+)" "\$HERMES_HOME/([^"]+)"', text):
            src, dst = m.groups()
            if src.startswith("config/") and src.endswith(".template"):
                continue
            if dst == "scripts/$f":
                collected.update(f"scripts/{n}" for n in block)
            else:
                collected.add(dst)
        for host_script in (_ROOT / "hosts").glob("*/scripts/*"):
            collected.add(f"scripts/{host_script.name}")
        for need in (
            "scripts/aws-keep-hot.sh",
            "scripts/aws-creds-refresh-linux.sh",
            "scripts/aws-keep-hot-linux.sh",
            "scripts/hermes-hygiene.py",
            "agent-hooks/red-gate.py",
            "skills/devops/aws-devfactory-operations",
        ):
            self.assertIn(need, collected)
        self.assertFalse([p for p in collected if "$" in p])
        self.assertNotIn("config.yaml", collected)
        self.assertNotIn(".env", collected)
        manifest = sb.mod.load_manifest(_MANIFEST)
        for path in sorted(collected):
            self.assertIsNotNone(sb.mod.find_restore_skip(manifest, "hermes", path), path)
        self.assertIsNone(sb.mod.find_restore_skip(manifest, "hermes", "config.yaml"))
        self.assertIsNone(sb.mod.find_restore_skip(manifest, "hermes", ".env"))
        planted = {"root": "hermes", "match": "config.yaml"}
        manifest = {**manifest, "restore_skip": [*manifest["restore_skip"], planted]}
        self.assertEqual(sb.mod.find_restore_skip(manifest, "hermes", "config.yaml"), planted)
        self.assertEqual(sb.mod.classify(sb.mod.load_manifest(_MANIFEST), "hermes", "agent-hooks")["class"], "repo-managed")

    def test_restore_skip_covers_isolated_config_symlinks(self):
        manifest = self.sb.mod.load_manifest(_MANIFEST)
        for base in ("claude-seatbelt-config", "claude-k3-config"):
            for path in ("skills", "skills/nested", "plugins", "plugins/nested", "CLAUDE.md"):
                with self.subTest(path=f"{base}/{path}"):
                    self.assertIsNotNone(self.sb.mod.find_restore_skip(manifest, "hermes", f"{base}/{path}"))

    def test_restore_skip_covers_every_repo_script(self):
        sb = self.sb
        manifest = sb.mod.load_manifest(_MANIFEST)
        listed = subprocess.run(
            [shutil.which("git", path=sb.orig_path), "-C", str(_ROOT), "ls-files", "scripts"], capture_output=True, text=True, check=True
        ).stdout.split()
        self.assertTrue(listed)
        for rel in listed:
            self.assertIsNotNone(sb.mod.find_restore_skip(manifest, "hermes", f"scripts/{Path(rel).name}"), rel)


class RestoreScriptsTest(RestoreBase):
    def test_restore_skip_covers_repo_script_in_restore(self):
        sb = self.sb
        self.put("hermes", "scripts/orphan-reaper.py", "dest-version")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/scripts").file("hermes/scripts/orphan-reaper.py", "bundle-version")
        b.file("hermes/scripts/mine.sh", "echo mine")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / "scripts/orphan-reaper.py").read_text(), "dest-version")
        self.assertRegex(out, r"skipped \(host-profile managed\).*orphan-reaper\.py")
        self.assertEqual((sb.hermes / "scripts/mine.sh").read_text(), "echo mine")

    def test_restore_preserves_real_k3_files_and_skips_only_managed_links(self):
        sb = self.sb
        rel = "claude-k3-config/plugins/installed_plugins.json"
        self.put("hermes", rel, "seeded")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/claude-k3-config").dir("hermes/claude-k3-config/plugins").file(f"hermes/{rel}", "bundle")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / rel).read_text(), "bundle")
        self.assertEqual(self.backup_path(rel).read_text(), "seeded")

    def test_restore_skips_k3_files_below_a_managed_link(self):
        sb = self.sb
        shared = sb.claude / "plugins"
        shared.mkdir(parents=True)
        (shared / "installed_plugins.json").write_text("shared")
        (sb.hermes / "claude-k3-config").mkdir()
        (sb.hermes / "claude-k3-config" / "plugins").symlink_to(shared, target_is_directory=True)
        rel = "claude-k3-config/plugins/installed_plugins.json"
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/claude-k3-config").dir("hermes/claude-k3-config/plugins").file(f"hermes/{rel}", "bundle")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((shared / "installed_plugins.json").read_text(), "shared")
        self.assertIn("skipped (host-profile managed)", out)

    def test_restore_never_overwrites_host_profile_files(self):
        sb = self.sb
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            before = {
                "scripts/watchdog.json": "dest-wd",
                "scripts/hermes-hygiene.py": "dest-hy",
                "scripts/state-manifest.yaml": "dest-sm",
                "agent-hooks/red-gate.py": "dest-rg",
                "skills/devops/aws-devfactory-operations/SKILL.md": "dest-skill",
            }
            for rel, text in before.items():
                self.put("hermes", rel, text)
            os.chmod(sb.hermes / "agent-hooks", 0o755)
            os.chmod(sb.hermes / "skills/devops/aws-devfactory-operations", 0o755)
            b = Bundle(source_home=str(sb.home))
            b.dir("hermes/scripts").dir("hermes/agent-hooks", mode=0o700).dir("hermes/skills")
            b.dir("hermes/skills/devops").dir("hermes/skills/devops/aws-devfactory-operations", mode=0o700)
            for rel in list(before) + ["scripts/aws-keep-hot.sh", "scripts/mine.sh"]:
                b.file(f"hermes/{rel}", f"bundle-{rel}")
            b.write(self.F)
            code, out, err = self.restore()
            self.assertEqual(code, 0, out + err)
            for rel, text in before.items():
                self.assertEqual((sb.hermes / rel).read_text(), text, rel)
            self.assertFalse((sb.hermes / "scripts/aws-keep-hot.sh").exists())
            self.assertEqual((sb.hermes / "scripts/mine.sh").read_text(), "bundle-scripts/mine.sh")
            for rel in list(before) + ["scripts/aws-keep-hot.sh", "agent-hooks", "skills/devops/aws-devfactory-operations"]:
                self.assertRegex(out, rf"skipped \(host-profile managed\) {re.escape(rel)}\n", rel)
            self.assertEqual(stat_mode(sb.hermes / "agent-hooks"), 0o755)
            self.assertEqual(stat_mode(sb.hermes / "skills/devops/aws-devfactory-operations"), 0o755)
            shutil.rmtree(sb.hermes / "agent-hooks")
            self.assertEqual(self.restore()[0], 0)
            self.assertFalse((sb.hermes / "agent-hooks").exists())

    def test_restore_skipped_link_prints_only_the_skip_line(self):
        sb = self.sb
        repo_a = self.outside / "repoA"
        repo_a.mkdir()
        (sb.hermes / "plugins").mkdir()
        (sb.hermes / "plugins/claude-orchestrate").symlink_to(repo_a / "plugin")
        b = Bundle(source_home="/Users/olduser")
        b.dir("hermes/plugins").link("hermes/plugins/claude-orchestrate", "/Users/olduser/hermes-setup/plugin")
        b.write(self.F)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        lines = [ln for ln in out.splitlines() if "claude-orchestrate" in ln]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("skipped (host-profile managed)", lines[0])
        self.assertNotIn("would replace link", out)
        code, out, err = self.restore()
        self.assertEqual(os.readlink(sb.hermes / "plugins/claude-orchestrate"), str(repo_a / "plugin"))
        self.assertEqual(self.backups(), [])

    def test_restore_skips_platform_specific_for_missing_platform(self):
        sb = self.sb
        manifest = _write(
            sb.home / "m.yaml",
            """\
            version: 1
            rules:
              - {root: hermes, match: "desktop", class: platform-specific, platform: mac, carry: true}
              - {root: hermes, match: "cron", class: platform-specific, platform: gateway, carry: true}
              - {root: claude, match: "*", class: host-local}
            """,
        )
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/desktop", cls="platform-specific", platform="mac")
        b.file("hermes/desktop/app.json", "{}", cls="platform-specific", platform="mac")
        b.dir("hermes/cron", cls="platform-specific", platform="gateway")
        b.file("hermes/cron/jobs.json", "{}", cls="platform-specific", platform="gateway")
        b.write(self.F)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            _code, out, _err = sb.run("--manifest", str(manifest), "restore", "--from", str(self.F))
        self.assertFalse((sb.hermes / "desktop").exists())
        self.assertFalse((sb.hermes / "cron").exists())
        self.assertIn("skipped (platform mac)", out)
        self.assertIn("skipped (platform gateway)", out)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "mac"}):
            sb.run("--manifest", str(manifest), "restore", "--from", str(self.F))
        self.assertTrue((sb.hermes / "desktop/app.json").exists())
        self.assertFalse((sb.hermes / "cron").exists())


def stat_mode(path):
    return os.stat(path).st_mode & 0o7777


class RestoreContentTest(RestoreBase):
    def test_restore_rewrites_text_config_only(self):
        sb = self.sb
        old = "/Users/olduser"
        tmp = self.make_tmp()
        b = Bundle(source_home=old, platforms=("linux", "sora", "gateway"))
        b.file("hermes/config.yaml", f"h: {old}/x\nk: /Users/olduserx/keep\n", cls="secret")
        b.file("hermes/synapse-mem.json", f'{{"p": "{old}/m"}}')
        b.dir("hermes/cron", cls="platform-specific", platform="gateway")
        b.file("hermes/cron/jobs.json", f'{{"p": "{old}/j"}}', cls="platform-specific", platform="gateway")
        b.dir("hermes/memories").file("hermes/memories/m.md", f"note {old}/x")
        b.file("claude/history.jsonl", f"{old}/h\n", cls="history")
        b.sqlite("hermes/state.db", _db_bytes(tmp, f"{old}/row"), cls="history")
        b.write(self.F)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "sora"}):
            code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        home = str(sb.home)
        self.assertEqual((sb.hermes / "config.yaml").read_text(), f"h: {home}/x\nk: /Users/olduserx/keep\n")
        self.assertEqual((sb.hermes / "synapse-mem.json").read_text(), f'{{"p": "{home}/m"}}')
        self.assertEqual((sb.hermes / "cron/jobs.json").read_text(), f'{{"p": "{home}/j"}}')
        self.assertEqual((sb.hermes / "memories/m.md").read_text(), f"note {old}/x")
        self.assertEqual((sb.claude / "history.jsonl").read_text(), f"{old}/h\n")
        self.assertEqual((sb.hermes / "state.db").read_bytes(), b.data[b.seq("hermes/state.db")])

        shutil.rmtree(sb.hermes)
        sb.hermes.mkdir()
        b2 = Bundle(source_home=old)
        pit = {
            "hermes/state-snapshots/s/config.yaml": "secret",
            "hermes/backups/b/.env": "secret",
            "hermes/.curator_backups/c.json": "secret",
            "hermes/.env.bak-x": "secret",
            "hermes/.env.pre-migration-backup-x": "secret",
            "hermes/config.yaml.bak-x": "secret",
            "hermes/config.yaml.orig-x": "secret",
            "claude/settings.json.bak": "secret",
        }
        for path, cls in pit.items():
            b2.file(path, f"v={old}/p", cls=cls)
        b2.file("hermes/.env", f"HOME_DIR={old}/p", cls="secret", mode=0o600)
        b2.file("hermes/config.yaml", f"home: {old}/p", cls="secret", mode=0o600)
        b2.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        for path in pit:
            root, rel = path.split("/", 1)
            self.assertEqual((sb.root(root) / rel).read_text(), f"v={old}/p", path)
        self.assertEqual((sb.hermes / ".env").read_text(), f"HOME_DIR={home}/p")
        self.assertEqual((sb.hermes / "config.yaml").read_text(), f"home: {home}/p")

    def test_restore_preserves_modes(self):
        sb = self.sb
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        b = Bundle(source_home="/Users/olduser")
        b.file("hermes/.env", "A=/Users/olduser/x", cls="secret", mode=0o600)
        b.file("hermes/config.yaml", "a: /Users/olduser/x", cls="secret", mode=0o600)
        b.dir("hermes/mcp-tokens", mode=0o700, cls="secret").file("hermes/mcp-tokens/t.json", "{}", mode=0o600, cls="secret")
        b.sqlite("hermes/state.db", _db_bytes(self.make_tmp(), "r"), mode=0o640, cls="history")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(stat_mode(sb.hermes / ".env"), 0o600)
        self.assertEqual(stat_mode(sb.hermes / "config.yaml"), 0o600)
        self.assertEqual(stat_mode(sb.hermes / "mcp-tokens"), 0o700)
        self.assertEqual(stat_mode(sb.hermes / "mcp-tokens/t.json"), 0o600)
        self.assertEqual(stat_mode(sb.hermes / "state.db"), 0o640)

    def test_restore_dry_run_writes_nothing(self):
        sb = self.sb
        self.put("hermes", "memories/same.md", "same")
        self.put("hermes", "memories/diff.md", "dest")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/memories").file("hermes/memories/same.md", "same").file("hermes/memories/diff.md", "bundle")
        b.file("hermes/memories/new.md", "new").file("hermes/scripts/hermes-hygiene.py", "x")
        b.write(self.F)
        before = _listing(sb)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(_listing(sb), before)
        self.assertIn("would write", out)
        self.assertRegex(out, r"identical.*same\.md")
        self.assertIn("skipped (host-profile managed)", out)

    def test_restore_dry_run_does_not_sweep_staging(self):
        sb = self.sb
        old = sb.hermes / "state-staging" / "old"
        old.mkdir(parents=True)
        t = time.time() - 2 * 86400
        os.utime(old, (t, t))
        b = Bundle(source_home=str(sb.home))
        b.file("hermes/SOUL.md", "s")
        b.write(self.F)
        self.assertEqual(self.restore("--dry-run")[0], 0)
        self.assertTrue(old.exists())
        self.assertEqual(self.restore()[0], 0)
        self.assertFalse(old.exists())

    def test_restore_merges_dir_keeps_destination_only_files(self):
        sb = self.sb
        self.put("hermes", "skills/local-only/SKILL.md", "local")
        self.put("hermes", "SOUL.md", "dest soul")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/skills").dir("hermes/skills/s1").file("hermes/skills/s1/SKILL.md", "s1")
        b.file("hermes/SOUL.md", "bundle soul")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / "skills/local-only/SKILL.md").read_text(), "local")
        self.assertEqual((sb.hermes / "skills/s1/SKILL.md").read_text(), "s1")
        self.assertEqual(self.backup_path("SOUL.md").read_text(), "dest soul")
        n = len(self.backups())
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.backups()), n)

    def test_restore_rerun_with_differing_home_creates_no_backup(self):
        sb = self.sb
        self.put("hermes", "config.yaml", "template")
        self.put("hermes", ".env", "template=1")
        b = Bundle(source_home="/Users/olduser")
        b.file("hermes/config.yaml", "home: /Users/olduser/x", cls="secret", mode=0o600)
        b.file("hermes/.env", "H=/Users/olduser/y", cls="secret", mode=0o600)
        b.write(self.F)
        self.assertEqual(self.restore()[0], 0)
        self.assertEqual(len(self.backups()), 1)
        mtime = (sb.hermes / "config.yaml").stat().st_mtime_ns
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual((sb.hermes / "config.yaml").stat().st_mtime_ns, mtime)
        for name in ("config.yaml", ".env"):
            self.assertRegex(out, rf"identical {re.escape(name)}\n")

    def test_restore_sqlite_moves_stale_wal(self):
        sb = self.sb
        sb.link_tool("lsof")
        tmp = self.make_tmp()
        conn = _wal_db(tmp / "other.db", "stale")
        self.addCleanup(conn.close)
        stale = (tmp / "other.db-wal").read_bytes()
        self.assertTrue(stale)
        self.put("hermes", "state.db", _db_bytes(tmp, "dest"))
        self.put("hermes", "state.db-wal", stale)
        b = Bundle(source_home=str(sb.home))
        b.sqlite("hermes/state.db", _db_bytes(tmp, "b1", "b2"), cls="history")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        db = sqlite3.connect(sb.hermes / "state.db")
        self.addCleanup(db.close)
        self.assertEqual(db.execute("pragma integrity_check").fetchone()[0], "ok")
        self.assertEqual([r[0] for r in db.execute("select v from t")], ["b1", "b2"])
        self.assertEqual(self.backup_path("state.db-wal").read_bytes(), stale)
        self.assertFalse((sb.hermes / "state.db-wal").exists())


class RestoreLinkTest(RestoreBase):
    def _outside_tree(self, rel_files):
        root = self.outside
        for rel, text in rel_files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}

    def test_restore_never_writes_through_destination_link(self):
        sb = self.sb
        snap = self._outside_tree({"x/SKILL.md": "old"})
        (sb.hermes / "skills").mkdir()
        (sb.hermes / "skills/x").symlink_to(self.outside / "x")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/skills").dir("hermes/skills/x")
        b.file("hermes/skills/x/SKILL.md", "new").file("hermes/skills/x/notes.md", "n")
        b.write(self.F)
        before = _listing(sb)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("would replace link skills/x", out)
        self.assertEqual(_listing(sb), before)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        now = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.outside.rglob("*") if p.is_file()}
        self.assertEqual(now, snap)
        self.assertFalse((sb.hermes / "skills/x").is_symlink())
        self.assertEqual((sb.hermes / "skills/x/SKILL.md").read_text(), "new")
        self.assertEqual((sb.hermes / "skills/x/notes.md").read_text(), "n")
        backup = self.backup_path("skills/x")
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), str(self.outside / "x"))
        n = len(self.backups())
        self.assertEqual(self.restore()[0], 0)
        self.assertEqual(len(self.backups()), n)

    def test_restore_bundle_link_replaces_destination_dir(self):
        sb = self.sb
        self.put("hermes", "skills/y/SKILL.md", "s")
        self.put("hermes", "skills/y/local.md", "l")
        b = Bundle(source_home="/Users/olduser")
        b.dir("hermes/skills").link("hermes/skills/y", "/Users/olduser/ext/y")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(os.readlink(sb.hermes / "skills/y"), f"{sb.home}/ext/y")
        self.assertEqual((self.backup_path("skills/y") / "SKILL.md").read_text(), "s")
        self.assertEqual((self.backup_path("skills/y") / "local.md").read_text(), "l")
        self.assertFalse((sb.home / "ext").exists())
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertRegex(out, r"identical skills/y\n")

    def test_restore_bundle_file_over_destination_file_link(self):
        sb = self.sb
        for same in (True, False):
            shutil.rmtree(sb.hermes / "state-restore-backups", ignore_errors=True)
            if os.path.lexists(sb.hermes / "SOUL.md"):
                os.unlink(sb.hermes / "SOUL.md")
            shutil.rmtree(self.outside)
            self.outside.mkdir()
            snap = self._outside_tree({"SOUL.md": "bundle soul" if same else "other"})
            (sb.hermes / "SOUL.md").symlink_to(self.outside / "SOUL.md")
            b = Bundle(source_home=str(sb.home))
            b.file("hermes/SOUL.md", "bundle soul", mode=0o640)
            b.write(self.F)
            before = _listing(sb, [self.outside])
            code, out, err = self.restore("--dry-run")
            self.assertEqual(code, 0, out + err)
            self.assertIn("would replace link SOUL.md", out)
            self.assertEqual(_listing(sb, [self.outside]), before)
            code, out, err = self.restore()
            self.assertEqual(code, 0, out + err)
            now = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in self.outside.rglob("*") if p.is_file()}
            self.assertEqual(now, snap)
            self.assertFalse((sb.hermes / "SOUL.md").is_symlink())
            self.assertEqual((sb.hermes / "SOUL.md").read_text(), "bundle soul")
            self.assertEqual(stat_mode(sb.hermes / "SOUL.md"), 0o640)
            backup = self.backup_path("SOUL.md")
            self.assertTrue(backup.is_symlink())
            self.assertEqual(os.readlink(backup), str(self.outside / "SOUL.md"))
            self.assertNotRegex(out, r"identical SOUL\.md")
            n = len(self.backups())
            code, out, err = self.restore()
            self.assertRegex(out, r"identical SOUL\.md")
            self.assertEqual(len(self.backups()), n)

    def test_restore_bundle_link_over_destination_link_other_target(self):
        sb = self.sb
        target_a = self.outside / "a"
        target_a.mkdir()
        (target_a / "SKILL.md").write_text("a")
        snap = {p: p.stat().st_mtime_ns for p in target_a.rglob("*")}
        (sb.hermes / "skills").mkdir()
        (sb.hermes / "skills/z").symlink_to(target_a)
        b = Bundle(source_home="/Users/olduser")
        b.dir("hermes/skills").link("hermes/skills/z", "/Users/olduser/ext/z")
        b.write(self.F)
        before = _listing(sb)
        code, out, err = self.restore("--dry-run")
        self.assertIn("would replace link skills/z", out)
        self.assertEqual(_listing(sb), before)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(os.readlink(sb.hermes / "skills/z"), f"{sb.home}/ext/z")
        self.assertEqual(os.readlink(self.backup_path("skills/z")), str(target_a))
        self.assertEqual({p: p.stat().st_mtime_ns for p in target_a.rglob("*")}, snap)
        shutil.rmtree(sb.hermes / "state-restore-backups")
        mtime = os.lstat(sb.hermes / "skills/z").st_mtime_ns
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertRegex(out, r"identical skills/z\n")
        self.assertEqual(self.backups(), [])
        self.assertEqual(os.lstat(sb.hermes / "skills/z").st_mtime_ns, mtime)


class RestoreSpecialFileTest(RestoreBase):
    def _bundle(self):
        b = Bundle(source_home=str(self.sb.home))
        b.dir("hermes/memories").file("hermes/memories/a.md", "a").file("hermes/memories/b.md", "b")
        b.file("hermes/SOUL.md", "soul")
        b.write(self.F)

    def test_restore_destination_fifo_or_socket_never_opened(self):
        sb = self.sb
        self._bundle()
        mem = sb.hermes / "memories"
        mem.mkdir()
        os.mkfifo(mem / "a.md")
        self.bind_socket(mem, "b.md")
        inodes = {n: os.lstat(mem / n).st_ino for n in ("a.md", "b.md")}
        code, out, err = self.restore("--dry-run", sub=True)
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (unsupported type fifo) memories/a.md", out)
        self.assertIn("would fail (unsupported type socket) memories/b.md", out)
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (unsupported type fifo) memories/a.md", out)
        self.assertIn("failed (unsupported type socket) memories/b.md", out)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        for n, ino in inodes.items():
            self.assertEqual(os.lstat(mem / n).st_ino, ino)
        self.assertEqual(self.backups(), [])
        os.unlink(mem / "a.md")
        os.unlink(mem / "b.md")
        self.assertEqual(self.restore("--dry-run", sub=True)[0], 0)
        shutil.rmtree(mem)
        os.mkfifo(mem)
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (unsupported type fifo) memories/a.md", out)
        self.assertIn("failed (unsupported type fifo) memories/b.md", out)
        self.assertTrue(stat_isfifo(os.lstat(mem)))

    def test_restore_fifo_swapped_in_after_plan_never_blocks(self):
        sb = self.sb
        self._bundle()
        self.put("hermes", "memories/a.md", "dest differs")
        target = sb.hermes / "memories/a.md"

        def swap():
            os.unlink(target)
            os.mkfifo(target)

        with mock.patch.object(sb.mod, "_after_plan", swap):
            code, out, err = self.run_thread("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (unsupported type fifo) memories/a.md", out)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertTrue(stat_isfifo(os.lstat(target)))
        self.assertFalse(list((sb.hermes / "state-restore-backups").rglob("a.md")))

    def test_restore_socket_swapped_in_after_plan(self):
        sb = self.sb
        self._bundle()
        self.put("hermes", "memories/a.md", "dest differs")
        target = sb.hermes / "memories/a.md"
        state = {}

        def swap():
            os.unlink(target)
            self.bind_socket(target.parent, "a.md")
            state["ino"] = os.lstat(target).st_ino

        with mock.patch.object(sb.mod, "_after_plan", swap):
            code, out, err = self.run_thread("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (unsupported type socket) memories/a.md", out)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        st = os.lstat(target)
        self.assertTrue(stat_issock(st))
        self.assertEqual(st.st_ino, state["ino"])
        self.assertFalse(list((sb.hermes / "state-restore-backups").rglob("a.md")))

    def test_restore_link_swapped_in_after_plan(self):
        sb = self.sb
        self._bundle()
        self.put("hermes", "memories/a.md", "dest differs")
        victim = self.outside / "a.md"
        victim.write_text("known")
        snap = (victim.stat().st_mtime_ns, victim.read_bytes())
        target = sb.hermes / "memories/a.md"

        def swap():
            os.unlink(target)
            os.symlink(victim, target)

        real_open = os.open
        followed = []

        def spy(path, flags, *a, **kw):
            if not flags & os.O_NOFOLLOW and os.path.realpath(path) == str(victim.resolve()):
                followed.append(path)
            return real_open(path, flags, *a, **kw)

        with mock.patch.object(sb.mod, "_after_plan", swap), mock.patch.object(os, "open", spy):
            code, out, err = sb.run("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (changed during restore) memories/a.md", out)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertEqual(followed, [])
        self.assertEqual((victim.stat().st_mtime_ns, victim.read_bytes()), snap)
        self.assertEqual(sorted(os.listdir(self.outside)), ["a.md"])
        self.assertEqual(os.readlink(target), str(victim))
        self.assertFalse(list((sb.hermes / "state-restore-backups").rglob("a.md")))
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(os.readlink(self.backup_path("memories/a.md")), str(victim))
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_text(), "a")
        self.assertEqual((victim.stat().st_mtime_ns, victim.read_bytes()), snap)


def stat_isfifo(st):
    import stat as _stat

    return _stat.S_ISFIFO(st.st_mode)


def stat_issock(st):
    import stat as _stat

    return _stat.S_ISSOCK(st.st_mode)


class RestoreClashMoveTest(RestoreBase):
    def _setup(self, with_socket):
        sb = self.sb
        self.put("hermes", "skills/x/SKILL.md", "orig")
        sub = sb.hermes / "skills/x/sub"
        sub.mkdir()
        if with_socket:
            self.bind_socket(sub, "s.sock")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/skills").link("hermes/skills/x", f"{sb.home}/ext/x")
        b.file("hermes/SOUL.md", "soul")
        b.write(self.F)
        self.src = str(sb.hermes / "skills/x")

    def _patch(self):
        real_rename, real_replace = os.rename, os.replace

        def wrap(real):
            def inner(src, dst, *a, **kw):
                if os.fspath(src) == self.src:
                    raise OSError(errno.EXDEV, "patched")
                return real(src, dst, *a, **kw)

            return inner

        return mock.patch.multiple(os, rename=wrap(real_rename), replace=wrap(real_replace))

    def test_restore_cross_device_clash_with_nested_socket_fails_entry(self):
        sb = self.sb
        self._setup(with_socket=True)
        x = sb.hermes / "skills/x"
        ino, sock_ino = os.lstat(x).st_ino, os.lstat(x / "sub/s.sock").st_ino
        with self._patch():
            code, out, err = sb.run("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (unsupported type socket at sub/s.sock) skills/x", out)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertTrue(x.is_dir() and not x.is_symlink())
        self.assertEqual(os.lstat(x).st_ino, ino)
        self.assertEqual((x / "SKILL.md").read_text(), "orig")
        self.assertEqual(os.lstat(x / "sub/s.sock").st_ino, sock_ino)
        self.assertFalse(list((sb.hermes / "state-restore-backups").rglob("x")))

    def test_restore_cross_device_clash_control_copies_into_backup(self):
        sb = self.sb
        self._setup(with_socket=False)
        with self._patch():
            code, out, err = sb.run("restore", "--from", str(self.F))
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.backup_path("skills/x") / "SKILL.md").read_text(), "orig")
        self.assertTrue((sb.hermes / "skills/x").is_symlink())

    def test_restore_cross_device_clash_removal_fails_after_copy(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory modes")
        sb = self.sb
        self.put("hermes", "skills/x/SKILL.md", "orig")
        self.put("hermes", "skills/x/ro/f", "frozen")
        ro = sb.hermes / "skills/x/ro"
        os.chmod(ro, 0o500)
        self.addCleanup(lambda: os.path.isdir(ro) and os.chmod(ro, 0o700))
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/skills").link("hermes/skills/x", f"{sb.home}/ext/x")
        b.write(self.F)
        self.src = str(sb.hermes / "skills/x")
        with self._patch():
            code, out, err = sb.run("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("skills/x", out + err)
        self.assertIn("EACCES", out + err)
        backup = self.backup_path("skills/x")
        self.assertIn(str(backup.parent.parent), out + err)
        self.addCleanup(lambda: os.path.isdir(backup / "ro") and os.chmod(backup / "ro", 0o700))
        self.assertEqual((backup / "SKILL.md").read_text(), "orig")
        self.assertEqual((backup / "ro/f").read_text(), "frozen")
        x = sb.hermes / "skills/x"
        self.assertTrue(x.is_dir() and not x.is_symlink())
        self.assertEqual((x / "ro/f").read_text(), "frozen")
        self.assertIn("applied", out)


class RestoreFailureTest(RestoreBase):
    def _bundle(self, **kw):
        b = Bundle(source_home=str(self.sb.home), **kw)
        b.dir("hermes/memories").file("hermes/memories/a.md", "a-bundle").file("hermes/memories/b.md", "b-bundle")
        b.file("hermes/SOUL.md", "soul")
        return b

    def test_restore_dry_run_digest_mismatch_exits_2(self):
        sb = self.sb
        self.put("hermes", "memories/a.md", "dest-a")
        b = self._bundle()
        b.tamper.add(b.seq("hermes/memories/a.md"))
        b.write(self.F)
        before = _listing(sb)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (digest mismatch) memories/a.md", out)
        self.assertRegex(out, r"would write memories/b\.md")
        self.assertEqual(_listing(sb), before)
        self._bundle().write(self.F)
        self.assertEqual(self.restore("--dry-run")[0], 0)

    def test_restore_digest_mismatch_leaves_target_and_applies_others(self):
        sb = self.sb
        self.put("hermes", "memories/a.md", "dest-a")
        b = self._bundle()
        b.tamper.add(b.seq("hermes/memories/a.md"))
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (digest mismatch) memories/a.md", out)
        self.assertEqual((sb.hermes / "memories/a.md").read_text(), "dest-a")
        self.assertEqual((sb.hermes / "memories/b.md").read_text(), "b-bundle")
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertEqual(list(sb.hermes.rglob(".*restore-*")), [])

    def test_restore_vanished_file_is_skipped(self):
        sb = self.sb
        b = self._bundle()
        b.vanish.add(b.seq("hermes/memories/a.md"))
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertIn("skipped (vanished during export) memories/a.md", out)
        self.assertFalse((sb.hermes / "memories/a.md").exists())

    def test_restore_dry_run_outside_root_exits_2(self):
        sb = self.sb
        (sb.hermes / "memories").mkdir()
        (self.outside / "keep.txt").write_text("k")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/memories").file("hermes/memories/a.md", "a")
        b.write(self.F)

        def swap():
            shutil.rmtree(sb.hermes / "memories")
            os.symlink(self.outside, sb.hermes / "memories")

        with mock.patch.object(sb.mod, "_after_plan", swap):
            code, out, err = sb.run("restore", "--from", str(self.F), "--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (outside root) memories/a.md", out)
        self.assertEqual(sorted(os.listdir(self.outside)), ["keep.txt"])
        os.unlink(sb.hermes / "memories")
        (sb.hermes / "memories").mkdir()
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/memories").file("hermes/memories/new/c.md", "c")
        b.write(self.F)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("would write memories/new/c.md", out)

    def test_restore_outside_root_parent_fails_entry(self):
        sb = self.sb
        (sb.hermes / "memories").mkdir()
        b = self._bundle()
        b.write(self.F)

        def swap():
            shutil.rmtree(sb.hermes / "memories")
            os.symlink(self.outside, sb.hermes / "memories")

        with mock.patch.object(sb.mod, "_after_plan", swap):
            code, out, err = sb.run("restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (outside root) memories/a.md", out)
        self.assertEqual(os.listdir(self.outside), [])
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")

    def test_restore_dry_run_gpg_nonzero_exits_2(self):
        sb = self.sb
        self._bundle().write(self.F)
        before = _listing(sb)
        with mock.patch.dict(os.environ, {"GPG_STUB_DEC_EXITS": "2,2"}):
            code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertTrue(out.rstrip().endswith("would fail (gpg exit 2)"), out)
        self.assertEqual(_listing(sb), before)
        with mock.patch.dict(os.environ, {"GPG_STUB_DEC_EXITS": "2,0"}):
            code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)

    def test_restore_pass1_ignores_gpg_sigpipe_exit(self):
        sb = self.sb
        self._bundle().write(self.F)
        with mock.patch.dict(os.environ, {"GPG_STUB_DEC_EXITS": "2,0"}):
            code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertEqual(len([e for e in sb.gpg_log() if e["mode"] == "decrypt"]), 2)
        os.unlink(sb.hermes / "SOUL.md")
        (sb.home / "gpg.log").unlink()
        with mock.patch.dict(os.environ, {"GPG_STUB_DEC_EXITS": "0,2"}):
            code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertIn("applied", out)
        shutil.rmtree(sb.hermes)
        sb.hermes.mkdir()
        with mock.patch.dict(os.environ, {"GPG_STUB_DEC_FAIL_EARLY": "1"}):
            code, out, err = self.restore()
        self.assertEqual(code, 2)
        self.assertEqual(os.listdir(sb.hermes), [])

    def test_restore_refuses_bad_sha(self):
        self._bundle().write(self.F, bad_sha=True)
        code, _out, err = self.restore()
        self.assertEqual(code, 1, err)
        self.assertEqual(self.sb.gpg_log(), [])
        self._bundle().write(self.F, write_sha=False)
        Path(f"{self.F}.sha256").unlink(missing_ok=True)
        code, _out, err = self.restore()
        self.assertEqual(code, 1, err)
        self.assertEqual(self.sb.gpg_log(), [])

    def test_restore_unknown_bundle_schema_exits_1(self):
        sb = self.sb
        for schema in (2, _MISSING, True):
            (sb.home / "gpg.log").unlink(missing_ok=True)
            self._bundle(schema=schema).write(self.F)
            before = _listing(sb)
            code, _out, err = self.restore()
            self.assertEqual(code, 1, (schema, err))
            self.assertIn("schema", err)
            self.assertEqual(len([e for e in sb.gpg_log() if e["mode"] == "decrypt"]), 1)
            self.assertEqual(_listing(sb), before)

    def test_restore_rejects_path_traversal_member(self):
        sb = self.sb
        for bad in ("../x", "/abs/x", "other/x"):
            b = Bundle(source_home=str(sb.home))
            b.file(bad, "x")
            b.entries[0]["root"] = "hermes"
            b.write(self.F)
            before = _listing(sb)
            code, out, err = self.restore()
            self.assertEqual(code, 1, (bad, err))
            self.assertEqual(_listing(sb), before)
        b = self._bundle()
        b.extra_members.append(("hermes/../../y", b"y"))
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertFalse((sb.home / "y").exists())
        self.assertFalse((sb.home.parent / "y").exists())

    def test_restore_closing_audit_exit_3(self):
        sb = self.sb
        (sb.hermes / "zzz-unclassified").mkdir()
        self._bundle().write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 3, out + err)
        self.assertIn("hermes/zzz-unclassified", out)

    def test_restore_then_seed_audit_exits_0_and_export_not_refused(self):
        sb = self.sb
        self.put("hermes", "config.yaml", "template")
        self.put("hermes", ".env", "t=1")
        b = Bundle(source_home="/Users/olduser")
        b.file("hermes/config.yaml", "a: 1", cls="secret").file("hermes/.env", "b=2", cls="secret")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.backups())
        self.assertEqual(sb.run("audit")[0], 0)
        g = sb.home / "g.gpg"
        code, out, err = sb.run("export", "--out", str(g))
        self.assertEqual(code, 0, err)
        meta = _bundle_json(_read_bundle(sb.home / "gpg.stdin"))
        for e in meta["entries"]:
            self.assertNotIn("state-restore-backups", e["path"])
            self.assertNotIn("state-staging", e["path"])


class RestoreGuardTest(RestoreBase):
    def _bundle(self):
        b = Bundle(source_home=str(self.sb.home))
        b.file("hermes/SOUL.md", "soul")
        b.write(self.F)

    def test_restore_gateway_pid_json(self):
        sb = self.sb
        self._bundle()
        pid_file = sb.hermes / "gateway.pid"
        data = {"pid": os.getpid(), "kind": "hermes-gateway", "argv": [], "hermes_home": str(sb.hermes), "start_time": 0}
        pid_file.write_text(json.dumps(data))
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 1, out + err)
        self.assertFalse((sb.hermes / "SOUL.md").exists())
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        pid_file.write_text(json.dumps({**data, "pid": dead.pid}))
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 0, out + err)
        self.assertTrue((sb.hermes / "SOUL.md").exists())
        os.unlink(sb.hermes / "SOUL.md")
        pid_file.write_text(str(os.getpid()))
        self.assertEqual(self.restore(sub=True)[0], 1)

    def test_restore_refuses_db_held_open(self):
        sb = self.sb
        sb.link_tool("lsof")
        conn = _wal_db(sb.hermes / "state.db", "held")
        holder = [conn]
        self.addCleanup(lambda: [c.close() for c in holder])
        b = Bundle(source_home=str(sb.home))
        b.sqlite("hermes/state.db", _db_bytes(self.make_tmp(), "new"), cls="history")
        b.write(self.F)
        before = {n: (sb.hermes / n).read_bytes() for n in ("state.db", "state.db-wal")}
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 1, out + err)
        self.assertIn("state.db", err)
        self.assertEqual({n: (sb.hermes / n).read_bytes() for n in before}, before)
        conn.close()
        holder.clear()
        code, out, err = self.restore(sub=True)
        self.assertEqual(code, 0, out + err)

    def test_missing_lsof_message(self):
        sb = self.sb
        self.put("hermes", "state.db", "existing")
        b = Bundle(source_home=str(sb.home))
        b.sqlite("hermes/state.db", _db_bytes(self.make_tmp(), "new"), cls="history").file("hermes/SOUL.md", "s")
        b.write(self.F)
        code, _out, err = self.restore(sub=True)
        self.assertEqual(code, 1)
        self.assertIn("sudo apt-get install lsof", err)
        self.assertEqual((sb.hermes / "state.db").read_text(), "existing")
        self.assertFalse((sb.hermes / "SOUL.md").exists())

    def test_missing_gpg_message_on_restore(self):
        self._bundle()
        (self.sb.bin / "gpg").unlink()
        code, _out, err = self.restore()
        self.assertEqual(code, 2)
        self.assertIn("sudo apt-get install gnupg", err)


class RestoreNotesTest(RestoreBase):
    def _env_bundle(self, text, name=".env"):
        b = Bundle(source_home=str(self.sb.home))
        b.file(f"hermes/{name}", text, cls="secret", mode=0o600)
        b.write(self.F)

    def test_restore_warns_on_telegram_enabled_non_gateway(self):
        self._env_bundle("TELEGRAM_BOT_TOKEN=SENTINEL-TG\n")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            _code, out, err = self.restore()
        self.assertIn("TELEGRAM_BOT_TOKEN", out)
        self.assertIn("WARNING: restored .env enables Telegram (TELEGRAM_BOT_TOKEN) on a non-gateway host", out)
        self.assertNotIn("SENTINEL-TG", out + err)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "sora"}):
            _code, out, err = self.restore()
        self.assertNotIn("WARNING", out)

    def test_restore_warns_on_config_yaml_telegram_enabled(self):
        text = "platforms:\n  telegram:\n    enabled: {}\n    token: SENTINEL-CY\n"
        self._env_bundle(text.format("true"), "config.yaml")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            _code, out, err = self.restore()
        self.assertIn("WARNING", out)
        self.assertIn("config.yaml", out)
        self.assertIn("platforms.telegram.enabled", out)
        self.assertNotIn("SENTINEL-CY", out + err)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "sora"}):
            self.assertNotIn("WARNING", self.restore()[1])
        self._env_bundle(text.format("false"), "config.yaml")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            self.assertNotIn("WARNING", self.restore()[1])

    def test_restore_config_overrides_note(self):
        sb = self.sb
        b = Bundle(source_home=str(sb.home), platforms=("linux", "sora", "gateway"))
        b.file("hermes/config.yaml", "a: 1", cls="secret", mode=0o600)
        b.write(self.F)
        self.put("hermes", "config.yaml", "a: 2")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl"}):
            _code, out, _err = self.restore()
        self.assertIn("hosts/wsl/config-overrides.yaml", out)
        self.put("hermes", "config.yaml", "a: 2")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "sora"}):
            _code, out, _err = self.restore()
        self.assertNotIn("config-overrides.yaml", out)

    def test_restore_notes_plugins_missing_from_dest_plugins_txt(self):
        sb = self.sb
        repo = sb.home / "repo"
        (repo / "hosts/wsl").mkdir(parents=True)
        (repo / "hosts/wsl/plugins.txt").write_text("superpowers obra/superpowers\n")
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/plugins")
        for name in ("spotify", "superpowers", "old.bak-20261105", "hermes-session-reset-policy", "synapse-mem"):
            b.dir(f"hermes/plugins/{name}")
        b.link("hermes/plugins/claude-orchestrate", "/x/y")
        for name in (".install-metadata.json", ".install-metadata.json.lock", "notes.txt"):
            b.file(f"hermes/plugins/{name}", "x")
        b.write(self.F)
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl", "REPO_DIR": str(repo)}):
            code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        (note,) = [ln for ln in out.splitlines() if ln.startswith("note: restored plugins")]
        self.assertIn("spotify", note)
        self.assertIn("hosts/wsl/plugins.txt", note)
        for name in ("superpowers", "old.bak", "claude-orchestrate", "hermes-session-reset-policy", "synapse-mem",
                     ".install-metadata", "notes.txt"):
            self.assertNotIn(name, note)
        (repo / "hosts/wsl/plugins.txt").unlink()
        shutil.rmtree(sb.hermes / "plugins")
        with mock.patch.dict(os.environ, {"HERMES_HOST_PROFILE": "wsl", "REPO_DIR": str(repo)}):
            code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        (note,) = [ln for ln in out.splitlines() if ln.startswith("note: restored plugins")]
        self.assertIn("spotify", note)
        self.assertIn("superpowers", note)
        self.assertIn("not found", note)
        for name in ("old.bak", "claude-orchestrate", "hermes-session-reset-policy", "synapse-mem", ".install-metadata", "notes.txt"):
            self.assertNotIn(name, note)


class RoundTripTest(unittest.TestCase):
    def _export(self, setup):
        sb1 = Sandbox(self)
        sb1.gpg_stub()
        setup(sb1)
        shared = Path(tempfile.mkdtemp(dir=sb1.home))
        out = shared / "b.gpg"
        self.assertEqual(sb1.run("export", "--out", str(out))[0], 0)
        return sb1, out

    def _into_second(self, out):
        sb2 = Sandbox(self)
        sb2.gpg_stub()
        sb2.link_tool("lsof") if shutil.which("lsof", path=sb2.orig_path) else None
        dest = sb2.home / "b.gpg"
        shutil.copy(out, dest)
        shutil.copy(f"{out}.sha256", f"{dest}.sha256")
        return sb2, dest

    def test_export_and_restore_smem_store(self):
        def setup(sb):
            sb.smem.mkdir()
            conn = _wal_db(sb.smem / "smem.db")
            self.addCleanup(conn.close)
            (sb.smem / "sessions").mkdir()
            (sb.smem / "sessions/123").write_text("x")
            (sb.smem / "spool").mkdir()
            (sb.smem / "spool/1.json").write_text(f'{{"h": "{sb.home}"}}')
            (sb.smem / "config.json").write_text(json.dumps({"home": str(sb.home)}))

        sb1, out = self._export(setup)
        spool_bytes = (sb1.smem / "spool/1.json").read_bytes()
        sb2, dest = self._into_second(out)
        code, o, e = sb2.run("restore", "--from", str(dest))
        self.assertEqual(code, 0, o + e)
        db = sqlite3.connect(sb2.smem / "smem.db")
        self.addCleanup(db.close)
        self.assertEqual([r[0] for r in db.execute("select v from t")], ["walrow"])
        self.assertEqual((sb2.smem / "spool/1.json").read_bytes(), spool_bytes)
        self.assertEqual(json.loads((sb2.smem / "config.json").read_text())["home"], str(sb2.home))
        self.assertFalse((sb2.smem / "sessions").exists())
        sb2.link_tool("lsof") if not (sb2.bin / "lsof").exists() else None
        holder = sqlite3.connect(sb2.smem / "smem.db")
        holder.execute("create table if not exists keep(x)")
        self.addCleanup(holder.close)
        code, o, e = sb2.run("restore", "--from", str(dest))
        self.assertEqual(code, 1, o + e)
        self.assertIn("smem.db", e)

    def test_export_restore_appended_and_truncated_files(self):
        def setup(sb):
            (sb.claude / "projects/p").mkdir(parents=True)
            (sb.claude / "projects/p/s.jsonl").write_bytes(b"line1\nline2\n")
            (sb.claude / "history.jsonl").write_bytes(b"0123456789")
            (sb.hermes / "sessions").mkdir()
            (sb.hermes / "sessions/x.json").write_text("{}")
            (sb.hermes / "memories").mkdir()
            (sb.hermes / "memories/m.md").write_text("m")

        def after_fstat(path):
            if str(path).endswith("s.jsonl"):
                with open(path, "ab") as f:
                    f.write(b"appended\n")
            if str(path).endswith("history.jsonl"):
                os.truncate(path, 5)

        def before_open(path):
            if str(path).endswith("sessions/x.json"):
                os.unlink(path)

        sb1 = Sandbox(self)
        sb1.gpg_stub()
        setup(sb1)
        with mock.patch.object(sb1.mod, "_after_fstat", after_fstat), mock.patch.object(sb1.mod, "_before_open", before_open):
            out = sb1.home / "b.gpg"
            self.assertEqual(sb1.run("export", "--out", str(out))[0], 0)
        sb2, dest = self._into_second(out)
        code, o, e = sb2.run("restore", "--from", str(dest))
        self.assertEqual(code, 0, o + e)
        self.assertEqual((sb2.claude / "projects/p/s.jsonl").read_bytes(), b"line1\nline2\n")
        self.assertEqual((sb2.claude / "history.jsonl").read_bytes(), b"01234")
        self.assertIn("skipped (vanished during export) sessions/x.json", o)
        members = _read_bundle(dest)
        meta = _bundle_json(members)
        seq = next(e["seq"] for e in meta["entries"] if e["path"] == "hermes/memories/m.md")
        tampered = sb2.home / "t.gpg"
        with tarfile.open(tampered, "w") as tar:
            for name, data in members:
                if name == f"digests/{seq}.json":
                    d = json.loads(data)
                    d["sha256"] = "0" * 64
                    data = json.dumps(d).encode()
                _tar_bytes(tar, name, data)
        Path(f"{tampered}.sha256").write_text(f"{hashlib.sha256(tampered.read_bytes()).hexdigest()}  t.gpg\n")
        (sb2.hermes / "memories").mkdir(exist_ok=True)
        (sb2.hermes / "memories/m.md").write_text("dest")
        (sb2.claude / "history.jsonl").unlink()
        code, o, e = sb2.run("restore", "--from", str(tampered))
        self.assertEqual(code, 2, o + e)
        self.assertEqual((sb2.hermes / "memories/m.md").read_text(), "dest")
        self.assertEqual((sb2.claude / "history.jsonl").read_bytes(), b"01234")


def _load_hygiene(name="hygiene_for_state_tests"):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / "hermes-hygiene.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class HygieneIntegrationTest(unittest.TestCase):
    def test_audit_script_never_sends(self):
        sb = Sandbox(self)
        log = sb.home / "hermes-argv.log"
        sb.stub("hermes", f'echo "$@" >> {log}\necho "hermes 1"')
        code, _out, _err = sb.run("audit")
        self.assertIn(code, (0, 1))
        calls = log.read_text().split("\n") if log.exists() else []
        self.assertTrue(all(c.strip() in ("", "--version") for c in calls), calls)
        source = _SCRIPT.read_text()
        self.assertNotIn("_alert_relay", source)
        self.assertNotRegex(source, r"[\"']send[\"']")

    def test_hygiene_main_includes_state_line(self):
        hyg = _load_hygiene()
        quiet = {n: (lambda *a, **k: None) for n in (
            "prune_checkpoints", "prune_archived_messages", "optimize_sessions", "checkpoint_wal",
            "prune_stale_files", "prune_remotion_bundles", "doctor_issues")}
        out = io.StringIO()
        with (
            mock.patch.multiple(hyg, **quiet),
            mock.patch.object(hyg, "state_audit", lambda: "state: 1 unclassified: x"),
            mock.patch.object(sys, "argv", ["hygiene"]),
            contextlib.redirect_stdout(out),
        ):
            self.assertEqual(hyg.main(), 0)
        self.assertIn("state: 1 unclassified: x", out.getvalue())

    def test_dry_run_output_unchanged(self):
        hyg = _load_hygiene()
        with tempfile.TemporaryDirectory() as tmp:
            roots = []
            for i in range(2):
                d = Path(tmp) / f"root{i}"
                d.mkdir()
                roots.append((d, False))
            scratch = Path(tmp) / "scratch"
            scratch.mkdir()
            out = io.StringIO()
            with (
                mock.patch.object(hyg, "STALE_ROOTS", roots),
                mock.patch.object(hyg, "SCRATCH_DIR", scratch),
                mock.patch.object(subprocess, "run", side_effect=AssertionError("subprocess started")),
                mock.patch.object(sys, "argv", ["hygiene", "--dry-run"]),
                contextlib.redirect_stdout(out),
            ):
                self.assertEqual(hyg.main(), 0)
        self.assertEqual(
            out.getvalue().splitlines(),
            ["prune_stale_files: None", "prune_remotion_bundles: None"],
        )


class InstallWiringTest(unittest.TestCase):
    def test_setup_installs_state_script_and_manifest(self):
        text = (_ROOT / "devbox" / "setup-hermes.sh").read_text()
        block = re.search(r"COMMON_SCRIPTS=\(\n(.*?)\n\)", text, re.DOTALL).group(1).split()
        self.assertIn("hermes-state.py", block)
        self.assertIn(
            'cp "$REPO_DIR/config/state-manifest.yaml" "$HERMES_HOME/scripts/state-manifest.yaml"', text
        )
        self.assertLess(text.index("done\n", text.index("COMMON_SCRIPTS[@]")), text.index("state-manifest.yaml"))

    def test_gitignore_covers_export_outputs(self):
        lines = (_ROOT / ".gitignore").read_text().splitlines()
        for pattern in ("*.gpg", "*.sha256", "*.gpg.lock", "*.tar.gz", "*.tar.gz.lock", "*.partial"):
            self.assertIn(pattern, lines)


class ReadmeTest(unittest.TestCase):
    def _section(self):
        text = (_ROOT / "README.md").read_text()
        heading = re.search(r"^## .*new host.*$", text, re.MULTILINE | re.IGNORECASE)
        self.assertIsNotNone(heading, "no section heading containing 'new host'")
        rest = text[heading.end():]
        nxt = re.search(r"^## ", rest, re.MULTILINE)
        return text, rest[: nxt.start()] if nxt else rest

    def test_readme_has_new_host_section(self):
        text, sec = self._section()
        for word in ("export", "restore", "audit", "--include-secrets", "lsof", "gnupg",
                     "hermes plugins install", "venv/bin/python", "TELEGRAM_BOT_TOKEN",
                     "~/.smem", "config-overrides.yaml", "hermes-state.py"):
            self.assertIn(word, sec, word)
        pos = -1
        for marker in ("setup-hermes.sh", "systemctl --user stop hermes-gateway", "restore", "setup-hermes.sh", "audit"):
            found = sec.find(marker, pos + 1)
            self.assertNotEqual(found, -1, f"{marker!r} missing after offset {pos}")
            pos = found
        low = sec.lower()
        for phrase in ("poll", "pasted secrets", "stop", "sessions", "manifest"):
            self.assertIn(phrase, low, phrase)
        self.assertIn("follow-up", low)
        self.assertNotRegex(sec, r"(?m)^\s*python3 ")
        self.assertIn("state-manifest.yaml", text.split("## ", 2)[1] if False else text[: text.index("## Install")])


if __name__ == "__main__":
    unittest.main()


def _skip_root(case):
    if os.geteuid() == 0:
        case.skipTest("root ignores directory modes")


def _chmod_back(case, path, mode=0o700):
    case.addCleanup(lambda: os.path.lexists(path) and os.chmod(path, mode))


class Fix1RestoreTest(RestoreBase):
    def _std(self, home=None):
        return Bundle(source_home=home or str(self.sb.home))

    def test_restore_dry_run_creates_no_temp_files(self):
        sb = self.sb
        sb.link_tool("lsof")
        old = "/Users/olduser"
        padded = b"abc\0\0" + b"\0" * 4096
        b = self._std(old)
        b.sqlite("hermes/state.db", _db_bytes(self.make_tmp(), "r"), cls="history")
        b.file("hermes/SOUL.md", "soul")
        b.dir("hermes/memories")
        b.file("hermes/config.yaml", f"h: {old}/x\n", cls="secret", mode=0o600)
        b.file("hermes/memories/big.bin", os.urandom(3 << 20))
        b.file("hermes/memories/shrunk.bin", padded)
        b.shrunk[b.seq("hermes/memories/shrunk.bin")] = 5
        b.write(self.F)
        names = ("TemporaryFile", "NamedTemporaryFile", "mkstemp", "SpooledTemporaryFile", "mkdtemp")
        private_tmp = sb.home / "private-tmp"
        private_tmp.mkdir()
        patches = [mock.patch.object(tempfile, n, side_effect=AssertionError(f"tempfile.{n}")) for n in names]
        patches += [
            mock.patch.dict(os.environ, {"TMPDIR": str(private_tmp)}),
            mock.patch.object(tempfile, "tempdir", str(private_tmp)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("would write memories/big.bin", out)
        self.assertIn("would write memories/shrunk.bin", out)
        self.assertEqual(os.listdir(private_tmp), [])
        for p in patches:
            p.stop()
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / "memories/shrunk.bin").read_bytes(), b"abc\0\0")
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("identical memories/shrunk.bin", out)

    def test_restore_dry_run_shrunk_digest_mismatch_still_detected(self):
        b = self._std()
        b.dir("hermes/memories")
        b.file("hermes/memories/shrunk.bin", b"abc" + b"\0" * 100)
        b.shrunk[b.seq("hermes/memories/shrunk.bin")] = 3
        b.tamper.add(b.seq("hermes/memories/shrunk.bin"))
        b.write(self.F)
        code, out, err = self.restore("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (digest mismatch) memories/shrunk.bin", out)

    def _clash_bundle(self, mode):
        b = self._std()
        b.dir("hermes/memories").file("hermes/memories/a.md", "new").file("hermes/SOUL.md", "soul")
        if mode == "tamper":
            b.tamper.add(b.seq("hermes/memories/a.md"))
        else:
            b.vanish.add(b.seq("hermes/memories/a.md"))
        b.write(self.F)

    def test_restore_clash_with_bad_digest_leaves_destination_in_place(self):
        sb = self.sb
        for kind in ("dir", "link"):
            for mode, line in (("tamper", "failed (digest mismatch) memories/a.md"), ("vanish", "skipped (vanished during export) memories/a.md")):
                with self.subTest(kind=kind, mode=mode):
                    shutil.rmtree(sb.hermes / "memories", ignore_errors=True)
                    victim = sb.hermes / "memories/a.md"
                    victim.parent.mkdir(parents=True)
                    if kind == "dir":
                        victim.mkdir()
                        (victim / "child").write_text("keep")
                    else:
                        (self.outside / "t").write_text("t")
                        victim.symlink_to(self.outside / "t")
                    self._clash_bundle(mode)
                    code, out, err = self.restore()
                    self.assertEqual(code, 2 if mode == "tamper" else 0, out + err)
                    self.assertIn(line, out)
                    self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
                    if kind == "dir":
                        self.assertTrue(victim.is_dir() and not victim.is_symlink())
                        self.assertEqual((victim / "child").read_text(), "keep")
                    else:
                        self.assertEqual(os.readlink(victim), str(self.outside / "t"))
                    self.assertEqual(self.backups(), [])
                    code, out, err = self.restore("--dry-run")
                    self.assertEqual(self.backups(), [])

    def test_restore_sqlite_identical_main_still_moves_stale_wal(self):
        sb = self.sb
        sb.link_tool("lsof")
        tmp = self.make_tmp()
        conn = _wal_db(tmp / "other.db", "stale")
        self.addCleanup(conn.close)
        stale = (tmp / "other.db-wal").read_bytes()
        same = _db_bytes(tmp, "same")
        self.put("hermes", "state.db", same)
        self.put("hermes", "state.db-wal", stale)
        b = self._std()
        b.sqlite("hermes/state.db", same, cls="history")
        b.write(self.F)
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertFalse((sb.hermes / "state.db-wal").exists())
        self.assertEqual(self.backup_path("state.db-wal").read_bytes(), stale)
        self.assertEqual((sb.hermes / "state.db").read_bytes(), same)

    def test_restore_short_write_is_completed(self):
        data = os.urandom(5000)
        b = self._std()
        b.dir("hermes/memories")
        b.file("hermes/memories/big.bin", data)
        b.write(self.F)
        real = os.write

        def short(fd, buf):
            buf = bytes(buf)
            return real(fd, buf[: len(buf) // 2]) if len(buf) > 1000 else real(fd, buf)

        with mock.patch.object(os, "write", short):
            code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((self.sb.hermes / "memories/big.bin").read_bytes(), data)

    def test_restore_entry_missing_class_or_bad_platform_refused_nothing_written(self):
        sb = self.sb
        for field, change in (("class", None), ("class", 5), ("platform", 7)):
            with self.subTest(field=field, change=change):
                b = self._std()
                b.dir("hermes/memories").file("hermes/memories/a.md", "a").file("hermes/SOUL.md", "soul")
                if change is None:
                    del b.entries[1][field]
                else:
                    b.entries[1][field] = change
                b.write(self.F)
                before = _listing(sb)
                code, out, err = self.restore(sub=True)
                self.assertEqual(code, 1, out + err)
                self.assertIn("bad entry", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(_listing(sb), before)
                self.assertEqual(self.backups(), [])

    def test_restore_readonly_dir_with_child_fails_per_entry_then_retries(self):
        _skip_root(self)
        sb = self.sb
        ro = sb.hermes / "memories" / "ro"
        _chmod_back(self, ro)

        def bundle(text, tamper=False):
            b = self._std()
            b.dir("hermes/memories").dir("hermes/memories/ro", mode=0o555).file("hermes/memories/ro/f", text).file("hermes/SOUL.md", "soul")
            if tamper:
                b.tamper.add(b.seq("hermes/memories/ro/f"))
            b.write(self.F)

        bundle("one", tamper=True)
        code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (digest mismatch) memories/ro/f", out)
        self.assertNotIn("bundle stream failed", out + err)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
        self.assertEqual(stat_mode(ro), 0o555)
        bundle("one")
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((ro / "f").read_text(), "one")
        self.assertEqual(stat_mode(ro), 0o555)
        bundle("two")
        code, out, err = self.restore()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((ro / "f").read_text(), "two")
        self.assertEqual(stat_mode(ro), 0o555)
        self.assertEqual(self.backup_path("memories/ro/f").read_text(), "one")

    def test_restore_special_swapped_between_kind_check_and_open(self):
        sb = self.sb
        target = sb.hermes / "memories/a.md"
        victim = self.outside / "a.md"
        victim.write_text("known")
        real = sb.mod.Restorer.current_kind
        for kind in ("fifo", "socket", "link"):
            with self.subTest(kind=kind):
                shutil.rmtree(sb.hermes / "memories", ignore_errors=True)
                self.put("hermes", "memories/a.md", "dest differs")
                b = self._std()
                b.dir("hermes/memories").file("hermes/memories/a.md", "a").file("hermes/SOUL.md", "soul")
                b.write(self.F)

                def swapping(restorer, plan, kind=kind):
                    seen = real(restorer, plan)
                    if plan.rel == "memories/a.md" and os.path.isfile(target):
                        os.unlink(target)
                        if kind == "fifo":
                            os.mkfifo(target)
                        elif kind == "socket":
                            self.bind_socket(target.parent, "a.md")
                        else:
                            os.symlink(victim, target)
                    return seen

                with mock.patch.object(sb.mod.Restorer, "current_kind", swapping):
                    code, out, err = self.run_thread("restore", "--from", str(self.F))
                self.assertEqual(code, 2, out + err)
                want = "changed during restore" if kind == "link" else f"unsupported type {kind}"
                self.assertIn(f"failed ({want}) memories/a.md", out)
                self.assertEqual((sb.hermes / "SOUL.md").read_text(), "soul")
                self.assertEqual(victim.read_text(), "known")
                self.assertEqual(self.backups(), [])


class Fix1ExportTest(ExportTestBase):
    def test_export_whatsapp_session_keys_never_carried(self):
        sb = self.sb
        self.base_tree()
        session = sb.hermes / "whatsapp" / "session"
        session.mkdir(parents=True)
        for name in ("creds.json", "identity-key-1.json", "app-state-sync-key-1.json"):
            (session / name).write_text("SENTINEL-WA")
        for flags in ((), ("--include-secrets",)):
            with self.subTest(flags=flags):
                for suffix in ("", ".sha256"):
                    Path(f"{self.out}{suffix}").unlink(missing_ok=True)
                code, _out, err = self.export(*flags)
                self.assertEqual(code, 0, err)
                self.assertNotIn(b"SENTINEL-WA", (sb.home / "gpg.stdin").read_bytes())
                paths = {e["path"] for e in _bundle_json(self.captured())["entries"]}
                self.assertFalse([p for p in paths if "whatsapp" in p], paths)

    def test_export_unreadable_carried_dir_fails_naming_path(self):
        _skip_root(self)
        sb = self.sb
        self.base_tree()
        locked = sb.hermes / "memories" / "locked"
        locked.mkdir()
        (locked / "x").write_text("x")
        os.chmod(locked, 0)
        _chmod_back(self, locked)
        code, out, err = self.export()
        self.assertEqual(code, 1, out + err)
        self.assertIn("memories/locked", err)
        self.assertIn("EACCES", err)
        for suffix in ("", ".partial", ".sha256"):
            self.assertFalse(os.path.lexists(f"{self.out}{suffix}"), suffix)
        self.assertEqual(sb.gpg_log(), [])

    def test_export_failure_after_rename_leaves_retryable_state(self):
        sb = self.sb
        self.base_tree()
        boom = OSError(errno.EIO, "boom")
        with mock.patch.object(sb.mod, "_write_sha256", side_effect=boom):
            code, out, err = self.export()
        self.assertNotEqual(code, 0)
        self.assertFalse(self.out.exists() and not os.path.lexists(f"{self.out}.sha256"), "bundle left without checksum")
        code, out, err = self.export()
        self.assertEqual(code, 0, out + err)
        want = hashlib.sha256(self.out.read_bytes()).hexdigest()
        self.assertIn(want, Path(f"{self.out}.sha256").read_text())

    def test_export_snapshots_sqlite_with_uri_special_characters(self):
        sb = self.sb
        self.base_tree()
        names = ["a#b.db", "c?d.db", "e%20f.db"]
        for n in names:
            conn = sqlite3.connect(sb.hermes / "memories" / n)
            conn.execute("create table t(v)")
            conn.execute("insert into t values (?)", (n,))
            conn.commit()
            conn.close()
        code, out, err = self.export()
        self.assertEqual(code, 0, out + err)
        members = dict(self.captured())
        for n in names:
            self.assertEqual(_db_values(members[f"hermes/memories/{n}"], self.tmpd), [n])


class Fix1FingerprintTest(unittest.TestCase):
    def test_unlistable_skills_subdir_nulls_set_with_warning(self):
        _skip_root(self)
        sb = Sandbox(self)
        skills = sb.hermes / "skills"
        (skills / "a").mkdir(parents=True)
        (skills / "a" / "SKILL.md").write_text("x")
        (skills / "b").mkdir()
        os.chmod(skills / "b", 0)
        _chmod_back(self, skills / "b")
        fp, _ = _audit_json(sb)
        self.assertIsNone(fp["skills"]["names"])
        self.assertIsNone(fp["skills"]["count"])
        self.assertTrue(any("skills" in w for w in fp["warnings"]), fp["warnings"])
        self.assertEqual(sb.run("audit")[0], 0)

    def test_wrong_shape_sources_null_the_sets_with_warnings(self):
        sb = Sandbox(self)
        (sb.home / ".claude.json").write_text("[]")
        (sb.claude / "settings.json").write_text("3")
        (sb.hermes / "cron").mkdir()
        (sb.hermes / "cron" / "jobs.json").write_text('{"nojobs": 1}')
        (sb.hermes / "config.yaml").write_text("")
        fp, _ = _audit_json(sb)
        for key in ("claude_mcp_servers", "claude_plugins", "cron_jobs", "mcp_servers", "model_aliases"):
            self.assertIsNone(fp[key], key)
        for needle in (".claude.json", "settings.json", "jobs.json", "config.yaml"):
            self.assertTrue(any(w.startswith(needle) for w in fp["warnings"]), (needle, fp["warnings"]))
        for bad in ('{"jobs": 3}', "[]", "null"):
            (sb.hermes / "cron" / "jobs.json").write_text(bad)
            fp, _ = _audit_json(sb)
            self.assertIsNone(fp["cron_jobs"], bad)
        (sb.hermes / "cron" / "jobs.json").write_text('{"jobs": [{"name": "j"}]}')
        fp, _ = _audit_json(sb)
        self.assertEqual(fp["cron_jobs"], ["j"])

    def test_unreadable_plugins_dir_does_not_crash_audit(self):
        _skip_root(self)
        sb = Sandbox(self)
        plugins = sb.hermes / "plugins"
        (plugins / "a").mkdir(parents=True)
        os.chmod(plugins, 0)
        _chmod_back(self, plugins)
        code, out, err = sb.run("audit", "--json")
        self.assertIn(code, (0, 1), out + err)
        fp = json.loads(out)
        self.assertIsNone(fp["hermes_plugins"]["installed"])
        self.assertTrue(any("plugins" in w for w in fp["warnings"]), fp["warnings"])

    def test_unreadable_root_does_not_crash_audit_and_names_path_on_export(self):
        _skip_root(self)
        sb = Sandbox(self)
        sb.gpg_stub()
        os.chmod(sb.claude, 0)
        _chmod_back(self, sb.claude)
        code, out, err = sb.run("audit", "--json")
        self.assertIn(code, (0, 1), out + err)
        self.assertTrue(any(".claude" in w for w in json.loads(out)["warnings"]))
        code, out, err = sb.run("export", "--out", str(sb.home / "b.gpg"))
        self.assertEqual(code, 2, out + err)
        self.assertIn(str(sb.claude), err)
        self.assertNotIn("internal error", err)


class Fix2RestoreTest(RestoreBase):
    def test_restore_dir_mode_failure_exits_nonzero_and_names_path(self):
        b = Bundle(source_home=str(self.sb.home))
        b.dir("hermes/memories", mode=0o750)
        b.file("hermes/memories/a.md", "a")
        b.write(self.F)
        target = str(self.sb.hermes / "memories")
        real = os.chmod

        def chmod(path, mode, *a, **kw):
            if os.path.realpath(path) == os.path.realpath(target) and mode == 0o750:
                raise PermissionError(errno.EACCES, "denied")
            return real(path, mode, *a, **kw)

        with mock.patch.object(os, "chmod", chmod):
            code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertIn("cannot set mode", err)
        self.assertIn(os.path.realpath(target), err)

    def test_restore_write_verification_failure_leaves_target_untouched(self):
        sb = self.sb
        b = Bundle(source_home=str(sb.home))
        b.dir("hermes/memories")
        b.file("hermes/memories/big.bin", os.urandom(5000))
        b.write(self.F)
        existing = self.put("hermes", "memories/big.bin", b"old contents")
        real = sb.mod._write_all

        def drop_last_byte(fd, data):
            return real(fd, bytes(data)[:-1])

        with mock.patch.object(sb.mod, "_write_all", drop_last_byte):
            code, out, err = self.restore()
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (write verification failed) memories/big.bin", out)
        self.assertEqual(existing.read_bytes(), b"old contents")
        self.assertEqual([n for n in os.listdir(existing.parent) if ".restore-" in n], [])


class Fix2ExportTest(ExportTestBase):
    def test_export_cleanup_failure_does_not_mask_original_error(self):
        sb = self.sb
        self.base_tree()
        boom = OSError(errno.EIO, "original boom")
        denied = PermissionError(errno.EACCES, "cleanup denied")
        with mock.patch.object(sb.mod, "_write_sha256", side_effect=boom), \
                mock.patch.object(sb.mod, "_discard", side_effect=denied):
            code, out, err = self.export()
        self.assertNotEqual(code, 0, out + err)
        self.assertIn("original boom", err)
        self.assertIn("cleanup denied", err)


# --- explicit --unencrypted export and restore -------------------------------------------------

_WARN = "WARNING: unencrypted bundle may contain secrets and history; do not upload it; delete it and its .sha256 after transfer"


def _run(sb, *argv):
    """sb.run that reports an argparse exit as a code instead of raising."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = sb.mod.main(list(argv))
        except SystemExit as e:
            code = e.code
    return code, out.getvalue(), err.getvalue()


def _sidecar(path: Path, bad=False):
    digest = "1" * 64 if bad else hashlib.sha256(Path(path).read_bytes()).hexdigest()
    Path(f"{path}.sha256").write_text(f"{digest}  {Path(path).name}\n")


def _gz_members(path):
    members = []
    with tarfile.open(path, mode="r|gz") as tar:
        for info in tar:
            f = tar.extractfile(info)
            members.append((info.name, f.read() if f else b""))
    return members


def _raise(*_a, **_k):
    raise AssertionError("gpg touched")


def _sentinel_tree(sb):
    files = {
        sb.hermes / ".env": "K=SENTINEL-ENV",
        sb.hermes / "auth.json": "SENTINEL-AUTH",
        sb.hermes / "config.yaml": "k: SENTINEL-CFG",
        sb.hermes / "skills" / "foo" / "SKILL.md": "skill",
        sb.hermes / "whatsapp" / "session" / "creds.json": "SENTINEL-WA",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    zpath = sb.hermes / "backups" / "x.zip"
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.writestr(".env", "SENTINEL-ZIP")


class UnencryptedExportTest(ExportTestBase):
    def setUp(self):
        super().setUp()
        self.out = self.out_dir / "b.tar.gz"

    def _nogpg(self):
        (self.sb.bin / "gpg").unlink()

    def test_unencrypted_flag_in_both_help_texts(self):
        sb = self.sb
        with mock.patch.dict(os.environ, {"COLUMNS": "200"}):
            texts = {}
            for sub in ("export", "restore"):
                rc, out, _ = sb.run_sub(sub, "--help")
                self.assertEqual(rc, 0)
                texts[sub] = " ".join(out.split())
            rc, top, _ = sb.run_sub("--help")
            self.assertEqual(rc, 0)
            top = " ".join(top.split())
        for sub, text in texts.items():
            self.assertIn("--unencrypted", text, sub)
            self.assertNotIn("passphrase", text.lower(), sub)
        self.assertEqual(top.count("unless --unencrypted"), 2, top)
        self.assertIn("gpg", top)

    def test_unencrypted_export_without_gpg_matches_layout(self):
        sb = self.sb
        self.base_tree()
        plain1 = self.out_dir / "p1.tar.gz"
        code, out, err = sb.run("export", "--out", str(plain1), "--unencrypted")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sb.gpg_log(), [])
        self.assertEqual(plain1.read_bytes()[:2], b"\x1f\x8b")
        enc = self.out_dir / "e.gpg"
        self.assertEqual(sb.run("export", "--out", str(enc))[0], 0)
        want = self.captured()
        self._nogpg()
        plain2 = self.out_dir / "p2.tar.gz"
        with mock.patch.object(sb.mod, "_gpg_env", _raise):
            code, out, err = sb.run("export", "--out", str(plain2), "--unencrypted")
        self.assertEqual(code, 0, out + err)
        got = _gz_members(plain2)
        self.assertEqual([n for n, _ in got], [n for n, _ in want])
        self.assertEqual(set(_bundle_json(got)), set(_bundle_json(want)))

    def test_unencrypted_export_mode_0600_under_umask_022(self):
        self.base_tree()
        old = os.umask(0o022)
        self.addCleanup(os.umask, old)
        for i, mask in enumerate((0o022, 0o277)):
            os.umask(mask)
            out = self.out_dir / f"m{i}.tar.gz"
            code, o, e = self.export("--unencrypted", out=out)
            self.assertEqual(code, 0, o + e)
            self.assertEqual(out.stat().st_mode & 0o7777, 0o600, oct(mask))

    def test_unencrypted_export_stale_partial_link_not_followed(self):
        sb = self.sb
        self.base_tree()
        victim = sb.home / "victim"
        victim.write_bytes(b"known bytes")
        Path(f"{self.out}.partial").symlink_to(victim)
        code, out, err = sb.run_sub("export", "--out", str(self.out), "--unencrypted")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(victim.read_bytes(), b"known bytes")
        self.assertIn("note: removed stale", out)

    def test_unencrypted_export_partial_open_refusal_keeps_foreign_partial(self):
        sb = self.sb
        self.base_tree()
        partial = Path(f"{self.out}.partial")
        victim = sb.home / "victim"
        victim.write_bytes(b"known bytes")

        def plant_file(_root):
            partial.write_bytes(b"sentinel bytes")

        def plant_link(_root):
            partial.symlink_to(victim)

        for plant in (plant_file, plant_link):
            with mock.patch.object(sb.mod, "sweep_staging", plant):
                code, out, err = self.export("--unencrypted")
            self.assertEqual(code, 1, out + err)
            self.assertIn(str(partial), err)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("internal error", err)
            for suffix in ("", ".sha256"):
                self.assertFalse(os.path.lexists(f"{self.out}{suffix}"))
            self.assertEqual(victim.read_bytes(), b"known bytes")
            if plant is plant_file:
                self.assertEqual(partial.read_bytes(), b"sentinel bytes")
                partial.unlink()
            else:
                self.assertTrue(partial.is_symlink())
        partial.unlink()
        self.assertEqual(self.export("--unencrypted")[0], 0)

    def test_unencrypted_sha256_written_for_final_bytes(self):
        self.base_tree()
        code, o, e = self.export("--unencrypted")
        self.assertEqual(code, 0, o + e)
        sha = (self.out_dir / "b.tar.gz.sha256").read_text()
        self.assertEqual(sha, f"{hashlib.sha256(self.out.read_bytes()).hexdigest()}  b.tar.gz\n")

    def test_unencrypted_export_refuses_existing_out(self):
        self.base_tree()
        self.assertEqual(self.export("--unencrypted")[0], 0)
        before = (self.out.read_bytes(), (self.out_dir / "b.tar.gz.sha256").read_bytes())
        code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 1, out + err)
        self.assertEqual((self.out.read_bytes(), (self.out_dir / "b.tar.gz.sha256").read_bytes()), before)

    def test_unencrypted_export_failure_leaves_nothing_and_retries(self):
        sb = self.sb
        self.base_tree()
        opened = []
        real_fdopen = os.fdopen

        def spy(*a, **k):
            f = real_fdopen(*a, **k)
            opened.append(f)
            return f

        def clean():
            for suffix in ("", ".partial", ".sha256"):
                self.assertFalse(os.path.lexists(f"{self.out}{suffix}"), suffix)

        with mock.patch.object(os, "fdopen", spy), \
                mock.patch.object(sb.mod, "_add_file", side_effect=OSError(errno.EIO, "boom")):
            code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 2, out + err)
        self.assertTrue(opened)
        self.assertTrue(all(f.closed for f in opened))
        clean()
        with mock.patch.object(sb.mod, "_write_sha256", side_effect=OSError(errno.EIO, "boom")):
            code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 2, out + err)
        clean()
        self.assertEqual(self.export("--unencrypted")[0], 0)

    def test_unencrypted_export_keyboard_interrupt_discards_partial(self):
        sb = self.sb
        self.base_tree()
        opened = []
        real_fdopen = os.fdopen

        def spy(*a, **k):
            f = real_fdopen(*a, **k)
            opened.append(f)
            return f

        with mock.patch.object(os, "fdopen", spy), \
                mock.patch.object(sb.mod, "_add_file", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            self.export("--unencrypted")
        self.assertTrue(opened)
        self.assertTrue(all(f.closed for f in opened))
        for suffix in ("", ".partial", ".sha256"):
            self.assertFalse(os.path.lexists(f"{self.out}{suffix}"), suffix)
        self.assertEqual(self.export("--unencrypted")[0], 0)

    def test_unencrypted_export_concurrent_same_out_refused(self):
        sb = self.sb
        self.base_tree()
        fd = os.open(f"{self.out}.lock", os.O_WRONLY | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        code, _out, err = sb.run_sub("export", "--out", str(self.out), "--unencrypted")
        self.assertEqual(code, 1, err)
        self.assertIn("already running", err)

    def test_unencrypted_export_secret_entries_follow_flag(self):
        sb = self.sb
        _sentinel_tree(sb)
        code, o, e = self.export("--unencrypted")
        self.assertEqual(code, 0, o + e)
        members = _gz_members(self.out)
        self.assertNotIn(b"SENTINEL-", b"".join(d for _, d in members))
        self.out.unlink()
        (self.out_dir / "b.tar.gz.sha256").unlink()
        code, o, e = self.export("--unencrypted", "--include-secrets")
        self.assertEqual(code, 0, o + e)
        members = _gz_members(self.out)
        blob = b"".join(d for _, d in members)
        for tag in (b"SENTINEL-ENV", b"SENTINEL-AUTH", b"SENTINEL-ZIP"):
            self.assertIn(tag, blob)
        self.assertNotIn(b"SENTINEL-WA", blob)

    def test_unencrypted_warning_once_and_only_with_flag(self):
        self.base_tree()
        code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[0], _WARN)
        self.assertEqual(out.count("WARNING: unencrypted"), 1)
        enc = self.out_dir / "e.gpg"
        code, out, err = self.export(out=enc)
        self.assertEqual(code, 0, err)
        self.assertNotIn("WARNING", out + err)

    def test_unencrypted_warning_on_refusals(self):
        sb = self.sb
        self.base_tree()
        sb.hermes.joinpath("zzz-unclassified").mkdir()
        code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 1, err)
        self.assertEqual(out.splitlines()[0], _WARN)
        sb.hermes.joinpath("zzz-unclassified").rmdir()
        self.assertEqual(self.export("--unencrypted")[0], 0)
        code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 1, err)
        self.assertEqual(out.splitlines()[0], _WARN)
        self.out.unlink()
        (self.out_dir / "b.tar.gz.sha256").unlink()
        Path(f"{self.out}.partial").write_bytes(b"junk")
        code, out, err = self.export("--unencrypted")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], _WARN)
        self.assertTrue(lines[1].startswith("note: removed stale"), lines)


class UnencryptedRestoreTest(RestoreBase):
    def setUp(self):
        super().setUp()
        self.F = self.sb.home / "bundles" / "b.tar.gz"

    def _nogpg(self):
        (self.sb.bin / "gpg").unlink()

    def _b(self, **kw):
        b = Bundle(source_home=str(self.sb.home), **kw)
        b.dir("hermes/memories").file("hermes/memories/a.md", "a-bundle").file("hermes/memories/b.md", "b-bundle")
        b.file("hermes/SOUL.md", "soul")
        return b

    def r(self, *extra, sub=False):
        if sub:
            return self.sb.run_sub("restore", "--from", str(self.F), "--unencrypted", *extra)
        return _run(self.sb, "restore", "--from", str(self.F), "--unencrypted", *extra)

    def test_unencrypted_sha256_enforced_on_restore(self):
        sb = self.sb
        self._b().write(self.F, gz=True, bad_sha=True)
        before = _listing(sb)
        code, out, err = self.r()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(_listing(sb), before)
        self._b().write(self.F, gz=True, write_sha=False)
        Path(f"{self.F}.sha256").unlink(missing_ok=True)
        code, out, err = self.r()
        self.assertEqual(code, 1, out + err)
        self.assertEqual(_listing(sb), before)

    def test_restore_gpg_missing_with_bad_sidecar(self):
        self._b().write(self.F, bad_sha=True)
        self._nogpg()
        code, _out, err = _run(self.sb, "restore", "--from", str(self.F))
        self.assertEqual(code, 2, err)
        self.assertIn("sudo apt-get install gnupg", err)

    def test_restore_sniff_falls_through_on_missing_or_short_bundle(self):
        sb = self.sb
        short = sb.home / "bundles" / "short"
        short.write_bytes(b"\x1f")
        for target in (sb.home / "bundles" / "nope", short):
            code, out, err = _run(sb, "restore", "--from", str(target))
            self.assertEqual(code, 1, out + err)
            self.assertRegex(err, r"checksum|cannot read")
            self.assertEqual(sb.gpg_log(), [])
        self._nogpg()
        for target in (sb.home / "bundles" / "nope", short):
            code, out, err = _run(sb, "restore", "--from", str(target))
            self.assertEqual(code, 2, out + err)
            self.assertIn("sudo apt-get install gnupg", err)
        code, out, err = _run(sb, "restore", "--from", str(sb.home / "bundles" / "nope"), "--unencrypted")
        self.assertEqual(code, 1, out + err)
        for bad in ("Traceback", "internal error", "drop"):
            self.assertNotIn(bad, err)

    def test_restore_from_directory_exits_1_both_modes(self):
        sb = self.sb
        d = sb.home / "bundles" / "d"
        d.mkdir()
        _sidecar(d) if False else Path(f"{d}.sha256").write_text(f"{'0' * 64}  d\n")
        before = _listing(sb)
        for extra in ((), ("--unencrypted",)):
            code, out, err = _run(sb, "restore", "--from", str(d), *extra)
            self.assertEqual(code, 1, (extra, out, err))
            self.assertIn("cannot read", err)
            self.assertNotIn("internal error", err)
            self.assertEqual(_listing(sb), before)

    def test_unencrypted_restore_closes_descriptor_on_manifest_error(self):
        sb = self.sb
        self._b().write(self.F, gz=True)
        opened, closed = [], []
        real_open, real_close = os.open, os.close

        def spy_open(path, *a, **k):
            fd = real_open(path, *a, **k)
            if os.fspath(path) == str(self.F):
                opened.append(fd)
            return fd

        def spy_close(fd):
            closed.append(fd)
            return real_close(fd)

        before = len(os.listdir("/dev/fd"))
        with mock.patch.object(os, "open", spy_open), mock.patch.object(os, "close", spy_close):
            code, out, err = _run(sb, "--manifest", str(sb.home / "nowhere.yaml"), "restore",
                                  "--from", str(self.F), "--unencrypted")
        self.assertEqual(code, 2, out + err)
        self.assertIn("manifest error", err)
        self.assertEqual(len(opened), 1, opened)
        self.assertEqual(closed.count(opened[0]), 1, closed)
        self.assertEqual(len(os.listdir("/dev/fd")), before)

    def test_unencrypted_restore_short_bundle(self):
        sb = self.sb
        for data in (b"", b"\x1f"):
            self.F.write_bytes(data)
            before = _listing(sb)
            _sidecar(self.F, bad=True)
            code, out, err = self.r()
            self.assertEqual(code, 1, (data, out, err))
            self.assertIn("checksum", err)
            _sidecar(self.F)
            code, out, err = self.r()
            self.assertEqual(code, 2, (data, out, err))
            self.assertIn("bundle.json", err)
            for bad in ("drop", "gpg", "Traceback", "internal error"):
                self.assertNotIn(bad, err)
            self.assertEqual(_listing(sb), before)

    def test_unencrypted_roundtrip_without_gpg(self):
        sb1 = Sandbox(self)
        sb1.smem.mkdir()
        conn = _wal_db(sb1.smem / "smem.db")
        self.addCleanup(conn.close)
        (sb1.hermes / "memories").mkdir()
        (sb1.hermes / "memories" / "m.md").write_text("mem")
        (sb1.hermes / "config.yaml").write_text(f"h: {sb1.home}/x\n")
        (sb1.hermes / ".env").write_text("K=1\n")
        shared = Path(tempfile.mkdtemp(dir=sb1.home))
        out = shared / "b.tar.gz"
        with mock.patch.object(sb1.mod, "_gpg_env", _raise), mock.patch.object(sb1.mod, "_open_gpg", _raise):
            code, o, e = _run(sb1, "export", "--out", str(out), "--include-secrets", "--unencrypted")
        self.assertEqual(code, 0, o + e)
        sb2 = Sandbox(self)
        dest = sb2.home / "b.tar.gz"
        shutil.copy(out, dest)
        shutil.copy(f"{out}.sha256", f"{dest}.sha256")
        victim = sb2.home.parent / f"{sb2.home.name}-victim"
        victim.write_text("outside")
        self.addCleanup(lambda: victim.unlink(missing_ok=True))
        (sb2.hermes / "memories").mkdir()
        (sb2.hermes / "memories" / "m.md").symlink_to(victim)
        (sb2.hermes / "config.yaml").write_text("sentinel: 1\n")
        argv = ("restore", "--from", str(dest), "--unencrypted")
        with mock.patch.object(sb2.mod, "_gpg_env", _raise), mock.patch.object(sb2.mod, "_open_gpg", _raise):
            before = _listing(sb2)
            code, o, e = _run(sb2, *argv, "--dry-run")
            self.assertEqual(code, 0, o + e)
            self.assertEqual(_listing(sb2), before)
            code, o, e = _run(sb2, *argv)
        self.assertEqual(code, 0, o + e)
        self.assertEqual((sb2.hermes / "config.yaml").read_text(), f"h: {sb2.home}/x\n")
        self.assertEqual(victim.read_text(), "outside")
        (ts,) = os.listdir(sb2.hermes / "state-restore-backups")
        self.assertEqual((sb2.hermes / "state-restore-backups" / ts / "hermes" / "config.yaml").read_text(),
                         "sentinel: 1\n")
        db = sqlite3.connect(sb2.smem / "smem.db")
        self.addCleanup(db.close)
        self.assertEqual([r[0] for r in db.execute("select v from t")], ["walrow"])

    def test_unencrypted_restore_refuses_non_gzip(self):
        sb = self.sb
        stale = sb.hermes / "state-staging" / "old"
        stale.mkdir(parents=True)
        (stale / "x").write_text("x")
        blobs = {
            "tar": None,
            "lead8c": b"\x8c\x0d\x04\x09" + os.urandom(64),
            "armor": b"-----BEGIN PGP MESSAGE-----\n\nabc\n-----END PGP MESSAGE-----\n",
        }
        for name, data in blobs.items():
            if data is None:
                self._b().write(self.F)
            else:
                self.F.write_bytes(data)
            _sidecar(self.F)
            before = _listing(sb)
            for extra in (("--dry-run",), ()):
                code, out, err = self.r(*extra)
                self.assertEqual(code, 1, (name, extra, out, err))
                self.assertIn("--unencrypted", err)
                for bad in ("gzip", "Traceback", "internal error"):
                    self.assertNotIn(bad, err)
                self.assertEqual(sb.gpg_log(), [])
                self.assertEqual(_listing(sb), before)

    def test_restore_without_flag_refuses_gzip_bundle(self):
        sb = self.sb
        self._b().write(self.F, gz=True)
        before = _listing(sb)
        for stub in (True, False):
            if not stub:
                self._nogpg()
            for extra in (("--dry-run",), ()):
                code, out, err = _run(sb, "restore", "--from", str(self.F), *extra)
                self.assertEqual(code, 1, (stub, extra, out, err))
                self.assertIn("--unencrypted", err)
                self.assertEqual(sb.gpg_log(), [])
                self.assertEqual(_listing(sb), before)

    def test_mismatch_precedes_manifest_load(self):
        sb = self.sb
        missing = str(sb.home / "nowhere.yaml")
        self._b().write(self.F, gz=True)
        code, _out, err = _run(sb, "--manifest", missing, "restore", "--from", str(self.F))
        self.assertEqual(code, 1, err)
        self.assertIn("--unencrypted", err)
        self.assertNotIn("manifest error", err)
        self._b().write(self.F)
        code, _out, err = _run(sb, "--manifest", missing, "restore", "--from", str(self.F), "--unencrypted")
        self.assertEqual(code, 1, err)
        self.assertIn("--unencrypted", err)
        self.assertNotIn("manifest error", err)

    def test_unencrypted_restore_warning_first_line(self):
        self._b().write(self.F, gz=True)
        code, out, err = self.r()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines()[0], _WARN)
        self.assertEqual(out.count("WARNING: unencrypted"), 1)
        code, out, err = self.r("--dry-run")
        self.assertEqual(out.splitlines()[0], _WARN)
        self.assertEqual(out.count("WARNING: unencrypted"), 1)
        self._b().write(self.F)
        code, out, err = _run(self.sb, "restore", "--from", str(self.F))
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("WARNING", out + err)

    def test_unencrypted_warning_on_restore_mismatch(self):
        self._b().write(self.F)
        code, out, err = self.r()
        self.assertEqual(code, 1, err)
        self.assertEqual(out.splitlines()[0], _WARN)

    def test_unencrypted_restore_pass1_unreadable_exits_2(self):
        sb = self.sb
        self.assertFalse((sb.hermes / "state-staging").exists())
        before = _listing(sb)
        import gzip

        self.F.write_bytes(gzip.compress(b"not a tar" * 200))
        _sidecar(self.F)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("bundle.json", err)
        for bad in ("gpg", "Traceback"):
            self.assertNotIn(bad, err)
        self.assertEqual(_listing(sb), before)
        with tarfile.open(self.F, "w:gz") as tar:
            _tar_bytes(tar, "x", b"x")
        _sidecar(self.F)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("bundle.json", err)
        for bad in ("gpg", "Traceback"):
            self.assertNotIn(bad, err)
        self.assertEqual(_listing(sb), before)

    def test_unencrypted_restore_truncated_stream_stops(self):
        self.put("hermes", "memories/a.md", "dest-a")
        b = self._b()
        b.file("hermes/memories/c.bin", os.urandom(300_000))
        b.write(self.F, gz=True)
        full = self.F.read_bytes()
        self.F.write_bytes(full[: len(full) - 100_000])
        _sidecar(self.F)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("bundle stream failed (ReadError)", err)
        self.assertRegex(out, r"applied: .*memories/a\.md")
        self.assertEqual(self.backup_path("memories/a.md").read_text(), "dest-a")
        self.F.write_bytes(full)
        _sidecar(self.F)
        code, out, err = self.r()
        self.assertEqual(code, 0, out + err)

    def _trailing(self, files):
        b = Bundle(source_home=str(self.sb.home))
        if files:
            b.file("hermes/SOUL.md", "soul")
        b.extra_members.append(("hermes/../../y", b"y"))
        b.write(self.F, gz=True)

    def test_unencrypted_restore_unexpected_member_exits_2(self):
        sb = self.sb
        self._trailing(False)
        before = _listing(sb)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("unexpected member hermes/../../y", err)
        self.assertIn("applied: (none)", out)
        self.assertEqual(_listing(sb), before)
        code, out, err = self.r("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (unexpected member", out)
        self.assertEqual(_listing(sb), before)
        self._trailing(True)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("unexpected member hermes/../../y", err)
        code, out, err = self.r("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (unexpected member", out)
        self.assertFalse((sb.home / "y").exists())
        self.assertFalse((sb.home.parent / "y").exists())

    def _tampered(self):
        b = self._b()
        b.tamper.add(b.seq("hermes/memories/a.md"))
        b.write(self.F, gz=True)

    def test_unencrypted_restore_digest_mismatch_fails_entry(self):
        sb = self.sb
        self.put("hermes", "memories/a.md", "dest-a")
        self._tampered()
        before = _listing(sb)
        code, out, err = self.r("--dry-run")
        self.assertEqual(code, 2, out + err)
        self.assertIn("would fail (digest mismatch) memories/a.md", out)
        self.assertEqual(_listing(sb), before)
        code, out, err = self.r()
        self.assertEqual(code, 2, out + err)
        self.assertIn("failed (digest mismatch) memories/a.md", out)
        self.assertEqual((sb.hermes / "memories/a.md").read_text(), "dest-a")
        self.assertEqual((sb.hermes / "memories/b.md").read_text(), "b-bundle")

    def test_unencrypted_restore_bundle_swapped_after_plan(self):
        sb = self.sb
        b = Bundle(source_home=str(sb.home))
        b.file("hermes/SOUL.md", "original")
        b.write(self.F, gz=True)
        other = sb.home / "bundles" / "other.tar.gz"
        o = Bundle(source_home=str(sb.home))
        o.file("hermes/SOUL.md", "other")
        o.write(other, gz=True)

        def swap():
            os.replace(other, self.F)
            os.replace(f"{other}.sha256", f"{self.F}.sha256")

        self._nogpg()
        with mock.patch.object(sb.mod, "_gpg_env", _raise), mock.patch.object(sb.mod, "_open_gpg", _raise), \
                mock.patch.object(sb.mod, "_after_plan", swap):
            code, out, err = self.r()
        self.assertEqual(code, 0, out + err)
        self.assertEqual((sb.hermes / "SOUL.md").read_text(), "original")

    def test_unencrypted_restore_never_builds_gpg_env(self):
        sb = self.sb
        self._nogpg()
        self._b().write(self.F, gz=True)
        other = sb.home / "bundles" / "other.tar.gz"
        o = Bundle(source_home=str(sb.home))
        o.file("hermes/SOUL.md", "other")
        o.write(other, gz=True)

        def swap():
            os.replace(other, self.F)
            os.replace(f"{other}.sha256", f"{self.F}.sha256")

        with mock.patch.object(sb.mod, "_gpg_env", _raise), mock.patch.object(sb.mod, "_open_gpg", _raise):
            self.assertEqual(self.r("--dry-run")[0], 0)
            self.assertEqual(self.r()[0], 0)
            with mock.patch.object(sb.mod, "_after_plan", swap):
                code, out, err = self.r()
            self.assertEqual(code, 0, out + err)

    def test_unencrypted_restore_exit_3_and_gateway_guard(self):
        sb = self.sb
        b = Bundle(source_home=str(sb.home))
        b.file("hermes/SOUL.md", "soul")
        b.write(self.F, gz=True)
        pid_file = sb.hermes / "gateway.pid"
        pid_file.write_text(json.dumps({"pid": os.getpid(), "kind": "hermes-gateway", "argv": [],
                                        "hermes_home": str(sb.hermes), "start_time": 0}))
        code, out, err = self.r(sub=True)
        self.assertEqual(code, 1, out + err)
        self.assertFalse((sb.hermes / "SOUL.md").exists())
        pid_file.unlink()
        (sb.hermes / "zzz-unclassified").mkdir()
        code, out, err = self.r()
        self.assertEqual(code, 3, out + err)
        self.assertIn("hermes/zzz-unclassified", out)

    def test_gpg_pass2_drain_oserror_maps_to_stream_failed(self):
        sb = self.sb
        b = Bundle(source_home=str(sb.home))
        b.file("hermes/SOUL.md", "soul")
        b.write(self.F)
        procs = []
        real = sb.mod._open_gpg

        class Drain:
            def __init__(self, f):
                self.f = f

            def read(self, n=-1):
                if n is None or n < 0:
                    raise OSError(errno.EIO, "drain boom")
                return self.f.read(n)

            def __getattr__(self, k):
                return getattr(self.f, k)

        def wrapped(gpg, bundle, stderr):
            proc = real(gpg, bundle, stderr)
            if stderr is None:
                proc.stdout = Drain(proc.stdout)
                procs.append(proc)
            return proc

        with mock.patch.object(sb.mod, "_open_gpg", wrapped):
            code, out, err = _run(sb, "restore", "--from", str(self.F))
        self.assertEqual(code, 2, out + err)
        self.assertIn("bundle stream failed (OSError)", err)
        self.assertNotIn("internal error", err)
        (proc,) = procs
        self.assertIsNotNone(proc.poll())

    def _run_spied(self):
        """Run the flagged restore recording its closefd=False wrappers and the bundle fd's open and close."""
        import builtins

        wrappers, opened, closed = [], [], []
        real_open, real_close, real_builtin = os.open, os.close, builtins.open

        def spy_open(path, *a, **k):
            fd = real_open(path, *a, **k)
            if os.fspath(path) == str(self.F):
                opened.append(fd)
            return fd

        def spy_close(fd):
            closed.append(fd)
            return real_close(fd)

        def spy_builtin(*a, **k):
            f = real_builtin(*a, **k)
            if k.get("closefd") is False:
                wrappers.append(f)
            return f

        with mock.patch.object(os, "open", spy_open), mock.patch.object(os, "close", spy_close), \
                mock.patch.object(builtins, "open", spy_builtin):
            result = self.r()
        return result, wrappers, opened, closed

    def test_unencrypted_restore_wrapper_closed_on_error(self):

        def truncated():
            b = self._b()
            b.file("hermes/memories/c.bin", os.urandom(300_000))
            b.write(self.F, gz=True)
            full = self.F.read_bytes()
            self.F.write_bytes(full[: len(full) - 100_000])
            _sidecar(self.F)

        scenarios = {"truncated": truncated, "trailing": lambda: self._trailing(True), "tampered": self._tampered}
        for name, build in scenarios.items():
            with self.subTest(name):
                build()
                (code, out, err), wrappers, opened, closed = self._run_spied()
                self.assertEqual(code, 2, (name, out, err))
                self.assertTrue(wrappers, name)
                self.assertTrue(all(w.closed for w in wrappers), name)
                self.assertEqual(len(opened), 1, name)
                self.assertEqual(closed.count(opened[0]), 1, name)


class UnencryptedWarningSecretsTest(unittest.TestCase):
    def test_unencrypted_warning_no_secret_values(self):
        sb1 = Sandbox(self)
        _sentinel_tree(sb1)
        out_dir = Path(tempfile.mkdtemp(dir=sb1.home))
        bundle = out_dir / "b.tar.gz"
        streams = []
        code, o, e = _run(sb1, "export", "--out", str(bundle), "--unencrypted", "--include-secrets")
        streams += [o, e]
        self.assertEqual(code, 0, o + e)
        sb2 = Sandbox(self)
        dest = sb2.home / "b.tar.gz"
        shutil.copy(bundle, dest)
        shutil.copy(f"{bundle}.sha256", f"{dest}.sha256")
        for extra in (("--dry-run",), ()):
            code, o, e = _run(sb2, "restore", "--from", str(dest), "--unencrypted", *extra)
            streams += [o, e]
            self.assertEqual(code, 0, o + e)
        self.assertNotIn("SENTINEL-", "".join(streams))


class UnencryptedDocsTest(unittest.TestCase):
    def test_readme_unencrypted_gnupg_line_negated(self):
        _text, sec = ReadmeTest._section(self)
        lines = [ln for ln in sec.splitlines() if "--unencrypted" in ln and "gnupg" in ln]
        self.assertEqual(len(lines), 1, lines)
        self.assertRegex(lines[0], r"\b(not|no)\b")

    def test_readme_unencrypted_cleanup_mentions_partial_and_no_gnupg(self):
        _text, sec = ReadmeTest._section(self)
        for word in ("export --unencrypted", "restore --unencrypted", ".tar.gz", ".sha256", ".partial",
                     "do not upload", "delete", "outside", "checkout"):
            self.assertIn(word, sec, word)
        self.assertLess(sec.index("hermes-state.gpg"), sec.index("--unencrypted"))

    def test_gitignore_covers_plaintext_partial(self):
        import fnmatch

        lines = (_ROOT / ".gitignore").read_text().splitlines()
        for pattern in ("*.tar.gz", "*.tar.gz.lock", "*.partial"):
            self.assertIn(pattern, lines)
        proc = subprocess.run(["git", "-C", str(_ROOT), "ls-files"], capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            self.skipTest("not a git checkout")
        tracked = [Path(p).name for p in proc.stdout.splitlines()]
        for pattern in ("*.tar.gz", "*.tar.gz.lock", "*.partial"):
            self.assertEqual([t for t in tracked if fnmatch.fnmatch(t, pattern)], [], pattern)
