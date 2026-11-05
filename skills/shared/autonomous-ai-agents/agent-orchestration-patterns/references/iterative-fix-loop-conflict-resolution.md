---
name: iterative-fix-loop-conflict-resolution
description: "Resolve rebase conflicts between sibling fix-loop PRs."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Git, Merge-Conflict, Tier-2]
    related_skills: [tier2-orchestration, merge-reconciler, github-pr-workflow]
---

# Iterative Fix-Loop Conflict Resolution

An "iterate until green" defect loop (drive a QC/test suite to a clean pass by
fixing one failure class at a time, rerunning, and repeating) routinely
produces MULTIPLE PRs against the SAME evolving function or check — iteration
N adds a check, iteration N+1 (built in parallel, or merged out of order)
refines the exact same lines. Rebasing the second onto the first-merged one
then hits a REAL conflict: two genuinely different edits to the same region,
not a mechanical whitespace clash.

This is a narrower, common case of what `merge-reconciler` handles generically
— codify the loop-specific version here since `merge-reconciler` and
`tier2-orchestration` are both bundled/protected and can't be edited directly.

## When to use

Use whenever a fix loop's iteration-N PR conflicts with iteration-(N-1)'s PR on
rebase, or any two PRs from the same defect-elimination campaign collide on
overlapping hunks. Do NOT use for a single agent's own straightforward
conflicts or generated-file conflicts — regenerate those instead.

## Recognizing the signal

- You are mid fix-loop (fix → merge → rerun → analyze → next fix) on one
  component/check.
- Two PRs from that loop touch the same file/function, and merging the first
  makes the second's rebase or merge report a real conflict (not auto-resolved).
- The conflicting hunks are typically the SAME check/validator function each
  iteration extended — e.g. one iteration added attribute-reading logic,
  the next added value-resolution logic, on the same lines.

## Procedure

1. **Rebase in a scratch worktree**, never the main checkout:
   `git worktree add --detach "$TMPDIR/rebase-<pr>" origin/<branch>`, then
   `git rebase origin/<updated-base>`. Check the path does not exist before use.
   Record the pre-rebase tip SHA and save conflicted file versions in isolated
   scratch paths. That tip is a comparison input, **not automatically a known-good
   oracle** for the merged result; both sides' intended behavior must survive.
2. **Do not resolve it yourself by eyeballing the diff alone**, and do not
   default to "theirs" or "ours" by habit — a wrong pick silently drops one
   iteration's fix while looking clean (tests can still pass if the dropped
   behavior wasn't the one they cover). Self-resolution (no delegate) is
   acceptable, and can beat delegating, when you already hold both sides'
   full diffs/intents from your own exploration this session AND you verify
   the result against both sides' stated invariants, the real defect inputs,
 and a focused test suite. A pre-rebase tip is useful as a comparison,
 but cannot certify a merged tree that includes new base behavior.
   Delegate instead when you do NOT already have that context, or the
   reference tip isn't recoverable.
3. **If self-resolving, or briefing a delegate, spell out the semantic
   invariant** — never "resolve the conflict." Either way, state:
   - What behavior side A (the base, already merged) added.
   - What behavior side B (being rebased) added.
   - ONE concrete end-to-end example the merged code must still get right —
     ideally the actual input/artifact that originally exposed the defect
     each side was fixing (e.g. "given SVG `<tspan fill=\"#800080\">8</tspan>`
     and description '\"8\" shown in purple', the merged check must still fail
     with a purple-mismatch reason").
   - Both conflicted files if a test file conflicts alongside the source file
     — instruct a union of both sides' tests, not a pick.
4. **Require the delegate to run the component's real test suite + linter**
   after resolving, not just report "resolved". If the authorized branch
   requires a history rewrite, verify its remote head and obtain appropriate
   approval before `git push --force-with-lease`; never use bare `--force`.
5. **Verify yourself against the original real defect artifact** before
   merging — not a synthetic reproduction, the actual file/output that
   surfaced the original bug for EACH side. Passing unit tests is not
   sufficient proof; the only real check is re-running the specific input
   that used to fail for both iterations and confirming both now fail/pass as
   designed.
6. Only merge once step 5 passes on the real artifacts, not the delegate's
   self-report.

## Pitfalls

- Trusting "conflict resolved, tests pass" from a delegate without your own
  artifact-level check — tests can stay green while one side's actual fix is
  silently reverted (e.g. the merged code no longer reads the newer of two
  attribution mechanisms).
- Rebasing without restating the semantic invariant — a bare "fix this
  conflict" delegation reproduces the generic-agent bias merge-reconciler
  exists to avoid: the resolver defaults to whichever side is easier to read,
  not whichever side the original defect required.
- Force-pushing without `--lease` when the loop has other iterations landing
  concurrently on the same branch.

## Related skills

- `merge-reconciler` — the general neutral-third-party conflict resolution
  pattern this specializes for the fix-loop case (bundled; read for the
  hunk-classification framework, don't expect to edit it).
- `tier2-orchestration` — owns the fix-loop's PR lifecycle (merge, rerun,
  escalate); this skill activates when its rebase step hits a real conflict.
