---
name: multi-round-review-convergence
description: "Judge whether a capped multi-round adversarial review loop (design review, code review, any author-vs-reviewer iteration with a hard round limit) has CONVERGED or DEADLOCKED at the limit, and what to do in each case. Use this whenever an orchestration skill (tier1-suborchestration, tier2-orchestration, or any future reviewer-loop) hits its round cap and must decide escalate-vs-accept. Complements those skills without editing them."
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Review, Multi-Agent, Design, Escalation]
    related_skills: [tier1-suborchestration, tier2-orchestration, requesting-code-review]
---

# Multi-round review convergence vs. deadlock

Orchestration skills that run an author↔reviewer loop (design-doc review,
code review) impose a hard round limit (commonly 3) to prevent infinite
looping. Hitting the limit is not one outcome — "still not `approved: yes`
after N rounds" splits into two very different situations, and the right
action differs:

## When the human pushes back on PR scope/complexity at the merge gate — decompose the diff against the issue text, don't just re-paste the PR body

Distinct from every reviewer-loop/wedge signature in this skill: once a PR is
up and sitting at the human merge gate (Phase 4 of `tier2-orchestration`), the
human reading it may ask "what does this actually do" or push back that it
"feels overcomplicated" — this is a request for a plainer decomposition, not
proof something is wrong, and not a request to re-surface the PR description
(they already read that).

Answer by:
1. Walking the diff file-by-file (cite line/file counts from `git show --stat`
   or `gh pr view --json files`) and tying each piece directly back to a
   specific sentence in the original issue/task body — this shows which part
   is the core fix vs. the larger of two coupled asks, instead of asserting
   the whole thing is necessary.
