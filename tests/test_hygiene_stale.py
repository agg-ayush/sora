"""hermes-hygiene removes only cache/temp entries untouched for the stale window."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("hygiene_under_test", _ROOT / "scripts" / "hermes-hygiene.py")
assert _spec and _spec.loader
hygiene = importlib.util.module_from_spec(_spec)
sys.modules["hygiene_under_test"] = hygiene
_spec.loader.exec_module(hygiene)

DAY = 86400


def _touch(path: Path, age_days: float, now: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x" * 1024)
    t = now - age_days * DAY
    os.utime(path, (t, t))


def _age_dir(path: Path, age_days: float, now: float) -> None:
    t = now - age_days * DAY
    os.utime(path, (t, t))


class PruneStaleFilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "cache"
        self.root.mkdir()
        self.now = time.time()

    def test_old_entries_removed_recent_kept(self):
        _touch(self.root / "old.bin", 10, self.now)
        _touch(self.root / "new.bin", 1, self.now)
        result = hygiene.prune_stale_files([(self.root, False)], days=7, now=self.now)
        self.assertFalse((self.root / "old.bin").exists())
        self.assertTrue((self.root / "new.bin").exists())
        self.assertIn("removed 1 entries", result)

    def test_dir_with_any_recent_file_is_kept(self):
        d = self.root / "profile"
        _touch(d / "stale.txt", 30, self.now)
        _touch(d / "nested" / "fresh.txt", 2, self.now)
        _age_dir(d / "nested", 30, self.now)
        _age_dir(d, 30, self.now)
        hygiene.prune_stale_files([(self.root, False)], days=7, now=self.now)
        self.assertTrue((d / "stale.txt").exists())

    def test_fully_stale_dir_removed(self):
        d = self.root / "old-profile"
        _touch(d / "a" / "b.txt", 20, self.now)
        _age_dir(d / "a", 20, self.now)
        _age_dir(d, 20, self.now)
        hygiene.prune_stale_files([(self.root, False)], days=7, now=self.now)
        self.assertFalse(d.exists())

    def test_dry_run_deletes_nothing(self):
        _touch(self.root / "old.bin", 10, self.now)
        result = hygiene.prune_stale_files([(self.root, False)], days=7, now=self.now, dry_run=True)
        self.assertTrue((self.root / "old.bin").exists())
        self.assertIn("removed 1 entries", result)

    def test_symlink_target_outside_root_is_untouched(self):
        outside = Path(self._tmp.name) / "outside"
        _touch(outside / "keep.txt", 30, self.now)
        _age_dir(outside, 30, self.now)
        link = self.root / "link"
        link.symlink_to(outside)
        t = self.now - 30 * DAY
        os.utime(link, (t, t), follow_symlinks=False)
        hygiene.prune_stale_files([(self.root, False)], days=7, now=self.now)
        self.assertFalse(link.is_symlink())
        self.assertTrue((outside / "keep.txt").exists())

    def test_missing_root_is_ignored(self):
        self.assertIsNone(hygiene.prune_stale_files([(self.root / "nope", False)], days=7, now=self.now))


HOUR = 3600


class PruneRemotionBundlesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.scratch = Path(self._tmp.name) / "scratch"
        self.scratch.mkdir()
        self.now = time.time()

    def _bundle(self, name: str, age_hours: float) -> Path:
        d = self.scratch / name
        (d / "static").mkdir(parents=True)
        (d / "index.html").write_text("x" * 1024)
        t = self.now - age_hours * HOUR
        for p in (d / "static", d / "index.html", d):
            os.utime(p, (t, t))
        return d

    def _prune(self, **kw):
        kw.setdefault("held_open", lambda _p: False)
        return hygiene.prune_remotion_bundles(self.scratch, now=self.now, **kw)

    def test_old_bundle_removed_recent_kept(self):
        old = self._bundle("remotion-webpack-bundle-OLD123", 3)
        new = self._bundle("remotion-webpack-bundle-NEW456", 1)
        result = self._prune()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())
        self.assertIn("removed 1 dirs", result)

    def test_recent_file_inside_old_dir_keeps_it(self):
        d = self._bundle("remotion-webpack-bundle-BUSY", 5)
        fresh = d / "static" / "fresh.js"
        fresh.write_text("x")
        os.utime(fresh, (self.now - 600, self.now - 600))
        self._prune()
        self.assertTrue(d.exists())

    def test_held_open_bundle_is_kept(self):
        d = self._bundle("remotion-webpack-bundle-HELD", 10)
        self.assertIsNone(self._prune(held_open=lambda _p: True))
        self.assertTrue(d.exists())

    def test_real_lsof_detects_open_file(self):
        if not shutil.which("lsof"):
            self.skipTest("lsof not installed")
        d = self._bundle("remotion-webpack-bundle-LSOF", 10)
        self.assertFalse(hygiene._held_open(d))
        with open(d / "index.html") as fh:  # noqa: F841 - held open on purpose
            self.assertTrue(hygiene._held_open(d))

    def test_other_names_untouched_even_when_old(self):
        other = self._bundle("some-other-cache", 100)
        near = self._bundle("remotion-bundle-xyz", 100)
        self.assertIsNone(self._prune())
        self.assertTrue(other.exists() and near.exists())

    def test_symlink_and_plain_file_with_prefix_untouched(self):
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("k")
        link = self.scratch / "remotion-webpack-bundle-LINK"
        link.symlink_to(outside)
        t = self.now - 10 * HOUR
        os.utime(link, (t, t), follow_symlinks=False)
        plain = self.scratch / "remotion-webpack-bundle-FILE"
        plain.write_text("x")
        os.utime(plain, (t, t))
        self.assertIsNone(self._prune())
        self.assertTrue(link.is_symlink() and plain.exists() and (outside / "keep.txt").exists())

    def test_dry_run_deletes_nothing(self):
        d = self._bundle("remotion-webpack-bundle-DRY", 4)
        result = self._prune(dry_run=True)
        self.assertTrue(d.exists())
        self.assertIn("removed 1 dirs", result)

    def test_missing_scratch_dir_is_ignored(self):
        self.assertIsNone(hygiene.prune_remotion_bundles(self.scratch / "nope", now=self.now))

    def test_stale_rule_unchanged_for_non_bundle_entries(self):
        # A 3-hour-old ordinary dir is NOT removed by the bundle rule (the 7-day rule still governs it).
        d = self._bundle("remotion-v4-assets-abc", 3)
        self._prune()
        self.assertTrue(d.exists())


DIFFED_LITERAL = (
    "skills.names",
    "hermes_plugins.enabled",
    "hermes_plugins.disabled",
    "hermes_plugins.installed",
    "claude_plugins",
    "claude_plugins_legacy_config",
    "claude_plugins_k3_config",
    "claude_mcp_servers",
    "mcp_servers",
    "model_aliases",
    "cron_jobs",
    "memory_provider",
    "platforms",
)
_STUB = """\
import json, os, sys
raw = os.environ.get("STUB_RAW")
if raw is not None:
    sys.stdout.write(raw)
