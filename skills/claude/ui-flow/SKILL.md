---
name: ui-flow
description: End-to-end UI build workflow that chains the installed design skills (impeccable, ui-ux-pro-max, frontend-design, ui-styling, vercel-react-best-practices, vercel-composition-patterns, web-design-guidelines) through fixed phases and standing preferences in references/preferences.md, with scripted quality gates — setup, shape, build, refine, review, ship. Use when the user asks to build a new UI/page/screen/app from scratch, run "the UI flow", or wants a guided design-to-ship process. Accepts an optional phase to jump to (setup | shape | build | refine | review | ship) and a target.
user-invocable: true
argument-hint: "[setup|shape|build|refine|review|ship] [target or feature description]"
---

# UI Flow

A fixed pipeline over the installed design skills. Creative work stays with those skills (invoke them with the Skill tool, e.g. `Skill(impeccable:impeccable, "shape pricing page")`); **what runs, in what order, and when a phase is finished is decided by the gate script, not by judgement.**

`GATE` below means: `python3 -I ~/.claude/skills/ui-flow/scripts/gate.py` run from the project root. Exit 0 = PASS, 1 = FAIL, 2 = usage/tool error. State is in `.ui-flow/state.json`.

## Start

1. Run `GATE status`. Its `phase` is where you start, unless the user passed a phase argument — then run `GATE set-phase <that phase> --force` and start there.
2. Tell the user in one line: phase and why (copy `reason`).
3. Every phase below has **Do**, **Exit gate**, **On fail**. Never move to the next phase until its exit gate passes. Record each transition with `GATE set-phase <next>` (which mechanically verifies the current phase's exit gate before advancing).
4. If PRODUCT.md or DESIGN.md are git-excluded in the main checkout, copy them into the working copy/worktree before starting; never commit those copies.

## Preferences

Read `references/preferences.md` at the start of **shape**, **build**, and **review**. Its P1–P12 preferences rank below only the user's explicit brief, above project documents and the individual style skills.

## Phases

### setup
- **Do:** `impeccable` → `init`. If the project already has styling, also `impeccable` → `document`. Then `ui-ux-pro-max` for style, palette and font pairing; write the chosen values into DESIGN.md (tokens, fonts, colors). For mockups, concepts and throwaway comparisons, follow P12: keep styling plain and skip the palette/font step.
- **Exit gate:** `PRODUCT.md` and `DESIGN.md` both exist (`GATE status` → `artifacts`).
- **On fail:** finish whichever file is missing. Do not proceed without it.

### shape
- **Do:** Read `references/preferences.md`; `impeccable` → `shape <feature>`. Write a brief with headings **Primary actions**, **Secondary actions**, **Pages** (what goes on each page), **States** (loading, empty, error, partial, disabled, success), and **Preferences** (P1–P12, each with how it applies or why not applicable). A scan alone never counts as running the flow.
- **Exit gate:** `GATE brief <brief.md>` → `PASS`; the user approves the brief unless they asked for a full unattended run.
- **On fail:** fill the missing headings or preference entries; re-ask if needed.

### build
- **Do:** Read `references/preferences.md`; `impeccable` → `<feature request>` (plain new work; never `craft`). For React/Tailwind/shadcn stacks also load `ui-styling`, `vercel-composition-patterns`, `vercel-react-best-practices`. Render and screenshot at 390px, 1280px, 1440px and 1920px; make use of the wide layout without sacrificing readable prose.
- **Exit gate:** it renders without console errors at all four widths, and `GATE detect <target> --mobile --wide` has been run once (the result seeds refine; it does not need to pass here).
- **On fail:** fix render errors first.

### refine
- **Do:** Run `GATE detect <target> --mobile --wide` and `GATE lint <source files/dirs of the screens touched>`. Run **exactly** the `impeccable` sub-commands listed in `commands`, in that order, each scoped to `findings_by_command`; do not add or skip commands. Fix lint findings, or suppress a line with an inline `ui-flow-ignore` comment stating the reason. Re-render and repeat both gates.
- Optional, only if the user explicitly asks: `bolder`, `quieter`, `delight`, `animate`, `overdrive`, `live`, `generate`. These are taste calls and are never picked automatically.
- **Exit gate:** `GATE detect` → `PASS` (no warning/error findings) **and** `GATE lint` → `PASS`.
- **On fail:** loop refine. `GATE set-phase refine` increments the round counter; after 3 rounds (`refine_rounds_left: 0`) show the remaining findings and let the user decide whether to fix or explicitly accept detector findings (`GATE set-phase review --force`). Lint must still PASS; do not force past lint failures.

### review
- **Do:** Read `references/preferences.md`; `impeccable` → `critique <target>`. Take the total, applicable max, and P0 count from its report and run `GATE critique <score> <max> <p0>`. Fix any P0/P1 issues it names (use `harden` only if critique flagged accessibility/edge-case P0/P1s). Then check **every** P1–P12: mark pass, fail or n.a. with one line of evidence each; run `GATE prefs <failed> <checked>` (`checked` must equal 12; any other count is a usage error).
- **Exit gate:** `GATE critique` → `PASS` (score ≥ 75% of applicable max, 0 P0), `GATE prefs` → `PASS` (no failed preference), and a fresh `GATE detect <target> --mobile --wide` → `PASS` and `GATE lint <source files/dirs of the screens touched>` → `PASS` after fixes. Any preference failure blocks regardless of critique score.
- **On fail:** fix the critique or preference failures, then go back to **refine** (`GATE set-phase refine`), which counts against the same 3-round budget. Never force past a preference failure.

### ship
- **Do:** `impeccable` → `polish <target>`, then run final `GATE detect <target> --mobile --wide` and `GATE lint <source files/dirs of the screens touched>`. Optionally `impeccable` → `extract` if the user wants reusable tokens/components moved into the design system.
- **Exit gate:** final detect and lint → `PASS`, and `last_critique` and `last_prefs` → `PASS`.
- **On pass:** `GATE set-phase done`.

## Rules

- One phase per turn unless the user asked for a full run. End each phase with: phase name, gate verdict, 2–4 lines on what changed, next phase.
- For another screen in the same project: `GATE set-phase shape` (resets the refine budget and brief, lint and preference verdicts), then loop shape → ship.
- When style skills disagree, the user's explicit brief, `references/preferences.md`, PRODUCT.md and DESIGN.md win, in that order.
- Never edit `.ui-flow/state.json` by hand; only through `GATE`.
- Never pass `--force` to `GATE set-phase` unless the user explicitly jumped phases or explicitly accepted detector findings after the 3-round budget; never use it to bypass lint or preferences.
- If the gate script errors (exit 2), report stderr to the user and stop.
