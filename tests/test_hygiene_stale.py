"""hermes-hygiene removes only cache/temp entries untouched for the stale window."""

import importlib.util
import os
import sys
import tempfile
import time
import shutil
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
