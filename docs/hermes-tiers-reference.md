# Hermes Multi-Tier Orchestration — Reference

**Last updated: 2026-08-08.** The tier system is built, migrated to kanban, E2E
validated, audited (audit-2026-07-30), and self-healing reaper added.

---

## What we built

A multi-tier autonomous coding pipeline on top of Hermes Agent:

**No orchestrator tier ever authors, reviews, or edits anything in-process.** T2
decides *what* needs doing and judges what comes back; every unit of actual work —
design, design review, implementation, tests, code review — is a T3 session. When
the tier docs say T2 "authors a design doc", that means T2 spawns a T3 session which
authors it.

- **T1** (per-repo, long-lived) — a *pure stateless dispatcher*. Takes task
  descriptions, triages design-vs-build FROM THE DESCRIPTION ALONE (never reads
  source), creates a kanban task, and hands the RAW task to T2 — with a
  needs-design flag. T1 does NOT run the design loop or spawn design authors/
  reviewers; that's T2's job. Stays warm across many issues (~1-2% context
  each). Points the user at the dashboard for progress.
- **T2** (per-issue, spawned in tmux) — a *design + implementation supervisor*.
  Claims the kanban task (atomic lock). If needs-design (and no doc was handed
  in), runs the design author (Kimi K3 via Fireworks, high effort) + design review
  (Codex/Sol, cross-engine, 3-round cap) loop ITSELF, attaches the accepted doc,
  then implements unit-by-unit against it. Spawns T3 coding sessions in isolated
  worktrees, runs the exit gate (impl + tests + review — each gate step that
  needs work done is itself a T3 session), raises a GitHub PR, moves to `review`,
  pings the human on Telegram, stops at human merge approval, self-terminates
  when done. Heartbeats kanban to keep the claim alive (TTL 900s).
  Never writes the implementation itself.
- **T3** — the executor: the Claude Code CLI (routed to kimi-k3 via Fireworks'
  Anthropic-compatible endpoint) or the Codex CLI, driven in tmux by the
  `claude-orchestrate` plugin. The only layer that reads or writes repo files. One
  session per work unit, whatever the kind: design, design review, implementation,
  tests, code review. Reports `DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED`.
- **T0** — Telegram thin router (deferred, not built).

**Coordination backend:** Hermes-native **kanban** (`hermes kanban` CLI, SQLite in
`~/.hermes/kanban.db`). No external daemon, no port. One kanban board per repo.

**Visibility:** the native **Hermes dashboard** (`hermes dashboard`, port 9119) with
the kanban tab — shows all tier tasks as cards with live state. No custom dashboard
to build.

## How to use it

```bash
# Start the dashboard (opens http://localhost:9119 in your browser)
holo dash

# Start a Tier-1 session for a repo (from the repo directory)
holo 1
# or just: holo

# Start a Tier-2 session directly for a specific issue (rare — T1 usually does this)
holo 2

# In a T1 session, just describe the task:
# "new issue: change the popup flag from per-lesson to per-interaction"
# T1 triages, creates a kanban task, spawns T2, and says "watch the dashboard"
```

## Launch commands (in `~/.zshrc`)

| Command | Does |
|---------|------|
| `holo` or `holo 1` | `hermes -s tier1-suborchestration` — Tier-1 session (default) |
| `holo 2` | `hermes -s tier2-orchestration` — Tier-2 session |
| `holo dash` | `hermes dashboard` — web dashboard at localhost:9119 |

Tier sessions MUST be persistent interactive tmux sessions, NOT `hermes … -q`
(single-query exits and strands delegate_task results). Exact spawn incantation
per the `hermes-session-cli-launch` skill. Claim keep-alive is structural: T2
passes `kanban_task_id`/`kanban_board` on every `claude_orchestrate start`, and
the plugin auto-heartbeats the kanban claim from inside its long blocking
`wait`/`gate` calls — see the plugin's auto-heartbeat bullet below and the
tier2 skill's claim/heartbeat principle (#2).

## The plugin — `claude-orchestrate`

`~/.hermes/plugins/claude-orchestrate/__init__.py` — a pure tmux session manager
(13 actions). No coordination logic — all kanban calls are in the skills.

Actions: `start` · `status` · `wait` · `steer` · `interrupt` · `result` · `stop` ·
`list` · `recover` · `gate` · `clean` · `check_diff` · `diagnose`

Key features:
- `start` — launches Claude Code or Codex in tmux; optional `effort` (claude
  `--effort`), `model`, `worktree`. Exports `TFY_API_KEY` into the tmux session
  (the server may not inherit it). Codex prompt sent via `send-keys` (positional
  args trigger a 0.144.x bug). Accepts optional `kanban_task_id`/`kanban_board`
  linkage, recorded in the session's `meta.json` for the auto-heartbeat.
