---
name: kanban-run-forensics
description: Use when tracing Kanban worker timeouts to sessions.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    category: devops
    tags: [kanban, sqlite, forensics, timeout]
---

# Kanban worker-run forensics

## When to Use

Use for local Kanban timeout, retry, crash, and gave-up investigations that must join run rows to full Hermes worker transcripts.

## Method

- Discover `task_runs` and `sessions` schema before joining. Worker session IDs are not necessarily `tasks.session_id`; match `sessions.source='kanban'` near `task_runs.started_at` and **verify the first user message names the exact task ID**. Concurrent sessions can start seconds apart, so nearest timestamp alone is unsafe.
- Keep the requested date window and supplied epoch literals separate: convert both to UTC first and flag any divergence; show out-of-calendar rows returned by an explicitly requested SQL predicate separately instead of silently dropping them.
- Read `task_runs.error`, `outcome`, and `metadata` to distinguish hard runtime limits, iteration-budget exhaustion, retry-ceiling `gave_up`, disappeared worker PIDs, and rc=0 protocol violations. `task_events.kind='gave_up'` does not imply a matching `task_runs.status='gave_up'` row.
- Inspect the final assistant `tool_calls` and corresponding `role='tool'` result messages by session and message ID. Quote both commands and results; mark missing results and distinguish an interrupted wait from proven failure of a background worker.
- Count literal `Test Files` in `role='tool'` message content only when asked for a reproducible proxy; then identify distinct full Vitest invocations from command scope, package/file count and `Start at` timestamps. Captured panes, log reads, CI excerpts, grep expressions, and targeted suites can contain the same string without representing additional full test runs.
- Calculate burn as sum of `ended_at-started_at` across runs (worker-hours); split each duration at regime boundaries. State whether subsets overlap and do not mistake concurrently running worker-hours for elapsed calendar time.
- Trace replacements from `task_links`, comments, bodies, creation time, PR/worktree continuity, run status and completion events. No link is itself a finding; avoid inventing one from title similarity. Note a review-gate successor separately from a new implementation owner.
