# Tier-2 pitfalls and lessons (moved from the main skill, unchanged)

Long-form pitfalls and per-incident lessons. The main skill keeps one-line pointers.

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
  dies. The plugin (`~/.hermes/plugins/claude-orchestrate/__init__.py`, legacy-fireworks
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


## Lessons

<!-- LESSON (legacy Fireworks route): "reads outside working directories" permission prompt
stalls sessions. A claude_orchestrate session (legacy model_provider=fireworks) whose
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
