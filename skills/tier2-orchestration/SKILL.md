---
name: tier2-orchestration
description: Supervise one coding issue from raw task to approved PR.
version: 0.4.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Coding-Agent, Tier-2, Kanban]
    related_skills: [claude-code, codex, pr-review-toolkit, github-pr-workflow, pr-description-style, requesting-code-review, hermes-agent]
---

# Tier-2 Design + Implementation Supervisor

Drive ONE issue from a raw task to a human-approved GitHub PR merge on **process
v2** (spec: `docs/dev-process-v2.md` in the harness repo). You run the stages
around the `design` skill: set up the card, run the design skill (grounding,
author, review), get a tests-first implementation from a CLI coding agent in an
isolated worktree, run the mechanical gates and ONE code-review session, drive
the fix loop and raise the PR. You coordinate; you never write the design or the
code yourself. Detail lives elsewhere: design contract and review procedure in
the `design` skill (`~/.hermes/skills/software-development/design/`), evidence
capture, hooks and agents in `plugins/hermes-dev-process/README.md` (harness repo),
the implementer brief in `references/implementer-brief.md`.

## Activation (how a T2 session starts)

A Tier-2 session is **launched with this skill preloaded** for ONE specific
issue — normally spawned by a Tier-1 session (per repo) at handoff into a
**persistent interactive tmux session**. Launch incantation: use the canonical
form from the `hermes-session-cli-launch` reference (under the
`hermes-administration` skill) —
`tmux new-session -d -s t2-<task_id> -x 200 -y 50 'hermes chat -s
tier2-orchestration -m k3p1 --tui'` then send the brief (do NOT use the stale bare
`hermes -s <skill> --cli` form; see that reference for the failure modes and any
flag drift). It MUST NOT be launched as `hermes … -q`: a single-query process
exits when
its own turn ends, so `delegate_task` steps in the gate (test-fixer, review
fallback) get interrupted and their results are lost — the supervisor dies
mid-gate. A persistent session stays alive to receive async re-entering results. Hermes skills are advisory, so
never rely on a generic session self-selecting this role; the launch carries the
skill.
**Lifecycle: ONE T2 per issue**, torn down when the issue is merged/closed (unlike
Tier-1, which is one long-lived instance per repo). If you are reading this skill
without a specific `task_id` to drive, stop and ask which issue you are Tier-2 for.

**Preflight — kanban must be initialized.** Your claim lock, gate evidence, and
the ledger/design attachments all live in the kanban backend (native Hermes, no
daemon needed). **Pass `--board <slug>` on EVERY `hermes kanban` call** — never
rely on the sticky active board; resolution procedure per the
`tier1-suborchestration` skill's board-resolution step (T1 passes the slug in
your handoff brief). No health-check curl, no daemon — kanban is always
available as long as Hermes is running.

**No-kanban fallback (brief-driven, not a default).** A board may simply not
exist for this repo yet (never initialized). If the handoff brief explicitly
authorizes proceeding without kanban when unavailable, do so rather than
stopping to create one: skip claim/heartbeat/ledger-attach/comment calls
entirely, track unit progress via the plugin's own on-disk state
(`~/.hermes/tasks/<task_id>/status.md` / `outcome.md`) and `git log`/`git
status` directly, and report final status (design rounds used, gate results,
PR link, any process hiccups) in your own final message instead of a kanban
comment trail. In this mode, call `set_phase` on each child task before gating
it: the parent task's phase is not visible to newly started child tasks, and
the plugin refuses to gate a task below phase 3. Do NOT silently fall back on your own initiative when the brief
is silent on it — if it doesn't say what to do when kanban is unavailable,
STOP and ask, same as any other unstated-in-brief ambiguity.

## Process v2 at a glance

The card dir is `~/.hermes/tasks/t2-<kanban_task_id>/` (`<card-dir>` below).
`process.json` there with `"version": 2` turns v2 and its plugin gates on; a card
without it is **legacy** (see "Legacy cards"). All artifacts live outside the repo.

| Artifact | Written by | Content |
|---|---|---|
| `process.json` | you, Phase 1 | `{"version": 2, "tier": "none\|light\|full", "modules": ["ui","risk"], "kind": "feature\|bugfix\|refactor\|test\|copy\|config", "design_path": "<abs path or null>", "base_commit": "<sha>"}` |
| `design.md` | design author | starts with a fenced `design-meta: tier=<light\|full> modules=<ui,risk\|none>` block |
| `evidence/test-impact.txt` | grounding | existing tests that touch the change |
| `evidence/red-<unit>.txt`, `green-<unit>.txt` | implementer | first line is the exact test command, then raw runner output |
| `review/<agent>-r<round>.md`, `code-review-r<round>.md` | review sessions | agent findings and the merged verdict |
| `metrics.jsonl` | plugin, you | `{"ts","stage","event":"start\|end\|refused\|amendment","round","detail"}` per line |

Session task ids (the plugin derives stage and review kind from the names; keep
them): `t2-<ID>-ground`, `-design` (revisions and amendments `-design-revise<N>`),
`-dreview<N>`, `-impl`, `-fix<N>`, `-creview<N>`. Routes (all seatbelt): grounding
and implementation and fix round 1 `sonnet`; design author, both review sessions
and fix rounds 2 and 3 `opus`.

Tiers (set at triage, you may raise, never lower): **none** = no design, tests-first
still applies to bug fixes; **light** = short design, one-paragraph approach, lens
review; **full** = alternatives, lens plus change-impact bundle, owner gets a design
summary. Modules: `ui` (user-facing UI) and `risk` (data, migrations, external
services, auth, money, irreversible).

## Core principles (non-negotiable)

1. **Read state first, then act.** Never track loop position in your own memory.
   Position lives on disk: kanban task state + the plugin task artifacts
   (`~/.hermes/tasks/<task_id>/` — `status.md`, `result.md`, `outcome.md`, `meta.json`).
   On any resume, reconstruct from there. Re-dispatching an already-done task is
   the #1 expensive failure.
2. **The kanban claim is your safety net + heartbeat discipline.** It structurally
   prevents duplicate work even if you misjudge — but still read state first. The
   TTL is 900s (15 min). **Pass `kanban_task_id` (and `kanban_board` when set) on
   every `claude_orchestrate start`** — the plugin then auto-heartbeats the kanban
   claim from INSIDE its long blocking calls (`wait`/`gate`), throttled to 60s,
   so a >TTL blocked `wait` can't starve the claim into a stale reclaim. Still
   call `hermes kanban heartbeat <task_id> --note "<progress>"` yourself at each
   status.md write / unit completion / ledger update for progress notes — the
   auto-heartbeat only keeps the claim alive; it carries no progress context.
3. **Never trust an agent's self-report.** Verify with real tool output. `gate`
   reads the real diff; YOU run the test suite yourself. An agent writing
   `outcome=DONE` or "tests pass" is a claim, not evidence.
