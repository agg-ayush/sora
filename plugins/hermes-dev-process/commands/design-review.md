---
description: "One-session design review: generalist pass plus parallel design agents, one merged verdict"
argument-hint: "<design-path> card=<path> binding=<path> task-dir=<dir> round=<n> [tier=<light|full>] [modules=<ui,risk|none>] [precheck=skip] [amendment=<path>]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Agent", "Task"]
---

# Design review

Review one design in one session. You do the generalist pass yourself and launch the design agents as parallel subagents. You write one merged, deduplicated verdict.

Arguments: "$ARGUMENTS"

- `<design-path>`: the design document (first argument, required).
- `card=`: card text path. `binding=`: file with the binding inputs (standing decisions and every file the task names; the card text itself counts as binding). `task-dir=`: the card directory. `round=`: review round number (default 1). `amendment=`: path to the gap payload when this is an amendment review.
- `tier=<light|full>`, `modules=<ui,risk|none>` and `precheck=skip` override the design's `design-meta` header; the arguments win. Use them for legacy designs that have no header.
- Defaults: `binding` is the card text only, `task-dir` is the directory of the design, `round` is 1. Any `guide=` argument is ignored: design reviewers do not get the system guide.
- Missing `<design-path>`, or no tier from either the arguments or the header: stop and say which. Never ask a question beyond that; no human is present.
- Design skill files: use `~/.hermes/skills/software-development/design/` when it exists. Otherwise use `${CLAUDE_PLUGIN_ROOT}/../../skills/shared/software-development/design/` when that variable is set and the directory exists, then `~/hermes-setup/skills/shared/software-development/design/`. Call the resolved directory `<design-skill>`.

## Rules

- Read-only on the repository and the design. You write only files under `<task-dir>/review/` and `<task-dir>/design-review-r<round>.md`.
- Never open previous verdicts or review files from other rounds (`design-review-r*.md` other than the one you write, `review/*-r<other round>.md`). Pass nothing from them to subagents.
- Every subagent gets the same binding inputs you have, in full. Give paths, not pasted text.
- Each subagent finishes within 20 minutes. Keep your own pass within the same limit.

## Steps

1. **Resolve tier and modules, then run the pre-check.** Tier and modules come from the `tier=` and `modules=` arguments when given, otherwise from the first fenced block of the design (`design-meta: tier=<light|full> modules=<...>` and `revision`). With `precheck=skip` skip the pre-check. Otherwise run `python3 <design-skill>/scripts/design_precheck.py <design-path>`. If it fails, write nothing else: print the missing list and stop (the review round is not used).
2. **Launch the design agents in parallel, first.** In ONE message make all Agent calls (the tool is `Agent` in current Claude Code and `Task` in older versions) so they run concurrently while you work:
   - light and full: agent `design-lens`.
   - full only: agent `change-impact-bundle`.
   - Use the plugin agent names (`subagent_type` `hermes-dev-process:design-lens` and `hermes-dev-process:change-impact-bundle`; if the Agent tool does not accept that form use the bare names).
   - Prompt for each: the design path, card path, binding inputs path, repo path (current directory), round and the output path `<task-dir>/review/<agent>-r<round>.md`. Do not pass a system guide. Tell it to write full findings there and return a short summary.
   - Optional: when the design rewrites many user-visible strings and a `ce-doc-review` skill is available, run it as one more parallel subagent writing to `<task-dir>/review/ce-doc-review-r<round>.md`.
   - Amendment review: launch only the agents whose area the amendment touches and tell them to review the changed sections and the sections that cite them.
3. **Generalist pass yourself.** Load `<design-skill>/references/review-procedure.md` and follow its generalist steps in order, starting with your own ten-item failure list from the card and binding inputs only, saved to `<task-dir>/review/generalist-r<round>.md` before you read the design body. Use `references/design-contract.md` as the checklist for sections and `references/anti-patterns.md` for categories to probe. Navigate with graphify and Serena if present (`references/context-pack.md`); cite only what you read. Do not read a system guide.
4. **Collect.** Read each agent's findings file. A missing or empty file means that agent failed: rerun it once; if it fails again set the coverage fields it feeds to `unchecked` and cap confidence at 70.
5. **Merge and dedupe** per the procedure: group by design section, one finding per root cause with the strongest evidence, re-verify any HIGH finding you have not read yourself, cap at 7 blocking, renumber B and NB ids. Nothing an agent found may be lost:
   - Card-rule or process conflicts (test scope, cleanup rules, tooling instructions the design ignores) are not design defects. List them in `card_rule_conflicts:` outside the cap.
   - Every missing test or untested transition any agent named (the lens "Missing-transition tests" list, the bundle's testability gaps, your own) goes to `required_tests:`, one line each with its source agent. Do not merge or drop these.
   - Every agent finding that is in neither blocking nor non-blocking after merging goes to `other_findings:`, one line each with severity and source file. A finding folded into a merged one is not repeated.
   - Never copy an agent's reassurance (covered, not an issue) into the verdict unless the agent cited the design section and the test or `file:line` that covers it. Treat unverified claims as gaps.
6. **Write the verdict** to `<task-dir>/design-review-r<round>.md`: the VERDICT block in the format in `review-procedure.md` (VERDICT, approved, confidence, coverage fields, blocking_issues, nonblocking_suggestions), with one extra header line directly under `VERDICT`, then three lists after the block:

   ```
   VERDICT
   note: full agent findings are in review/*.md. The author must address every required_tests line and read the agent files. This verdict is a merged index, not the complete list.
   approved: ...
   (rest of the block unchanged)

   card_rule_conflicts:
   - C1 <conflict, card text it breaks, required change>
   required_tests:
   - T1 <test or transition that must have a test> (source: <agent>)
   other_findings:
   - O1 [HIGH|MED|LOW] <one line> (source: review/<file>.md)
   ```

   `approved` follows blocking issues only. Write `- none` for an empty list. Use O, C and T ids, never F ids.
7. **Return** only a short summary: approved, confidence, blocking count, non-blocking count, required_tests count, card_rule_conflicts count, verdict path and which agents ran.

Done when the verdict file exists, every coverage field is filled and no finding quotes code you did not read.
