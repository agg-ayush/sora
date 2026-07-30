# Tier System Redesign — Execution Plan

**Status:** proposed 2026-07-23, awaiting build. Supersedes ad-hoc decisions made
during the audit discussion. The canonical architecture reference
(`hermes-tiers-reference.md`) will be updated as each piece lands.

---

## Motivation

Four pain points identified during audit:

1. **T1 reads code it doesn't need to** — "2 layers of info." T1 triages by reading
   source, then T2 reads the same source. T1 should triage from task description
   alone; code understanding belongs in T2 (or the author session), never T1.
2. **T1 eats 40-50% context per issue** — should be a light multi-issue entry point
   (~1-2% per issue). Currently needs a new T1 session per issue because it bloats
   context with code/design-doc reading.
3. **No live visibility between T1 and T2** — no push/websocket; user polls "Status?"
   manually. Claude Code CLI doesn't have this issue for single sessions; our
   multi-session case needs a dashboard.
4. **No proactive reporting** — user keeps asking "Status?" instead of being shown
   state. Need a dashboard or push channel.

Additional: many subagent steps are sequential when they could be parallel
(tests + review; independent implementation units).

## Decision: migrate from Paperclip to kanban

**Rationale:** kanban (native Hermes) provides equivalent-or-better functionality
for all load-bearing pieces, with strictly better maintainability (no external
daemon, no pinned clone, no port to manage — ships with Hermes). Two gaps have
adequate workarounds. Path A (Paperclip-reading dashboard plugin) would be
throwaway work — we'd build a bridge then rip it out on eventual kanban migration.

### Capability mapping (Paperclip → kanban)

| Capability | Paperclip (current) | Kanban (native) | Status |
|---|---|---|---|
| Issue/task lifecycle | `POST/GET/PATCH /issues` | `kanban create/show/complete` | ✅ equivalent |
| Concurrent-writer lock | checkout (ownership 409, per-agent UUID) | `kanban claim` (atomic, TTL 900s, per-profile) | ✅ equivalent |
| Release on crash | `POST /issues/{id}/release` | `kanban reclaim` | ✅ equivalent |
| Gate/review evidence | `POST /issues/{id}/comments` | `kanban comment` | ✅ equivalent |
| Design doc / ledger | versioned documents (`PUT /documents/{key}`, revisions) | `kanban attach` (files, no versioning) + comments | ⚠️ workaround: attachment + comment mirror; loses revision history but current doc always available |
| Human merge approval | Approval object (approve/reject/request-revision, pollable) | `kanban block --kind needs_input` / `unblock` | ⚠️ workaround: block=gate, unblock=approved; reject/revision via re-block with reason. Redundant anyway — the GitHub PR is the real approval surface (Phase 4 redesign). |
| Task dependencies | hand-rolled `depends_on` in ledger JSON | `kanban link`/`unlink` (native parent→child) | ✅ kanban **better** |
| Notifications/push | none (would build watcher) | `kanban notify-subscribe` (gateway push) | ✅ kanban **better** |
| Heartbeat/progress | none (tmux-based stall detection) | `kanban heartbeat` (native, with notes) | ✅ kanban **better** |
| Dashboard | none (would build) | native kanban dashboard tab (cards, WebSocket, drag-drop) | ✅ kanban **better** |
| Boards per repo | companies (manual) | boards (native, one per project) | ✅ equivalent |
| Workspace isolation | plugin's `worktree` param | `--workspace worktree` / `worktree:<path>` | ✅ equivalent |

### What gets removed
- Paperclip dependency entirely: `paperclip-up` launcher, pinned clone at
  `/tmp/paperclip-spike`, embedded Postgres, port 3100, the `agent_id`-must-be-UUID
  gotcha. All gone.