- Kanban auto-heartbeat — when a session was started with `kanban_task_id`, the
  plugin heartbeats that kanban claim from INSIDE the long blocking `wait`/`gate`
  calls (throttled to 60s per session, forced once at `gate`; failures never
  raise). This is the structural fix for a >TTL blocked `wait` starving the
  900s claim into a stale reclaim — the supervisor's event loop is blocked
  inside `wait`, so the heartbeat has to come from inside the plugin. T2 still
  heartbeats manually at progress points for the note text.
- Four-status outcome — agents write `DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED`
  to `outcome.md`; `status`/`wait`/`result` surface it.
- Tool-agnostic stall detection — `stalled` requires BOTH no status.md/outcome.md
  change for N seconds AND no live activity indicator in the pane (spinner /
  "esc to interrupt" / token counter). A thinking session (high-effort turns can
  think for minutes without writing files) shows the indicator, so it stays
  `working` — never false-flagged as stalled.
- `interrupt` — sends Esc; use ONLY on a genuinely stalled session (no indicator,
  no file change), never on one that's actively thinking.
- `diagnose` — non-destructive pane+log+meta+state dump for hang root-causing.
- `check_diff` — deterministic path-allowlist fence for the test-fixer.
- `gate` — impl-complete check + composite verdict from external review/tests.

## Kanban coordination (in the skills, not the plugin)

| Concern | Command | Used by |
|---------|---------|---------|
| Create task | `hermes kanban create <title> --body <desc> --json` | T1 |
| Atomic claim (lock) | `hermes kanban claim <task_id>` (TTL 900s) | T2 |
| Release claim | `hermes kanban reclaim <task_id>` | T2 |
| Heartbeat (keep alive) | `hermes kanban heartbeat <task_id> --note <text>` — plus plugin auto-heartbeat inside `wait`/`gate` for sessions started with `kanban_task_id` | T2 |
| Gate evidence | `hermes kanban comment <task_id> <text>` | T2 |
| Design doc / ledger | `hermes kanban attach <task_id> <file>` | T2 |
| Human merge gate | `hermes kanban request-review <task_id> [--board <b>]` (running→review) | T2 (PR up for review) |
| Needs-input gate | `hermes kanban block --kind needs_input <task_id> <reason>` | T2 (needs human INPUT) |
| Human approves | `hermes kanban unblock <task_id>` | Human |
| Complete (review→done) | `hermes kanban complete <task_id> --result <text>` | T2 (after merge) |
| Dependencies | `hermes kanban link <parent> <child>` | T2 (parallel units) |
| Stale-claim sweep | `hermes kanban dispatch` (reclaims dead-process claims) | Gateway/cron |

(Block syntax gotcha: see the tier1/tier2 skills' Pitfalls sections.)

## Design principles (non-negotiable)

1. **Verify, never trust.** Gate reads real diffs; supervisor runs tests itself.
2. **Read state first.** Position lives in kanban, not agent memory.
3. **Enforce at launch.** Tier role = preloaded skill (`holo`/`holo -2`).
4. **Interactive tmux, not headless.** Live steering, prompt detection.
5. **Human authority is explicit.** Every merge requires human approval.
6. **Bounded loops.** 3 rounds design review, 3 rounds code review, 3 test-fix
   loops, ~10 implementation iterations — all → escalate.
7. **No orchestration files in the codebase.** Briefs, outcomes, ledgers live in
   kanban attachments or artifact dirs, never committed to repos.
8. **Never sleep-and-peek.** Use `claude_orchestrate wait` (event-driven).
9. **T1 never reads source code.** Triage from task description alone.
10. **Orchestrators never do the work.** T1/T2 dispatch and judge; all authoring,
    reviewing, and editing happens in a T3 session. "T1 authors a design doc" is
    shorthand for "T1 spawns a T3 that authors it".
11. **Skills are self-contained.** No external doc references; cross-skill refs OK.

## Gate order (Phase 3)

Per the tier2 skill's Phase 3: tests + review run in PARALLEL; tests fail fast —
address a fast test failure first, re-run both once the code is stable.

## Phase 4 — PR + human approval

Per the tier2 skill's Phase 4: push → PR (description per `pr-description-style`)
→ human review gate → human approves → T2 sets auto-merge and polls until merged →
cleanup (branch/worktree, `kanban complete` + `reclaim`) → self-terminate.

## Auth fallback

Probe + fallback routing per the tier2 skill's auth-fallback principle (probe via
the plugin with `model_provider=fireworks`, never raw `claude -p`). The routing
summary, in short: coding + T1 author/review → `executor=codex`; T2 code review →
`requesting-code-review` via delegate_task (kimi-k3).

**Effort (defaults):** T2 design author/reviser = `effort=high` (design is
judgment-heavy, kimi-k3 via Fireworks). T2 coding sessions = `effort=medium`. T2
code review = `effort=medium`.
A *thinking* session is not a stalled one — stall detection ignores file-staleness
when the pane shows an activity indicator. Genuine stall (no indicator + no file
change) → `interrupt` (Esc) once → `diagnose` → fall back to Codex.

## State-transition review

Covered by the `pr-review-toolkit` skill — see the `state-transition-reviewer`
row in its specialist-reviewers table (triggers, adversarial paths, output).

