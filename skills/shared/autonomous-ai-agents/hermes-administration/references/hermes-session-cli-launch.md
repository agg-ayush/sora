---
name: hermes-session-cli-launch
description: "Correct CLI invocation for spawning a persistent, skill-preloaded Hermes session in a detached tmux pane (used by tier1/tier2 orchestration handoffs and similar patterns). Use when launching a durable background Hermes session via tmux — covers the exact flags required and the silent-failure mode when they're wrong."
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Hermes-CLI, Tmux, Orchestration, Session-Launch]
    related_skills: [tier1-suborchestration, tier2-orchestration, hermes-agent]
---

# Launching a persistent skill-preloaded Hermes session via tmux

Used whenever an orchestration pattern (T1→T2 handoff, or any other durable
background Hermes worker) needs to spawn a **detached, persistent, interactive**
Hermes session with a skill preloaded.

## Related operational pitfalls

See refs: `wedged-session-recovery.md` (mid-task stall), `clarify-loop-blocking.md`,
`clean-exit-no-pr-recovery.md` (clean exit, real work, no PR — most common;
also multi-choice pickers).

See archived `dispatch-style-inheritance.md` note (not an active skill reference; verify the current tier skill instead): spawned coding/design/review
sessions don't inherit Ayush's Hermes-memory style rules (comment terseness,
customer-facing changesets, PR description conventions) — restate them in every
dispatch prompt or expect a rewrite round.

Includes a stuck-`review`-state task recovery procedure (`kanban complete`/
`promote`/`unblock` all refusing a task due to a stale `task_runs` row — try
`kanban-review.py --to done` first, then direct DB fix) — see pitfall #6.

See archived `t2-orchestrate-lifecycle-pitfalls.md` note (not an active skill reference; verify the current tier skill instead) for detailed lifecycle
failure modes and recovery procedures, including: `steer` silently dropping
input on an already-finished session, a T2 session dying mid-gate while a
review/fix subagent keeps running independently, minimal-diff-vs-prettier-clean
tradeoffs, and (pitfall 4) **a `review`-state task's T2 session already being
gone when human follow-up arrives post-PR** — launch a fresh differently-named
session briefed with the existing branch/worktree/PR instead of trying to
resurrect the dead session name.falls.md` for two recurring T2
failure modes: (1) `claude_orchestrate steer` silently no-ops on a session
that already reached `done`/`exited`, and (2) diff-churn reconciliation
(minimal-diff vs prettier-clean) is a real tradeoff requiring explicit
sign-off, not a silent pick.

## Correct command

See archived `t2-dispatch-discipline.md` note (not an active skill reference; verify the current tier skill instead) for the hard rule that a launched T2
supervisor never hand-edits target-repo code itself — even a fully-diagnosed,
"small" fix must be dispatched via `claude_orchestrate`, for the full lifecycle
of the issue (not just initial implementation).

```
tmux new-session -d -s <session-name> -x 200 -y 50 'hermes chat -s <skill-name> --tui'
```

- `-s <skill-name>` is a flag of the `chat` **subcommand**, not a top-level
  `hermes` flag. `hermes -s <skill-name>` (omitting `chat`) is accepted by
  argparse-level parsing in some contexts but is NOT the interactive chat
  invocation — the process exits almost immediately instead of booting to an
  input prompt.
- `--tui` launches the modern TUI (matches how these sessions are normally\n  driven/inspected via `tmux capture-pane`). Add `--cli` instead if you\n  specifically want the classic REPL.\n- Use `hermes chat --help` to confirm current flags if this ever looks stale —\n  flags do shift across Hermes versions.\n\n## Pitfall: instant death on the FIRST turn, seconds after a verified-alive launch, with no crash-log signature

Observed directly: `tmux new-session -d -s <name> 'hermes -s tier2-orchestration --cli'`
booted fine (confirmed via `tmux ls` + pane showing the input prompt), a brief
was sent and submitted correctly, the pane showed "Initializing agent...
reasoning..." — then the tmux session vanished entirely (gone from `tmux ls`,
its hermes process gone from `ps aux`) within ~15-20s, before the first tool
call completed. This is a DIFFERENT failure mode from the "dies after 15-45
min, often mid-lifecycle" pattern below: it is immediate, and
`~/.hermes/logs/tui_gateway_crash.log` had NO `gateway exit`/stdin-EOF line
anywhere near that timestamp — the documented diagnostic signature does not
always apply, and the log will not always explain the death.

Also observed in the same environment at the same time: a sibling session
launched with the bare top-level form `hermes -s <skill>` (no `chat`
subcommand, no explicit `--cli`/`--tui`) survived 1h12m+ without issue. Do not
treat `--cli` as reliably safer than the bare form on this evidence alone —
both forms have now been seen to die instantly AND to survive for hours;
neither is guaranteed, and the crash log won't always show why.

Practical response: don't burn cycles root-causing an instant death with no
log signature. Verify liveness with `tmux ls` a few seconds after sending the
brief (not just right after `new-session`), and if the session is gone,
respawn once under a NEW session name (never reuse — see the self-kill
pitfall below) using the documented-correct `hermes chat -s <skill> --tui`
form before assuming a deeper problem. A single instant death is not yet a
pattern; a repeat under the corrected invocation is worth escalating.

## Pitfall: `--cli` extends survival but does NOT guarantee it — a long-lived detached session can still die

(See archived `e2e-testing-and-review-specialist-notes.md` note (not an active skill reference; verify the current tier skill instead) for hermetic-E2E-test
debugging sequences and the `pr-review-toolkit` state-transition-reviewer gap — moved
there to keep this file under the size cap.)\n\nOn hosts where `hermes chat --tui` in a detached tmux pane dies from the TUI\ngateway closing its command pipe (`stdin EOF`), the documented workaround is\n`--cli` (classic REPL, bypasses the TUI gateway process). This DOES extend\nsurvival time (observed: minutes with `--tui` vs. tens of minutes with\n`--cli`), but it is **not immune** — a `--cli` session has also been observed\nto die the same way (`gateway exit ... reason=stdin EOF (TUI closed the\ncommand pipe)`, logged even under `--cli`) after roughly 15–45 min, sometimes\nmid-lifecycle on a multi-phase supervisor task (e.g. right after a gate/review\nstep passes, before commit/PR). Treat `--cli` as \"buys more runway,\" not\n\"solves the problem\": any long-lived (tens of minutes) detached supervisor\nsession on this host should assume it MAY die before completing and be\ndesigned so a mid-run death doesn't destroy already-good work — see\n`tier2-orchestration`'s \"commit early, don't let uncommitted work outlive the\nsupervisor\" pitfall.\n\nCheck `~/.hermes/logs/tui_gateway_crash.log` for `gateway exit` lines to\nconfirm this cause when a supervisor session goes silent/dead with no other\nvisible error — grep for the timestamp window around when the session was\nlast seen alive. If repeated respawns keep dying the same way within the same\nrun, stop respawning and drive the remaining steps directly instead (using\nwhatever design/review/implementation artifacts the dead session already\nwrote to disk) rather than burning further attempts against unstable\ninfrastructure.\n\n## Pitfall: an omitted `effort` (or similar) flag reads as ambiguous on a later audit

Leaving `effort` (or any per-call config like `model`/`executor`) unset on a
`claude_orchestrate start` call isn't harmless just because the executor's
default happens to be reasonable. A later audit (self- or external) can't tell
"intentionally using the default" from "forgotten" — it just sees a gap and
has to re-derive intent. State every meaningfully-different-per-call-site
config value explicitly at each call site, even when the value matches what
the default would have produced anyway. This is cheap insurance against
audit churn and against a future edit silently changing the default under an
unstated call.

## Pitfall: host sleep (laptop lid closed) kills detached tmux sessions — another death cause besides stdin-EOF

Observed directly: a healthy, actively-working `t2-*` tmux session (mid design-review
loop, no stdin-EOF signature) vanished entirely from `tmux ls` immediately after the
user reported closing their laptop lid. This is a THIRD distinct death cause beyond the
two documented above (instant-death-on-launch, and the 15-45min stdin-EOF mid-lifecycle
death) — the host going to sleep can suspend/kill the tmux server's child processes
outright, with no crash-log signature to check (it's not a Hermes/TUI-internal failure at
all, just the host losing power/suspending). Symptom: `tmux ls` no longer lists the
session, `tmux capture-pane` returns `can't find pane`, and the task's kanban claim never
advanced (still `ready`) because the session died before or during claiming.

This means on a laptop host, ANY unattended supervisor run is at risk from the user simply
closing the lid — not just from the TUI's own instability. Same recovery order applies
(check worktree for unpushed completed work first, respawn under a fresh never-reused
session name, re-send the claim-first brief). No fix available at the orchestration layer
(can't prevent the user's OS from sleeping); the practical mitigation is: whenever a
"is it healthy" check finds the session simply gone with no other explanation, ask/assume
host sleep as the default hypothesis before treating it as a novel crash worth deep
root-causing.

**This can recur repeatedly on the SAME task** (observed 3x in one session, one death per
lid-close) — it is not a one-shot fluke to root-cause once and move on from. Each time,
follow the identical respawn recipe (new session name, `hermes kanban --board <slug> claim
<task_id>` as the FIRST instruction in the brief, `tail -25` the pane a few seconds later to
confirm real activity). If the kanban task carries an attachment or comment showing a
completed sub-phase from a prior dead run (e.g. a design doc already authored and attached),
say so EXPLICITLY in the new run's brief — quote the substance (chosen mechanism, key
findings, rejected alternatives) and instruct it not to re-author that phase — so each
respawn resumes forward instead of re-doing already-finished work. Proactively tell the user,
once this has happened twice on the same task, that keeping the laptop awake (staying
plugged in with the lid open, or disabling sleep in System Settings) for the remainder of
the run is the actual fix on their end — repeating the respawn silently forever without
naming this is a worse outcome than saying it once.

**`caffeinate -i -s -d` does NOT prevent this.** Those flags block idle/display/system sleep
but NOT clamshell (lid-close) sleep — macOS suspends on lid-close regardless of caffeinate
unless an external display is attached. Observed directly: started `caffeinate -i -s -d` as
a background process after the 4th death, relaunched T2, and it still died at death #5 from
a lid-close — caffeinate had zero effect. Do not suggest or rely on caffeinate as the fix for
THIS failure mode; the only real mitigations are not closing the lid (external display
attached, or the user physically keeps it open) or macOS's own "prevent sleep on power
adapter" setting — nothing achievable from inside the agent's own tool calls.

**After 3+ deaths on the same task from this cause, stop respawning T2 as a persistent
supervisor and switch approach: drive the remaining phase(s) via a single non-interactive
`delegate_task` call instead of another tmux/hermes-chat session.** A background
`delegate_task` subagent doesn't depend on a long-lived local tmux pane surviving sleep — it
runs out-of-band and its result re-enters the conversation when done regardless of what the
laptop does in between. Concretely, once a design doc is complete (attached to the kanban
task or found on disk in the task artifact dir, e.g. `~/.hermes/tasks/<task_id>/design.md`),
package it as full context and delegate implementation directly: point `context` at the
design doc's absolute path with an instruction to read it first, restate the target
repo/branch-off-main/target-file constraints and the test/lint/build gate commands, and
require a PR (not a merge) as the deliverable. This trades T2's structured phases (ledger,
cross-engine review rounds, kanban heartbeats) for a single best-effort pass — an acceptable
tradeoff when the design is already validated and the alternative is burning more attempts
against unstable sleep-prone infrastructure. Still get the PR reviewed by a human before
merge, same as the T2 path.

