---
description: "One code review session: conformance against the design, quality agents and a mutation probe run as parallel subagents; writes the two-verdict file"
argument-hint: "<design-path|none> [range=<base>..<head>] [task_dir=<dir>] [round=<n>] [tier=<none|light|full>] [table=<path>] [brief=<path>] [repo=<path>]"
allowed-tools: ["Task", "Bash", "Read", "Write", "Glob", "Grep"]
---

# Card review

Review a card's diff in one session. Arguments: "$ARGUMENTS"

You are the parent. You launch the reviewers, merge their findings and write one verdict file. You do not review the code yourself except to spot-check a finding you are about to keep.

## 1. Inputs

First token is the design path, or `none` when the card has no design (tier none), in which case `brief=<path>` names the task statement that plays the design's role. The rest are `key=value` pairs. Resolve in this order:

| Input | Default |
|---|---|
| `repo` | current directory (the card worktree) |
| `task_dir` | directory of the design file; if that has no `evidence` folder, ask the caller |
| `tier` | `tier` in `<task_dir>/process.json`, else the `design-meta` line at the top of the design |
| `round` | 1 |
| `range` | round 1: `base_commit` from `<task_dir>/process.json`, then `..HEAD`. Round 2 or later: the sha in `<task_dir>/review/head-r<round-1>.txt` then `..HEAD` (the fix diff only). If a default is missing, stop and say which input is needed |
| `table` | section 6 of the design |

Then:
1. `mkdir -p <task_dir>/review`; write the current `git rev-parse HEAD` to `<task_dir>/review/head-r<round>.txt`.
2. `git diff --stat <range>` and `git diff --name-only <range>`. If the diff is empty, stop.
3. For round 2 or later also collect the accepted findings of the previous round from `<task_dir>/code-review-r<round-1>.md`; every reviewer gets them with the instruction to check each is fixed by a change with a reproducing test.
4. Classify the diff from the file list and a quick read: test files changed, error handling changed (try, catch, except, fallback, error branches), new or changed types, substantial new comments or docstrings, stateful behaviour (the design has a behaviour model, or the diff adds a latch, ref, gate flag, persisted state or restore path), behaviour changed (not only docs, copy, config, comments or types).

## 2. Launch reviewers in parallel

Send every Task call below in one message so they run concurrently. Use `subagent_type` with the plugin prefix (`hermes-dev-process:conformance-reviewer`, `pr-review-toolkit:code-reviewer`); if a prefixed name is rejected use the bare name.

| Agent | Launch when | Role |
|---|---|---|
| `hermes-dev-process:conformance-reviewer` | always | diff against design: missing, extra, misunderstood, boundaries, escalation, test quality, verification promises, changed assertions |
| `pr-review-toolkit:code-reviewer` | always | bugs, security, project guideline violations |
| `pr-review-toolkit:silent-failure-hunter` | error handling changed | swallowed errors, bad fallbacks |
| `pr-review-toolkit:pr-test-analyzer` | test files changed and tier is full | behavioural coverage gaps beyond the design table |
| `pr-review-toolkit:type-design-analyzer` | new or changed types | invariants a type fails to enforce |
| `pr-review-toolkit:comment-analyzer` | substantial new comments or docstrings | comments that are wrong or misleading |
| `pr-review-toolkit:state-transition-reviewer` | stateful behaviour | failure then retry, reset coverage, mid-flight change |
| `hermes-dev-process:mutation-probe` | tier is light or full and behaviour changed | at most 5 mutants in a throwaway worktree; never the card worktree |

Never launch `code-simplifier`: it rewrites code and offers approach opinions.

Every prompt contains: repo path, diff range, design path (or brief), verification table, task dir, round, tier, the accepted findings for round 2 or later, and the output rule. Give no review transcripts and no implementer notes.

Output rule for every agent: write full findings to `<task_dir>/review/<agent>-r<round>.md` (agent name without prefix), one finding per line as

`F<n> [BLOCKING|NONBLOCKING] [conformance|quality|tests|design-defect] [escape:design|impl|test] <file:line> | <concrete failure> | <required fix>`

Review the diff range only. Report only defects with a file:line and the concrete failure they cause. No approach preferences, naming, style or alternative designs. Return at most 10 lines: counts, the file path and the BLOCKING lines.

Mutation-probe is the only heavy reviewer: it runs test processes one at a time and at most 5 mutants. Do not launch a second test-running agent. The other agents are read-only.

## 3. Collect

After all agents return:
- If an agent returned an error or its file is missing, write its returned text to the file when it has findings, otherwise rerun that agent once. If it fails again record it under AGENTS as `failed` and continue; one failed agent does not fail the review.
- Read each findings file in full.

## 4. Merge

Build one finding list:
1. Parse every finding. Reject any without a file:line and a concrete failure (what input or action produces what wrong result). Count these as `dropped: unsupported`.
2. Drop approach preferences: renames, restructuring, style, "consider", "could be simpler", alternative libraries or designs, and anything contradicting the approved design's approach. Count as `dropped: approach`.
3. Deduplicate: findings on the same file:line or the same cause become one; keep the strongest severity and the most specific fix; list all source agents.
4. Severity gate. BLOCKING only for: a requirement missing or misunderstood, a behaviour transition without a test that can fail, a vacuous test, an unexplained weakened assertion, a must-escalate decision taken in code, a bug or security flaw with a concrete failing scenario, an error swallowed so that data or state is lost, a mutant that violates a requirement and survived. Everything else is NONBLOCKING. Keep at most 10 NONBLOCKING findings, most useful first.
5. Spot-check every BLOCKING finding: read the cited file:line yourself. If the claim does not hold, drop it (`dropped: unverified`) or downgrade it to NONBLOCKING with `unverified` in the failure text.
6. Assign the category for the verdict: findings in `conformance`, `tests` and `design-defect` decide the conformance verdict; findings in `quality` decide the quality verdict. Assign a missing escape label from the evidence: `escape:design` when the design was silent or wrong, `escape:impl` when the code departs from clear design text, `escape:test` for missing or weak tests, quality bugs the design could not have prevented are `escape:impl`. Do not emit `escape:noise`; noise is dropped.
7. Renumber F1, F2 and so on, BLOCKING first.

## 5. Write the verdict

Write `<task_dir>/code-review-r<round>.md` with exactly this block first, then the run notes:

```
VERDICT
conformance: pass|fail
quality: pass|fail
findings:
- F1 [BLOCKING|NONBLOCKING] [conformance|quality|tests|design-defect] [escape:design|impl|test] <file:line> | <concrete failure> | <required fix>

AGENTS
- <agent>: ok|failed|skipped (<reason>) | <blocking>/<nonblocking> | review/<agent>-r<round>.md
dropped: unsupported=<n> approach=<n> unverified=<n> duplicates=<n>
mutation: run=<n> killed=<n> survived=<n>
```

Rules: `conformance: fail` when any BLOCKING finding has category conformance, tests or design-defect; `quality: fail` when any BLOCKING finding has category quality; otherwise pass. With no findings write `findings:` followed by `- none`. A BLOCKING `design-defect` finding means the caller routes to the design amendment path, never to an ad hoc fix; say so in its required-fix field.

## 6. Report

Print the verdict block, the path of the verdict file and the wall time. Keep it short.