else:
    sys.stdout.write(open(os.environ["STUB_FP"]).read())
sys.stderr.write(os.environ.get("STUB_ERR", ""))
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""
_MARKER = "hermes-state-audit.off"
_BASELINE = "hermes-state-fingerprint.json"


def _fp(**sets):
    fp = {
        "schema": 1,
        "host": "h",
        "home": "/h",
        "platforms": ["mac"],
        "unclassified": [],
        "warnings": [],
        "skills": {"count": 1, "names": ["s0"]},
        "hermes_plugins": {"enabled": ["e"], "disabled": ["d"], "installed": ["i"]},
        "claude_plugins": ["c"],
        "claude_plugins_legacy_config": ["cs"],
        "claude_plugins_k3_config": ["k3"],
        "claude_mcp_servers": ["cm"],
        "mcp_servers": ["m"],
        "model_aliases": ["ma"],
        "cron_jobs": ["cj"],
        "memory_provider": "mp",
        "versions": {"hermes": "1", "claude": "1"},
    }
    for name, value in sets.items():
        _set_path(fp, name, value)
    return fp


def _set_path(fp, name, value):
    parts = name.split(".")
    for part in parts[:-1]:
        fp = fp[part]
    fp[parts[-1]] = value


def _get_path(fp, name):
    for part in name.split("."):
        fp = fp[part]
    return fp


class StateAuditStepTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.hh = self.root / "hh"
        self.state = self.root / "state"
        for d in (self.home, self.hh, self.state):
            d.mkdir()
        self.stub = self.root / "stub.py"
        self.stub.write_text(_STUB)
        self.fp_file = self.root / "fp.json"
        env = {
            "HOME": str(self.home),
            "HERMES_HOME": str(self.hh),
            "WATCHER_STATE_DIR": str(self.state),
            "STUB_FP": str(self.fp_file),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("STUB_RAW", "STUB_EXIT", "STUB_ERR"):
            os.environ.pop(key, None)
        sp = mock.patch.object(hygiene, "STATE_SCRIPT", self.stub)
        sp.start()
        self.addCleanup(sp.stop)
        self.baseline = self.state / _BASELINE

    def set_fp(self, fp):
        self.fp_file.write_text(json.dumps(fp))

    def call(self, fp=None):
        if fp is not None:
            self.set_fp(fp)
        return hygiene.state_audit()

    def main_returns_0(self):
        quiet = {n: (lambda *a, **k: None) for n in (
            "prune_checkpoints", "prune_archived_messages", "optimize_sessions", "checkpoint_wal",
            "prune_stale_files", "prune_remotion_bundles", "doctor_issues")}
        with (
            mock.patch.multiple(hygiene, **quiet),
            mock.patch.object(sys, "argv", ["hygiene"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return hygiene.main()

    def read_baseline(self):
        return json.loads(self.baseline.read_text())

    def test_state_step_sequence(self):
        fp = _fp()
        self.assertIsNone(self.call(fp))
        self.assertEqual(self.read_baseline()["skills"]["names"], ["s0"])
        self.assertIsNone(self.call())
        fp3 = _fp(**{"skills.names": ["s0", "newskill"]})
        self.assertIn("+newskill", self.call(fp3))
        self.assertIsNone(self.call())
        un = _fp(unclassified=[{"root": "hermes", "name": "weird-entry"}], **{"skills.names": ["s0", "newskill"]})
        self.assertIn("weird-entry", self.call(un))
        self.assertIn("weird-entry", self.call())
        self.baseline.unlink()
        os.environ["STUB_EXIT"] = "2"
        self.assertEqual(self.call(), "state audit failed (exit 2)")
        self.assertFalse(self.baseline.exists())

    def test_unclassified_line_is_capped(self):
        names = [{"root": "hermes", "name": f"n{i:02d}"} for i in range(13)]
        line = self.call(_fp(unclassified=names))
        self.assertTrue(line.startswith("state: 13 unclassified: hermes/n00"))
        self.assertIn("hermes/n09", line)
        self.assertNotIn("hermes/n10", line)
        self.assertTrue(line.endswith("+3 more"))

    def test_exit1_garbage_stdout_is_failure_no_baseline(self):
        for exit_code, raw in ((1, "Traceback (most recent call last):\nboom\n"), (0, "[]"), (1, '{"schema": 2}')):
            os.environ["STUB_EXIT"] = str(exit_code)
            os.environ["STUB_RAW"] = raw
            os.environ["STUB_ERR"] = "Traceback boom"
            self.assertEqual(self.call(), f"state audit failed (exit {exit_code})", raw)
            self.assertFalse(self.baseline.exists())

    def test_step_uses_hermes_home(self):
        del os.environ["WATCHER_STATE_DIR"]
        self.set_fp(_fp())
        stub = self.root / "echo_home.py"
        stub.write_text(
            "import os, sys\nopen(os.environ['STUB_FP'] + '.home', 'w').write(os.environ['HERMES_HOME'])\n"
            + _STUB
        )
        with mock.patch.object(hygiene, "STATE_SCRIPT", stub):
            self.assertIsNone(hygiene.state_audit())
        self.assertTrue((self.hh / "watcher-state" / _BASELINE).exists())
        self.assertEqual(Path(str(self.fp_file) + ".home").read_text(), str(self.hh))
        self.assertFalse((self.home / ".hermes").exists())

    def test_state_dir_matches_watermark_rule(self):
        sys.path.insert(0, str(_ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(_ROOT / "scripts"))
        import _watermark

        cwd = Path.cwd()
        cases = [
            ({"HERMES_HOME": ""}, self.home / ".hermes" / "watcher-state", ["WATCHER_STATE_DIR"]),
            ({}, self.state, []),
        ]
        for extra, expected, drop in cases:
            with mock.patch.dict(os.environ, extra):
                for key in drop:
                    os.environ.pop(key, None)
                self.assertEqual(_watermark._state_dir(), expected)
                before = set(os.listdir(cwd))
                self.assertIsNone(self.call(_fp()))
                self.assertTrue((expected / _BASELINE).exists())
                self.assertEqual(set(os.listdir(cwd)), before)
            shutil.rmtree(expected, ignore_errors=True)
            if expected == self.state:
                self.state.mkdir()

    def test_corrupt_or_wrong_shape_baseline_rebaselines(self):
        for content in (b'{"schema": 1, "skills', b"\xff\xfe", b"[]", b"null", b"42", b'{"schema": 2}',
                        b'{"schema": true}', b'{"schema": 1.0}'):
            self.baseline.write_bytes(content)
            fp = _fp()
            out = self.call(fp)
            self.assertIn("state baseline unreadable; re-baselined", out, content)
            self.assertNotIn("fingerprint changed", out)
            self.assertEqual(self.read_baseline(), fp)
            self.assertIsNone(self.call())
            self.assertEqual(self.main_returns_0(), 0)

    def test_every_diffed_set_reports_change(self):
        self.assertEqual(tuple(DIFFED_LITERAL), tuple(hygiene.DIFFED_SETS))
        for name in DIFFED_LITERAL:
            with self.subTest(name):
                base = _fp(**{n: ("a" if n == "memory_provider" else ["x"]) for n in DIFFED_LITERAL})
                self.baseline.write_text(json.dumps(base))
                new = json.loads(json.dumps(base))
                _set_path(new, name, "b" if name == "memory_provider" else ["x", "y"])
                out = self.call(new)
                body = out.split("state fingerprint changed: ", 1)[1]
                segments = body.split("; ")
                self.assertEqual(len(segments), 1, out)
                want = f"{name} +b -a" if name == "memory_provider" else f"{name} +y"
                self.assertEqual(segments[0], want)
                self.assertIsNone(self.call())
                self.assertEqual(_get_path(self.read_baseline(), name), _get_path(new, name))

    def test_legacy_isolated_plugin_baseline_field_is_preserved(self):
        baseline = _fp()
        del baseline["claude_plugins_legacy_config"]
        baseline["claude_plugins_seatbelt"] = ["cs"]
        self.baseline.write_text(json.dumps(baseline))
        self.assertIsNone(self.call(_fp()))
        self.assertEqual(self.read_baseline()["claude_plugins_legacy_config"], ["cs"])

    def test_inner_wrong_shape_baseline_rebaselines(self):
        self.assertEqual(len(set(DIFFED_LITERAL)), 13)
        self.assertEqual(set(DIFFED_LITERAL), set(hygiene.DIFFED_SETS))
        self.assertEqual(len(hygiene.DIFFED_SETS), 13)
        hp = ["hermes_plugins.enabled", "hermes_plugins.disabled", "hermes_plugins.installed"]
        cases = [
            ({"skills": []}, ["skills.names"]),
            ({"skills": {"names": 5}}, ["skills.names"]),
            ({"skills": {"names": ["a", 5]}}, ["skills.names"]),
            ({"hermes_plugins": []}, hp),
            ({"hermes_plugins": {"enabled": "x"}}, ["hermes_plugins.enabled"]),
            ({"hermes_plugins": {"disabled": {"a": 1}}}, ["hermes_plugins.disabled"]),
            ({"hermes_plugins": {"installed": [1]}}, ["hermes_plugins.installed"]),
            ({"claude_plugins": {"a": True}}, ["claude_plugins"]),
            ({"claude_plugins_legacy_config": 5}, ["claude_plugins_legacy_config"]),
            ({"claude_plugins_k3_config": 5}, ["claude_plugins_k3_config"]),
            ({"claude_mcp_servers": [None]}, ["claude_mcp_servers"]),
            ({"mcp_servers": "a"}, ["mcp_servers"]),
            ({"model_aliases": {"fast": "x"}}, ["model_aliases"]),
            ({"cron_jobs": [1]}, ["cron_jobs"]),
            ({"platforms": "mac"}, ["platforms"]),
            ({"memory_provider": ["x"]}, ["memory_provider"]),
        ]
        self.assertEqual({t for _, tags in cases for t in tags}, set(DIFFED_LITERAL))
        for bad, tags in cases:
            with self.subTest(bad):
                base = {"schema": 1}
                for n in DIFFED_LITERAL:
                    if n.split(".")[0] not in bad:
                        _set_path(base, n, "old") if n == "memory_provider" else _set_path_deep(base, n, ["old"])
                base.update(bad)
                self.baseline.write_text(json.dumps(base))
                fp = _fp()
                self.assertEqual(self.call(fp), "state baseline unreadable; re-baselined")
                self.assertEqual(self.read_baseline(), fp)
                self.assertIsNone(self.call())
                self.assertEqual(self.main_returns_0(), 0)

    def test_missing_or_null_baseline_set_adopts_silently(self):
        stub = _fp(**{"mcp_servers": ["a", "b"], "skills.names": ["s1", "s2"], "memory_provider": "p"})
        full = json.loads(json.dumps(stub))
        no_mcp = json.loads(json.dumps(full))
        del no_mcp["mcp_servers"]
        null_mcp = {**full, "mcp_servers": None}
        no_names = {**full, "skills": {"count": 0}}
        null_prov = {**full, "memory_provider": None}
        for label, base in (("bare", {"schema": 1}), ("no mcp", no_mcp), ("null mcp", null_mcp),
                            ("no names", no_names), ("null provider", null_prov)):
            with self.subTest(label):
                self.baseline.write_text(json.dumps(base))
                self.assertIsNone(self.call(stub))
                saved = self.read_baseline()
                self.assertEqual(saved["mcp_servers"], ["a", "b"])
                self.assertEqual(saved["skills"]["names"], ["s1", "s2"])
                self.assertEqual(saved["memory_provider"], "p")
                out = self.call(_fp(**{"mcp_servers": ["a", "b", "c"], "skills.names": ["s1", "s2"], "memory_provider": "p"}))
                self.assertIn("mcp_servers +c", out)
                self.assertNotIn("+a", out)

    def test_missing_state_dir_is_created(self):
        del os.environ["WATCHER_STATE_DIR"]
        self.assertIsNone(self.call(_fp()))
        self.assertTrue((self.hh / "watcher-state" / _BASELINE).exists())
        self.assertEqual(self.main_returns_0(), 0)

    def _readonly(self, mode=0o500):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory modes")
        os.chmod(self.state, mode)
        self.addCleanup(os.chmod, self.state, 0o700)

    def test_read_only_state_dir_gives_line_no_raise(self):
        self.baseline.write_text(json.dumps(_fp()))
        old = self.baseline.read_bytes()
        self._readonly()
        fp = _fp(**{"skills.names": ["s0", "newskill"]})
        out = self.call(fp)
        self.assertIn("+newskill", out)
        self.assertIn("state baseline write failed", out)
        self.assertEqual(self.baseline.read_bytes(), old)
        self.assertEqual(os.listdir(self.state), [_BASELINE])
        self.assertEqual(self.call(), out)
        self.assertEqual(self.main_returns_0(), 0)

    def test_state_dir_is_regular_file(self):
        f = self.root / "afile"
        f.write_bytes(b"known")
        os.environ["WATCHER_STATE_DIR"] = str(f)
        self.set_fp(_fp())
        self.assertEqual(self.call(), "state baseline write failed")
        self.assertEqual(f.read_bytes(), b"known")
        self.assertEqual(sorted(os.listdir(self.root)), sorted(["afile", "fp.json", "stub.py", "home", "hh", "state"]))
        self.assertEqual(self.call(), "state baseline write failed")
        self.assertEqual(self.main_returns_0(), 0)

    def test_unreadable_baseline_unwritable_dir_single_line(self):
        self.baseline.write_text("[]")
        self._readonly()
        self.set_fp(_fp())
        self.assertEqual(self.call(), "state baseline unreadable; write failed")
        self.assertEqual(self.baseline.read_text(), "[]")
        self.assertEqual(os.listdir(self.state), [_BASELINE])
        self.assertEqual(self.call(), "state baseline unreadable; write failed")
        os.chmod(self.state, 0o700)
        self.assertEqual(self.call(), "state baseline unreadable; re-baselined")
        self.assertIsNone(self.call())

    def test_baseline_temp_name_is_unique(self):
        (self.state / "hermes-state-fingerprint.json.tmp").mkdir()
        (self.state / ".hermes-state-fingerprint.fixed.tmp").write_text("keep")
        self.assertIsNone(self.call(_fp()))
        self.assertTrue(self.baseline.exists())
        self.assertTrue((self.state / "hermes-state-fingerprint.json.tmp").is_dir())
        self.assertEqual((self.state / ".hermes-state-fingerprint.fixed.tmp").read_text(), "keep")
        tmps = [n for n in os.listdir(self.state) if n.endswith(".tmp")]
        self.assertEqual(sorted(tmps), [".hermes-state-fingerprint.fixed.tmp", "hermes-state-fingerprint.json.tmp"])
        self.baseline.unlink()
        with mock.patch.object(os, "replace", side_effect=OSError("boom")):
            self.assertEqual(self.call(), "state baseline write failed")
        tmps = [n for n in os.listdir(self.state) if n.endswith(".tmp")]
        self.assertEqual(sorted(tmps), [".hermes-state-fingerprint.fixed.tmp", "hermes-state-fingerprint.json.tmp"])

    def test_audit_timeout_gives_line_no_baseline(self):
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("x", 1)):
            self.assertEqual(hygiene.state_audit(), "state audit failed (exit timeout)")
            self.assertEqual(self.main_returns_0(), 0)
        self.assertFalse(self.baseline.exists())
        with mock.patch.object(subprocess, "run", side_effect=OSError("secret message")):
            out = hygiene.state_audit()
        self.assertEqual(out, "state audit failed (error OSError)")
        self.assertNotIn("secret message", out)

    def test_opt_out_marker_skips_step(self):
        self.set_fp(_fp())
        called = []
        real_run = subprocess.run
        spy_hits = []
        real_stat = os.stat
        stat_calls = []

        def run_spy(*a, **k):
            called.append(a)
            return real_run(*a, **k)

        def watch(owner, name, marker):
            real = getattr(owner, name)

            def wrapper(*a, **k):
                if a and os.fspath(a[0]) == marker:
                    spy_hits.append(name)
                return real(*a, **k)

            return mock.patch.object(owner, name, wrapper)

        def spies(marker):
            stack = contextlib.ExitStack()
            for owner, name in ((Path, "exists"), (Path, "is_file"), (os.path, "exists"),
                                (os.path, "isfile"), (os.path, "lexists")):
                stack.enter_context(watch(owner, name, marker))
            stack.enter_context(mock.patch.object(subprocess, "run", run_spy))
            return stack

        def check(expected, marker):
            self.assertEqual(hygiene.state_audit(), expected)
            self.assertEqual(spy_hits, [], f"marker checked with {spy_hits}")
            spy_hits.clear()

        marker = str(self.state / _MARKER)
        (self.state / _MARKER).write_text("")
        with spies(marker):
            check(None, marker)
            self.assertEqual(called, [])
            self.assertFalse(self.baseline.exists())
            (self.state / _MARKER).unlink()
            check(None, marker)
            self.assertTrue(self.baseline.exists())
        self.baseline.unlink()
        called.clear()

        def stat_patch(path, *a, **k):
            stat_calls.append(os.fspath(path))
            if os.fspath(path) == marker:
                raise PermissionError(13, "patched")
            return real_stat(path, *a, **k)

        with spies(marker), mock.patch.object(os, "stat", stat_patch):
            check("state audit failed (error PermissionError)", marker)
            self.assertIn(marker, stat_calls)
            self.assertEqual(self.main_returns_0(), 0)
        self.assertEqual(called, [])
        if os.geteuid() != 0:
            locked = self.root / "locked"
            (locked / "ws").mkdir(parents=True)
            os.chmod(locked, 0)
            self.addCleanup(os.chmod, locked, 0o700)
            os.environ["WATCHER_STATE_DIR"] = str(locked / "ws")
            marker_a = str(locked / "ws" / _MARKER)
            with spies(marker_a):
                check("state audit failed (error PermissionError)", marker_a)
            self.assertEqual(called, [])
        afile = self.root / "afile"
        afile.write_text("x")
        os.environ["WATCHER_STATE_DIR"] = str(afile)
        with spies(str(afile / _MARKER)):
            check("state baseline write failed", str(afile / _MARKER))

    def test_versions_and_warnings_only_change_is_silent(self):
        self.assertIsNone(self.call(_fp()))
        other = _fp(versions={"hermes": "2", "claude": "9"}, warnings=["w"], home="/other", **{"skills.count": 9})
        self.assertIsNone(self.call(other))

    def test_null_set_keeps_baseline(self):
        self.assertIsNone(self.call(_fp(mcp_servers=["a"])))
        self.assertIsNone(self.call(_fp(mcp_servers=None)))
        self.assertEqual(self.read_baseline()["mcp_servers"], ["a"])
        self.assertIsNone(self.call(_fp(mcp_servers=["a"])))

    def test_fingerprint_change_line_capped(self):
        base = _fp(**{"skills.names": [], "cron_jobs": [f"j{i:02d}" for i in range(12)]})
        self.assertIsNone(self.call(base))
        new = _fp(**{"skills.names": [f"s{i:02d}" for i in range(25)], "cron_jobs": []})
        out = self.call(new)
        skills = next(seg for seg in out.split("; ") if "skills.names" in seg)
        self.assertEqual(skills.count(" +s"), 10)
        self.assertTrue(skills.endswith("+15 more"))
        cron = next(seg for seg in out.split("; ") if "cron_jobs" in seg)
        self.assertEqual(cron.count(" -j"), 10)
        self.assertTrue(cron.endswith("+2 more"))

    def test_memory_provider_scalar_change(self):
        self.assertIsNone(self.call(_fp(memory_provider="holographic")))
        self.assertIn("memory_provider +synapse-mem -holographic", self.call(_fp(memory_provider="synapse-mem")))
        self.assertIsNone(self.call())
        self.assertIsNone(self.call(_fp(memory_provider=None)))
        self.assertEqual(self.read_baseline()["memory_provider"], "synapse-mem")

    def test_step_does_not_flag_own_state_dir(self):
        del os.environ["WATCHER_STATE_DIR"]
        os.environ["PATH"] = str(self.root)
        fixtures = _ROOT / "tests" / "fixtures"
        for root, base in (("hermes", self.hh), ("claude", self.home / ".claude"), ("smem", self.home / ".smem")):
            base.mkdir(exist_ok=True)
            for name in (fixtures / f"mac-{root}-entries.txt").read_text().split():
                (base / name).touch()
        for own in ("watcher-state", "state-staging", "state-restore-backups"):
            (self.hh / own).unlink()
            (self.hh / own).mkdir()
        with mock.patch.object(hygiene, "STATE_SCRIPT", _ROOT / "scripts" / "hermes-state.py"):
            self.assertIsNone(hygiene.state_audit())
            self.assertIsNone(hygiene.state_audit())

    def test_empty_hermes_home_audits_home_dot_hermes(self):
        (self.home / ".hermes").mkdir()
        (self.home / ".hermes" / "brand-new-entry").touch()
        env = {**os.environ, "HERMES_HOME": "", "PATH": str(self.root)}
        proc = subprocess.run([sys.executable, str(_ROOT / "scripts" / "hermes-state.py"), "audit", "--json"],
                              env=env, capture_output=True, text=True, check=False, timeout=60)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("brand-new-entry", proc.stdout)


def _set_path_deep(fp, name, value):
    parts = name.split(".")
    for part in parts[:-1]:
        fp = fp.setdefault(part, {})
    fp[parts[-1]] = value


if __name__ == "__main__":
    unittest.main()
