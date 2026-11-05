# Incident orchestration under a stop request

First define the incident workstream, blast radius, stop scope, and who may authorize deploy/merge/credential rotation. A pause of new dispatch is not a stop of already-running workers; verify which action the user requested. Scope cancellation to the named incident, not unrelated board cards or tmux sessions.

For a full stop: stop new dispatch; list active workers and their child sessions; request each to checkpoint; verify process exit with `ps`/session status and exact card state. Preserve dirty worktrees and pushed/unpushed commits; do not `git restore`, archive, or let a reaper destroy the only copy. Recheck for respawns and confirm no *incident-scoped* workers remain. In a credential incident, rotate/revoke via authorized secret-management channels; never paste keys into commands, kanban comments, or transcripts.

For a restart: inspect the preserved branch, dirty files, active claims, and external systems' current state before dispatch. Assign one writer per worktree and resume at the explicit checkpoint; record changed scope on every affected card and read it back. A deployment, secret rotation, or PR merge needs the corresponding explicit authorization even when incident response is urgent. Verify each resulting external state (revoked credential, new revision, checks on exact PR head) before declaring recovery complete.

Use `$HERMES_HOME` or the active profile for state paths. `/proc` is Linux-only; on macOS use portable `ps`/CLI status, and check that the PID still belongs to the expected process rather than trusting a recycled number.
