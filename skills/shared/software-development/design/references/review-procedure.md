# Design review procedure

One review round is one Opus session (`/design-review`). The parent session does the generalist review below and launches the design agents as parallel subagents. The parent merges everything into one verdict.

## Inputs (all required)

- design path (the `design-meta` block gives tier and modules)
- card text path
- binding inputs: the task, standing decisions and every file the task names. Every reviewer and every subagent gets them in full. A review without them produces false blockers.
- task directory and round number

Never open previous verdicts or review files from other rounds. The `Changes since review` section inside the design is part of the design and may be read.

## Generalist pass (the parent does this itself)

Do the steps in order.

1. **Own failure list first.** Read the card and binding inputs only. Write the ten most likely ways the change fails after release: states, races, two tabs or two actors, partial failures, stale or double sources of truth, consumers you would grep, input modes. Save the list in `<task-dir>/review/generalist-r<round>.md` before reading the design.
2. **Read the design**, then mark which of the ten it covers. The count is `own_failure_list_covered`.
3. **Verify citations.** Open at least five `path:line` citations from Grounding and confirm each claim against the code. If the design has fewer than five, open all of them. Any wrong claim is a finding. Also check the design for claims about existing code that carry no citation. Review that affirms a wrong claim is worse than none.
4. **Grep consumers.** For every changed component, helper, field, status value and string, grep the repo yourself and compare with the design's consumer table. A missing consumer or a consumer marked unchanged that must change is a finding.
5. **Audit the verification table.** For each row decide whether it would fail on the baseline code and on one plausible wrong implementation (name it). List every row that is conditional, tautological, string or class-name only, single-width, fixture-blind or renders a different component than the one under test. List requirements and transitions with no row.
6. **Challenge the approach** (full tier only). Name one alternative the design did not consider. Test the pick against it with evidence from the repo. This is the only stage where approach is judged. It is a finding only when the rationale is false, an alternative violates a binding input or the pick has an unaddressed cost. On light tier the approach is not challenged.
7. **Module check.** UI: every new control has an interaction contract, surface states are listed, sizes that matter have a test. Risk: failure-mode table, time budgets against measured latency, idempotency, rollback with data effects.
8. **Binding inputs.** A design that contradicts a binding input is HIGH. A reviewer finding that contradicts one is dropped.

## Finding rules

- Each finding has a design section, file:line evidence when it concerns existing code, the concrete failure and a required correction.
- Unproven claims are tagged `unverified` and cannot be HIGH.
- HIGH: the design as written produces wrong behaviour, a broken contract, a missed consumer or a check that cannot fail. MED: the implementer would have to guess on a contract-visible point.
- Approach preferences, naming taste and style are not findings. Approach is challenged only as in step 6.
- At most 7 blocking findings, ranked by severity. Anything beyond goes to non-blocking with the note `blocking-class, over cap`.

## Merge and dedupe (after the subagents return)

1. Read each agent's file at `<task-dir>/review/<agent>-r<round>.md`.
2. Group findings by design section. Findings with the same root cause become one finding with the strongest evidence and the sources noted (generalist, lens, bundle).
3. Re-verify any HIGH finding that came only from a subagent and carries no file:line you have read. Downgrade it to `unverified` if you cannot reproduce it.
4. Apply the cap of 7 blocking. Renumber B1, B2 and NB1, NB2. Card-rule or process conflicts (test scope, cleanup rules, tooling instructions) go to `card_rule_conflicts:` outside the cap. Every missing test or untested transition any agent named goes to `required_tests:` with its source agent. Every agent finding not merged into blocking or non-blocking goes to `other_findings:` with severity and source file. Nothing an agent found is dropped.
5. If an agent failed or returned no file, rerun it once. If it fails again, set the matching coverage fields to `unchecked` and note which agent is missing.

## Verdict

Write to `<task-dir>/design-review-r<round>.md`, exactly:

```
VERDICT
approved: yes|no
confidence: <0-100>
coverage:
  requirements_testable: yes|gaps
  grounding_verified: yes|gaps|unchecked
  behaviour_model: complete|gaps|missing|n/a
  verification_plan: discriminating|weak|missing
  modules: complete|gaps|missing|n/a
  own_failure_list_covered: <n>/10
blocking_issues:
- B1 [HIGH|MED] <issue, location, required correction>
nonblocking_suggestions:
- NB1 <suggestion>

card_rule_conflicts:
- C1 <conflict, card text it breaks, required change>
required_tests:
- T1 <test or transition that must have a test> (source: <agent>)
other_findings:
- O1 [HIGH|MED|LOW] <one line> (source: review/<file>.md)
```

A header line `note:` under `VERDICT` states that full agent findings are in `review/*.md` and that the author must address `required_tests` and read the agent files. The three lists follow the block; `- none` when empty. They never use F ids.

`approved: yes` only when there are no blocking issues. Write `- none` for an empty list.

Field meaning:
- `requirements_testable`: every requirement has a number, state or observable.
- `grounding_verified`: `yes` when at least five citations were opened and all held; `gaps` when any failed; `unchecked` when fewer than five could be opened.
- `behaviour_model`: `n/a` only when the design states why there are no states or async work and you agree.
- `verification_plan`: `discriminating` when every row fails on baseline or a named mutant; `weak` when some rows cannot fail; `missing` when there is no table.
- `modules`: `n/a` when `design-meta` lists none.

## Confidence rubric

- 90 to 100: all coverage fields clean, at least five citations verified, own list covered 8 of 10 or more, no unverified HIGH items.
- 70 to 89: coverage clean, but some items unverified or own list covered 6 or 7 of 10.
- Below 70: a coverage field is `gaps`, `missing` or `unchecked`, or a subagent is missing.
- Never above 70 if any coverage field is `gaps`, `missing` or `unchecked`.

## Amendment review

When the implementer reports a design gap, the author amends the affected sections and bumps `revision`. The review is one round, scoped to what changed.

- Inputs: the amended design, the gap payload (section, claim, observed reality), the card and binding inputs. Not the system guide and not previous verdicts.
- Review the changed sections and any section that cites them (consumer rows, verification rows, behaviour transitions).
- Check that the amendment fixes the reported gap against the observed reality, that frozen intent is untouched (otherwise stop and escalate to the owner), that the verification table gained rows for the new behaviour and that `Changes since review` is complete.
- Same verdict format. Unchanged sections are not re-opened unless the change invalidates them.
- Launch only the design agents whose area the amendment touches (the lens for any state or test change).
