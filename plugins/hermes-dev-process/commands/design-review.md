---
description: "One-session design review: generalist pass plus parallel design agents, one merged verdict"
argument-hint: "<design-path> card=<path> binding=<path> guide=<path> task-dir=<dir> round=<n> [amendment=<path>]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Task"]
---

# Design review

Review one design in one session. You do the generalist pass yourself and launch the design agents as parallel subagents. You write one merged, deduplicated verdict.

Arguments: "$ARGUMENTS"

- `<design-path>`: the design document (first argument, required).
- `card=`: card text path. `binding=`: file with the binding inputs (standing decisions and every file the task names; the card text itself counts as binding). `guide=`: system guide path. `task-dir=`: the card directory. `round=`: review round number (default 1). `amendment=`: path to the gap payload when this is an amendment review.
- Missing required values: stop and say which. Never ask a question beyond that; no human is present.

## Rules

- Read-only on the repository and the design. You write only files under `<task-dir>/review/` and `<task-dir>/design-review-r<round>.md`.
- Never open previous verdicts or review files from other rounds (`design-review-r*.md` other than the one you write, `review/*-r<other round>.md`). Pass nothing from them to subagents.
- Every subagent gets the same binding inputs you have, in full. Give paths, not pasted text.
- Each subagent finishes within 20 minutes. Keep your own pass within the same limit.

## Steps

1. **Read the header and run the pre-check.** The first fenced block of the design holds `design-meta: tier=<light|full> modules=<...>` and `revision`. Run `python3 ~/.hermes/skills/software-development/design/scripts/design_precheck.py <design-path>`. If it fails, write nothing else: print the missing list and stop (the review round is not used).
2. **Launch the design agents in parallel, first.** In ONE message make all Task calls so they run concurrently while you work:
   - light and full: agent `design-lens`.
   - full only: agent `change-impact-bundle`.
   - Use the plugin agent names (`subagent_type` `hermes-dev-process:design-lens` and `hermes-dev-process:change-impact-bundle`; if the Task tool does not accept that form use the bare names).
   - Prompt for each: the design path, card path, binding inputs path, guide path, repo path (current directory), round and the output path `<task-dir>/review/<agent>-r<round>.md`. Tell it to write full findings there and return a short summary.
   - Optional: when the design rewrites many user-visible strings and a `ce-doc-review` skill is available, run it as one more parallel subagent writing to `<task-dir>/review/ce-doc-review-r<round>.md`.
   - Amendment review: launch only the agents whose area the amendment touches and tell them to review the changed sections and the sections that cite them.
3. **Generalist pass yourself.** Load `~/.hermes/skills/software-development/design/references/review-procedure.md` and follow its generalist steps in order, starting with your own ten-item failure list from the card and binding inputs only, saved to `<task-dir>/review/generalist-r<round>.md` before you read the design body. Use `references/design-contract.md` as the checklist for sections and `references/anti-patterns.md` for categories to probe. Navigate with graphify and Serena if present (`references/context-pack.md`); cite only what you read.
4. **Collect.** Read each agent's findings file. A missing or empty file means that agent failed: rerun it once; if it fails again set the coverage fields it feeds to `unchecked` and cap confidence at 70.
5. **Merge and dedupe** per the procedure: group by design section, one finding per root cause with the strongest evidence, re-verify any HIGH finding you have not read yourself, cap at 7 blocking, renumber B and NB ids.
6. **Write the verdict** to `<task-dir>/design-review-r<round>.md` in exactly the format in `review-procedure.md` (VERDICT, approved, confidence, coverage fields, blocking_issues, nonblocking_suggestions).
7. **Return** only a short summary: approved, confidence, blocking count, non-blocking count, verdict path and which agents ran.

Done when the verdict file exists, every coverage field is filled and no finding quotes code you did not read.
