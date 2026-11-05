# External memory provider across hosts (synapse-mem / smem)

Applies when an event-sourced external memory store (smem) is the Hermes memory provider on more than one host.

## Default: independent store per host
Each host keeps its own store, the same way built-in Hermes memory worked per host. The user works on the remote host through the WezTerm mux, so that host's memory being local to it is fine. Do not add cross-host sync (sync repo, crons) unless the user asks for shared memory; unrequested sync infra gets torn down.

## Deploy on an extra host
1. Install the binary, clone the fork that holds `integrations/`, run its `activate.sh` (sets `memory.provider`, installs the out-of-tree plugin).
2. Persist the binary path in the profile config (`smem_bin`): `hermes memory status` runs without the login PATH and reports "not available" otherwise, even when sessions work.
3. Probe end to end: a `hermes chat` turn stores a fact through the provider tools, `smem recall` finds it, `smem verify` is ok.

## Rolling out a fork fix of the binary and adapter
1. Re-run the gates yourself on a detached worktree of fork main (`git worktree add --detach <scratch> origin/main`): `make check`, `make test`, and the adapter e2e (`PYTHONDONTWRITEBYTECODE=1 ~/.hermes/hermes-agent/venv/bin/python integrations/agents/hermes/tests/test_provider_e2e.py`). A worker's pass counts are self-reports.
2. A/B the user-visible fix on a throwaway store with the OLD installed binary vs the newly built one (same seed memories, same queries), and drive adapter fixes through the real provider class in an isolated `HERMES_HOME` (e.g. call `on_session_end` twice and count episodes).
3. Back up the installed binary and plugin per host (`~/.hermes/cache/smem-predeploy-<ts>/`), install, then confirm the plugin checksum equals the fork file on both hosts and `smem verify` is ok on the real store. Cross-build the remote binary locally (`GOOS=linux GOARCH=amd64 go build ./cmd/smem`) and scp it; install via `.new` + `mv` so a running reader never sees a half-written file.
4. Re-run a known noise query against the real store to show the change live.
5. The binary takes effect immediately; the plugin loads at process start, so tell the user which processes need a restart (their own TUI, the remote gateway). Check the remote gateway is idle (no running kanban, no recent API calls in `agent.log`) before bouncing it.

## Removing a sync remote
If the CLI has no `remote remove` verb (`smem --help` lists only `remote add|list`), the registration lives in the store's SQLite `meta` table as `remote.<name>`. Delete that row (`delete from meta where key like 'remote.%'`), then confirm `smem remote list` says local only and `smem verify` is ok. Also drop the crons, the sync script in the setup repo and the local clones on every host.

## Cross-host sync (only when the user asks for shared memory)
- Private sync repo, one append-only feed file per replica; `smem sync` imports/exports, git only moves files. Hourly cron per host, staggered (:00 / :30) to reduce push races.
- The script must `git pull --rebase` before `smem sync` and, if `git push` is rejected, fetch + rebase + retry once. A rejected push is otherwise silent and the other host never sees new events.
- Every distinct actor identity gets its own signing key (`hermes-cli@host` vs `user@host` from a manual CLI write). Events from an untrusted key import as quarantined: `sync` reports them "already present" yet recall/why show nothing. Check `smem keys` first when a synced memory is missing; trust the user's own machine keys on every host (`smem keys trust <id>`).
- Verify both directions with a fresh memory each way (write, sync both hosts, recall on the other), then `smem verify` on both.

## Answering "does the external provider actually help?"
Role split to explain first: built-in `MEMORY.md`/`USER.md` is a small hand-curated set injected whole every turn (standing rules live there); the external provider is a searchable store injected by per-turn recall, and its unique value is decision provenance (choice, rejected options, assumptions) plus decay/contradiction tracking. "Isn't that what native memory does?" is only true for plain fact storage.

