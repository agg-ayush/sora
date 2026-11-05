---
name: design-remediation-executability-check
description: "A design doc's operator-remediation step ('if X breaks, the operator can run Y to recover') must be verified by actually running Y against the real CLI/tool — not accepted on the strength of the doc's prose alone."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Review, Design, Verification, Tier-2]
    related_skills: [multi-round-review-convergence, tier2-orchestration]
---

# Design-doc remediation executability check

A design doc frequently includes a residual-risk section along the lines of
"this closes the primary case; for the remaining edge case (e.g. in-flight
runs, legacy state, a partially-migrated resource), the operator can
remediate by running `<command>`." A reviewer who reads only the prose and
checks it for internal consistency will approve this — the sentence reads
as a complete, reasonable answer. It can still be false: the named command
may not actually do what the sentence claims against the real tool.

## What actually happened (worked example)

A design closing a data-leak issue (turn-segmentation metrics reaching a
judge's scoring context) proposed, for runs already in-flight when the fix
ships, that the operator re-run the normalize step via `flow step` /
`flow resume` to purge the legacy artifact before the run resumed. Two prior
review rounds accepted this sentence as a satisfactory answer to "what about
runs already in flight." Round 3's reviewer instead **ran the actual CLI
commands** against a real run directory — `flow step` and `flow resume`
both failed with `workflow missing required params`, because the underlying
`loadWorkflow(workflow, cwd, {})` call is invoked with empty parameter
overrides for those two subcommands, and the evaluation workflow declares
required params. The proposed remediation was not executable as written,
full stop — not a documentation gap, a real product bug. It was filed as a
separate CLI bug (own repo, own issue) and the design's residual-risk
section was rewritten to state the honest scope limitation instead of a
false remediation path.

## The check

Whenever a design doc's risk/limitation section says an operator (human or
another automated step) "can run `<command>`" to resolve or remediate
something, before accepting that as closing the risk:

1. Identify the exact command/subcommand named.
2. Exercise it on an isolated, representative instance or an approved safe
   dry run, checking the actual CLI flags and end state. A potentially
   destructive remediation must **not** be run against live production merely
   to review a design. Source reading alone may miss default-value or
   empty-override behavior that surfaces at actual invocation.
3. If it fails, that failure is evidence the design's scope claim is false,
   not a tooling annoyance to route around — surface it as a genuine
   residual-risk finding (see `multi-round-review-convergence.md`'s
   convergence-vs-deadlock split: a remediation that turns out to be
   non-executable is architectural/genuine residue, not a narrow mechanical
   fix, so it should escalate for a human scoping decision rather than being
   patched around silently).
4. File the underlying tool bug separately from the design/PR whose review
   surfaced it — don't fold an unrelated CLI/engine defect into the design
   doc's own scope.

## Why this is a reviewer discipline, not a one-off

Every design review pass that stops at "does the prose make sense" rather
than "does the named remediation actually execute" will pass a design with
a false safety net. This is the same class of gap as "local-green does not
mean CI-green" and "reuse/extend brief needs an explicit reuse-audit
instruction" documented in `multi-round-review-convergence.md` — a generic
correctness read of the artifact doesn't catch it; an explicit executability
probe does. When briefing a design-review session (Codex/Sol or otherwise),
call out any operator-remediation claim by name and ask the reviewer to
execute it, not just read it.
