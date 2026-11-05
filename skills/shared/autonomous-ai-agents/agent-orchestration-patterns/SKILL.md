---
name: agent-orchestration-patterns
description: Coordinate agent reviews, rollouts, and recovery safely.
metadata:
  hermes:
    tags: [Orchestration, Tier-2, Review, Rollout, Tool-Evaluation]
---

# Agent orchestration patterns

Use for a live multi-agent build with review rounds, shared worktrees, a staged cutover, or a disputed worker/status report. The owning Tier-1/Tier-2 skill defines roles and merge authority; these references cover exceptional cases. Do not convert a check or an idle worker into merge authorization.

## Operating rules

1. For status, read the board **and** live worker/child state, the actual worktree and pushed head, and PR checks/review on that exact head. A heartbeat proves a supervisor is alive, not that its child is progressing. Correct a stale green claim when the head changes. Give a concrete user-facing progress line, not a kanban-column paraphrase.
2. Before fixing red CI in a PR, reproduce the same failure on a clean base at the relevant commit and inspect the base workflow history. Search for an existing tracking card. If it is an independently owned base failure, record that blocker and avoid silently widening this PR. Do not discard uncommitted changes to park work: checkpoint or get explicit approval first.
3. Send design/code changes back to the owning worker, even if the fix seems mechanical. A reviewer stays independent. On a long-running task, retain an author/implementer session when useful, but restart on actual death, exhausted context, or a deliberate phase checkpoint. Verify tool receipts and externally changed state yourself.
4. A dispatcher-served kanban board owns claims and worker spawns. Assign a card and confirm its claim rather than hand-spawning an untracked competing worker. For a stale card, first read its exact status/run and determine whether a worker or PR is still active; use supported CLI state transitions, not an old claim/reclaim workaround. Stop or replace only the affected authorized workstream, preserving its branch and dirty worktree.
5. Scope merge, cutover, rollback, incident stops, and security-sensitive actions to the user's authorization. An open PR with green checks is not permission to merge. An infrastructure migration with an explicit validation gate keeps the old service live until separately approved cutover.

## Load the relevant reference

- Review/design: `references/multi-round-review-convergence.md`, `references/design-review-parallel-dispatch.md`, `references/design-review-trust-asymmetry.md`, `references/design-remediation-executability-check.md`, `references/directed-gap-analysis-audits.md`, `references/session-retention-across-phases.md`, `references/requirement-correction-rework.md`, `references/premature-closure-in-decision-conversations.md`, `references/decision-record-tracker-mechanics.md`.
- PR/worktree/CI: `references/iterative-fix-loop-conflict-resolution.md`, `references/scope-creep-and-baseline-verification.md`, `references/worktree-provenance-verification.md`, `references/already-resolved-task-verification.md`, `references/issue-coupling-consolidation.md`, `references/issue-to-fix-location-mismatch.md`, `references/repo-targeting-before-dispatch.md`, `references/ad-hoc-fixture-verification.md`.
- Workers and board: `references/t1-card-decomposition-and-decision-relay.md`, `references/kanban-board-watcher-pattern.md`, `references/background-conductor-pattern.md`, `references/claude-orchestrate-plugin-mechanics.md`, `references/claude-orchestrate-permission-prompts-and-crash-retry.md`, `references/codex-launcher-instant-death.md`, `references/parallel-batch-execution.md`, `references/when-not-to-delegate-research.md`.
- Deploy/incident: `references/infra-migration-staged-rollout.md`, `references/deploy-pipeline-and-demo-ops.md`, `references/incident-firefight-orchestration.md`, `references/orchestration-retrospective-forensics.md`, `references/playwright-hard-to-simulate-conditions.md`, `references/handoff-brief-config-not-code.md`.
- Tool adoption and hiring evaluation: `references/agent-tool-adoption.md`, `references/tool-evaluations.md`, `references/hiring-eval-report-generation.md`, `references/hiring-eval-verification.md`.

## Practical verification

Check source commands with the installed `--help` and current official docs; plugin internals and board semantics can change. `hermes kanban --board <name> <subcommand>` puts the board flag before the subcommand. Resolve state paths through the active `$HERMES_HOME`/project context, not a hard-coded host path. Secret values belong in an authorized secret store, never a shell launch string, transcript, or chat. When tools are unavailable, report the limitation rather than inventing an outcome.
