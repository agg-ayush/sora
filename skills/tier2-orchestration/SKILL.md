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
daemon needed). **Board: use the `--board <slug>` that T1 passed in your handoff
brief on EVERY `hermes kanban` call.** Never rely on the sticky active board — it
drifts and tasks land on the wrong repo's board. If T1 didn't specify one, resolve
it: `hermes kanban boards list --json` → the board whose `default_workdir` == your
repo path. No health-check curl, no daemon — kanban is always available as long as
Hermes is running.

## Core principles (non-negotiable)

1. **Read state first, then act.** Never track loop position in your own memory.
   Position lives on disk: kanban task state + the plugin task artifacts
   (`~/.hermes/tasks/<task_id>/` — `status.md`, `result.md`, `outcome.md`, `meta.json`).
   On any resume, reconstruct from there. Re-dispatching an already-done task is
   the #1 expensive failure.
2. **The kanban claim is your safety net + heartbeat discipline.** It structurally
   prevents duplicate work even if you misjudge — but still read state first. The
   TTL is 900s (15 min): call `hermes kanban heartbeat <task_id> --note "<progress>"`
   at each status.md write AND between `claude_orchestrate wait` calls. **`wait`
   blocks your event loop — you cannot heartbeat while blocked.** Use SHORT waits
   (timeout=120) + heartbeat between waits; if the session is still `working`,
   heartbeat then `wait` again. Long design/implementation turns routinely exceed
   900s — without this loop the claim expires and another T2 double-claims.
3. **Never trust an agent's self-report.** Verify with real tool output. `gate`
   reads the real diff; YOU run the test suite yourself. An agent writing
   `outcome=DONE` or "tests pass" is a claim, not evidence.
4. **Code comment/docstring conventions — enforce in every coding-session
   prompt.** The T3 worker (Claude Code, kimi-k3) does not inherit Hermes memory
   or the user's global comment conventions. Every coding-session prompt (Phase 2
   implementation, Phase 3.3 review-fix) must include: terse, present-tense,
   necessary only — no restating what the code shows, no issue/PR references, no
   narrating past/fixed behavior. Docstrings: only what's necessary — what it
   does + non-obvious caller contract; no design-rationale or 'why' narration the
   code already shows. Prefer no comment over a noisy one.
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
   - **Stall handling:** `stalled` = pane shows NO activity indicator AND no status
     change (a thinking/working session is NOT stalled). On a genuinely stalled
     claude session: first check `doom_loop` in the status/wait output — if
     `doom_loop: true`, the session is in a tool-call loop (same tool + same
     normalized args 3+ times) — do NOT steer or wait again, ESCALATE
     immediately (report the loop fingerprint and stop the session). If
     `doom_loop` is false, `interrupt` (Esc) once → `wait`; if still stalled,
     `diagnose` (captures pane+log for root-causing) then `stop` → fall back
     to codex. Codex ignores `--effort`.
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
3. `claude_orchestrate start` in a SCRATCH DIR (not the target repo, no
   `worktree`), `executor=claude`, `model_provider=fireworks` (Kimi K3 via
   Fireworks — the design author), `effort=high`. Do NOT pass `model` (K3 is set
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
   its path for the reviewer. Use the SHORT-wait + heartbeat loop from
   principle #8 until the session finishes (a high-effort design turn routinely
   exceeds the TTL).

**1b.2 Design review** (Codex/Sol, cross-engine):
1. `claude_orchestrate start` in a scratch dir, `executor=codex`,
   `model=openai-group/gpt-5.6-sol` (Sol — the design reviewer). `task_id` e.g.
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
2. `claude_orchestrate wait`; read the VERDICT file (NOT the doc). **Use the same
   SHORT-wait + heartbeat loop as 1b.1** (principle #8). Branch:
   - `approved: yes` → design accepted. Proceed to 1b.3 (attach + implement).
   - `approved: no` → write the blocking issues to a file (`<issues-file>`,
     out-of-repo). Start a NEW Claude Code author session
     (`model_provider=fireworks`, `effort=high`)
     in a scratch dir, pointed at the current doc + `<issues-file>` to REVISE:
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
   - The kanban claim is independent of the coding executor. If claude is down,
     fall back to `executor=codex` — the claim stays held (no need to
     release/re-claim).
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
3. `claude_orchestrate wait` with SHORT timeouts + heartbeats between waits —
   the same SHORT-wait + heartbeat loop as principle #8.
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
   - **Fallback on failed/crashed/stalled claude run**: retry the SAME unit ONCE
     with `executor=codex`. The kanban claim stays held (no need to
     release/re-claim — the claim is separate from the executor). If codex also
     fails → ESCALATE.
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
1. `claude_orchestrate start` a Claude Code session (`executor=claude`,
   `model_provider=fireworks` — Kimi K3) in the
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
2. `wait` for the session; read the verdict file. (This is a distinct review
   session from the implementer session — never reuse the implementer to review
   its own work.)
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
     hermes send -t telegram:<chat-id> -q "PR ready for review: <task title> — <PR url>"
     ```
     Do this once per PR, right after moving to `review`. Also subscribe the task so
     `blocked`/`completed` events auto-ping Telegram:
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

### Phase 5 — Cleanup
1. Mark the task done. The task is in `review` (Phase 4 moved it there for the
   merge gate), and `hermes kanban complete` accepts review-state tasks. Use:
   `hermes kanban complete <task_id> --result "merged via PR #N"`.
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

## Pitfalls
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
