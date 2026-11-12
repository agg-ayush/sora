"""scripts/process_metrics.py against synthetic card directories."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

_path = Path(__file__).resolve().parent.parent / "scripts" / "process_metrics.py"
_spec = importlib.util.spec_from_file_location("process_metrics_under_test", _path)
assert _spec is not None and _spec.loader is not None
pm = importlib.util.module_from_spec(_spec)
sys.modules["process_metrics_under_test"] = pm
_spec.loader.exec_module(pm)


def ev(stage, event, round_=None, ts=1000.0, **detail):
    return {"ts": ts, "stage": stage, "event": event, "round": round_, "detail": detail}


class MetricsBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "tasks"
        self.root.mkdir()

    def card(self, name, proc=None, events=(), verdicts=None, raw_lines=()):
        d = self.root / f"t2-{name}"
        d.mkdir()
        if proc is not None:
            (d / "process.json").write_text(json.dumps(proc))
        lines = [json.dumps(e) for e in events] + list(raw_lines)
        if lines:
            (d / "metrics.jsonl").write_text("\n".join(lines) + "\n")
        for fname, text in (verdicts or {}).items():
            (d / "review").mkdir(exist_ok=True)
            (d / "review" / fname).write_text(text)
        return d


VERDICT = (
    "VERDICT\nconformance: fail\nquality: pass\nfindings:\n"
    "- F1 [BLOCKING] [conformance] [escape:design] a.py:1 | x | y\n"
    "- F2 [BLOCKING] [tests] [escape:test] a.py:2 | x | y\n"
    "- F3 [NONBLOCKING] [quality] [escape:noise] a.py:3 | x | y\n"
    "- F4 [NONBLOCKING] [quality] a.py:4 | x | y\n"
)


class CardAggregationTest(MetricsBase):
    def test_per_card_fields(self):
        self.card("t_one", {"version": 2, "tier": "full", "kind": "feature", "modules": ["ui"]}, [
            ev("design_review", "start", 1, ts=0, task_id="d1"),
            ev("design_review", "end", 1, ts=600, task_id="d1", minutes=10),
            ev("design_review", "start", 2, ts=700, task_id="d2"),
            ev("design_review", "end", 2, ts=1000, task_id="d2"),  # minutes derived: 5
            ev("code_review", "start", 1, task_id="c1"),
            ev("code_review", "start", 1, task_id="c1"),  # crash restart, same round
            ev("code_review", "end", 1, task_id="c1", minutes=7.5),
            ev("code_review", "start", 2, task_id="c2"),
            ev("implementation", "start", None, ts=0, task_id="i1"),
            ev("implementation", "end", None, ts=1200, task_id="i1"),  # derived: 20
            ev("design", "amendment", 1, minutes=12),
            ev("design", "amendment", 2, minutes=3),
            ev("design_review", "refused", None, reason="precheck"),
            ev("code_review", "refused", None, reason="evidence"),
            ev("code_review", "refused", None, reason="evidence"),
        ], verdicts={"verdict-r1.md": VERDICT})
        report = pm.collect(self.root)
        (c,) = report["cards"]
        self.assertEqual((c["card"], c["tier"], c["kind"], c["modules"]), ("t_one", "full", "feature", ["ui"]))
        self.assertEqual((c["design_review_rounds"], c["code_review_rounds"]), (2, 2))
        self.assertEqual((c["amendments"], c["amendment_minutes"]), (2, 15.0))
        self.assertEqual(c["minutes_by_stage"], {"design_review": 15.0, "code_review": 7.5, "implementation": 20.0})
        self.assertEqual(c["findings"], {"design": 1, "impl": 0, "test": 1, "noise": 1, "unlabelled": 1})
        self.assertEqual(c["refused"], {"precheck": 1, "evidence": 2})

    def test_findings_fall_back_to_end_event_counts(self):
        self.card("t_two", {"version": 2, "tier": "light"}, [
            ev("code_review", "start", 1, task_id="c1"),
            ev("code_review", "end", 1, task_id="c1",
               findings={"design": 2, "impl": 1, "test": 0, "noise": 3, "unlabelled": 0}),
        ])
        (c,) = pm.collect(self.root)["cards"]
        self.assertEqual(c["findings"], {"design": 2, "impl": 1, "test": 0, "noise": 3, "unlabelled": 0})

    def test_reviewer_agent_files_are_not_double_counted(self):
        self.card("t_three", {"version": 2, "tier": "light"}, verdicts={
            "verdict-r1.md": VERDICT, "conformance-reviewer-r1.md": VERDICT})
        (c,) = pm.collect(self.root)["cards"]
        self.assertEqual(sum(c["findings"].values()), 4)

    def test_only_v2_cards_are_included(self):
        self.card("t_legacy", None, [ev("code_review", "start", 1)])
        self.card("t_v1", {"version": 1, "tier": "full"})
        self.card("t_v2", {"version": 2, "tier": "none", "kind": "bugfix"})
        (self.root / "not-a-card").mkdir()
        (self.root / "t2-file").write_text("x")
        names = [c["card"] for c in pm.collect(self.root)["cards"]]
        self.assertEqual(names, ["t_v2"])

    def test_tolerates_bad_lines_and_missing_metrics(self):
        self.card("t_bad", {"version": 2, "tier": "light"}, [ev("code_review", "start", 1)],
                  raw_lines=["{broken", "[]", '{"no_event": 1}', ""])
        self.card("t_empty", {"version": 2, "tier": "none"})
        cards = {c["card"]: c for c in pm.collect(self.root)["cards"]}
        self.assertEqual(cards["t_bad"]["code_review_rounds"], 1)
        self.assertEqual(cards["t_empty"]["code_review_rounds"], 0)
        self.assertEqual(cards["t_empty"]["minutes_by_stage"], {})

    def test_iso_timestamps_are_accepted(self):
        self.card("t_iso", {"version": 2, "tier": "light"}, [
            {"ts": "2026-01-01T00:00:00Z", "stage": "implementation", "event": "start", "round": None,
             "detail": {"task_id": "i"}},
            {"ts": "2026-01-01T00:30:00+00:00", "stage": "implementation", "event": "end", "round": None,
             "detail": {"task_id": "i"}},
        ])
        (c,) = pm.collect(self.root)["cards"]
        self.assertEqual(c["minutes_by_stage"], {"implementation": 30.0})

    def test_read_only(self):
        self.card("t_ro", {"version": 2, "tier": "light"}, [ev("code_review", "start", 1)],
                  verdicts={"verdict-r1.md": VERDICT})

        def snapshot():
            return sorted((p.as_posix(), p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob("*"))

        before = snapshot()
        pm.render_markdown(pm.collect(self.root))
        self.assertEqual(before, snapshot())


class SummaryTest(MetricsBase):
    def fill(self, with_design, no_design):
        for i, rounds in enumerate(with_design):
            self.card(f"t_d{i}", {"version": 2, "tier": "light"},
                      [ev("code_review", "start", r, task_id=f"c{r}") for r in range(1, rounds + 1)])
        for i, rounds in enumerate(no_design):
            self.card(f"t_n{i}", {"version": 2, "tier": "none"},
                      [ev("code_review", "start", r, task_id=f"c{r}") for r in range(1, rounds + 1)])

    def test_baseline_comparison_and_no_hints_under_ten_cards(self):
        self.fill([1, 2, 3], [4, 5])
        s = pm.collect(self.root)["summary"]
        self.assertEqual((s["cards"], s["cards_with_design"], s["cards_no_design"]), (5, 3, 2))
        self.assertEqual(s["mean_code_rounds_with_design"], 2.0)
        self.assertEqual(s["mean_code_rounds_no_design"], 4.5)
        self.assertEqual((s["baseline_rounds_with_design"], s["baseline_rounds_no_design"]), (3.1, 4.6))
        (hint,) = s["hints"]
        self.assertIn("insufficient data (5 of 10", hint["hint"])

    def test_keep_or_drop_hints_at_ten_cards(self):
        self.fill([1, 2, 1, 2, 1, 1, 2, 1], [2, 3])
        s = pm.collect(self.root)["summary"]
        hints = {h["piece"]: h for h in s["hints"]}
        self.assertEqual(hints["design stage (tiers light and full)"]["hint"], "keep")
        self.assertEqual(hints["none-tier path"]["hint"], "keep")
        self.assertIn("1.38 vs baseline 3.1", hints["design stage (tiers light and full)"]["basis"])
        self.assertIn("design pre-check", hints)
        self.assertIn("RED/GREEN evidence gate", hints)

    def test_hints_flag_worse_than_baseline(self):
        self.fill([4] * 8, [6, 6])
        hints = {h["piece"]: h["hint"] for h in pm.collect(self.root)["summary"]["hints"]}
        self.assertEqual(hints["design stage (tiers light and full)"], "drop or rework")
        self.assertEqual(hints["none-tier path"], "raise tiers")

    def test_design_escape_share_hint(self):
        self.fill([1] * 9, [1])
        self.card("t_f", {"version": 2, "tier": "full"}, verdicts={"verdict-r1.md": VERDICT})
        s = pm.collect(self.root)["summary"]
        self.assertEqual(s["findings"]["design"], 1)
        self.assertEqual(s["design_escape_share"], 0.25)
        hints = {h["piece"]: h["hint"] for h in s["hints"]}
        self.assertEqual(hints["design review lenses"], "keep")

    def test_empty_root(self):
        report = pm.collect(self.root)
        self.assertEqual(report["cards"], [])
        self.assertIn("No cards", pm.render_markdown(report))

    def test_missing_root(self):
        self.assertEqual(pm.collect(self.root / "nope")["cards"], [])


class CliTest(MetricsBase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pm.main(list(argv))
        self.assertEqual(code, 0)
        return buf.getvalue()

    def test_markdown_table(self):
        self.card("t_cli", {"version": 2, "tier": "light", "kind": "bugfix"}, [
            ev("code_review", "start", 1, task_id="c1"), ev("code_review", "end", 1, task_id="c1", minutes=4)],
            verdicts={"verdict-r1.md": VERDICT})
        out = self.run_cli("--root", str(self.root))
        self.assertIn("| Card | Tier | Kind |", out)
        self.assertIn("| t_cli | light | bugfix | 0 | 1 | 0 | code_review 4.0 | 1/0/1/1 (1) |", out)
        self.assertIn("## Summary", out)
        self.assertIn("| 3.1 |", out)
        self.assertIn("## Keep or drop", out)

    def test_json_output(self):
        self.card("t_cli", {"version": 2, "tier": "none"})
        data = json.loads(self.run_cli("--root", str(self.root), "--json"))
        self.assertEqual(data["cards"][0]["card"], "t_cli")
        self.assertEqual(data["summary"]["cards"], 1)

    def test_default_root_uses_hermes_home(self):
        home = Path(self._tmp.name) / "home"
        (home / "tasks").mkdir(parents=True)
        d = home / "tasks" / "t2-t_home"
        d.mkdir()
        (d / "process.json").write_text('{"version": 2, "tier": "none"}')
        with patch.dict(os.environ, {"HERMES_HOME": str(home)}):
            data = json.loads(self.run_cli("--json"))
        self.assertEqual([c["card"] for c in data["cards"]], ["t_home"])


if __name__ == "__main__":
    unittest.main()
