#!/usr/bin/env python3
"""Card state helper for tier-2 process v2. Stdlib only.

  card_state.py init <card-dir> --tier none|light|full --kind <kind> --base <sha>
                [--modules ui,risk] [--design-path <abs path>]
  card_state.py raise-tier <card-dir> light|full [--design-path <abs path>]
  card_state.py set-design <card-dir> <abs path>
  card_state.py metric <card-dir> <stage> <event> [--round N] [--detail '<json>']

`init` writes process.json (refuses when one exists) and creates evidence/ and
review/. `raise-tier` only moves none -> light -> full. `metric` appends one
line to metrics.jsonl in the format the plugin and process_metrics.py read.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

TIERS = ("none", "light", "full")
KINDS = ("feature", "bugfix", "refactor", "test", "copy", "config")
MODULES = ("ui", "risk")
EVENTS = ("start", "end", "refused", "amendment")


def _load(card: Path) -> dict:
    return json.loads((card / "process.json").read_text("utf-8"))


def _save(card: Path, data: dict) -> None:
    tmp = card / "process.json.tmp"
    tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    tmp.replace(card / "process.json")


def metric(card: Path, stage: str, event: str, round_: int | None = None, detail=None) -> None:
    if event not in EVENTS:
        raise SystemExit(f"event must be one of {', '.join(EVENTS)}")
    row = {"ts": round(time.time(), 3), "stage": stage, "event": event,
           "round": round_, "detail": detail if detail is not None else {}}
    card.mkdir(parents=True, exist_ok=True)
    with open(card / "metrics.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def init(card: Path, tier: str, kind: str, base: str, modules: list[str], design_path: str | None) -> None:
    if (card / "process.json").exists():
        raise SystemExit(f"{card / 'process.json'} exists; use raise-tier or set-design")
    bad = [m for m in modules if m not in MODULES]
    if bad:
        raise SystemExit(f"unknown modules: {', '.join(bad)}")
    card.mkdir(parents=True, exist_ok=True)
    (card / "evidence").mkdir(exist_ok=True)
    (card / "review").mkdir(exist_ok=True)
    _save(card, {"version": 2, "tier": tier, "modules": modules, "kind": kind,
                 "design_path": design_path, "base_commit": base})
    metric(card, "triage", "end", None, {"tier": tier, "modules": modules, "kind": kind})


def raise_tier(card: Path, tier: str, design_path: str | None) -> str:
    data = _load(card)
    cur = data.get("tier", "none")
    if TIERS.index(tier) <= TIERS.index(cur):
        raise SystemExit(f"tier is {cur}; the tier can only be raised")
    data["tier"] = tier
    if design_path:
        data["design_path"] = design_path
    _save(card, data)
    metric(card, "triage", "end", None, {"raised_from": cur, "tier": tier})
    return cur


def set_design(card: Path, path: str) -> None:
    data = _load(card)
    data["design_path"] = path
    _save(card, data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("card")
    p.add_argument("--tier", choices=TIERS, required=True)
    p.add_argument("--kind", choices=KINDS, required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--modules", default="")
    p.add_argument("--design-path")
    p = sub.add_parser("raise-tier")
    p.add_argument("card")
    p.add_argument("tier", choices=TIERS[1:])
    p.add_argument("--design-path")
    p = sub.add_parser("set-design")
    p.add_argument("card")
    p.add_argument("path")
    p = sub.add_parser("metric")
    p.add_argument("card")
    p.add_argument("stage")
    p.add_argument("event", choices=EVENTS)
    p.add_argument("--round", type=int)
    p.add_argument("--detail", default="{}")
    a = ap.parse_args(argv)
    card = Path(a.card).expanduser()
    if a.cmd == "init":
        mods = [m for m in a.modules.split(",") if m]
        init(card, a.tier, a.kind, a.base, mods, a.design_path)
    elif a.cmd == "raise-tier":
        raise_tier(card, a.tier, a.design_path)
    elif a.cmd == "set-design":
        set_design(card, a.path)
    else:
        metric(card, a.stage, a.event, a.round, json.loads(a.detail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
