"""hermes-hygiene removes only cache/temp entries untouched for the stale window."""

import importlib.util
import os
import sys
import tempfile
import time
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


if __name__ == "__main__":
    unittest.main()
