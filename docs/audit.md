# hermes-setup — Audit Report

**Scope:** `agg-ayush/hermes-setup` cross-checked against the installed
base Hermes Agent repo (`~/.hermes/hermes-agent`) and the live `hermes` CLI on this
machine. Covers correctness bugs, doc/reality drift, internal inconsistencies,
missing content, and external prior-art worth adopting.

---

## 1. Bugs / correctness issues

### 1.1 README install step 8 uses a broken CLI invocation
`README.md` step 8 says:
```bash
hermes cron add --schedule "30m" --script ~/.hermes/scripts/orphan-reaper.py --no-agent
```
`hermes cron add` (alias of `create`) takes `schedule` as a **positional** argument,
not a `--schedule` flag. Confirmed by running it — exits 2 with
`unrecognized arguments: --schedule`. Correct form:
```bash
hermes cron add "30m" --script ~/.hermes/scripts/orphan-reaper.py --no-agent
```
The cron job is actually registered correctly on this machine (`hermes cron list`
shows `orphan-reaper`, schedule `*/30 * * * *`, active) — so the real workaround
was found and used, it just never made it back into the README. A fresh clone
following the doc verbatim will fail at step 8.

### 1.2 `plugin/__init__.py` — `effort` enum doesn't match the real `claude` CLI
The plugin schema and validation restrict `effort` to
`{"low", "medium", "high", "max", "auto"}`, but the installed `claude` binary's
`--effort` flag only accepts `low, medium, high, xhigh, max` (checked via
`claude --help`). Concretely:
- `"auto"` is accepted by the plugin's validator but will be rejected by `claude`
  itself at the shell level → a silent late failure inside the tmux pane, not
  caught by `_start`'s upfront validation.
- `"xhigh"` is a real, useful effort level that the plugin can't pass through at all.

### 1.3 `orphan-reaper.py` can reap a session that's legitimately waiting for input
The reaper's only "still working" signal is the literal string `"esc to interrupt"`
in the pane. But `claude-orchestrate`'s own `_session_state()` (in `plugin/__init__.py`)
treats a session showing a `❯` prompt with no pending activity indicator as
`needs_input` — i.e. alive and waiting for a T2 `steer` call, not idle-and-done.
The reaper doesn't check for that case; it will kill a session sitting at a prompt
waiting for `steer`, indistinguishable in its logic from a session that finished
and is sitting at a shell prompt. Given the 30-minute cron cadence, this is a
narrow window but a real one — a T2 that is slow to `steer` back after a
`needs_input` state could lose the whole tmux session.

**Suggested fix:** reuse (or port) the plugin's own `waiting_for_input` /
`actively_working` heuristics in the reaper instead of a single substring check,
or better, only reap sessions with no corresponding *live* kanban claim at all
(i.e., truly orphaned — no owning T2), rather than reaping by pane content alone.

### 1.4 `kanban-review.py` doesn't set `PRAGMA busy_timeout`
The base `hermes_cli/kanban_db.py` deliberately opens SQLite in WAL mode and sets
an explicit `busy_timeout` before any write transaction, because the kanban
dispatcher can be running concurrently. `kanban-review.py` opens the same DB file
with a bare `sqlite3.connect(str(db))` — no `PRAGMA busy_timeout`, no WAL PRAGMA,
no retry loop. If this script runs while `hermes kanban dispatch`/the gateway
dispatcher is mid-write, it can throw `database is locked` rather than blocking
briefly and succeeding. Low probability, but a real gap next to code that goes out
of its way to guard against exactly this.

**Suggested fix:** add `con.execute("PRAGMA busy_timeout=5000")` (or reuse
`hermes_cli.kanban_db`'s own connection helper by importing it directly, since it's
on the same machine — trading independence from `hermes update` overwrites for
correctness).

### 1.5 Dead code: `meta_for()` in `orphan-reaper.py`
Defined, never called. Either wire it in (e.g., to check `meta.json`'s `rundir`
for a still-open worktree before killing) or delete it.

---

## 2. Internal inconsistencies

### 2.1 `docs/tier-system-redesign.md` contradicts itself on the orphan-reaper's fate
- "What gets removed" section: lists *"The `no_agent` orphan-reaper cron"* as
  something kanban's TTL claim expiry makes redundant and that will be removed.
- "Build sequence → 1. Migrate to kanban" section, two paragraphs later: *"Orphan-reaper
  cron updated: Paperclip-release logic removed... reaper now kills idle tmux
  sessions only."* — i.e. kept, not removed, repurposed.
