#!/usr/bin/env python3
"""Aggregate process v2 metrics across card directories. Read-only.

Scans <tasks-root>/t2-*/ for cards whose process.json has "version": 2 and
reads metrics.jsonl plus verdict files. Reports per card: tier, design and code
review rounds, amendments, minutes per stage and code-review findings by escape
label. The summary compares against the audit baseline (3.1 review rounds for
cards with design, 4.6 without) and, once at least 10 v2 cards exist, prints a
keep or drop hint per process piece.

Usage: process_metrics.py [--root DIR] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BASELINE_ROUNDS_WITH_DESIGN = 3.1
BASELINE_ROUNDS_NO_DESIGN = 4.6
BASELINE_DESIGN_ESCAPE_SHARE = 0.61  # audit: share of findings that were design-stage gaps
MIN_CARDS_FOR_HINTS = 10
LABELS = ("design", "impl", "test", "noise")

_FINDING_RE = re.compile(r"^\s*[-*]?\s*F\d+\b.*$", re.M)
_ESCAPE_RE = re.compile(r"\[escape:\s*(design|impl|test|noise)\s*\]", re.I)


def default_root() -> Path:
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(home) / "tasks"


def _ts(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _read_events(path: Path) -> list:
    events = []
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("event"):
            events.append(row)
    return events


def _detail(row: dict) -> dict:
    d = row.get("detail")
    return d if isinstance(d, dict) else {}


def _rounds(events: list, stage: str) -> int:
    starts = [e for e in events if e.get("stage") == stage and e.get("event") == "start"]
    distinct = {e.get("round") for e in starts if e.get("round") is not None}
    return len(distinct) if distinct else len(starts)


def _stage_minutes(events: list) -> dict:
    """Sum minutes per stage from end events (detail.minutes, else paired start/end timestamps)."""
    starts = {}
    for e in events:
        if e.get("event") == "start":
            starts[(e.get("stage"), _detail(e).get("task_id"), e.get("round"))] = _ts(e.get("ts"))
    minutes: dict = {}
    for e in events:
        if e.get("event") != "end":
            continue
        d = _detail(e)
        mins = d.get("minutes")
        if not isinstance(mins, (int, float)):
            t0, t1 = starts.get((e.get("stage"), d.get("task_id"), e.get("round"))), _ts(e.get("ts"))
            if t0 is None or t1 is None:
                continue
            mins = max(0.0, (t1 - t0) / 60)
        stage = str(e.get("stage") or "other")
        minutes[stage] = round(minutes.get(stage, 0.0) + float(mins), 2)
    return minutes


def _count_findings(text: str) -> dict:
    counts = {k: 0 for k in LABELS}
    counts["unlabelled"] = 0
    for line in _FINDING_RE.findall(text):
        m = _ESCAPE_RE.search(line)
        counts[m.group(1).lower() if m else "unlabelled"] += 1
    return counts


def _findings(card: Path, events: list) -> dict:
    """Verdict files are the source of truth; fall back to counts recorded in end events."""
    total = {k: 0 for k in LABELS}
    total["unlabelled"] = 0
    files = sorted(set(card.glob("review/*verdict*.md")) | set(card.glob("*verdict*.md")))
    parsed = False
    for f in files:
        try:
            counts = _count_findings(f.read_text("utf-8", errors="replace"))
        except OSError:
            continue
        if sum(counts.values()):
            parsed = True
            for k, v in counts.items():
                total[k] += v
    if not parsed:
        for e in events:
            f = _detail(e).get("findings") if e.get("event") == "end" else None
            if isinstance(f, dict):
                for k in total:
                    total[k] += int(f.get(k, 0) or 0)
    return total


def collect_card(card: Path) -> dict | None:
    try:
        proc = json.loads((card / "process.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(proc, dict) or proc.get("version") != 2:
        return None
    events = _read_events(card / "metrics.jsonl")
    minutes = _stage_minutes(events)
    amendments = [e for e in events if e.get("event") == "amendment"]
    amend_minutes = sum(float(_detail(e).get("minutes", 0) or 0) for e in amendments)
    refused = [e for e in events if e.get("event") == "refused"]
    return {
        "card": card.name[3:] if card.name.startswith("t2-") else card.name,
        "tier": proc.get("tier"),
        "kind": proc.get("kind"),
        "modules": proc.get("modules") or [],
        "design_review_rounds": _rounds(events, "design_review"),
        "code_review_rounds": _rounds(events, "code_review"),
        "amendments": len(amendments),
        "amendment_minutes": round(amend_minutes, 2),
        "minutes_by_stage": minutes,
        "findings": _findings(card, events),
        "refused": {
            "precheck": sum(1 for e in refused if _detail(e).get("reason") == "precheck"),
            "evidence": sum(1 for e in refused if _detail(e).get("reason") == "evidence"),
        },
    }


def _mean(values: list) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _hints(cards: list, s: dict) -> list:
    n = len(cards)
    if n < MIN_CARDS_FOR_HINTS:
        return [{"piece": "all", "hint": f"insufficient data ({n} of {MIN_CARDS_FOR_HINTS} v2 cards)",
                 "basis": "no keep or drop call before the sample is large enough"}]
    hints = []
    wd, nd = s["mean_code_rounds_with_design"], s["mean_code_rounds_no_design"]
    if wd is not None:
        keep = wd <= BASELINE_ROUNDS_WITH_DESIGN
        hints.append({"piece": "design stage (tiers light and full)", "hint": "keep" if keep else "drop or rework",
                      "basis": f"mean code-review rounds {wd} vs baseline {BASELINE_ROUNDS_WITH_DESIGN}"})
    if nd is not None:
        keep = nd <= BASELINE_ROUNDS_NO_DESIGN
        hints.append({"piece": "none-tier path", "hint": "keep" if keep else "raise tiers",
                      "basis": f"mean code-review rounds {nd} vs baseline {BASELINE_ROUNDS_NO_DESIGN}"})
    share = s["design_escape_share"]
    if share is not None:
        keep = share < BASELINE_DESIGN_ESCAPE_SHARE
        hints.append({"piece": "design review lenses", "hint": "keep" if keep else "drop or strengthen",
                      "basis": f"design-escape share of findings {share} vs baseline {BASELINE_DESIGN_ESCAPE_SHARE}"})
    for piece, key in (("design pre-check", "precheck"), ("RED/GREEN evidence gate", "evidence")):
        caught = s["refusals"][key]
        hints.append({"piece": piece, "hint": "keep" if caught else "keep only if it adds no measurable time",
                      "basis": f"{caught} refusal(s) across {n} cards"})
    amend = s["amendments"]
    hints.append({"piece": "amendment route", "hint": "keep" if amend else "no data",
                  "basis": f"{amend} amendment(s), {s['amendment_minutes']} min"})
    return hints


def summarize(cards: list) -> dict:
    with_design = [c for c in cards if c["tier"] in ("light", "full")]
    no_design = [c for c in cards if c["tier"] == "none"]
    findings = {k: sum(c["findings"].get(k, 0) for c in cards) for k in (*LABELS, "unlabelled")}
    total = sum(findings.values())
    s = {
        "cards": len(cards),
        "cards_with_design": len(with_design),
        "cards_no_design": len(no_design),
        "mean_code_rounds_with_design": _mean([c["code_review_rounds"] for c in with_design]),
        "mean_code_rounds_no_design": _mean([c["code_review_rounds"] for c in no_design]),
        "baseline_rounds_with_design": BASELINE_ROUNDS_WITH_DESIGN,
        "baseline_rounds_no_design": BASELINE_ROUNDS_NO_DESIGN,
        "mean_design_review_rounds": _mean([c["design_review_rounds"] for c in with_design]),
        "findings": findings,
        "design_escape_share": round(findings["design"] / total, 2) if total else None,
        "refusals": {"precheck": sum(c["refused"]["precheck"] for c in cards),
                     "evidence": sum(c["refused"]["evidence"] for c in cards)},
        "amendments": sum(c["amendments"] for c in cards),
        "amendment_minutes": round(sum(c["amendment_minutes"] for c in cards), 2),
    }
    s["hints"] = _hints(cards, s)
    return s


def collect(root: Path) -> dict:
    cards = []
    for card in sorted(Path(root).glob("t2-*")):
        if card.is_dir():
            row = collect_card(card)
            if row:
                cards.append(row)
    return {"cards": cards, "summary": summarize(cards)}


def _fmt(v) -> str:
    return "-" if v is None else str(v)


def render_markdown(report: dict) -> str:
    cards, s = report["cards"], report["summary"]
    out = ["# Process v2 metrics", ""]
    if not cards:
        out.append("No cards with process.json version 2 found.")
        return "\n".join(out) + "\n"
    out += ["| Card | Tier | Kind | Design rounds | Code rounds | Amendments | Minutes by stage | "
            "Findings d/i/t/n (unlabelled) |", "|---|---|---|---|---|---|---|---|"]
    for c in cards:
        mins = ", ".join(f"{k} {v}" for k, v in sorted(c["minutes_by_stage"].items())) or "-"
        if c["amendment_minutes"]:
            mins += f", amendment {c['amendment_minutes']}"
        f = c["findings"]
        out.append(f"| {c['card']} | {_fmt(c['tier'])} | {_fmt(c['kind'])} | {c['design_review_rounds']} | "
                   f"{c['code_review_rounds']} | {c['amendments']} | {mins} | "
                   f"{f['design']}/{f['impl']}/{f['test']}/{f['noise']} ({f['unlabelled']}) |")
    out += ["", "## Summary", "", "| Measure | Value | Baseline |", "|---|---|---|",
            f"| v2 cards | {s['cards']} (design {s['cards_with_design']}, none {s['cards_no_design']}) | |",
            f"| Mean code-review rounds, cards with design | {_fmt(s['mean_code_rounds_with_design'])} | "
            f"{BASELINE_ROUNDS_WITH_DESIGN} |",
            f"| Mean code-review rounds, cards without design | {_fmt(s['mean_code_rounds_no_design'])} | "
            f"{BASELINE_ROUNDS_NO_DESIGN} |",
            f"| Mean design-review rounds | {_fmt(s['mean_design_review_rounds'])} | |",
            f"| Design-escape share of findings | {_fmt(s['design_escape_share'])} | "
            f"{BASELINE_DESIGN_ESCAPE_SHARE} |",
            f"| Refusals (pre-check / evidence) | {s['refusals']['precheck']} / {s['refusals']['evidence']} | |",
            f"| Amendments | {s['amendments']} ({s['amendment_minutes']} min) | |",
            "", "## Keep or drop", "", "| Piece | Hint | Basis |", "|---|---|---|"]
    out += [f"| {h['piece']} | {h['hint']} | {h['basis']} |" for h in s["hints"]]
    return "\n".join(out) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=None, help="tasks directory (default $HERMES_HOME/tasks)")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args(argv)
    report = collect(args.root or default_root())
    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
