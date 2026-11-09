"""The per-card review-round cap is enforced by `claude_orchestrate start`.

Nothing here launches tmux or Claude: the session launcher (_start_session)
is stubbed, and the one end-to-end test replaces _run so no subprocess runs.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_plugin_path = Path(__file__).resolve().parent.parent / "plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate_review_cap", _plugin_path)
assert _spec and _spec.loader
co = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate_review_cap"] = co
_spec.loader.exec_module(co)

PROMPT = "Run /pr-review-toolkit:review-pr and write the verdict to /tmp/verdict.md"


class ReviewCapBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "tasks"
        self.root.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ORCHESTRATE_REVIEW_CAP"}
        self.launched = []
        self.fail_launch = False
        patches = [
            patch.dict(os.environ, env, clear=True),
            patch.object(co, "_tasks_root", lambda: self.root),
            patch.object(co, "_session_exists", return_value=False),
            patch.object(co, "_start_session", side_effect=self._fake_launch),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _fake_launch(self, args):
        if self.fail_launch:
            return {"ok": False, "error": "tmux new-session failed"}
        self.launched.append(args["task_id"])
        return {"ok": True, "task_id": args["task_id"]}

    def start(self, task_id, kanban="t_aaaa0001", prompt=PROMPT, **extra):
        args = {"task_id": task_id, "prompt": prompt, "workdir": "/tmp"}
        if kanban:
            args["kanban_task_id"] = kanban
        args.update(extra)
        return co._start(args)

    def finish(self, task_id):
        d = self.root / task_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "outcome.md").write_text("DONE\n")

    def ledger_rows(self, kanban="t_aaaa0001"):
        return json.loads((self.root / ".review-rounds" / f"{kanban}.json").read_text())["rounds"]


class CapEnforcementTest(ReviewCapBase):
    def test_fourth_review_is_refused_with_escalation_message(self):
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-x-review-r{i}")["ok"])
            self.finish(f"t2-x-review-r{i}")
        res = self.start("t2-x-review-r4")
        self.assertFalse(res["ok"])
        self.assertTrue(res["escalate"])
        msg = res["error"]
        self.assertIn("review-round cap reached", msg)
        self.assertIn("kanban_block kind=needs_input", msg)
        self.assertIn(".review-rounds", msg)
        self.assertNotIn("t2-x-review-r4", self.launched)
        self.assertEqual(len(self.launched), 3)

    def test_non_review_starts_are_unaffected(self):
        for i in range(6):
            self.assertTrue(self.start(f"t2-x-impl-{i}", prompt="implement the feature")["ok"])
        for name in ("t2-x-review-fix", "t2-x-reviewfix", "t2-x-design-revise", "t2-x-drevision", "t_aafe12e5-preview"):
            for n in range(5):
                self.assertTrue(self.start(f"{name}{n}", prompt="edit the code")["ok"], name)
        self.assertFalse((self.root / ".review-rounds").exists())

    def test_impl_session_mentioning_toolkit_is_not_a_review(self):
        for i in range(5):
            res = self.start(f"t2-x-impl-{i}", prompt="afterwards the reviewer runs pr-review-toolkit")
            self.assertTrue(res["ok"])

    def test_review_detected_from_prompt_when_name_is_neutral(self):
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-x-toolkit-{i}")["ok"])
            self.finish(f"t2-x-toolkit-{i}")
        self.assertFalse(self.start("t2-x-audit")["ok"])

    def test_verdict_file_prompt_counts_as_review(self):
        p = "Review the diff. Write your verdict to /tmp/v.md"
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-x-check{i}", prompt=p)["ok"])
            self.finish(f"t2-x-check{i}")
        self.assertFalse(self.start("t2-x-check4", prompt=p)["ok"])

    def test_different_kanban_tasks_are_counted_separately(self):
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"a-review{i}", kanban="t_aaaa0001")["ok"])
            self.finish(f"a-review{i}")
        self.assertFalse(self.start("a-review4", kanban="t_aaaa0001")["ok"])
        self.assertTrue(self.start("b-review1", kanban="t_bbbb0002")["ok"])

    def test_no_kanban_task_id_is_uncapped(self):
        for i in range(8):
            self.assertTrue(self.start(f"manual-review{i}", kanban=None)["ok"])
            self.finish(f"manual-review{i}")

    def test_kanban_id_is_derived_from_t2_task_id(self):
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-t_1d276ee2-review-r{i}", kanban=None)["ok"])
            self.finish(f"t2-t_1d276ee2-review-r{i}")
        self.assertFalse(self.start("t2-t_1d276ee2-review-r4", kanban=None)["ok"])

    def test_code_and_design_reviews_have_separate_caps(self):
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-x-dreview{i}")["ok"])
            self.finish(f"t2-x-dreview{i}")
        self.assertFalse(self.start("t2-x-dreview4")["ok"])
        self.assertIn("design-review", self.start("t2-x-dreview5")["error"])
        self.assertTrue(self.start("t2-x-review1")["ok"])

    def test_model_cannot_lift_the_cap_through_arguments(self):
        for i in (1, 2, 3):
            self.start(f"t2-x-review-r{i}")
            self.finish(f"t2-x-review-r{i}")
        res = self.start("t2-x-review-r4", review_cap=99, force=True, override=True, cap=99)
        self.assertFalse(res["ok"])


class CapConfigurationTest(ReviewCapBase):
    def test_env_override_changes_the_cap(self):
        with patch.dict(os.environ, {"CLAUDE_ORCHESTRATE_REVIEW_CAP": "1"}):
            self.assertTrue(self.start("t2-x-review-r1")["ok"])
            self.finish("t2-x-review-r1")
            self.assertFalse(self.start("t2-x-review-r2")["ok"])
        with patch.dict(os.environ, {"CLAUDE_ORCHESTRATE_REVIEW_CAP": "5"}):
            for i in (1, 2, 3, 4, 5):
                self.assertTrue(self.start(f"t2-y-review-r{i}", kanban="t_bbbb0002")["ok"])
                self.finish(f"t2-y-review-r{i}")
            self.assertFalse(self.start("t2-y-review-r6", kanban="t_bbbb0002")["ok"])

    def test_invalid_env_falls_back_to_default(self):
        for bad in ("", "abc", "0", "-2"):
            with patch.dict(os.environ, {"CLAUDE_ORCHESTRATE_REVIEW_CAP": bad}):
                self.assertEqual(co._review_cap(), 3)

    def test_human_extra_file_grants_more_rounds(self):
        for i in (1, 2, 3):
            self.start(f"t2-x-review-r{i}")
            self.finish(f"t2-x-review-r{i}")
        self.assertFalse(self.start("t2-x-review-r4")["ok"])
        (self.root / ".review-rounds" / "t_aaaa0001.extra").write_text("1\n")
        self.assertTrue(self.start("t2-x-review-r4")["ok"])
        self.finish("t2-x-review-r4")
        self.assertFalse(self.start("t2-x-review-r5")["ok"])

    def test_human_can_reset_by_deleting_the_ledger(self):
        for i in (1, 2, 3):
            self.start(f"t2-x-review-r{i}")
            self.finish(f"t2-x-review-r{i}")
        (self.root / ".review-rounds" / "t_aaaa0001.json").unlink()
        self.assertTrue(self.start("t2-x-review-r4")["ok"])


class LedgerTest(ReviewCapBase):
    def test_ledger_format(self):
        self.start("t2-x-review-r1")
        data = json.loads((self.root / ".review-rounds" / "t_aaaa0001.json").read_text())
        self.assertEqual(data["kanban_task_id"], "t_aaaa0001")
        (row,) = data["rounds"]
        self.assertEqual((row["task_id"], row["kind"]), ("t2-x-review-r1", "code"))
        self.assertIsInstance(row["started_at"], float)
        leftovers = [p.name for p in (self.root / ".review-rounds").iterdir() if p.suffix == ".tmp"]
        self.assertEqual(leftovers, [])

    def test_ledger_survives_a_new_plugin_instance(self):
        for i in (1, 2, 3):
            self.start(f"t2-x-review-r{i}")
            self.finish(f"t2-x-review-r{i}")
        spec = importlib.util.spec_from_file_location("claude_orchestrate_review_cap_2", _plugin_path)
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        with patch.object(fresh, "_tasks_root", lambda: self.root), \
             patch.object(fresh, "_session_exists", return_value=False), \
             patch.object(fresh, "_start_session", side_effect=AssertionError("must not launch")):
            res = fresh._start({"task_id": "t2-x-review-r4", "prompt": PROMPT, "workdir": "/tmp",
                                "kanban_task_id": "t_aaaa0001"})
        self.assertFalse(res["ok"])

    def test_corrupt_ledger_is_treated_as_empty(self):
        d = self.root / ".review-rounds"
        d.mkdir()
        (d / "t_aaaa0001.json").write_text("{not json")
        self.assertTrue(self.start("t2-x-review-r1")["ok"])

    def test_ledger_dir_is_not_reported_as_a_task(self):
        self.start("t2-x-review-r1")
        with patch.object(co, "_run", side_effect=AssertionError("no subprocess")):
            orphans = co._recover({})["orphaned"]
        self.assertNotIn(".review-rounds", [o["task_id"] for o in orphans])


class CrashRestartTest(ReviewCapBase):
    def test_restart_of_a_crashed_review_does_not_count_twice(self):
        for _ in range(3):  # no outcome written between starts: the session crashed
            self.assertTrue(self.start("t2-x-review-r1")["ok"])
        rows = self.ledger_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["restarts"], 2)

    def test_crash_restarts_are_bounded(self):
        for _ in range(4):  # original + 2 free restarts, then a new round
            self.start("t2-x-review-r1")
        self.assertEqual(len(self.ledger_rows()), 2)

    def test_rerunning_a_finished_review_counts_again(self):
        self.start("t2-x-review-r1")
        self.finish("t2-x-review-r1")
        self.start("t2-x-review-r1")
        self.assertEqual(len(self.ledger_rows()), 2)

    def test_failed_launch_does_not_burn_a_round(self):
        self.fail_launch = True
        for _ in range(5):
            self.assertFalse(self.start("t2-x-review-r1")["ok"])
        self.fail_launch = False
        for i in (1, 2, 3):
            self.assertTrue(self.start(f"t2-x-review-r{i}")["ok"])
            self.finish(f"t2-x-review-r{i}")

    def test_existing_session_does_not_consume_a_round(self):
        with patch.object(co, "_session_exists", return_value=True), \
             patch.object(co, "_start_session", return_value={"ok": False, "error": "already exists"}):
            for _ in range(5):
                co._start({"task_id": "t2-x-review-r1", "prompt": PROMPT, "workdir": "/tmp",
                           "kanban_task_id": "t_aaaa0001"})
        self.assertFalse((self.root / ".review-rounds" / "t_aaaa0001.json").exists())


class EndToEndStubTest(unittest.TestCase):
    """Real _start_session with every subprocess replaced: a refused start spawns nothing."""

    def test_refused_start_runs_no_subprocess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_run(cmd, timeout=None):
                calls.append(cmd)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            args = {"prompt": "run pr-review-toolkit", "workdir": tmp, "executor": "claude", "model": "sonnet",
                    "kanban_task_id": "t_cccc0003"}
            with patch.object(co, "_tasks_root", lambda: root), \
                 patch.object(co, "get_hermes_home", return_value=root), \
                 patch.object(co, "_session_exists", return_value=False), \
                 patch.object(co, "_seatbelt_headers", return_value="x-tfy-api-key: DUMMY"), \
                 patch.object(co, "_session_state", return_value={"state": "working"}), \
                 patch.object(co, "_run", side_effect=fake_run), \
                 patch("time.sleep"), \
                 patch.dict(os.environ, {}, clear=True):
                for i in (1, 2, 3):
                    r = co._start(dict(args, task_id=f"t2-e2e-review-r{i}"))
                    self.assertTrue(r["ok"], r)
                    (root / f"t2-e2e-review-r{i}" / "outcome.md").write_text("DONE\n")
                before = len(calls)
                refused = co._start(dict(args, task_id="t2-e2e-review-r4"))
            self.assertFalse(refused["ok"])
            self.assertEqual(len(calls), before)
            self.assertFalse((root / "t2-e2e-review-r4").exists())


if __name__ == "__main__":
    unittest.main()
