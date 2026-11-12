"""Worktree .graphify seeding: a copy, never a link into the main repo."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_plugin_path = Path(__file__).resolve().parent.parent / "plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate_graphify_seed", _plugin_path)
assert _spec is not None and _spec.loader is not None
co = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate_graphify_seed"] = co
_spec.loader.exec_module(co)


class SeedGraphifyTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.main = Path(self._tmp.name) / "main"
        self.wt = Path(self._tmp.name) / "wt"
        self.main.mkdir()
        self.wt.mkdir()

    def fill_main(self):
        g = self.main / ".graphify"
        (g / "cache").mkdir(parents=True)
        (g / "graph.json").write_text("main-graph")
        (g / "cache" / "a.bin").write_text("a")
        for name in ("branch.json", "worktree.json", "needs_update"):
            (g / name).write_text("stale")
        return g

    def test_copy_is_independent_and_drops_state_files(self):
        main_g = self.fill_main()
        co._seed_graphify(self.main, self.wt)
        wt_g = self.wt / ".graphify"
        self.assertTrue(wt_g.is_dir() and not wt_g.is_symlink())
        self.assertEqual((wt_g / "graph.json").read_text(), "main-graph")
        self.assertEqual((wt_g / "cache" / "a.bin").read_text(), "a")
        for name in ("branch.json", "worktree.json", "needs_update"):
            self.assertFalse((wt_g / name).exists(), name)
            self.assertTrue((main_g / name).exists(), name)  # main untouched
        (wt_g / "graph.json").write_text("changed")
        (wt_g / "new.json").write_text("x")
        self.assertEqual((main_g / "graph.json").read_text(), "main-graph")
        self.assertFalse((main_g / "new.json").exists())

    def test_no_main_graph_creates_nothing(self):
        co._seed_graphify(self.main, self.wt)
        self.assertFalse((self.main / ".graphify").exists())
        self.assertFalse((self.wt / ".graphify").exists())

    def test_empty_main_graph_is_not_copied(self):
        (self.main / ".graphify").mkdir()
        co._seed_graphify(self.main, self.wt)
        self.assertFalse((self.wt / ".graphify").exists())
        self.assertEqual(list((self.main / ".graphify").iterdir()), [])

    def test_legacy_symlink_is_replaced_by_a_copy(self):
        main_g = self.fill_main()
        (self.wt / ".graphify").symlink_to(main_g)
        co._seed_graphify(self.main, self.wt)
        wt_g = self.wt / ".graphify"
        self.assertFalse(wt_g.is_symlink())
        (wt_g / "graph.json").write_text("changed")
        self.assertEqual((main_g / "graph.json").read_text(), "main-graph")

    def test_legacy_symlink_to_empty_main_is_removed_not_followed(self):
        main_g = self.main / ".graphify"
        main_g.mkdir()
        (self.wt / ".graphify").symlink_to(main_g)
        co._seed_graphify(self.main, self.wt)
        self.assertFalse((self.wt / ".graphify").exists())
        self.assertTrue(main_g.is_dir())

    def test_existing_real_dir_is_left_alone(self):
        self.fill_main()
        own = self.wt / ".graphify"
        own.mkdir()
        (own / "mine.json").write_text("keep")
        co._seed_graphify(self.main, self.wt)
        self.assertEqual([p.name for p in own.iterdir()], ["mine.json"])

    def test_oserror_fails_open(self):
        self.fill_main()
        co._seed_graphify(self.main, self.wt / "missing" / "deeper")  # copytree target parent absent is created; must not raise
        co._seed_graphify(self.main / "nope", self.wt)


if __name__ == "__main__":
    unittest.main()
