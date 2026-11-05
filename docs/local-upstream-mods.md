# Local upstream mods

Local patches applied to the **live `~/.hermes/hermes-agent` clone** that are
NOT committed/pushed upstream (we don't own that repo — it's a Hermes-managed
clone of the upstream `hermes-agent` source).

**Re-apply and re-verify after every `hermes update`** — the update flow pulls
fresh upstream source into `~/.hermes/hermes-agent` and will silently drop any
of these local edits.

## 1. Readonly kanban connect for delegated children

**Status:** no longer applied on either host. Upstream now provides the readonly connection for delegated children; the former `kanban_db.py`/`kanban.py` local patch is obsolete.

## 2. Exclude `local_automation_v1` from `pending_rows` viewer receipts

**Status:** applied + verified 2026-11-03. The `gateway/session_queued_controls.py` change exists on the remote only; the Mac has the `tui_gateway/session_history.py` change.

**Why.** On the canonical gateway (`gateway/session_queued_controls.py`), `pending_rows()` included `local_automation_v1` rows (background process completions, subagent completions, heartbeats) in `session.info.pending`. When those rows transitioned `queued → started`, `ui-tui/src/app/createGatewayEventHandler.ts` (`newlyStartedRows`) painted `started.user` (the full `[IMPORTANT: Background process ...]` or `[ASYNC DELEGATION BATCH COMPLETE ...]` model text) as a live `❯` user chat bubble on screen.

**Files + functions changed:**

- `gateway/session_queued_controls.py` (remote only)
  - `pending_rows(authority, ref)` — filters out `'local_automation_v1' in (row.get('payload') or {})` so internal automation turns are not broadcast as user-queued prompt bubbles.
- `tui_gateway/session_history.py` (Mac + remote)
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