- The `no_agent` orphan-reaper cron (kanban's TTL-based claim expiry + the dashboard
  handle this — dead sessions' claims auto-expire after 900s).
- The deferred "reaper watchdog" (same reason).

### What stays
- The `claude-orchestrate` plugin (tmux session management) — Paperclip-independent,
  unchanged. Its checkout-related code (the `_pc_post` calls in `_start`/`_stop`/
  `_recover`/`_gate`) gets replaced with kanban `claim`/`reclaim`/`comment` CLI calls
  OR removed entirely (if kanban manages claims from the skill layer, not the plugin).
- `holo` launcher, all the plugin primitives (`start`/`wait`/`steer`/`interrupt`/
  `gate`/`check_diff`/`clean`/`diagnose`/`effort`).
- The full design-review pipeline, human merge gate (now PR-based), all the
  hard-won gotchas (agent_id, outcome-location, stall-detection, auth-fallback,
  effort=medium, tests-before-review).

---

## Build sequence

### 1. Migrate to kanban (the big swap) — IN PROGRESS

**Done:**
- ✅ Plugin de-Paperclipped: all `_pc_post` calls, `issue_id`/`agent_id`/`checkout_held`
  removed. Plugin is now a pure tmux session manager (committed on `main`).
- ✅ Paperclip daemon stopped, `paperclip-up` launcher removed.
- ✅ Orphan-reaper cron updated: Paperclip-release logic removed (kanban TTL handles
  stale claims); reaper now kills idle tmux sessions only.
- ✅ T2 skill rewrite dispatched (deleg_35e811b1) — replacing Paperclip REST with
  kanban CLI, adding heartbeat, tests+review parallel, independent units.
- ✅ T1 skill rewrite dispatched (deleg_fcbabbbe) — replacing Paperclip + redesigning
  as stateless dispatcher that never reads code.

**Pending (after skill rewrites land):**
- ✅ T1 skill rewrite verified — zero Paperclip, kanban throughout, "never read source" as first principle, dashboard pointing, all gotchas kept.
- ✅ T2 skill rewrite verified — zero Paperclip, 24 kanban mentions, heartbeat (12 refs), all gotchas kept (effort, interrupt, 3-round, check_diff, PR skills, tests/review order).
- ⬜ Update `hermes-tiers-reference.md` — dispatched (deleg_2c06adb4).
- ⬜ End-to-end validation: re-run the core T2 loop against kanban.
- ✅ Paperclip fully retired: spike clone, daemon, `~/.paperclip` data dir, `paperclip-up` launcher all removed. Backups in `~/.hermes/backups/`.
- ✅ Reference doc rewritten + verified (zero Paperclip, 47 kanban refs).
- ✅ E2E validation PASSED (2026-07-23): full happy path (create→claim→claude session→fix→tests→gate→heartbeat→comment→block→unblock→complete→reclaim→stop) + all adversarial paths (double-claim rejected, claim-on-done rejected, unblock-non-blocked rejected, stale-claim reclaimed by dispatch, link/unlink dependencies). 3 bugs found+fixed during validation: (1) `block --kind` must precede task_id (argparse), (2) TFY_API_KEY not inherited by tmux server (explicit export fix), (3) codex 0.144.x positional-prompt bug (send-keys workaround).

### 2. T1 redesign — stateless dispatcher + reporter

**Scope:** T1 becomes a light wrapper that never reads code, stays warm across
many issues, and uses the dashboard for reporting (not inline boards).

**Changes:**
- Add "NEVER read source code / git / files in the target repo" — triage from task
  description alone. Code understanding is T2's job (or the author session's).
- T1's per-issue context = task description + issue ID + triage decision + T2
  session name. ~1-2% context. 20+ issues in one T1 session.
- T1's response to "new issue: X" = `kanban create` → triage → spawn T2 →
  "spawned, watch the dashboard at localhost:9119/kanban" (point at dashboard,
  don't print a text board).
- Remove any step where T1 reads code, runs git in the target repo, or holds
  design docs in context (they're kanban attachments).

### 3. Tests + review in parallel

**Scope:** T2's gate runs tests and review concurrently instead of sequentially.

**Changes:**
- 3.2 becomes "spawn test-run + review session concurrently, wait for both."
- Tests: the supervisor runs the suite (or a test session does). Review: the
  `/pr-review-toolkit:review-pr` session.
- On completion: if tests fail → test-fix loop (sequential). If review fails →
  review-fix loop (sequential). If both fail → tests first (cheaper).
- Low collision risk: test-fixer edits config, reviewer reads source — different
  files. Accepted.

### 4. Independent units in parallel

**Scope:** T2 dispatches independent implementation units concurrently using
kanban's native dependency graph.

**Changes:**
- T1's design doc (or T2's plan) specifies unit dependencies.
- T2 creates kanban subtasks per unit with `kanban link` (parent→child = depends_on).
- Units with no unmet dependencies dispatch concurrently (each own worktree +
  `kanban claim`).
- Dependent units wait for their parent to `complete` before claiming.
- The ledger (now kanban tasks + dependencies) is the recovery map.

---

## What this doc is NOT

- Not a build log (that's the reference doc + commit history).
- Not a skill (skills are self-contained runtime instructions; this is a planning
  doc for the human + the building agent).
- Not permanent — delete or archive once the migration is done and the reference
  doc reflects the kanban-based architecture.
