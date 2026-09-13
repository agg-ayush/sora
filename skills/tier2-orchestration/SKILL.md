---
name: tier2-orchestration
description: Supervise one coding issue from raw task to approved PR.
version: 0.3.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Coding-Agent, Tier-2, Kanban]
    related_skills: [claude-code, codex, pr-review-toolkit, github-pr-workflow, pr-description-style, requesting-code-review, hermes-agent]
---

PLACEHOLDER_BODY

<!-- LESSON: shared-checkout collision hazard
When multiple T2 sessions share one working tree (no per-task worktree), a
sibling session can `git checkout` the shared branch mid-commit. The fixer
then sees its commit briefly land on the wrong branch and self-reports
DONE_WITH_CONCERNS with a "branch collision" note. Fix: pass `worktree` to
claude_orchestrate start so each task gets an isolated git worktree+branch.
Verify ground truth with `git show HEAD:<file>` and `git log` directly,
never trust the subagent's self-report of file content when a shared
checkout is in play; the working tree may have been mutated under it.
-->
<!-- LESSON: claude_orchestrate wait action bug
The `wait` action throws "NameError: name 'artifact_dir' is not defined"
when kanban_task_id/board are passed (intermittent). Workaround: use
`status` with a sleep-and-poll loop instead of `wait` when this fires.
-->
<!-- LESSON: Fireworks/K3 "reads outside working directories" permission prompt
stalls sessions. A claude_orchestrate session (model_provider=fireworks) whose
workdir is a scratch dir or worktree, reading a repo OUTSIDE that workdir, hits
an interactive TUI menu "Allow reads outside the working directories? 1.Yes
2.No 3.Ask again". Text `steer` cannot navigate arrow-key menus; the session
sits on the prompt and looks like a silent crash (status frozen at
investigating, no outcome). The `permissions.blockReadsOutsideWorkingDirectories
= false` flag in ~/.hermes/claude-k3-config/.claude.json does NOT reliably
suppress it. Fix: in the poll loop, `tmux capture-pane` and if the prompt text
is present, `tmux send-keys Enter` to dismiss it (option 1 is pre-highlighted).
Pre-seed `projects[<workdir>].hasTrustDialogAccepted=true` too. Same class as
the trust-dialog pitfall already in the skill: both are first-run TUI menus
that kill Fireworks sessions, distinguishable from a real crash by the menu
text in the pane.
-->
<!-- LESSON: implementer over-build — unrelated migration/test edits.
A coding session can fold in pre-existing repo bugs it notices while
implementing. Observed: a task to wire provision.sh ALSO renamed an existing
migration 0002_transcript_file_id.sql -> 0003 and rewrote its body to
ADD COLUMN IF NOT EXISTS, claiming to fix a version collision with a sibling
0002_session_status_check.sql. Renaming an already-shipped migration is
dangerous (prod DBs record version 2) and was out of scope. Fix: after the
session reports done, `git diff origin/main..HEAD --name-only` against the
design's planned file list; any file NOT in the design is a scope-creep
candidate. Revert out-of-scope files directly (git checkout origin/main --
<file>, or rewrite the content) and steer the session to re-test+commit, or
finish yourself. Record the pre-existing bug as a linked kanban task, do not
let the PR carry the fix. The migration collision itself was a real pre-existing
origin/main bug (13 DB test files red, schema_migrations_pkey duplicate) that
must be baselined, not fixed in this PR.
-->
<!-- LESSON: baseline test runs need a separate worktree with linked node_modules.
To prove a branch's failures are pre-existing (not regressions), run the suite
on a clean origin/main checkout: `git worktree add --detach <path> origin/main`,
then `ln -s <main-checkout>/orchestrator/node_modules <baseline>/orchestrator/node_modules`
(worktrees don't share node_modules). Run vitest on both, diff the passing-file
sets: "passed on baseline but failed on branch" = regressions (must fix);
"failed on both" = pre-existing (record, don't block). `git worktree remove
--force` the baseline after. This is the rigorous version of the skill's
"baseline first" rule when DB-dependent tests are involved.
-->