- Reality: it's alive, deployed, and referenced as permanent infrastructure in
  `hermes-tiers-reference.md`'s "Orphan reaper" section and the README.

This is a stale planning artifact that was never reconciled after the actual
decision (keep-but-repurpose) was made. Low-risk since the canonical reference doc
(`hermes-tiers-reference.md`) got it right, but `tier-system-redesign.md` is still
committed to the repo and will mislead a reader who doesn't cross-check both files.
Per the repo's own README, this planning doc is explicitly *"Not permanent — delete
or archive once the migration is done and the reference doc reflects the
kanban-based architecture"* — and the migration has, per the reference doc's own
"Last updated" line, already completed (E2E validated 2026-07-23). This doc appears
to be past its stated shelf life and should be archived/deleted per its own stated
intent, or its "What gets removed" section corrected.

### 2.2 `docs/aws-article-fleet-reference.md` doesn't belong in this repo
It's infra notes for a Windows PowerPoint-COM article-generation fleet and an
S3/SQS video-render pipeline — completely unrelated to the Hermes tier
orchestration system this repo documents. The README's `docs/` bullet lists it
alongside `hermes-tiers-reference.md` as if part of the same reference set
("fleet/redesign docs"), which is misleading. Likely got bundled in during a
memory-offload cleanup ("moved out of always-loaded agent memory... to keep the
per-turn context lean") into whatever repo/dir was open at the time. Recommend
moving it to a repo that actually owns the article-gen fleet, or a dedicated
personal-notes repo — it has zero bearing on tier orchestration and dilutes what
"hermes-setup" is supposed to document.

---

## 3. Missing / incomplete content

### 3.1 `config/env.template` omits `TRUEFOUNDRY_API_KEY`
The live `~/.hermes/.env` carries **two** distinct TrueFoundry-related secrets:
- `TFY_API_KEY` — used by the `claude`/`codex` CLIs themselves (exported into the
  tmux session by `plugin/__init__.py`'s `_start`, per its own comment: *"ambient
  ANTHROPIC_API_KEY breaks the TrueFoundry gateway claude uses"*).
- `TRUEFOUNDRY_API_KEY` — used by `hermes`'s own provider config
  (`providers.truefoundry.api_key: ${TRUEFOUNDRY_API_KEY}` in `config.yaml.template`... except
  it isn't there either — see below).

Neither the env template nor the config template actually reference
`TRUEFOUNDRY_API_KEY`, yet without it `hermes`'s own model calls (not the
claude/codex subprocess calls) can't authenticate. A fresh-machine setup following
the templates verbatim would get the claude_orchestrate subprocess sessions working
but never notice hermes's own top-level model routing is broken until it tries to
run T1/T2 itself.

**Suggested fix:** add both keys to `env.template` with the distinction commented
inline (subprocess-CLI auth vs. hermes's own provider auth), and add the
`providers.truefoundry` block (api_key/api/default_model/models) to
`config.yaml.template` — right now the template only shows the top-level `model:`
block, not the `providers:` block the live config actually needs.

### 3.2 No mention of `hermes kanban swarm` in any doc
See §4.1 below — this is as much a missing-feature note as a "content gap," since
none of the reference docs, skills, or the redesign doc mention this native
primitive exists, even though it maps directly onto what T2's Phase 2 parallel-units
logic hand-rolls via `kanban link` + separate `claude_orchestrate` sessions.

---

## 4. Suggested improvements / feature additions

### 4.1 Evaluate `hermes kanban swarm` for the parallel-units case
`hermes kanban swarm --worker PROFILE:TITLE[:SKILLS] --verifier V --synthesizer S
<goal>` is a **native** parallel-workers → verifier → synthesizer graph primitive
in the installed hermes-agent build. `docs/tier-system-redesign.md` §4
("Independent units in parallel") describes T2 doing almost exactly this by hand:
create child kanban tasks per unit via `kanban link`, dispatch each concurrently,
then presumably reconcile. That reconciliation/verification step is exactly
`swarm`'s job, built-in. Worth a design spike: could T2's Phase 2 units-with-no-shared-deps
case delegate to `kanban swarm` instead of hand-rolling worker dispatch + an ad hoc
ledger, or is `swarm`'s worker model (Hermes-profile-only, not tmux/claude_orchestrate-based)
a poor fit because it doesn't support interactive tmux/claude sessions? Either way
this is undocumented prior art sitting one command away and should at least be
evaluated and the verdict recorded (even if "rejected, here's why" like the
existing "Prior-art verdict" section does for LangGraph/CrewAI/etc.).

### 4.2 Claude Code's native Agent Teams feature (Opus 4.6+, Feb 2026) overlaps with T2/T3
Anthropic shipped **Agent Teams** as a Claude Code feature: a lead agent spawns
2-16 teammates that share a codebase, message each other peer-to-peer via a
mailbox, and each get their own 1M-token context — no tmux, no `claude_orchestrate`
plugin, no manual send-keys/capture-pane polling. ([docs](https://code.claude.com/docs/en/agent-teams))
This is architecturally close to what `claude-orchestrate` + tier2-orchestration's
Phase 2 implementation loop does by hand (spawn N workers, supervise, gate). Since
this repo's own design principle is "no framework adopted wholesale... borrowed
mechanics, not engine," a full swap isn't necessarily right — the tier system needs
cross-engine review (Codex/Sol) which Agent Teams doesn't do, and it needs the
kanban durability/audit trail which Agent Teams doesn't provide. But at minimum
it's worth an explicit "considered, rejected because X" entry in the "Prior-art
verdict" section of `hermes-tiers-reference.md`, the same treatment given to
LangGraph/CrewAI/AutoGen/OpenAI Agents SDK/ultraswarm/Claude Squad/OpenHands.
Given it's a first-party Anthropic feature specifically for this exact use case,
its absence from that verdict list stands out.

### 4.3 Prior art: `amux` (mixpeek) — open-source control plane, tmux-native, phone/web dashboard
[github.com/mixpeek/amux](https://github.com/mixpeek/amux) — single-file,
self-healing, orchestrates "dozens of parallel Claude Code, Codex & Gemini sessions
from one web dashboard or your phone," tmux-native. This is close enough in shape
to `claude-orchestrate` + `holo dash` that it's worth a skim for ideas even if not
adopted wholesale — in particular its "self-healing" claim (auto-restart on crash)
is exactly the gap the current `orphan-reaper` fills more crudely (kill only, no
resurrect), and its phone-accessible dashboard is a lighter-weight answer to the
deferred "T0 Telegram router" than building one from scratch.

### 4.4 Prior art: Claude Squad — TUI, git-worktree isolation, multi-CLI (Claude/Codex/Aider/Gemini)
Already implicitly known to this repo (`hermes-tiers-reference.md`'s prior-art
verdict rejects it as "TUI-only") — worth re-confirming that verdict still holds,
since Claude Squad has continued to develop; if its architecture notes ("tmux +
worktrees + TUI... git worktrees hit the sweet spot: proper isolation with zero
overhead") have since added a non-interactive/scriptable mode, the rejection
rationale may be stale. Not a strong signal either way, just worth a periodic
recheck given the "designed for solo dev, not headless orchestration" framing may
have shifted.

### 4.5 The `effort=auto` bug (§1.2) suggests a small hardening pass on the plugin's own validation
Since `_start` already validates `effort` against a hardcoded set before ever
touching the CLI, that set is the single source of truth the plugin claims to
enforce — but it's out of sync with the actual `claude --help` output. A quick
`claude --help | grep -A1 effort` diff against the plugin's `enum` list would have
caught this immediately; worth adding as a periodic manual check (or scripting it)
whenever the `claude` CLI version bumps, since Anthropic could add/remove levels
without this repo's plugin schema knowing.

---

## 5. Summary punch list

| # | Item | Type | Severity |
|---|------|------|----------|
| 1.1 | README `hermes cron add --schedule` is broken syntax | Bug (doc) | Medium — blocks fresh-machine setup |
| 1.2 | plugin `effort` enum has `auto` (invalid) and lacks `xhigh` (valid) | Bug | Medium |
| 1.3 | orphan-reaper can kill a `needs_input`-waiting session | Bug | Medium — silent data/session loss |
| 1.4 | kanban-review.py missing `busy_timeout` | Bug | Low — rare race |
| 1.5 | `meta_for()` dead code in orphan-reaper.py | Cleanup | Trivial |
| 2.1 | redesign doc self-contradicts on orphan-reaper's fate, past its own shelf-life | Consistency | Low |
| 2.2 | aws-article-fleet-reference.md is off-topic for this repo | Consistency | Low |
| 3.1 | env.template / config.yaml.template missing `TRUEFOUNDRY_API_KEY` + `providers.truefoundry` block | Missing content | Medium — breaks hermes's own model calls on fresh setup |
| 3.2 | `kanban swarm` unmentioned anywhere | Missing content | Low |
| 4.1 | Evaluate `hermes kanban swarm` for T2 parallel-units | Feature/architecture | — |
| 4.2 | Record a verdict on Claude Code's native Agent Teams | Feature/architecture | — |
| 4.3 | Skim `amux` for self-healing + mobile dashboard ideas | External tool | — |
| 4.4 | Recheck Claude Squad rejection rationale is still current | External tool | — |
| 4.5 | Add a CLI-flag-drift check for `effort` values | Process | — |

---

## Sources consulted (external)

- [Claude Code Agent Teams docs](https://code.claude.com/docs/en/agent-teams)
- [amux (mixpeek) — GitHub](https://github.com/mixpeek/amux)
- [Claude Squad review — vibecodinghub.org](https://vibecodinghub.org/tools/claude-squad)
- [absmartly/Tmux-Orchestrator — GitHub](https://github.com/absmartly/Tmux-Orchestrator)
- [primelines-ai/claude-tmux-orchestration — GitHub](https://github.com/primelines-ai/claude-tmux-orchestration)

---

## Response (2026-08-08 — verified + acted on)

All 14 items independently verified against the live CLI / source. Every claim is
**confirmed true**. Actions taken:

### Bugs fixed

| # | Claim | Verdict | Fix |
|---|---|---|---|
| 1.1 | README `--schedule` syntax broken | ✅ confirmed (`schedule` is positional) | Fixed README to `hermes cron add "30m" ...` |
| 1.2 | Plugin effort enum: `auto` invalid, `xhigh` missing | ✅ confirmed via `claude --help` | Fixed enum to `{low, medium, high, xhigh, max}` |
| 1.3 | Reaper kills `needs_input`-waiting sessions | ✅ confirmed — `is_active` only checked `"esc to interrupt"` | Added `❯` prompt-marker check (mirrors plugin's `_session_state`); a session at a prompt is alive, not idle |
| 1.4 | kanban-review.py missing `busy_timeout` | ✅ confirmed — WAL set but no busy_timeout | Added `PRAGMA busy_timeout=5000` |
| 1.5 | `meta_for()` dead code | ✅ confirmed — defined, never called | Deleted |

### Inconsistencies fixed

| # | Claim | Verdict | Fix |
|---|---|---|---|
| 2.1 | redesign doc self-contradicts + past shelf life | ✅ confirmed — says reaper removed AND repurposed; doc itself says "delete once migration done" | Deleted `docs/tier-system-redesign.md` (migration complete; canonical reference doc is `hermes-tiers-reference.md`) |
| 2.2 | aws-article-fleet-reference.md off-topic | ✅ confirmed — unrelated infra notes bundled during memory offload | Removed from this repo (belongs in a fleet/personal-notes repo) |

### Missing content fixed

| # | Claim | Verdict | Fix |
|---|---|---|---|
| 3.1 | env.template missing `TRUEFOUNDRY_API_KEY` + config template missing `providers.truefoundry` | ✅ confirmed — live `.env` + `config.yaml` have both; templates had neither | Added `TRUEFOUNDRY_API_KEY` to env.template with inline distinction (subprocess-CLI vs hermes-provider); added `providers.truefoundry` block to config.yaml.template |
| 3.2 | `kanban swarm` unmentioned | ✅ confirmed — exists, not documented | Recorded verdict in `hermes-tiers-reference.md` prior-art section (rejected for parallel-units: profile-based, not tmux; no cross-engine review; no kanban claim lifecycle) |

### Prior-art verdicts recorded (in `hermes-tiers-reference.md`)

| # | Item | Verdict |
|---|---|---|
| 4.1 | `hermes kanban swarm` | Rejected — Hermes-profile workers, not tmux/`claude_orchestrate`; no cross-engine review; no claim/heartbeat/ledger. Re-evaluate if swarm gains a tmux-executor mode. |
| 4.2 | Claude Code Agent Teams | Rejected — Anthropic-only (no cross-engine review), no kanban durability/audit, no interactive steering, no human merge gate. |
| 4.3 | amux (mixpeek) | Not adopted (plugin is purpose-built + kanban-integrated; amux manages its own workers, doesn't adopt tier sessions). Self-healing pattern borrowed into the reaper (detects context-compaction, redacted_thinking, rate-limit, stuck prompts; auto-responds). |
| 4.4 | Claude Squad recheck | Reconfirmed — still TUI-only, designed for solo dev. |
| 4.5 | Effort-enum drift check | Recorded as a note in the prior-art section: diff `claude --help` against the plugin enum on every CLI version bump. |

All fixes applied in the same commit as this response.
