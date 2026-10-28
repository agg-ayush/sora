---
name: tier2-orchestration
description: Supervise one coding issue from raw task to approved PR.
version: 0.3.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Coding-Agent, Tier-2, Kanban]
    related_skills: [claude-code, codex, pr-review-toolkit, github-pr-workflow, pr-description-style, requesting-code-review, hermes-agent]
---

# Tier-2 Design + Implementation Supervisor

Drive ONE issue from a raw task to a human-approved GitHub PR merge. You own TWO
phases: (1) **design** — author a design doc via an Opus 5.5 session (seatbelt,
high effort) and cross-engine review it via a GLM-5.3 session (3-round cap),
and (2) **implementation** — turn the accepted design into code via a CLI coding
agent in an isolated worktree, gate it, and raise a PR. You are the supervisor:
you coordinate, you never write the design or the implementation yourself.

## Activation (how a T2 session starts)

A Tier-2 session is **launched with this skill preloaded** for ONE specific
issue — normally spawned by a Tier-1 session (per repo) at handoff into a
**persistent interactive tmux session**. Launch incantation: use the canonical
form from the `hermes-session-cli-launch` reference (under the
`hermes-administration` skill) —
`tmux new-session -d -s t2-<task_id> -x 200 -y 50 'hermes chat -s
tier2-orchestration -m glm53 --tui'` then send the brief (do NOT use the stale bare
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
   is a Claude Code `/pr-review-toolkit:review-pr` session; delegate_task fallback
   only with explicit approval — different model group). Test-fix → a
   `delegate_task` sub-agent (the configured
   delegation model — currently openai-group/gpt-6-sol). State +
   control flow → kanban CLI + on-disk state. Do not blur these.
5. **One writer per issue.** Never two concurrent implementation sessions on one
   issue. The kanban claim enforces this atomically. Distinct tasks across
   DIFFERENT issues are fine.
6. **Continuous execution.** Do not pause between units for check-ins. Stop only
   for: BLOCKED you cannot resolve, genuine ambiguity, all-done, or the human
   merge gate.
7. **Probe the prescribed route before spawning; a dead route means STOP, not a
   silent switch.** Before spawning a session, probe its prescribed route with a
   trivial prompt ("reply PONG") and a short timeout. Claude Code steps: probe
   via the plugin with the same `model_provider` the session will use
   (`seatbelt` for the design author and implementation, `fireworks` for the
   GLM-5.3 design/code reviews). Do
   NOT probe the Fireworks path with a raw `claude -p` — that checks the
   TF/Anthropic endpoint, not the Fireworks path, and reports the wrong model
   group (a false `claude-teams-group` alarm). Seatbelt steps probe with
   `model_provider=seatbelt` and the same `model` (`opus`/`sonnet`) the step
   will use. If the probe fails, do NOT
   fall back to another executor on your own — a switch changes the model group
   and billing route, and the design phase's cross-engine split depends on the
   groups being distinct. STOP and get explicit human approval before switching
   any step's engine/group. The kanban claim is independent of the executor — an
   approved switch needs no release/re-claim.
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
    Orchestrate an Opus 5.5 author session (`executor=claude`,
    `model_provider=seatbelt`, `model=opus`, `effort=high`)
    and a GLM-5.3 review session (`model_provider=fireworks`, cross-group) via
    `claude_orchestrate`. Read
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
`claude_orchestrate action=set_phase task_id=<task_id> phase=1b` — record that you're in design. Then:
T2 OWNS this loop. Design touches no repo — author and review sessions run in a
SCRATCH DIR (NOT the target repo, NO worktree). The author session reads the
target repo to ground the design; it does not write to it.

**1b.1 Design authoring** (Opus 5.5 via seatbelt, high effort):
1. Probe claude auth via the plugin (NOT a raw `claude -p` — that checks the
   TF/Anthropic endpoint, not the seatbelt path): `claude_orchestrate start`
   with `model_provider=seatbelt`, `model=opus`, a trivial prompt ("reply PONG"),
   and a short timeout. If it errors or the session exits → the seatbelt path is
   down (most commonly: rc token stale vs TFY_API_KEY, or 403 not-a-member).
   STOP for explicit human approval before switching the author step to another
   engine (cross-group — principle #7; a same-group author+reviewer split also
   defeats the cross-engine review).
2. Write the raw task to a file (`<task-file>`, out-of-repo). Choose an
   `<out-path>` for the design doc OUTSIDE any repo (task artifact dir or tmp).
