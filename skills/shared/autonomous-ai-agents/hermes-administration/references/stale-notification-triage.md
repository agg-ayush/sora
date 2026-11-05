---
title: Triaging stale/phantom Hermes TUI notifications
---

# Stale/phantom notifications (commits, crons) that don't correspond to real state

When the Hermes TUI surfaces a notification-looking entry — something
that reads like a `git log` commit, or a cron-job name — that you don't
recognize, don't answer from the notification's own text or by guessing
its source ("probably a subagent transcript" / "probably a file
watcher"). Verify against ground truth first, then answer:

- Claimed commit → `git log --oneline -20` in the relevant repo. Not
  there → not a real commit. It's a stale delegation-system UI artifact
  or leftover render, not something whose provenance needs explaining
  before you say "not real."
- Claimed cron job → `cronjob(action='list')` (or `hermes cron list`).
  Name not in the live list → stale/orphaned notification data, not a
  job that needs handling.

Lead with the verification, not a guess: "Checked `<ground truth
source>` — this isn't real" beats a paragraph theorizing where a phantom
notification came from.

## Disambiguate the referent before answering

"What are these?" pointing at a UI element is ambiguous — it can mean
the notification/banner itself, or the actual underlying object (crons,
scripts, commits) that a notification is reporting on. Answering the
wrong referent repeatedly is a real frustration cost: observed live, the
user had to escalate to "stop answering about the notifs... im asking
about the crons you put up" after two prior misreads answered about the
notification chrome instead of the real crons.

When the question could point at either the notification UI or the
underlying real object, default to answering about the concrete real
object first (the actual cron job / commit / script) — that's almost
always what's being asked about. Only explain the notification mechanism
itself if the user's follow-up makes clear that's what they meant.

## Background/subagent completions rendering as user prompt bubbles

Two distinct paths make `[IMPORTANT: Background process ...]` or
`[ASYNC DELEGATION BATCH COMPLETE ...]` text show as a `❯` user prompt.
Ask which one the user sees (live on screen vs after `/resume`) before
fixing, and trace the real path with a read-only repro before claiming the
root cause:

- **After `/resume` only:** legacy `state.db` rows with `role='user'` and
  NULL `display_kind`. Backfill with a sqlite UPDATE by content prefix
  (`process_complete` / `async_delegation_complete`).
- **Live on screen (canonical gateway):** the gateway's `session.info`
  pending list includes `local_automation_v1` admissions carrying the full
  model-facing text, and the TUI appends every `queued -> started` row as a
  user message (`newlyStartedRows` in `createGatewayEventHandler.ts`)
  while ignoring the typed card sent on `message.start`. Not caused by
  memory plugins. Fix by filtering `local_automation_v1` rows out of
  `pending_rows()` (`gateway/session_queued_controls.py`); a projection
  fallback in `_legacy_display_kind` (`tui_gateway/session_history.py`)
  covers untyped rows. Check upstream `origin/main` first.

No native toggle covers both: `display.background_process_notifications`
only affects terminal background-process wakes, not delegation
completions.

## Real cron deliveries

A reply to `Cronjob Response: <name> (job_id: <id>)` refers to exactly that ID. Inspect the cron entry, its `no_agent` script (when applicable), and recent outputs before explaining. For "stop" pause; for "delete/remove" remove, using the current `hermes cron --help` or cron-management tool, then read back the ID. Silencing an alert does not repair its underlying cause.

## Script drift and iteration alerts

For `installed script differs from repo`, compare both directions and the actual repo path. The live script may be a valid host-specific migration; follow called scripts, check tracked history, run the read-only check before copying either direction. `saml2aws` is retired here; do not restore old auth scripts from a stale repo snapshot.

`max_runtime=0s` can mean a kanban worker hit its iteration cap, not elapsed time. Check the worker outcome and new run ID/PID; a dispatcher can retry in the same worktree. `agent.max_turns` is not `delegation.max_iterations`; changing it affects new workers, not in-flight workers.
