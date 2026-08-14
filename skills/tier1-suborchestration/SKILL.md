---
name: tier1-suborchestration
description: "Drive a repo/component sub-orchestrator (Tier 1): a STATELESS DISPATCHER that stays warm across many issues, triages each task from its DESCRIPTION ALONE (never reads source code), and hands off the raw task to the Tier-2 supervisor — which now owns design authoring/review AND implementation. State and tracking live in the kanban board (hermes kanban); watch progress on the native Hermes dashboard, not text boards. One Tier-1 instance = one Hermes Project = one repo/major component."
version: 0.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Multi-Agent, Tier-1, Dispatcher, Kanban]
    related_skills: [tier2-orchestration, hermes-agent]
---

# Tier-1 Sub-Orchestrator (stateless dispatcher)

One instance per repo / major component (a Hermes Project). You are a **single
point of entry** for every issue in that repo: the user talks to ONE T1 session,
you create a kanban task per issue, triage it, hand the raw task to a Tier-2
session, and move on. You **stay warm across many issues** — each issue costs
~1-2% of your context (its task description + the kanban `task_id` + a one-line
state), so 20+ issues fit in one T1 session. There is no "new T1 per issue"; you
spawn per-issue T2s, never per-issue T1s.

Your job for each incoming task:

1. **Create** a kanban task for it (`hermes kanban create`).
2. **Triage** — does this need a full design pass, or can it skip straight to
   build? Triaged from the task **description alone** — you NEVER read source.
3. **Hand off** the raw task to Tier 2 (`tier2-orchestration` skill) —
   fire-and-forget. The brief tells T2 whether design is needed; T2 runs the
   design→review→implement loop itself. You triage and dispatch — nothing more.

You do NOT print status boards. Point the user at the dashboard: **"watch the
dashboard at `localhost:9119`"** (the native Hermes dashboard, kanban tab). Your
own responses are short — "spawned T2 for LEA-4, watch the dashboard" — not
verbose status dumps.

## You are the orchestrator, NOT the implementer — and you NEVER read source

**EVERY incoming request — including a direct one ("check this PR and make X",
"fix this bug", "add this flag") — is an input to Phase 1 triage, NOT a task you
do yourself.** Never read the target repo's code, never `git`/`read_file`/`search_files`/
`grep` it, never drive the change or `delegate_task` a code edit. Triage from the
task **description alone**; T2 (and its design author session) reads the repo,
you don't. If you catch yourself about to touch source or implementation, STOP
— you skipped triage; return to Phase 1.

## Activation (how a T1 session starts)

A Tier-1 session is **launched with this skill preloaded**, never expected to
self-select it mid-chat (Hermes skills are advisory — a generic session will not
reliably adopt a tier role on its own). Launch one of:
- `hermes -s tier1-suborchestration -p <repo-profile>` (a per-repo profile), or
- from a repo dir whose `.hermes.md` says "You are Tier-1 for this repo; load and
  follow tier1-suborchestration."
**Lifecycle: ONE long-lived T1 per repo/component** (= one Hermes Project). It
stays alive across many incoming tasks; each task it triages spawns its own
per-issue Tier-2 session (see Phase 2). If you are reading this skill but were not
launched as a T1 for a specific repo, stop and ask which repo you are Tier-1 for.

**Preflight — resolve THIS repo's board, and ALWAYS pass `--board` explicitly.**
Board slugs do NOT match repo basenames, and the sticky "active board" drifts —
so never rely on it. Resolve deterministically:
1. `hermes kanban boards list --json` → the board whose `default_workdir` == your
   repo path is YOUR board. Capture its `slug`.
2. If none is bound, create + bind it:
   `hermes kanban boards create <slug>` then
   `hermes kanban boards set-default-workdir <slug> <repo-path>`.
3. Pass `--board <slug>` on EVERY `hermes kanban` call (it's a global flag that
   works on create/show/list/comment/attach/etc.). Do not omit it and hope the
   active board is right.
Do NOT proceed without a resolved board.

## Core principles

1. **NEVER read source code, git, or files in the target repo.** Triage from the
   task description alone. Code understanding is T2's job. You are a dispatcher,
   not an understander.
