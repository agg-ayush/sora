---
title: Recent Hermes and Claude friction audit (macOS)
version: 1.0.0
author: Hermes Agent
license: MIT
---

# Recent Hermes and Claude friction audit (macOS)

## When to Use

Use when reviewing recent local sessions, Claude Code transcripts, task artifacts, and rotated logs to identify recurring friction.

- Set one timezone-aware half-open window `[start, end)` and convert every event timestamp before counting. Query `date` rather than inferring the current clock. Anchor sessions by message timestamp, not session creation: old sessions can contain the bulk of recent work.
- Query all `sessions` and `messages` rows in `~/.hermes/state.db` within that window, inspecting schema first. Read the live WAL-aware DB read-only and cross-check counts; do not assume immutable snapshots include pending WAL data. Deduplicate message replay copies by `(session_id, tool_call_id)` for tool outcomes and `(session_id, timestamp, content)` for user turns, while retaining raw row counts for coverage.
- Review every user turn for corrections in context; literal keywords such as `no`, `wait`, `stop`, or `why` produce false positives. Distinguish failed tool returns from successful tool wrappers that conceal a failed subprocess. Check command pipelines for missing `pipefail`/lost exit statuses.
- Enumerate every task directory in `~/.hermes/tasks/`, then include both newly created directories and older directories whose `status.md`, `outcome.md`, `result.md`, or `meta.json` changed in-window. Pair terminal task status with outcome and actual published artifact; deduplicate result-only mirrors. A `complete` label does not prove a push or PR happened.
- Inventory all `~/.hermes/logs/` files and rotations. Parse timestamped records and multiline tracebacks, count errors by stable signature, and deduplicate copied streams (e.g. `errors.log*` versus `agent.log*`, `gateway.log*` versus `gateway.error.log`). Explicitly report earliest retained timestamp for each rotation: missing older logs cannot establish absence of incidents. Diagnose shutdown signals before labeling nonzero-exit diagnostics as crashes.
- Scan all JSONL files in `~/.claude/projects/` and `~/.claude/history.jsonl` by each record's timestamp, not file mtime. Separate real human prompts, tool-result user records, metadata/attachments, and untimestamped records. A restart is overhead, not proven failure unless an error is recorded.
- Report absolute source paths, exact denominators and counts, representative session/task IDs and timestamps, residual uncertainty, and a concrete hook/script/skill/config fix for every recurring failure. Read-only audits should not alter live sessions, credentials, or gateway state.
