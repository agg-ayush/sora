---
name: tier2-orchestration
description: "Drive a single coding issue from a raw task to a human-approved GitHub PR merge as a Tier-2 supervisor owning BOTH design and implementation. Use when orchestrating autonomous coding work: (design) author a design doc via a Kimi K3 session (Fireworks, high effort), cross-engine review it via a Codex/Sol session (3-round cap); (implement) assign the accepted design to a CLI coding agent in an isolated worktree, keep it working with stall detection, run an exit gate (impl-complete + pr-review-toolkit code review + separate-model test-fix), then raise a GitHub PR (keeping its description current as the review surface) and stop at human approval/merge on the PR. Sequences the claude_orchestrate tool (Claude Code / Codex sessions), a delegate_task test-fixer, gh for PRs, and kanban (issue tracking + claim lock + blocks + design-doc attachment)."
version: 0.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Coding-Agent, Tier-2, Kanban]
    related_skills: [claude-code, codex, pr-review-toolkit, github-pr-workflow, pr-description-style, requesting-code-review, hermes-agent]
---

# Tier-2 Design + Implementation Supervisor

Drive ONE issue from a raw task to a human-approved GitHub PR merge. You own TWO
phases: (1) **design** — author a design doc via a Kimi K3 session (Fireworks,
high effort) and cross-engine review it via a Codex/Sol session (3-round cap),
and (2) **implementation** — turn the accepted design into code via a CLI coding
agent in an isolated worktree, gate it, and raise a PR. You are the supervisor:
you coordinate, you never write the design or the implementation yourself.

## Activation (how a T2 session starts)

