---
name: pr-verification-audits
description: Audit diff hygiene, verify fixes, and triage PR issues.
metadata:
  hermes:
    tags: [review, diff, testing, git, QA]
---

# PR Verification and Audits

This skill provides procedures for verifying code changes during or after a coding session, especially when doing autonomous AI-driven development.

## Always-on review checks (every PR, before approve/merge)

1. **No magic numbers.** Every duration/limit/threshold literal in the diff must be a named constant whose name carries the unit and whose value shows the derivation (`RETENTION_WINDOW_HOURS = 30 * 24`, not `720`). Tests assert the same derivation, not a repeated bare literal — a bare literal hides intent and gives two places to drift.
2. **Third-party API shapes verified against the vendor's live docs.** For any request field/endpoint sent to an external API, fetch the vendor's current reference page and compare field path, type, units and allowed values. Internal consistency between code and its own tests proves nothing — both can encode an invented field. Put the doc URL in the review note or PR body as evidence.
3. **Tests assert behavior, not current state or borrowed content.** Reject a diff whose tests (a) hardcode values that change with normal work (migration counts, catalog sizes, a specific live/published record), since the next ordinary change turns CI red for no defect; derive the value (count the migrations dir) or resolve it at runtime from a stable source; or (b) vendor real product content (assignment statements, prod docs, copies of another repo's files) as fixtures. Parser/renderer tests want a handful of hand-written synthetic edge-case fixtures, one per shape that matters (nesting, malformed input, injection vectors). Vendored content inflates the diff by thousands of lines, duplicates a source of truth that drifts, and couples this repo's CI to another repo's edits. Smoke/e2e suites never pin a mutable prod record and never write to the prod DB to set up their own preconditions; pick from what the live API already reports (e.g. the first currently-published item). Before telling the user a fix is covered, check that the e2e/smoke leg exercises the fixed path itself; a leg that passes via an override, bypass or fail-open proves nothing about the fix, so card a real-path test (with a negative control) before the next live run depends on it.
4. **Route fixes to the owning worker.** When the user says "have it change it", the change goes to the card/worker that owns the branch as a concrete steer (plus any verification ask as an explicit deliverable with evidence); the orchestrator patching the worktree itself breaks the one-writer rule. Only hand-patch when the user explicitly asks you to.

See the linked references for specific verification tasks:
- `references/coding-agent-diff-hygiene-audit.md`
- `references/fix-verification-audit.md`
- `references/lint-format-baseline-triage.md`
- `references/no-test-suite-verification.md`
- `references/scope-proportionality-audit.md`
- `references/pr-description-style.md` (Writing collaborator-facing PR descriptions)
