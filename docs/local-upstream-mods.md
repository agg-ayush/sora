# Local upstream mods

Local patches applied to the **live `~/.hermes/hermes-agent` clone** that are
NOT committed/pushed upstream (we don't own that repo — it's a Hermes-managed
clone of the upstream `hermes-agent` source).

**Re-apply and re-verify after every `hermes update`** — the update flow pulls
fresh upstream source into `~/.hermes/hermes-agent` and will silently drop any
of these local edits.

## 1. Readonly kanban connect for delegated children

**Status:** applied + verified 2026-08-19.

**Why.** The tier-system T1 background watcher needs read-only `hermes kanban
watch` from inside a `delegate_task` child (a background subagent). The
mutation gate (`hermes_cli/kanban_db.py:165`,
`_assert_not_delegated_child_mutation`) correctly blocks delegated mutations —
but the cold-connect path ran `init_db` / migrations inside a `write_txn`, so
even a pure read tripped the gate and exited 1 before the watcher could open
the DB. We need a read path that skips init/migrations when the caller is a
delegated child only asking to read.

**Files + functions changed:**

- `hermes_cli/kanban_db.py`
  - `_connect_readonly(path)` (new) — opens an existing DB via
    `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, sets `row_factory`,
    applies `PRAGMA query_only=1` (defense-in-depth), skips the WAL pragma
    (a write op) and the entire `init_db` / migration / `write_txn` pass.
    Never calls `_assert_not_delegated_child_mutation`.
  - `connect(..., readonly=False)` — new kwarg. When `readonly=True` and the
    DB file exists, returns the ro connection; falls through to the normal
    path on `OperationalError` or missing file. Byte-identical behavior when
    `readonly=False`.
  - `connect_closing(..., readonly=False)` — forwards the kwarg.

- `hermes_cli/kanban.py`
  - `_READONLY_ACTIONS` frozenset (new) —
    `list/ls/show/diagnostics/diag/attachments/tail/watch/stats/log/runs/assignees/notify-list/context`.
  - `_is_delegated_child_context()` (new) — true iff
    `HERMES_DELEGATED_CHILD_CONTEXT` is set.
  - `kanban_command` routing — for delegated-child + read-only action, skips
    the auto-`init_db()` (the cold-connect failure point — it routes through
    the gated `write_txn`); fails fast with a clear message if the DB file
    doesn't exist yet ("run a non-delegated `hermes kanban list` once to
    initialize/migrate it").
  - `_cmd_list` / `_board_task_counts` read paths — routed through
    `connect_closing(readonly=_is_delegated_child_context())`; `_cmd_list`
    skips the `recompute_ready` mini-dispatch write in child context (ready
    states may be one tick stale for a delegated read).

**Invariant preserved.** The mutation trust boundary is fully intact:
`_is_delegated_child_cli_mutation` and the DB-layer `write_txn` assert are
untouched — delegated children still cannot mutate kanban. Only the *read*
path bypasses the init/migration write.

**Caveat.** The ro path can fail with `unable to open database file` if the
DB's `-wal` / `-shm` files are absent and un-creatable (e.g. after a crashed
writer). Rare in practice — the gateway daemon keeps boards warm — and the
non-delegated path is unaffected. If you hit it, run any non-delegated
`hermes kanban list` once to recreate the WAL files.

**Verification.** 60 passed, 1 skipped on
`tests/hermes_cli/test_kanban_db.py test_kanban_cli.py test_kanban_boards.py
tests/tools/test_delegate_kanban_isolation.py`. Delegated `kanban list`,
`show`, `stats`, `runs`, `boards list`, and `watch` all work; delegated
`complete` is still blocked with exit 1. Cold DB + delegated fails cleanly;
cold DB + non-delegated auto-inits.

## 2. Exclude `local_automation_v1` from `pending_rows` viewer receipts

**Status:** applied + verified 2026-11-03.

**Why.** On the canonical gateway (`gateway/session_queued_controls.py`), `pending_rows()` included `local_automation_v1` rows (background process completions, subagent completions, heartbeats) in `session.info.pending`. When those rows transitioned `queued → started`, `ui-tui/src/app/createGatewayEventHandler.ts` (`newlyStartedRows`) painted `started.user` (the full `[IMPORTANT: Background process ...]` or `[ASYNC DELEGATION BATCH COMPLETE ...]` model text) as a live `❯` user chat bubble on screen.

**Files + functions changed:**

- `gateway/session_queued_controls.py` (`sora`)
  - `pending_rows(authority, ref)` — filters out `'local_automation_v1' in (row.get('payload') or {})` so internal automation turns are not broadcast as user-queued prompt bubbles.
- `tui_gateway/session_history.py` (`Mac` + `sora`)
  - `_legacy_display_kind(role, text)` — recognizes `[IMPORTANT: Background process ` (`process_complete`) and `[ASYNC DELEGATION BATCH COMPLETE` (`async_delegation_complete`) when projecting any untyped row (e.g. a turn interrupted before post-turn stamping).

## 3. Seatbelt Claude Teams OAuth route identity (`seatbelt-claude-teams.patch`)

**Status:** applied + verified 2026-11-05 on Mac and `sora`.

**Why.** Makes Hermes treat `https://<model-gateway>` / `<model-gateway>` (`providers.seatbelt`) as a native Claude Code OAuth route across main chat, thinking retention, and auxiliary calls (`_maybe_wrap_anthropic`), preventing 429s ("Third-party apps now draw from extra usage").

**Files + functions changed:**

- `agent/anthropic_credentials.py` — `anthropic_route_is_oauth` returns `True` for `seatbelt` / `<model-gateway-domain>` / `<model-gateway>`.
- `agent/anthropic_endpoints.py` — `_is_third_party_anthropic_endpoint` returns `False` for Seatbelt/<model-gateway> hosts so signed thinking blocks are preserved.
- `agent/auxiliary_client.py` — `_maybe_wrap_anthropic` sets `is_oauth=anthropic_route_is_oauth(base_url, api_key)` instead of hardcoded `False`.
- `agent/anthropic_message_convert.py` — `_sanitize_tool_id` strips TrueFoundry's `__thought__<base64>` suffix from Gemini 4 tool call IDs (and bounds length to `<=64` chars) so Bedrock/Anthropic doesn't 400 with `toolUseId failed to satisfy constraint` when switching mid-chat from Argon to Opus/Sonnet.
- `tests/agent/test_anthropic_route_oauth_identity.py` — regression tests for Seatbelt main + aux identity.
