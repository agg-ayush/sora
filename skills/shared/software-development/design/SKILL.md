---
name: design
description: Triage, write and review a decision-level design.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [design, triage, design-review, process, tier2]
    related_skills: [tier1-suborchestration, tier2-orchestration]
---

# Design Skill

Stages 1 to 4 of the card process: triage, grounding, design, design review, plus amendments. The design is a decision-level guidebook: what to build, the interfaces and states, the tests that prove it and what the implementer may decide alone. It does not cover implementation, code review or merge (tier-2 orchestration owns those).

## When to Use

- Tier 1 is triaging a card, or tier 2 is deciding whether a card needs a design.
- Authoring a design, reviewing one or amending one after the implementer found a gap.
- Not for: personal brainstorming, throwaway spikes (use `spike`) and cards triaged `none`.

## Stage flow

| # | Stage | Who | Output | Done when |
|---|---|---|---|---|
| 1 | Triage | Tier 1 (tier 2 may raise) | `design: none, light or full` plus modules, `process.json` | tier recorded, rules in `references/tiers.md` |
| 2 | Grounding | Read-only explorer subagent, launched by the author at the start of its session (light and full) | existing patterns, every consumer, covering tests with file:line | consumer list found by grep, test list saved as `evidence/test-impact.txt` |
| 3 | Design | Opus author | design doc per `references/design-contract.md` | `scripts/design_precheck.py` prints `ok` |
| 4 | Design review | `/design-review` (one Opus session) | verdict per `references/review-procedure.md` | `approved: yes`, or 3 rounds used and escalated |
| 5 | Amendments | Author, then one scoped review | revised design with `Changes since review` | amendment review approved, or escalated if scope changed |

Tier none skips stages 2 to 4. Light and full run all five; full adds alternatives, the change-impact bundle and an owner summary.

## References

- `references/tiers.md`: none, light, full rules, modules, re-tiering, how to write `process.json`.
- `references/design-contract.md`: required sections, behaviour model, verification table, may-decide and must-escalate, UI and risk modules, amendments.
- `references/review-procedure.md`: generalist review steps, verdict format, confidence rubric, merge and dedupe, amendment review.
- `references/context-pack.md`: what each role gets, graph and symbol tools, the bias rules.
- `references/anti-patterns.md`: the failure categories designs and reviews keep missing, with examples. Read once before authoring or reviewing.
- `scripts/design_precheck.py <design.md>`: structural check. Exit 0 prints `ok` plus warnings; exit 1 lists what is missing.

## Rules every design session follows

1. Every claim about existing code cites `path:line` read in this session. The context pack is for navigation, not evidence.
2. Consumer and call-site lists come from grep, never from the graph alone. Mark each consumer changing or unchanged.
3. Name decisions, not code. A design longer than the code it describes has written the code instead.
4. Every requirement and every behaviour transition has a verification row naming the wrong implementation it must catch.
5. Run the pre-check before asking for review. A pre-check failure goes back to the author and does not use a review round.
6. Reviewers get the card text, binding inputs (standing decisions and files the task names), the design, the system guide and the tools. They never get previous verdicts or the author's reasoning outside the doc.
7. At most 3 design review rounds per card. Unresolved after the third: escalate with the latest doc and the open blockers.
8. Every non-blocking suggestion gets a written answer in `Changes since review` (adopted or rejected with a reason). Adopted ones become acceptance criteria in the implementation brief.
9. Tier may be raised, never lowered. NEEDS_CONTEXT or BLOCKED from the implementer because the task is bigger than designed re-tiers the card.
10. Problem, goals, non-goals and requirements are frozen intent. An amendment that changes any of them goes to the owner.

## Procedure for tier 2

1. Read the tier and modules from the card (tier 1 comment) and write `process.json` (see `references/tiers.md`). Tier none: stop here.
2. Hand the author `references/design-contract.md` and `references/anti-patterns.md`. The author runs grounding first by launching the explorer as a subagent in its own session (no separate grounding session), saves `evidence/test-impact.txt` from its output, then writes the design.
3. Author writes `<card dir>/design.md` starting with the `design-meta` block. Run `scripts/design_precheck.py`; loop with the author until `ok`.
4. Run `/design-review <design.md>` with the inputs listed in `references/review-procedure.md`. Read only the verdict file.
5. `approved: no`: send the blocking issues to the author, who revises in place, bumps `revision` and answers every id in `Changes since review`. Pre-check again with `--nb <ids from the verdict>`, then a fresh review. `approved: yes`: send the non-blocking answers on to the implementer's brief.
6. Attach the accepted design to the card and give the implementer the design, the test-impact map and the system guide path.
7. When the implementer returns a design gap (section, claim, observed reality): send it to the author for a scoped amendment, one amendment review round, then resume. Scope change goes to the owner.

## Pitfalls

- Treating "the exact fix is given" as a reason for tier none. The fix says what to change, not what it touches.
- Letting the design restate the diff. Interfaces and states belong in the doc; function bodies do not.
- A behaviour model written only for the happy path. Every state needs failure, retry, repeat, cancellation and identity change rows.
- A verification table of tests that pass on the baseline code. Each row must fail on the baseline or on a named wrong implementation.
- Giving a reviewer the previous verdict. It anchors the next round on the old findings.

## Verification

- `design_precheck.py` prints `ok` on the design before the review starts.
- `<task-dir>/design-review-r<round>.md` exists and has every coverage field filled.
- `Changes since review` answers every non-blocking id from the last verdict.
- `process.json` exists with `"version": 2` and the tier matches the design-meta block.