3. `claude_orchestrate start` in the scratch dir (per Inputs; no `worktree`),
   `executor=claude`, `model_provider=seatbelt`, `model=opus` (Opus 5.5 via
   seatbelt — the design author), `effort=high`, `kanban_task_id=<kanban task>`
   (+ `kanban_board=<slug>` when the board is set) so the plugin auto-heartbeats
   the claim during the long wait (principle #2). `task_id` e.g.
   `t2-<TASK_ID>-design`. RETAIN this session's id — it stays alive through the
   review loop.
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

**1b.2 Design review** (GLM-5.3 via Fireworks, cross-group):
1. `claude_orchestrate start` in the scratch dir (per Inputs), `executor=claude`,
   `model_provider=fireworks` (GLM-5.3 — the design reviewer; do NOT pass
   `model`, the route pins GLM-5.3 via env),
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
     out-of-repo). **Steer the SAME design-author session** (retained from
     1b.1) with: "Read the design doc at `<doc-path>` and the blocking issues at
     `<issues-file>`. Revise the doc in place to address every blocking issue.
     Then set status complete + write DONE to your outcome file." Then run a
     FRESH GLM review (1b.2 again, new review session — the reviewer is always
     fresh; only the author is retained). If the author session died since
     1b.1, start a new author with the same route + prompt it with the current
     doc and issues. **HARD LIMIT: at most 3
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
`claude_orchestrate action=set_phase task_id=<task_id> phase=2` — record that you're implementing. Then:
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