2. Naming disproportion plainly if it exists (e.g. "a ~200-line core fix plus
   a ~700-line secondary mechanism is the majority of this diff") rather than
   defending every line uniformly.
3. Ending with an explicit scope-cut option ("if you think part X is overkill,
   say so and I'll have it stripped down") rather than only justifying the
   current shape — let the human decide, don't pre-decide it's fine on their
   behalf.

Worked example (alpha-learn-content-gen #1421, GH-1415 Drive-pull-revert fix):
human asked "why does render_keys.py exist, feel like we're overcomplicating
this" on a PR combining (a) an `rclone --update` sync fix (~66 lines,
directly closes the reported revert bug) and (b) a new content-keyed render
provenance system (~700 lines incl. tests, the "additionally, dedup should
key on content" paragraph from the issue). Answer decomposed the diff stat by
file, mapped fix (a) to the bug report's core complaint and fix (b) to the
issue's own "additionally" ask, named (b) as the larger and more complex half
by line count, and explicitly offered to have it stripped down if the human
judged it unnecessary — rather than just repeating the PR's before/after
bullets, which the human had already read and found insufficiently plain.

## Convergence — safe to resolve without a human, without a further round

All of the following hold:
- The blocker **count is shrinking round-over-round** (e.g. 5 → 4 → 2), not
  flat or growing.
- The final round's residue is **narrow and mechanical** — an ordering/
  sequencing fix, a missing required attribute in IaC (e.g. a CloudFormation
  `DeletionPolicy` required by `resource import`), a config flag, a stop/start
  ordering correction. Not an architecture or approach question.
- The reviewer supplied an **exact prescribed fix** for each remaining item,
  and the author/reviewer are not in real disagreement about direction.

**Action:** apply the reviewer's exact fixes directly to the artifact
yourself (verified against source with the same rigor a review round would
use), then proceed past the gate — do not spend a 4th/Nth round, and do not
escalate something that has no real ambiguity left. Log what you changed and
why (e.g. as a comment/audit note) so the trail shows a human didn't rubber-
stamp it blind.

## Deadlock — escalate to a human

Any of the following:
- Blocker count is **flat or growing** round-over-round.
- The residue is **architectural** (a design-direction question), not
  mechanical.
- Author and reviewer **genuinely disagree** on approach, not just on
  execution detail.
- A blocking issue reflects ambiguity in the **task itself**, not the
  artifact — no amount of doc/code revision resolves it without a human
  decision.

**Action:** stop looping at the round limit. Escalate with the latest
artifact + the outstanding blocking issues, framed so the human can make the
one decision that's actually needed (not a re-run of the whole review).

## Do not conflate the signal

Do not treat "not yet `approved: yes`" alone as deadlock — read the *trend*
across rounds (shrinking vs. flat/growing) and the *nature* of the residue
(mechanical vs. architectural), not just the final verdict string.

## Mixed/plateaued trend across rounds — weight the LAST round's residue nature over the raw count trajectory

The convergence/deadlock split above assumes a clean monotonic trend (5→4→2
or flat/growing). Real loops don't always cooperate: a trajectory like 3→3→2
(flat, then shrinking) is neither cleanly "shrinking round-over-round" nor
cleanly "flat or growing" — don't average the three numbers or eyeball the net
direction (3→2 "looks like progress") to decide. At the round cap, what
actually matters is whether the FINAL round's specific residue meets the
convergence bar on its own: narrow+mechanical, with an exact prescribed fix,
no real author/reviewer disagreement on direction. If the last round's
blockers are still framed as "define X" / "make this path do Y or
centralize Z" — i.e. still asking for a design/interface decision, not
handing you a drop-in patch — that's deadlock-shaped residue regardless of how
the raw count moved to get there, and the mid-loop plateau (round 1→2 flat)
was itself an early tell the loop wasn't converging cleanly even before the
cap hit.

**Worked example** (alpha-learn-content-gen t_6b3d3137, failure-class-aware
regen routing, needs-design=YES, 3-round cap): blocker counts ran 3→3→2.
Round 3's two survivors were (a) a paired-adoption/PNG-commit invariant broken
on a specific code path, prescribed fix given as an either/or ("make this path
explicitly verify-only, OR centralize paired PNG commit after every adopted
mutation") — a real design choice, not a single determined patch; and (b) a
promised manifest data channel with literally no field to carry it
(`SVGRegenerator` returns only `str | None`), prescribed fix again either/or
("define a structured regenerator result or explicit prompt-history
channel"). Both are genuine, specific, and well-diagnosed, but both still
require the design author to pick a direction — not apply a reviewer-supplied
patch. Treated as deadlock, escalated via `hermes kanban block --kind
needs_input` + a direct Telegram ping, framing the two survivors explicitly as
"plumbing/interface issues, not conceptual" (distinguishing them from a
from-scratch architecture rethink) so the human's decision is narrow and fast
even though the loop didn't resolve.

## Mixed residue at the cap — classify each blocker separately, don't treat the round as monolithic

A round can be deadlock BY TREND (flat/growing blocker count) while still
containing blockers of very different validity. Don't draft the escalation
from the raw blocker list as if every item carries equal weight — classify
each one first:

- **Goalpost-moving, not a defect:** the reviewer demands a stronger guarantee
  than the task's own stated acceptance criteria. Tell: restate the design's
  own contract for that mechanism and compare it word-for-word against what
  the task asked for. If they match, the reviewer is asking for more than the
  task requires (often something unprovable — e.g. "prove a best-effort
  detached warm always completes before every read" when the task only asked
  the cold path be "absorbed," which by construction admits an occasional slow
  read). Flag it in the escalation as "matches task acceptance, not a real
  gap" — don't present it as equally blocking.
- **Genuine, real gap:** the reviewer is pointing at an actual design choice
  the author made that trades off a real property (concurrency safety,
  correctness, data loss) the task or its context plausibly cares about, even
  if the author didn't call it out as a known tradeoff. This is the one that
  needs an actual human decision.

Frame the escalation around the genuinely-ambiguous item(s) with a clear
recommended default (state your own read, don't just dump both sides), and
name the spurious item(s) explicitly as "reviewer exceeded task acceptance" so
the human isn't re-litigating something already settled. This keeps a capped,
flat-trend deadlock answerable in one human reply instead of requiring them to
re-derive the review transcript themselves.

**Worked example** (Windows EC2 Drive-mount migration, t_fdf9cc90, 3-round cap):
round 3 verdict was flat at 2 blockers vs. round 2's 2 (not shrinking →
deadlock by trend). Blocker 1 ("prewarm remains racy," demanding proof a
detached best-effort cache-warm completes before every first read) asked for
more than the design's own accepted contract ("worst case: one slow first read
per cache-expiry window, off the hook's critical path") — which is exactly
what the task asked pre-warm to do (absorb the cold walk, not eliminate every
possible slow read). Blocker 2 (the mounted warm path takes no lock on a
shared-write tree) was a genuine, real design gap the author had made a
deliberate but debatable call on. The supervisor split them, recommended
accepting the design with a small amendment for blocker 2 only, and escalated
with an explicit lettered-options menu rather than the raw verdict text.

## `clarify()` can silently no-op — don't loop it, fall back to a durable channel

Observed twice in the same escalation: `clarify()` returned successfully (no
error) with `user_response` empty — the question apparently never rendered on
the user's client. Retrying an identical `clarify()` call a second time
reproduced the exact same empty result. Treat two empty returns in a row as
the CHANNEL failing, not as "the user is still thinking" — a third identical
retry is very unlikely to behave differently.

**Fallback the moment this happens:** put the decision on a durable,
independently-checkable surface instead of the interactive question:
1. `hermes kanban block --kind needs_input <task_id> "<the exact question +
   options, spelled out>"` — persists on the dashboard, survives session
   restarts, doesn't depend on the chat UI rendering correctly.
2. A direct out-of-band ping on the user's actual configured notification
   channel (e.g. `hermes send -t telegram:<chat_id> -q "<question +
   options>"`) so they see it even if they're not watching this session.
3. Stop the turn. Wait for the response to arrive via the kanban comment or
   the messaging channel — do not re-issue `clarify()` a third time, and do
   not guess an answer to keep moving just because the interactive channel is
   unavailable.

This is the delivery mechanism for the "Deadlock — escalate to a human"
guidance above, not a replacement for it — that section says WHAT to put in
the escalation; this section is HOW to make sure it actually reaches the
human when the primary interactive-question tool fails silently.

## Same discipline applies to a single-round `quality: approved` verdict with a minor finding

The convergence pattern above (narrow/mechanical residue with an exact
prescribed fix → apply and move on, no extra round) isn't limited to a
multi-round loop hitting its cap — it applies just as directly to a
**single-round** review that already returned `quality: approved` but flags
one minor, non-blocking finding (e.g. a dead/unused constant left over from an
unimplemented optional code path). Fix it yourself, amend into the existing
commit, and proceed straight to push/PR — don't spin a second review round or
a `requesting-code-review` auto-fix cycle for a finding the reviewer already
scoped as non-blocking. Reserve another round for findings that actually
failed `spec`/`quality`.

## Worked example

ALP article-generation Linux→Windows-COM migration design (Claude-Opus author,
Codex/Sol reviewer, cross-engine, 3-round cap):
- Round 1: 5 blockers (StatusStore return-type mismatch, render-producer IAM
  left optional, invalid CFN queue-ownership transfer, under-specified
  cancellation, single-consumer discipline unenforceable).
- Round 2: 4 blockers (1 confirmed resolved from round 1; 2 were refinements
  of round-1 issues the fix didn't fully close; 2 were genuinely new — a
  missing 4th CFN parameter, a Win32 Job-Object handle-lifetime bug).
- Round 3: 2 blockers, both narrow and each with an exact reviewer-prescribed
  fix — (a) disabling a control Lambda doesn't stop an already-running
  consumer's receive loop (fix: stop-first + `ec2 wait instance-stopped`
  before relying on redelivery), (b) CloudFormation resource import requires
  `DeletionPolicy` on every imported resource (fix: add `DeletionPolicy:
  Retain` to the two queue resources in the target template).

Shrinking count (5→4→2), narrow/mechanical residue, exact prescribed fixes,
no direction disagreement → **convergence**. The orchestrating session
applied both fixes directly to the design doc and proceeded to store/hand-off
rather than opening a 4th round or escalating.

## No-push / local-merge exit variant (tier2)

Some Tier-2 briefs explicitly forbid pushing or opening a PR for the run (e.g.
a scoped multi-unit build meant to land as local commits on a base branch,
reviewed by the human before any PR exists). This isn't a review-convergence
question, but it's the same class of "gate passed, now what does Phase 4 mean"
decision this skill already governs: when the brief says no push/no PR,
substitute a **local merge to the base branch per unit** (`git merge
--ff-only`) for the push+PR step, and treat the human gate as "post the
composite verdict (all units, commits, review confidences) as a comment,
then stop" — never push or open a PR under an explicit no-push constraint
just because the gate passed. Confirm with the human before promoting to a
push/PR flow.

## Ledger/bookkeeping drift is a different failure mode than round-limit deadlock

Don't confuse "reviewer loop hit its round cap" (this skill's main subject)
with "the orchestrator's own bookkeeping (a Paperclip ledger, a status file)
disagrees with the artifact's real state" — e.g. a `tier2-orchestration`
ledger showing units `pending` when `git log` shows them already committed
and merged on the branch, with no explanation of who/what advanced it.

That is not a review deadlock and has no round count to read a trend from.
Treat it as ground-truth-vs-bookkeeping desync: read the real diff for every
commit past your last verified point, check it against spec yourself, run the
real test suite, and only then rewrite the bookkeeping to match — do not
discard the work (it may be correct) and do not accept it uninspected just
because it exists and looks plausible (it may not be). This applies the same
"never trust a self-report, verify with real evidence" discipline this skill
already assumes for reviewer verdicts, just aimed at the ledger itself instead
of at a reviewer's `approved: yes/no`. See
`references/ledger-branch-drift-recovery.md` for the step-by-step recovery
procedure and a worked example (LEA-4 Tier-2 run, units 9-11 landed on the
branch with the ledger reset to all-`pending`).

## Verify the brief's target component before designing/dispatching — a behavior-described brief can name the wrong concrete subsystem

Distinct from every wedge/lock/CI-verification issue above, and earlier in the
pipeline than any of them: a build brief written from a user-observed symptom
("orchestrator session spawns aren't reliable, spawned sessions don't
un-archive") rather than an exact file:line can point Tier-2 at the wrong
concrete component when the codebase has multiple similarly-purposed
subsystems. Observed (alpha-learn-content-gen, t_280d7841): the brief said
"audit and fix the orchestrator session-spawn reliability" with a referenced
path that turned out to be a naming near-miss (`lesson_qc_auto_checker` vs the
real `lesson-qc-auto-checker`, underscores vs hyphens). Tier-2 designed,
implemented, reviewed, and opened a full PR (#1261) against the **trigger-based
headless auto-orchestrator** (`auto_orchestrator.py`) — a real component that
plausibly matched the brief's words — while the actual target was a
completely separate path: the **interactive `__orchestrator__` dashboard chat
session** a developer drives manually, whose `spawn-fix-sessions` output is
materialized into fresh lesson chats by frontend JS (`chats.js`/`chat.js`).
Both went through a full gate (impl+tests+review, CI green) before the human
caught the mismatch — expensive, because the entire cycle had to be redone
against the correct component (PR closed, worktree/branch discarded, fresh
design+implementation+review+PR against the right files).

**The tell was already visible early and was not treated as a stop signal:**
the brief's referenced path (`lesson_qc_auto_checker`, underscores) did not
exist verbatim in the repo (real dir is `lesson-qc-auto-checker`, hyphens).
Tier-2 correctly noticed the mismatch, but resolved it by fuzzy-matching to
the nearest similarly-named real file/module rather than treating "the brief's
own path reference is wrong" as evidence the whole named-component identification
might be wrong, and re-deriving the target from the user-observable symptom
instead.

**Fix — before writing the design doc or dispatching anything:**
1. If a brief's referenced path doesn't exist verbatim, do not silently
   substitute the nearest-sounding real path and proceed. Treat it as a signal
   to re-derive the target from the symptom, not just fix the path string.
2. Trace the exact user-observable surface the brief describes (which UI, which
   trigger, which literal action a human takes) forward to its source in code,
   rather than pattern-matching the brief's prose/keywords to whichever file
   sounds closest. "Session spawn" can mean a cron/trigger-driven headless
   process AND a manually-opened interactive dashboard session in the same
   codebase — these are typically fully separate modules with separate tests,
   separate call paths, and no shared code, so getting the wrong one produces
   a diff that looks completely legitimate (compiles, passes its own tests,
   reviews clean) while doing nothing for the reported problem.
3. When two candidate components both plausibly fit the brief's wording and the
   brief itself doesn't disambiguate (no exact file:line, no stack trace, no
   screenshot of which UI surface), that ambiguity is worth a cheap check-in
   with the human BEFORE the design doc — cheaper than a full
   design→implement→gate→PR cycle discovered wrong only at human review.
4. This is a `tier2-orchestration` Phase 1 gap: step 6 (read the design doc /
   write the brief file) should include a target-verification pass — confirm
   the brief's named component is the one that actually owns the reported
   symptom's user-observable surface, not just that the referenced path can be
   made to resolve to *some* real file.

## Redundant spawn detection (before you even get to a review loop)

Before spawning a Tier-2 (or any per-issue supervisor) session, check whether
one already exists for that issue: `tmux ls | grep <session-name-pattern>` AND
`gh pr list`/`gh pr view` for a PR tied to the issue. `tmux new-session -d -s
<name>` does **not** error on a name collision — it silently attaches to the
existing session instead. If you spawn against a name that's already running
(or already finished), your brief lands as fresh input into an
already-working or already-completed session rather than starting a new one —
redundant at best, confusing mid-task interference at worst.

Detect this after the fact: compare the session's reported wall-clock/token
count against your own spawn time. A large mismatch (e.g. the pane shows "1h
5m" of work seconds after you just issued the spawn) means you attached to a
pre-existing session, not a fresh one — go verify what it already produced
(PR, ledger doc) instead of re-briefing it or assuming your instructions were
ignored.

## Verify a subordinate session's self-reported PR/CI state independently

Never propagate a subordinate session's (T2's) self-reported "CI green" /
"check X is non-blocking" into an upstream status report or a merge-adjacent
decision without an independent check. A self-report is a claim, same as a
reviewer's "looks good" — same discipline as the ledger-drift section above,
aimed at CI/PR state instead of ledger state:

1. Resolve the PR's real current head (`gh pr view <n> --json headRefOid`),
   not the branch tip you assume.
2. Query check-runs and commit-status for THAT sha directly
   (`commits/{sha}/check-runs`, `commits/{sha}/status`) rather than trusting
   `gh pr checks` alone — an external status (e.g. Semgrep) posted against an
   earlier commit and never re-posted after later fix commits reads as a
   current failure but is stale. `state:pending` + empty `statuses` on the
   real head, while `gh pr checks` still shows an old `fail`, confirms staleness.
3. Check whether the base branch even has required-check branch protection
   (`branches/{base}/protection` — a 404 means none configured, so nothing
   mechanically blocks a merge; the gate is human judgment only).
4. Corroborate PR provenance against the accepted design by content, not
   title/branch-name similarity — match named components/fixes from the
   design's blocking-issue list against the PR body.

See `references/pr-ci-verification.md` for the exact commands.

## Wedged review session (high-effort-thinking loop) — recognize and unwedge

A distinct failure mode from round-limit deadlock: a single review round's
**session itself** gets stuck mid-turn in sustained high-effort deliberation
and never emits a verdict, even though the diff under review is small (seen
on diffs from ~2 to ~80 lines). Symptom: `status.md` stays `investigating`,
the tmux pane shows a "thinking with high effort" / "Xm elapsed" spinner with
no new tool calls, and this persists well past what the diff size justifies
(seen: 10-40+ minutes on trivial diffs). This is not deadlock between rounds —
it's one round's session failing to converge to output at all. First observed
3-for-3 across separate review rounds in a single Tier-2 build (ALP-1/#1108),
all on a Claude Code review session. **Correction: this is NOT Claude-exclusive**
— a later Tier-1 design review (ALP-3/#1241) hit the identical pattern on a
**Codex reviewer** (`openai-group/gpt-5.6-sol`): 300+s stalled reading code, then
after an interrupt it stated its verdict conclusion in the pane ("the design is
not safe to implement as written") but kept re-entering the thinking loop
instead of writing the file, requiring **three separate interrupt cycles**
before the verdict file finally appeared. Treat this as a cross-engine failure
mode, not an engine-specific one — apply the same recovery to either author or
reviewer, either engine.

**A plain `claude_orchestrate steer` message often does not fix it, and can
fail in TWO different ways** — (a) if the session is mid-turn inside its own
thinking, the steer gets silently queued ("queued for next turn") and never
delivered until that turn ends on its own, which may never happen; (b) even
after a successful `interrupt` leaves the session idle-at-prompt, a `steer`
call can paste the message into the input line WITHOUT submitting it — the
text is visibly sitting at the prompt but Enter was never sent, so the
session just sits there. Always verify with a pane check after `steer`;
if the message is visible but unconsumed, submit it explicitly:
`terminal(command="tmux send-keys -t <task_id> Enter")`, then `wait` again.
Don't assume `steer` delivered the turn just because the call returned ok.

**Recovery procedure (works reliably):**
1. Send `Escape` directly to the session's tmux pane (`tmux send-keys -t
   <session> Escape`) to interrupt the in-flight turn. This is more forceful
   than `steer` and actually breaks the loop.
2. Immediately follow with an explicit, directive instruction (via `steer` or
   `tmux send-keys -l "..."` + Enter): "Write your verdict to <verdict-path>
   NOW using what you already concluded (spec/quality/confidence/findings). Do
   not investigate further. Then set status complete + write DONE to your
   outcome file."
3. Verify with a pane check that the steer text was actually submitted (not
   just pasted) — if it's sitting unsent at the prompt, send a bare Enter.
4. If it's still stalled after another minute or two, repeat step 1-3 once —
   it can take two to three Escape+nudge cycles (observed 3 on a Codex
   reviewer in ALP-3).
5. Verify the verdict file actually appeared before trusting `status=complete`
   — don't assume the nudge worked just because the pane looks idle.

In every observed case the model had already reached a real, usable
conclusion before wedging — the interrupt did not degrade review quality, it
just stopped unproductive re-deliberation.

**Don't wait passively for `stall_seconds` to fire.** A review session that's
been in `investigating` for ~10+ minutes with a static/repeating pane and no
new tool-use is a candidate for this treatment even before the stall timeout
elapses — actively poll and apply Escape+nudge rather than trusting the
orchestrating supervisor's own stall detection to catch it (the supervisor's
`steer`-based nudge can itself get swallowed per the caveat above).

**Prevent it, don't just recover from it.** The root trigger is almost always
default `high`/`max` reasoning effort on a task that doesn't need it —
structured-verdict reviews and bounded design docs rarely require deep
multi-step deliberation. If your `claude_orchestrate start` call supports an
`effort` param, launch review/design sessions with `effort=medium` up front;
this alone eliminates most wedges before they happen (observed: eliminated the
3-for-3 recurrence on the repo where this was first found). Reserve
`Escape`+nudge (or a plugin `interrupt` action, if available) for sessions
already wedged, and a non-destructive `diagnose`/pane-dump action (if
available) to capture evidence *before* killing a hung session — future
root-causing needs the pane+log+state snapshot, and killing first destroys it.

## Bash-hook error loop — a DIFFERENT wedge signature, do not apply the think-loop fix

The high-effort-thinking wedge above (Escape+nudge, `effort=medium`) fixes a
session stuck deliberating with no tool calls. There is a **second, unrelated**
wedge signature that looks superficially similar (session `stalled`, no verdict
file appears) but has a different cause and needs a different response:
repeated `PreToolUse:Bash hook error` / `PostToolUse:Bash hook error` lines on
every single tool call, degrading into `API error · Retrying in 0s` retries.
Root cause observed: a `.claude/`-level hook (from CLAUDE.md/settings, inherited
from the repo or a parent dir) invokes a hardcoded OS-specific path — e.g.
`venv/Scripts/activate` (Windows) — while the session is actually running in a
macOS/Linux worktree. The hook fails before/after every tool call and the
session can never produce real output, no matter how long you wait.

**Escape/`interrupt` does NOT fix this** — it's not mid-turn deliberation, so
interrupting just clears the current attempt and the identical hook error
fires again on the very next tool call. Spending an interrupt-and-retry cycle
on this wastes time without changing the outcome.

**Recognize it by the signature, not by the stall duration:** repeated
`hook error` lines in the pane, especially referencing a path that doesn't
match the host OS (a Windows-style `Scripts/activate` on a Mac/Linux box, or
vice versa). The moment you see this pattern, skip straight to: `stop` the
session and re-run that step with a different executor (Codex instead of
Claude, or fall back to a `delegate_task` specialist-reviewer batch per the
`requesting-code-review` skill) — neither of which runs Claude Code's own Bash
hooks. Fixing the hook's activation path for the host OS is the durable fix if
you control that config; the executor swap is the immediate unblock when you
don't (e.g. reviewing someone else's worktree/repo state).

## Sub-agents-done-but-no-verdict-file wandering — a THIRD wedge signature, distinct from both above

The two wedge signatures already documented (high-effort-thinking loop with
zero tool calls; Bash-hook error loop with repeated hook-error lines) don't
cover this one: a `/pr-review-toolkit:review-pr`-style session where the
sub-agents it dispatched (`code-reviewer`, `pr-test-analyzer`, etc.) all
report "Done" — pane literally shows "N agents finished ... Done" for each —
and yet the top-level session never writes the verdict file you asked for.
Instead it keeps "Wandering… (Nm Ns · thinking with medium effort)" while
issuing REAL tool calls (re-reading the same source lines, re-running the
project's test suite a second time) to re-verify a finding its sub-agent
already reported. This reproduced at `effort=medium`, so it's not simply "use
medium effort" fixing it the way it fixes the pure think-loop wedge — the
session has genuine tool activity, so `stall_seconds`-based stall detection
may not even fire, and `Escape`/interrupt is the wrong tool for the same
reason it's wrong for the bash-hook case: there's no single stuck turn to
break, it just resumes the same re-verification pattern on the next turn.

**Recognize it by this exact combination:** (a) sub-agent summary lines in
the pane show every dispatched reviewer as finished/Done, (b) the requested
output file does not exist on disk, (c) the pane shows continuing REAL tool
calls (shell commands, file reads) rather than a static thinking spinner or
repeated hook-error lines.

**Fix:** ONE `steer` telling it explicitly that the sub-agents already
finished, to stop re-verifying, and to write the verdict file NOW from the
results it already has (restate the exact path/format). `wait` once more
(~180s is enough — it's a short write, not more investigation). If the file
still isn't there after that single cycle, `stop` the session immediately —
a second steer reliably reproduces the same wander rather than resolving it —
and fall back to a non-CLI reviewer path (e.g. the `requesting-code-review`
skill's `delegate_task` specialist batch: code-reviewer, pr-test-analyzer,
silent-failure-hunter run in parallel on the raw diff). While that fallback
batch runs, do your own quick spec-compliance read of the diff yourself —
cheap insurance, and it often resolves the one substantive risk before the
subagents report back anyway.

## Background sub-agents that never complete within a sane time cap — a FOURTH wedge signature, distinct from "done but no verdict"

Distinct from the "sub-agents-done-but-no-verdict-file wandering" section
above (which requires the sub-agents to have already reported Done): this is
the case where the dispatched sub-agents (`code-reviewer`,
`silent-failure-hunter`, etc. from `/pr-review-toolkit:review-pr`) themselves
never finish — the pane shows their live elapsed time and token count
climbing indefinitely (e.g. `11m 28s · 73.6k tokens`, `11m 9s · 95.6k tokens`)
with no completion, while the top-level session sits idle just polling for
their result. Observed on a chat-status-dot fix review (t_cea60b98): both
`code-reviewer` and `silent-failure-hunter` ran past 11 minutes with token
counts still increasing, never returning.

**Don't treat this as the high-effort-thinking wedge** — `interrupt` (Esc)
targets the TOP-LEVEL session's own turn, but the top-level session isn't
stuck thinking, it's correctly (if uselessly) waiting on background tasks
that are the actual hang. Interrupting it just re-enters the same "waiting
for N background agents" loop on the next turn — confirmed: 3 separate
`steer` attempts (including one paired with `interrupt`) each got a polite
acknowledgment ("Understood — I'll continue waiting...") and then resumed
identical waiting behavior, wasting 3 full poll cycles (~10 min) before the
session was given up on.

**Time-box the sub-agents' own elapsed time, not the top-level session's
`stall_seconds`.** The pane literally shows each sub-agent's live duration —
read it. If any sub-agent exceeds roughly 10-12 minutes of its OWN elapsed
time with no completion, that round has failed; don't wait for
`claude_orchestrate`'s stall detection (which watches the top-level session's
status.md/outcome, and won't fire if that session is "working" by virtue of
polling, even though the real work is stuck).

**Don't spend more than ONE steer/interrupt cycle trying to unwedge this.**
Because the top-level session is correctly blocked (not confused), asking it
again to "stop waiting and compile from partial results" tends to produce the
same polite non-compliance every time — it's designed to wait for those
agents and a single nudge rarely overrides that. After one attempt, `stop`
the whole review session immediately and fall back to the
`requesting-code-review` skill's `delegate_task` specialist-reviewer batch on
the raw diff (glm-5p2) — don't burn further turns coaxing a verdict out of a
session whose actual bottleneck (the hung sub-agents) you have no lever over.

## Dead T2 session with uncommitted-but-complete work in the worktree — recover directly, don't respawn blind

A distinct failure mode from every wedge signature above (which are all about a
LIVE session stuck/looping) and from the ledger/bookkeeping-drift section above
(which is about a live git history the ledger disagrees with): here the T2
supervisor session **is gone entirely** — no tmux pane, no process — and the
kanban task has silently fallen back to `ready` with no session attached. This
reads externally as "nothing happened, task reset" but the actual work (a full
design doc, or a complete implementation diff) can be sitting untouched in the
worktree or as a kanban attachment, because the session died in the gap between
finishing the work and running its own commit/push/PR steps.

Observed (alpha-learn-content-gen #1311/#1321 rebake-reprovision fix): the
design-author session completed and attached a 441-line design doc; the
implementation session completed a 4-file, 128/118-line diff matching that
design exactly — then both sessions exited before committing. Two consecutive
`ready`-state sightings for the same task (once after design, once after
implementation) were each mistaken at first for "no progress" when the
worktree actually held complete work both times.

**Recovery sequence for whoever notices the `ready`-with-no-session symptom**
(a T1, a human, or a fresh T2 asked to check status) — do this BEFORE
respawning a new T2 from scratch:
1. `tmux ls | grep <task-related-pattern>` — confirm the session is truly gone,
   not just idle/thinking (a live "thinking" spinner is not this failure mode).
2. Check the worktree directly: `git status --short`, `git log --oneline
   main..HEAD`, `git diff main --stat`. Also `hermes kanban attachments
   <task_id>` — a design doc can be fully attached even though the tmux
   session that authored it is gone.
3. If there's a real, complete diff matching the design/brief's stated scope
   (not a half-edited file mid-refactor): run the language's own syntax/lint
   check yourself before trusting it (`bash -n` for shell, `python -m
   py_compile` / `yaml.safe_load` for Python/YAML, a brace/paren/bracket count
   for PowerShell where no local linter is installed) — a session killed
   mid-edit can leave a file that looks plausible but doesn't parse.
4. If it checks out clean: commit it yourself (a real message — problem +
   what changed, per `pr-description-style`, no session/task-number
   narration), push the branch, and open the PR yourself (`gh pr create`,
   body per `pr-description-style`). Don't wait for a freshly respawned T2 to
   redo mechanical steps you can finish faster and with less risk of
   re-diverging from the already-reviewed design.
5. **Dispatch an independent review regardless of who committed the code** —
   the same session/human that recovered and committed the diff must not be
   its only reviewer. Use `delegate_task` with the SPECIFIC safety/correctness
   invariants from the design doc spelled out in its context (e.g. "must
   never touch the live worker process," "must abort before the destructive
   step on any failure") rather than a generic "review this diff" ask — a
   generic review prompt won't reliably check for the exact failure modes the
   design was written to prevent (see the "reuse/extend" review-prompt-gap
   section elsewhere in this skill for why generic prompts miss
   brief-specific risks).
6. Kill any other stale/dead sessions for the same task found along the way,
   and leave a kanban comment stating explicitly what was recovered vs.
   respawned so the audit trail doesn't read as a silent task reset.
7. Still stop at the human merge gate as normal — recovering a dead session's
   work does not bypass PR approval; it only rescues the work product so a
   respawn cycle isn't wasted re-deriving it.

## Idle-session accumulation is a distinct failure mode from any single wedge

Across a build/validation session running many T1/T2/worker sessions back to
back, sessions that finish (or crash before self-terminating) but are never
torn down accumulate silently — 20+ idle tmux sessions is not unusual after a
long multi-task run. This is NOT the same problem as a wedged session (which
never finishes); it's finished-and-orphaned sessions nobody reaped, each one
(a) a live process consuming memory and (b) possibly still holding a Paperclip
checkout lock that blocks the issue from being picked up again — the second
effect is the more expensive one because it's silent (nothing errors; the
issue just never becomes available).

**Don't rely on manual reaping** — a script/step you have to remember to run
is worthless for this: orphans build up between the times you remember, and
the one time it actually matters (a blocked issue re-pickup) you won't have
run it recently. The durable fix is a silent scheduled watchdog:
- Classify each session before touching it: idle-at-prompt (no
  "esc to interrupt"/active-spinner marker in the pane) → safe to reap;
  actively working → never touch.
- For any session that held a checkout and is now gone (dead session, lock
  still held per that session's own state file), release the lock — this is
  the higher-value half of the sweep, since a stuck lock actively blocks
  future work while a merely-idle session just wastes memory.
- Run this as a `no_agent` cron watchdog (deterministic script, no LLM calls,
  silent stdout unless it actually acts) on a short interval (e.g. every 30
  min) rather than as a manual or LLM-driven step — it's pure mechanical
  triage with no judgment call, so paying LLM tokens for it is waste, and a
  cron is the only form that reliably runs without being remembered.

This complements, not replaces, each orchestration skill's own self-termination
step (a T2 killing its own session on Phase-5 completion) — the watchdog is the
safety net for the crashed-before-cleanup path that self-termination can't
cover by construction.

See `references/orphan-reaper-watchdog.md` for the concrete script shape
(classify/reap/release steps, cron wiring, a worked first-run result) — copy
that pattern rather than re-deriving it per orchestration skill.

## A green "full-chain E2E" suite can be hollow — verify the test BODY, not the pass count, before accepting "we tested the complete pipeline"

Distinct from every wedge/lock/CI-verification issue in this skill: this one is
about the CONTENT of a passing test suite, discovered while checking a T2's
claim that a multi-stage pipeline rebuild was "fully tested E2E" before merge.
275+ tests passing, including files literally named `test_sentinel_full_chain.py`
and `test_sentinel_cron_e2e.py`, turned out to prove far less than the names
promised — and the gap was only visible by opening the test bodies, not by
reading pass/fail counts or file names.

Two specific hollowing patterns to check for whenever a subordinate session (or
your own past self) claims "the complete pipeline was tested end-to-end":

1. **The "full chain" test hand-builds its own fixture instead of calling the
   real entry point.** `test_run_report_renders_full_chain` constructed a
   `list[LedgerEvent]` by hand (collected → frequency_counted → ... →
   pr_created) and passed it straight to `render_run_report(events)`. That
   proves the renderer formats a given sequence correctly — it does NOT prove
   the pipeline's real top-level entry point (`run_sentinel_cron_v2()`) ever
   produces that sequence from real inputs. Same trap in
   `test_ledger_has_complete_v2_stage_sequence` — asserting a stage-name list
   is present in a report says nothing about whether a live run reaches those
   stages. Tell: does the test call the actual production entry point and let
   IT generate the events/state, or does it construct the events/state itself
   and only exercise the downstream consumer of that data?

2. **The exact subsystem the claim hinges on is mocked.** A test literally
   named `test_verifier_runs_real_qc_and_returns_booleans` (under a class
   `TestDesignerVerifierRealQC`) did `patch("...verifier.subprocess.run")` —
   with an explicit comment admitting "We can't run the real QC subprocess in
   a unit test, but we can verify the subprocess template + invocation shape is
   correct." That's a legitimate and useful test, but it proves invocation
   *shape*, not real execution — and the test's own name claims the opposite
   ("runs real QC"). Grep the file for `patch(`/`Mock`/`MagicMock` and check
   whether it wraps the specific call the test's name/claim is about.

**Confirming evidence, not just test-reading, closes the loop:** in the
observed case, grepping the pipeline's ledger for `pr_created` events carrying
a `run_id` (the v2 marker) returned zero — i.e. no real run of the rebuilt
pipeline had EVER produced a PR, despite "full-chain E2E" tests being green.
That's the deciding check: if the claimed artifact (a PR, a rendered report
from a live run, a DB write) has never actually been produced by a real
invocation, the claim "we tested the complete pipeline" is false regardless of
how many tests pass — say so plainly rather than accepting the pass count.

**Procedure when reviewing any "E2E"/"full-chain"/"integration" test claim:**
1. Read the test file's actual body (`grep -nE 'def test_|patch\(|Mock'`), not
   just its name or the pass/fail summary.
2. For each test whose name claims to exercise "the full pipeline"/"the real
   X": check whether it imports and calls the real top-level function, or
   constructs its own intermediate fixture and calls a narrower downstream
   function.
3. For each test whose name claims "real" execution of a subprocess/network/
   DB call: check for a `patch`/`Mock` wrapping that exact call.
4. Independently query the artifact the claimed real run would produce (a
   ledger event, a PR, a file on disk) rather than trusting "tests pass" as
   proof it happened.
5. If gaps exist, name them precisely (which test, which mock, what it does
   and doesn't prove) rather than a blanket "not fully tested" — the honest
   answer usually is "wiring is tested and correct, execution has never
   happened," which is actionable, not just a red flag.

## A fully-green gate (impl+tests+review+CI) is not proof of an architectural crux claim proven only by fakes — build a real-process e2e proactively

Distinct from the "hollow full-chain E2E" section above (which is about auditing
an EXISTING test claiming to be E2E) and from every wedge/lock issue in this
skill: this is about recognizing, BEFORE a human has to ask, that an
architectural design's core claim — "a process survives its parent's death,"
"lock/ownership hands off correctly across a process boundary," "no
duplicate/lost events across a restart" — can pass a fully green gate (impl
verdict pass, 1000+ unit tests green, code review `approved`, all CI checks
green including external scans) while the actual claim has never been
exercised with real processes. If the bulk of Phase 3.2's tests use fakes/
mocks/in-process doubles for the layer the claim is about (a fake CLI runner,
a stub subprocess, an in-process loop standing in for a real spawn), green
there proves the fakes behave as programmed, not that the real system does.

**Observed** (alpha-learn-content-gen #1434, agent-supervisor/dashboard
decoupling): PR reached `MERGEABLE`/`CLEAN` with 45/45 checks green, review
`approved` at confidence 90, ~3000 unit tests passing across 3 suites — then
the human held the merge specifically because "most tests use fakes" and
required a true e2e with a REAL claude CLI process on a real host before
proceeding, unprompted by any gate failure. Building it surfaced 2 real
defects invisible to every fake-runner test: (1) a repo-root package shadowing
a same-named pip package, which only breaks when a real subprocess actually
imports the real library (a fake runner imports nothing); (2) a cleanup-path
crash on a genuine failed real spawn (a fake runner's "spawn" never fails that
way, so the code path had zero coverage despite the mocked suite being green).

**The lesson: don't wait to be asked.** When a design's central claim is a
real-process/runtime-boundary behavior and the test suite backing the gate is
predominantly fakes for that exact boundary, flag it explicitly in the PR
description ("this suite validates X via fakes; a real-process e2e for the
crux claim does/does not exist") and consider building the real e2e as part of
reaching mergeable, not as a reactive response to a human's after-the-fact
"but did you actually test it for real" push. A fully green mocked gate is a
necessary check, not a sufficient one, for this class of claim.

**Technique for the real e2e itself** (worked pattern, transferable to any
process-boundary-survival claim):
1. Start REAL processes for every layer in the claim — no fakes anywhere in
   the chain under test (a real supervisor/owner process, a real coordinator/
   caller process, and, for CLI-spawning designs, a REAL coding-agent CLI
   child process).
2. Kill only the layer the claim says the system survives losing (e.g. the
   coordinator), never the layer under test (the owner, the spawned child).
3. Assert process identity across the boundary via `ps -o pid,ppid,command`
   before/after snapshots — same pid, same ppid after the kill — not log
   lines or return codes. This proves continuity, not just "something is
   running now."
4. Exercise the exact production re-attach/resume contract a fresh instance
   of the killed layer would use, and assert strict sequence continuity (no
   dup, no gap) across the boundary.
5. Cover the design's negative-path promises too (a second writer refused, a
   live lock never clobbered, a dead lock correctly reclaimed) — as core to
   the claim as the happy path, and just as easy for a fake to miss.
6. Mark it `real_cli`/`integration` and exclude it from the standard CI test
   filter (CI has no real CLI/gateway credentials) — it's a host-only,
   pre-merge verification test, not a CI-suite member. Document the exact run
   command and captured evidence (ps snapshots, per-assertion pass table) in
   the PR/kanban trail so a human doesn't have to re-run it to trust it, and
   independently re-run it yourself once before accepting a subordinate
   session's "e2e passed" self-report — same discipline as every other
   self-reported outcome in this skill.

This complements `tier2-orchestration` Phase 3 (exit gate: impl/tests/review):
treat "is the crux claim proven only by fakes" as a question worth asking for
any architectural build, alongside the existing impl+tests+review checks, not
a separate optional step that only exists when explicitly requested.

## Real-process e2e validation escalates in ROUNDS — each round reuses the harness and can surface a NEW defect the prior rounds' fakes/scope missed

Continuation of the section above, for when the human keeps raising the bar
after the first real-process e2e passes rather than stopping at one. Observed
on the same PR (#1434) across three escalating asks in one session: (1) one
crux e2e (real CLI survives a dashboard restart, viewer reattaches with no
dup/gap) → passed, 2 defects found+fixed; (2) "beyond the single e2e, add+run
multi-session restart, repeated restarts, SIGKILL recovery, WS reconnect,
long multi-turn, concurrency, failure injection, soak" (9 more scenarios) →
all passed, more test-logic fixes, no product defects that round; (3) "convert
the 5 areas that are STILL only unit-tested (not yet real-process) into real
e2e too" (TCP+token transport, defs-pin flip, headless-drive-under-restart,
Windows lock-mutex branch, interaction-across-restart) → passed, and this
round found the round's own real defect (a drive spawn path missing the
gateway env injection the primary spawn path had, causing an unbounded hang).

**Pattern to follow, not re-derive per round:**
1. Each round is additive, not a redo — reuse and extend the SAME harness file
   (process spawn/kill helpers, a protocol client, an evidence recorder) built
   in round 1 rather than hand-rolling new scaffolding per round.
2. Before scoping a new round, explicitly enumerate what's STILL only
   fake/unit-tested vs. already real-process-covered — the human's third ask
   here was specifically "the areas the prior two rounds' fakes still cover"
   ((a) transport variant, (b) a config/versioning edge, (c) a lifecycle edge,
   (d) an OS-specific branch, (e) a request/response edge across the same
   restart boundary already proven for the happy path) — a genuinely new
   scenario, not a re-run of round 1/2's coverage.
3. Push + re-run CI after EVERY round's real code fixes land, even mid-way
   through a multi-round validation program — don't batch all fixes to the end
   of the last round. Append a coverage-summary section to the PR body each
   round (see `pr-description-style`) rather than only updating it once at the
   end, so a human checking the PR mid-program sees current, not stale, scope.
4. A later round finding a defect earlier rounds' fakes/scope structurally
   couldn't reach is the EXPECTED outcome of this escalation, not a sign the
   earlier rounds were inadequate — say so plainly in the round's report
   rather than either overclaiming completeness after round 1/2 or treating
   round 3's find as an embarrassing miss.

## A cross-task reviewer finding arriving AFTER your own gate is green is still actionable — fold it in like a review-round fix, don't freeze scope at "gate passed"

Distinct from every in-loop review-round pattern above (author↔reviewer inside
ONE task): a SEPARATE Tier-2 task reviewing an adjacent/dependent surface (e.g.
a Windows-migration T2 reviewing this PR's auth/transport code because its own
host is about to become the production runtime for that code) can post a
finding on ITS OWN kanban task, addressed to yours, after your PR is already
`MERGEABLE`/`CLEAN` with CI fully green. Treat this exactly like a review
round's blocking issue, not as out-of-scope feedback that arrived "too late" —
if it's a genuine, host-confirmed defect (not a stylistic preference), dispatch
a fix session, re-verify, re-push, re-run CI, and reply on the OTHER task's
kanban thread confirming the agreed mechanism + the fix, before considering the
PR done. A green gate is a snapshot, not a lock against new evidence.

**Recognize a genuine cross-task finding vs. noise:** it's confirmed on a
LIVE host (not theorized), names an exact file/function/line, and states the
precise failure mode reproduced there — as opposed to a general "have you
considered X" comment. The former needs a fix; treat the latter as an FYI to
note, not act on immediately.

**Worked example** (alpha-learn-content-gen #1434 agent-supervisor +
production-readiness review from a parallel Windows-migration T2, t_fdf9cc90):
the Windows T2 confirmed on the live prod-bound host that `auth.py`'s
`_current_principal()`/`_acl_windows()` (icacls-based token-file ACL for the
TCP+shared-token supervisor↔dashboard channel) breaks under an NSSM
LocalSystem service context — `getpass.getuser()` returns the machine account
with a trailing `$` (e.g. `EC2AMAZ-SIH5IVK$`), which `icacls` cannot map to a
SID ("No mapping between account names and security IDs was done"), so
`store_token()` raises and the supervisor can never provision/re-read its
token when run exactly as production runs it (LocalSystem). Fix: resolve a
machine-account (`...$`) or literal `SYSTEM` principal to the well-known
`SYSTEM` name before calling `icacls` (SYSTEM is already an allowed principal;
symmetric on both the grant and verify sides so store→restart→load round-trips
under LocalSystem), dedupe grantees, and declare the optional `keyring`
credential-store fallback as a `sys_platform=='win32'` dependency so it's
actually installed on the host instead of silently degrading to the (until
then broken) file-ACL-only path. Proven with tests that monkeypatch the
principal + stub `icacls` so they run on POSIX CI/dev (the general pattern for
testing Windows-only code paths without a Windows box). Fixed, re-verified,
pushed, CI re-run green, and the confirming reply posted on the OTHER task's
kanban thread — all before the PR was considered actually done, despite the
gate already having been green once.

**Testing a Windows-only code path without Windows access:** monkeypatch the
function that reads OS/session identity (e.g. `getpass.getuser`) to return the
values you need to prove (a machine-account name ending in `$`, literal
`SYSTEM`, a normal user), and stub the external OS tool (`icacls`,
`subprocess.run`) rather than skipping the test — this is the same technique
`test_windows_lock_mutex_branch`-style tests already use elsewhere for
`msvcrt` locking; reuse the pattern rather than re-deriving it.

## A subordinate session's PASS summary can directly contradict its own captured evidence file — grep the raw evidence, don't trust the prose line

A sharper, more specific version of "never trust a self-report" than the
generic rule already states: it's not just that a claim needs independent
re-verification — a session can hand you BOTH a prose summary ("17/17 PASS,
11.8s") AND a machine-written evidence JSON from the very same run, and the
two can flatly disagree (the JSON showing `duration_s: 430.4` and the core
assertion as `FAIL`). This is not a vague-claim problem where you're deciding
whether to trust prose absent evidence — the evidence was RIGHT THERE,
self-generated by the session, and the session's own summary contradicted it.

**Observed** (alpha-learn-content-gen #1434, phase-2 headless-drive scenario):
a session reported the scenario passing at 11.8s; its own captured evidence
JSON showed a 430s duration and the "drive completed" assertion as FAIL. The
supervisor's own independent re-run reproduced the failure consistently
(2/2 runs, ~430s, "still driving at timeout") — confirming the JSON, not the
prose, was the truth, and that the defect was real and reproducible (missing
gateway-env injection on that spawn path). It was fixed at root and
re-verified (18.9s, 17/17 pass, evidence regenerated all-pass) before being
accepted.

**Procedure — do this every time a session hands you both a summary and an
evidence artifact from the same run, not just when something feels off:**
1. Open the evidence file yourself and check for FAIL/non-zero-exit/outlier-
   duration markers BEFORE reading or trusting the prose "N/N PASS" line.
2. If they disagree, the evidence file wins — treat the prose summary as
   unreliable for the WHOLE report, not just the contradicted line, and
   re-verify every other claim in that session's report too.
3. Re-run the specific failing scenario yourself, more than once if the first
   re-run is ambiguous (real-process tests over a network/gateway can be
   genuinely flaky — 2 consistent failures rules that out; 1 does not).
4. Once a root-cause fix lands, regenerate the evidence file (don't just trust
   a second prose "now it passes" claim) and diff it against the first,
   broken one to confirm the specific failing assertion flipped.
5. Document the correction explicitly in the kanban/PR trail ("a prior
   session's report misreported X; caught on independent re-run; now
   genuinely green, evidence regenerated") rather than silently replacing the
   bad claim with the corrected one — the audit trail should show the
   catch, not just the final state.

## A stale claim can refuse `claim`/`reclaim` even when its TTL is long expired, if the task sits in `review`

Distinct from the `ready`-state-no-transition and `holder:null` sections below:
a task left in kanban `review` status by a session that died mid-task can have
a lock whose TTL expired hours/days ago (`lock_ts << now - TTL`, confirmed by
reading the raw lock timestamp) and `hermes kanban claim <task_id>` still
refuses — TTL expiry alone does not auto-clear a `review`-status claim the way
it does for a `ready`/`running` one. Don't loop retrying plain `claim` calls
expecting the TTL check to eventually kick in; it won't, because the refusal
here is state-gated (`status=review`), not TTL-gated. Use `hermes kanban
reclaim <task_id>` explicitly (a distinct verb from `claim`) — it force-clears
a claim regardless of TTL/status and is the correct recovery action the moment
you've confirmed via `hermes kanban show <task_id> --json` that no live
session actually holds it (dead tmux session, no process). Re-run a plain
`claim` immediately after `reclaim` succeeds to establish YOUR hold.

## `claude_orchestrate steer` with blank/empty text on a dialog-confirm prompt can CANCEL the session, not confirm it

A second dialog-steering trap distinct from the "queued/pasted-but-unsubmitted"
issue documented elsewhere in this skill (that one is about a steer being
silently swallowed mid-turn): sending `steer` with an EMPTY message string to
try to produce a bare Enter keypress on a workspace-trust or
bypass-permissions dialog can land on the wrong option and exit the session
entirely — observed the pane vanish immediately after an empty-text `steer`
call on the Claude Code trust prompt (default selection was "Yes", but the
empty-text send + Enter combination resolved to exit instead). `steer` always
sends the literal text via `send-keys -l` followed by a separate Enter — an
empty payload is not a safe way to produce "just press Enter." For dialog
navigation, send the ACTUAL required keystroke sequence as real content (e.g.
a literal `\n` string, or an explicit `Down` then confirm for a
bypass-permissions dialog whose default is "No, exit") rather than an empty
string. If a dialog-confirm steer makes the pane disappear, don't retry the
identical empty steer — restart the session fresh (Claude Code usually skips
re-prompting workspace trust for an already-trusted directory, so only the
bypass-permissions dialog will likely reappear) and use a real keystroke
payload the second time.

## An independent auditor pass with zero prior context is a cheap, high-value LAST step before human handoff — not redundant with the review rounds

Distinct from "verify a subordinate session's self-reported PR/CI state
independently" above (which is about checking specific claims a session made)
and from the multi-round review→fix loop itself (which is bounded to 3 rounds
and shares context/summaries across rounds by design): once the capped review
loop converges (`approved`/`spec: pass`) and the gate is green, dispatch ONE
more check — a fresh `delegate_task` subagent with explicitly ZERO trust in
any prior summary, told to re-verify every claimed finding/fix against the
actual code and to run the real test suite itself, before attaching a final
verdict to the PR/kanban and pinging the human. This costs one delegate_task
call and catches the specific failure mode none of the in-loop reviews can:
review N's session inherits (or is influenced by) framing from review N-1's
summary, so a subtle regression the loop collectively glossed over survives
all N rounds. A genuinely fresh context with no inherited framing, explicit
per-finding CLOSED/PARTIAL/OPEN classification instructions, and its own
independent test run is worth the extra call precisely because Tier-2's own
context (and every review session dispatched from within it) has been
steadily accumulating the same narrative across the whole task. Frame the
delegate goal as: re-derive each finding's status from disk/git diff/tests,
not from the verdict files T2 already trusts.

## A trivial nit at the human review gate doesn't need the full revert→Phase-2→re-review loop — and `heartbeat` fails on a `review`-status task

Distinct from the round-cap convergence/deadlock question this skill mostly
covers: sometimes the human reviewing a PR at the Phase 4 merge gate doesn't
send it back for a real fix round — they ask for something purely cosmetic
(trim verbose comments, fix a typo, reformat a string) with explicitly no
logic change. Running the full `tier2-orchestration` Phase-2 cycle (dispatch a
coding-agent session, wait, gate, re-review) for this is disproportionate —
it's slower than doing it directly and burns a review round for something that
was never in dispute.

**When the ask is verifiably comment/whitespace-only:** apply the edit
yourself directly in the worktree (skip the coding-agent dispatch entirely).
Verify scope with `git diff | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' |
grep -vE '^[+-]\s*(//|$)'` — if that returns non-empty, something beyond
comments/blank lines changed and you should fall back to the real fix loop
instead of self-certifying a logic change as trivial. If it returns empty,
rerun the project's real test+lint+build yourself (same standard as any gate
pass), commit, push, and record it with a kanban comment. Leave the task in
`review` — this isn't a new review round, it's a same-round housekeeping edit.

**`hermes kanban heartbeat <task_id>` fails on a task sitting in `review`**
("cannot heartbeat, not running?") — heartbeat only accepts `running` tasks.
Use `hermes kanban comment` to record this kind of edit instead; don't treat
the heartbeat error as something to fix or retry.

## A residual defect surviving several prompt-tweak iterations is not automatically a model-capability limit — check for an enforcement gap first

Distinct from every session-mechanics/wedge pattern in this skill: this is a
judgment trap in an iterative generate→QC→fix loop (e.g. a Tier-2-driven
prompt/enforcement build), not a session-liveness problem. When a defect class
survives multiple rounds of prompt tweaks aimed at the generating model, the
natural conclusion is "the model just can't do this reliably, accept it as a
residual risk." That conclusion is frequently wrong — the more common root
cause is that the QC/enforcement layer has a gap (a check that doesn't exist,
or an existing check that's too narrow) letting the bad output through, not
that the generator is incapable of correct output.

Observed repeatedly on one build (script-image-gen SVG generation pipeline):
a malformed-field crash, a containment check that only flagged straddling
overlap and missed elements placed fully outside their container, a
color-exclusivity check that only compared across separate elements and
missed a defect within one text element's tspan fragments, and a spacing
defect ("substituted value not placed inline") initially written off as "LLM
geometric-edit imprecision" — every one of these turned out to be a fixable
QC/enforcement gap once pushed on, not a genuine model ceiling. The tell each
time: a *deterministic, measurable* property of the output (position, color,
containment, spacing) existed that could distinguish good from bad — the gap
was that nothing measured it yet.

**Before declaring a defect a genuine model-capability blocker:**
1. Ask whether a deterministic check — measuring geometry, color, text
   position, containment, or another concrete rendered property — could catch
   the bad output and force a regen. If yes, that's a QC/enforcement task, not
   a capability limit, regardless of how many prompt-only iterations already
   failed to fix it.
2. Only accept it as a true model-capability limit once you've confirmed no
   measurable signal distinguishes the defective output from a correct one —
   not merely because a prompt instruction was ignored once or twice. A prompt
   fix repeatedly failing is evidence the fix belongs in enforcement, not
   evidence the defect is unfixable.
3. When challenged ("that doesn't sound like a blocker, more like an
   enforcement issue"), re-derive the check from the measurable property
   rather than defending the "model limit" framing — in every observed case
   here, the reframe led directly to a working deterministic check within one
   more iteration.

## An idle-at-prompt T2 pane mid design-loop can be a correct round-cap escalation, not a wedge or a death — check the board before applying ANY recovery procedure

Distinct from every wedge signature above (think-loop, bash-hook-error,
sub-agents-done-wandering, background-sub-agents-never-complete) and from the
"dead T2 with uncommitted work" section: those all assume something has gone
wrong. This is the case where NOTHING has gone wrong — the T2 is behaving
exactly as designed, and treating the symptom as a wedge/death wastes an
interrupt cycle or a needless respawn.

Symptom: an orchestrator (T1, or the operator) polls a T2's tmux pane during
a needs-design task and sees it idle at its input prompt, with the visible
history showing a `sleep 300`/`sleep 180`-style wait call as the last tool
call, and no new activity for a while. On its own this pattern-matches every
wedge signature above. The distinguishing check is the KANBAN TASK STATE, not
the pane: if `hermes kanban show <task_id>` shows the task `blocked` with
`needs_input` (not `ready`/`running` with a dead session, and not `review`),
and a design doc (`design-r<N>.md` or similar) is attached, the T2 has hit
`multi-round-review-convergence`'s round cap with the final round returning
genuine blocking issues, escalated correctly per this skill's own Deadlock
section, and is now idle BECAUSE it is waiting on the human decision — not
because it crashed or wedged.

**Always check board state before applying wedge recovery or a respawn:**
1. `hermes kanban show <task_id> --json` — if `status: blocked` +
   `needs_input`, this is a design escalation, not a wedge. Stop; do not
   Escape/interrupt, do not respawn, do not treat it as dead.
2. Read the attached design doc's final round to see the actual blocking
   issues before relaying anything to the human — classify each as
   narrow/mechanical (has an exact reviewer-prescribed fix, can be applied as
   a targeted amendment to the existing doc without a new round) vs.
   structural (a real approach fork). See the "Mixed/plateaued trend" section
   above for the classification method and a worked example.
3. Present the human with an explicit decision (amend the doc vs. spin a new
   round vs. accept-with-documented-risk) rather than dumping the raw review
   text or silently picking one path forward.
4. Only fall back to wedge-recovery procedures (Escape+nudge, session
   restart) if the kanban state does NOT show a clean `blocked`/`needs_input`
   design-doc escalation — e.g. the task is still `running` with no attached
   doc and the pane has been idle past what the round's own turn should take.

## The orchestrator (T1/T2 supervisor) must NEVER personally amend a design doc or a T2's source diff to resolve a review blocking issue — hand it back to the T2, even for a "precision edit"

Distinct from every session-mechanics/wedge pattern in this skill: this is a
role-boundary rule, not a diagnostic one. Authoring/amending a design doc and
editing implementation code are BOTH the T2's job — design authoring and
implementation, respectively — never the orchestrating T1/supervisor's, no
matter how small, mechanical, or "obviously correct" the edit looks, and no
matter whether the T2 session is mid-sleep/idle/between rounds at the moment.

**Why this is a hard rule and not a judgment call:** a supervisor editing the
artifact directly bypasses the exact review discipline this skill exists to
protect. Observed twice in one build: (1) a supervisor's own "one-line"
amendment to a design doc's regenerator-return-type section, meant to resolve
a review blocking issue, missed that the new recomposition prompt needed a
SEPARATE channel from the existing edit-instruction `feedback_history` (not
merged into it) — an interaction the T2's OWN next design-review round caught
immediately, and the T2's actual revision (a distinct `regen_prompt_history`
field) was strictly better than the supervisor's hand-edit; (2) a supervisor's
direct regex fix to a QC check's source file (to widen a color-description
pattern match) also missed the real phrasing gap on the first attempt. Both
times, handing the identical blocking-issue list to the T2 and letting it run
its own amend→re-review cycle produced a correct, verified result — because
that cycle is specifically designed to catch exactly this class of subtle
interaction, and a solo direct edit has no reviewer at all.

**The fix, every time a review returns blocking issues (design OR code):**
hand the blocking-issue list + artifact path BACK to the live T2 session (one
`tmux send-keys` steer) and let it run its own amend/fix → re-review round.
Only if the T2 session is genuinely dead (no live process, confirmed via
`tmux ls`) does direct recovery become appropriate — and even then, per the
"Dead T2 session with uncommitted-but-complete work" section elsewhere in this
skill, recovering dead-session work still requires dispatching an independent
review of anything you personally commit, never self-certifying it.

**There is no efficiency argument for doing it yourself.** If a live T2
session exists for the task, steering it costs exactly one `tmux send-keys`
call — cheaper than diagnosing and re-fixing your own mistake after the fact,
and it preserves the review discipline the multi-round loop is there for.
User correction on this exact pattern, treat as a standing rule going forward:
"don't try and amend it yourself if you're gonna make so many mistakes, give
it to T2."

## `checkout_conflict` with `holder: null` is a status mismatch, not a lock

Distinct from every failure mode above, but same family ("don't misdiagnose a
signal that looks like one thing but is actually another\"): `tier2-orchestration`
Phase 2 step 2 says `checkout_conflict` means \"another writer holds the issue,
STOP\" — that's only true when the 409 response's `holder` field is a real
agent UUID. Paperclip's checkout call rejects on ANY status outside
`expectedStatuses: [\"todo\",\"backlog\",\"blocked\"]`, independent of whether
anyone holds the issue, and returns `holder: null` for that case. A `holder:
null` conflict is not a lock problem — chasing `recover`, inspecting
`checkoutRunId`, or searching run history for `cancelled` runs are all dead
ends here (confirmed no lock is held; that's not the blocker).

Fix: the issue's status is simply outside the eligible set (commonly stuck at
`in_review`/`in_progress` from a prior run that completed but never got its
status reset). PATCH it back to an eligible status, then retry `start`:

```bash
curl -s -X PATCH http://localhost:3100/api/issues/<ISSUE_ID> \\
  -H 'Content-Type: application/json' -d '{"status":"backlog"}'
```

Then verify the checkout actually engaged the normal way (issue flips to
`in_progress`, `assigneeAgentId` = your agent, `checkoutRunId` set) before
trusting `start`'s `ok:true`.

## `checkout_conflict` with `holder: null` is a status mismatch, not a lock

Distinct from every failure mode above, but same family ("don't misdiagnose a
signal that looks like one thing but is actually another"): `tier2-orchestration`
Phase 2 step 2 says `checkout_conflict` means "another writer holds the issue,
STOP" — that's only true when the 409 response's `holder` field is a real
agent UUID. Paperclip's checkout call rejects on ANY status outside
`expectedStatuses: ["todo","backlog","blocked"]`, independent of whether
anyone holds the issue, and returns `holder: null` for that case. A `holder:
null` conflict is not a lock problem — chasing `recover`, inspecting
`checkoutRunId`, or searching run history for `cancelled` runs are all dead
ends here (confirmed no lock is held; that's not the blocker).

Fix: the issue's status is simply outside the eligible set (commonly stuck at
`in_review`/`in_progress` from a prior run that completed but never got its
status reset). PATCH it back to an eligible status, then retry `start`:

```bash
curl -s -X PATCH http://localhost:3100/api/issues/<ISSUE_ID> \
  -H 'Content-Type: application/json' -d '{"status":"backlog"}'
```

Then verify the checkout actually engaged the normal way (issue flips to
`in_progress`, `assigneeAgentId` = your agent, `checkoutRunId` set) before
trusting `start`'s `ok:true`.

## kanban's `ready` claim state has no direct `→running`/`→review` transition — use `block` as the "awaiting human" signal instead

Distinct from every Paperclip-era conflict below (kanban has replaced Paperclip;
this lesson is for the current `hermes kanban` + `kanban-review.py` backend):
`hermes kanban claim <task_id>` sets a task to `ready`, NOT `running` — but
`~/.hermes/scripts/kanban-review.py --to running` only accepts the
`running→review`/`review→running` family of moves and REJECTS `ready→running`
and `ready→review` with `cannot move to 'X' (allowed from: [...])`. If your
implementation loop never explicitly flips the task to `running` at some other
point (e.g. `tier2-orchestration`'s ledger/heartbeat steps don't call an
explicit `→running` transition today), you can reach Phase 4 (PR up, ready for
human review) still sitting in `ready`, and BOTH `--to running` and `--to
review` fail identically.

**Don't loop retrying transitions when you hit this** — it's a state-machine
gap, not a usage error, and retrying different `--to` values wastes calls.
Fall back immediately to `hermes kanban block --kind needs_input <task_id>
"PR #N ready for review and merge approval"`. `block` is accepted from `ready`
(it's not gated by the same allowed-from list as `--to running/review`), it
still surfaces correctly on the dashboard, and it still fires the
notify-subscribe ping — functionally equivalent for the "PR is up, stop and
wait for a human" signal even though the task shows as `blocked` rather than
`review` on the board.

Also note `hermes kanban heartbeat <task_id>` fails the same way on a
non-`running` task (`"cannot heartbeat … (not running?)"`) — once you're at
this blocked/ready state waiting for human input, skip heartbeating; the claim
question is moot since you've already stopped for human input rather than
continuing autonomous work.

## `TFY_API_KEY` (or any gateway env var) missing inside a claude_orchestrate-launched tmux session

A separate infra gotcha from the checkout-status one above, same family of
"the symptom looks like one thing, the real cause is elsewhere": a
`claude_orchestrate start` session (claude OR codex executor) fails or hangs
with something like `Missing environment variable: TFY_API_KEY`, even though
`echo $TFY_API_KEY` in your own shell shows it's set.

Root cause: the plugin launches sessions inside a **tmux server** — and a
tmux server inherits the environment that existed when the server was first
started, not your shell's environment at the moment you call `start`. If the
server has been running since before the key was exported (or since before
`.env`/shell config loaded it), every new session/pane on that server is
missing it regardless of what your interactive shell currently has. This is
NOT a credentials problem and re-exporting the key in your own shell does
nothing for it.

**Fix:** the plugin's launch `shell_cmd` must explicitly `export
TFY_API_KEY=...` (or whatever gateway key the executor needs) before `cd`/exec,
so the exported value rides into the new session regardless of the tmux
server's inherited env. If you're extending `claude_orchestrate` or building a
similar tmux-launcher yourself, always prepend needed env exports to the
launch command rather than assuming ambient inheritance — confirm by checking
`tmux show-environment -t <server>` if this error recurs.

**A second, unrelated bug can look identical:** Codex CLI (observed on
0.144.x) throws the same-looking `Missing environment variable` error
specifically when given a **positional prompt argument** (`codex "prompt
text"`), even with the key correctly present — but launches clean with no
positional arg, and the error reappears the instant the prompt is actually
submitted. Workaround: launch codex bare (no prompt on the command line), wait
for its TUI to come up, then `send-keys` the prompt text + Enter as a separate
step. If the env-var error appears/disappears depending on whether a prompt
was passed inline (not on whether the key is actually exported), this codex
quirk — not a real env problem — is the cause; don't spend more time chasing
it as an auth/config issue.

## A "reuse/extend existing mechanism" brief needs an explicit reuse check in the review prompt — generic correctness review passes right over a parallel fork

Distinct from every failure mode above: when a design/brief says "extend the
existing X" (a queue, a session registry, a cache, any existing state
machine), a generic code-review pass — even a thorough one with multiple
specialist reviewers and a fully green test suite — can approve a diff that
actually built a SECOND, parallel implementation of the same concept instead
of reusing the original. Each path looks locally correct in isolation
(compiles, passes its own tests, handles its own errors), so nothing in a
generic "find bugs/security issues/logic errors" review prompt trips on it —
the defect isn't a bug in either path, it's the existence of two paths for one
concept, one of which silently lacks capabilities the other had.

Observed (ALP-3 queue-while-busy, `alpha-learn-content-gen` #1242): the
frontend already had a working `pendingQueue` mechanism (turn-in-progress
queuing) with edit/delete chip controls and chip-only rendering (no chat-log
duplication). The brief was to extend it to also queue while a headless
session drives the turn. The implementation instead added a second track
(`awaiting_ack`/`server_queued` states) with its own send path and its own
`_renderQueue` branch — which (a) called `appendEvent` to render the message
as a full chat bubble AND pushed the same message to the queue chip, causing
visible duplication, and (b) rendered `awaiting_ack`/`server_queued` chips
WITHOUT the `<button class="cc-queue-rm">` remove control that `local`-state
chips get, silently dropping edit/delete for anything queued this way. This
passed a 3-specialist review batch (silent-failure-hunter, code-reviewer,
test-coverage-analyzer — 5 findings fixed) and 1147 local + 39 CI tests, and
was only caught by the human manually using the feature after merge-readiness
was declared.

**Fix the review prompt, not just this instance.** Whenever a unit's brief
contains "extend"/"reuse"/"add to the existing <mechanism>" language, the
Tier-2 Phase 3.3 review prompt (or any `requesting-code-review`/specialist
dispatch) MUST add an explicit reuse-audit instruction, not just "review this
diff for bugs":

> "The brief says to extend the existing `<mechanism>`. Diff the new code path
> against the pre-existing one for that mechanism: does the new code actually
> route through the existing state/render/control functions, or did it
> introduce a parallel set of states/branches for the same concept? If
> parallel, enumerate every capability, UI control, or invariant the original
> mechanism had (list them from the pre-change code) and confirm each one
> still applies to messages/entries that take the new path. A duplicate
> display of the same logical event (e.g. both a chat-log entry AND a queue
> chip for one message) is itself a defect to flag."

This is a review-PROMPT gap, not a reviewer-choice gap — running more
specialists or a stronger model doesn't help if none of them are told to
check for reuse-vs-fork; it needs to be asked for explicitly, the same way the
"local-green does not mean CI-green" section below needs an explicit grep
step rather than trusting "run the suites the diff touches."

## Local-green does not mean CI-green when a diff changes a shared response shape

A different gap from every wedge/lock/env issue above: the exit gate's local
test run (3.2) can pass cleanly and STILL have CI fail on push, because
"run every test suite the diff touches" (by file path) is not the same
guarantee as "every test that asserts the changed behavior has been updated."
When a change alters a dict/string literal that other code asserts exact
equality on (a WS ack shape, an API response envelope, a serialized event
dict), the test that guards that literal can live in a **sibling test file**
that exercises a different code path (e.g. a detach/reconnect flow vs. the
normal send flow) than the file colocated with the source module you touched
— and "which test file covers this source file" reasoning misses it entirely.

Observed (ALP-3 headless-bridge queue-while-busy build): changing the WS `ack`
dict shape in `chat_session.py`/`chat_api.py` to add `queued`/`client_message_id`
fields was caught and updated in the colocated `test_chat_session.py`, all
local suites passed (1064 + 83 tests), CI showed 37/38 green — then the 38th
check (`lesson-qc-auto-checker`) failed on push because a sibling file,
`test_chat_ws_detach.py`, had 6 exact-match assertions on the OLD ack dict
shape for the detach code path. This cost a full push→CI-fail→diagnose→
fix→push→re-wait-on-CI round trip that a one-line grep would have prevented.

**Fix the gate step, not just this one instance:** before declaring 3.2 tests
complete, grep the actual literal(s) your diff changed across the WHOLE
component's test tree, not just the file(s) colocated with the touched source
module: `grep -rn '"kind": "ack"' components/<component>/tests/` (substitute
the real changed literal). Update every hit, not just the ones in the
same-named test file. Do this in addition to — not instead of — "run every
suite the diff touches by path"; the two checks catch different gaps.

## Codex silent-startup wedge on an IMPLEMENTATION session — a third wedge signature, distinct from both above

The two wedge signatures documented above (high-effort-thinking loop; Bash-hook
error loop) were both observed on **review** sessions. A third, distinct
signature shows up on **implementation** sessions launched via
`claude_orchestrate start executor=codex` (commonly as the fallback after a
Claude Code implementer wedged): the pane shows only the startup banner and the
prompt echoed back, with **zero** subsequent tool-call or reasoning output —
no search, no read, no "thinking" spinner, nothing — even minutes later. A
`steer` message asking it to write a one-word status to `status.md` produces
no visible reaction either; the prompt just sits there unconsumed.

Do not confuse this with legitimate long investigation (which — even when
slow — shows *some* tool activity: searches, reads, shell commands) or with
the high-effort-thinking signature (which shows an active "thinking"/spinner
line). If the pane is genuinely blank after the prompt with no tool-call
markers at all, that's the wedge, not patience being warranted. `diagnose`
(pane+log dump) confirms before you `stop` it — same evidence-before-kill
discipline as the other two signatures.

**When BOTH the claude implementer AND its codex fallback wedge on the same
unit** (one via think-loop, one via silent-startup, or any combination), and
the unit's brief is precise enough — exact file(s), exact edit locations/line
anchors, a small targeted diff, an explicit test command — don't escalate
immediately. Fall back to a `delegate_task` **leaf** subagent as a third-tier
implementer: inline the full edit spec directly in the delegate goal (a leaf
subagent won't reliably chase an out-of-repo brief file path the way a CLI
coding session does — put the concrete before/after description in the prompt
itself, with the brief file path as a secondary reference). Require it to
report back verifiable evidence — `git diff --stat`, the real test command's
output, a commit SHA — same "never trust a self-report" discipline as
everywhere else in this skill. `delegate_task` runs its own isolated
terminal/session outside the tmux/CLI machinery both coding CLIs wedge on for
this failure class, so it's a legitimate third rung on the ladder, not a
workaround to avoid using next time. Only escalate to the human if the
delegate_task attempt also fails, or the unit turns out too ambiguous/large to
specify precisely inline (in which case it needed a design pass, not a bigger
hammer).

## New interleaved event/frame type breaks exact-count test assertions REPO-WIDE, not just in the shape-changed literal's sibling file

A related but distinct gap from the "local-green does not mean CI-green when a
diff changes a shared response shape" section above: that section covers
changing an EXISTING literal's shape (a dict grows a field) that a sibling
test asserts exact-equality on. This section covers ADDING a wholly NEW
frame/event/message type to a shared stream (a WebSocket, an event bus, a
queue) that a sibling test doesn't assert equality on at all — it just reads
N raw frames expecting exactly N specific ones. The new frame doesn't fail an
assertion, it **shifts the read count and can make a blocking read hang
forever** waiting for a frame that will never arrive at that position. This
is a different failure shape (hang vs. wrong-value assertion) and needs a
different fix (a skip-aware read helper, not an updated literal).

Observed (alpha-learn-content-gen, t_cea60b98, chat status-dot invariant fix):
adding a `session_status` broadcast frame on every turn-start/turn-end broke
~10 WS tests across 3 files that did bare `ws.receive_json()` N times
expecting exactly N event frames. Fixing the first failing file's assertions
one CI-round at a time cost 4+ debugging passes, including one raw
`ws.receive_json()` that blocked for the full test timeout because a
`seq <= cutover` replay-skip guard interacted with the new frame's sequencing
in a way that wasn't obvious from the assertion alone — required tracing the
production `attach()`/replay path, not just patching the test.

**Fix the gate step:** when a unit's diff adds a new frame/event type to any
shared multi-consumer stream:
1. Grep the RAW read call pattern for that stream across the WHOLE test tree
   (not just the file colocated with the source module), e.g.
   `search_files(pattern='receive_json\(\)\["event"\]')` repo-wide — every
   hit is a candidate off-by-N.
2. Introduce (or extend) ONE shared filtering helper (e.g. `_receive_event`)
   that skips the new frame type, and migrate every raw call site to it in a
   single pass — don't fix them one CI-failure-at-a-time as they surface.
3. Treat a raw read that BLOCKS (times out) rather than asserting wrong, as a
   signal to trace the production emit/replay/filter path for that frame
   (ordering vs. an existing seq/cutover/silent-attach guard), not just a
   test-side symptom — the fix is sometimes a small production guard change
   (e.g. "only emit the live-only status frame on silent/replay attach, not a
   fresh attach") plus the test update, not the test update alone.
4. Re-run the FULL suite before pushing, and still treat CI as authoritative
   after a green local run — per the sibling section above, a straggler a
   local run doesn't happen to include is a real gate failure.

- `tier2-orchestration` Phase 2 step 4 (fallback on failed/stalled claude
  implementation run → codex) — this section is the missing third rung: what
  to do when codex ALSO wedges, and how to recognize codex's wedge signature
  (silent-startup) as distinct from claude's (think-loop).
- `tier2-orchestration` Phase 3.3 (code review) — the reuse-vs-fork section
  above is the missing review-prompt instruction for any brief that says
  "extend/reuse the existing X"; add it explicitly rather than trusting a
  generic correctness-review prompt to catch a parallel-mechanism fork.
- `tier2-orchestration` Phase 3.2 (code review→fix loop, 3-round cap) — same
  logic applies to `spec:fail`/`needs_fixes` verdicts. The wedged-session
  recovery above applies here too: if a single review round's session stalls
  in high-effort thinking rather than the loop deadlocking across rounds,
  Escape+nudge it before assuming a round-limit or convergence question.
  The "local-green does not mean CI-green" section above also plugs in here:
  grep the changed literal shape across the whole test tree before declaring
  3.2 tests complete, not just the suites the diff's file paths touch. The
  "new interleaved event/frame type" section above is the companion case for
  ADDING a frame (not changing an existing one's shape) — same grep-first
  discipline, plus watch for blocking (not just failing) raw reads.
- `tier2-orchestration` Phase 1 (setup, before claiming) — the brief-target-
  verification section above is the missing preflight check: confirm the
  brief's named component actually owns the reported symptom's user-observable
  surface before writing a design doc or dispatching, especially when the
  brief's own referenced path doesn't exist verbatim (a naming near-miss is a
  signal to re-derive the target, not to fuzzy-match to the nearest real file).
- `tier2-orchestration` Phase 4 step 5 (human review at the merge gate) — the
  trivial-nit section above is the missing shortcut: a comment-only/formatting
  ask from the human doesn't need the full revert→Phase-2→re-review cycle —
  apply it directly, verify scope via the comment/blank-line diff grep, rerun
  tests/lint/build yourself, and use `hermes kanban comment` (not `heartbeat`,
  which rejects a `review`-status task) to record it.
- `tier2-orchestration` Phase 4 step 4 (move to `review` after PR is up) —
  the kanban `ready`-state section above is the missing fallback: if
  `kanban-review.py --to review`/`--to running` both reject with an
  allowed-from error, the task is still in `ready` (claim state) with no
  direct transition — use `hermes kanban block --kind needs_input` instead of
  retrying transitions, and skip heartbeating once blocked.
- `tier2-orchestration` Phase 1 step 1 (claim) — the stale-claim-in-`review`
  section above is the missing recovery step: a `review`-status task's claim
  can survive its own TTL expiry and refuse plain `claim` retries; use
  `reclaim` explicitly (a distinct verb), then `claim` again, rather than
  looping on `claim` waiting for TTL logic that doesn't apply to this status.
- `tier2-orchestration` Phase 1b.1/1b.2 and Phase 2 step 2 (PTY dialog
  handling on session start) — the blank-steer-cancels-dialog section above
  extends the `claude-code` skill's dialog-handling pitfall specifically to
  the `claude_orchestrate steer` action: never send an empty-text steer to try
  to produce a bare Enter on a trust/permissions dialog.
- `tier2-orchestration` Phase 3.3/Phase 4 (exit gate → human handoff) — the
  independent-auditor-pass section above is the recommended final step after
  the review→fix loop converges and before pinging the human: one
  zero-prior-context `delegate_task` re-verification catches drift the
  in-loop reviews structurally can't (shared framing across rounds).
- `tier2-orchestration` Phase 2 step 2 (`checkout_conflict` handling) — before
  treating a 409 as \"another writer holds it,\" check `holder`; `null` means a
  status mismatch (see the section above), not a genuine ownership conflict.
- `tier2-orchestration` Phase 3.3 (code review) — the sub-agents-done-but-no-
  verdict-file wandering section above is a third wedge signature to check for
  alongside the think-loop and bash-hook-error ones, before falling back to
  the `requesting-code-review` `delegate_task` specialist batch.
- `tier2-orchestration` Phase 3.3 (code review) — the background-sub-agents-
  never-complete section above is a FOURTH wedge signature: unlike the
  wandering case, the sub-agents themselves never finish (climbing elapsed
  time/tokens with no completion). Time-box each sub-agent's own elapsed time
  (~10-12 min) rather than relying on the top-level session's stall detection,
  and don't spend more than one steer/interrupt cycle before falling back to
  the `requesting-code-review` `delegate_task` specialist batch.
- Any future reviewer-loop skill with a hard round cap should link here
  rather than re-deriving the convergence/deadlock distinction from scratch.
- Idle-session-accumulation watchdog (above): applies to ANY orchestration
  skill that spawns per-task tmux sessions (T1 author/reviewer sessions, T2
  worker/review sessions), not just the review loop specifically — link here
  from a new orchestration skill rather than re-deriving the reap-vs-preserve
  classification.
- `tier2-orchestration` Phase 3.2/3.3 (never trust an agent's self-report on
  tests/review) — the hollow-full-chain-E2E section above is the missing
  procedure for the specific case of a subordinate session (or a T2's own
  summary) claiming "the complete pipeline was tested end-to-end": read the
  test bodies for hand-built fixtures feeding a narrow downstream function and
  for mocks wrapping the exact subsystem the claim is about, and independently
  confirm the claimed real artifact (PR, DB write, rendered live report)
  actually exists before accepting the claim.
- `tier2-orchestration` Phase 2 (implementation loop) and Phase 1b (design
  loop) — the "dead T2 session with uncommitted-but-complete work" section
  above is the missing recovery path for BOTH loops when the supervisor
  session itself (not a coding sub-session) dies mid-run: check the worktree
  and kanban attachments for salvageable work before respawning, and always
  get an independent review of anything you personally commit on the dead
  session's behalf.
- `tier2-orchestration` Phase 3 (exit gate) — the "fully-green gate is not
  proof of a fakes-only crux claim" section above is a step to add alongside
  impl/tests/review for any architectural build: before declaring mergeable,
  ask whether the design's central real-process/boundary claim was ever
  exercised with real processes, or only with fakes/mocks — and build the
  real-process e2e proactively rather than waiting for a human to demand it.
- `tier2-orchestration` Phase 3 (exit gate) — the "real-process e2e escalates
  in rounds" section above is the missing multi-round shape for when a human
  keeps raising the real-process-coverage bar after round 1 passes: reuse the
  same harness, explicitly enumerate what's still fake-only before scoping the
  next round, push+re-run CI after every round's fixes, and expect (not fear)
  a later round finding a defect earlier rounds structurally couldn't reach.
- `tier2-orchestration` Phase 3.2/3.3 and core principle 3 (never trust a
  self-report) — the "PASS summary can contradict its own evidence file"
  section above is the sharpest form of that rule: when a session hands you
  BOTH a prose summary and a machine-written evidence artifact from the same
  run, grep the evidence for FAIL/outlier-duration markers before trusting the
  prose line, and if they disagree, distrust the WHOLE report, not just the
  one contradicted claim.
- `tier2-orchestration` Phase 4 (human review at the merge gate) — the
  cross-task-reviewer-finding section above is the missing "gate is green but
  new evidence arrived" case: a parallel task's host-confirmed finding on your
  merged-ready PR is a real review round, not stale feedback — fix, re-verify,
  re-push, re-CI, and reply on the other task's thread before treating the PR
  as actually done.
- `tier2-orchestration` Phase 1b (design loop) and `tier1-suborchestration`
  (T1 monitoring a T2 it spawned) — the "idle-at-prompt T2 pane can be a
  correct round-cap escalation" section above is the missing disambiguation
  step before applying ANY wedge-recovery or respawn procedure to a T2 that
  looks idle mid design-loop: check `hermes kanban show <task_id>` for
  `blocked`/`needs_input` + an attached design doc first — that state means
  the T2 escalated correctly and is waiting on the human, not that it died or
  wedged.
- Codex CLI model ids must be bare, never Hermes-prefixed.
  a `claude_orchestrate` session with `executor=codex`, the `model` param must
  be the id codex itself understands (e.g. `gpt-5.6-sol`), NOT a Hermes
  provider-group-prefixed id (`openai-group/gpt-5.6-sol`) — the prefix causes
  the codex session to exit instantly with no output and a null outcome, which
  reads exactly like an unrelated launch/infra failure rather than a bad model
  string. Also: a codex TUI session (the `executor=codex` path launches the
  bare interactive TUI, not `codex exec`) in a fresh, non-git, untrusted
  scratch dir will exit silently the same way — the directory-trust menu eats
  the scripted prompt input trying to dismiss it. Before dispatching real
  design-review/orchestration work to a codex session in any new scratch dir:
  `git init` the dir AND add `[projects."<abs-path>"]` to `~/.codex/config.toml`
  (or accept the trust prompt once interactively) first, and confirm with a
  trivial probe prompt before trusting real output there.
