---
name: agent-orchestration-patterns
description: Advanced Tier-2 orchestration playbooks and patterns.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [Orchestration, Tier-2, Review, Rollout]
---

# Agent Orchestration Patterns

Umbrella for advanced Tier-2/Tier-1 orchestration scenarios that go past the standard PR lifecycle: adversarial review convergence, fix-loop rebase conflicts, and infra-migration rollout gating.

## When to Use

- A reviewer↔author loop (design review, code review) hit its round cap (usually 3) without `approved: yes` — decide **converge vs deadlock** rather than blindly run round N+1 or rubber-stamp escalate.
- Two PRs from the same fix-loop conflict on rebase — both iterations legitimately extended the same lines, so "ours" or "theirs" silently drops one fix.
- A task migrates a live production service (new host OS, new region, new runtime, new deployment topology, or a same-host ownership/lifecycle refactor with comparable blast radius) — decide whether PR approval is the real merge trigger or just a checkpoint.
- A human at the merge gate asks "what does this PR actually do" or pushes back that it "feels overcomplicated" — decompose the diff against the issue text instead of re-pasting the PR body.

## Procedure

### Multi-round review convergence vs deadlock (references/multi-round-review-convergence.md)

At the round cap, check the blocker trend:
- **Converged (safe to resolve without a human, no further round):** blocker count shrinking round-over-round (5→4→2); residue is narrow/mechanical (ordering, missing IaC attribute, config flag); reviewer supplied the exact prescribed fix. Action: apply the reviewer's fixes yourself, verified to review-round rigor, then proceed past the gate. Log what you changed and why.
- **Deadlocked (escalate):** blocker count flat/growing; residue is architectural (a design-direction question); author and reviewer genuinely disagree. Action: stop the loop, hand a human the convergent/divergent summary, don't spend round N+1.
- **Merge-gate pushback on scope/complexity:** walk `git show --stat` / `gh pr view --json files` file-by-file, tie each piece to a specific sentence in the original issue, name disproportion plainly by line count, and end with an explicit scope-cut option ("if part X is overkill, say so and I'll strip it").

### Fix-loop rebase conflict resolution (references/iterative-fix-loop-conflict-resolution.md)

1. Rebase in a scratch worktree (`git worktree add /tmp/rebase-<pr>.XXXXXX origin/<branch> --detach`), never the main checkout. Before starting, save the pre-rebase branch tip's conflicted files to `/tmp/theirs_final_<file>` via `git show <old-tip>:<path>` — that tip is usually the byte-for-byte oracle both sides are converging toward.
2. Do NOT eyeball-resolve or default to ours/theirs — a wrong pick silently drops one iteration's fix while tests stay green.
3. Spell out the **semantic invariant** to whoever resolves (self or delegate): what side A added, what side B added, ONE concrete end-to-end input both sides must still get right, and that conflicting test files get a union, not a pick.
4. Require the real test suite + linter, and `git push --force-with-lease` (never bare `--force`).
5. Verify yourself against the original real defect artifact for EACH side before merging — passing unit tests is not sufficient proof.

### Infra-migration staged rollout (references/infra-migration-staged-rollout.md)

Recognize the strict-gate signal: the human says "don't merge until we've proven it works for real", "keep the old system running in parallel", "give it a domain, run it under real usage, then decide", "I want it 100% accurate before we change production". Any of these overrides the default approve→merge path — PR approval becomes a checkpoint, not the finish line.

Exit bar before merge:
1. PR stays open/unmerged — it's a staging artifact.
2. Stand up the real target infra from the branch (actual host/container/service).
3. Give it a reachable staging endpoint.
4. Run the full e2e/smoke suite against the live staging deploy and drive real usage on it.
5. Keep the old production system live and untouched throughout.
6. Deliverable is a go/no-go cutover report, not a merge — actual merge + old-system retirement needs explicit follow-up approval.

## Pitfalls

- Treating round-cap as a single outcome — "not approved after 3 rounds" splits into converged (safe to resolve) vs deadlocked (escalate); the actions are opposite.
- Force-pushing without `--lease` when sibling fix-loop iterations are landing concurrently.
- Trusting a delegate's "conflict resolved, tests pass" without artifact-level verification against the original defect input.
- Answering merge-gate scope pushback by re-pasting the PR body — the human already read it; they want a plainer decomposition mapped to the issue text.
- Merging a migration branch on PR approval + green CI alone when the human invoked the strict-gate signal — live staging proof is the actual bar.
- Provisioning migration staging in a region without verifying access first — confirm with `aws ec2 describe-vpcs --region <region>` and check the target AMI/service is available there before committing to it.

## Verification

- For convergence calls: blocker-count trend is computed from the actual round artifacts, not vibes; residue is classified mechanical-vs-architectural with citation.
- For conflict resolution: re-run the specific failing input from EACH side's original defect report against the merged code and confirm both behave as designed; `git diff` against the saved `/tmp/theirs_final_*` oracle where one exists.
- For migration rollout: the go/no-go report cites real staging endpoint hits and e2e results, not just CI-green on the diff; the old system is confirmed untouched.

## References

- `references/multi-round-review-convergence.md` — full convergence/deadlock taxonomy, worked merge-gate pushback example.
- `references/iterative-fix-loop-conflict-resolution.md` — full rebase procedure, delegate briefing template.
- `references/infra-migration-staged-rollout.md` — provisioning technique notes (region/IAM/DNS checks), full cutover gate checklist.
