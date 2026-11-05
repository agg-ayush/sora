# T1 card decomposition and decision relay

On a dispatcher-served board, the **card is the durable handoff**: name the assignee profile, exact repo/base/worktree, scope, acceptance criteria, dependencies, and merge/stop authority. Confirm an actual claim/run; do not hand-spawn a second worker. If a card with an existing PR is not being claimed, inspect the dispatch guard and active worker before deciding whether to make a continuation card. Do not strip a PR link or archive a worktree to bypass a guard blindly.

## Split and recover

- Re-read the accepted architecture and map every required module to a card. Independent PRs get independent clean base ancestry, with a separate integration card owning shared wiring; mock another team's published contract rather than implementing their system. A merged child is not proof it is in the parent branch: inspect the parent's actual head and files.
- A retry notification is not proof of permanent death. Read the latest run/events, process and child-session state, branch HEAD, dirty files, and pushed PR. A fresh heartbeat from a T2 does not prove its coder is making progress. If a retry already owns the worktree, do not start another writer.
- For a replacement card, preserve the same branch/worktree and record exact remaining work and latest pushed/dirty state. Transfer dependency links, watcher coverage, and any scheduled supervision brief. Check whether archiving the predecessor triggers a worktree reaper; verify the worktree remains intact before changing status. Do not discard local-only work or assume an old PID still identifies the same process.
- For blocked or triage cards, read latest comments, live dependencies, and review findings. Move genuine deferred hardening behind the release card without stopping its worker unless requested; unblock false or obsolete dependencies with a reason. A reviewer exhausted by repeated findings needs an explicit new review plan, not a waived gate.

## Decisions, scope, and authority

- Ask only unresolved questions. A user-supplied mockup/contract overrides older heuristics. Put the settled decision and what it supersedes on **every affected card**, PR body, and scheduled supervision prompt, then read back each change. Deferral means no build/send until reauthorized; unlink it from release gating and add a negative test where feasible.
- Keep a UI card scoped to the UI; card the backend prerequisites separately. Interpret styling instructions literally, compare the rendered branch with the user's mockup side by side, and walk the UI locally before merge. Do not infer layout from memory; inspect the actual image. A release card can gate on a minimal happy path while nonessential hardening runs in parallel, provided safety necessary for correct operation remains in scope.
- A user's stop/revert request applies to the named workstream. Map merged PRs to that issue before proposing reversions; stop/close unmerged work, but obtain authorization before a revert that triggers production deploy. A global production flag or shared-infra change requires explicit blast-radius approval.
- T2 stops at review unless the delegation explicitly says otherwise. T1 may merge only within the stated workstream's authorization, after scoped diff, requested review, and exact-head checks. Read back merged PR state and deployed revision. GitHub Actions runs do **not** automatically queue: verify `concurrency` and deployment policy before triggering concurrent merges or deploys.

## Status and deadlines

Use board events, live worker/child processes, latest pushed SHA, and exact-head PR/CI state to distinguish running from progressing. Classify milestone-gating versus non-gating cards; give user-facing per-deliverable ranges grounded in current evidence, not an unverified ETA. Do not present a mock-backed unit suite as a production/browser end-to-end test. Under deadline, batch tightly related fixes into a push and let exact-head CI cover the full change, but retain mandatory safety and review gates. Stop polling when the user asks for an immediate different action. Keep only one watcher per board and make sure it covers replaced card IDs.

Avoid universal rules that forbid all code delegation: the board's ownership and one-writer invariant matter, while the authorized T1 workflow determines whether a bounded helper may edit code. Do not use a second writer on a shared worktree without an explicit handoff.