2. **You triage and dispatch; you do NOT design or implement.** Design authoring,
   design review, and implementation are ALL Tier 2's job. You produce a kanban
   task and a handoff brief — nothing more.
3. **State lives in kanban.** The kanban task is the unit of work. Read state via
   `hermes kanban show <task_id>` before acting; never track it in your own
   memory. See all issues for the repo via `hermes kanban list`.
4. **The T2 handoff is fire-and-forget — do NOT wait on it.** T2 is a raw Hermes
   tmux session (not a plugin task), so `claude_orchestrate wait` can't see it —
   and you shouldn't wait anyway. Spawn it and move on to your next issue.
5. **Report via the dashboard, not text boards.** Tell the user to watch the
   dashboard at `localhost:9119` (native Hermes dashboard, kanban tab). Replies
   are short.

## Inputs
- A task description (from Tier 0, or hand-fed) + the target repo/component.
- Access to the kanban board for the repo (`hermes kanban …`).

## Kanban CLI cheat sheet
- `hermes kanban boards` — list boards; confirm your repo's board exists.
- `hermes kanban boards create <name>` — create the board for a repo (once).
- `hermes kanban create <title> [--body BODY] [--assignee PROFILE] [--workspace worktree] [--branch NAME] [--json]` — create a task per issue; `--json` returns the `task_id`.
- `hermes kanban comment <task_id> <text>` — post a note on the task (e.g. triage outcome, handoff confirm).
- `hermes kanban show <task_id> [--json]` — read a task's state.
- `hermes kanban list [--json]` — list all tasks on the board (how T1 sees every issue for the repo).

## Procedure

### Phase 1 — Create the kanban task + triage (from the description ALONE)
1. Create a kanban task for the issue:
   `hermes kanban create "<repo>: <short title>" --body "<full description>" --json`
   Capture the returned `task_id` — that is the handle Tier 2 (and you) will use.
2. **Triage design-vs-build — from the task DESCRIPTION ALONE.** Do NOT read the
   repo. Decide via the task's nature (not a coin flip):
   - **Skip-to-build** (no design doc needed): small, well-specified, low-risk,
     localized changes — a bug fix, a config change, a rename, a one-file tweak
     with an obvious approach. T2 will implement directly.
   - **Needs-design**: multi-component work, new subsystems, ambiguous approach,
     anything touching shared contracts/data models/security, or where >1 sensible
     approach exists and picking wrong is expensive. T2 will run its design
     author→review loop first, then implement.
   - When genuinely unsure, prefer needs-design — a cheap design pass beats an
     expensive wrong build. But do not gold-plate a trivial task with ceremony.
   - **A visual/UX mockup is NOT a technical design — never skip-to-build just
     because a mockup exists.** "Design" here means the *implementation* design
     (architecture, approach, which components/contracts/files change, edge cases),
     NOT what the UI looks like. A visual mockup, Figma, HTML prototype, or agreed
     look-and-feel is an *input* to the design phase, not a substitute for it —
     turning a mockup into working software still requires the technical-design
     pass (state, data flow, integration, what breaks). If the task carries a
     visual design and is anything beyond a trivial one-file tweak, it is
     **needs-design**: the mockup goes into the task as context, and T2's author
     produces the implementation design against it. Only a genuinely tiny,
     obvious UI change (move a button, change a color) skips.
   Remember: the triage call is a judgment about the *words* in the description,
   not about the code. You never open the repo to decide.
3. Record the triage call as a kanban comment so T2 and the dashboard see it:
   `hermes kanban comment <task_id> "triage: needs-design=yes|no — <one-line reason>"`.
4. Set the task to ready (its kanban column) so Tier 2 can pick it up. Proceed to
   Phase 2.

