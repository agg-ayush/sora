# Hermes Multi-Tier Orchestration — Reference

**Last updated: 2026-07-23.** The tier system is built, migrated to kanban, and E2E validated.

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
  in), runs the design author (Claude/Opus, high effort) + design review
  (Codex/Sol, cross-engine, 3-round cap) loop ITSELF, attaches the accepted doc,
  then implements unit-by-unit against it. Spawns T3 coding sessions in isolated
  worktrees, runs the exit gate (impl + tests + review — each gate step that
  needs work done is itself a T3 session), raises a GitHub PR, moves to `review`,
  pings the human on Telegram, stops at human merge approval, self-terminates
  when done. Heartbeats kanban to keep the claim alive (TTL 900s).
  Never writes the implementation itself.
- **T3** — the executor: Claude Code / Codex CLI, driven in tmux by the
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
(single-query exits and strands delegate_task results). **Spawn with `--cli`**
(`hermes -s tier2-orchestration --cli`): if `display.interface: tui` is the
default, the TUI's stdin closes (EOF) in a detached tmux pane and the parent dies
within minutes — `--cli` forces the classic REPL, which handles detached stdin
correctly. **Heartbeat the kanban claim during any long `claude_orchestrate wait`**
(design-author/review waits can exceed the 900s TTL): call
`hermes kanban heartbeat <task_id>` every ~10 min while waiting, or the claim
expires and another T2 can double-claim.

## The plugin — `claude-orchestrate`

`~/.hermes/plugins/claude-orchestrate/__init__.py` — a pure tmux session manager
(13 actions). No coordination logic — all kanban calls are in the skills.

Actions: `start` · `status` · `wait` · `steer` · `interrupt` · `result` · `stop` ·
`list` · `recover` · `gate` · `clean` · `check_diff` · `diagnose`

Key features:
- `start` — launches Claude Code or Codex in tmux; optional `effort` (claude
  `--effort`), `model`, `worktree`. Exports `TFY_API_KEY` into the tmux session
  (the server may not inherit it). Codex prompt sent via `send-keys` (positional
  args trigger a 0.144.x bug).
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
| Heartbeat (keep alive) | `hermes kanban heartbeat <task_id> --note <text>` | T2 |
| Gate evidence | `hermes kanban comment <task_id> <text>` | T2 |
| Design doc / ledger | `hermes kanban attach <task_id> <file>` | T2 |
| Human merge gate | `python3 ~/.hermes/scripts/kanban-review.py <task_id> [--board <b>]` (running→review) | T2 (PR up for review) |
| Needs-input gate | `hermes kanban block --kind needs_input <task_id> <reason>` | T2 (needs human INPUT) |
| Human approves | `hermes kanban unblock <task_id>` | Human |
| Complete (review→done) | `python3 ~/.hermes/scripts/kanban-review.py <task_id> --to done --result <text>` | T2 (after merge) |
| Dependencies | `hermes kanban link <parent> <child>` | T2 (parallel units) |
| Stale-claim sweep | `hermes kanban dispatch` (reclaims dead-process claims) | Gateway/cron |

**Block syntax gotcha:** `--kind needs_input` must come BEFORE the task_id (argparse
ordering). Correct: `hermes kanban block --kind needs_input <task_id> <reason>`.

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

3.1 impl-complete → **3.2 tests** (fail-fast) → **3.3 review** (parallel with
tests where possible) → 3.4 adversarial QA (optional, high-risk only).

Tests before review: tests are a fast deterministic gate; review is expensive.
Running review on code that fails its tests wastes a round. Tests-first means the
reviewer sees a passing baseline; its coverage findings (pr-test-analyzer) then
lead to additional tests you can validate.

## Phase 4 — PR + human approval

Push branch → open/update GitHub PR (`gh pr create`/`edit`, description per
`pr-description-style` skill, kept current) → `kanban block --kind needs_input`
→ **STOP** (human gate) → human approves on PR → T2 merges (`gh pr merge`, proper
message per `pr-description-style`) → verify tests → delete branch + worktree →
`kanban complete` + `reclaim` → self-terminate (`tmux kill-session`).

## Auth fallback

Claude Code auths through a gateway that occasionally times out. Before spawning a
claude session, probe `claude -p "reply PONG"` (~30s cap); if it fails, fall back:
- Coding → `executor=codex`
- T1 author/review → Codex sessions
- T2 code review (`/pr-review-toolkit:review-pr`) → `requesting-code-review` skill
  via delegate_task (glm-5p2)

**Effort:** T1 design author/reviser = Opus at `effort=high` (design is
judgment-heavy). T2 coding sessions = `effort=medium`. `effort=high` on Opus via the
TF gateway can occasionally wedge, but a *thinking* session is not a stalled one —
stall detection now ignores file-staleness when the pane shows an activity
indicator, so it won't false-trip. Genuine stall (no indicator + no file change) →
`interrupt` (Esc) once → `diagnose` → fall back to Codex.

## Orphan reaper

`~/.hermes/scripts/orphan-reaper.py` — silent `no_agent` cron (every 30m). Kills
idle tier tmux sessions (never active ones showing "esc to interrupt"). Kanban's
`dispatch` handles stale claims (dead-process detection). Together they prevent
orphaned sessions from accumulating.

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
(TUI-only), OpenHands (too volatile), claude-code-acp (solo, stateless `-p`).