Audit from data, not impressions, on every host:
1. Find the provider store: `~/.hermes/synapse/smem.db` (repo-local `.smem/smem.db` stores are separate and usually empty). Count `memories` by `kind` and `scope`, `decisions`, `actions`, `events`, and list non-episode contents.
2. Classify each memory as real lesson vs probe/test noise vs duplicate (`group by content having count(*)>1`).
3. Test recall quality: an unrelated query should return nothing; a real query with `--explain --no-record` shows relevance x salience x confidence per hit. Time it (`/usr/bin/time -p`) before blaming latency.
4. Read the plugin (`~/.hermes/plugins/synapse-mem/__init__.py`) for the automatic paths: `prefetch` limit and whether it applies any score floor, `on_session_end` episode capture (what it keeps and length caps), `on_memory_write` mirroring (scope `hermes-native-<target>`), `capture_tool_call` spooling.
5. Check whether mirroring works per host (count `scope like 'hermes-native%'`). Zero on a host where native memory was written is usually a long-running TUI process loaded before the plugin update; compare plugin mtime with `ps -o lstart` of `tui_gateway.entry` before calling it a bug.
6. Confirm injected recall is turn-scoped, not persisted: `messages` rows in `state.db` should not contain the recall header.

Before proposing fixes, read the adapter's shipped defaults (`get_config_schema` / `initialize` in the plugin) and diff them against `~/.hermes/synapse-mem.json` on each host. Known defaults: `enable_turn_capture` False (session-end episodes are opt-in; a host with it on is our choice, not a tool bug), `max_prefetch` 10, `session_context` True, `capture_tool_calls` True. Mirroring (`on_memory_write`) copies only NEW native writes; entries that existed before the provider was installed are never copied, so a host shows a small fraction of its native entries mirrored and none from `USER.md` until written again.

Classify each fix for the user as (1) our config/ops/skills: quick, revertible, verify by observation; or (2) smem core or its shipped adapter: harder, needs a throwaway-store repro and upstream issue/PR (see the `github-pr-response-workflows` skill, "Prove it is upstream's before filing"). Typical (1) fixes: turn episode capture off, retract probe/duplicate memories, restart the long-running TUI so mirroring loads, lower `max_prefetch`, add a "record the decision" step to the tier skills, decide on `capture_tool_calls`. Verified (2) ownership:

| Symptom | Owner | Why |
|---|---|---|
| Unrelated memory injected at relevance 1.00 | core recall | OR fallback when AND finds <20, then BM25 normalized to the best candidate; no absolute coverage floor |
| Recall/session context slows as actions grow | core read paths | event-time and quarantine scans over the whole log; `sweep` covers memories only, signed actions are permanent by design |
| Episode = last Q/A only, never for long sessions | adapter | `on_session_end` only, 1,200-char caps |
| Episode pairs an unanswered prompt with the previous reply | adapter | last user and last assistant text scanned independently |
| Identical duplicate memory | adapter | session end delivered twice (finalize then shutdown), no idempotency key; core `remember` creating a new assertion per call is intended append-only behavior |
| Read-only tool calls stored as actions | adapter | skip list is a denylist that misses discovery tools |

Before calling a duplicate a core dedupe gap, compare the pair's `actor`, `session` and `recorded_at`: same session milliseconds apart means a callback fired twice. The Hermes adapter exists only in our fork, not upstream, so adapter fixes go to the fork; only core items get upstream issues.

Clean noise with `smem --db <store> retract <mem> --reason ...` (never true: probes, duplicates) or `invalidate` (stopped being true: stale routing facts), never SQL deletes, then `smem verify`.

Cross-host sharing is low value when the user works on the remote host for development and uses the Mac only to manage it: skip sync and search the other host's store over SSH when needed.

Pain points this audit typically finds (check each, report with counts): session-end episodes keep only the last Q/A so long-lived sessions save nothing useful; recall injects the top-N with no relevance floor (noise every turn); per-host stores mean one host's real lessons never reach the other; decision provenance unused (0 decisions); tool-call spool grows unbounded with no reader. Present as a table with evidence, then ask which to fix first; do not change the provider during the audit.