A Tier-2 session is **launched with this skill preloaded** for ONE specific
issue — normally spawned by a Tier-1 session (per repo) at handoff into a
**persistent interactive tmux session**. Launch incantation: use the canonical
form from the `hermes-session-cli-launch` skill —
`tmux new-session -d -s t2-<task_id> -x 200 -y 50 'hermes chat -s
tier2-orchestration --tui'` then send the brief (do NOT use the stale bare
`hermes -s <skill> --cli` form; see that skill for the failure modes and any
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
comment trail. Do NOT silently fall back on your own initiative when the brief
is silent on it — if it doesn't say what to do when kanban is unavailable,
STOP and ask, same as any other unstated-in-brief ambiguity.

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
   prompt.** The verbatim convention text is in the Phase 2 prompt template
   (kept there as a copy-paste block — use that text, don't paraphrase). The
   T3 worker does not inherit Hermes memory or the user's global conventions, so
   the prompt must carry them.
5. **Boundary rule.** Coding sessions + code review → `claude_orchestrate` (review
   is a Claude Code `/pr-review-toolkit:review-pr` session; kimi-k3 fallback when
   claude auth is down). Test-fix → a `delegate_task` sub-agent (kimi-k3). State +
   control flow → kanban CLI + on-disk state. Do not blur these.
5. **One writer per issue.** Never two concurrent implementation sessions on one
   issue. The kanban claim enforces this atomically. Distinct tasks across
   DIFFERENT issues are fine.
6. **Continuous execution.** Do not pause between units for check-ins. Stop only
   for: BLOCKED you cannot resolve, genuine ambiguity, all-done, or the human
   merge gate.
7. **Claude auth is a soft dependency — never a hard blocker.** Before spawning ANY
   Claude Code session (coding, design-author, design-revise, review), probe auth
   via the plugin with the same `model_provider` the session will use:
   `claude_orchestrate start` with `model_provider=fireworks` (the current routing),
   a trivial prompt ("reply PONG"), and a short timeout. If it errors/exits → the
   Fireworks path is down, fall back to `executor=codex` for that step (the kanban
   claim is independent of the executor). Do NOT probe with a raw `claude -p` —
   that checks the TF/Anthropic endpoint, not the Fireworks path, and reports
   the wrong model group (a false `claude-teams-group` alarm). For design:
   cross-engine split weakens (author+reviewer both codex-family) — note it in a
   kanban comment, proceed. Escalate only if BOTH engines down.
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
10. **Design = judgment → use CLI coding-agent sessions, not inline reasoning.**
    Orchestrate a Kimi K3 author session (`model_provider=fireworks`, `effort=high`)
    and a Codex/Sol review session (cross-engine) via `claude_orchestrate`. Read
    the VERDICT file, never the design-doc body, into your own context. Author and
    reviewer MUST be different model families — never let the author review its own
    doc.
11. **Reflexion one-shot on gate failure.** When a gate check fails (impl/test/
    review), don't kill the session and start fresh — steer the existing session
    with a reflection prompt: "PRIOR ATTEMPT FAILED. The failing signal was: <the
    gate output>. Reflect in one sentence on WHY it failed and what to change,
    then produce a corrected attempt. Do not repeat the same approach." Then
    re-gate ONCE. If still failing, escalate. Bounded — not a loop. (Borrowed from
    sentinel's self_heal.py — the Reflexion one-shot pattern.)
12. **Design-review rounds capped at 3.** After the 3rd review, if still not
    approved → STOP and ESCALATE with the latest doc + outstanding blocking issues.
    Do NOT start a 4th round. A blocking issue that reflects genuine ambiguity in
    the TASK itself (not the doc) → ESCALATE for clarification, don't spin another
    round.
13. **Deny-guard protects every spawned session.** `~/.hermes/scripts/deny-guard.sh`
    is wired into every `claude_orchestrate start` as a PreToolUse hook. It blocks
    destructive commands (rm -rf, git reset --hard, etc.) in T3 sessions. Never
    disable or bypass it.

## Inputs

- A kanban `task_id` (unit of work + orchestration namespace), created by Tier-1.
- The **raw task body** + a **`needs-design` flag** from the Tier-1 handoff brief.
  If T1 instead handed an already-accepted design doc (attached to the kanban
  task), skip the design phase and implement against it. If the task is marked
  `needs-design: false` (skip-to-build), also skip the design phase.
- Target repo `workdir` and `base_branch`.
- A scratch dir for design-author/review sessions (NOT the target repo — design
  touches no repo; no worktree).

## Procedure

### Phase 1 — Setup + resume check
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
6. **Read the task body + the `needs-design` flag** from the handoff brief
   (`hermes kanban show <task_id> --json`). Determine the design path:
   - If a design doc is ALREADY ATTACHED to the kanban task (handed in from
     outside, or produced by a prior run of this T2) → skip the design phase
     (Phase 1b); note the attachment path and proceed to Phase 2.
   - If `needs-design: false` (skip-to-build) → skip Phase 1b; proceed to Phase 2.
   - If `needs-design: true` AND no attached design doc → run Phase 1b now.
7. Write the raw task to a FILE **outside the codebase** (task artifact dir
   `~/.hermes/tasks/<task_id>/` or a tmp path) for the design-author session to
   read. Never paste long task text into dispatch prompts; point the agent at the
   out-of-repo file path. All design docs / verdicts / briefs stay OUTSIDE the
   worktree/repo — an internal brief file would pollute the diff the gate and
   `check_diff` inspect.

### Phase 1b — Design author + design review (only when needs-design AND no
attached doc)
T2 OWNS this loop. Design touches no repo — author and review sessions run in a
SCRATCH DIR (NOT the target repo, NO worktree). The author session reads the
target repo to ground the design; it does not write to it.

**1b.1 Design authoring** (Kimi K3 via Fireworks, high effort):
1. Probe claude auth via the plugin (NOT a raw `claude -p` — that checks the
   TF/Anthropic endpoint, not the Fireworks path): `claude_orchestrate start`
   with `model_provider=fireworks`, a trivial prompt ("reply PONG"), and a short
   timeout. If it errors or the session exits → the Fireworks path is down; fall
   back to `executor=codex` for the author step (note the weakened cross-engine
   split in a kanban comment). Escalate only if BOTH engines unavailable.
2. Write the raw task to a file (`<task-file>`, out-of-repo). Choose an
   `<out-path>` for the design doc OUTSIDE any repo (task artifact dir or tmp).
3. `claude_orchestrate start` in the scratch dir (per Inputs; no `worktree`),
   `executor=claude`, `model_provider=fireworks` (Kimi K3 via
   Fireworks — the design author), `effort=high`, `kanban_task_id=<kanban task>`
   (+ `kanban_board=<slug>` when the board is set) so the plugin auto-heartbeats
   the claim during the long wait (principle #2). Do NOT pass `model` (K3 is set
   via env, not `--model`). `task_id` e.g. `t2-<TASK_ID>-design`.
   Prompt (verbatim shape): "Read `<task-file>` (and read the target repo at
   `<repo-path>` as needed) and write a design doc to `<out-path>`: problem
   statement; chosen approach (pick ONE, justify vs alternatives);
   file/component-level plan; interfaces/contracts; build sequence; risks. **Also
   include:** a failure-mode analysis (for each critical flow: partial/gray/
   asymmetric failures, dependency latency spikes, what happens when a dependency
   is slow but not down) and a rollback strategy (reversible migrations, data loss
   on rollback, kill switches, forward/backward compat). Then set status complete
   and write DONE to your outcome file."
4. `claude_orchestrate wait` for the session; on `done`/`DONE` the doc exists at
   `<out-path>`. Do NOT read the doc content into your context — you only need
   its path for the reviewer. The wait may be long (a high-effort design turn
   routinely exceeds the TTL) — with `kanban_task_id` passed at `start`, the
   plugin auto-heartbeats the claim from inside `wait` (principle #2).

**1b.2 Design review** (Codex/Sol, cross-engine):
1. `claude_orchestrate start` in the scratch dir (per Inputs), `executor=codex`,
   `model=openai-group/gpt-5.6-sol` (Sol — the design reviewer),
   `kanban_task_id=<kanban task>` (+ `kanban_board=<slug>` when set — principle
   #2 auto-heartbeat). `task_id` e.g.
   `t2-<TASK_ID>-dreview`. Choose a `<verdict-path>` OUTSIDE any repo. Prompt
   (verbatim shape): "Read the design doc at `<doc-path>` and the task at
   `<task-file>`. Review the doc against the task + constraints. Write your
   verdict to `<verdict-path>` in EXACTLY this structure, then set status
   complete + write DONE to your outcome file:
   ```
   VERDICT
   approved: yes|no
   confidence: <0-100>
   blocking_issues:
   - <issue, or "none">
   nonblocking_suggestions:
   - <suggestion, or "none">
   ```"
2. `claude_orchestrate wait`; read the VERDICT file (NOT the doc). **Same
   auto-heartbeat coverage as 1b.1** — `kanban_task_id` was passed at `start`,
   so the plugin keeps the claim alive inside the wait (principle #2). Branch:
   - `approved: yes` → design accepted. Proceed to 1b.3 (attach + implement).
   - `approved: no` → write the blocking issues to a file (`<issues-file>`,
     out-of-repo). Start a NEW Claude Code author session
     (`model_provider=fireworks`, `effort=high`)
     in the scratch dir (per Inputs), pointed at the current doc + `<issues-file>` to REVISE:
     "Read the design doc at `<doc-path>` and the blocking issues at
     `<issues-file>`. Revise the doc in place to address every blocking issue.
     Then set status complete + write DONE to your outcome file." Then run a
     FRESH Codex review (1b.2 again, new session). **HARD LIMIT: at most 3
     review rounds total.** If still not approved after the 3rd review → STOP
     and ESCALATE to a human with the latest doc + outstanding blocking issues.
     Do NOT start a 4th round.
   - A blocking issue that reflects genuine ambiguity in the TASK itself (not the
     doc) → ESCALATE to a human for clarification; do not spin another round.

**1b.3 Attach accepted design + proceed:**
1. `hermes kanban attach <task_id> <doc-path>` — ATTACH the accepted design doc
   to the kanban task. MANDATORY. Verify with `hermes kanban attachments
   <task_id>`.
2. Post the verdict as a kanban comment: `hermes kanban comment <task_id>
   "design approved: confidence <N>, blocking none | nonblocking: <summary>"`.
3. Proceed to Phase 2. The implementation loop reads the design doc from the
   attachment (path from `hermes kanban attachments <task_id>`).

### Phase 2 — Implementation loop
The design doc now comes from Phase 1b (T2-authored + reviewed) OR was handed in
attached to the kanban task. Either way, read its path from
`hermes kanban attachments <task_id>` and point implementation sessions at the
file — never paste the doc into a prompt.

The **ledger is a versioned kanban attachment** (key `ledger`, JSON:
`{units:[{id,desc,status:pending|complete,commit,review}]}`), written via
`hermes kanban attach <task_id> <ledger-file>` after each unit completes. On ANY
(re)start, read it FIRST and treat `status:complete` units as done — it's the
durable recovery map that prevents re-dispatching completed work.

**Parallel units via kanban link.** If the design doc identifies independent
units (no code dependencies between them), create child kanban tasks for each
unit and link them: `hermes kanban link <parent-task_id> <child-task_id>`. This
lets you track each unit's state independently and enables parallel execution
where safe. Sequential units with dependencies stay as entries in the ledger.

**Design doc stays on the PARENT — children reference it, do NOT re-attach it.**
The design doc is a single source of truth on the top-level (parent) task. Do NOT
copy/attach it onto each child (duplication → drift). A child task carries only its
own unit-specific brief (its slice of the work) in the child's body or a small
brief attachment. The child-unit coding session's prompt points at BOTH: its
unit brief AND the parent's design attachment (read the parent doc's path from
`hermes kanban attachments <parent-task_id>`). So a child session prompt is:
"Read <unit-brief> and the design doc at <parent-design-path>, implement this unit."

Repeat until all units done or a stop condition fires:
1. Read the ledger attachment → first unit with `status:pending`. If none
   (all complete), go to Phase 3. (No ledger yet → derive units from the design
   doc, write the initial ledger, attach it, start at unit 1.)
2. `claude_orchestrate start`: `task_id`, `workdir`, `worktree=<name>`,
   `executor=claude`, `model_provider=fireworks` (Kimi K3), `effort=medium`,
   `kanban_task_id=<kanban task>` (+ `kanban_board=<slug>` when set — the plugin
   auto-heartbeats the claim inside the long `wait`, principle #2),
   `prompt` = "Read <brief-file> and the
   design doc, implement this unit. Code comments/docstrings: terse, present-tense,
   necessary only — no restating what the code shows, no issue/PR references, no
   narrating past/fixed behavior. Docstrings: only what's necessary — what it does
   + non-obvious caller contract; no design-rationale or 'why' narration the code
   already shows. Prefer no comment over a noisy one." (points at files, not pasted text).
   **Prepend auto-promoted error rules.** Before composing the prompt, run
   `python3 ~/.hermes/scripts/error-journal.py inject claude` (or `inject codex`
   when falling back) and prepend the returned markdown block to the prompt.
   It lists recurring T3 failure patterns auto-promoted from the error journal
   (threshold: `TIER_ERROR_PROMOTE_THRESHOLD`, default 3). Empty output = no
   active rules; skip silently. This is cheap insurance against re-tripping
   known failure modes.
   - `task_id` for the plugin is the tmux session name (e.g. `t2-<TASK_ID>-u3`).
     Keep it lowercase. The kanban task_id is separate and used for claim/comment/
     heartbeat/complete calls.
   - The kanban claim is independent of the coding executor (principle #7) —
     fall back to `executor=codex` without releasing the claim.
   - **Graphify seed (only when the main repo has a `.graphify/` graph):** the
     worktree starts with NO graph (it's not committed, so `git worktree add`
     doesn't propagate it). Right after `start` returns and the worktree exists,
     seed it so the coding agent can run `graphify minimal-context` /
     `affected-flows` from its first turn:
     ```bash
     MAIN_REPO=<the repo workdir>  # NOT the worktree path
     WT=<the new worktree path>    # e.g. $MAIN_REPO/.worktrees/<name> or the path start reports
     if [ -d "$MAIN_REPO/.graphify" ] && [ ! -d "$WT/.graphify" ]; then
       cp -R "$MAIN_REPO/.graphify" "$WT/.graphify"
       rm -f "$WT/.graphify/branch.json" "$WT/.graphify/worktree.json" "$WT/.graphify/needs_update"
       (cd "$WT" && graphify update . --no-description --no-label --no-cluster >/dev/null 2>&1)
     fi
     ```
     This is a cheap CP-copy + incremental reconcile against the branch's code —
     NOT a cold build (26K-node content repo: seconds, no API cost). Skip it
     silently if the main repo has no graph (app does, content does; a fresh repo
     may not). Do not block the unit on the update finishing — it runs in the
     worktree and the post-commit hook keeps it current from here.
3. `claude_orchestrate wait` for the session — with `kanban_task_id` passed at
   `start`, the plugin auto-heartbeats the claim from inside `wait` (principle
   #2); no manual heartbeat-between-waits loop needed.
4. Branch on the returned `state` + `outcome`:
   - `state=done` or `exited` → read `outcome`:
     - `DONE` → Phase 3 gate.
     - `DONE_WITH_CONCERNS` → read `outcome_detail`; if the concern is a real
       correctness/scope gap, re-`start` with added context; else note it and
       proceed to gate.
     - `NEEDS_CONTEXT` → provide what `outcome_detail` asks, re-`start` (same executor).
     - `BLOCKED` → assess `outcome_detail`: context gap → add context, retry;
       plan/design wrong → ESCALATE; unit too large → split, update the plan.
     - `outcome=null` on a `done` session → treat as DONE-unverified; proceed to
       gate (the gate is the real check anyway). On an `exited` session with null
       outcome → the agent likely crashed: go to the fallback below.
   - `state=needs_input` → the agent is asking something; read the pane, `steer`
     the answer, `wait` again.
   - `state=stalled` → check `doom_loop` in the status/wait output FIRST: if
     `doom_loop: true`, the session is in a tool-call loop (same tool + same
     normalized args 3+ times) — do NOT steer or wait again, ESCALATE
     immediately (report the loop fingerprint and stop the session). If
     `doom_loop` is false, steer once ("report current status"); if it's a
     **claude** session wedged in a think-loop, `interrupt` (Esc) instead
     of/after the steer; `wait` again; if still `stalled`, `diagnose`
     (capture pane+log), `stop`, treat as a failed run → fallback below.
     (Stall = no activity indicator in the pane AND no status change — a
     session showing a thinking/working spinner is NOT stalled.)
   - **Wedged-child self-recovery (observed 3× in one workstream):** if your
     `claude_orchestrate wait` has been open >10 min, do NOT keep waiting
     blindly — check the child session's on-disk state directly:
     `~/.hermes/tasks/<child-task>/result.md` and `outcome.md` presence. If
     the child wrote `DONE`/completed minutes ago while your `wait` is still
     open, the call is wedged, not working: interrupt the wait (C-c), read the
     child's result/verdict files directly, and proceed from them. Never let a
     completed child hold a supervisor hostage in a wait call.
   - **Fallback on failed/crashed/stalled claude run**: retry the SAME unit ONCE
     with `executor=codex`. The claim stays held (independent of the executor —
     principle #7). If codex also fails → ESCALATE.
5. Track an iteration counter in the ledger; exceed a sane max (e.g. 10) → ESCALATE.
6. After each unit completes: update the ledger file and `hermes kanban attach
   <task_id> <ledger-file>`. Then `hermes kanban heartbeat <task_id> --note
   "unit N/M complete"` to keep the claim alive.

### Phase 3 — Exit gate
Run all three checks; the task passes only if impl+tests+review all pass.
**Tests and review run in PARALLEL** (per the redesign) — kick off both
simultaneously since they inspect the same diff independently. However, if tests
fail fast, you may cancel/ignore the review round rather than acting on review
findings for code that's about to change. The fail-fast logic still applies: if
tests surface a failure, address that first and re-run both once the code is
stable. This avoids wasting a review round on code about to change.

**3.1 impl-complete.** `claude_orchestrate gate task_id=<..>` → reads `impl`
verdict. If `impl:fail` (no `complete` / empty diff) → steer the session with a
reflection prompt once (see below), re-gate once; if still failing, **record
the failure to the error journal** (see "Error journal wiring" below) with
`error_type=impl_incomplete` and `signal_trace` = the gate's fail reason, then
back to Phase 2.

**3.2 tests + narrow-fix** (this skill fills the gate `tests` slot):
1. **Baseline first.** Before running the agent's tests, capture the pre-existing
   failures: run the suite on the base commit (`git stash` or `git worktree` the
   base) and record which tests fail. The agent's tests should block only on NEW
   failures — a repo with pre-existing red tests shouldn't block a fix. If the
   agent's changes introduce a new failure, that's a gate failure. If they fail
   only on tests that were already red, that's not a gate failure (note it).
2. Run the project's test suite YOURSELF via terminal in `<rundir>`. Read the real
   exit code + output. Pass → review (3.3).
   - **First run `hermes verify <rundir> --phase test --save`** — it auto-detects
     the project's build/test recipe (and persists it to `.hermes/environment.json`
     for reuse). If verify detects the recipe correctly, use it. Fall back to the
     repo's documented commands (its `.hermes.md` / package.json scripts) only if
     verify's detection is wrong for this repo.
   - **Run EVERY test suite the diff touches, not just the primary component's.**
     A monorepo often has multiple independent suites (e.g. a component's own
     `tests/` AND a repo-level `.claude/scripts/tests/`), each a separate CI job.
     `git diff --name-only base..HEAD` → for every distinct suite whose files
     changed, run THAT suite. A change under `.claude/scripts/` MUST run
     `.claude/scripts/tests`; a change under `components/X` MUST run X's tests.
     Running only the primary suite is how a stale test in a sibling suite slips
     to CI (observed: a turn-cap removal left a stale guarding test in the
     agent-scripts suite that the component-only gate never ran).
   - **When you remove/alter a behavior, grep for and update the test(s) that
     guarded it** in the SAME change — a passing primary suite does not prove a
     sibling suite's now-stale assertion won't fail.
   - **If the repo has CI, verify it green before declaring the gate passed:**
     after pushing, `gh pr checks <pr>` must show all checks passing; a red CI
     check is a gate failure even if your local run was green.
   - **CI runs checks your local suite doesn't cover (Semgrep, other static/security
     scanners) — this shows up only AFTER the PR is opened, not during 3.2/3.3.**
     Once the PR is up, re-poll `gh pr checks <pr>` (Phase 4) even after gate 3.2/3.3
     passed; a scanner failure reopens the gate. Get the finding detail via
     `gh api repos/<org>/<repo>/commits/<sha>/check-runs` then
     `gh api repos/<org>/<repo>/check-runs/<id>/annotations` (the `gh pr checks`
     summary line has no file/line detail). Dispatch a normal fix session (same
     worktree/branch) with the exact rule id + file + line from the annotation and
     the concrete hardening asked for (e.g. a Semgrep
     `prototype-pollution-loop` hit on dynamic property/index access wants
     `Object.prototype.hasOwnProperty.call` + a `__proto__`/`prototype`/`constructor`
     denylist, not a suppression comment) — re-run tests, push, re-poll checks.
3. On failure, capture `BEFORE_SHA = git rev-parse HEAD` in the worktree, then
   `delegate_task` a test-fixer (kimi-k3). Its goal:
   run the suite and fix ONLY small mechanical failures (missing dependency,
   trivial config/env). Constraint in its context, verbatim: "Do NOT modify
   implementation source. You may edit ONLY dependency/config/env files
   (lockfiles, requirements.txt/pyproject/package.json, .env, CI/config). If a
   failure needs a production-code change, STOP and report it — do not fix it."
4. **ENFORCE the allowlist deterministically via the `check_diff` action (do NOT
   eyeball the diff yourself).** After the fixer returns, call
   `claude_orchestrate check_diff` with `task_id`, `base_sha=<BEFORE_SHA>`,
   `allowlist=<dep/config/env globs>` (e.g. `["*.lock","requirements*.txt",
   "pyproject.toml","package*.json",".env*","*.cfg","*.ini","*.toml",".github/**",
   "ci/**"]`), and `reset_on_violation=true`. If it returns `clean:false`, the
   fixer touched implementation source — the action has already hard-reset the
   worktree to `BEFORE_SHA` (undoing the overreach); treat tests as `fail` this
   round. This is the fence, enforced in code — never trust the fixer's word or
   your own read of the diff.
5. Re-run the suite YOURSELF. Max 3 fix loops. Still failing → **record
   `error_type=test_failure`** with `signal_trace` = the failing test names +
   first error line, then ESCALATE.

**3.3 code review** (this skill fills the gate `review` slot) — primary path via
the `pr-review-toolkit` `/pr-review-toolkit:review-pr` command in a **Claude Code
session** (not the implementer session):

0. **Scope the review to THIS PR's delta, always.** Compute the review base with
   `git merge-base origin/<parent-branch> HEAD` so the range covers only this
   branch's own commits. The review prompt must name
   the exact commit range (`origin/<base>..HEAD` of the PR's branch) and instruct
   the reviewer to read only that diff — never the cumulative stack diff, never
   the whole component. On a stacked branch, the base is the previous stack
   branch, not the trunk. Reviewing beyond the delta duplicates earlier rounds
   and scales cost with stack size instead of change size.
1. `claude_orchestrate start` a Claude Code session (`executor=claude`,
   `model_provider=fireworks` — Kimi K3; pass `kanban_task_id`/`kanban_board`
   as everywhere else, principle #2) in the
   task's worktree (`workdir=<rundir>`). Prompt it to run the pr-review-toolkit
   the review over this unit's changes and write a structured verdict to an
   out-of-repo file. The review should specifically probe: (a) resource-lifecycle
   bugs (a resource opened but not closed on every path, an external call made
   without a timeout, a subprocess not reaped); (b) missing retry/backoff on
   transient external failures (network, S3, the gateway); (c) false-success
   swallowed errors (a catch that logs but continues, a return-code ignored);
   (d) check-then-act without atomicity (a `if not exists: create` that races,
   a read-modify-write without a lock). Then write your verdict to <verdict-path>
   in the `pr-review-toolkit` verdict format (that skill's "The verdict format"
   section is canonical). Set status complete + write DONE to
   your outcome file." Launch with `effort=medium` (high effort is the main claude
   hang trigger; a structured-verdict review doesn't need it). Do NOT pass `model`
   in the fireworks path (K3 is set via env).
2. `wait` for the session; read the verdict file. (Distinct review session from
   the implementer — per the `pr-review-toolkit` Pitfalls entry, never reuse the
   implementer to review its own work.)
3. On `needs_fixes`/`spec:fail`: dispatch ONE fix via a coding session
   (`claude_orchestrate start`, same worktree) with ALL findings + the
   structured feedback appended to its brief; then re-run the review (primary or
   fallback, whichever this run used). **HARD
   LIMIT: at most 3 review→fix rounds** (count them). If still not clean after
   the 3rd review → **record `error_type=review_needs_fixes`** with
   `signal_trace` = the outstanding CRITICAL/HIGH findings summary, then STOP
   and ESCALATE to a human with the outstanding findings; do not
   start a 4th round. Do not open one fix session per finding.
4. A finding that conflicts with the plan text → ESCALATE (human decides which governs).
5. **Fallback when claude auth is down** (preflight probe fails): use the
   `requesting-code-review` delegate_task fallback exactly as the
   `pr-review-toolkit` skill's "Fallback (Claude Code auth down)" section
   specifies; fold findings into the same structured verdict, treat
   CRITICAL/HIGH the same, and note in the gate comment that review ran via the
   kimi-k3 fallback, not pr-review-toolkit.

**3.2b live-model check for prompt/labeling changes (mandatory when applicable).**
If the unit's core change is a MODEL PROMPT or a model-assigned label/classification
(e.g. a judge/verifier prompt instructed to tag its own output with a new field),
fixture-fed unit tests are NOT sufficient evidence, no matter how green — they only
prove the gate logic handles pre-labeled data correctly, never that the model
actually produces sensible labels under the new prompt. Run the changed step LIVE
against a real (or realistic replayed) input at least once, with real spend
authorized, and read its actual output before calling the gate passed:
1. Seed a real run dir with genuine upstream inputs (a prior real run's artifacts,
   not synthetic fixtures).
2. Invoke ONLY the changed step with the real model executor (not the fake/mocked
   executor the unit suite uses).
3. Read the produced artifact directly and judge whether the labels/output are
   SENSIBLE against the task's intent — not just schema-valid.
4. Feed that real output through the gate/aggregation logic to confirm the
   downstream behavior is correct on real data, not just synthetic probes.
This is a distinct, additional check from 3.2/3.3 — do not treat "unit tests
green" as proof a prompt actually works. (Observed: an abstain-gate fix's tests
all passed against hand-built fixtures; only a live verifier run against a real
candidate's drafts confirmed the model's `kind` labels actually landed on the
correct side of the candidate-facing/internal split.)

**3.4 adversarial QA** (optional, HIGH-RISK changes only — NOT YET BUILT, skip
unless the change touches auth/security/migration paths or is a large diff).

Record the composite gate verdict: `hermes kanban comment <task_id> "<verdict
summary>"` (impl pass/fail, tests pass/fail, review approved/needs_fixes, rounds
used, any fallback notes).

### Phase 4 — Raise PR + human approval
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
4. Link the PR back to the kanban task: `hermes kanban comment <task_id> "PR: <url>"`
   for the audit trail. Then **move the task to the `review` status** (PR is up,
   awaiting the human's code review):
   `hermes kanban request-review <task_id> [--board <repo>] --summary
   "PR #N up for review" --force`. **STOP.** Autonomy ends here — a human decision is
   required for EVERY merge (hard rule).
   - Use `review`, NOT `blocked`, for the normal "PR is ready, please review + merge"
     case — the dashboard shows it in the Review column. Reserve `blocked`
     (`hermes kanban block --kind needs_input <task_id> "<what you need>"`) for when
     you genuinely need the human's INPUT/decision to proceed (an ambiguity, a
     credential, a design call) — that's a different signal than "ready for review."
   - **Notify the human that a PR is ready for review** (the kanban notifier fires
     on `completed`/`blocked` but NOT `review`, so send a direct ping):
     ```
     hermes send -t telegram "PR ready for review: <task title> — <PR url>"
     ```
     Do this once per PR, right after moving to `review`. Also subscribe the task so
     `blocked`/`completed` events auto-ping Telegram:
     ```
     hermes kanban notify-subscribe <task_id> --platform telegram
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
4. **Run one fresh independent code-review round** (Codex/Sol, `claude_orchestrate`)
   against the reworked diff (`origin/<base>...HEAD`) before treating it as ready.
   A smaller diff is not itself proof of correctness — get an actual approved
   verdict on the NEW diff, same as any other Phase 3.3 review.
5. **Re-verify with real test execution against the new diff**, not the prior
   PR revision's green CI — the mechanism changed, so its own test run must be
   fresh (baseline + branch, per 3.2), even if the old PR had already gone green
   once.

### Phase 5 — Cleanup
1. Mark the task done. The task is in `review` (Phase 4 moved it there for the
   merge gate), and `hermes kanban complete` accepts review-state tasks. Use:
   `hermes kanban complete <task_id> --result "merged via PR #N" --summary "<2-3 sentence handoff: what changed, key decisions>" --metadata '{"changed_files": [...], "pr": <N>}'`.
   The `--summary` and `--metadata` feed `hermes kanban context` so downstream
   tasks and the T1 dispatcher can see what was done without opening the PR.
2. `hermes kanban reclaim <task_id>` — release the claim (do this BEFORE
   self-terminating so the claim doesn't linger until TTL expiry).
3. Prune the task artifact dir (avoid unbounded growth). Only remove worktrees
   this run created.

**Self-terminate.** As the FINAL step, once the issue reaches a terminal state
(merged, discarded/rejected, or escalated-and-handed-off — i.e. nothing more for
this supervisor to do), kill your own tmux session so it stops holding a `hermes`
process in memory: `tmux kill-session -t t2-<task_id>`. A per-issue T2 must not
linger after its issue is done. (Only the happy/decided path self-reaps; a T2 that
errors out BEFORE Phase 5 will still linger — an external reaper is possible future
scope.)

## Escalate to a human when
- BLOCKED because the plan/design is fundamentally wrong.
- Design review not approved after the 3rd round (send latest doc + outstanding
  blocking issues; do NOT start a 4th round).
- A design blocking issue reflects genuine ambiguity in the TASK itself (not the
  doc) → human clarification needed before another design round.
- Both Claude and Codex engines unavailable for the design-author step.
- Implementation loop or test-fix loop hits max iterations (stuck).
- A review finding conflicts with plan text (human decides which governs).
- The gate cannot pass after retries.
- Always, for the merge decision.

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
or `kimi-k3` for a delegate_task fixer). `error_type` is a short snake_case
slug (e.g. `impl_incomplete`, `test_failure`, `review_needs_fixes`,
`auth_expired`, `context_overflow`, `stuck_loop`). Keep `signal_trace` specific
— not "tests failed" but "test_foo.py::test_bar AssertionError: expected 3
got 4".

**Inject on T3 spawn.** Before composing every Phase-2 coding-session prompt
(and every Phase-3.3 review-fix prompt), run:
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
- **A fix that lands as commits on OTHER PRs' branches (not its own) loses
  traceability unless you deliberately restore it.** This happens when issue X's
  fix is a genuine blocking prerequisite for smoke-testing issues Y and Z (e.g.
  a dangling-path bug both Y's and Z's branches share), so the cleanest
  mechanical fix is applying it directly on Y's and Z's branches rather than
  extracting a third branch and reverting it back out of Y/Z. Left as plain
  commits, issue X now has no PR that visibly resolves it and a reviewer of
  Y or Z has no signal that X's fix rides along in their diff — "if it pushed
  to 31 and 32 no one will know we fixed it." Fix: amend the commit(s) on each
  affected branch to carry a `Fixes #X` trailer, and reopen issue X (it
  auto-closes when either PR merges, and GitHub's PR view shows the trailer
  inline so a reviewer sees X was addressed in THIS diff). Don't silently fold
  a blocking fix into a dependent branch without this — always ask whether the
  issue should stay separately visible before choosing the folded-in mechanical
  fix over a standalone PR.
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
- stop→release→re-claim on the codex fallback → DON'T; the claim is independent of
  the executor, just switch `executor=codex`.
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
  `effort=medium` completes cleanly.** Observed twice in one Phase 1b.2 revise
  loop. If a design session dies with no outcome at `effort=high`, retry the SAME
  revision prompt once at `effort=medium` before treating it as a stalled/crashed
  session requiring the codex fallback (principle #7) — cheaper first try than
  switching engines.
- **Brief-driven (no-kanban) T2 flows sharing ONE repo checkout across concurrent
  issues → branch collisions.** When a T2 works directly against a repo path
  (via terminal `git checkout -b`/`commit`, not a `claude_orchestrate` worktree)
  and another T2 is simultaneously working a DIFFERENT issue in the SAME repo
  path, either side's `git checkout <other-branch>` silently switches the shared
  working tree out from under the other session — `git status` then shows the
  wrong branch's uncommitted files mixed in as if they were yours (observed:
  session A's `render-dossier.ts` WIP appeared in session B's `git status` after
  session A checked out its branch in the shared tree). Before every `git add`/
  `git commit`, re-check `git branch --show-current` matches what you expect and
  diff the staged files against exactly what YOU touched — never `git add -A`
  blind in a shared checkout. If the tree has been switched, `git stash` isn't
  safe either (competes with the other session); instead identify exactly which
  paths are yours (`git diff --name-only` against your own last known commit) and
  stage only those. Prefer an isolated `git worktree add` per issue any time two
  T2s might run against the same repo concurrently — this is what Phase 2's
  `worktree=<name>` already does for `claude_orchestrate` sessions; extend the
  same isolation to ad-hoc terminal-driven git work in a brief-driven flow, don't
  work directly in a shared primary checkout.
- **Verify against the committed branch, not the live working tree, once a
  shared checkout may have moved.** After push, run verification (build/test/
  ad-hoc content checks) via `git show <branch>:<path>` (or a worktree checked
  out to that branch) rather than reading files straight off disk — the shared
  tree can be pointed at a different branch by a concurrent session by the time
  you get to verification, and a check against the wrong branch's files reports
  false failures that look like your own change regressed.
