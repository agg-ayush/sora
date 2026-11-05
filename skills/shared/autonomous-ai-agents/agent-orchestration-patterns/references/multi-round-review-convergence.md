# Multi-round review convergence

A review round is useful only when each blocking finding changes a concrete artifact or resolves a real decision. Keep a ledger per finding: exact file/line, claimed failure, reproducible evidence, owner, fix, verification, and disposition. Compare **the last round's substance** as well as blocker count: a shrinking count with a remaining architectural disagreement is not convergence; a flat count of narrow regressions may still be tractable. Do not unilaterally declare a reviewer wrong because its finding is inconvenient.

## Scope and handoff

- When the human questions a large PR, map the actual changed files and behavior back to the literal issue and accepted design. Identify unrequested fixes and independent concerns; do not restate the PR description as justification.
- Verify the brief's named component against the actual behavior/code before dispatch. If the requested behavior resides elsewhere, correct the target and scope first. Require a review of reuse/extension versus a parallel mechanism when reuse was an explicit requirement.
- Record a user clarification or change in the governing artifact and affected cards. If `clarify` does not deliver, retry once, then post a durable decision request and hold at the decision boundary; do not guess. A question is not consent to implement an option.
- A small, prescribed blocker can be returned to the **owning T2** for a focused amendment and verification. The supervisor must not directly edit the T2's design or source diff, even to bypass another review round. If a finding is a changed requirement or an architecture choice, ask the human; do not smuggle it into a 'mechanical fix.' At the round cap, classify *each* remaining finding (confirmed defect, disputed interpretation, new scope, question) rather than escalating a raw count.
- A minor reviewer finding alongside `approved` still requires explicit disposition. A late cross-task finding that affects this PR remains actionable after a previously green gate; reopen only the affected review/verification, preserving the original authorization boundary.

## Evidence before a green claim

Inspect the PR's exact pushed SHA, current CI conclusion, actual test body and raw evidence. A self-reported PASS can contradict the generated JSON/log; a suite called 'full-chain e2e' can use only fakes or assert that a mocked call occurred. For a lifecycle/ownership claim, run a real process, interrupt the coordinator, observe worker survival, state continuity and lock behavior, then separately exercise unattended triggers if they use another spawn path. Reuse the harness across rounds and record newly found defects and fixes. Add a fresh independent reviewer on high-risk changes; the author's own green report is not independent verification.

A local pass is not CI pass. Changes to a shared response shape or interleaved event frame can break repo-wide consumers and exact-count assertions; search all producers/consumers and rerun relevant integration suites. A residual defect after prompt-only edits may indicate a missing code-enforced constraint rather than a model limitation; test where the required behavior is actually enforced.

## Session diagnosis, not reflexive restarts

Check the board status, session status, tmux pane, process ownership, worktree and artifacts *before* steering or killing a slow reviewer. Distinguish: an authorized pause or round-cap escalation; live deliberation; repeated failing shell hooks; completed subagents with no verdict artifact; still-running subagents; a dead supervisor with recoverable dirty work; and an idle child after sleep/network loss. Choose a bounded intervention for the observed state. Never send an empty confirmation steer to a dialog; inspect the highlighted menu option first. Do not assume a duplicate tmux session name silently attaches: ordinary `tmux new-session -d -s <name>` fails when the name exists.

An expired board claim may coexist with a live task in `review`; inspect state and claim owner, then use the current CLI/API-supported `request-review` and state transition rather than old 'block as awaiting human' or blanket `reclaim` workarounds. Do not persist gateway credentials in a tmux command line to fix a missing env var; use the authorized secret source and a supported non-logging injection mechanism. Preserve uncommitted work before any recovery. A stale worktree path or plugin gate returning zero diff is a reason to inspect the actual branch-to-worktree mapping and diff, not proof that the worker made no changes.
