"""Tier-2 orchestration skill: process v2 names match the contract; card_state helper."""

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skills" / "tier2-orchestration"
SKILL = SKILL_DIR / "SKILL.md"

_spec = importlib.util.spec_from_file_location("tier2_card_state", SKILL_DIR / "scripts" / "card_state.py")
assert _spec and _spec.loader
cs = importlib.util.module_from_spec(_spec)
sys.modules["tier2_card_state"] = cs
_spec.loader.exec_module(cs)

LEGACY_LINE_COUNT = 1197


def _load_plugin():
    spec = importlib.util.spec_from_file_location("claude_orchestrate_tier2_skill", ROOT / "plugin" / "__init__.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["claude_orchestrate_tier2_skill"] = mod
    spec.loader.exec_module(mod)
    return mod


class SkillTextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL.read_text("utf-8")

    def test_frontmatter(self):
        self.assertTrue(self.text.startswith("---\n"))
        head = self.text.split("\n---\n", 1)[0]
        self.assertIn("name: tier2-orchestration", head)
        m = re.search(r"^description: (.+)$", head, re.M)
        self.assertIsNotNone(m)
        desc = m.group(1) if m else ""
        self.assertTrue(len(desc) <= 60 and desc.endswith("."))

    def test_shorter_than_before(self):
        self.assertLess(len(self.text.splitlines()), LEGACY_LINE_COUNT)

    def test_contract_names_present(self):
        for name in [
            "process.json", '"version": 2', "design_path", "base_commit", "design-meta:",
            "evidence/test-impact.txt", "evidence/red-<unit>.txt", "green-<unit>.txt", "metrics.jsonl",
            "/design-review", "/card-review", "design_precheck.py", "process_metrics.py",
            "STATUS:", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED", "DESIGN GAP",
            "escape:design", "design-defect", "amendment", "Changes since review", "design-review-r", "task-dir=", "code-review-r<N>.md",
            "t2-<ID>-ground", "t2-<ID>-dreview<N>", "t2-<ID>-creview<N>", "t2-<ID>-impl",
            "repo-guides/<repo>.md", ".graphify", "~/.local/bin/graphify",
            "plugins/hermes-dev-process/README.md", "code-explorer",
        ]:
            self.assertIn(name, self.text, name)

    def test_session_names_match_plugin_classifier(self):
        co = _load_plugin()
        review_prompt = "/card-review /x/design.md round=1"
        for tid, kind in (
            ("t2-t_ab12cd34-dreview1", "design"),
            ("t2-t_ab12cd34-creview2", "code"),
            ("t2-t_ab12cd34-impl", None),
            ("t2-t_ab12cd34-fix1", None),
            ("t2-t_ab12cd34-design-revise1", None),
            ("t2-t_ab12cd34-design", None),
            ("t2-t_ab12cd34-ground", None),
        ):
            self.assertEqual(co._review_kind(tid, review_prompt if kind else "Read the brief."), kind, tid)
        for tid, stage in (
            ("t2-t_ab12cd34-ground", "grounding"),
            ("t2-t_ab12cd34-design", "design"),
            ("t2-t_ab12cd34-design-revise1", "design"),
            ("t2-t_ab12cd34-impl", "implementation"),
            ("t2-t_ab12cd34-fix2", "fix"),
        ):
            self.assertEqual(co._v2_stage(tid, None), stage, tid)

    def test_referenced_files_exist(self):
        design = ROOT / "skills" / "shared" / "software-development" / "design"
        for rel in set(re.findall(r"`(references/[\w.-]+\.md)`", self.text)):
            self.assertTrue((SKILL_DIR / rel).is_file() or (design / rel).is_file(), rel)
        for rel in set(re.findall(r"tier2-orchestration/(scripts/[\w.-]+\.py)", self.text)):
            self.assertTrue((SKILL_DIR / rel).is_file(), rel)

    def test_no_em_dash_in_new_references(self):
        for name in ("implementer-brief.md",):
            self.assertNotIn("\u2014", (SKILL_DIR / "references" / name).read_text("utf-8"), name)


class CardStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.card = Path(self._tmp.name) / "t2-t_x"

    def test_init_writes_contract_shape(self):
        cs.main(["init", str(self.card), "--tier", "light", "--kind", "bugfix", "--base", "abc123", "--modules", "ui,risk"])
        data = json.loads((self.card / "process.json").read_text())
        self.assertEqual(data, {"version": 2, "tier": "light", "modules": ["ui", "risk"], "kind": "bugfix",
                                "design_path": None, "base_commit": "abc123"})
        self.assertTrue((self.card / "evidence").is_dir() and (self.card / "review").is_dir())
        row = json.loads((self.card / "metrics.jsonl").read_text().splitlines()[0])
        self.assertEqual((row["stage"], row["event"]), ("triage", "end"))

    def test_init_refuses_existing(self):
        args = ["init", str(self.card), "--tier", "none", "--kind", "copy", "--base", "abc"]
        cs.main(args)
        with self.assertRaises(SystemExit):
            cs.main(args)

    def test_raise_tier_only_up(self):
        cs.main(["init", str(self.card), "--tier", "light", "--kind", "feature", "--base", "abc"])
        cs.main(["raise-tier", str(self.card), "full", "--design-path", "/x/design.md"])
        data = json.loads((self.card / "process.json").read_text())
        self.assertEqual((data["tier"], data["design_path"]), ("full", "/x/design.md"))
        for tier in ("light", "full"):
            with self.assertRaises(SystemExit):
                cs.main(["raise-tier", str(self.card), tier])

    def test_metric_line_format(self):
        cs.main(["metric", str(self.card), "amendment", "amendment", "--round", "1", "--detail", '{"gap": "1"}'])
        row = json.loads((self.card / "metrics.jsonl").read_text().splitlines()[0])
        self.assertEqual(set(row), {"ts", "stage", "event", "round", "detail"})
        self.assertEqual((row["stage"], row["event"], row["round"], row["detail"]), ("amendment", "amendment", 1, {"gap": "1"}))

    def test_unknown_module_rejected(self):
        with self.assertRaises(SystemExit):
            cs.main(["init", str(self.card), "--tier", "full", "--kind", "feature", "--base", "a", "--modules", "bogus"])


if __name__ == "__main__":
    unittest.main()