### Lighter manifestation: tmux session SURVIVES the lid-close, only the in-flight API call dies

Not every lid-close kills the tmux session outright (the full-death case above). Observed
repeatedly (2x in one session, same task): `tmux ls` still lists the session, the pane is
still there, but the in-flight `Claude Orchestrate` worker call errored out with `API call
failed after 3 retries: Connection error` (network dropped mid-request when the lid closed)
and the top-level agent gave up and dropped to an idle `ready` prompt — no crash, no
disappeared session, just stalled. This is CHEAPER to recover than a full respawn:

1. Confirm the tmux session is still alive (`tmux ls | grep <name>`) and the pane shows the
   `API call failed` / idle-`ready` symptom, not a vanished session — if alive, do NOT
   respawn under a new name; that would abandon a perfectly good session for no reason.
2. Verify the network/gateway is actually back before steering, so you're not re-triggering
   the same failure immediately: `curl -sS -o /dev/null -w '%{http_code}' --max-time 10
   <the Seatbelt base URL https://<model-gateway> (or the configured non-TF endpoint)>` — expect
   `200`. (A direct `curl https://api.anthropic.com` check is irrelevant here if the worker
   routes through a TrueFoundry/custom gateway, not direct Anthropic — check the actual
   configured base URL, don't assume.)
3. Steer a resume message into the SAME session (`tmux send-keys -t <name> -l '<msg>'` then
   `Enter`) explicitly naming: network is back, what unit/phase it was mid-way through, which
   units are already committed (so it doesn't re-do finished work), and an instruction to
   re-claim the kanban task and continue. Confirm it actually resumes (`sleep 20-25; tmux
   capture-pane -t <name> -p | tail -12` showing real tool-call activity, not still idle)
   before reporting healthy.
4. This can recur multiple times across one run (each lid-close is independent) — repeat the
   same three-step check-verify-steer sequence each time rather than escalating to a full
   respawn, as long as the tmux session itself keeps surviving.

## Pitfall: `tier1-suborchestration`'s own Phase 2 send-keys template still embeds the deprecated bare `-s --cli` form

Confirmed directly: a T1 session copy-pasted `tier1-suborchestration`'s literal
Phase 2 launch template (`tmux new-session -d -s t2-<task_id> ... 'hermes -s
tier2-orchestration --cli'`) for two concurrent T2 handoffs, and both died —
one instantly mid-design-review, one with no artifacts written at all — inside
15-20 minutes, exactly matching the documented bare-`-s` failure mode above.
`tier1-suborchestration` is a manually-authored/protected skill, so it can't be
autonomously patched to fix its own example; until a human updates it, treat
its literal launch line as STALE and always substitute the corrected form from
this skill (`hermes chat -s <skill> --tui`) when actually spawning a T2 —
don't trust a tier skill's embedded shell snippet just because it's written
inline in the procedure text you're following.

Respawn recipe that recovered both dead T2s in this incident: fresh
never-reused session names, `hermes chat -s tier2-orchestration --tui`,
verify `tmux ls` shows the session before sending any brief, then a claim-first
brief that explicitly named any artifacts the dead predecessor already wrote to
disk (e.g. `~/.hermes/tasks/<task_id>/design-v1.md`, a `dreview.log`) with an
instruction not to re-author that work — both resumed forward correctly on the
first try. Also worth a quick `hermes chat --help | grep -E '\-s|--tui|--cli'`
before respawning if there's any doubt the flags still match this skill's
documented form — cheap, avoids repeating a stale-flag guess against a version
drift.

## Pitfall: `--cli` is only needed for detached-tmux children, not the top-level supervisor

`--cli`/`--tui` matters because of WHERE a process's stdin comes from, not
because of which skill it's running. A top-level supervisor (e.g. tier1) that
the user launches directly in their own interactive terminal has a real stdin
— the default TUI is fine there, no `--cli` needed. Only sessions spawned
INSIDE a detached tmux pane (a supervisor's own children, e.g. tier1→tier2)
need `--cli` forced, because that's where the TUI-stdin-EOF death happens.
Auditing "does every skill say `--cli`" is the wrong question; audit "is this
process's stdin an interactive terminal or a detached pane" and require
`--cli` only for the latter. Document which of a multi-tier pattern's own
launch vs. its children's launch needs it, explicitly, so the next audit
doesn't flag the top-level launch as a false gap.

## Pitfall: don't trust a "session died" report — verify tmux state directly

An agent (or a sub-report from one) claiming a spawned session "died," "is
gone," or "never advanced" can simply be wrong — e.g. it read the wrong
kanban board, or misread stale output. Before acting on a death report (respawning,
escalating, or rewriting a "root cause"), verify directly:
1. `tmux has-session -t <name>` — exit 0 / empty output means it's alive.
2. `tmux list-panes -t <name> -F '#{pane_pid}'` then `ps -p <pid> -o
   pid,command` — confirms the actual running command line (and whether it
   was launched with the flag you expect, e.g. `--cli`).
3. `tmux capture-pane -t <name> -p | tail -20` — shows real-time activity
   (thinking/tool-call output means it's working, not stalled).
Only escalate to "it's actually dead" once tmux itself confirms the session is
gone — a dashboard/kanban read alone is not proof of process death.

## Recipe: answering a repeated live "status?" / "healthy?" check on a running T2 cheaply

When the user asks for status on a spawned supervisor session repeatedly across
a session, don't re-read the whole kanban task history or scroll the full pane
each time — run this exact three-part check and report only the delta since the
last check:

```
hermes kanban show <task_id> 2>/dev/null | grep -E 'heartbeat|commented' | tail -4
tmux capture-pane -t <tmux-session> -p 2>/dev/null | tail -14
tmux ls 2>/dev/null | grep <tmux-session>
```

- The kanban `heartbeat`/`commented` tail gives the last durable checkpoint
  (unit progress, phase transitions, human-readable notes the supervisor wrote).
  Prefer these over `reclaimed`/`claimed` lock-churn lines — those are noise from
  the stale-claim pattern below, not progress signal.
- The pane tail shows live activity (current tool call name + elapsed seconds,
  e.g. `Claude Orchestrate (795s)`) — this is the "is it actually still working
  right now" signal, distinct from the last kanban checkpoint which can be many
  minutes stale during a single long orchestrate call.
- `tmux ls | grep <name>` is the final liveness gate — if the session is gone,
  everything else is moot; go to the recovery order below instead of reporting
  a status.
- Report status as: current phase/unit (from kanban) + what the pane shows it's
  doing right now + one honest flag if a single call has been running unusually
  long (a call sitting well past its own typical duration for that step is worth
  naming as "watch, not yet a problem" rather than staying silent about it).
- A `ready` status + a `reclaimed` event with `terminated: false` is COSMETIC
  (stale-claim TTL lapse during a long wait, not death) — never report this as
  "it died" on its own; corroborate against the tmux/pane check below before
  concluding anything is wrong.

**Combine all four checks (branch commits, tmux pane, tmux liveness, CI) into
ONE terminal call chained with `;`, not four separate tool calls, when polling
repeatedly across a long supervision run** (observed pattern: 8+ poll cycles
over 2.5h+ on one PR). This halves per-poll tool-call overhead without losing
signal. Pipe `gh pr view --json statusCheckRollup` through a python one-liner
instead of eyeballing the raw check list — this scales to PRs with 40+ checks:

```bash
cd <repo-or-worktree> && \
echo "---BRANCH TIP---"; git log --oneline <branch> | head -6; \
echo "---AHEAD---"; git status -sb | head -1; \
echo "---PANE---"; tmux capture-pane -t <tmux-session> -p 2>/dev/null | tail -18; \
echo "---CI---"; gh pr view <pr> --json statusCheckRollup,mergeable 2>/dev/null | python3 -c "
import sys,json
d=json.load(sys.stdin)
checks=d.get('statusCheckRollup',[])
fails=[c for c in checks if c.get('conclusion')=='FAILURE']
succ=[c for c in checks if c.get('conclusion')=='SUCCESS']
pend=[c for c in checks if c.get('status')!='COMPLETED']
print('mergeable:', d.get('mergeable'), '| FAILING:', len(fails), [c['name'] for c in fails[:3]], '| SUCCESS:', len(succ), '| IN_PROGRESS:', len(pend))"
```

Read the branch-tip commit list first when reporting back — it's the most
reliable progress signal of all (each committed finding/unit is unambiguous,
unlike pane text which can lag, repeat, or go stale mid-long-call). Cross-check
new commits against what the pane currently claims to be doing: a mismatch
(commits landing with no matching pane narration, e.g. a delegated subagent
committing on the session's behalf; or pane narration with no new commit,
e.g. still investigating/running tests) tells you which of the two signals is
currently lagging, so the status report doesn't parrot stale pane text as if
it were the latest state.

## Pitfall: kanban claim reclaimed mid-run looks like a death but may just be a missed heartbeat

A supervisor task tracked in kanban (e.g. tier2-orchestration) can show its task
flip back to `ready` with a stale/expired claim even when the session is still
alive and working. Cause: the claim TTL (commonly 900s / 15min) lapses because
the agent didn't call the heartbeat command during a long wait
(`claude_orchestrate wait`, a multi-minute design-author or review turn).
`ready` + stale-claim metadata does NOT by itself prove the process died — check
for BOTH signs before concluding it's dead:
1. Is the tmux session still listed (`tmux ls`) and is its pane showing recent
   activity?
2. Is there a `gateway exit · reason=stdin EOF` line in the crash log at/before
   the time the claim went stale (real death) vs. no such line (still alive,
   just an unheartbeated claim)?

**Recovery order when a supervisor task is found dead/exited (`ready` +
stale claim, tmux session actually gone):**
1. Check the crash log (`~/.hermes/logs/tui_gateway_crash.log` or the
   `tee`'d session log if one was piped) for the stdin-EOF signature to
   distinguish "launch flag / TUI-gateway death" from a genuinely novel failure
   worth investigating further.
2. **Check the worktree for completed-but-unpushed work FIRST** — a session that
   died after finishing a unit (commit made, not pushed, or PR not opened yet)
   has real progress that should be pushed/PR'd directly rather than re-running
   the unit from scratch. `git log`, `git diff <base>..HEAD --stat` in the
   worktree before deciding to respawn.
3. Only respawn (with a fresh, never-reused session name per the pitfall above,
   and `--cli` verified literally present in the command) if there is genuinely
   unfinished work.
4. If you push/PR the work yourself instead of waiting on a respawned session,
   still get an independent review pass (different session/engine) before
   calling it done — don't substitute your own diff read for a real review.

## Pitfall: `hermes kanban show <id> --json` nests fields under a top-level `task` key — a flat parse silently returns all-nulls

Piping straight to `json.load(sys.stdin)` and reading `d.get('status')`,
`d.get('claimed_by')`, etc. at the top level returns `None` for every field
even on a real, populated task — the payload is one level deeper, under
`d['task']`, with `comments` living as a separate top-level sibling
(`d['comments']`), not nested inside `task`. A `None`-everything result from
this shape mistake is easy to misread as "the task record is empty/gone" when
the task is fine and you just parsed it wrong.

Correct parse:

```python
d = json.load(sys.stdin)
t = d.get('task', d)          # tolerate either shape defensively
status, claimed_by = t.get('status'), t.get('claimed_by')
comments = d.get('comments') or t.get('comments') or []
```

Confirm the real shape once per session with a quick unparsed dump
(`... --json | head -c 500`) before writing a parser against it, rather than
assuming a flat schema and burning a call on a false "field is null" read.

## Pitfall: `kanban-review.py`'s status transition refuses a lapsed claim — re-claim before retrying, don't treat it as corruption

`python3 ~/.hermes/scripts/kanban-review.py <task_id> --board <slug> --reason "..."`
(moving a task to `review` in Phase 4 of a T2-style flow) can fail with `task is
'ready', cannot move to 'review' (allowed from: ['running'])` even when the
PR/work is genuinely done — this is the SAME claim-TTL-lapse-during-a-long-wait
cause as the "kanban claim reclaimed mid-run" pitfall below, just surfacing at
the review-transition step instead of mid-implementation. It is not a sign the
task record is broken. Fix: `hermes kanban --board <slug> claim <task_id>`
(re-claim to flip back to `running`), confirm with `hermes kanban --board
<slug> show <task_id> --json` that `status: running`, then re-run the
`kanban-review.py` transition — it succeeds immediately once the precondition
status is right.

## Pitfall: re-claiming does NOT reliably flip `ready`→`running` when driving a task manually (no dispatcher-spawned worker) — heartbeat and the review-transition script can both stay permanently blocked

The existing pitfall above (`kanban-review.py`'s status transition refuses a lapsed claim) says "re-claim to flip back to running" — that's true for the common case (a genuine claim-TTL lapse mid-run) but NOT universal. Observed directly on a manually-driven T2 pass (no `hermes kanban dispatch` spawning an actual worker session — the top-level agent itself was doing all the driving): `hermes kanban --board <slug> claim <task_id>` succeeded, but the task's `status` stayed `ready`, not `running`. Chased it through every manual lever available and none worked:

1. `hermes kanban heartbeat <task_id>` → rejected ("cannot heartbeat a non-running task").
2. `hermes kanban --board <slug> dispatch --max 1` → skipped the task entirely with `Skipped (unassigned): <task_id>` — dispatch requires an assignee AND appears to be the only path that actually sets `running`, which normally happens as a side effect of it spawning a worker.
3. `hermes kanban --board <slug> assign <task_id> <profile>` → assignee set correctly, but `status` was still `ready` afterward — assignment alone does not trigger the running transition either.
4. `python3 ~/.hermes/scripts/kanban-review.py <task_id> --board <slug> --reason "..."` → still refused with `cannot move to 'review' (allowed from: ['running'])`.

There is no manual CLI verb (as of this writing) that forces `ready`→`running` outside of the dispatcher actually spawning and claiming through a worker process. Don't loop through assign/dispatch/re-claim combinations hoping one works — that's wasted cycles chasing a state-machine transition that the manual-drive path structurally can't reach.

**Practical resolution:** this is cosmetic, not a real blocker, when you (the top-level agent) are doing the actual work yourself rather than dispatching to a kanban-tracked worker. Don't gate reporting "PR ready for review" on the kanban status transition succeeding:
- Keep the claim held (comments/attachments still work fine on a `ready`+claimed task).
- Post the PR link and gate verdict as a kanban comment for the audit trail (`hermes kanban --board <slug> comment <task_id> "PR: <url> — gate passed ..."`) — this succeeds regardless of status.
- Send the human notification directly (`hermes send -t telegram:...`) rather than relying on the `review`-status dashboard column or the status-triggered notifier (which only fires on `completed`/`blocked`, not `review` anyway).
- Report the task status nuance to the user as a one-line aside, not as a blocker needing resolution before you can hand off the PR.

## Pitfall: `claude_orchestrate gate`'s impl-complete check can misread when a session reused an EXISTING worktree

The `gate` action's impl-complete check inspects the rundir tied to the
session's `task_id`. If a coding session was dispatched pointing at an
already-existing worktree path (rather than having `claude_orchestrate start`
create a fresh one via `worktree=`), `gate` can report no live worktree /
`impl:fail` even though the diff is real and every unit is genuinely done —
it's inspecting the wrong location, not evidence the work is missing. Verify
directly before re-running anything: `cd <the actual worktree path>; git diff
<base_sha>..HEAD --stat` — a non-empty, unit-matching diff there overrides a
stale/misreading gate call. Don't re-run/re-dispatch units on the strength of
a `gate` verdict alone when you already have independent confirmation (commits,
prior test runs) that the work landed.

## Pitfall: `claude_orchestrate gate`'s impl-complete check has a SECOND false-negative mode — it can be checking for uncommitted working-tree changes, not a real diff against base

Distinct from the "reused an existing worktree" false-negative above. Observed directly: a
unit was fully implemented, committed, pushed, and a PR already opened — `gate` still reported
`impl:fail` on the same rundir/worktree it created. A clean `git status` right after a commit
is expected, not evidence of missing work; the check appears to look for dirty-tree state
rather than independently verifying commit history against the base branch.

Don't loop retrying `gate` or re-dispatching the unit on this signal alone — verify impl
completeness yourself against real evidence: `git log --oneline <base>..HEAD` (commits
present?), `git diff <base>...HEAD --stat` (real changed-file diff, not working-tree status),
`gh pr view <n> --json state,url` (PR exists?). A non-empty, unit-matching diff + an open PR
overrides a `gate impl:fail` verdict from this heuristic — note the override in your own gate
comment rather than treating the tool's check as ground truth.

## Pitfall: `git checkout <base_sha> -- <path>` inside the ACTIVE fix worktree overwrites the fix commit's files in the working tree — use a detached worktree to diff base-vs-fix failures instead

When proving a failing test is pre-existing env breakage (not caused by the diff) by
comparing base vs. fix, do NOT run `git checkout <base_sha> -- <path>` in the SAME worktree
holding the fix commit — it silently overwrites the fix's files in the working tree with the
base version (the commit itself stays intact, but `git log` still shows the fix commit as HEAD
while the files on disk are base's, which reads like the fix vanished). Recovery is `git
checkout HEAD -- <path>` (or `git reset --hard HEAD`), but it's an unforced detour.

Safer: a throwaway DETACHED worktree at the base commit, leaving the active fix worktree
untouched:

```bash
git worktree add --detach /tmp/base-compare <base_sha>
cd /tmp/base-compare && <run the same test suite>
# sort+diff the FAILED line lists between base and fix runs
git worktree remove /tmp/base-compare
```

Byte-identical failure sets (via `diff` on sorted failure lists) between base and fix is solid
proof a given failure predates the diff.

## Pitfall: task flips back to `ready` — diagnose with kanban JSON + tmux + crash log together, in one pass, before respawning

A task showing `ready` after you already dispatched a T2 onto it is NOT proof
of a novel problem — it is the expected surface symptom of the documented
"claim expired" state (see the "kanban claim reclaimed" pitfall below),
whether the cause is a missed heartbeat OR the session dying outright. Don't
guess; run all three checks together and let the combination tell you which:

```bash
hermes kanban --board <slug> show <task_id> --json   # status + claimed_by (parse per the shape above) + comments (did it even claim?)
tmux ls | grep <session-name>                          # session still alive?
grep -a "$(date +%Y-%m-%d)" ~/.hermes/logs/tui_gateway_crash.log | tail -5   # stdin-EOF signature at/near the death window?
```

- Comments present (it claimed, maybe posted a branch/worktree comment) +
  tmux session gone + no crash-log signature at that time = the "instant
  death on first turn, no log signature" mode from the launch pitfall above.
  Don't spend cycles hunting for a root cause the log won't show you —
  respawn once under a fresh, never-reused session name using the documented
  `hermes chat -s <skill> --tui` form, and add an explicit "re-claim the task
  as your first action" line to the brief so it doesn't sit idle assuming the
  old claim still holds.
- After respawning, verify recovery with the SAME `kanban show --json`
  parse — `status` moving from `ready` to `running`/`claimed` within the first
  30-60s of the new session's first tool call is the confirmation signal, not
  just an idle "pane looks busy" read.

## Pitfall: declaring an issue/task "already resolved" from a stale kanban/PR-merge read

Before triaging an incoming issue as duplicate, already-fixed, or safe to skip
(and especially before writing a kanban comment or a GitHub issue comment saying
so), check the issue's LIVE state — not just a prior merged PR or a kanban task
marked `done`. A PR that once closed an issue does not mean the issue stays
resolved; the reporter can reopen it with new information.

`gh issue view <n> --json state,stateReason,closedAt,comments` — if
`state=OPEN` and `stateReason=REOPENED`, read the reopening comment. It is the
current, real scope and supersedes the original issue body or any earlier PR
that closed it. A stale read here produces a wrong triage call, a wasted
supervisor spawn on already-done work, AND an incorrect public comment that then
has to be walked back once the mistake is caught — check live state first, every
time, before declaring something redundant.

## Pitfall: `hermes kanban --board <slug>` flag placement — must come BEFORE the subcommand

`--board` is a global flag on `hermes kanban` itself, not a flag of the
subcommand. It must appear right after `kanban`, before `list`/`create`/
`comment`/`show`/etc.:

```
hermes kanban --board <slug> list --json
hermes kanban --board <slug> create "<title>" --body "<body>" --json
hermes kanban --board <slug> comment <task_id> "<text>"
```

Putting it after the subcommand (`hermes kanban list --board <slug>`) fails
with `unrecognized arguments: --board <slug>` — this is an argparse position
requirement (each subparser doesn't inherit the parent's global flags after
its own positional), not a missing feature or a board-resolution problem. If
you hit that error, move the flag; don't debug board resolution instead.

## Pitfall: a skill invoked mid-chat is not the same as a properly launched session in that role

Skills like `tier1-suborchestration` assume activation via a dedicated launch
(`hermes -s <skill> -p <profile>` or a `.hermes.md` directive) with a clean
board binding and no prior source-touching in the session. When a user instead
invokes such a skill by NAME mid-chat in an ordinary session — one that may
have already read/touched the target repo's source before the skill loaded —
that discipline is already broken and can't be retroactively restored by
pretending the session started clean. Don't silently improvise a hybrid: state
the mismatch plainly and let the user pick between (a) proceeding as a
one-shot dispatcher for the tasks at hand (resolve the board, triage, spawn
downstream sessions) while flagging the session isn't a clean instance of the
role, or (b) handing off to a properly launched instance instead. Once the
user picks, proceed directly — don't re-litigate the choice on every
subsequent step.

Also, before creating any new task/session under such a role, list existing
work first (e.g. `hermes kanban --board <slug> list --json`) to check whether
something covering the same ground is already `running`/`review` under another
worker — never duplicate or re-dispatch work already in flight.

## Pitfall: silent tmux death on a bad invocation

If the command inside `tmux new-session` exits immediately (wrong flag, missing
subcommand, etc.), tmux tears the session down right away. This is **silent** —
`tmux new-session -d` itself reports success. The failure only surfaces later,
when you `tmux send-keys -t <session-name> ...` and get `can't find pane:
<session-name>` — by which point you've already "sent" a brief into a session
that never existed.

**Always verify liveness immediately after spawning, before sending any brief:**

```
tmux new-session -d -s worker1 -x 200 -y 50 'hermes chat -s some-skill --tui'
sleep 6            # let Hermes boot to its input prompt
tmux ls             # confirm worker1 is listed
```

If `tmux ls` doesn't show the session, the launch command itself is wrong —
fix the command and respawn before attempting to send a brief. Do not treat a
"no error" from `new-session -d` as proof the session is alive.

## Pitfall: brief text landing but not submitting

Even with a correct launch, `tmux send-keys -l '<brief text>'` followed
immediately by `tmux send-keys Enter` can occasionally leave the Enter
un-consumed (text sits in the input box, agent stays idle). After sending,
capture the pane and confirm the agent is actually working (tool calls,
thinking indicator, status change) rather than assuming submission succeeded:

```
tmux send-keys -t worker1 -l 'brief text here'
sleep 1
tmux send-keys -t worker1 Enter
sleep 5
tmux capture-pane -t worker1 -p | tail -20   # confirm real activity, not an idle prompt
```

A spawned-but-idle (or never-spawned) worker is a silent failure that strands
whatever task was handed to it — always verify, never assume.

## Pitfall: a respawned worker finds its OWN old session name and kills itself

When a worker dies/stalls repeatedly and you respawn it under the **same tmux
session name** each retry, the fresh session can — as part of routine
self-orientation ("what's my current state, any leftovers to clean up?") — run
`tmux ls` / `git worktree list`, spot a session with that name (itself, or a
dead predecessor with the same name), decide it's a stale leftover from a
prior failed attempt, and run `tmux kill-session -t <that-name>` to "clean
up" — which kills the session it's running in. This reads externally as "the
worker keeps dying for no reason" across several respawn cycles, when the real
cause is self-inflicted: it terminated itself while tidying up what it
believed was orphaned state.

Symptom pattern to recognize: a worker dies within seconds-to-minutes of being
steered toward any kind of environment/state audit (worktree list, tmux ls,
"check for leftovers"), with no code pushed and no error surfaced — because
there's no error, it exited cleanly by its own command.

Fixes (apply both):
1. **Never reuse a tmux session name across respawn attempts.** Give every
   fresh attempt at the same logical task a unique name (append an attempt
   suffix: `t2-foo`, `t2-foo2`, `t2-foo3`, ...). This alone prevents the new
   session from ever seeing "its own" name in `tmux ls` as a foreign leftover.
2. **When briefing any worker that might self-audit its environment, add an
   explicit guard**: "Do NOT run `tmux kill-session` for any reason, on any
   session, including ones that look like leftovers." Cheap insurance against
   a worker "cleaning up" its own supervisor process.

## Pitfall: "works interactively for me, wedges for the agent" — check hooks before blaming reasoning

When a spawned Claude Code (or similar) session looks alive but sits idle,
unable to submit or advance, and this happens ONLY when the agent launches it
(never when the human runs the same CLI interactively), don't default to
diagnosing a reasoning/over-thinking hang. First check the target repo's
`.claude/settings.json` for `PreToolUse`/`Stop`/`UserPromptSubmit` hooks that
shell out with a hardcoded OS-specific path — classic case: a Windows-authored
repo's hook does `. "$CLAUDE_PROJECT_DIR/venv/Scripts/activate"`, which doesn't
exist on macOS/Linux (`venv/bin/`). Effect: the `Stop` hook errors on every
turn-end, and/or a `PreToolUse` gate hard-blocks every Bash call with a message
telling the agent to use a path that literally can't exist on its OS — an
unwinnable instruction, so the session sits wedged no matter how many times
you nudge it. This explains "identical CLI, different outcome": the human's
interactive shell never goes through the agent-only PreToolUse gate check the
same way, or has the right venv already active.

Diagnose fast: `grep -n hook .claude/settings.json` in the target repo, then
hand-run the flagged hook script with a synthetic `tool_input` JSON on stdin
to see if it emits a block/error (e.g.
`echo '{"tool_name":"Bash","tool_input":{"command":"..."}}' | python .claude/scripts/hooks/on_pre_tool_use.py`).
Fix in the repo's own `.claude/` files, on a branch (never main) — this is a
repo config bug, not an orchestration or reasoning bug:
- Make hook shell commands try both venv layouts:
  `. "$DIR/venv/bin/activate" 2>/dev/null || . "$DIR/venv/Scripts/activate"`.
- Make any allow/deny marker list in the hook's own Python logic recognize
  both `venv/bin/...` and `venv/Scripts/...` forms, not just whichever the
  repo was originally authored under.
- Re-run the hook script standalone (as above) to confirm it now allows the
  cross-platform form before re-spawning the worker.

## Pitfall: extended-thinking stall (session alive, "thinking…" for minutes, zero tool calls) is a distinct failure mode from a dead/crashed session

Observed repeatedly across a single multi-unit implementation run (Sentinel v2
rebuild, 10+ units dispatched via `claude_orchestrate`): a session that is
genuinely alive (tmux pane active, pane text changing, `status.md` not stale)
can still sit "thinking…" / "almost done thinking…" for 5-6+ minutes producing
ZERO tool calls, ZERO file writes. This is NOT the same as the "session
crashed at `starting`" signature (empty tmux log, `outcome: null`) — the
process is running and burning tokens, just not converging to an action. It
recurred hardest on units perceived as high-stakes/ambiguous by the agent
(e.g. changing a function's signature while preserving backward compatibility
across 5 call sites) and on units where a loaded repo rule file
(`.claude/rules/*.md`) nudges the agent toward extra design contemplation
before acting.

Recovery sequence that worked, in order, escalating only when the prior step
fails:
1. `interrupt` (sends Esc) → `wait` a cycle. If it starts producing tool calls,
   done.
2. If still just thinking after the interrupt, `steer` with a concrete,
   unambiguous next action ("stop planning, write the file now — here is the
   exact content/spec") → `wait`.
3. **If it re-enters extended thinking a SECOND time after the steer** (i.e.
   interrupt+steer did not break the loop once already), stop retrying that
   session — `stop` it and have the supervisor write the file(s) directly with
   its own file tools, using the design doc's exact spec. The supervisor
   already read the full design doc to derive units; it usually has enough
   detail to hand-write one unit's code without another agent turn. This is
   faster and cheaper than a 3rd interrupt/steer cycle, and it stops burning
   the unit's iteration budget on a session that isn't producing output.
4. The same "stop retrying, take over directly" response applies to a session
   stuck re-reading the same single file for 10+ minutes with the pane frozen
   on "Reading 1 file…" and never completing — a live-but-hung read, not a
   crash. Kill it, don't wait out a 4th cycle.

## Pitfall: large single-file mechanical edits reliably poison a coding session's context

A unit that requires deleting/editing many blocks scattered through one very
large file (observed: a 3200+ line test file, deleting ~15 test classes tied to
removed functionality) is a specific trigger for BOTH the extended-thinking
stall above AND premature auto-compaction (context climbing to 77-94% from
repeated re-reads of the same large file). The failure mechanism: an
instruction phrased as "find and remove the old X tests" makes the agent
re-read the whole file (often more than once) to locate every occurrence,
which is what fills the context window and triggers the stall/compaction
cycle — not the edit itself, which is mechanically simple.

Mitigation: before dispatching this class of unit, have the supervisor run its
own `search_files`/`read_file` pass to enumerate the exact line ranges or
symbol/class names that need to go, and hand the session that concrete list
directly in the brief ("delete lines 2232-2520 covering classes
TestRequestDiff and TestValidateGenerationFix; keep test_layer_for_file_maps_*
and test_layer_rerun_fails_without_pythonpath which test a symbol that is NOT
being removed") instead of a "go find and remove ..." instruction. This
removes the re-read-to-locate step entirely. If a session already got wedged
on this class of edit and repeated interrupt/steer isn't converging, this is
also a good candidate for the supervisor to finish directly (via `patch`/
`execute_code` precise line-range deletion) rather than re-dispatching — the
supervisor doing its own line-range analysis to unblock a stuck delete-heavy
unit is a normal, low-risk supervisor action, not scope creep.

## Pattern: an external PR review lands mid-supervision — verify before steering, don't just relay it

While a supervised session (T2 or similar) is mid-flight on a long implementation
run, a human or a separately-run audit can drop a detailed review comment on the
PR the session already opened. Observed twice on the same PR in one session: the
second review caught real, critical defects that the session's own test suite
(250-300+ passing unit tests) and an earlier automated code-review pass both
missed — a downstream record object never actually receiving the field an
upstream stage produced (so a "verified fix" shipped as a structurally empty PR
via `git commit --allow-empty`), a designer appending to names that turned out to
be local variables scoped inside a function rather than module-level globals (so
the "wiring" was a silent no-op — `NameError` when actually imported/exec'd,
though nothing in the test suite ever did that), and a source-tree path computed
one directory level too shallow so "verification" silently ran against the
original unedited file. All three passed every existing test because those tests
asserted on the wrong thing (string presence instead of import/exec, a mocked
subprocess boundary, a same-directory fixture) rather than the real production
path — exactly the class of bug a live end-to-end run (not a hand-built unit
test) surfaces, which is why building a true end-to-end test alongside fixing
these findings compounds the value.

Don't relay such a review to the supervised session verbatim and call it done —
and don't dismiss it because "we already gated this PR" either. Do this instead,
BEFORE steering:
1. Read every cited file:line yourself against the CURRENT code (not the PR diff
   summary, not the reviewer's paraphrase). If the reviewer gave a reproduction
   command/snippet, re-run it independently.
2. Bucket findings into confirmed-true / confirmed-false / can't-verify and
   report the split back to the user before acting — don't silently filter.
3. Steer the supervised session with ONLY the confirmed-true findings, each with
   its file:line and a concrete fix direction (file-handoff discipline — point at
   findings, don't dump the reviewer's full prose into the steer message beyond
   what's needed to act on it).
4. This does not reset any review→fix round cap the session's own gate is
   tracking — it's an independent, human-triggered cycle layered on top. But
   note explicitly that once it recurs on the same PR, rising total round count
   is itself a signal worth naming (possible sign the implementation approach
   needs rethinking, not just another patch).
5. After the session reports the fixes done, insist on (or independently run)
   the FULL gate again — tests + review — not a spot-check of just the named
   lines. This class of bug (a value never threaded through, a name resolved at
   the wrong scope, a path off by one directory level) tends to recur at other
   call sites using the same pattern within the same PR; a review that finds one
   instance is a strong hint to grep for the same shape elsewhere.

## Pitfall: gate reports zero/empty diff when the worktree base is stale

A worktree created earlier for a task can sit N commits behind `origin/main` by
the time the implementation session finishes. `claude_orchestrate gate` (or any
diff-based check) walking `origin/main..HEAD` against the CURRENT `origin/main`
in that state can report an empty diff (comparing against a base that's already
ahead of the branch's actual fork point) or a polluted diff containing unrelated
files from the commits `origin/main` gained since the worktree was created —
easy to misattribute to the feature branch.

Diagnose in the worktree: `git log --oneline <branch>..origin/main` (any output
= behind) and `git diff origin/main..HEAD --stat` (unexpected files present?).
Fix by rebasing onto current `origin/main` — do not debug the gate/diff tooling
itself for what's actually a stale base:

```
git fetch origin
git rebase origin/main   # resolve conflicts if any
```

Re-run the test suite once after the rebase before trusting any gate/review
result from before it — treat the pre-rebase run as void.

> **Policy:** Claude Code must never run against the TrueFoundry gateway (pay-per-token `anthropic-primary` billing); a machine-wide managed hook and `claude_orchestrate` block it. Do not reuse a TF-gateway `ANTHROPIC_BASE_URL` for a Claude Code launch. The TF-gateway examples below are historical; launch Claude Code through `claude_orchestrate` with `model_provider=seatbelt` (or `fireworks`).

When launching a headless/interactive Claude Code CLI into a tmux pane for a
handoff (this skill's core pattern, applied to `claude` instead of `hermes
chat`), you can hit `Login: Expired — log in again` even though
`~/.claude/settings.json` has a working TrueFoundry-gateway config
(`ANTHROPIC_BASE_URL` + `ANTHROPIC_CUSTOM_HEADERS: "x-tfy-api-key: <key>"`).
That header is a **routing** credential, not an **auth** credential. Setting
`ANTHROPIC_AUTH_TOKEN` (or `ANTHROPIC_API_KEY`) to the same tfy key to try to
"fix" the expired login produces `401 anthropic error: Invalid bearer token`
and several silent retries before it surfaces — a plausible-looking guess that
wastes a full launch cycle. Likewise, don't probe gateway auth with
`claude --bare -p ...`: `--bare` skips loading `~/.claude/settings.json`
entirely (so `ANTHROPIC_CUSTOM_HEADERS` never applies) and the probe just
hangs against a request that can't route.

Correct handling:
1. Confirm the real state first: `claude auth status --text` (do this before
   touching any env var — it tells you definitively whether this is routing
   or auth).
2. A genuinely expired OAuth login has no non-interactive fix — it requires a
   human to complete `/login` (or `claude auth login --sso`) in the live
   session's browser flow. Surface this to the user immediately rather than
   iterating through credential-swap guesses; every other piece of the
   handoff (worktree, branch, task brief) can be fully staged and ready to
   fire the moment the human confirms login.
3. Do not lift a *deployed service's* own `ANTHROPIC_API_KEY` (found via SSH
   into a container, etc.) for local interactive use — it's scoped to that
   service's flow, not a general-purpose credential.

## Pattern: `clarify` tool returning empty/not rendering — don't block silently, don't spam the same call, escalate via kanban comment + direct notification

Observed repeatedly across one long T2-style supervision session (4+ separate
decision points: a design-review escalation, an AWS region/DNS choice, a mount-
mechanism decision, an OAuth/TLS trade-off) — `clarify` consistently returned an
empty response with no selection surfacing back, on every attempt including
retries. This is not a one-off transient hiccup; treat a SECOND empty `clarify`
response in the same session as confirmation the channel isn't rendering for the
user right now, not proof of a wrong question or a fluke worth retrying a third
time.

**Fallback that worked every time it was tried**, do this on the second empty
`clarify` response rather than continuing to call `clarify`:
1. Write the full decision (options, one-line consequence each, what you'll
   default to if unanswered) as a kanban comment on the task — durable, visible
   on the dashboard even if the chat channel is degraded.
2. Send a direct ping on the user's real notification channel (e.g. `hermes
   send -t telegram:<chat-id> -q "<decision needed + compact options>"`) — this
   is a different delivery path than the in-session `clarify` UI and reaches the
   user even when `clarify` itself is broken for this session.
3. Continue any genuinely unblocked work in parallel while holding on the
   blocking decision itself — don't idle the whole task waiting on one channel.
4. When the user's next message answers the decision (even a bare one-word/
   number reply like "3" with no other context), treat it as resolving the
   most recently posted decision set — don't re-ask for clarification on which
   decision it was answering unless truly ambiguous (more than one open
   decision pending at once).

This mirrors `tier2-orchestration`'s own escalation principle (send the decision
set, don't block silently) but that skill is protected from editing here — this
is the concrete channel-level workaround to pair with it whenever `clarify`
itself is the thing not working, independent of which orchestration skill
triggered the escalation.

## Pitfall: routing `claude` to a third-party Anthropic-compatible endpoint (Fireworks/Kimi K3, or similar) — cached OAuth silently overrides env-var routing

`claude_orchestrate`'s `model_provider` param (`seatbelt` default, `fireworks`
fallback; `truefoundry` is refused for the claude executor) exists because pointing the `claude` CLI at a non-Anthropic,
non-TF-gateway endpoint via plain env vars (`ANTHROPIC_BASE_URL`,
`ANTHROPIC_AUTH_TOKEN`) does NOT work reliably on a machine with an existing
Claude Code OAuth login — the cached OAuth state overrides env-based routing,
and the failure looks like a credential problem (401/403 from the target
provider) when it's actually a routing problem (the request never left for
that provider — proven by pointing `ANTHROPIC_BASE_URL` at a local echo
server that received zero requests, yet still got the target provider's 401).

Fix: isolate config via `CLAUDE_CONFIG_DIR` pointed at a fresh, persistent,
never-shared-with-the-OAuth-session directory (not `/tmp`) — a directory with
no `.claude.json`/keychain entry has nothing to override the env vars with.
Also: use `ANTHROPIC_AUTH_TOKEN` not `ANTHROPIC_API_KEY` for Bearer-auth
providers (Claude Code sends `API_KEY` as `x-api-key`, which Fireworks
rejects); never pass `--model <provider>/<path>` in interactive mode (it
truncates the path → 403 — set the model via `ANTHROPIC_MODEL` env instead,
which works in both print and interactive mode); and pre-seed `.claude.json`
onboarding/trust state in the fresh config dir so the first orchestrated
launch doesn't stall on a dialog `wait` can't dismiss. Full debugging detail,
Full debugging detail, verification recipe, and the header/model-flag gotchas:
archived `fireworks-kimi-k3-routing.md` note (not an active skill reference; verify the current tier skill instead).

## Pitfall: a Claude Code pane showing "sonnet" / a high context-% is a COSMETIC TUI display quirk, not proof the actual API call misrouted — verify the real destination before declaring a routing failure

Observed directly: during a `model_provider=truefoundry` design-author session, the tmux
pane displayed the model name as `sonnet` and climbed to 83%/200k context with repeated
auto-compaction, which was read (and reported to the user) as "it's routing to claude-sonnet's
200k window instead of Kimi K3's 1M." The user corrected this after the fact: the actual tool
calls WERE going out via the correct backend (fireworks) the whole time — the sonnet label and
the 83%/200k figure were the Claude Code TUI's own internal/cosmetic display assumption, not
evidence of where the request actually got routed. Conflating "what the pane displays" with
"what the request actually hit" produced a wrong root-cause claim that then had to be walked
back.

**Do not infer actual request routing from the pane's displayed model name or context-%
alone.** Those are the CLI's own internal bookkeeping/display and can be stale, wrong, or
simply not reflect the configured `model_provider`. Before reporting a routing failure (to the
user, or as the reason for restarting/switching engines), verify the REAL destination directly —
e.g. confirm `ANTHROPIC_BASE_URL`/`ANTHROPIC_CUSTOM_HEADERS`/`model_provider` actually in effect
for that process (`ps -p <pid> -o command` / the launched env), or point at independent evidence
the request landed at the intended provider (a probe call, a response field, or the provider's
own request log) — not just what the TUI prints. This does not invalidate the routing pitfall
above (`model_provider=truefoundry` really can silently default to sonnet-200k when `model` is
unset) — that failure mode is real and worth diagnosing when there's independent confirming
evidence (e.g. the session was later found stuck thrashing with no forward progress, or a probe
call confirmed the wrong endpoint). The lesson is narrower: a cosmetic pane reading alone is not
that evidence, and should not be cited as the root cause without corroboration.

**Recurred a second time in a later, unrelated session** — same exact shape
(pane showed `sonnet` + climbing context-%, reported as a real routing failure,
user corrected it as cosmetic) even with this pitfall already written down.
Once is a lesson to record; twice means the write-up alone doesn't stop the
mistake — add a concrete pre-claim check, not just a warning: before telling the
user "it routed to the wrong model/window," name what INDEPENDENT evidence you
have beyond the pane (a probe call's actual response, a `ps`-confirmed env var,
a provider-side log) — if you have none, say "the pane shows X, I haven't
independently confirmed it" instead of asserting a routing failure as fact.

**Recurred a THIRD time** — same exact shape (pane at "sonnet" + 83%/200k
climbing, hit the compaction thrash symptom, was written up in a task summary
as "routing/context-window mismatch" root cause, then corrected by the user
after the fact: the actual tool calls were going out via `fireworks`
correctly the whole session; the sonnet label and 83% figure were purely the
Claude Code TUI's own cosmetic bookkeeping). Two prior documented recurrences
did not prevent a third — the "add a pre-claim check" mitigation above is
necessary but insufficient as a standalone warning; it has to be enforced as a
hard gate, not a reminder to self-check. Concrete rule going forward: **treat
any claim of "it's routing to the wrong model / wrong context window" as
DRAFT until you've run the corroboration check, and only include it in a
status update, a kanban comment, or a summary to the user AFTER that check
passes.** If a task summary is being written under time pressure and the
check hasn't been run, either run it first or phrase the observation as "pane
displayed X, unconfirmed" — never state it as settled fact in anything the
user will read, even informally. Diagnosing a *genuinely* wedged/thrashing
session (compaction loop, no forward progress) is still legitimate and
independent of the model-name/context-% figure — interrupt/diagnose/fallback
on real stall symptoms regardless; just don't attribute the STALL's cause to
the displayed model/context-% without corroboration.

## Pitfall: mocked-class staticmethod delegation in a supervised session's own test work — a "no error, no effect" trap

When a T2/supervisor session (or a subagent it dispatched) writes a test that
patches a class with `unittest.mock.patch(...)` and then tries to delegate one
of that class's `@staticmethod`s to the REAL implementation so the test still
exercises real logic, assigning `mock_cls.method = staticmethod(real_fn)` is a
silent no-op: a `staticmethod` object sitting as a plain attribute on a
`MagicMock` has no class-level `__get__` binding to invoke it, so
`mock_cls.method(...)` just returns another MagicMock — no error, no
exception, and whatever the real function was supposed to mutate never
happens. The fix is to assign the ALREADY-UNWRAPPED plain function:
`mock_cls.method = RealClass.method` (accessing a `@staticmethod` via its
class already yields the plain function in Python 3.10+, so no explicit
unwrap/`.__func__` call is needed — trying `.__func__` on it will error since
it's no longer a descriptor at that point).

Symptom to recognize fast: an assertion checking "did the real logic run"
fails with the untouched default and NO traceback anywhere upstream — this
combination (silent, error-free non-execution) is the tell. Confirm by adding
a print inside the real function body; if it never fires, this is the cause.

## Recipe: relaying a T2's escalated design decision to the user — plain English first, jargon on request

When a supervised T2 hits its design-review round cap (or any other genuine human-decision gate) and reports back with a multi-paragraph technical writeup (competing concerns, named mechanisms, reviewer objections), do NOT relay that writeup verbatim as the first pass. Observed directly: after receiving a full technical dump on a mount-mechanism decision, Ayush asked "simplify the design decision for me" — the raw T2 report is the wrong default shape for a status update, even though it's exactly right to have in hand for follow-up detail.

Default shape when surfacing a T2 escalation:
1. One line on what's actually done (context, not the ask).
2. The decision reduced to the smallest number of named options with a one-clause consequence each, no library/mechanism jargon unless the user's own question implies they already know it.
3. Stop there and let the user answer. Do NOT pre-load a recommendation with full tradeoff prose unless they ask "what's better" or explicitly hand you the pick ("your call" / "I don't understand either, you pick") — at that point DO give the recommendation with reasoning (the existing "surface downsides too" preference still applies), but keep the explainer itself short and mechanism-first: name what each option actually IS in one clause ("X is the thing that makes the mount work at all, you need it regardless"; "Y is just the service babysitter — standard, working now, vs. Z which is flaky") before recommending.
4. Relay the user's answer back to the T2 verbatim as the instruction (with your own concrete elaboration of what it implies operationally), not a vague paraphrase — the T2 session needs the precise decision to act on, not your compressed summary of it.

This mirrors the existing "explain optional/cosmetic changes in plain English before asking" preference, but recurs specifically at T2 design-decision escalation points too — a technical infra decision (mount mechanism, region, rollout gate) gets the same simplify-first treatment as a cosmetic config choice.

## Pitfall: a genuinely hermetic E2E test for a real subprocess/QC/LLM pipeline is a multi-hour, multi-bug debugging path — not a one-shot write

Expect a predictable sequence of masking bugs (stale-module import caching,
subprocess env leakage, fixture format drift, wrong-shape fake stubs, missing
ledger emission). Full detail + fixes:
archived `e2e-testing-and-review-specialist-notes.md` note (not an active skill reference; verify the current tier skill instead).

## Pitfall: a subagent dispatched for "mechanical wiring" can silently write only tests, then go quiet, and look done

A subagent given a large wiring/refactor task can produce a comprehensive test
suite that passes — because it injects fakes for the exact seams it was
supposed to wire into production code — commit only that, and then stall or
return with the production diff still fully stubbed. Never accept "tests
pass" from a wiring subagent as proof the wiring happened: `git log`/`git
diff` its worktree yourself and grep the production files for the stub
markers you expect it to have removed (e.g. `qc_runner=None`, `emit=None`,
`llm=None`) before trusting the result.

## Pattern: a second/independent review often re-reports findings you're already mid-fix on — verify, don't restart

When a second review (a different reviewer, or the same reviewer re-run) lands
mid-supervision with findings that look new, diff them against your current
fix list and the LIVE worktree state (`git show`, `grep` for the fixed
pattern) before reacting. A review that reports the exact same blockers you
already patched is confirmation your fix is correct, not a signal to re-do the
work — and treating it as new work wastes a review/fix round for nothing.
Conversely, genuinely new findings from the same review should still go
through the normal "read every cited file:line against current code, bucket
confirmed/false/can't-verify" discipline described above before steering them
into the session.

## Pitfall: the TOP-LEVEL supervisor itself (not a spawned child) goes silent — empty responses after tool calls, repeatedly, late in a very long/deep session

Distinct from every stall/death pattern above (which are about CHILD sessions
spawned via `claude_orchestrate`/tmux) — the top-level agent driving the whole
supervision can itself start returning an EMPTY text response immediately after
executing tool calls, several turns in a row, very late in an exceptionally long
single conversation (observed: after a context-compaction event, 200+ tool calls,
and hitting the "maximum tool-calling iterations" cap earlier in the same
session). The user's exact nudge ("you just executed tool calls but returned an
empty response, please process the results and continue") repeated verbatim three
times in a row without producing a real response each time — simply repeating the
same generic nudge does not reliably break the loop once it starts.

There is no child session to `interrupt`/`steer`/`stop` here — the supervisor
*is* the wedged process. Since the affected agent cannot introspect why it went
empty, the recovery has to come from the OUTSIDE (the user or a fresh turn):
- Prefer a **narrow, single, concrete next action** over a generic "continue" —
  e.g. name the exact next command to run and what to do with its output, rather
  than "process the results above and continue," which gives the stuck agent
  nothing new to lock onto.
- If 2 identical generic nudges in a row both produce empty responses, stop
  repeating the same nudge a 3rd time — that's the same "attempt budget" lesson
  as the mock-patch corruption pitfall: a fix that didn't work once is unlikely to
  work unchanged the second time. Escalate to either (a) a much more specific
  single-step instruction, or (b) starting a fresh session/turn boundary
  (e.g. via context compaction or `/new`) that resumes from on-disk state
  (kanban task, ledger attachment, git log) rather than continuing to nudge the
  same degraded turn.
- This is more likely to surface very late in a single session that has already
  been through a context-compaction cycle and/or an iteration-cap warning earlier
  in the same conversation — treat those two events as leading indicators that
  the session is running unusually deep and may be more prone to this failure
  mode going forward, not just isolated past incidents.

## Pitfall: `claude_orchestrate executor=codex` exits instantly with no verdict — two distinct silent-launch causes (model id prefix, untrusted dir)

Confirmed directly during a T2 design-review loop: two Codex/Sol review sessions
launched via `claude_orchestrate start executor=codex model=<id>` exited within
seconds with an empty pane and no verdict/outcome file written — indistinguishable
at first glance from a claude-auth-down or credentials problem, but the real
causes were launch-configuration, not auth:

1. **Model id must be BARE, with no Hermes provider-group prefix.**
   `model=openai-group/gpt-5.6-sol` fails silently; `model=gpt-5.6-sol` works.
   `openai-group/` is the Hermes routing/provider-GROUP name (used elsewhere in
   Hermes model config), not a codex CLI model id — codex's own `-m` flag wants
   the bare id only. `tier2-orchestration`'s own Phase 1b.2 text still shows the
   prefixed (wrong) form as of this writing; it's a protected/manually-authored
   skill so it can't be patched here — treat that line as STALE and always strip
   the group prefix when launching codex, regardless of what any tier skill's
   embedded example shows.
2. **The workdir must be a git repo AND already codex-trusted.** Codex's TUI
   shows an interactive directory-trust prompt for any non-git or untrusted dir.
   `claude_orchestrate` drives codex via tmux `send-keys`, which cannot dismiss
   that trust menu (the prompt text just gets typed into the menu instead of
   selecting an option) — the session exits immediately, same empty-pane
   symptom as cause #1. Before first codex use in any scratch dir:
   ```bash
   cd <scratch-dir> && git init
   ```
   then either add a `[projects."<scratch-dir>"]` entry to `~/.codex/config.toml`,
   or run codex there once interactively (any path giving a real TTY) and accept
   the trust prompt manually so later non-interactive launches skip it.

Diagnosis order when a `claude_orchestrate`/codex session exits with a null
outcome: (a) check the model string for a provider-group prefix to strip; (b)
confirm the workdir is git-initialized and present in codex's trusted projects;
(c) only after ruling both out, investigate as a genuine auth/network issue
(e.g. probe `codex exec -m <bare-id> "test"` directly in the same dir for a
readable error instead of the send-keys-driven TUI).

**Third cause, distinct from both above: an "update available" TUI prompt on codex startup
eats the send-keys review brief.** Confirmed directly on a T2 design-review loop: after
ruling out both the model-prefix and directory-trust causes (a manual `codex exec` probe in
the same dir worked fine), the plugin-driven session STILL exited instantly. Root cause:
codex shows an interactive "a new version is available, update now?" dialog on launch in some
environments, and `claude_orchestrate`'s tmux `send-keys` (same limitation as the trust-prompt
case — it types text, it doesn't select a dialog option) gets consumed by that dialog instead
of reaching the actual review prompt, so the session exits with an empty pane and no verdict.
Symptom is identical to the other two causes (instant exit, null outcome) — check all three
in order rather than assuming it's whichever fixed it last time.

Fix: dismiss the update prompt once interactively in the same dir so codex stops showing it on
subsequent non-interactive launches. **Do this via a fresh probe in a SCRATCH dir first, not by
hand-editing `~/.codex/config.toml` while other codex sessions may be running.** That file is
SHARED and GLOBAL — an append that duplicates an existing key (e.g. re-adding an already-present
`[projects."<dir>"]` block) corrupts it for EVERY codex process, not just the one being debugged.
Observed directly: a duplicate-entry append broke every codex launch on the host, including an
already-running, healthy plugin review session on an unrelated task. If a review that was
working a moment ago suddenly starts exiting instantly right after touching
`~/.codex/config.toml`, suspect self-inflicted config corruption first — diff/view the file for
duplicate `[projects."..."]` or other duplicate keys before looking anywhere else.

**Third cause, distinct from both above: an "update available" TUI prompt on codex startup
eats the send-keys review brief.** Confirmed directly on a T2 design-review loop: after
ruling out both the model-prefix and directory-trust causes (a manual `codex exec` probe in
the same dir worked fine), the plugin-driven session STILL exited instantly. Root cause:
codex shows an interactive "a new version is available, update now?" dialog on launch in some
environments, and `claude_orchestrate`'s tmux `send-keys` (same limitation as the trust-prompt
case — it types text, it doesn't select a dialog option) gets consumed by that dialog instead
of reaching the actual review prompt, so the session exits with an empty pane and no verdict.
Symptom is identical to the other two causes (instant exit, null outcome) — you can't tell
which of the three you're hitting from the exit alone; check all three in order rather than
assuming it's whichever you fixed last time.

Fix: dismiss/pre-empt the update prompt once interactively in the same dir (accept or decline
it manually via a real TTY) so codex stops showing it on subsequent non-interactive launches,
the same pattern as pre-trusting a directory. **Do this via a fresh probe session in a SCRATCH
dir first, not by hand-editing `~/.codex/config.toml` while other codex sessions may be running
against it.** `~/.codex/config.toml` is a SHARED, GLOBAL file — any concurrent codex launch
(including live plugin-driven review sessions) reads it. An append that accidentally duplicates
an existing TOML key (e.g. re-adding a `[projects."<dir>"]` block that's already present)
corrupts the file for EVERY codex process reading it, not just the one you're debugging —
observed directly: a duplicate-entry append broke every codex launch on the host, including an
already-running, healthy plugin review session in a completely different task that had nothing
to do with the dir being edited. If a review/session that was working a moment ago suddenly
starts exiting instantly right after you touched `~/.codex/config.toml`, treat "I just corrupted
the shared config" as the first hypothesis, not a coincidental unrelated regression — diff/view
the file for duplicate `[projects."..."]` or other duplicate keys and remove the dup before
looking anywhere else.

## Pitfall: `.graphify/` doesn't propagate to a new `git worktree add` — seed it once, hooks are already shared

`.graphify/` is untracked, so a freshly created worktree (T2's per-unit implementation
worktree, or any manually created one) starts with NO graph even when the main repo has
one. Git hooks (`post-commit`/`post-checkout`/`post-merge`/`post-rewrite`) are the
opposite — they live in the main repo's `.git/hooks/` and are automatically shared across
ALL worktrees of that repo, so `graphify hook status` run inside a worktree already
reports all four installed; no per-worktree hook install step is needed or possible.

Seed a worktree's graph once, right after it's created, by copying the main repo's graph
as a baseline and letting `graphify update` reconcile it against the worktree's branch
diff — this is a cheap CP-copy + incremental pass, not a cold rebuild (seconds on a
25k+ node corpus, zero LLM cost with the `--no-description --no-label` flags):

```bash
MAIN_REPO=<main repo path>       # NOT the worktree
WT=<new worktree path>
if [ -d "$MAIN_REPO/.graphify" ] && [ ! -d "$WT/.graphify" ]; then
  cp -R "$MAIN_REPO/.graphify" "$WT/.graphify"
  rm -f "$WT/.graphify/branch.json" "$WT/.graphify/worktree.json" "$WT/.graphify/needs_update"
  (cd "$WT" && graphify update . --no-description --no-label --no-cluster >/dev/null 2>&1)
fi
```

After this one-time seed, the worktree's (shared) post-commit hook keeps its graph
current automatically on every commit inside that worktree — same as the main checkout.
Applies to any pre-existing worktree found with no `.graphify/`, not just ones a
supervisor creates itself: seed it the same way before pointing a coding session at it,
rather than letting it silently fall back to plain file reads.

## Pitfall: the supervisor's OWN shell `PYTHONPATH` (not the repo's `.envrc`) shadows a target repo's namespace packages during independent test verification

Distinct from the documented `.envrc`-clobbers-`PYTHONPATH` issue (that's the
TARGET repo's own direnv). This one is the SUPERVISOR's Hermes process itself:
the shell running `terminal()` calls has `PYTHONPATH=/Users/ayush/.hermes/hermes-agent`
exported (Hermes's own tooling), and when you `cd` into a target repo's test dir
and invoke `pytest`/`python` to independently verify a dispatched session's
claimed test results, that exported var can shadow same-named packages in the
target repo — observed concretely: `.claude/scripts/tools/` is a namespace
package, and with the polluted `PYTHONPATH` still exported, `import
tools.session` / `import tools.orchestrator` raised `ModuleNotFoundError` even
though the module plainly exists on disk. This produced a long, misleading
debugging detour (chasing what looked like a real regression / hung subprocess)
before the actual cause — the supervisor's own shell state, not the code under
test — was found.

**Symptom to recognize fast**: a test/import that the dispatched session itself
reported as passing fails ONLY when YOU (the supervisor) re-run it, with an
import error naming a package that visibly exists in the repo. Before treating
this as a real regression, check `echo $PYTHONPATH` in the same shell and strip
it for the verification run:

```bash
CLEAN_PP=$(echo "${PYTHONPATH:-}" | tr ':' '\n' | grep -v "hermes-agent" | grep -v "^$" | paste -sd: -)
cd <target-repo-test-dir> && PYTHONPATH="$CLEAN_PP" <venv>/bin/python -m pytest ...
```

or simply `PYTHONPATH="" <venv>/bin/python -m pytest ...` when you don't need
any of your own path entries for that invocation. Always verify a suspicious
independent-verification failure against a CLEAN env before concluding a
dispatched session's self-report was wrong or that a regression exists — this
false trail can eat many tool calls (repeated hangs, kills, isolation-narrowing)
before the real cause is checked.

**Related but separate pre-existing repo issues to recognize, not chase as
regressions** (same debugging session, different root causes — check both
before assuming your branch broke something):
- A tracked `mcp/` directory at a repo root can shadow the real MCP SDK package
  when pytest is invoked FROM that root (cwd lands on `sys.path`) — reproduces
  identically on the base branch, not something the branch introduced.
- A test file that hits real external network resources (S3/LLM API/DB) with no
  creds present can hang instead of cleanly erroring/skipping at collection or
  setup time, if its skip condition doesn't actually short-circuit before the
  first network call. Confirm by running that ONE file in isolation with the
  same missing creds — if it hangs alone too, it's pre-existing and unrelated,
  exclude it (`--ignore=<path>`) rather than debugging your branch.

**A dispatched worktree's OWN venv is not automatically the right env for
verification either** — if that venv was created fresh for the worktree
(rather than reusing the main repo's already-provisioned one), it may be
missing third-party deps the test suite needs (`boto3`, etc.), producing
another false failure. When a session's brief says "reuse the main repo's
venv," verification calls must use that SAME venv path, not
`<worktree>/venv/bin/python`.

**A test passing in isolation but failing in a full-suite run is a
test-isolation bug (shared/leaked state — a global counter, an env var, a
cached token, an unreset temp dir), not a flaky test to retry past.** Don't
weaken the assertion or mark it skip; find and fix the missing setup/teardown
reset. When handing this off to a fixer session, name the suspect shared-state
categories explicitly (module-level globals, unclosed file handles/locks, env
vars set but not restored) rather than a generic "fix this test" instruction.

A dispatched coding session that hits a patch-tool ambiguity (non-unique
`old_string`, stale context after a prior partial apply) and just retries the
same patch shape can leave the file with N duplicate copies of the same block
plus a syntactically broken tail (a stray closing brace, a `with` block whose
body never got filled in) — observed: 6-7 duplicate "capture the real
staticmethod" blocks stacked in one test function, with the actual test body
(the cron invocation + ledger-event collection) never present at all because
every retry re-added the SAME preamble instead of finishing the function.

Symptom to recognize: the supervised session reports "the file-mutation
verifier flagged my last patch didn't apply" or similar, then goes idle — this
is the session's own signal that it's stuck in a patch loop on already-corrupt
content, not a transient tool hiccup.

Recovery (supervisor does this directly, does not just re-steer the same
session to "try again"):
1. `read_file` the FULL affected region (not a snippet) to see the actual
   corruption shape — count duplicate blocks, find where the body actually
   diverges from what the surrounding code needs.
2. Identify what's structurally missing (often the meat of the function —
   the actual invocation/assertions — never got added because every fix
   attempt only ever touched the preamble).
3. `write_file`/`patch` a full clean replacement of the corrupted region in ONE
   shot — do not attempt an incremental patch against mangled content a 3rd
   time. Write the complete, correct region including the part that was never
   there.
4. Verify with a syntax check (`python -m py_compile <file>`) before re-running
   the test — a `py_compile` pass confirms the rewrite is structurally valid
   even before you know if the test logic itself passes.
5. Steer the session with what was fixed and why, so it doesn't re-diagnose
   from scratch or re-attempt the same failed patch shape on the next turn.

## Recipe: a commit pushed during a GitHub Actions outage can silently never get a CI run — check by SHA on recovery, not by branch/PR status

A `git push` that lands while GitHub Actions is degraded/down can succeed (the ref
updates fine — that's git, not Actions) while the workflow trigger itself is
dropped, with no error surfaced anywhere. `gh pr checks <pr>` and
`gh api .../commits/<branch>/check-runs` will look fine but are silently reporting
runs registered against an OLDER commit on the branch — they don't tell you "no
run exists for the current tip" on their own. Symptom: `gh pr checks` shows "1
pass" (looks healthy) but cross-checking `git log` HEAD against
`gh api repos/<owner>/<repo>/actions/runs?branch=<branch>` shows every returned
`workflow_runs[].head_sha` predates the actual PR tip.

Verification sequence on "GitHub is back, is CI actually running":
```bash
git log --format='%H' -1                       # the real current tip
gh api 'repos/<owner>/<repo>/actions/runs?branch=<branch>&per_page=10' \
  --jq '.workflow_runs[] | [.id, .name, .head_sha[:7], .status, .conclusion] | @tsv'
```
If no returned run's `head_sha` matches the current tip, CI never fired for that
commit — don't wait for it or re-poll hoping it appears. Force a fresh trigger:
```bash
git commit --allow-empty -m "ci: retrigger after GitHub Actions outage"
git push origin <branch>
```
then re-run the same verification query and confirm a new `in_progress` run
appears with `head_sha` matching the new tip before reporting "CI is running."
This is safe on any branch (empty commit, no content change) and is the correct
fix here — do not try to "reissue" or manually dispatch the existing (never-run)
workflow via `gh workflow run`, since there was never a run object for that SHA
to reissue.

## Pattern: user asks "is this genuinely needed" mid-PR — pressure-test your own added scope honestly, then cut it fast when confirmed

When the user pushes back on a PR's complexity ("i feel like we're
overcomplicating stuff here", "is it genuinely needed") after you've already
shipped an implementation, do not defend the existing scope by default. Re-derive
from the original incident: which parts of the fix actually address something
OBSERVED, and which parts are defense-in-depth for a risk that was never
triggered. State the honest split — "no, not strictly — fix 1 alone resolves
every observed incident; fix 2 is defense-in-depth and is the bulk of the
complexity" — even though you authored/shipped both. If the user agrees to cut,
steer the implementer to strip the unneeded part immediately (delete the files/
tests it added, restore the untouched files to the base branch, re-verify the
full test suite, update the PR title/body/commit to match the reduced scope) —
don't leave the stripped code behind commented-out or "just in case." This mirrors
the existing "surface downsides of a recommended option" preference, but applies
retroactively to scope you already built, not just to a live decision.

## Recipe: locating which orchestration session/task produced an existing PR or branch, and auditing its completeness

Given only a PR URL/number (no known `task_id`), reconstruct which supervised
session built it and whether it's actually done:

```bash
# 1. Get the PR's head branch
gh pr view <n> --repo <owner>/<repo> --json headRefName,body,mergeStateStatus --jq '.headRefName'

# 2. Find the worktree carrying that branch (checked out or orphaned)
git -C <main-repo> worktree list | grep <branch-name>

# 3. Find the claude_orchestrate task dir whose meta.json points at that worktree
for d in ~/.hermes/tasks/*/meta.json; do
  python3 -c "
import json
try:
    m = json.load(open('$d'))
    if '<branch-name>' in json.dumps(m) or '<worktree-path>' in json.dumps(m):
        print('$d', m)
except Exception: pass
"
done
```

Once found, `~/.hermes/tasks/<task_id>/outcome.md` and `status.md` give the
session's own completion claim — but verify independently, don't trust it
alone (per the "never trust an agent's self-report" principle):

```bash
git -C <worktree> fetch origin <base_branch>
git -C <worktree> rev-list --count HEAD..origin/<base_branch>   # how stale is the branch?
git -C <worktree> diff origin/<base_branch>...HEAD --stat        # what did it actually add?
gh pr checks <n> --repo <owner>/<repo>                            # CI state
```

A PR can be "code-complete per the design/outcome claim" while still being
N commits behind main (check for path conflicts — usually none if the diff
only touches files unique to this PR) and never having been live-fired (e.g.
a deploy workflow whose first real run only happens on merge to main). State
both facts plainly: code-complete vs. production-proven are different bars,
and which one the user's "is this complete" question is actually asking about
determines whether you say yes.

## Pitfall: don't assume a PR without a `claude_orchestrate` task came from the autonomous (T2) pipeline — check commit attribution before naming a resumable session

A `claude_orchestrate` task dir under `~/.hermes/tasks/<task_id>/` proves a
Claude Code session ran and wrote file contents in some worktree — it does
NOT prove that session is what produced the PR, or that resuming it
(`claude --resume <session_id>` in that worktree) is the right continuation
target. Observed directly: a task dir (`t2-script-gen-cicd`) existed and had
written 4 CI/CD files, but the PR's actual commits carried none of the
`Co-Authored-By: Claude` trailers the autonomous pipeline always leaves, and
the PR had zero bot comments/reviews — the session had reported "DONE,
nothing committed," and a HUMAN-DRIVEN Hermes session (T1-style: a person
chatting with Hermes, Hermes doing the SSM/AWS legwork, then committing the
Claude-written files under the user's own git identity) did the actual
commit/push/PR-open afterward. Naming the Claude Code session as "the session
to continue" in that case is wrong — continuing it only gets you back into
the file-authoring sub-step, not the orchestrating Hermes session that
actually drove the PR to existence and holds the fuller context.

**Attribution check — run both, in one call, before naming ANY session as
the continuation point:**

```bash
git -C <worktree-or-repo> log --format='%h | %an | %s%n%(trailers)' <base>..<pr-branch>
gh pr view <n> --repo <owner>/<repo> --json comments,reviews \
  --jq '[.comments[].author.login, .reviews[].author.login] | unique'
```

- Commits carrying `Co-Authored-By: Claude` trailers AND/OR bot-authored PR
  comments/reviews present → genuine T2 autonomous-pipeline PR. The
  `claude_orchestrate` task (or its underlying Claude Code session id, found
  under `~/.claude/projects/<mangled-worktree-path>/*.jsonl`) IS the right
  continuation target — resume with `claude --resume <session_id>` from that
  worktree.
- No Claude trailers, no bot activity, commits authored as the human user →
  T1-style flow (human-in-the-loop, Hermes doing legwork + orchestration, human
  identity on the commits). The right continuation target is the Hermes TUI/CLI
  session itself, NOT the Claude Code sub-session that only wrote file
  contents. Find it with `session_search(query="<task/feature keywords>")` —
  match on the actual work done (task_id string, filenames touched, AWS
  instance ids, SSM commands), not just the PR title — and resume with
  `hermes --continue <session_id>` (or `hermes chat --continue <session_id>`
  depending on installed CLI form). Confirm you found the RIGHT session by
  checking its bookend_start/bookend_end match the work in question, since
  `session_search` can return an unrelated session that happens to share
  keywords (e.g. an unrelated skill-audit session that only mentions the
  worktree name in passing).

Don't guess which case applies from the PR title or "no CI bot" alone — always
run the attribution check above first; giving the user the wrong resume target
(a dead-end sub-session vs. the actual driving session) wastes their next
message finding out it doesn't have the context they need.

## Pattern: T2's `pr-review-toolkit` review step needs a stateful-diff specialist that file-by-file review can't provide

A diff can pass every file-by-file specialist individually while the composed
STATE MACHINE across those files still deadlocks (failure-then-retry latch
never cleared, mid-flight config toggle, dual-writer desync) — none of the
per-file specialists enumerate transitions across the whole diff. A
`state-transition-reviewer` specialist was added to the `pr-review-toolkit`
plugin for this, but **confirmed NOT self-verifying**: even with the
conditional "include it if stateful cues present" instruction wired into the
review prompt, a review can still come back `approved` on a diff with a
textbook trigger cue (a `useRef`/status latch) and miss the exact bug the
specialist exists to catch. Require the verdict to include a literal
`state_transitions:` section when the diff carries a trigger cue — its
absence means the specialist didn't run, not that it ran clean. Full
detail: archived `e2e-testing-and-review-specialist-notes.md` note (not an active skill reference; verify the current tier skill instead).

## Pitfall: auditing a skill and its paired reference doc separately misses CROSS-document contradictions — check them against each other, not just each against reality

A tier skill (e.g. `tier2-orchestration`) and its paired reference doc (e.g.
`hermes-tiers-reference.md`) both describe the same mechanisms in prose, and
they drift independently — an audit that reads each file in isolation and
fixes staleness against current code/config can still leave the two files
actively contradicting each other on the same point. Confirmed concretely:
the skill said "tests and review run in PARALLEL, fail-fast on tests" while
the reference doc said "3.2 tests (fail-fast) → 3.3 review (parallel with
tests where possible)" — sequential language contradicting the skill's
explicit parallel model — and this survived at least one prior full-repo
audit pass untouched because that pass checked staleness (old model names,
dead Paperclip references) but never diffed the two documents' descriptions
of the SAME behavior against each other. Same pattern hit model attribution:
one file said the design author is "Claude/Opus" days after another file had
already been updated to kimi-k3.

When auditing a skill+reference-doc pair (or any two files that describe one
mechanism from two angles — e.g. a skill and its README, or two skills that
both reference a shared subsystem), add an explicit cross-document pass:
grep both files for the same key terms (gate order, model/effort per phase,
status transitions, board/repo bindings) and read the matched sections
side-by-side, not just each file top-to-bottom against its own internal
consistency. A "no staleness found" verdict on each file individually is not
proof the pair agrees with each other.

## Pitfall: ad-hoc verification scripts need the repo's own bootstrap module, not just sys.path.insert of the target file's directory

When a harness/reminder demands a standalone `hermes-verify-*.py` script exercising changed behavior directly (rather than the repo's real test suite), and the target module does a cross-tree runtime import that only resolves because the repo's own bootstrap entrypoint (e.g. `_bootstrap.py`) mutates `sys.path` as a side effect of being imported (e.g. `.claude/scripts/utils/auto_orchestrator.py` doing `from hooks.utils import register_session` — `hooks` isn't a real installed package, it only resolves after `_bootstrap` inserts the right sibling dirs) — plain `sys.path.insert(0, <module's own dir>)` in the verification script is NOT enough. It produces `ModuleNotFoundError: No module named 'hooks.utils'; 'hooks' is not a package`, which reads like a packaging bug in the target module but is actually a missing bootstrap step in the probe. Fix: `import _bootstrap` (or whatever the repo's equivalent side-effecting entrypoint is) BEFORE importing the target module in the verification script. Also run the probe through the repo's OWN venv python (not the ambient `python3`) since these utility modules often depend on packages (`filelock`, etc.) only installed there — running with a bare system python fails one level earlier with a `ModuleNotFoundError` on the dependency itself, a different failure than the bootstrap gap that can be misdiagnosed as the same thing if you don't check which import line actually raised. When in doubt, prefer running the repo's own test suite (already encodes the correct bootstrap/path/venv) over a hand-rolled probe, and only hand-roll when asserting something the suite doesn't cover.

## Pattern: staging/prod isolation validation — check every "watches a shared resource autonomously" mechanism for double-enablement, not just per-host lock correctness

When validating a migration by running a new host alongside the old one against a
shared backing store (a Drive mount, a shared DB, a shared queue), a bug class that
per-host testing structurally cannot catch: two hosts each independently watching
the SAME shared tree and taking autonomous action on it (an auto-orchestrator, a
watcher, a cron-like trigger) — even when each host's own local coordination state
(sessions.json, locks) is completely correct in isolation and never itself shared.
Symptom: duplicate work (two live sessions on the same logical unit), not a crash —
easy to miss unless specifically looked for, since every individual host's own
test suite stays green.

Fix shape (generalizes beyond any one stack): (1) gate the autonomous-action
mechanism so only ONE host role runs it against the shared tree (an explicit
role env var overriding the feature flag, not relying on the flag alone); (2)
make any cross-host coordination token host-aware (prefix with a host id) as
defense-in-depth even if the primary fix is (1); (3) add a startup assertion
that host-local state truly never resolves under the shared mount, so the
"local state / shared resource" separation can't silently regress later without
a hard failure. Full incident + code shape lives in `qc-dashboard-perf-triage`'s
archived `windows-migration-assessment.md` note (not an active skill reference; verify the current tier skill instead) ("Staging/prod isolation" section) —
read that for the concrete diff shape before re-deriving this from scratch on a
different shared-resource migration.

## Pattern: `orphan-reaper.py` is self-healing, not kill-only — check for auto-recovery before manually diagnosing a T2/T1 pane

`~/.hermes/scripts/orphan-reaper.py` (cron, every 30m, silent `no_agent`) does
NOT just reap idle sessions anymore. It first checks the pane for four specific
recoverable prompt states and auto-responds via `send-keys` BEFORE considering
a session idle enough to kill:

| Pane shows | Reaper action |
|---|---|
| Context-compaction prompt (`compact this conversation`, `/compact`) | sends "y" |
| `redacted_thinking ... cannot be modified` (Claude Code corruption bug) | targeted kill (not idle-kill) so the T2 supervisor's own recovery/respawn logic picks it back up |
| `/rate-limit-options` prompt | sends "1" (stop and wait for reset) |
| A bare `y/n`/`[y/N]` prompt at the input line | sends "y" |

Only if none of those match AND the pane shows no active-work marker AND no
`❯` waiting-for-steer prompt does it kill as genuinely idle. Practical effect
for a supervisor (T1/T2) reading this skill: if a spawned/child session looks
wedged on one of these EXACT prompt shapes, don't rush to
`interrupt`/`diagnose`/`stop`+respawn it yourself within the same ~30 min
window — the reaper may resolve it first. Only escalate to manual
intervention once you've confirmed (via `tmux capture-pane`) the prompt is
NOT one of the four shapes above, or it's still stuck well past a full cron
cycle. This does not change any of the death/stall pitfalls above (a genuinely
crashed process or a real extended-thinking stall still needs the documented
manual recovery) — it only adds an extra "wait one tick, it might self-heal"
check before assuming the worst on these four specific prompt patterns.

## Recipe: parking a PR mid-external-outage with a merge-only-on-explicit-signal steer, and running live post-merge verification yourself afterward

When a human-decision gate (Phase 4 merge approval) coincides with an external
outage (GitHub down) that also blocks CI, the right move is a single steer into
the supervising session that does ALL of the following at once, so it survives
being unattended for however long the outage lasts:
1. Stop actively pushing/rerunning CI (nothing will register during the outage —
   see the SHA-check recipe above).
2. If live E2E validation isn't feasible pre-merge (e.g. the repro environment is
   a deployed/hosted box, not the dev sandbox), have it add a "Post-merge
   verification" section to the PR body NOW with the exact concrete repro steps
   (specific commands, what to fingerprint/compare, what JSON field proves
   success) — do this before parking, not as an afterthought once merge happens.
3. PARK explicitly: no merge until the human says the literal go-ahead word. Name
   what "the word" unblocks (merge with a proper message per `pr-description-style`,
   wait for deploy, then execute the post-merge verification itself and report the
   evidence) so the parked session has the full unblock sequence queued, not just
   "wait."
4. Keep the kanban task in `review` throughout — don't let a parked-for-outage
   session drift its own status.

On recovery ("github should be up now, rerun the jobs"): re-verify CI is actually
attached to the current tip (recipe above) before declaring it "running" back to
the user — a stale "1 pass" reading during recovery is the single most likely
place to give a false-healthy status right after an outage.
