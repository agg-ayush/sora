# Local upstream mods

Local patches applied to the **live `~/.hermes/hermes-agent` clone** that are
NOT committed/pushed upstream (we don't own that repo — it's a Hermes-managed
clone of the upstream `hermes-agent` source).

Each mod lives in `patches/*.patch` (generated with `git diff` from the host
checkouts). `devbox/setup-hermes.sh` applies them idempotently per file: skip if
already applied, apply if clean, otherwise print a loud `WARNING` and continue
(never forces or 3-way merges). `HERMES_SKIP_PATCHES=true` skips the step;
Claude-only and skills-only modes exit before it.

**After every `hermes update`** (which drops local edits) re-run
`bash devbox/setup-hermes.sh`, then re-run the tests below.

## 1. Readonly kanban connect for delegated children

**Status:** no longer applied on either host. Upstream now provides the readonly connection for delegated children; the former `kanban_db.py`/`kanban.py` local patch is obsolete.

## 2. Exclude `local_automation_v1` from `pending_rows` viewer receipts

**Patch:** `patches/session-bubble-fix.patch` (applied by `setup-hermes.sh`). **Status:** applied + verified 2026-11-03. Before the patch file existed, `gateway/session_queued_controls.py` was on the remote only and `tui_gateway/session_history.py` on both; setup now applies both everywhere.

**Why.** On the canonical gateway (`gateway/session_queued_controls.py`), `pending_rows()` included `local_automation_v1` rows (background process completions, subagent completions, heartbeats) in `session.info.pending`. When those rows transitioned `queued → started`, `ui-tui/src/app/createGatewayEventHandler.ts` (`newlyStartedRows`) painted `started.user` (the full `[IMPORTANT: Background process ...]` or `[ASYNC DELEGATION BATCH COMPLETE ...]` model text) as a live `❯` user chat bubble on screen.

**Files + functions changed:**

- `gateway/session_queued_controls.py`
  - `pending_rows(authority, ref)` — filters out `'local_automation_v1' in (row.get('payload') or {})` so internal automation turns are not broadcast as user-queued prompt bubbles.
- `tui_gateway/session_history.py`
  - `_legacy_display_kind(role, text)` — recognizes `[IMPORTANT: Background process ` (`process_complete`) and `[ASYNC DELEGATION BATCH COMPLETE` (`async_delegation_complete`) when projecting any untyped row (e.g. a turn interrupted before post-turn stamping).

## 3. TrueFoundry tool-call ID compatibility

**Patch:** `patches/truefoundry-tool-id.patch` (applied by `setup-hermes.sh`).

**Why.** TrueFoundry appends a `__thought__<base64>` signature to Gemini tool-call IDs. Anthropic/Bedrock rejects IDs over 64 characters, so switching a Gemini session to an Anthropic model can fail with `toolUseId failed to satisfy constraint`.

**Files + functions changed:**

- `agent/anthropic_message_convert.py` — `_sanitize_tool_id` strips the `__thought__` suffix and hash-truncates IDs to at most 64 characters.

## 4. Claude Teams and direct-Anthropic OAuth identity

**Patch:** `patches/anthropic-oauth-identity.patch` (applied by `setup-hermes.sh`). Verify: `pytest tests/agent/test_anthropic_route_oauth_identity.py` in the Hermes checkout.

**Why.** TrueFoundry Claude Teams routes need Claude Code OAuth identity. Auxiliary calls must use the same route-identity rule as the main chat instead of hardcoding `is_oauth=False`.

**Files + functions changed:**

- `agent/anthropic_credentials.py` — `anthropic_route_is_oauth` recognizes TrueFoundry Claude Teams providers.
- `agent/auxiliary_client.py` — `_maybe_wrap_anthropic` derives OAuth identity with `anthropic_route_is_oauth`.
- `tests/agent/test_anthropic_route_oauth_identity.py` — covers TrueFoundry Claude Teams and direct-versus-third-party auxiliary identity.
