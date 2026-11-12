"""Process v2 gates and metrics in `claude_orchestrate start`.

No tmux or Claude runs: _start_session is stubbed, as in test_review_cap.py.
The design pre-check is a stub with the same check(path) -> (ok, problems,
warnings) interface, plus one integration test against the real script.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_plugin_path = Path(__file__).resolve().parent.parent / "plugin" / "__init__.py"
_spec = importlib.util.spec_from_file_location("claude_orchestrate_process_v2", _plugin_path)
assert _spec and _spec.loader
co = importlib.util.module_from_spec(_spec)
sys.modules["claude_orchestrate_process_v2"] = co
_spec.loader.exec_module(co)

REAL_LOAD_PRECHECK = co._v2_load_precheck
KANBAN = "t_aaaa0001"
CODE_PROMPT = "Run /pr-review-toolkit:review-pr and write the verdict to {verdict}"
DESIGN_PROMPT = "Review the design doc at /tmp/design.md. Write your verdict to /tmp/dv.md"

RED_PYTEST = "pytest tests/test_x.py\n=== 1 failed in 0.1s ===\nFAILED tests/test_x.py::test_a - assert 1 == 2\n"
GREEN_PYTEST = "pytest tests/test_x.py\n=== 3 passed in 0.2s ===\n"


class GateBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "tasks"
        self.root.mkdir()
        self.card = self.root / f"t2-{KANBAN}"
        self.launched = []
        self.precheck_result = (True, [], [])
        self.precheck_calls = []
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ORCHESTRATE_REVIEW_CAP"}
        patches = [
            patch.dict(os.environ, env, clear=True),
            patch.object(co, "_tasks_root", lambda: self.root),
            patch.object(co, "_session_exists", return_value=False),
            patch.object(co, "_start_session", side_effect=self._fake_launch),
            patch.object(co, "_v2_load_precheck", return_value=self._fake_check),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _fake_check(self, path):
        self.precheck_calls.append(path)
        return self.precheck_result

    def _fake_launch(self, args):
        self.launched.append(args["task_id"])
        (self.root / args["task_id"]).mkdir(parents=True, exist_ok=True)
        return {"ok": True, "task_id": args["task_id"]}

    def make_card(self, **proc):
        self.card.mkdir(parents=True, exist_ok=True)
        data = {"version": 2, "tier": "light", "modules": [], "kind": "feature", "design_path": None, "base_commit": "abc"}
        data.update(proc)
        (self.card / "process.json").write_text(json.dumps(data))

    def evidence(self, name, text):
        d = self.card / "evidence"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(text)

    def good_evidence(self):
        self.evidence("red-a.txt", RED_PYTEST)
        self.evidence("green-a.txt", GREEN_PYTEST)

    def start(self, task_id, prompt, kanban=KANBAN):
        return co._start({"task_id": task_id, "prompt": prompt, "workdir": "/tmp", "kanban_task_id": kanban})

    def metrics(self):
        path = self.card / "metrics.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def ledger_rounds(self):
        path = self.root / ".review-rounds" / f"{KANBAN}.json"
        return json.loads(path.read_text())["rounds"] if path.exists() else []

    def code_start(self, name="t2-x-review-r1", verdict="/tmp/v.md"):
        return self.start(name, CODE_PROMPT.format(verdict=verdict))


class LegacyTest(GateBase):
    def test_no_process_json_is_a_noop(self):
        self.assertTrue(self.start("t2-x-dreview1", DESIGN_PROMPT)["ok"])
        self.assertTrue(self.code_start()["ok"])
        self.assertEqual(self.precheck_calls, [])
        self.assertFalse(self.card.exists())

    def test_version_one_or_garbage_is_legacy(self):
        self.card.mkdir()
        for body in ('{"version": 1}', "{not json", "[]", '{"version": "2"}'):
            (self.card / "process.json").write_text(body)
            self.assertTrue(self.start("t2-x-dreview1", DESIGN_PROMPT)["ok"])
        self.assertEqual(self.precheck_calls, [])
        self.assertFalse((self.card / "metrics.jsonl").exists())

    def test_no_kanban_id_is_legacy(self):
        self.make_card()
        self.assertTrue(self.start("manual-review1", CODE_PROMPT.format(verdict="/tmp/v.md"), kanban=None)["ok"])
        self.assertEqual(self.metrics(), [])


class DesignGateTest(GateBase):
    def test_precheck_pass_starts_and_counts_a_round(self):
        self.make_card(design_path="/tmp/design.md")
        res = self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.precheck_calls, ["/tmp/design.md"])
        self.assertEqual(len(self.ledger_rounds()), 1)

    def test_precheck_falls_back_to_card_design_md(self):
        self.make_card(design_path=None)
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.assertEqual(self.precheck_calls, [str(self.card / "design.md")])

    def test_precheck_failure_refuses_and_counts_no_round(self):
        self.make_card(design_path="/tmp/design.md")
        self.precheck_result = (False, ["missing section: Verification table", "R2 not in verification table"], [])
        for i in range(5):  # refusals never reach the cap
            res = self.start(f"t2-x-dreview{i}", DESIGN_PROMPT)
            self.assertFalse(res["ok"])
            self.assertFalse(res["escalate"])
        self.assertIn("- missing section: Verification table", res["error"])
        self.assertIn("- R2 not in verification table", res["error"])
        self.assertIn("design author", res["error"])
        self.assertIn("No review round was used", res["error"])
        self.assertEqual(res["missing"], ["missing section: Verification table", "R2 not in verification table"])
        self.assertEqual(self.launched, [])
        self.assertEqual(self.ledger_rounds(), [])
        self.assertFalse((self.root / ".review-rounds").exists())
        self.precheck_result = (True, [], [])
        self.assertTrue(self.start("t2-x-dreview9", DESIGN_PROMPT)["ok"])
        self.assertEqual(len(self.ledger_rounds()), 1)

    def test_precheck_script_missing_fails_open_with_warning(self):
        self.make_card()
        with patch.object(co, "_v2_load_precheck", return_value=None):
            res = self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.assertTrue(res["ok"])
        (start,) = [m for m in self.metrics() if m["event"] == "start"]
        self.assertTrue(start["detail"]["warnings"][0].startswith("design pre-check script not found"))

    def test_precheck_warnings_do_not_block(self):
        self.make_card()
        self.precheck_result = (True, [], ["citation looks stale"])
        self.assertTrue(self.start("t2-x-dreview1", DESIGN_PROMPT)["ok"])

    def test_design_gate_ignores_code_review_evidence(self):
        self.make_card()  # no evidence at all
        self.assertTrue(self.start("t2-x-dreview1", DESIGN_PROMPT)["ok"])


class CodeGateTest(GateBase):
    def test_evidence_present_starts(self):
        self.make_card(tier="light")
        self.good_evidence()
        self.assertTrue(self.code_start()["ok"])
        self.assertEqual(len(self.ledger_rounds()), 1)

    def test_missing_evidence_refuses_without_a_round(self):
        for tier in ("light", "full"):
            self.make_card(tier=tier)
            res = self.code_start()
            self.assertFalse(res["ok"])
            self.assertFalse(res["escalate"])
            self.assertIn("no non-empty evidence/red-*.txt", res["error"])
            self.assertIn("no non-empty evidence/green-*.txt", res["error"])
            self.assertIn("No review round was used", res["error"])
        self.assertEqual(self.launched, [])
        self.assertEqual(self.ledger_rounds(), [])

    def test_empty_files_count_as_missing(self):
        self.make_card()
        self.evidence("red-a.txt", "")
        self.evidence("green-a.txt", "pytest tests\n")  # command line only
        res = self.code_start()
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["evidence_missing"]), 2)

    def test_red_without_failure_is_refused(self):
        self.make_card()
        self.evidence("red-a.txt", GREEN_PYTEST)
        self.evidence("green-a.txt", GREEN_PYTEST)
        res = self.code_start()
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["evidence_missing"]), 1)
        self.assertIn("red-a.txt does not show a failing test", res["error"])
        self.assertEqual(self.ledger_rounds(), [])

    def test_green_with_failure_is_refused(self):
        self.make_card()
        self.evidence("red-a.txt", RED_PYTEST)
        self.evidence("green-a.txt", RED_PYTEST)
        res = self.code_start()
        self.assertFalse(res["ok"])
        self.assertIn("green-a.txt does not show a clean passing run", res["error"])

    def test_runner_markers(self):
        reds = {
            "vitest": "npx vitest run\n FAIL  src/a.test.ts > renders\n × renders 3ms\n Tests  1 failed | 4 passed (5)\n",
            "jest": "npx jest\nFAIL src/a.test.js\n  ✕ works (4 ms)\nTests: 1 failed, 2 passed\n",
            "go": "go test ./...\n--- FAIL: TestA (0.00s)\nFAIL\tpkg\t0.01s\n",
            "exit": "./run-tests\nweird runner output\nexit: 2\n",
        }
        greens = {
            "vitest": "npx vitest run\n ✓ src/a.test.ts (3)\n Tests  3 passed (3)\n",
            "jest": "npx jest\nPASS src/a.test.js\nTests: 3 passed, 3 total\n",
            "go": "go test ./...\nok  \tpkg\t0.01s\n",
            "exit": "./run-tests\nall good\nexit: 0\n",
        }
        for name in reds:
            self.assertTrue(co._v2_red_ok(reds[name].partition("\n")[2]), name)
            self.assertTrue(co._v2_green_ok(greens[name].partition("\n")[2]), name)
            self.assertFalse(co._v2_red_ok(greens[name].partition("\n")[2]), name)
            self.assertFalse(co._v2_green_ok(reds[name].partition("\n")[2]), name)

    def test_zero_exit_marker_overrides_failure_text_in_red(self):
        self.assertFalse(co._v2_red_ok("FAILED tests/x.py::t\nexit: 0\n"))

    def test_zero_failed_summary_is_not_a_failure(self):
        self.assertTrue(co._v2_green_ok("0 failed, 4 passed\n"))

    def test_bugfix_on_none_tier_requires_evidence(self):
        self.make_card(tier="none", kind="bugfix")
        res = self.code_start()
        self.assertFalse(res["ok"])
        self.good_evidence()
        self.assertTrue(self.code_start()["ok"])

    def test_refactor_on_none_tier_does_not(self):
        self.make_card(tier="none", kind="refactor")
        self.assertTrue(self.code_start()["ok"])

    def test_non_review_sessions_are_not_gated(self):
        self.make_card(tier="full")
        self.assertTrue(self.start("t2-x-impl-1", "implement the feature")["ok"])


class FailOpenTest(GateBase):
    def test_exception_in_design_gate_allows_start(self):
        self.make_card()
        with patch.object(co, "_v2_load_precheck", side_effect=RuntimeError("boom")):
            res = self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.assertTrue(res["ok"])
        self.assertEqual(len(self.ledger_rounds()), 1)

    def test_exception_in_precheck_check_allows_start(self):
        self.make_card()

        def boom(path):
            raise ValueError("bad design file")

        with patch.object(co, "_v2_load_precheck", return_value=boom):
            self.assertTrue(self.start("t2-x-dreview1", DESIGN_PROMPT)["ok"])

    def test_exception_in_code_gate_allows_start(self):
        self.make_card()
        with patch.object(co, "_v2_evidence_problems", side_effect=OSError("disk")):
            self.assertTrue(self.code_start()["ok"])

    def test_metrics_write_failure_never_blocks(self):
        self.make_card()
        self.good_evidence()
        with patch("builtins.open", side_effect=OSError("read-only")):
            co._v2_metrics_append(self.card, "code_review", "start", 1, {})  # must not raise
        self.assertTrue(self.code_start()["ok"])


class MetricsEventsTest(GateBase):
    def test_refused_events_for_both_gates(self):
        self.make_card()
        self.precheck_result = (False, ["no tests table"], [])
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.code_start()
        design, code = self.metrics()
        self.assertEqual((design["stage"], design["event"]), ("design_review", "refused"))
        self.assertEqual(design["detail"]["reason"], "precheck")
        self.assertEqual(design["detail"]["missing"], ["no tests table"])
        self.assertEqual((code["stage"], code["event"]), ("code_review", "refused"))
        self.assertEqual(code["detail"]["reason"], "evidence")
        self.assertIsInstance(code["ts"], float)

    def test_start_event_carries_the_round(self):
        self.make_card()
        self.good_evidence()
        self.code_start("t2-x-review-r1")
        self.code_start("t2-x-review-r2")
        starts = [m for m in self.metrics() if m["event"] == "start"]
        self.assertEqual([(m["stage"], m["round"]) for m in starts], [("code_review", 1), ("code_review", 2)])
        self.assertEqual(starts[1]["detail"]["task_id"], "t2-x-review-r2")

    def test_cap_refusal_is_logged(self):
        self.make_card()
        self.good_evidence()
        for i in (1, 2, 3):
            self.code_start(f"t2-x-review-r{i}")
        res = self.code_start("t2-x-review-r4")
        self.assertTrue(res["escalate"])
        last = self.metrics()[-1]
        self.assertEqual((last["event"], last["detail"]["reason"]), ("refused", "review-round cap"))

    def test_start_events_for_non_review_sessions_use_a_stage_name(self):
        self.make_card()
        self.start("t2-x-impl-1", "implement it")
        self.start("t2-x-design-author", "write the design")
        stages = [m["stage"] for m in self.metrics()]
        self.assertEqual(stages, ["implementation", "design"])

    def test_failed_launch_writes_no_start_event(self):
        self.make_card()
        self.good_evidence()
        with patch.object(co, "_start_session", return_value={"ok": False, "error": "tmux failed"}):
            self.code_start()
        self.assertEqual(self.metrics(), [])

    def test_end_event_with_finding_counts(self):
        self.make_card()
        self.good_evidence()
        verdict = self.card / "review" / "verdict-r1.md"
        verdict.parent.mkdir()
        verdict.write_text(
            "VERDICT\nconformance: fail\nquality: pass\nfindings:\n"
            "- F1 [BLOCKING] [conformance] [escape:design] a.py:1 | x | y\n"
            "- F2 [NONBLOCKING] [quality] [escape:impl] a.py:2 | x | y\n"
            "- F3 [BLOCKING] [tests] [escape:design] a.py:3 | x | y\n"
            "- F4 [NONBLOCKING] [quality] a.py:4 | x | y\n"
        )
        self.code_start("t2-x-review-r1", verdict=str(verdict))
        self.finish("t2-x-review-r1")
        co._read_outcome("t2-x-review-r1")
        co._read_outcome("t2-x-review-r1")  # idempotent
        ends = [m for m in self.metrics() if m["event"] == "end"]
        self.assertEqual(len(ends), 1)
        end = ends[0]
        self.assertEqual((end["stage"], end["round"]), ("code_review", 1))
        self.assertEqual(end["detail"]["outcome"], "DONE")
        self.assertEqual(end["detail"]["findings"], {"design": 2, "impl": 1, "test": 0, "noise": 0,
                                                    "unlabelled": 1, "total": 4, "blocking": 2})
        self.assertGreaterEqual(end["detail"]["minutes"], 0)

    def test_end_event_reads_the_card_review_command_verdict(self):
        self.make_card()
        self.good_evidence()
        (self.card / "code-review-r1.md").write_text(
            "VERDICT\nconformance: fail\nquality: pass\nfindings:\n"
            "- F1 [BLOCKING] [conformance] [escape:design] a.py:1 | x | y\n"
            "- F2 [NONBLOCKING] [quality] [escape:impl] a.py:2 | x | y\n"
        )
        self.start("t2-x-creview1", "/card-review /x/design.md card=/x/task.md task-dir=%s round=1" % self.card)
        self.finish("t2-x-creview1")
        co._read_outcome("t2-x-creview1")
        (end,) = [m for m in self.metrics() if m["event"] == "end"]
        self.assertEqual((end["stage"], end["round"]), ("code_review", 1))
        self.assertEqual(end["detail"]["findings"]["total"], 2)
        self.assertEqual(end["detail"]["findings"]["design"], 1)
        self.assertEqual(end["detail"]["findings"]["blocking"], 1)

    def test_end_event_prefers_prompt_path_over_command_file(self):
        self.make_card()
        self.good_evidence()
        (self.card / "code-review-r1.md").write_text("- F1 [BLOCKING] [tests] [escape:test] a.py:1 | x | y\n")
        explicit = self.card / "review" / "verdict-r1.md"
        explicit.parent.mkdir()
        explicit.write_text("- F1 [BLOCKING] [quality] [escape:impl] a.py:1 | x | y\n- F2 [NONBLOCKING] a.py:2 | x | y\n")
        self.code_start("t2-x-review-r1", verdict=str(explicit))
        self.finish("t2-x-review-r1")
        co._read_outcome("t2-x-review-r1")
        (end,) = [m for m in self.metrics() if m["event"] == "end"]
        self.assertEqual(end["detail"]["findings"]["total"], 2)

    def test_design_review_candidate_does_not_record_zero_findings(self):
        self.make_card()
        (self.card / "design-review-r1.md").write_text(
            "VERDICT\napproved: no\nblocking_issues:\n- B1 [HIGH] x | y\nnonblocking_suggestions:\n- NB1 z\n")
        self.start("t2-x-dreview1", "/design-review %s/design.md task-dir=%s round=1" % (self.card, self.card))
        self.finish("t2-x-dreview1")
        co._read_outcome("t2-x-dreview1")
        (end,) = [m for m in self.metrics() if m["event"] == "end"]
        self.assertEqual((end["stage"], end["round"]), ("design_review", 1))
        self.assertNotIn("findings", end["detail"])

    def test_end_event_without_verdict_file_has_no_findings(self):
        self.make_card()
        self.good_evidence()
        self.code_start("t2-x-review-r1", verdict="/nonexistent/v.md")
        self.finish("t2-x-review-r1")
        co._read_outcome("t2-x-review-r1")
        (end,) = [m for m in self.metrics() if m["event"] == "end"]
        self.assertNotIn("findings", end["detail"])

    def test_end_event_for_design_review_has_no_findings_and_uses_round(self):
        self.make_card()
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.finish("t2-x-dreview1")
        co._read_outcome("t2-x-dreview1")
        (end,) = [m for m in self.metrics() if m["event"] == "end"]
        self.assertEqual((end["stage"], end["round"]), ("design_review", 1))

    def test_pending_outcome_writes_no_end_event(self):
        self.make_card()
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        (self.root / "t2-x-dreview1" / "outcome.md").write_text("PENDING\n")
        co._read_outcome("t2-x-dreview1")
        self.assertEqual([m for m in self.metrics() if m["event"] == "end"], [])

    def test_rerun_of_same_session_logs_a_second_end(self):
        self.make_card()
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.finish("t2-x-dreview1")
        co._read_outcome("t2-x-dreview1")
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        co._read_outcome("t2-x-dreview1")
        self.assertEqual(len([m for m in self.metrics() if m["event"] == "end"]), 2)

    def test_legacy_card_outcome_read_writes_nothing(self):
        self.start("t2-x-dreview1", DESIGN_PROMPT)
        self.finish("t2-x-dreview1")
        co._read_outcome("t2-x-dreview1")
        self.assertFalse(self.card.exists())
        self.assertFalse((self.root / "t2-x-dreview1" / ".metrics.json").exists())

    def finish(self, task_id):
        d = self.root / task_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "outcome.md").write_text("DONE\n")


class PrecheckLoaderTest(unittest.TestCase):
    def test_loads_check_from_a_script_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "design_precheck.py"
            script.write_text("def check(path):\n    return (False, ['nope ' + path], [])\n")
            with patch.object(co, "_v2_precheck_path", return_value=script):
                check = REAL_LOAD_PRECHECK()
        self.assertEqual(check("x"), (False, ["nope x"], []))

    def test_missing_script_returns_none(self):
        with patch.object(co, "_v2_precheck_path", return_value=None):
            self.assertIsNone(REAL_LOAD_PRECHECK())


class VerdictPathTest(unittest.TestCase):
    def test_extraction(self):
        card = Path("/c")
        f = co._v2_verdict_path
        self.assertEqual(f("write the verdict to /tmp/x/verdict-r1.md now", card, 1), Path("/tmp/x/verdict-r1.md"))
        self.assertEqual(f("Write your verdict to `/tmp/out.md`.", card, 1), Path("/tmp/out.md"))
        self.assertEqual(f("no path here", card, 2), card / "review" / "verdict-r2.md")
        self.assertIsNone(f("no path here", card, None))

    def test_candidates_include_review_command_files(self):
        card = Path("/c")
        f = co._v2_verdict_candidates
        self.assertEqual(f("code", card, 2, None), [card / "code-review-r2.md", card / "review" / "verdict-r2.md"])
        self.assertEqual(f("design", card, 1, "/p/v.md"),
                         [Path("/p/v.md"), card / "design-review-r1.md", card / "review" / "verdict-r1.md"])
        self.assertEqual(f("code", card, None, None), [])
        self.assertEqual(f(None, card, 1, None), [])


class RealPrecheckIntegrationTest(GateBase):
    def test_real_script_is_importable_and_refuses_a_stub_design(self):
        script = co._v2_precheck_path()
        if script is None:
            self.skipTest("design_precheck.py not present yet")
        spec = importlib.util.spec_from_file_location("real_precheck", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        bad = self.card / "design.md"
        self.card.mkdir(parents=True, exist_ok=True)
        bad.write_text("# Not a design\n")
        self.make_card(design_path=str(bad))
        with patch.object(co, "_v2_load_precheck", return_value=mod.check):
            t0 = time.time()
            res = self.start("t2-x-dreview1", DESIGN_PROMPT)
            self.assertLess(time.time() - t0, 2.0)
        self.assertFalse(res["ok"], res)
        self.assertTrue(res["missing"])
        self.assertEqual(self.ledger_rounds(), [])


if __name__ == "__main__":
    unittest.main()