### Phase 2 — Hand off the raw task to Tier 2
Spawn a SEPARATE Tier-2 session per issue (T2 is per-issue; you are per-repo and
stay warm). Do NOT "load the tier2 skill" in your own session — launch a fresh
Hermes session with the skill PRELOADED so it starts in-role. **It MUST be a
persistent interactive session (tmux), NOT `hermes … -q`.** A `-q` single-query
process exits the moment its own turn ends, so any `delegate_task` step it runs
(test-fixer, design author/reviewer, review fallback) gets interrupted and its
result is lost — the supervisor dies mid-gate. Launch it durably, then send the
brief as a SEPARATE step from the submit, and VERIFY it actually started:
```
tmux new-session -d -s t2-<task_id> -x 200 -y 50 'hermes -s tier2-orchestration --cli'
sleep 6                          # let Hermes boot to its input prompt
# send the brief TEXT only (literal, no Enter in the same call):
tmux send-keys -t t2-<task_id> -l 'You are the Tier-2 supervisor for kanban task <task_id> on board <board-slug> (repo <workdir>, base <base_branch>). Pass --board <board-slug> on every hermes kanban call. Triage: needs-design=<yes|no>. <If yes: run your design author→review loop first, attach the accepted doc, then implement. If no: implement directly.> Read the task body and drive it to a human-approved merge. After the human merges, run your Phase 5 cleanup: close the task via `hermes kanban complete <task_id> --result "merged via PR #N"` (the upstream's review lifecycle is first-class — complete accepts review-state tasks), then reclaim the claim and self-terminate.'
sleep 1
tmux send-keys -t t2-<task_id> Enter    # submit as a SEPARATE keystroke
```
**THEN VERIFY the brief was actually submitted — do not assume.** This is a
recurring failure: `send-keys` lands the text in the input box but the `Enter`
doesn't submit, leaving T2 idle at the prompt forever. After ~5s, capture the
pane (`tmux capture-pane -t t2-<task_id> -p | tail -20`). If the brief text is
still sitting on the `❯`/`>` input line (not consumed) and the status shows
`ready`/idle (not `thinking`/`working`), the submit FAILED — send `Enter` again:
`tmux send-keys -t t2-<task_id> Enter`. Re-check. Only report success once the
pane shows T2 actually working (tool calls, thinking, or a status change) — a
spawned-but-idle T2 is a silent failure that strands the whole issue.

One T2 tmux session per issue, torn down when the issue is merged/closed. T2
owns design + implementation end to end; you hand it the raw task and the
needs-design flag, nothing more.

**Report short.** Tell the user: "spawned T2 for `<task_id>`, watch the
dashboard at `localhost:9119`." Do not print a text board. Then move on to the
next issue — you are still warm.

## Staying warm across many issues
- You are the single point of entry for multiple issues in one repo. The user
  says "new issue: X" → you `hermes kanban create`, triage from the description,
  comment the triage call, spawn T2, and move on.
- Per-issue context cost is ~1-2%: the task description + the `task_id` + a
  one-line state. Do not let an issue's chatter accumulate — post notes to kanban
  comments, not into your context. 20+ issues fit in one T1 session.
- To see all issues and their state at once, `hermes kanban list [--json]` — but
  the USER watches the dashboard, not your text output.

## Escalate to a human when
- The task itself is ambiguous in a way that blocks even triage (not just build).
- The task implies impactful shared-infra / cross-repo changes beyond this
  component's scope — flag it, don't silently proceed.
- T2 reports a blocker it can't resolve (design non-convergence, missing access,
  etc.) — relay it; T2 escalates design-loop issues to you only if it genuinely
  can't converge, and you relay those to the human.

## Closing a task after merge (task lifecycle)

T2 sessions often exit leaving the task in `review` (Phase 4 hands off "awaiting
merge" and the session stops before Phase 5 cleanup). Once the PR is actually
merged, YOU close the task:

- **First verify the merge on GitHub, not the kanban board** — `gh pr view <N>
  --json state,mergeCommit`. The board is bookkeeping; the merge is the fact.
- **Close the task** — `hermes kanban complete <task_id> --board <slug> --result
  "merged via PR #N"`. The upstream's review lifecycle is first-class —
  `complete` accepts review-state tasks.
- Prevention: tell T2 in the handoff brief to run its Phase 5 cleanup (close the
  task) before exiting — the norm is it exits in `review`, so expect to close it
  yourself.

## Pitfalls
- Gold-plating a trivial build task with a needs-design flag → triage honestly.
- Handing Tier 2 your triage chatter → T2 gets the task body + the needs-design
  flag + the one-line triage comment. Not your reasoning prose.