4. **Code comment/docstring conventions — enforce in every coding-session
   prompt.** The verbatim convention text is in `references/implementer-brief.md`
   (use that text, don't paraphrase). The T3 worker does not inherit Hermes memory
   or the user's global conventions, so the brief must carry them.

5. **Boundary rule.** Coding sessions + reviews → `claude_orchestrate` (design review
   is a Claude Code `/design-review` session, code review a `/card-review` session;
   `delegate_task` fallback only with explicit approval — different model group).
   Test-fix → a `delegate_task` sub-agent (the configured `delegation.model`). State
   + control flow → kanban CLI + on-disk state. Do not blur these.
5. **One writer per issue.** Never two concurrent implementation sessions on one
   issue. The kanban claim enforces this atomically. Distinct tasks across
   DIFFERENT issues are fine.
6. **Continuous execution.** Do not pause between units for check-ins. Stop only
   for: BLOCKED you cannot resolve, genuine ambiguity, all-done, or the human
   merge gate.
7. **Probe the prescribed route before spawning; a dead route means STOP, not a
   silent switch.** Before the first session of a card, probe its route via the
   plugin with a trivial prompt ("reply PONG"), the same `model_provider=seatbelt`
   and the same `model` the step will use, and a short timeout. All steps run
   seatbelt: `opus` for the design author, both review sessions and fix rounds 2
   and 3; `sonnet` for grounding, implementation and fix round 1. Do NOT probe with
   a raw `claude -p` (that checks the TF/Anthropic endpoint, not seatbelt). If the
   probe fails, do NOT fall back to another executor on your own — a switch changes
   the model group and billing route. STOP and get explicit human approval before
   switching any step's engine/group. Reviewer independence comes from a FRESH
   session, not a different engine. The kanban claim is independent of the executor
   — an approved switch needs no release/re-claim.
   - **Stall handling:** `stalled` = pane shows NO activity indicator AND no
     status change (a thinking/working session is NOT stalled). The operative
     `doom_loop`/stall branch is in the Phase 2 branch table below — apply it.

8. **Never `sleep`-and-peek to wait on a spawned session. Use `claude_orchestrate
   wait`.** It blocks event-driven and returns the instant the session leaves
   `working` — no fixed-interval `sleep` + `capture-pane` loop. (For non-session
   async — a `delegate_task` result, a human PR approval — poll the specific
   signal directly, don't sleep-spin.)
9. **Terminal SIGTERM on long scans.** The host kills long-running terminal
   subprocesses (exit 143, SIGTERM, no output). For anything that might run long
   (a `find`/`grep` over a large tree, a `tmux capture-pane` on a huge pane, a
   scan), use `execute_code` instead of `terminal` — it runs in the Hermes Python
   process, not a shell subprocess that gets killed. (Observed in an 8-day-old
   T2 session; the session's own words: "exit code 143 (SIGTERM) with no output.")
10. **Design = judgment → CLI coding-agent sessions, not inline reasoning.** The
    `design` skill defines the stages; you launch them through `claude_orchestrate`
    (Opus author, then ONE fresh Opus review session running `/design-review`).
    Read the VERDICT file, never the design-doc body, into your own context. The
    author never reviews its own doc: the reviewer is a fresh session every round.

11. **Reflexion one-shot on gate failure.** When a gate check fails (impl/test/
    review), don't kill the session and start fresh — steer the existing session
    with a reflection prompt: "PRIOR ATTEMPT FAILED. The failing signal was: <the
    gate output>. Reflect in one sentence on WHY it failed and what to change,
    then produce a corrected attempt. Do not repeat the same approach." Then
    re-gate ONCE. If still failing, escalate. Bounded — not a loop. (Borrowed from
    sentinel's self_heal.py — the Reflexion one-shot pattern.)
12. **Review rounds capped at 3 per kind (design, code), plugin-enforced.**
    `claude_orchestrate start` refuses a 4th review session with `escalate:true`: do
    not retry, rename or review by another route; `kanban_block kind=needs_input`
    with the latest doc or findings and the outstanding blocking issues. A blocking
    issue that reflects genuine ambiguity in the TASK itself → ESCALATE, don't spin
    another round. A start refused by the design pre-check or the missing-evidence
    gate does not count as a round (Phases 1b and 3).
13. **Deny-guard protects every spawned session.** `~/.hermes/scripts/deny-guard.sh`
    is wired into every `claude_orchestrate start` as a PreToolUse hook. It blocks
    destructive commands (rm -rf, git reset --hard, etc.) in T3 sessions. Never
    disable or bypass it.

## Inputs

- A kanban `task_id` (unit of work + orchestration namespace), created by Tier-1.
- The **raw task body** and the Tier-1 **triage decision**: `design: none|light|full`,
  `modules` (`ui`, `risk`) and `kind`. A legacy brief with `needs-design: yes` means
  `design: full`; `needs-design: no` means `design: none` (kind defaults to `feature`
  unless the card is plainly a bug fix, refactor, test, copy or config change).
  If T1 handed an already-accepted design doc (attached to the kanban task), skip
  the design stages and implement against it (record its path as `design_path`).
- Target repo `workdir` and `base_branch`; for notifications the Telegram chat id
  when the brief gives one.
- A scratch dir for grounding, design-author and review sessions (NOT the target
  repo: design touches no repo; no worktree).

## Procedure

### Phase 1 — Setup + resume check
`claude_orchestrate action=set_phase task_id=<task_id> phase=1` — record that you're in setup. Then:
1. `hermes kanban claim <task_id>` — atomically claim the issue. If another T2
   holds it, the claim fails (STOP — don't fight it). If resuming and the claim
   has expired, re-claim here.
2. `hermes kanban show <task_id> --json` — read the task state, body, and
   attachments list. If the task is already completed/merged, `hermes kanban
   reclaim <task_id>` (release the claim) and STOP.
3. If a prior session is gone but its task dir lingers, run
   `claude_orchestrate recover` (task_id or bare) to report orphaned task dirs.
   kanban's TTL handles stale claims automatically — no manual release needed
   for expired claims.
4. Choose a stable `task_id` for the tmux session (derive from the kanban task
   id, e.g. `t2-<TASK_ID>`). This is the plugin session name, separate from the
   kanban task_id.
5. **Post session context to kanban** so the dashboard card shows what's running:
   `hermes kanban comment <task_id> "tmux: t2-<TASK_ID> | branch: <branch-name> |
   repo: <workdir>"`. Do this right after claiming — the dashboard kanban tab shows
   comments, so the card immediately displays the tmux session name (for `tmux
   attach`), the worktree branch, and the repo path.
6. **Process mode.** Read `<card-dir>/process.json` if it exists: it decides the card
   (v2). If it does not exist and the card already started (a `design.md`, a ledger
   attachment or a worktree exists), the card is **legacy**: skip to "Legacy cards"
   and never create `process.json` mid-flight (that would switch gates on under a
   running card). Otherwise this is a new v2 card: continue.
7. **Raw task file.** Write the raw task to `<card-dir>/task.md`, OUTSIDE the codebase
   (never paste long task text into dispatch prompts; point agents at the file). Put
   the card body first, then a `## Binding inputs` section: standing decisions from
   kanban comments and every file the task names. All design docs, verdicts and
   briefs stay outside the worktree/repo: an in-repo brief pollutes the diff that the
   gate and `check_diff` inspect.
8. **Base commit and `process.json`.** Compute the base from the base branch, then write
   the file with the helper (it also creates `evidence/` and `review/` and logs the
   triage metric):
   ```bash
   git -C <workdir> fetch origin <base_branch>
   BASE=$(git -C <workdir> rev-parse origin/<base_branch>)
   python3 ~/.hermes/skills/tier2-orchestration/scripts/card_state.py init <card-dir> \
     --tier <none|light|full> --modules <ui,risk or empty> --kind <kind> --base "$BASE"
   ```
   `--tier` is the handoff's `design:` value (legacy `needs-design` maps as in Inputs).
   Add `--design-path <abs path>` only when T1 handed in an accepted design. Stacked
   branches: use the previous stack branch as `<base_branch>`.
9. **Context pack.** Append a `## Context pack` section to `task.md` listing, with absolute paths:
   - System guide `~/hermes-setup/repo-guides/<repo>.md` (harness repo) when it exists, with
     its `verified-at` commit. Flag it `stale` when that commit is not `BASE`: sessions
     re-verify the entries they rely on.
   - Knowledge graph `<workdir>/.graphify/graph.json` when `<workdir>/.graphify/` exists
     (query: `graphify query "<question>" --graph <path>`; use `~/.local/bin/graphify`
     when `graphify` is not on PATH).
   - Symbol tools: Serena (`activate_project` with the repo root).
   - The rule: the pack is for navigation, not evidence. Findings and design claims cite
     file:line read in the session; consumer lists are confirmed by grep.
   A missing guide or graph is fine: list what exists. Never build one inside a card.
10. Branch on the tier: `none` goes to Phase 2 (the task file is the spec). `light` and
    `full` go to Phase 1b unless a design doc is already attached to the kanban task
    (skip 1b, note its path, `card_state.py set-design <card-dir> <path>`).

### Phase 1b — Run the design skill (tier light or full, and no attached doc)
`claude_orchestrate action=set_phase task_id=<task_id> phase=1b` — record that you're in design. Then:
The `design` skill owns the contract (sections, tier rules, verification table,
review procedure). Load it once with `skill_view(name='design')` and point sessions at its files by
installed path: `<design-skill>` = `~/.hermes/skills/software-development/design`.
Design touches no repo: every session below runs in a SCRATCH DIR (no worktree) and
reads the repo at `<repo-path>` read-only. Pass `kanban_task_id` (+ `kanban_board`)
on every `start` (principle 2).

**1b.1 Grounding** (`task_id=t2-<ID>-ground`, `model=sonnet`, `effort=medium`).
Probe the route first (principle 7). Prompt: "Act as the feature-dev `code-explorer`
agent (launch it as a subagent). Read `<card-dir>/task.md` (binding inputs and context
pack are in it). Write `<card-dir>/grounding.md`: existing patterns to follow, every
consumer and call site of anything the card changes (found by grep, each marked
changing or unchanged) and the existing tests that cover those paths, all as
`path:line`. Write the test list to `<card-dir>/evidence/test-impact.txt`, one
`path:line | test name` per line. Set status complete and write DONE to your outcome
file." Gate: both files exist and contain `path:line` citations; otherwise steer once.

**1b.2 Author** (`task_id=t2-<ID>-design`, `model=opus`, `effort=high`, `executor=claude`,
`model_provider=seatbelt`). Prompt: "Read `<design-skill>/SKILL.md`, then `references/design-contract.md` and
`references/anti-patterns.md` there, and follow them for tier `<tier>`, modules `<modules>`. Inputs: `<card-dir>/task.md`, `<card-dir>/grounding.md`, the repo at
`<repo-path>` (read-only). Write the design to `<card-dir>/design.md`. Set status complete
and write DONE to your outcome file." Then `card_state.py set-design <card-dir> <card-dir>/design.md`.
RETAIN this session through the loop. `wait` (long waits are covered by the
auto-heartbeat). Never read the doc body into your context.

**1b.3 Pre-check** (no review round spent):
`python3 <design-skill>/scripts/design_precheck.py <card-dir>/design.md`. Exit 1 prints the
problems: write them to `<card-dir>/review/precheck-<n>.md`, steer the author ("Read
`<that file>` and fix every problem in place"), re-run. The plugin runs the same check
when a review starts and refuses with `precheck_failed` (no round counted); treat that
refusal like an exit 1. Three failed pre-checks in a row: ESCALATE.

**1b.4 Review: ONE Opus session per round** (`task_id=t2-<ID>-dreview<N>`, `model=opus`,
`effort=medium`, fresh every round). Prompt: `/design-review <card-dir>/design.md
card=<card-dir>/task.md binding=<card-dir>/task.md guide=<system guide path, if any>
task-dir=<card-dir> round=<N>`. The command runs the generalist pass itself and the design
agents as parallel subagents (the tier sets which), writes agent findings to
`<card-dir>/review/<agent>-r<N>.md` and the merged verdict to
`<card-dir>/design-review-r<N>.md`. Do not give the reviewer earlier verdicts or the
author's reasoning. Reviewers have a 20 minute cap: if
`wait` passes 25 minutes, apply the wedged-child recovery in Phase 2 and retry the session
once. `wait`, read the VERDICT block of the verdict file only:
```
VERDICT
approved: yes|no
confidence: <0-100>
coverage: requirements_testable, grounding_verified, behaviour_model, verification_plan,
          modules, own_failure_list_covered
blocking_issues: B1 [HIGH|MED] ...
nonblocking_suggestions: NB1 ...
```
- `approved: yes` → go to 1b.5. Record any `gaps`, `missing` or `unchecked` coverage field
  in the kanban comment.
- `approved: no` → write the blocking issues to `<card-dir>/review/blocking-r<N>.md`. Steer
  the SAME author session (or start `t2-<ID>-design-revise<N>` with the same route if it
  died; at `effort=high` a dead revise retries once at `medium`): "Read `<card-dir>/design.md` and
  `<card-dir>/review/blocking-r<N>.md`. Revise the doc in place, bump `revision`, fix every
  blocking issue and answer every blocking and non-blocking id under `Changes since review`
  (adopted or rejected with a reason). Set status complete and write DONE." Pre-check (1b.3), then a
  fresh review round. **At most 3 rounds**; the plugin refuses the 4th (`escalate:true`):
  STOP and ESCALATE with the latest doc and the outstanding blocking issues.
- A blocking issue that reflects ambiguity in the TASK itself → ESCALATE for clarification.

**1b.5 Close the design.**
1. Every NB must have an answer: `python3 <design-skill>/scripts/design_precheck.py
   <card-dir>/design.md --nb NB1,NB2,...` (the ids from the last verdict). On failure steer the
   author to answer the missing ones and re-run; no new review round. Adopted NBs become
   acceptance criteria in the implementation brief.
2. `hermes kanban attach <task_id> <card-dir>/design.md` (MANDATORY) and verify with
   `hermes kanban attachments <task_id>`.
3. `hermes kanban comment <task_id> "design approved (<tier>): confidence <N>, <coverage
   gaps or none> | NB: <a> adopted, <r> rejected"`.
4. Full tier only: send the owner a short design summary, for information only (never
   waits for a reply): problem, chosen approach and why the alternatives lost, main
   risks, the tests promised, the design path. Use the Telegram route from Phase 4
   (`hermes send -t telegram:<chat-id> "..."`) when the brief gave a chat id; otherwise
   post it as a kanban comment starting `OWNER SUMMARY:`.
5. Proceed to Phase 2.

### Phase 2 — Implementation loop (tests first)
`claude_orchestrate action=set_phase task_id=<task_id> phase=2` — record that you're implementing. Then:
The design doc comes from Phase 1b OR was handed in attached to the kanban task:
read its path from `hermes kanban attachments <task_id>` (also `design_path` in
`process.json`) and point sessions at the file; never paste the doc into a prompt. At
tier none the task file `<card-dir>/task.md` plays the design's role. At tier none and
kind `bugfix` the failing test that reproduces the bug is the RED run; other tier-none
kinds (refactor, test, copy, config) need no RED file: the existing suite staying green
is the evidence.

The **ledger is a versioned kanban attachment** (key `ledger`, JSON:
`{units:[{id,desc,status:pending|complete,commit,review}]}`; the unit `id` is the `<unit>` in
`evidence/red-<unit>.txt` and `green-<unit>.txt`), written via
`hermes kanban attach <task_id> <ledger-file>` after each unit completes. On ANY
(re)start, read it FIRST and treat `status:complete` units as done — it's the
durable recovery map that prevents re-dispatching completed work.

**Parallel units via kanban link.** If the design doc identifies independent
units (no code dependencies between them), create child kanban tasks for each
unit and link them: `hermes kanban link <parent-task_id> <child-task_id>`. This
lets you track each unit's state independently and enables parallel execution
where safe. Sequential units with dependencies stay as entries in the ledger. Heavy runs (full
suite, browser, mutation) stay one at a time per card even with parallel units.

**Dependent units compose onto accepted commits.** Parallel drafts of dependent
units may duplicate an earlier unit's helpers or state. Before a later unit's
final review, rebuild its diff on the accepted base and run the combined gates;
an isolated green run is provisional. The scope audit covers duplicate semantic
mechanisms, not just duplicate files.

**Design doc stays on the PARENT — children reference it, do NOT re-attach it.**
The design doc is a single source of truth on the top-level (parent) task. Do NOT
copy/attach it onto each child (duplication → drift). A child task carries only its
own unit-specific brief (its slice of the work) in the child's body or a small
brief attachment. The child-unit coding session's prompt points at BOTH: its
unit brief AND the parent's design attachment (read the parent doc's path from
`hermes kanban attachments <parent-task_id>`). So a child session prompt is:
"Read <unit-brief> and the design doc at <parent-design-path>, implement this unit."

Repeat until all units done or a stop condition fires. **One implementation session
per task, retained across units**: start it once (below), then steer the SAME session
into each next unit ("Read `<card-dir>/impl-brief.md`, updated for unit N, and follow it.
Commit when done.") instead of spawning a fresh session per unit. Start a new session
only if the retained one died or hit a hard context wall. Before steering, confirm it
still exists with `claude_orchestrate status`: completed sessions can vanish. If it is
gone, start a new named session in the same workdir.
1. Read the ledger attachment → first unit with `status:pending`. If none (all
   complete), go to Phase 3. (No ledger yet → derive units from the design's build
   sequence, write the initial ledger, attach it, start at unit 1.)
2. **Worktree first, then the session.** The red-before-green hook must be in place before
   the implementer's first edit, and `start` creates its worktree only as the session
   begins, so create the worktree yourself and start the session inside it:
   ```bash
   WT=<workdir parent>/.orchestrate-worktrees/<name>     # the path start would use
   git -C <workdir> worktree add "$WT" -b <name> <base_commit>   # stacked: the stack base
   ```
   Then, before `start`:
   1. Red gate hook: for cards with `kind` feature or bugfix at tier light or full, and
      bugfix at tier none (not refactor, test, copy or config), write the hook into
      `$WT/.claude/settings.local.json` with the steps in "TDD enforcement" of
      `plugins/hermes-dev-process/README.md` (harness repo; merge into an existing file).
      Delete the file when implementation ends, before the review session.
   2. Graphify seed, only when the main repo has a `.graphify/` graph (it is not
      committed, so the worktree has none):
   ```bash
   MAIN_REPO=<the repo workdir>  # NOT the worktree path
   GRAPHIFY=$(command -v graphify || echo ~/.local/bin/graphify)
   if [ -d "$MAIN_REPO/.graphify" ] && [ ! -d "$WT/.graphify" ] && [ -x "$GRAPHIFY" ]; then
     cp -R "$MAIN_REPO/.graphify" "$WT/.graphify"
     rm -f "$WT/.graphify/branch.json" "$WT/.graphify/worktree.json" "$WT/.graphify/needs_update"
     (cd "$WT" && "$GRAPHIFY" update . --no-description --no-label --no-cluster >/dev/null 2>&1)
   fi
   ```
      This is a cheap copy plus incremental reconcile (seconds, no API cost), not a cold
      build. Skip silently when there is no graph. Do not block the unit on it.
   3. Fill `references/implementer-brief.md` into `<card-dir>/impl-brief.md` for the unit
      (design path, test-impact map, context pack, adopted NB criteria).
   4. `claude_orchestrate start`: `task_id=t2-<ID>-impl`, `workdir=$WT` (no `worktree`
      argument), `executor=claude`, `model_provider=seatbelt`, `model=sonnet` (route
      comes from env, no `--model` flag), `kanban_task_id=<kanban task>` (+
      `kanban_board=<slug>`). `prompt` = the error-journal block (`python3
      ~/.hermes/scripts/error-journal.py inject claude`, skip when empty) followed by "Read
      `<card-dir>/impl-brief.md` and follow it for unit `<id>`." Keep the `task_id`
      lowercase; it is the tmux session name, separate from the kanban task id. The kanban
      claim is independent of the executor: if an engine switch is approved (principle 7)
      change the route only, never release/re-claim.
   - **Model route is prescribed, not chosen.** Launch exactly this route. If it is
     unavailable, STOP and get explicit human approval before rerouting.
3. `claude_orchestrate wait` for the session; the plugin auto-heartbeats the claim
   inside `wait` (principle 2). Heavy runs are the implementer's targeted tests only;
   the full suite and browser suite wait for the gate.
4. Branch on the returned `state` + `outcome`, and read the last `STATUS:` line of the
   session's `result.md` (the payload after it is the detail):
   - `state=done` or `exited` → read `outcome`/STATUS:
     - `DONE` → confirm the unit's `evidence/red-<unit>.txt` and `green-<unit>.txt` are
       non-empty (tier none, other kinds: skip); missing → steer the session to capture
       them from a real run, never write them yourself. Then update the ledger and go on;
       when all units are done, Phase 3.
     - `DONE_WITH_CONCERNS` → read the concerns; a real correctness or scope gap →
       steer with the missing requirement, else note the concerns on the card and go on.
     - `NEEDS_CONTEXT` → supply the missing fact (file, command, env, decision) and
       steer. If it shows the task is bigger than designed, re-tier (below).
     - `BLOCKED` with `DESIGN GAP` → the **amendment route** below. Other BLOCKED:
       context gap → add context and steer; unit too large → split it in the ledger,
       or re-tier if the whole card is larger than its tier; design fundamentally wrong
       → ESCALATE.
     - `outcome=null` on a `done` session → treat as DONE-unverified and proceed to the
       evidence check; on an `exited` session with null outcome the agent likely crashed:
       go to the failed-run branch below.
   - `state=needs_input` → the agent is asking something; read the pane, `steer` the
     answer, `wait` again.
   - `state=stalled` → check `doom_loop` in the status/wait output FIRST: if
     `doom_loop: true`, the session is in a tool-call loop (same tool + same
     normalized args 3+ times): do NOT steer or wait again, ESCALATE immediately
     (report the loop fingerprint and stop the session). If `doom_loop` is false,
     steer once ("report current status"); if the session is wedged in a think-loop,
     `interrupt` (Esc) instead of or after the steer; `wait` again; if still `stalled`,
     `diagnose` (capture pane+log), `stop`, treat as a failed run. (Stall = no activity
     indicator in the pane AND no status change; a thinking or working spinner is NOT
     stalled.)
   - **Wedged-child self-recovery:** if your `wait` has been open >10 min, check the
     child's on-disk state directly (`~/.hermes/tasks/<child-task>/result.md` and
     `outcome.md`). If the child wrote `DONE`/completed minutes ago while your `wait` is
     still open, the call is wedged: interrupt the wait (C-c), read the child's result
     and verdict files directly, and proceed. Never let a completed child hold a
     supervisor hostage.
   - **Failed/crashed/stalled run**: retry the SAME unit ONCE on the same prescribed
     route. Still failing → STOP for explicit approval before switching engines
     (principle 7); the claim stays held regardless.
5. Track an iteration counter in the ledger; exceeding a sane max (e.g. 10) → ESCALATE.
6. After each unit completes: update the ledger file and `hermes kanban attach
   <task_id> <ledger-file>`, then `hermes kanban heartbeat <task_id> --note "unit N/M
   complete"`.

**Re-tier (size).** When NEEDS_CONTEXT or BLOCKED shows the card is bigger than its
tier (a `none` card touching state, async paths, shared contracts or several consumers;
a `light` card needing alternatives): raise only. `card_state.py raise-tier <card-dir>
light|full`, run Phase 1b at the new tier (the author sees the work so far), then
resume. For units already committed, capture their RED by running the new tests on
`base_commit` in a detached worktree. Never lower a tier.

**Amendment route** (an implementer design gap, or a `design-defect` code-review finding).
The design is wrong or silent on something contract-visible; do not argue it in code. At
tier none there is no design to amend: re-tier instead. Note the start time (for the
metric's minutes).
1. The implementer stops (its worktree and commits stay). Write `<card-dir>/review/gap-<n>.md`:
   section, claim, observed reality with file:line, who found it.
2. Steer the retained author session (or start `t2-<ID>-design-revise<N>`, `opus`, `high`):
   "Read `<card-dir>/design.md` and `<card-dir>/review/gap-<n>.md`. Amend the doc scoped to this
   gap: change only what it requires, keep the may-decide list and verification table
   consistent, bump `revision`, and add a line to `Changes since review` (the change log:
   section, the claim that was wrong, what was observed, what changed). Set status
   complete and write DONE."
3. **Scope check.** An amendment that changes frozen intent (problem, goals, non-goals,
   requirements: added, dropped or reinterpreted) or changes what users or other consumers
   see beyond the design's stated surface is scope-changing: `kanban_block kind=needs_input`
   with the gap and the proposed change, and wait for the owner. Otherwise continue.
4. Pre-check (1b.3), then ONE amendment review round: a fresh `t2-<ID>-dreview<N>` session
   running `/design-review <card-dir>/design.md card=... binding=... task-dir=<card-dir>
   round=<N> amendment=<card-dir>/review/gap-<n>.md` (same other arguments as 1b.4). It counts
   toward the design-review cap; if the cap is spent, ESCALATE. Not approved after that one
   round → ESCALATE (no second amendment round).
5. Approved → re-attach the design (`hermes kanban attach`), append the metric
   (`card_state.py metric <card-dir> amendment amendment --detail '{"gap":"<n>","sections":"...","minutes":<m>,"scope_changing":false}'`), record
   `error_type=design_gap` in the error journal, and steer the implementer: "The design
   changed. Re-read `<card-dir>/design.md` sections `<list>`, update tests first (new RED if the
   table changed), then continue." Then `wait` (step 3). A gap found by code review resumes
   through Phase 3: gates, then the next review round.

### Phase 3 — Exit gate
`claude_orchestrate action=set_phase task_id=<task_id> phase=3` — required before the gate call below. The plugin refuses to gate in earlier phases. Then:
Order: impl-complete → mechanical gates → ONE code-review session → fix loop. Review
starts only after the gates pass, so a review round is never spent on code that is about
to change. Heavy runs (full suite, browser run, the review session's mutation probe)
run one at a time per card, never together.

**3.1 impl-complete.** `claude_orchestrate gate task_id=<..>` → reads the `impl` verdict.
If `impl:fail` (no `complete` / empty diff) → steer the session with a reflection prompt
once (principle 11), re-gate once; still failing → **record the failure to the error
journal** (see "Error journal wiring") with `error_type=impl_incomplete` and
`signal_trace` = the gate's fail reason, then back to Phase 2. Audit the diff against the
design's file list now: any file not in the design is a scope-creep candidate (see
Pitfalls).

**3.2 Mechanical gates.** `card_state.py metric <card-dir> gates start`; at the end `... gates end
--detail '{"minutes":<m>,"result":"pass|fail"}'`. You run these yourself via terminal in
`<rundir>`, never trusting the agent's word. Get the commands from `hermes verify <rundir>
--phase test --save` (auto-detects and persists the recipe in `.hermes/environment.json`)
or, if detection is wrong, from the repo's system guide and `package.json`. Order:
1. **Cheap gates, together** (one terminal call starting them in parallel, then
   collecting every exit code): lint, types, and the impact-scoped regression run (the
   tests in `evidence/test-impact.txt` plus every new or changed test). Also run EVERY
   test suite the diff touches, not just the primary component's: for each distinct suite
   whose files changed in `git diff --name-only <base_commit>..HEAD`, run that suite
   (a monorepo has several, each its own CI job). When a behaviour is removed or altered,
   grep for the tests that guarded it and update them in the same change.
2. **Full suite, once**, only after (1) is green. A green full suite on a commit is
   proof: do not rerun it on that commit; rerun only after the code changes. A flaky
   failure gets its cause fixed, never a rerun until green. When the suite shows failures,
   separate pre-existing from new: run only the failing tests on `base_commit` in a
   detached worktree (`git worktree add --detach <path> <base_commit>`, link
   `node_modules` if needed, remove it afterwards; never `git stash`: the stash list is
   repo-global). Block only on NEW failures; note pre-existing ones.
3. **Real-browser run, UI-module cards only**, after (1) and (2) pass: the changed flows
   through the repo's focused e2e command (system guide), one browser run at a time.
   Do not widen a focused run into the whole browser suite.
4. The mutation probe runs inside the review session (3.3), after these pass.
5. **CI scanners.** CI runs checks the local gates do not (Semgrep and other
   static/security scanners); they show up only after the PR is up. Re-poll
   `gh pr checks` in Phase 4; a scanner failure reopens the gate. Get detail via `gh api
   repos/<org>/<repo>/commits/<sha>/check-runs`, then `.../check-runs/<id>/annotations`,
   and send a normal fix session (as in 3.4, no review round consumed) with the exact
   rule id, file and line and the concrete hardening asked for (never a suppression
   comment).

A gate failure that is the implementer's code: steer the implementer session with the
failing output (reflexion one-shot, principle 11) and re-run the failed gates once; no
review round is consumed. If it fails again, record `error_type=test_failure` with the
failing test names and the first error line, then ESCALATE.
A failure that is only a missing dependency or trivial config/env: `delegate_task` a
test-fixer (the configured `delegation.model`; capture `BEFORE_SHA = git rev-parse HEAD`
first). Its context, verbatim: "Do NOT modify implementation source. You may edit ONLY
dependency/config/env files (lockfiles, requirements.txt/pyproject/package.json, .env,
CI/config). If a failure needs a production-code change, STOP and report it; do not fix
it." Enforce the fence in code, never by reading the diff: `claude_orchestrate check_diff`
with `task_id`, `base_sha=<BEFORE_SHA>`, `allowlist=["*.lock","requirements*.txt",
"pyproject.toml","package*.json",".env*","*.cfg","*.ini","*.toml",".github/**","ci/**"]`,
`reset_on_violation=true`. `clean:false` means the fixer touched source and the worktree
was reset: count the gate as failed. Max 3 fix loops.

**3.2b Live-model check for prompt or labeling changes (mandatory when applicable).**
If the card's core change is a MODEL PROMPT or a model-assigned label or classification,
fixture-fed unit tests prove only that the gate logic handles pre-labeled data. Run the
changed step LIVE once against a real (or realistically replayed) input with real spend
authorized: seed a run dir with genuine upstream artifacts, invoke only the changed
step with the real model executor, read the produced artifact and judge whether the
output is SENSIBLE against the task's intent (not only schema-valid), then feed it
through the downstream logic. This is additional to 3.2 and 3.3.

**3.3 Code review: ONE Opus session.** Delete the red gate hook file from the worktree first.
Compute the review base: `git merge-base
origin/<parent-branch> HEAD` (on a stacked branch the parent is the previous stack
branch, not trunk), so the range covers only this PR's own commits.
`claude_orchestrate start`: `task_id=t2-<ID>-creview<N>` (N = round, 1 first), fresh
session, `executor=claude`, `model_provider=seatbelt`, `model=opus`, `effort=medium`,
`workdir=<rundir>`, `kanban_task_id` (+ board). Prompt: `/card-review <design-path or none>
range=<merge-base>..HEAD task_dir=<card-dir> round=<N> tier=<tier> repo=<rundir>`
(add `brief=<card-dir>/task.md` when there is no design), then the sentence "Verdict file:
`<card-dir>/code-review-r<N>.md`" (the plugin reads that path to count findings by escape
label in `metrics.jsonl`). The command launches the
conformance reviewer, the pr-review-toolkit quality agents and, at light and full tier, the
mutation probe as parallel subagents, writes each agent's findings to
`<card-dir>/review/<agent>-r<N>.md` and the two verdicts to `<card-dir>/code-review-r<N>.md`.
- **Plugin gate.** For tier light or full, or kind `bugfix`, `start` refuses (no round
  consumed) unless `evidence/red-*.txt` and `green-*.txt` exist, are non-empty, RED shows a
  failing test and GREEN a pass. On `evidence_missing` steer the implementer to capture them
  from real runs (or fix the evidence shape), then start the review again.
- `wait`, then read ONLY the VERDICT block and the AGENTS block of the verdict file:
  ```
  VERDICT
  conformance: pass|fail
  quality: pass|fail
  findings:
  - F1 [BLOCKING|NONBLOCKING] [conformance|quality|tests|design-defect] [escape:design|impl|test] <file:line> | <concrete failure> | <required fix>
  ```
- **Hold the line on findings.** Each needs `file:line` and a concrete failure; drop (and
  count) any that lack either, and drop approach preferences (naming, structure, "could
  be simpler", other libraries). Confirm every finding carries an `escape:` label (the
  measurement depends on it); fill a missing one from the evidence. Reviewers get no
  implementer notes and no earlier transcripts.
- Both `pass` → gate passed. Go to Phase 4. NONBLOCKING findings start no fix round; keep
  them for the PR comment (Phase 4).
- BLOCKING `design-defect` → the **amendment route** (Phase 2), never an ad hoc fix. Other
  BLOCKING findings → the fix loop (3.4).
- A finding that conflicts with the design or plan text → ESCALATE (a human decides which
  governs).
- **Review route down** (probe fails): STOP for explicit human approval first; the
  `delegate_task` fallback uses a different model group. If approved, use the
  `requesting-code-review` fallback as the `pr-review-toolkit` skill's "Fallback (Claude Code
  auth down)" section specifies, fold its findings into the same verdict format, and say so
  in the gate comment.

**3.4 Fix loop.** At most **3 review rounds** (the plugin counts review sessions per
`kanban_task_id` and refuses the 4th with `escalate:true`; only a human can lift it).
For each round that has BLOCKING findings:
1. Write them (all, once) to `<card-dir>/review/accepted-r<N>.md`. One fix session for ALL
   findings, never one per finding.
2. Move the previous `evidence/red-*.txt` and `green-*.txt` into `evidence/r<N>/` and put the
   red gate hook back (README "TDD enforcement", step 4). Fix session: round 1 steers the
   original implementer (the retained `-impl` session; if gone, start `t2-<ID>-fix1`,
   `sonnet`, `workdir=$WT`). Rounds 2 and 3 start `t2-<ID>-fix<N>` on `opus`, same `workdir`. Prepend the error-journal block. Prompt: "Read `<card-dir>/impl-brief.md`
   Fix protocol section and `<card-dir>/review/accepted-r<N>.md`, and follow them." Every fix starts
   with a RED test that reproduces its finding (`evidence/red-fix<N>-<F#>.txt`), then the fix
   (`green-fix<N>-<F#>.txt`). Confirm the fix diff contains test changes; if not, steer.
3. Re-run the gates affected by the fix (3.2 order; the full suite runs once more because
   the code changed).
4. Re-review: `t2-<ID>-creview<N+1>` with `round=<N+1>`; the command reviews the fix diff
   only (range from `review/head-r<N>.txt`) plus whether each accepted finding is fixed by a
   change with a reproducing test.
After the 3rd review, findings still BLOCKING: record `error_type=review_needs_fixes` with the
outstanding findings as `signal_trace`, start no 4th round, and PARK them: go to Phase 4,
and post every outstanding finding (id, file:line, failure, escape label, why parked) as a
PR comment; say "N findings parked" in the request-review summary so the owner decides at
the merge gate.

**Gate verdict.** `hermes kanban comment <task_id> "<verdict summary>"`: impl, gates,
conformance and quality verdicts, rounds used, parked findings, any fallback.

**Measurement** (never blocks the card). The plugin appends `start`, `end` and `refused`
events to `<card-dir>/metrics.jsonl` for every session it starts; the `end` event of a code
review carries finding counts by escape label. You append what the plugin cannot see:
the `amendment` events (Phase 2), `gates` start and end (3.2), and the merge end (Phase 5),
all with `card_state.py metric`. After about 10 pilot cards, summarize with `python3
~/hermes-setup/scripts/process_metrics.py` (harness repo; `--json` for data): rounds per
card, minutes per stage, amendments and escapes by label against the audit baseline.

### Legacy cards (no `process.json`)
A card that was already running when process v2 shipped has no `process.json` and stays
on the old flow to its end; the plugin applies no gates, evidence checks or metrics to it.
Never add `process.json` to a started card. The old flow differs from v2 only here: design
(when `needs-design: yes`) is an Opus author session plus a fresh Opus review session per
round using the four-field VERDICT (`approved`, `confidence`, `blocking_issues`,
`nonblocking_suggestions`) with the same 3-round cap; implementation is a retained Sonnet
session per task that runs the suite when a unit is done; the gate runs the tests yourself
(baseline first: run the suite on the base commit in a detached worktree and block only on
new failures; the `check_diff` fence and test-fixer rules apply unchanged) and a fresh Sonnet
`/pr-review-toolkit:review-pr` session writing a verdict file, with at most 3 review→fix
rounds (one fix session for all findings per round); no escape labels. Claim, ledger,
`check_diff`, PR, merge gate, cleanup and error journal are identical to v2.

### Phase 4 — Raise PR + human approval
`claude_orchestrate action=set_phase task_id=<task_id> phase=4` — record that you're raising the PR. Then:
The review/approval surface is a **real GitHub PR**, not the local diff. Keep the
PR (and its description) as the living source of truth; do not ask the human to
watch a local worktree.

1. Gate all-pass → push the worktree branch to the remote
   (`git push -u origin <branch>`). NEVER push to / open the PR against a protected
   base by committing directly — the branch is separate, the PR targets
   `base_branch`. (PR/branch/CI mechanics: follow the `github-pr-workflow` skill.)
2. **Open (or update) a PR** targeting `base_branch` (`gh pr create`, or `gh pr
   edit` if one exists for the branch). **Write the description per the
   `pr-description-style` skill** — load and follow it; do not improvise the body.
   (In short: definitive, collaborator-facing, problem + before/after behavior;
   exclude internal review/iteration/agent-process narrative. The skill is the
   authority on what's in vs out.)
3. **Keep the PR description current** as the unit evolves — if a review→fix round
   changes behavior, edit the body (`gh pr edit --body-file -`, per
   `pr-description-style`) so it always reflects the final state. The PR body is the
   review surface; keep it accurate.
3b. **Review notes on the PR.** Post the NONBLOCKING findings from the last code review and
   any PARKED blocking findings (Phase 3.4) as one PR comment (`gh pr comment <N>
   --body-file <file>`): finding id, `file:line`, the concrete failure and, for parked ones,
   why they were parked. The owner reads them at the merge gate.
4. **Wait for CI and review bots on the exact PR head via `pr-wait.py`** (do NOT write
   ad-hoc `sleep`/`gh pr checks` loops):
   ```bash
   python3 ~/.hermes/scripts/pr-wait.py <pr_number_or_url> --until green
   ```
   `pr-wait.py` holds a per-PR lock (`~/.local/state/pr-wait/`), retries transient
   GitHub 5xx/429s with backoff, and exits `0` when all required checks pass on the
   current head (or `1` immediately if a required check fails, the branch goes `DIRTY`,
   or unresolved review threads appear, printing the exact failing check/thread URL).
   If `pr-wait.py` exits `1`, fix the CI failure or review comment in the worktree,
   commit, push, and re-run `pr-wait.py <PR> --until green` before requesting human review.
5. Link the PR back to the kanban task: `hermes kanban comment <task_id> "PR: <url>"`
   for the audit trail. Then **move the task to the `review` status** (PR is up,
   green, awaiting the human's code review):
   `hermes kanban request-review <task_id> [--board <repo>] --summary
   "PR #N up for review[; N findings parked]" --force`. **STOP.** Autonomy ends here — a human decision is
   required for EVERY merge (hard rule).
   - Use `review`, NOT `blocked`, for the normal "PR is ready, please review + merge"
     case — the dashboard shows it in the Review column. Reserve `blocked`
     (`hermes kanban block --kind needs_input <task_id> "<what you need>"`) for when
     you genuinely need the human's INPUT/decision to proceed (an ambiguity, a
     credential, a design call) — that's a different signal than "ready for review."
   - **Notify the human that a PR is ready for review** (the kanban notifier fires
     on `completed`/`blocked` but NOT `review`, so send a direct ping). `hermes
     send -t telegram "<msg>"` alone errors `No home channel set for telegram` —
     the channel must be the literal chat-id, not the bare platform name:
     ```
     hermes send -t telegram:<chat-id> "PR ready for review: <task title> — <PR url>"
     ```
     Do this once per PR, right after moving to `review`. Also subscribe the task so
     `blocked`/`completed` events auto-ping Telegram — `--chat-id` is a required
     flag, not implied by `--platform`:
     ```
     hermes kanban notify-subscribe <task_id> --platform telegram --chat-id <chat-id>
     ```
5. The human reviews and approves on the PR (GitHub approval). On approval they can
   either `hermes kanban unblock <task_id>` (if you'd blocked) or the review status
   is cleared as you proceed. Poll for the approval signal:
   `hermes kanban show <task_id> --json` (watch the status) and
   `gh pr view --json state,reviewDecision,mergedAt`. If the reviewer sends the PR
   back for changes, move it back to running:
   `hermes kanban reopen-review <task_id> --reason "..."`,
   fix, re-review. Do NOT merge before the
   block clears AND the PR shows approval.
6. **On human approval (block cleared), set auto-merge and verify it completes.**
   The human approves; you enable auto-merge so GitHub merges once CI passes —
   `gh pr merge --auto` per repo convention (`github-pr-workflow` — squash/rebase/ff
   as the base requires), with a **proper merge commit message** (clean, definitive,
   collaborator-facing, problem + before/after; NO internal narrative — per
   `pr-description-style`; supply the message, don't let `gh` auto-generate). Do NOT
   wait for the human to click merge. Then **keep polling until it actually merges**:
   auto-merge means GitHub merges when CI passes, so poll
   `gh pr view <N> --json state,mergeCommit,mergedAt` until `state=MERGED` (and
   `gh pr checks <N>` for the CI status). If CI fails, the auto-merge won't fire —
   address the failure (Phase 2/3), push, re-verify approval, re-set auto-merge. If
   the repo has auto-merge disabled, `gh pr merge --auto` errors — fall back to a
   direct `gh pr merge` (same message) and poll for the merge to land.

   **Write the merge-pending flag so the auto-complete cron picks it up fast:**
   after setting auto-merge, write `~/.hermes/tasks/<task_id>/.merge-pending`
   with `{"pr_number": <N>, "repo": "<org>/<repo>"}`. The cron polls these
   flags first (fast path) and auto-completes the task the moment the merge
   lands — no waiting for the next review-state scan. Clear the flag after
   the merge is confirmed (or the cron clears it when it completes the task).

### Rework after a post-hoc "over-built" rejection
Distinct from the Phase 1b design-review cap (which bounds rounds BEFORE
implementation). This is triggered when a human/reviewer rejects the SHIPPED
approach as overengineered after a PR is already up (e.g. a `steer-<task>.txt`
brief arriving after Phase 4) — a scope correction on live code, not a 4th design
round. The rejection itself usually specifies the minimal mechanism to keep, so a
fresh Kimi-author + Codex-reviewer design loop is unneeded overhead; author the
minimal rework directly (read_file/patch) against the rejection's own spec.
1. **Split out any separable, correct, pre-existing sub-fix bundled into the
   over-built PR into its OWN branch/PR first.** Diff precisely against the true
   base (`git diff`/`git show` on individual hunks, not a bulk cherry-pick) so
   only that isolated change + its own tests carry over — none of the abandoned
   design's other churn or incidental rewording. Verify the result is exactly
   `base + the isolated hunk` before pushing (e.g. `git diff origin/main -- <file>`
   shows only the intended lines).
2. **Reset the original PR branch to `origin/<base>` and rebuild the minimal
   version directly.** For a small, concretely-specified simplification, hand-author
   via `read_file`/`patch` rather than spinning a new design-author/review round —
   reserve the full Phase 1b loop for genuinely underspecified redesigns.
3. **Update the PR title AND body** (`gh pr edit --title ... --body-file -`, per
   `pr-description-style`) to describe the NEW minimal mechanism. Never leave an
   over-built PR's original description in place after a rework — it no longer
   matches the diff and misleads the human reviewer.
4. **Run one fresh independent code-review round** (Sonnet via seatbelt, `claude_orchestrate`)
   against the reworked diff (`origin/<base>...HEAD`) before treating it as ready.
   A smaller diff is not itself proof of correctness — get an actual approved
   verdict on the NEW diff, same as any other Phase 3.3 review.
5. **Re-verify with real test execution against the new diff**, not the prior
   PR revision's green CI — the mechanism changed, so its own test run must be
   fresh (baseline + branch, per 3.2), even if the old PR had already gone green
   once.

4. **Run one fresh independent code-review round** (`/card-review`, Opus via seatbelt, as in
   Phase 3.3) against the reworked diff (`origin/<base>...HEAD`) before treating it as ready.
   A smaller diff is not itself proof of correctness: get an actual passing verdict on the NEW
   diff. It counts toward the plugin's 3-round cap.

5. **Re-verify with real test execution against the new diff**, not the prior
   PR revision's green CI — the mechanism changed, so its own test run must be
   fresh (baseline + branch, per 3.2), even if the old PR had already gone green
   once.

### Phase 5 — Cleanup
`claude_orchestrate action=set_phase task_id=<task_id> phase=5` — record that you're cleaning up. Then:
1. Mark the task done. The task is in `review` (Phase 4 moved it there for the
   merge gate), and `hermes kanban complete` accepts review-state tasks. Use:
   `hermes kanban complete <task_id> --result "merged via PR #N" --summary "<2-3 sentence handoff: what changed, key decisions>" --metadata '{"changed_files": [...], "pr": <N>}'`.
   The `--summary` and `--metadata` feed `hermes kanban context` so downstream
   tasks and the T1 dispatcher can see what was done without opening the PR.
2. `hermes kanban reclaim <task_id>` — release the claim (do this BEFORE
   self-terminating so the claim doesn't linger until TTL expiry).
3. Close the measurement: `card_state.py metric <card-dir> merge end --detail
   '{"pr":<N>,"review_rounds":<n>,"parked":<n>}'`. Then prune the card's scratch and large
   logs (avoid unbounded growth) but KEEP `process.json`, `metrics.jsonl`, `design.md` and
   `review/` (`scripts/process_metrics.py` reads them). Remove only worktrees this run
   created (`git -C <workdir> worktree remove $WT` after the merge lands).
4. Escape analysis: when a code-review finding labelled `escape:design` traces to a wrong or
   missing entry in the system guide, record it as a linked kanban task naming the guide
   entry and the file:line that disproves it (see "Recording discovered work"); do not edit
   the harness repo from a card.

**Self-terminate.** As the FINAL step, once the issue reaches a terminal state
(merged, discarded/rejected, or escalated-and-handed-off — i.e. nothing more for
this supervisor to do), kill your own tmux session so it stops holding a `hermes`
process in memory: `tmux kill-session -t t2-<task_id>`. A per-issue T2 must not
linger after its issue is done. (Only the happy/decided path self-reaps; a T2 that
errors out BEFORE Phase 5 will still linger — an external reaper is possible future
scope.)

## Escalate to a human when
- BLOCKED because the plan/design is fundamentally wrong.
- Design review not approved after the 3rd round (design non-convergence; send
  latest doc + outstanding blocking issues; do NOT start a 4th round), or three
  failed pre-checks in a row.
- A design amendment that changes scope (requirement added, dropped or reinterpreted, a
  non-goal crossed), or an amendment review that is not approved after its one round.
- A design blocking issue reflects genuine ambiguity in the TASK itself (not the
  doc) → human clarification needed before another design round.
- Missing access you cannot resolve yourself — a credential, permission, or
  environment gap that blocks implementation or the gate.
- A step's prescribed route is unavailable — engine/model-group switches need
  explicit human approval (principle #7); escalate if none is granted.
- Implementation loop or test-fix loop hits max iterations (test failures that
  stay red after the bounded fix loops in Phase 3.2).
- A review finding conflicts with the design or plan text (human decides which governs).
- The gate cannot pass after retries. Blocking code-review findings left after the 3rd
  round are parked on the PR (Phase 3.4), not escalated separately.
- Always, for the merge decision.

Dispatcher-level calls (which repo a task belongs to, whether a task is even
well-formed enough to triage, cross-repo scope) are NOT yours — surface those
back to T1 rather than deciding them here.

## Error journal wiring (auto-promoted lessons)

The error journal at `~/.hermes/scripts/error-journal.py` captures recurring
T3 gate failures and auto-promotes them to candidate rules that get prepended
to future coding-session prompts.

- **Journal:** `~/.hermes/tier_orchestrator/error_journal.jsonl` (append-only).
- **Candidate rules:** `~/.hermes/tier_orchestrator/auto_skills/<error_type>.md`
  — each marked `[auto-promoted, needs-review]` at the top. They are NOT loaded
  as Hermes skills; a human reviews and (optionally) promotes them by hand.
- **Threshold:** 3 occurrences of the same `error_type` triggers promotion.
  Override via `TIER_ERROR_PROMOTE_THRESHOLD` env var.

**Record on gate failure.** When any gate check fails (impl, tests, review),
call:
```bash
python3 ~/.hermes/scripts/error-journal.py record \
  <task_id> <agent_type> <error_type> \
  "<signal_trace — what specifically was misread>" \
  "<what_should_have_happened>" \
  ["<prompt_snippet — optional short excerpt>"]
```
Use `agent_type` = the executor that produced the failure (`claude`, `codex`,
or the delegation model for a delegate_task fixer). `error_type` is a short snake_case
slug (e.g. `impl_incomplete`, `test_failure`, `review_needs_fixes`,
`auth_expired`, `context_overflow`, `stuck_loop`). Keep `signal_trace` specific
— not "tests failed" but "test_foo.py::test_bar AssertionError: expected 3
got 4".

**Inject on T3 spawn.** Before composing every Phase-2 coding-session prompt
(and every fix-session prompt), run:
```bash
python3 ~/.hermes/scripts/error-journal.py inject <agent_type>
```
Prepend the returned markdown block to the prompt. Empty output = no active
rules for that agent; skip silently.

**Inspect / force-promote.** `patterns` shows what's near/over threshold;
`promote` rewrites the candidate files (idempotent — run after a batch of
records to refresh counts).

## Recording discovered work (out-of-scope findings)

If you find a bug, missing test, or improvement while implementing that is
NOT part of your current task's scope — per the no-scope-creep rule, fix
your assigned task only, don't fold the extra work in. Record the finding as
a **linked task**, not just a kanban comment (comments get buried; a link is
queryable graph structure):

```
hermes kanban create "Fix <thing found>" --board <slug> --triage
hermes kanban link <this_task_id> <new_task_id>
```

This makes the origin task the parent of the discovered one — `hermes kanban
list --status triage` (or a T1 sweep) surfaces it later without anyone
having to recall which task's comments to dig through. Do this at the moment
you find it, not as a batch cleanup at the end — findings noted only in your
head are lost when the session ends.

## Pitfalls
- **Worker tool quirks** (kanban_create id echo, tool_call payload corruption, worker CLI mutation refusal, `gh pr checks --json` on gh 2.45, tmux submit) live in `references/worker-tool-pitfalls.md`. Read it before driving kanban workers or tmux sessions.
- **Implementation sessions tend to bundle adjacent-but-unassigned functionality into the diff — audit the diff against the task's stated scope before Phase 4, don't just check the gate.** Observed: a task to build a "JSONL→markdown transcript adapter" also implemented an unrequested Google-Drive fetch/unpack/workflow-wiring step, roughly tripling the PR's size and duplicating logic that may already exist elsewhere in the pipeline (the user caught it only from the PR size: "why is this which is basically a transcription converter that big?"). Before opening/updating the PR, diff the actual changes against the task description — if the diff does something the task never asked for, split it into a separate task/PR (or drop it) rather than folding it in as "while I was there." This matters most when the user has pre-delegated merge trust (e.g. "assume I'm okay with these as long as comments aren't too verbose") — the PR won't get a manual scope read from them, so the scope check has to happen here, before the PR goes up.
- **A persistent T2 kept alive across multiple tasks does NOT self-close the
  task it's leaving.** Phase 5 (`complete` + `reclaim` + self-terminate) only
  fires when the session actually exits. If T1 (or you) steers a still-alive
  T2 onto a new task instead of spawning a fresh one, the OLD task's Phase 5
  never runs — it's on whoever reassigns the T2 to close the outgoing task
  (`hermes kanban complete <old_task_id> --result "merged via PR #N"`) right
  at reassignment time, not later.
- **Block syntax gotcha (argparse ordering):** `--kind needs_input` must come
  BEFORE the task_id — `hermes kanban block --kind needs_input <task_id> <reason>`.
- Pasting accumulated history or the design-doc body into dispatch prompts → use
  file handoffs (out-of-repo paths); read only verdict files.
- Letting the test-fixer edit implementation source → enforce with `check_diff`
  (`reset_on_violation=true`), never your own read of the diff.
- stop→release→re-claim around an executor switch → DON'T; the claim is
  independent of the executor (and any switch is approval-gated — principle #7).
- Running design sessions in the target repo / with a worktree → design touches no
  repo; use a scratch dir (the author READS the repo but does not write to it).
- Forgetting to attach the accepted design doc (`hermes kanban attach` + verify
  with `hermes kanban attachments`) before Phase 2 → the implementation loop reads
  the doc from the attachment.
- **`claude_orchestrate wait` can itself throw (observed: `NameError` referencing
  an internal `artifact_dir` var, on every call for the affected session) —
  distinct from the session being stalled/stuck.** When `wait` errors instead of
  returning a state, don't retry `wait` in a loop; fall back to polling the
  session's on-disk state directly (`status.md` / `outcome.md` under
  `~/.hermes/tasks/<task_id>/`, same files principle #1 already treats as the
  durable source of truth) until it reads `complete`/`DONE`.
- **A design author/revise session (`effort=high`) can die silently (exit with no
  outcome) on a revision turn, reproducibly, while the same prompt at
  `effort=medium` completes cleanly.** Observed twice in one Phase 1b.4 revise
  loop. If a design session dies with no outcome at `effort=high`, retry the SAME
  revision prompt once at `effort=medium` before treating it as a stalled/crashed
  session — an engine switch is approval-gated (principle #7), so the same-route
  retry is the cheaper first try.
- **Evidence is never authored by you or by an agent's summary.** `evidence/red-*.txt` and
  `green-*.txt` are raw output of real runs with the exact command on line 1; the plugin
  refuses a code review without them. Steer the implementer to capture a real run; never
  write the file yourself.
- **Session names are the plugin's classifier.** Use `-ground`, `-design`,
  `-design-revise<N>`, `-dreview<N>`, `-impl`, `-fix<N>`, `-creview<N>`. A review that is
  not named and prompted as a review is not counted against the 3-round cap, and a fix named
  like a review is.
- **Never write `process.json` on a card that already started**; it would switch gates on
  under a running legacy card. Only `card_state.py raise-tier` changes an existing file.
- **Review sessions get paths, never earlier verdicts or the author's reasoning**; a pasted
  verdict anchors the reviewer. The host is small: the full suite, the browser run and the
  mutation probe never run at the same time on one card.
- **The amendment review is a design review round** (plugin cap 3): if the cap is spent,
  ESCALATE instead of retrying.
- Longer pitfalls and per-incident lessons (fix commits that land on other PRs' branches,
  shared-checkout branch collisions, verifying against the committed branch, the legacy
  Fireworks trust-dialog stall, test-baseline and rebase recipes, and more) live in
  `references/lessons.md`. Read it when the situation matches.
