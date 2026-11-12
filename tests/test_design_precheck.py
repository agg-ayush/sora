"""Tests for the design pre-check script."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/shared/software-development/design/scripts/design_precheck.py"
spec = importlib.util.spec_from_file_location("design_precheck", SCRIPT)
dp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dp)

TABLE = """| Id | Test | Level | Observable asserted | Wrong implementation caught |
|---|---|---|---|---|
| R1 | selecting removes rows | unit | list holds only unselected ids | removes all rows |
| R2 | undo restores order | unit | ids and order equal the original | restores at the end |
"""


def make_doc(tier="light", modules="none", revision=None, replace=None, drop=None, extra=""):
    meta = "design-meta: tier=%s modules=%s" % (tier, modules)
    if revision:
        meta += "\nrevision: %d" % revision
    sections = {
        "problem": "## Problem, goals and non-goals\nUsers cannot do X.\nNon-goals: Y.\n",
        "requirements": "## Requirements\n- R1: removing selected rows leaves the others.\n- R2: undo restores order.\n",
        "grounding": "## Grounding\nPattern at `src/a/store.ts:10-40`. Consumer at src/a/List.tsx:5.\nAlso src/a/Badge.tsx:9 and src/jobs/digest.ts:22-70.\n",
        "approach": "## Approach\nAlternatives: A is slower, B is chosen because it bounds calls.\n" if tier == "full" else "## Approach\nUse the existing store path.\n",
        "behaviour": "## Behaviour model\nn/a: no states or async work.\n",
        "interfaces": "## Interfaces and data shapes\nOne new field on the store.\n",
        "verification": "## Verification\n" + TABLE,
        "decide": "## May decide alone and must escalate\nMay decide: naming. Must escalate: any contract change.\n",
        "build": "## Build sequence\nStore then list.\n",
        "failure": "## Failure modes\nRequest fails: rows return.\n",
        "rollback": "## Rollback\nRevert the commit.\n",
        "open": "## Open questions\nNone.\n",
    }
    if "ui" in modules:
        sections["ui"] = "## UI module\nSurface states: none, selected.\n"
    if "risk" in modules:
        sections["risk"] = "## Risk module\nTime budget 5 s against p95 1.2 s.\n"
    for k, v in (replace or {}).items():
        sections[k] = v
    for k in drop or []:
        sections.pop(k, None)
    return "```\n%s\n```\n\n# Design\n\n%s%s" % (meta, "\n".join(sections.values()), extra)


def run(tmp_path, text, **kw):
    p = tmp_path / "design.md"
    p.write_text(text, encoding="utf-8")
    return dp.check(str(p), **kw)


def test_light_doc_passes(tmp_path):
    ok, problems, warnings = run(tmp_path, make_doc("light"))
    assert ok, problems
    assert problems == [] and warnings == []


def test_full_doc_with_modules_passes(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("full", "ui,risk"))
    assert ok, problems


def test_requirements_may_live_in_problem_section(tmp_path):
    text = make_doc("light", drop=["requirements"], replace={
        "problem": "## Problem, goals and non-goals\nNon-goals: Y.\n- R1: a.\n- R2: b.\n"})
    ok, problems, _ = run(tmp_path, text)
    assert ok, problems


def test_legacy_doc_without_header_fails_clearly(tmp_path):
    ok, problems, _ = run(tmp_path, "# Design\n\n## Problem\nx\n")
    assert not ok
    assert len(problems) == 1 and "design-meta" in problems[0] and "legacy" in problems[0]


def test_bad_tier_and_module(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light").replace("tier=light modules=none", "tier=none modules=net"))
    assert not ok
    assert any("tier must be" in p for p in problems)
    assert any("unknown module" in p for p in problems)


@pytest.mark.parametrize("key,label", [
    ("grounding", "grounding"), ("approach", "approach"), ("behaviour", "behaviour model"),
    ("interfaces", "interfaces"), ("verification", "verification"), ("decide", "may decide"),
    ("build", "build sequence"), ("failure", "failure modes"), ("rollback", "rollback"),
    ("open", "open questions"), ("requirements", "requirements"), ("problem", "problem"),
])
def test_missing_core_section(tmp_path, key, label):
    ok, problems, _ = run(tmp_path, make_doc("light", drop=[key]))
    assert not ok
    assert any("missing section: " + label in p for p in problems), problems


def test_empty_section_fails(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"rollback": "## Rollback\n\n"}))
    assert not ok and any("empty section: rollback" in p for p in problems)


def test_declared_module_section_required(tmp_path):
    text = make_doc("full", "ui,risk", drop=["ui", "risk"])
    ok, problems, _ = run(tmp_path, text)
    assert not ok
    assert "missing module section: ui" in problems
    assert "missing module section: risk" in problems


def test_empty_module_section(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("full", "risk", replace={"risk": "## Risk module\n"}))
    assert not ok and "empty module section: risk" in problems


def test_requirement_missing_from_table(tmp_path):
    table = TABLE.split("| R2")[0]
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"verification": "## Verification\n" + table}))
    assert not ok and any("requirement R2 has no row" in p for p in problems)


def test_r1_does_not_match_r10(tmp_path):
    table = TABLE.replace("| R2 |", "| R20 |")
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"verification": "## Verification\n" + table}))
    assert not ok and any("requirement R2 has no row" in p for p in problems)


def test_table_missing_columns(tmp_path):
    table = "| Id | Test |\n|---|---|\n| R1 | a |\n| R2 | b |\n"
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"verification": "## Verification\n" + table}))
    assert not ok
    msg = [p for p in problems if "missing columns" in p][0]
    assert "level" in msg and "wrong implementation caught" in msg


def test_no_table(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"verification": "## Verification\nTests exist.\n"}))
    assert not ok and "verification section has no table" in problems


def test_empty_wrong_implementation_cell(tmp_path):
    table = TABLE.replace("removes all rows", " ")
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"verification": "## Verification\n" + table}))
    assert not ok and any("empty wrong implementation caught cell" in p for p in problems)


def test_transition_without_row(tmp_path):
    bm = "## Behaviour model\n| Id | Transition |\n|---|---|\n| T1 | idle to busy |\n| T2 | busy to idle |\n"
    table = TABLE.replace("| R1 |", "| R1, T1 |")
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"behaviour": bm, "verification": "## Verification\n" + table}))
    assert not ok and any("transition T2 has no row" in p for p in problems)


def test_grounding_needs_citations(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"grounding": "## Grounding\nThe store handles it.\n"}))
    assert not ok and any("path:line citations" in p for p in problems)


def test_full_needs_three_citations(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("full", replace={"grounding": "## Grounding\nsrc/a.ts:1 only.\n"}))
    assert not ok and any("need at least 3" in p for p in problems)


def test_full_needs_alternatives(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("full", replace={"approach": "## Approach\nJust do it.\n"}))
    assert not ok and "full tier approach lists no alternatives" in problems


def test_problem_needs_non_goals(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"problem": "## Problem\nUsers cannot do X.\n"}))
    assert not ok and "problem section does not state non-goals" in problems


@pytest.mark.parametrize("word", ["TBD", "TODO", "..."])
def test_placeholders_fail(tmp_path, word):
    ok, problems, _ = run(tmp_path, make_doc("light", replace={"rollback": "## Rollback\n%s\n" % word}))
    assert not ok and any("placeholder" in p for p in problems)


def test_placeholder_inside_code_is_ignored(tmp_path):
    text = make_doc("light", replace={"rollback": "## Rollback\nRevert `git revert ...` or\n```\nTODO ...\n```\n"})
    ok, problems, _ = run(tmp_path, text)
    assert ok, problems


def test_vague_adjective_warns_but_passes(tmp_path):
    text = make_doc("light", replace={"requirements": "## Requirements\n- R1: the list is fast.\n- R2: undo is quick under 200 ms and robust (3 retries).\n"})
    ok, problems, warnings = run(tmp_path, text)
    assert ok, problems
    assert len(warnings) == 1 and "fast" in warnings[0]


def test_long_doc_and_code_warn(tmp_path):
    code = "```\n" + "x = 1\n" * 45 + "```\n"
    ok, _, warnings = run(tmp_path, make_doc("light", extra="\n" + code + "filler\n" * 200))
    assert ok
    assert any("fenced code" in w for w in warnings)
    assert any("soft limit" in w for w in warnings)


def test_revision_without_changes_section_fails(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", revision=2))
    assert not ok and any("Changes since review" in p for p in problems)


def test_revision_with_changes_section_passes(tmp_path):
    extra = "\n## Changes since review\n- NB1 adopted: added a retry row.\n- NB2 rejected: out of scope for this card.\n"
    ok, problems, _ = run(tmp_path, make_doc("light", revision=2, extra=extra), nb_ids=["NB1", "NB2"])
    assert ok, problems


def test_revision_one_needs_no_changes_section(tmp_path):
    ok, problems, _ = run(tmp_path, make_doc("light", revision=1))
    assert ok, problems


def test_nb_without_decision_fails(tmp_path):
    extra = "\n## Changes since review\n- NB1 noted.\n"
    ok, problems, _ = run(tmp_path, make_doc("light", revision=2, extra=extra))
    assert not ok and any("without adopted or rejected" in p for p in problems)


def test_unanswered_nb_fails(tmp_path):
    extra = "\n## Changes since review\n- NB1 adopted: done.\n"
    ok, problems, _ = run(tmp_path, make_doc("light", revision=2, extra=extra), nb_ids=["NB1", "NB3"])
    assert not ok and "Changes since review does not answer NB3" in problems


def test_unreadable_file(tmp_path):
    ok, problems, _ = dp.check(str(tmp_path / "nope.md"))
    assert not ok and "cannot read" in problems[0]


def test_cli_exit_codes(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(make_doc("light"))
    bad = tmp_path / "bad.md"
    bad.write_text("# old doc\n")
    r = subprocess.run([sys.executable, str(SCRIPT), str(good)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("ok")
    r = subprocess.run([sys.executable, str(SCRIPT), str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "design-meta" in r.stdout