Repeat until all units done or a stop condition fires. **One implementation
session per task, retained across units** — start it once (below), then steer
the SAME session into each subsequent unit ("Read <unit-N-brief> and the design
doc at <parent-design-path>, implement this unit. Commit when done.") instead
of spawning a fresh session per unit. Start a new session only if the retained
one died or hit a hard context wall.
1. Read the ledger attachment → first unit with `status:pending`. If none
   (all complete), go to Phase 3. (No ledger yet → derive units from the design
   doc, write the initial ledger, attach it, start at unit 1.)
2. `claude_orchestrate start`: `task_id`, `workdir`, `worktree=<name>`,
   `executor=claude`, `model_provider=seatbelt`, `model=sonnet` (Sonnet 5.5 via
   seatbelt — the implementation route; model comes from env, no `--model`
   flag), `kanban_task_id=<kanban task>` (+ `kanban_board=<slug>` when set
   — the plugin auto-heartbeats the claim inside the long `wait`, principle #2).
   `prompt` = "Read <brief-file> and the
   design doc, implement this unit. Code comments/docstrings: terse, present-tense,
   necessary only — no restating what the code shows, no issue/PR references, no
   narrating past/fixed behavior. Docstrings: only what's necessary — what it does
   + non-obvious caller contract; no design-rationale or 'why' narration the code
   already shows. Prefer no comment over a noisy one." (points at files, not pasted text).
   **Prepend auto-promoted error rules.** Before composing the prompt, run
   `python3 ~/.hermes/scripts/error-journal.py inject claude` and prepend the
   returned markdown block to the prompt.
   It lists recurring T3 failure patterns auto-promoted from the error journal
   (threshold: `TIER_ERROR_PROMOTE_THRESHOLD`, default 3). Empty output = no
   active rules; skip silently. This is cheap insurance against re-tripping
   known failure modes.
   - `task_id` for the plugin is the tmux session name (e.g. `t2-<TASK_ID>-impl`).
     Keep it lowercase. The kanban task_id is separate and used for claim/comment/
     heartbeat/complete calls.
   - The kanban claim is independent of the coding executor — if an engine
     switch is approved (principle #7), change the route only; never
     release/re-claim for it.
   - **Model route is prescribed, not chosen.** Launch exactly the route this
     step documents (here: seatbelt/Sonnet 5.5; other steps prescribe their
     own — seatbelt/Opus design author, Fireworks/GLM reviews). Never
     spontaneously pick a different model
     or silently switch model groups/billing routes — the same rule
     covers sessions you launch manually via tmux. There is no pre-approved
     cross-group substitution: if the prescribed route is unavailable, STOP
     and get explicit human approval before rerouting.
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
     `doom_loop` is false, steer once ("report current status"); if the
     session is wedged in a think-loop, `interrupt` (Esc — works for both
     claude and codex sessions) instead of/after the steer; `wait` again; if
     still `stalled`, `diagnose`
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
   - **Failed/crashed/stalled run**: retry the SAME unit ONCE on the same
     prescribed route. Still failing → STOP for explicit approval before
     switching engines (cross-group — principle #7); the claim stays held
     regardless.
5. Track an iteration counter in the ledger; exceed a sane max (e.g. 10) → ESCALATE.
6. After each unit completes: update the ledger file and `hermes kanban attach
   <task_id> <ledger-file>`. Then `hermes kanban heartbeat <task_id> --note
   "unit N/M complete"` to keep the claim alive.

### Phase 3 — Exit gate
`claude_orchestrate action=set_phase task_id=<task_id> phase=3` — required before the gate call below. The plugin refuses to gate in earlier phases. Then:
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
   failures: run the suite on the base commit in a detached worktree
   (`git worktree add --detach <path> <base-sha>` — never a `git stash`/`pop`
   cycle; the stash list is repo-global and a foreign stash silently corrupts
   the baseline) and record which tests fail. The agent's tests should block only on NEW
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
     summary line has no file/line detail). Dispatch a normal fix session
     (`executor=claude`, `model_provider=seatbelt`, `model=sonnet`, same worktree/branch) with the
     exact rule id + file + line from the annotation and
     the concrete hardening asked for (e.g. a Semgrep
     `prototype-pollution-loop` hit on dynamic property/index access wants
     `Object.prototype.hasOwnProperty.call` + a `__proto__`/`prototype`/`constructor`
     denylist, not a suppression comment) — re-run tests, push, re-poll checks.
3. On failure, capture `BEFORE_SHA = git rev-parse HEAD` in the worktree, then
   `delegate_task` a test-fixer (delegation model — currently gpt-6-sol). Its goal:
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
   `model_provider=fireworks` — the independent code review runs on GLM-5.3 via
   the Fireworks Anthropic-compatible endpoint, a distinct group from the
   seatbelt/Sonnet implementer; do NOT pass `model`, the route pins GLM-5.3 via
   env; pass
   `kanban_task_id`/`kanban_board` as everywhere else, principle #2) in the
   task's worktree (`workdir=<rundir>`). Prompt it to run the pr-review-toolkit
   the review over this unit's changes and write a structured verdict to a
   file under this review session's `artifact_dir`. The review should specifically probe: (a) resource-lifecycle
   bugs (a resource opened but not closed on every path, an external call made
   without a timeout, a subprocess not reaped); (b) missing retry/backoff on
   transient external failures (network, S3, the gateway); (c) false-success
   swallowed errors (a catch that logs but continues, a return-code ignored);
   (d) check-then-act without atomicity (a `if not exists: create` that races,
   a read-modify-write without a lock). Then write your verdict to <verdict-path>
   in the `pr-review-toolkit` verdict format (that skill's "The verdict format"
   section is canonical). Set status complete + write DONE to
   your outcome file." Launch with `effort=medium` (high effort is the main claude
   hang trigger; a structured-verdict review doesn't need it).
   **Fireworks auth is explicit and fails closed:** the plugin refuses to launch
   this route without `FIREWORKS_API_KEY` in the environment. If `start` returns
   that error, the step FAILS CLOSED — stop and escalate. Do NOT substitute
   another model group (principle #7 — no cross-group fallback).
2. `wait` for the session; read the verdict file. (Distinct review session from
   the implementer — per the `pr-review-toolkit` Pitfalls entry, never reuse the
   implementer to review its own work.)
3. On `needs_fixes`/`spec:fail`: dispatch ONE fix via a coding session
   (`claude_orchestrate start`, `executor=claude`, `model_provider=seatbelt`, `model=sonnet` — the
   prescribed coding route, same as Phase 2; same worktree) with ALL findings + the
   structured feedback appended to its brief; then re-run the review (primary or
   fallback, whichever this run used). **HARD
   LIMIT: at most 3 review→fix rounds** (count them). If still not clean after
   the 3rd review → **record `error_type=review_needs_fixes`** with
   `signal_trace` = the outstanding CRITICAL/HIGH findings summary, then STOP
   and ESCALATE to a human with the outstanding findings; do not
   start a 4th round. Do not open one fix session per finding.
4. A finding that conflicts with the plan text → ESCALATE (human decides which governs).
5. **When the review route is down** (preflight probe fails, or the TF-auth
   fail-closed check above fires): STOP for
   explicit human approval first — the fallback runs on the delegation model,
   a different group/billing route. If approved, use the
   `requesting-code-review` delegate_task fallback exactly as the
   `pr-review-toolkit` skill's "Fallback (Claude Code auth down)" section
   specifies; fold findings into the same structured verdict, treat
   CRITICAL/HIGH the same, and note in the gate comment that review ran via the
   delegate_task fallback, not pr-review-toolkit.

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
4. **Run one fresh independent code-review round** (GLM-5.3 via Fireworks, `claude_orchestrate`)
   against the reworked diff (`origin/<base>...HEAD`) before treating it as ready.
   A smaller diff is not itself proof of correctness — get an actual approved
   verdict on the NEW diff, same as any other Phase 3.3 review.
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
- Design review not approved after the 3rd round (design non-convergence — send
  latest doc + outstanding blocking issues; do NOT start a 4th round).
- A design blocking issue reflects genuine ambiguity in the TASK itself (not the
  doc) → human clarification needed before another design round.
- Missing access you cannot resolve yourself — a credential, permission, or
  environment gap that blocks implementation or the gate.
- A step's prescribed route is unavailable — engine/model-group switches need
  explicit human approval (principle #7); escalate if none is granted.
- Implementation loop or test-fix loop hits max iterations (test failures that
  stay red after the bounded fix loops in Phase 3.2).
- A review finding conflicts with plan text (human decides which governs).
- The gate cannot pass after retries.
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
- **Implementation sessions tend to bundle adjacent-but-unassigned functionality into the diff — audit the diff against the task's stated scope before Phase 4, don't just check the gate.** Observed: a task to build a "JSONL→markdown transcript adapter" also implemented an unrequested Google-Drive fetch/unpack/workflow-wiring step, roughly tripling the PR's size and duplicating logic that may already exist elsewhere in the pipeline (the user caught it only from the PR size: "why is this which is basically a transcription converter that big?"). Before opening/updating the PR, diff the actual changes against the task description — if the diff does something the task never asked for, split it into a separate task/PR (or drop it) rather than folding it in as "while I was there." This matters most when the user has pre-delegated merge trust (e.g. "assume I'm okay with these as long as comments aren't too verbose") — the PR won't get a manual scope read from them, so the scope check has to happen here, before the PR goes up.
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
  `effort=medium` completes cleanly.** Observed twice in one Phase 1b.2 revise
  loop. If a design session dies with no outcome at `effort=high`, retry the SAME
  revision prompt once at `effort=medium` before treating it as a stalled/crashed
  session — an engine switch is approval-gated (principle #7), so the same-route
  retry is the cheaper first try.
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
- **The Fireworks/K3 path pre-seeds onboarding but NOT per-directory workspace
  trust — a session launched in a fresh worktree (or scratch dir) hangs on the
  first-run \"Is this a project you trust?\" TUI menu and exits with
  `outcome=null`, which looks identical to a silent crash.** Text `steer` cannot
  navigate that menu (it needs arrow-key + Enter, not typed text), so the session
  dies. The plugin (`~/.hermes/plugins/claude-orchestrate/__init__.py`, fireworks
  branch) sets `hasCompletedOnboarding` and approves the API key in
  `~/.hermes/claude-k3-config/.claude.json`, but trust is stored per-directory as
  `projects[<abs-path>].hasTrustDialogAccepted = true` in that same file — it is
  NOT pre-seeded for the run dir. Fix BEFORE `start`: pre-seed trust for the exact
  path the session will `cd` into (the worktree path =
  `<workdir>.parent/.orchestrate-worktrees/<worktree-name>`, or the scratch dir
  for design sessions):
  ```python
  import json, pathlib
  wt = "~/Trilogy/.orchestrate-worktrees/<branch>"  # the rundir
  cfg = pathlib.Path.home()/".hermes"/"claude-k3-config"/".claude.json"
  d = json.loads(cfg.read_text())
  d.setdefault("projects", {}).setdefault(wt, {})["hasTrustDialogAccepted"] = True
  cfg.write_text(json.dumps(d, indent=2))
  ```
  Then `start` runs straight past the dialog. Distinguish this from a real crash:
  a trust-gated exit shows the \"trust this folder?\" menu in the pane (`status`
  tail) at exit time; a true crash shows a working/thinking pane then disappears.
  This is NOT an auth failure — Fireworks routing is up (claude launched and
  connected); probe auth by checking whether the menu appeared, not by assuming
  the null outcome means auth is down.

<!-- LESSON: Fireworks/K3 "reads outside working directories" permission prompt
stalls sessions. A claude_orchestrate session (model_provider=fireworks) whose
workdir is a scratch dir or worktree, reading a repo OUTSIDE that workdir, hits
an interactive TUI menu "Allow reads outside the working directories? 1.Yes
2.No 3.Ask again". Text `steer` cannot navigate arrow-key menus; the session
sits on the prompt and looks like a silent crash (status frozen at
investigating, no outcome). The `permissions.blockReadsOutsideWorkingDirectories
= false` flag in ~/.hermes/claude-k3-config/.claude.json does NOT reliably
suppress it. Fix: in the poll loop, `tmux capture-pane` and if the prompt text
is present, `tmux send-keys Enter` to dismiss it (option 1 is pre-highlighted).
Pre-seed `projects[<workdir>].hasTrustDialogAccepted=true` too. Same class as
the trust-dialog pitfall already in the skill: both are first-run TUI menus
that kill Fireworks sessions, distinguishable from a real crash by the menu
text in the pane.
-->
<!-- LESSON: implementer over-build — unrelated migration/test edits.
A coding session can fold in pre-existing repo bugs it notices while
implementing. Observed: a task to wire provision.sh ALSO renamed an existing
migration 0002_transcript_file_id.sql -> 0003 and rewrote its body to
ADD COLUMN IF NOT EXISTS, claiming to fix a version collision with a sibling
0002_session_status_check.sql. Renaming an already-shipped migration is
dangerous (prod DBs record version 2) and was out of scope. Fix: after the
session reports done, `git diff origin/main..HEAD --name-only` against the
design's planned file list; any file NOT in the design is a scope-creep
candidate. Revert out-of-scope files directly (git checkout origin/main --
<file>, or rewrite the content) and steer the session to re-test+commit, or
finish yourself. Record the pre-existing bug as a linked kanban task, do not
let the PR carry the fix. The migration collision itself was a real pre-existing
origin/main bug (13 DB test files red, schema_migrations_pkey duplicate) that
must be baselined, not fixed in this PR.
-->
<!-- LESSON: baseline test runs need a separate worktree with linked node_modules.
To prove a branch's failures are pre-existing (not regressions), run the suite
on a clean origin/main checkout: `git worktree add --detach <path> origin/main`,
then `ln -s <main-checkout>/orchestrator/node_modules <baseline>/orchestrator/node_modules`
(worktrees don't share node_modules). Run vitest on both, diff the passing-file
sets: "passed on baseline but failed on branch" = regressions (must fix);
"failed on both" = pre-existing (record, don't block). `git worktree remove
--force` the baseline after. This is the rigorous version of the skill's
"baseline first" rule when DB-dependent tests are involved.
-->
<!-- LESSON: repeated rebase conflicts on a slow-moving main.
When a PR sits open while main keeps landing batches (a security remediation
wave, sibling PRs), expect to be asked to rebase more than once and to hit
conflicts in the SAME files each time. Resolution pattern that works: for each
conflicted file, read both sides first (`git log --oneline main -- <file>` or
the conflict hunk itself) to see WHAT each side added, then keep both by
merging import lists and both describe/test blocks rather than picking one
side. Verify the merge structurally before running anything: grep-count that
each branch's marker (an import name, a `describe("...")` block) appears
exactly once — catches a dropped or duplicated block before wasting a test run
on it. Only after that, run tsc/lint/full-suite, then a focused run of just the
conflicted test file to confirm both branches' suites pass. After each
force-push, `mergeStateStatus` goes UNKNOWN for several seconds before GitHub
recomputes it — poll (`gh pr view --json mergeable,mergeStateStatus`) until it
settles to MERGEABLE/CLEAN rather than reporting UNKNOWN as a problem.
-->
<!-- LESSON: kanban triage->ready requires `specify`, not promote/claim.
A task created in `triage` status cannot be `claim`ed (errors "status=triage")
and `promote` only moves todo/blocked->ready (errors "promote only applies to
todo or blocked"). A `dispatch` pass also won't move triage tasks (it promotes
todo->ready but leaves triage alone). The correct transition out of triage is
`hermes kanban --board <b> specify <task_id> --author <who>` — this records the
triage decision and moves triage->todo; a subsequent `dispatch` pass (or the
gateway daemon) then promotes todo->ready, after which `claim` works. Full
sequence for a needs-design=no task you're executing directly: `assign` ->
`specify` -> `dispatch` -> `claim`. (The `--board` flag is a GLOBAL kanban
option that goes BEFORE the subcommand: `hermes kanban --board <b> <cmd>`, not
`hermes kanban <cmd> --board <b>`.)
-->
<!-- LESSON: claude_orchestrate start overwrites prompt.md with the `prompt` arg.
If you pre-write a detailed spec to ~/.hermes/tasks/<id>/prompt.md and then call
`start` with a short "read prompt.md and execute it" wrapper as the `prompt`
arg, `start` WRITES that short wrapper into prompt.md, clobbering your spec.
The session then reads a self-referential file ("read prompt.md" whose body is
"read prompt.md") and correctly reports NEEDS_CONTEXT / blocked. Fix: do NOT
pre-populate prompt.md yourself. Either (a) pass the FULL spec as the `prompt`
arg directly (claude_orchestrate writes it to prompt.md for you), or (b) write
your spec to a DIFFERENT filename (e.g. spec.md) and pass `prompt`="Read
~/.hermes/tasks/<id>/spec.md in full and execute it" so start's write of
prompt.md doesn't touch your spec. If you already hit the clobber, rewrite
prompt.md with the full spec and `steer` the still-alive session to re-read it.
-->
<!-- LESSON: ad-hoc verification script for conflict-resolution edits.
When a gate demands fresh verification evidence for a specific edit (not just
"suite is green"), write a temp script (`mktemp -t hermes-verify-XXXXXX.sh`)
that: (1) greps for leftover `<<<<<<<`/`=======`/`>>>>>>>` markers in exactly
the files touched by the resolution; (2) greps that each side's import AND at
least one use-site of that import are present (an import with no use-site
means the merge kept the name but dropped the usage); (3) runs the project's
CANONICAL test/lint commands read from `package.json` `scripts.test` /
`scripts.lint` (don't guess `npm test` vs `vitest run` vs a monorepo script —
read the actual script string first); (4) runs a focused test invocation on
just the conflicted file and confirms 0 failed; (5) confirms local HEAD ==
`origin/<branch>` so the evidence is against what's actually pushed. Delete
the script and any temp log files after. This satisfies "fresh evidence" gates
without re-litigating the whole suite from scratch every time.
-->
<!-- LESSON: foreign stashes in the shared stash list corrupt `git stash pop`.
A shared repo checkout accumulates stashes from OTHER tasks/branches (the list
is repo-global, not per-worktree). A bare `git stash` + `git stash pop` in a
worktree can pop a FOREIGN stash (different branch) and fire spurious merge
conflicts in files you never touched (observed: routes-admin.ts conflict from a
smoke-probe stash). It also means 'git stash; run tests; git stash pop' is NOT
a safe way to get a baseline — the cycle silently mis-fires. Fix: never use
stash in a kanban worktree. For a baseline run, `git worktree add --detach
<path> origin/main` (plus a node_modules symlink) instead — clean, isolated,
no stash. This also prevents the false 'tests fail on baseline too' reading
that a contaminated stash cycle produces (it masked a real regression here).
-->
<!-- LESSON: VirtualClock.sleep(0) parks a waiter that never resolves without advance().
Adding `await clock.sleep(x)` before an existing call path is NOT a no-op when
x can be 0: VirtualClock.sleep(0) pushes a waiter that only resolves on an
explicit advance(), unlike SystemClock whose setTimeout(0) resolves on the
event loop. A caller that never advances the clock after the call (the
reconcile recording sweep) hangs forever (test timeout). Fix: guard with
`if (delayMs > 0)` before sleeping, so a 0 delay registers no waiter, matching
the prepare-proctoring.ts pattern.
-->
<!-- LESSON: claude_orchestrate deny-guard blocks push/PR by design
The orchestrate PreToolUse deny-guard hook hard-blocks `git push` and
`gh pr create` inside the T2 session ("the merge gate is the broker; the T3
agent edits+commits, never pushes/PRs"). Don't fight it or work around it:
have the T2 commit and verify locally, then the orchestrator (main session)
does `git push` + `gh pr create` itself after independently re-running the
suites. Tell the T2 up front it will not push so it doesn't burn a turn
diagnosing the block.
-->
<!-- LESSON: Next.js build-time inlining silently killed an env-gated route.
A wrapper route gated on `process.env.WRAPPER_TEST_LOGIN_TOKEN` +
`process.env.NODE_ENV === "production"` worked in vitest but shipped as a
bare `return 404` in the production build: Next/webpack statically replaces
literal `process.env.<NAME>` member expressions and the minifier folds the
comparison, dead-code-eliminating the real runtime env lookup. The unit
tests stayed green because vitest never runs the minified output. Detect by
grepping the compiled chunk (`.next/server/app/**/route.js`) for the env
identifier and by curling the route under `next start`; fix by reading env
through a `runtimeEnv(name)` indirection the inliner cannot fold
(wrapper/src/lib/http/runtime-env.ts). Any env-gated/debug surface in a
Next app needs this treatment and a live check against the production
build, not just the unit suite.
-->
<!-- LESSON: "verified e2e" must mean the real user path, not an API/unit substitute.
Calling a multi-hop user-facing flow (login -> admission -> session -> sandbox ->
terminal) "verified e2e" after only hitting the backend API directly (session CRUD
calls, fabricated join requests) misses exactly the bugs that only exist in the
browser-facing glue: silent fire-and-forget calls whose failures are swallowed, a
CDN/proxy stripping the Host header so redirect construction breaks, a WS route
that was spec'd but never wired. These do not show up in any API-level check.
Corrective from the user after several such false "done" reports: "how did you
test it e2e and pass it if things like this are just coming up?" Rule: for a
user-facing flow, "e2e verified" requires driving the actual browser/real infra
path end to end at least once before reporting success — an API-level contract
call against the same backend is a narrower, different claim and must be labeled
as such ("contract-tested", not "e2e verified"). When you cannot drive a browser
yourself, say plainly what kind of check you actually ran and that a live
click-through is still needed, rather than upgrading the language to "verified"
or "e2e" for something narrower than that.
-->
<!-- LESSON: stray `.worktrees/` dirs from kanban worker sandboxes are not yours.
A shared repo checkout that kanban workers also operate on accumulates untracked
`.worktrees/<task-id>/` directories from their isolated worktrees. Before every
commit, `git status --short` and confirm anything under `.worktrees/` is
untracked (`??`), not something you modified — then leave it alone, stage only
the files you actually changed, and never `git add -A`/`git add .` in a repo
where kanban workers may be running concurrently (it will sweep their worktree
into your commit).
-->
<!-- LESSON: a T2 claude_orchestrate session can come up on Claude Teams OAuth
even with model_provider=truefoundry, and stall dead.
Symptom: pane shows "Your organization has disabled Claude subscription access
for Claude Code · Use an Anthropic API key instead" and the session sits at an
empty prompt ("Cooked for 0s · done") without working. Cause: ~/.claude.json has
an oauthAccount entry, and that OAuth token can win over the TF gateway env.
Diagnosis only — never hand-fix by relaunching tmux with raw TF env and a
self-chosen model (that bypasses the pinned route, switches the billing group,
and exposes credentials in the tmux command line). For the scoped Opus review
route the plugin already injects TF auth and fails closed (Phase 3.3 step 1);
any other route hitting this stall means that route's auth is broken — STOP
and escalate per principle #7, do not improvise a replacement launch.
-->
<!-- LESSON: tmux `mouse on` alone does NOT wire the scroll wheel — you also need terminal-features.
To make the mouse wheel scroll a tmux pane (e.g. Claude Code transcript through
ttyd+xterm.js), `set -g mouse on` is necessary but NOT sufficient on tmux 3.4.
Its built-in `terminal-features` entry for `xterm*` only advertises
`clipboard:ccolour:cstyle:focus:title` — no `mouse`. Without
`set -as terminal-features 'xterm*:mouse'` tmux never enters mouse mode on the
client and never parses the incoming SGR wheel sequences: they leak into the
pane as literal bytes (a wheel tick appears as `64;91;27M` at the bash prompt)
instead of firing WheelUpPane. Debug path: `tmux -vv` server log shows the
client's negotiated `client_termfeatures` (grep for `mouse`) and whether wheel
bytes appear as `mouse input (SGR)` + `wheel at X,Y` (parsed) vs get written
to the pane (not parsed). Verify with a native PTY client sized to the window
(`pty.fork()` + `TIOCSWINSZ`), writing `\x1b[<64;col;rowM` (wheel up) /
`\x1b[<65;...M` (down) to the master, then `display-message -p '#{pane_in_mode}'`
— 1 = copy-mode entered = wheel works. Two gotchas: (1) the wheel coords must
be within the pane bounds or the key won't fire (a default 80x24 PTY puts
col 91 out of bounds and silently no-ops); (2) driving ttyd's own HTML page in
a browser does NOT forward input to tmux in a scratch harness — use a real PTY
client for the tmux-side proof, and confirm xterm.js sends SGR via a
WebSocket.send hook (`addInitScript`, byte-dump the frames).
-->
<!-- LESSON: Google resumable-upload is TWO write-requests per logical upload;
a Drive write-rate pacer that prices 1 token per upload under-paces ~2x.
When building/verifying a token-bucket limiter in front of Google Drive (or
YouTube) uploads, each logical uploadFile is an initiate/metadata HTTP request
PLUS a content HTTP request on the per-user write-request quota (ensureFolder
is likewise 2). If the pacer debits 1 write-token per call it admits ~2x the
real volume and the wave still 429s (observed: 1242 429s + 7 transcript
failures with the pacer "on" but under-priced, vs 191 429s + 0 failures after
charging 2). Price the limiter in actual API requests, not logical calls, and
make the per-call write count a config knob. Verify against a SIMULATED
429ing sink that charges the same 2-per-upload so the paced-vs-unpaced delta
isolates the limiter's effect.
-->
<!-- LESSON: a T2 blocked on its own Monitor/background-task wait ignores
queued steers until you Esc-interrupt the wait.
When a T2 backgrounds a long vitest run and arms a Monitor that never fires
(e.g. its pgrep target already exited), the pane freezes on "Waiting for
task" and a steer/send-keys message only QUEUES ("Press up to edit queued
messages"). Recover: `tmux send-keys -t <s> Escape` to break the wait, then
the queued message processes. Recover the background run's metrics yourself
from the on-disk log or the session's own .jsonl transcript under
~/.claude/projects/<workdir-slug>/ (grep for the marker line) rather than
trusting the T2 to find it — after a compact the T2 loses the number and will
burn turns re-searching the filesystem for a value that only lived in
scrollback.
-->
<!-- LESSON: claude_orchestrate steer requires task_id explicitly, not just message.
`claude_orchestrate(action="steer", message=...)` fails with "task_id and
message are required" even though message was passed — the tool always
needs the target task_id in the same call. Always pass both
`task_id=<the exact id used at start>` and `message` together on every steer;
don't assume the tool tracks a "current" session.
-->
<!-- LESSON: when related unmerged work sits on sibling branches in the same
repo checkout, citing a function/line number from memory (or from whatever
branch happens to be checked out elsewhere) instead of the actual target
branch is a recurring, self-repeating failure mode — it hit both the design
author AND the supervisor reviewing it in the same session, from the same
root cause. If branch A (in review) and branch B (an unrelated unmerged PR)
both touch the same file, a design/spec citing "function X at line N" must
be verified with `git show <target-branch>:<path>` or a grep run INSIDE that
branch's actual worktree, never assumed from a sibling branch's code or from
what the file looked like in a different local checkout. Symptom when wrong:
a reviewer's "blocking" finding that a cited function doesn't exist turns out
to be checking the wrong branch too — verify which branch YOU are reading
before trusting either side of that disagreement.
-->
<!-- LESSON: after a review round lands fixes, sweep the WHOLE doc/diff for
residual stale claims, not just the section the reviewer flagged.
An author can correct the flagged sentence precisely while leaving an earlier
or later section still repeating the same now-wrong claim (e.g. a corrected
"current-state" note at one line, but a numbered build-step elsewhere still
citing the old wrong-branch function and line range). A revision commit that
"looks done" per the diff of the flagged hunk can still contain the exact
error the review blocked on. After any revision commit, grep the full file
for the corrected term/citation (e.g. the wrong function name, the wrong line
range) and confirm every remaining occurrence is now either absent or
explicitly reframed as a correction/merge-order note — don't stop at
re-reading only the paragraph that was called out.
-->
<!-- LESSON: when a design's mechanism choice hinges on an unverified runtime
behavior (does the platform's native feature actually cover this case, or
does docs' stated exclusion hold for the real error shape), make the design's
first deliverable a cheap, blocking live experiment that decides between the
candidate mechanisms — do not commit to building one mechanism on a docs
reading alone. Structure the doc as "Phase 0: observe X live, which
determines whether we do (config-only mechanism A) or (build mechanism B)",
gated before any code-writing steps. This keeps the design honest about what
is actually known vs assumed, and avoids building the more expensive
mechanism only to discover the cheap one already worked (or vice versa).
-->