**Gate order:** tests (fast, fail-fast) then review (expensive) in PARALLEL — the
exit gate runs both concurrently, acting on tests first if they fail fast.

## Orphan reaper

`~/.hermes/scripts/orphan-reaper.py` — silent `no_agent` cron (every 30m) that
heals recoverable failure modes and kills genuinely IDLE tier tmux sessions
(behavior + boundary vs kanban `dispatch` per the README).

## What's deferred

- **T0** (Telegram router) — thin, skill-only when built.
- **Reboot-persistent dashboard** — `holo-dash` covers it for now.
- **Adversarial QA (3.4)** — optional, high-risk only.
- **Per-repo kanban boards** — each board is bound to its repo path via
  `default_workdir` (`hermes kanban boards create <slug> --default-workdir <repo>`
  or `boards set-default-workdir <slug> <repo>`). Slugs do NOT match repo basenames:
  `/Users/ayush/Trilogy/app` → `learning-app`; `/Users/ayush/Trilogy/content` →
  `alpha-learn-content-gen`. Resolve the board via `hermes kanban boards list --json`
  (match `default_workdir` to the repo path) and ALWAYS pass `--board <slug>`
  explicitly — never rely on the sticky active board (it drifts; caused tasks to
  land on the wrong repo's board).
- **Independent units in parallel** — `kanban link` is ready; T2 needs to dispatch
  concurrent worktrees for independent units (built into the skill, not yet
  exercised in a live multi-unit run).

## What we migrated from (historical context)

The tier system was originally built on **Paperclip** (an external daemon with
embedded Postgres at localhost:3100). We migrated to **kanban** (native Hermes)
because:
- No external daemon/port/dependency (kanban is SQLite in `~/.hermes/`)
- Native dashboard with WebSocket (no custom plugin to build)
- Native notifications, heartbeat, dependency graph
- Better maintainability (ships with Hermes, maintained by the Hermes team)

Paperclip is fully retired (clone, daemon, data dir, launcher — all removed;
backups in `~/.hermes/backups/`). The two gaps (no versioned documents, no
structured approval object) have adequate workarounds: attachments + comments for
docs, `block`/`unblock` for the human gate (which is now PR-based anyway).

## Prior-art verdict

Built thin on our own primitives — no framework adopted wholesale. Every agent
framework (LangGraph, CrewAI, AutoGen, OpenAI Agents SDK) owns the LLM/execution
loop, which inverts our architecture. ultraswarm (closest prior art) makes opposite
choices on all axes; we borrowed its mechanics (completion gate, structured-feedback-
on-reject, squash→gate→ff-only merge), not its engine. Rejected: Claude Squad
(TUI-only, designed for solo dev — reconfirmed 2026-07-30), OpenHands (too volatile),
claude-code-acp (solo, stateless `-p`).

Additional prior art evaluated (2026-07-30 audit):

- **`hermes kanban swarm`** (native): a worker→verifier→synthesizer graph primitive
  in the installed Hermes build. Rejected for T2's parallel-units case: `swarm`'s
  workers are Hermes-profile-based (not tmux/`claude_orchestrate`), so they can't run
  interactive coding sessions, don't support cross-engine review (Codex/Sol), and
  don't use the kanban claim/heartbeat/ledger lifecycle T2 depends on. T2's hand-rolled
  `kanban link` + `claude_orchestrate` dispatch stays. Worth re-evaluating if `swarm`
  gains a tmux-executor mode.
- **Claude Code Agent Teams** (Anthropic, Opus 4.6+): a lead agent spawns 2-16
  teammates sharing a codebase with peer-to-peer mailboxes, each with 1M context —
  no tmux, no plugin. Architecturally close to T2's Phase 2 loop. Rejected: no
  cross-engine review (Anthropic-only), no kanban durability/audit trail, no
  interactive steering/`steer`/`interrupt`, no human merge gate. The tier system's
  cross-engine + kanban + human-gate requirements are load-bearing and Agent Teams
  doesn't provide them.
- **Ralph Workflow** (Ralph-Workflow/Ralph-Workflow): an orchestrator for the agents
  you already have (Claude Code, Codex CLI) — define a workflow in a TOML file,
  run overnight. Rejected: no kanban coordination, no interactive steering, no
  cross-engine review, no human gate, no persistent memory. Solves a simpler
  problem (single task, not a multi-issue pipeline).
- **Beads** (gastownhall/beads): distributed graph issue tracker for agents (Dolt
  backend). Rejected: redundant with kanban (task tracking + dependencies +
  dashboard + notifications already covered). The persistent-memory angle
  (`bd prime`/`bd remember`) is interesting but we already have reference docs +
  skills. Same category as other rejected prior art.
- **Effort-enum drift note:** the plugin's `effort` validator must match `claude --help`'s
  accepted values. A 2026-07-30 audit caught `auto` (invalid, claude rejects it) and a
  missing `xhigh`. Fixed to `{low, medium, high, xhigh, max}`. On every `claude` CLI
  version bump, diff `claude --help | grep -A1 effort` against the plugin's enum.
