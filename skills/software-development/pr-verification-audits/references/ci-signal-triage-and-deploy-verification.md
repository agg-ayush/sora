---
name: ci-signal-triage-and-deploy-verification
description: "Judge whether red/stuck CI checks reflect a real test failure or a GitHub-platform-side outage before reacting, and — for fixes that can only be fully proven on deployed infra (server-side timing, cron ticks, environments CI can't reach) — write a concrete post-merge verification recipe into the PR. Use whenever an orchestration skill (tier1-suborchestration, tier2-orchestration) or a human is driving a PR through CI/merge and checks look wrong, or the change under test depends on behavior that only manifests once deployed. Complements tier2-orchestration/github-pr-workflow/pr-description-style without editing them (those are manually-authored and off-limits to autonomous edits)."
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [CI, GitHub-Actions, Outage, Deployment, Verification, Tier-2]
    related_skills: [tier2-orchestration, github-pr-workflow, pr-description-style, infra-migration-staged-rollout]
---

# CI signal triage + deploy-only verification

Two related judgment calls that come up while driving a PR through an automated
gate (`tier2-orchestration` Phase 3/4, or any human-driven PR): (1) is a wave of
red/stuck checks a real test failure or a GitHub-platform outage, and (2) for a
fix whose correctness only shows up once deployed, what goes in the PR so a human
(or a later agent turn) can actually prove it worked after merge.

## 1. Real test failure vs GitHub platform outage

**Outage signature** — treat as platform-side, not code:
- Many/all jobs fail identically at the *setup* phase: `Failed to resolve action
  download info`, `Service Unavailable`, or similar infra-level errors — not a
  specific assertion failing inside a test.
- Runs sit `queued` for many minutes with zero job progress, or the whole matrix
  fails uniformly regardless of which files the diff touched.

**Confirm before reacting** — don't guess from vibes:
```bash
curl -s https://www.githubstatus.com/api/v2/components.json | python3 -c "
import json,sys
cs={c['name']:c['status'] for c in json.load(sys.stdin)['components']}
print('Actions:', cs.get('Actions'))"
```
`major_outage` / `partial_outage` on the `Actions` component confirms it.

**During a confirmed outage:**
- Stop force-pushing / cancelling+rerunning to "unstick" the queue — each attempt
  just wedges another run behind the backlog and burns time for no signal.
- Note the outage once on the tracking task/issue (one comment) so a resuming
  session doesn't re-diagnose the same thing from scratch.
- Hand the wait off to a background poller instead of blocking the foreground
  loop on it:
  ```bash
  # detect a NEW run appearing on the branch (id changes from the last
  # known/wedged run), then watch that one to completion
  N=$(gh run list --repo <org>/<repo> --branch <branch> --limit 1 \
        --json databaseId --jq '.[0].databaseId')
  if [ -n "$N" ] && [ "$N" != "<last-known-run-id>" ]; then
    gh run watch "$N" --repo <org>/<repo> --exit-status --interval 30
  fi
  ```
- If a human says to stand down/park during the outage, stop touching CI and the
  PR entirely (no polling "just to check") until they give the explicit word to
  resume — treat that instruction as overriding the default push-until-green loop.
- Once a genuinely new run appears and completes, go back to reading real
  per-job results — don't assume recovery just because the queue is moving; the
  new run's actual pass/fail is still the signal that matters.

## 2. Post-merge verification for deploy-only-verifiable fixes

Some fixes can't be proven by local pytest / CI alone because the failure mode
only exists once the code runs in its real deployment context — a server-side
periodic sync tick, `DEPLOYED_MODE`-gated behavior, timing races that need a
live cron, anything CI's ephemeral runner can't reproduce. For these, add a
**"Post-merge verification"** section to the PR body (alongside Context/
Behavior-change/Validation — see `pr-description-style` for the rest of the PR
shape) with the exact, reproducible steps to run against the live target after
merge: concrete commands, what artifact to fingerprint/compare (e.g. `md5sum`
before/after on the files at risk), and what a passing result looks like
concretely (e.g. a specific JSON field being `[]`/non-null, a file's mtime/hash
being unchanged). Write it as an executable checklist, not a hedge about
pre-merge confidence — this is what turns "should be fixed" into "here's how to
prove it."

**Sequence when a human says "park it, don't merge, I'll say when":**
1. Add the post-merge verification section to the PR body now — don't wait for
   the merge signal to write it.
2. Do not push/rerun CI, force-push, or merge until the explicit merge word
   arrives. If GitHub is mid-outage, the "add the verification section" step is
   still safe to do (it's a `gh pr edit`, not a CI action) — do it now rather
   than waiting for the outage to clear.
3. Keep the tracking task in its review/pending state — do not advance it to
   done/blocked while parked.
4. On the merge word: merge (proper commit message per `pr-description-style`),
   wait for the deploy to actually land, then execute the documented
   verification steps yourself against the live server/target and report the
   concrete evidence (fingerprints, JSON field values) — not just "looks fine."

## 3. Re-check the FULL `gh pr checks` list after every push, not just the workflow you already track

A PR can be green on the CI workflow you're gating on (e.g. `ci.yml`:
tests/lint/build) while GitHub still reports `mergeStateStatus: UNSTABLE`
because of a *separate* check run from a different GitHub App — e.g. an
org-wide Semgrep/security-scan bot that isn't part of the repo's own workflow
file and won't show up if you only look at `ci.yml` job results or re-run
tests/lint/build locally.

Observed case: after pushing a "pure refactor" commit (a shared helper
deduplicating repeated logging calls), `ci.yml` was green, but a separate
`Semgrep` check failed — the refactor introduced a
`` console.error(`...${label}`) `` non-literal-format-string pattern the
security scanner flags (`javascript.lang.security.audit.unsafe-formatstring`).
This was invisible to local `pnpm run test`/`lint`/`tsc` because none of those
run a security scanner; it only surfaces via `gh pr checks` or the GitHub
check-runs API.

**Rule for "is the PR actually clean" at ANY point after the initial push:**
1. `gh pr checks <pr>` — read every row, not just the ones you recognize from
   your own workflow file.
2. For any `fail`/`failure` row that isn't your tracked test/lint/build job,
   pull its annotations before assuming it's pre-existing noise:
   ```bash
   SHA=$(git rev-parse HEAD)
   gh api "repos/<owner>/<repo>/commits/$SHA/check-runs" | python3 -c \
     "import json,sys; d=json.load(sys.stdin); [print(c['name'],c['conclusion'],c['id']) for c in d['check_runs']]"
   gh api "repos/<owner>/<repo>/check-runs/<id>/annotations" | python3 -c \
     "import json,sys; [print(a['path'],a['start_line'],a['message'][:200]) for a in json.load(sys.stdin)]"
   ```
   Piping through `| python3 -m json.tool` can choke on this endpoint's output
   shape — parse with a small inline `json.load` script instead.
3. If the annotation points at a line from your latest commit, fix it (through
   a coding session, not a direct hand-edit — see below) and push again, then
   re-run `gh pr checks` again. Don't declare "no pending issues" from memory
   of an earlier check; every "anything pending?" question should trigger a
   fresh pull of the check list and `mergeStateStatus`.
4. Quick fix for the unsafe-formatstring pattern specifically: replace
   template-literal interpolation inside a log call's first argument with a
   `%s`-style literal format string plus the variable as a separate positional
   arg — `console.error('...%s...', label, ...)` instead of
   `` console.error(`...${label}...`) ``. Same fix applies to `console.log`/`warn`.

## 4. Monorepo CI-only dep failures: diagnose by import graph in one pass, not one push per package

A recurring pattern when a T2-driven PR adds new tests (esp. e2e/hook-chain
tests that spawn real subprocesses) to a monorepo component: local suites are
green because the local venv (often the main repo's shared venv, or a worktree
venv built from it) has every sibling component's deps installed transitively
from unrelated earlier work. CI installs each component from a clean
`pip install -e ".[test]"` with only that component's own declared deps, so a
new test fails there with `ModuleNotFoundError`/`ImportError` for something the
local env happened to have lying around but was never declared.

**The trap is fixing these one at a time via push→wait→read-log→fix→repush.**
Each fix just uncovers the next undeclared transitive import. Observed chain on
one PR (agent-supervisor + lesson-qc components, real-CLI hook-chain tests):
missing `yaml` → declared → next failure `filelock` (a subprocess the test
spawns imports it) → declared → next failure that subprocess's own
`python-pptx` import → declared → next failure `requests`/`openai`/`pydub`/
`audioop-lts` (all present locally via the shared venv, none declared in the
component's `pyproject.toml`). Five push/CI-wait round-trips for what one pass
would have caught.

**Do it in one pass:** the instant ONE CI-only dep failure appears,
`grep -rn '^import\|^from' <every new/changed test file>` — including files any
test-spawned subprocess or hook script executes (a test shelling out to
`on_prompt.py` needs THAT script's import graph checked too, not just the test
file's) — and diff the full import set against the component's
`[project.dependencies]` / `[project.optional-dependencies].test` in
`pyproject.toml`. Add everything missing in one edit (dispatch via a
`delegate_task` test-fixer fenced to `pyproject.toml`/lockfiles via
`claude_orchestrate check_diff`, per `tier2-orchestration`'s test-fix flow —
never hand-edit, see §5 below) before pushing again, instead of reacting to
each CI run's single reported failure.

A companion CI-noise signal in this same family: a GitHub Actions job stuck
showing `in_progress` forever after the *run's own* conclusion is already
`completed: success` is a runner infra flake, not a code issue — check
`gh run view <id> --json status,conclusion` (the run-level conclusion, not the
individual stale job status) before chasing it; an empty
`git commit --allow-empty && git push` to force a fresh run is the fastest
unblock, faster than trying to re-run just the stuck job.

## 5. T2 must never hand-edit source directly, even for a one-line "trivial" fix

The general Hermes convention lets the agent hand-edit genuinely small
infra/config changes directly instead of delegating. **That exception does not
apply while acting as a T2 supervisor.** `tier2-orchestration`'s boundary rule
(core principle 4) routes ALL code changes through `claude_orchestrate` coding
sessions — with no line-count carve-out — because a session-driven commit is
tracked/attributable and gets the same verify-yourself treatment as everything
else in the pipeline; a direct supervisor `patch` bypasses that.

Observed: mid-task, under time pressure to close out a small fix (a dep-array
bug, then separately a 2-line security-scan format-string fix), the supervisor
used its own `patch` tool directly instead of dispatching a session — twice.
The user's explicit instruction for that task ("everything routes through
subagents/tool calls") makes clear the trivial-fix exception is suspended
under T2.

**Rule:** if you're driving as T2 and about to `patch`/`write_file` a source
file for any reason, stop — dispatch a `claude_orchestrate` session (worktree,
`executor=claude`, `model_provider=fireworks`) with the exact fix described,
then verify + commit through that session's normal flow. No exception for
"it's one line."

## 6. A required-Semgrep supply-chain finding is often a mutable-tag GitHub Action, not app logic

When the org-wide Semgrep check (§3) fails on a workflow-file change, pull the
annotations before assuming it's a code-security finding — it commonly flags a
new/edited GitHub Actions step that references a third-party action by a
mutable tag (`uses: some-org/some-action@v3`) instead of a pinned commit SHA, a
standard supply-chain-hardening rule, not a logic bug. Fix by resolving the
tag's exact commit SHA and pinning it (`uses: some-org/some-action@<full-sha>
# v3`, keeping the human-readable version as a comment), matching however the
rest of the repo's workflows already pin third-party actions (check a couple of
existing `.github/workflows/*.yml` files for the convention before assuming
none exists). This clears the check with a genuine security improvement, not a
suppression — don't spend time trying to get Semgrep to ignore the finding.

## 7. A test that hangs or fails only in YOUR shell is often your own env, not the diff — diagnose with a clean-env bisect before touching code

Before treating a hung or newly-failing test as a real regression from the
diff under test, rule out your own shell's accumulated environment state.
Two concrete pollution sources recur in this repo family and produce failures
that look exactly like real regressions:

- **A tracked repo-root package shadows a same-named pip package.** A stray
  `mcp/` directory (or any dir matching an installed package name) sitting at
  the repo root gets put on `sys.path` by `cwd`-relative pytest invocation,
  shadowing the real installed SDK — this fails identically on base AND the
  branch under test, so it is never the diff's fault, only the invocation cwd.
- **Hermes's own agent process's `PYTHONPATH` leaks into subprocess test runs.**
  If you're running `terminal()`/background shells from inside a Hermes agent
  session, that session's own `tools/` package (Hermes's internal tools dir)
  can land ahead of the target repo's own `tools/` on `sys.path`, so
  `import tools.session` or a string-path `monkeypatch.setattr("tools.session.x")`
  resolves to the WRONG package — symptoms range from `ModuleNotFoundError` to
  a test hanging indefinitely (blocked in an asyncio/subprocess wait on state
  that never materializes because it patched the wrong module).

**Diagnostic procedure — do this before writing a single line of fix code:**
1. Re-run the SAME invocation (same command, same cwd) with a sanitized env:
   `env -i PATH="$PATH" HOME="$HOME" <venv>/bin/python -m pytest ...` (add back
   only what the test genuinely needs — a stripped `env -i` can itself hang a
   subprocess-spawning test if it drops something required; if that happens,
   restore vars one at a time rather than abandoning the clean-env approach).
2. Compare the SAME sanitized invocation against `git stash`/base commit. If it
   fails/hangs identically on base, it's environmental — not your diff.
3. If it's genuinely different between your shell and clean env, the cause is
   almost always sys.path shadowing: `python -c "import tools; print(tools.__file__)"`
   from inside the exact same env/cwd the test uses, and confirm it resolves to
   the target repo's module, not a same-named package from Hermes's own install
   or a stray tracked dir.
4. Once isolated, run the test suite from the SAME directory + env CI actually
   uses (often the repo root, with a repo-scoped venv that has the component's
   deps — not the Hermes session's own shell) — that is the actual ground truth
   for "does this pass," not your immediate interactive shell.

**Time cost of skipping this:** in one T2 run, chasing what looked like a real
`test_auto_orchestrator` regression (a crashed implementation session mid-fix)
took ~10 separate diagnostic tool calls before finally isolating it to (a) test
invocation cwd (namespace-package resolution differs from-repo-root vs
from-`tests/`) and (b) the *supervising* Hermes agent's own `PYTHONPATH`
polluting the subprocess — neither was a code defect. Running the clean-env
bisect (step 1-2 above) FIRST, the moment a "regression" surfaces during your
own re-verification (not the implementer's), would have cut this to 2 calls.

## 8. `gh pr merge --delete-branch` fails when run from the issue's own worktree

When driving a per-issue worktree (one worktree/branch per T2 issue), running
the merge command from inside that worktree fails at the branch-delete step:
`fatal: 'main' is already used by worktree at '<main-repo-path>'` — gh needs to
move the local branch to a safe ref post-merge and can't, because the branch
you're standing on IS the one being deleted. The merge itself usually still
lands (re-running `gh pr merge` from the main checkout reports "already
merged" — verify with `gh pr view --json state,mergedAt` rather than assuming
the first error means nothing happened), but `--delete-branch` silently fails
on both halves: the remote delete may or may not go through, and the local
delete separately fails with `cannot delete branch '<name>' used by worktree at
'<worktree-path>'` until the worktree is gone.

**Correct order:**
1. Run `gh pr merge` from the **main repo directory**, not the worktree.
2. Confirm merged: `gh pr view <N> --json state,mergedAt`.
3. Stop any process still running out of the worktree (dev servers, watchers
   started during manual/demo testing).
4. `git worktree remove --force <worktree-path>`.
5. `git branch -D <branch>`.
6. `git push origin --delete <branch>` (or re-run `gh pr merge <N>
   --delete-branch` once the worktree is gone — it no-ops on the already-merged
   PR but finishes the branch cleanup).

Don't assume `--delete-branch` alone is sufficient in a worktree-per-issue
setup — it needs the worktree gone first.

## 9. Kanban task-state quirk when driving T2 manually (no dispatcher)

A kanban task claimed via `hermes kanban claim <task_id>` stays at status
`ready` — claiming does NOT transition it to `running`. Two downstream calls
assume `running` and will reject the task while manually driven:
- `hermes kanban heartbeat <task_id>` — rejects a `ready` task.
- The `review`-transition helper / `hermes kanban` review-move calls — same
  rejection, and `hermes kanban dispatch`-adjacent verbs that WOULD move it to
  `running` also want an assignee and spawn a worker you don't want when you
  (T2) are driving by hand.

This isn't a real blocker — the claim itself is what prevents double-work, and
it doesn't expire just because heartbeat calls are failing on a manual run.
Workaround: skip heartbeat and track progress via `hermes kanban comment
<task_id> "<progress note>"` instead for the duration of the manual drive. Set
an assignee (`hermes kanban assign <task_id> <your-profile>` or equivalent) if
you need any transition verb that requires one. Don't burn cycles hunting for
the "right" transition command — comments are a sufficient audit trail when
you're the one holding the claim.

## 10. `git worktree remove --force` can fail with "Directory not empty" even after a clean merge

Once a T2/tier2-orchestration issue's branch is squash-merged, `git worktree
remove --force <path>` for cleanup can still error with `Directory not empty` —
untracked scratch left inside the worktree (a test venv, `__pycache__`, build
artifacts from running suites there) isn't cleared by `remove`. The worktree
still gets de-registered from git despite the error (confirm with `git worktree
list` — it drops out — or force it with `git worktree prune`); only the
on-disk directory lingers. Once the branch's work is confirmed on main (squash
commit present in `git log origin/main`, `gh pr view --json state` shows
`MERGED`), it's safe to `rm -rf` the leftover directory directly. Don't treat
the `remove --force` error as evidence the merge didn't really land — check the
PR/commit state, not the worktree-removal exit code.

## 11. Design-review round-cap override: keep iterating without re-asking each round

`tier2-orchestration`'s design-review loop caps at 3 rounds by default and
escalates to a human on the 3rd unapproved verdict. If the human explicitly
overrides the cap ("run as many more rounds as needed," "don't descope
issues X/Y/Z"), the override covers ALL subsequent rounds — don't stop to ask
again at round 5, 6, 7. Track the round count in kanban comments for
resumability, but treat re-escalation as warranted only if a NEW round surfaces
a blocking issue that's actually task-level ambiguity (not a design gap the
reviewer can trace in code). Observed case: post-override it took 8 rounds
total to reach `approved: yes` on a hard concurrency surface (lock ownership +
lease reclamation), with the blocking-issue count genuinely narrowing each
round (4→6→3→2→3→2→1→0) as the reviewer traced deeper into real control flow —
that convergence shape is normal for adversarial review of concurrency design,
not a signal to abandon the loop or seek a shortcut.

## 12. A deploy script that stops the old container before the new one is confirmed up can brick prod on ANY failure in between

If a deploy script's sequence is `docker stop/rm <old>` → (config/env upserts) →
`docker run <new>` → health-wait, then ANY failure between the stop and the
health-wait succeeding leaves the box with **no running container at all** —
not a rollback, a hard outage. This is a fragile ordering regardless of how
solid the individual steps look in isolation (observed: the actual `docker run`
commands worked fine when run manually seconds later; the automated run still
exited 1 partway through and left the box bare — the specific failing sub-step
wasn't reproducible after the fact, but the OUTAGE was 100% reproducible from
the ordering itself).

**If you hit this (found prod down after an auto-deploy):**
1. Read-only assess first: `docker ps -a` (empty = confirmed bare), a health
   endpoint curl, and the last ~40 lines of the workflow run's deploy-step log
   (`gh run view <id> --log-failed`, then grep from `Stopping old container`
   forward) to see exactly which lines DID print before it died — usually only
   the stop/rm, nothing after.
2. Recreate manually in the SAME order the script would have used (check
   `.env`/secrets are intact on the box, `docker run` the dependency container
   first if there is one, then the main service), verifying each `docker
   inspect ... Health.Status` before moving to the next.
3. Flag the ordering defect as a follow-up (don't hand-patch the workflow file
   mid-incident under time pressure) — the durable fix is starting/health-check
   the NEW container before stopping/removing the OLD one (blue-green swap, or
   at minimum: create new → wait healthy → THEN stop old), so a failure anywhere
   in between leaves the OLD container still serving instead of nothing.

**The durable fix, concretely (stage-then-swap + rollback):**
- Capture the currently-running image as a rollback target BEFORE anything
  stops: `PREV_IMAGE=$(docker inspect --format='{{.Image}}' <container> || true)`.
- Run the new image under a different name on a temporary port
  (`<service>-staged` on a scratch port), and health-gate it there. Only give
  the old container its graceful SIGTERM/stop AFTER staging reports healthy.
- Make the health-wait function return the terminal status (not just loop and
  fall through) so a timeout OR an unhealthy result after the swap triggers an
  explicit `rollback()` back to `PREV_IMAGE` on the real port — a lapsed wait
  must not be silently treated as success.
- If the deploy also brings up a companion/sidecar container (e.g. a
  supervisor) that the main service doesn't strictly need to serve, wrap that
  block so its failure logs a warning and the deploy **continues** — a sidecar
  dying must never abort or roll back the primary service that's already up.
- Pre-create any host directories a container mount depends on
  (`mkdir -p /data/whatever`) before the `docker run` that mounts them, so a
  fresh box / first deploy of a new mount doesn't fail on a missing dir. **Existence
  is not enough — `chown` the directory to the container's runtime UID, not just
  root.** A plain `sudo mkdir -p /data/whatever` creates it root-owned; if the
  container that writes into that mount runs as a non-root user (e.g. `appuser`
  at uid 1000, as most hardened images do), every write inside the mount fails
  with `PermissionError` even though the mount itself succeeds and the container
  starts healthy. Observed: this was the ONE failure left after the stage-then-swap
  fix above made the dashboard swap itself fully atomic (healthz stayed 200
  throughout) — the deploy's very last step, publishing versioned defs into a
  mounted volume, died on exactly this. Fix: `sudo mkdir -p /data/whatever &&
  sudo chown <container-uid>:<container-uid> /data/whatever` (check the
  Dockerfile's `USER` directive or `docker inspect --format '{{.Config.User}}'`
  on a running container for the exact uid) in the SAME deploy step that creates
  the directory, before the container that writes to it ever runs. Fix the
  already-provisioned box by hand once (`sudo chown` on the live path) so the
  current deploy is unblocked, then land the same `chown` in the workflow file
  so every future first-deploy-on-a-fresh-box gets it automatically.

**Verifying the fix without touching the live service:** exercise the SAME
script logic against throwaway container names + a free port on the real prod
box, leaving the actual running service untouched the whole time. Extract the
workflow's deploy step to a local shell function/script parameterized by
container name + port, then drive these scenarios and confirm the real
service's health endpoint stays 200 throughout each:
1. Happy path — staging comes up healthy → swap → healthy → exit 0.
2. Bad image — staging never turns healthy → abort, nothing touched → exit 1.
3. Forced failure after staging is healthy (e.g. name collision on swap) →
   confirm `rollback()` actually restores the previous image and it goes
   healthy again on the real port.
4. Sidecar/companion container crash-looping → confirm the primary deploy
   still completes (warning logged, exit 0), not aborted.
Clean up every throwaway container/artifact afterward and re-confirm the real
service's health endpoint before declaring the fix verified — "the script
looks right" is not evidence; a scenario-by-scenario dry run against real
`docker` on the real box, with the live service continuously healthy, is.

**Live flag-flip verification recipe** (proving a runtime-mode env var change
actually took effect, e.g. flipping an agent-supervisor architecture on): don't
trust `printenv` alone inside the container as sufficient proof of the new code
path being exercised — corroborate with process ancestry:
```bash
# after spawning a real session through the app, confirm which container
# actually owns the spawned process (the claim under test)
docker exec <new-owner-container> ps -ef | grep <expected-binary>
# then prove survival: stop the OLD/other container mid-run
docker stop <container-that-should-no-longer-matter>
# confirm the spawned process is STILL alive (ps again, same pid)
docker start <container-you-stopped>
# confirm a fresh client can reattach and receives contiguous state
# (no gaps/dupes in whatever sequence/cursor field the app exposes)
```
This is the pattern that gave concrete proof (not just "flag is set") that a
dashboard-restart-survives-in-the-supervisor architecture change actually
worked live on prod.

## 13. A human adds an in-scope requirement AFTER the tracked task already reached `done`

`tier2-orchestration` (manually-authored, off-limits to autonomous edits) has no
"reopen a done task to running" transition — `hermes kanban edit` on a `done`
task only touches `result`/`summary`, not status, and there's no direct
un-complete verb. This surfaces when a human's follow-up instruction arrives
post-merge (e.g. "you must also root-cause and fix the deploy bug you hit" after
the original PR is already merged and the task marked done).

**Don't fight the state machine — track via comments, drive the fix as its own
unit:** `hermes kanban comment <task_id> "<progress note>"` on the same (done)
task keeps the audit trail attached to the right place. Drive the actual fix as
a fresh dispatch: new branch off the current `main` (the original branch/worktree
is already merged and gone — don't try to resurrect it), same
`claude_orchestrate` session pattern, same verify-yourself discipline (run the
real test suite, don't trust the session's self-report). If a new PR results,
link it back with a comment on the original task rather than trying to reopen
it. This is the same "comments substitute for a transition verb that doesn't
fit the state model" pattern as §9's `ready`-status heartbeat quirk — don't burn
cycles hunting for the "correct" reopen command; it doesn't exist for this case.

## 15. Full production smoke-test checklist: proving EVERY user-facing path for real, not just the one you already validated

When a human asks to exercise every user-facing path for real on prod after a
risky architecture change goes live (not just the one path already proven by
the e2e that unblocked the merge), treat it as a distinct deliverable with its
own checklist — don't assume the earlier e2e's coverage generalizes.

**Method:**
1. Enumerate every distinct user-facing surface as a todo list BEFORE touching
   prod: interactive/foreground usage, unattended/auto-invoked usage (cron,
   auto-orchestrator, webhooks), batch/report jobs, build/publish/deploy tooling,
   the read API surface, session-lifecycle edges (init-on-already-initialized,
   restore, error-mid-turn, idle/orphan cleanup), and any cross-service sync
   (Drive, S3, queues) the change could have regressed.
2. For each item, run the REAL path (real CLI process, real trigger endpoint,
   real container restart) — not a mock — and verify with real evidence:
   process ancestry (`ps` showing which container/pid owns the spawned
   process), log lines with the actual completion/stop_reason, or an artifact
   file's field values (see §14 — never trust a self-report or a bare "worked").
3. Keep the real service continuously healthy throughout: confirm the health
   endpoint / `docker ps` after every restart or kill you perform as part of a
   test, before moving to the next item.
4. Post the result as a table (`path | exercised | result | evidence`) on the
   tracking task — a prose summary is not sufficient for a checklist deliverable;
   the table is what lets a human audit coverage at a glance.
5. **Explicitly name any boundary you did NOT cross**, with why, rather than
   skipping silently or doing it anyway. A real content publish (pushes to
   prod S3/CloudFront), a real payment, or any other customer-facing mutation
   discovered mid-smoke needs the same "explicit approval before impactful
   shared-infra actions" gate as everything else — prove the tooling/gate up to
   that boundary (e.g. the render queue is reachable, preflight runs clean) and
   stop there, naming exactly what a go-ahead would unlock.
6. **Distinguish a real defect from by-design behavior surfaced during
   exploration.** Smoke testing routinely turns up things that look alarming
   in isolation but are intended — e.g. a completed interactive session whose
   viewer disconnected still holding its lesson lock, because the owning
   service intentionally keeps the runtime attached for re-attach until an
   orphan TTL elapses. Verify the mechanism (check the actual TTL/reap code
   path) before reporting it as a bug; if it's intended, report it as an ops
   note (what an operator should expect) rather than a blocking finding.
7. Clean up your own test artifacts (synthetic test-lesson sessions/locks,
   scratch files) at the end so they don't linger looking like real orphaned
   state to whoever looks at prod next; note anything you couldn't clean
   immediately (e.g. a lock waiting on its TTL) so it isn't mistaken for a leak.

## 16. A deploy run reporting `exit 1` right after the critical work succeeded is often an SSH-session drop, not a new script bug

After fixing a deploy-atomicity defect (§12) and re-triggering the deploy via a
follow-up merge, the run can still show `exit 1` even though the swap/health-gate
logic you just fixed worked perfectly — the box IS on the new image, healthy,
correct env. Don't reflexively treat this as "another bug in the same deploy
step" and start re-reading the script for a second ordering flaw. Two things
recur together in this shape:

- The run's captured stdout ends cleanly right after an expected mid-script echo
  (e.g. a staging-container cleanup line) — no error text, no stack trace, just
  silence then `Process exited with status 1`.
- The box's real state (checked read-only via SSH/docker inspect) already
  matches what the LATER parts of the script were supposed to produce (new
  image running, healthy, correct env vars) — meaning those later steps DID
  execute, they just didn't get to finish echoing/exiting cleanly inside the
  same CI-captured SSH session (e.g. `appleboy/ssh-action`'s connection can
  drop after the remote work completes but before its own exit-code plumbing
  finishes, which the Action reports as `exit 1` regardless of what the remote
  script actually returned).

**Diagnostic order — verify real state before hunting for a new defect:**
1. Read what the log actually captured (`gh run view <id> --log-failed`), find
   the exact last printed line, and note there's no error message at all
   between that line and the exit — that absence is itself the tell (a real
   script failure under `set -euo pipefail` prints the failing command or at
   least stops with context, it doesn't just go silent).
2. SSH to the box and check the actual current state against what the deploy
   was supposed to produce: `docker ps` (right images/health), `docker inspect
   --format '{{json .Config.Env}}'` (right env), and any deploy-tail action
   (e.g. a defs-publish/activate step) run manually — if it succeeds cleanly
   when run directly, the script logic itself is sound; the CI-reported
   failure was transport, not logic.
3. Only if the box's real state does NOT match the expected outcome (a step
   genuinely didn't run, or ran with wrong effect) should you treat it as a new
   defect and go back to reading the script for a second bug.
4. Report the box's verified real state as the ground truth in your final
   status ("script logic is correct and verified twice — live re-run + a
   dry-run — the run's `exit 1` was an SSH-transport artifact after the swap
   completed, not a code defect"), rather than either declaring the deploy
   fully proven from CI's green/red status alone or panicking into a third
   patch round for a defect that isn't there.

This complements — doesn't replace — §12's rule that "verified" for a deploy
fix means watching a real re-triggered run to completion: watching it is still
required; this section is about correctly INTERPRETING what you see when that
real run's own reported exit code disagrees with the box's actual state.

## 17. `claude_orchestrate gate`'s `impl` verdict can misfire to "zero changes" when the rundir was captured mid-checkout — verify with real git before trusting it

`tier2-orchestration` Phase 3.1 treats `gate`'s `impl:fail` (empty diff) as
ground truth that Phase 2 produced nothing and should be re-run. This can be a
false negative, not a real absence of work: if the coding/implementation
session's `claude_orchestrate start` was issued (or the worktree checkout was
still settling) before the surrounding orchestration finished switching into
the correct worktree — e.g. you resumed/reclaimed a task whose prior session
had already started against a worktree path you hadn't `cd`'d into yet — the
gate's captured rundir points at the wrong directory (or the pre-checkout
state of the right one) and reports "zero changes" even though dozens of real
commits and thousands of lines of diff exist on the branch.

**Observed:** a T2 resume on a task with 5 phases of work (drive_sync removal,
runtime-fallback removal, host-wiring, docs, plus a post-review fix commit) —
31 commits ahead of `origin/main`, 57 files changed, +2190/−3467 — had
`claude_orchestrate gate` report `impl:fail` / zero real changes. The task was
in fact code-complete; the gate had captured its rundir before the resume's
worktree checkout had fully switched over.

**Rule — never let a `gate` `impl:fail` alone send you back to Phase 2:**
before re-dispatching a coding session over what you believe is a false
negative, verify directly in the actual worktree:
```bash
git log --oneline origin/<base>..HEAD    # real commit list
git diff --stat origin/<base>...HEAD     # real changed-files summary
```
If real commits/diff exist, the gate misfired — proceed to review/tests on the
real evidence instead of re-running the implementation phase over completed
work. Only trust `impl:fail` as genuine when these two commands also show
nothing ahead of base.

## 18. Before opening a PR for a task, check for a stale PR from a prior run — don't assume a clean slate

A resumed/reclaimed T2 task can have a leftover PR from an earlier session that
no longer represents the real work: opened as a docs-only stub, or based on a
branch that was itself built on another PR that has since gone stale/unmerged.
Opening a second PR without checking leaves two competing PRs for one issue and
confuses the human reviewer.

**Before opening a PR, check:** `gh pr list --head <branch>` for the exact
branch you're about to push, AND search by title/kanban history for any older
PR tied to this task_id/issue on a differently-named branch. If one exists,
read its diff (`gh pr diff <N> --stat`) and base
(`gh pr view <N> --json baseRefName,headRefName`) — a PR that's a small
docs-only stub, or based on an unmerged/stale branch, while your current
worktree branch has the real, current, complete work (check `git diff
origin/main...HEAD --stat` for a substantive net diff) is stale, not a
duplicate to merge with.

**Resolution:** push your real branch and open a fresh PR against the current
base. Then close the stale one with a one-line comment pointing at the new PR
number and why (e.g. "superseded — built on an old/unmerged base; see #<new>
for the current, complete cutover"). Don't try to force-rebase the stale PR's
branch onto the new work — replacing it is cheaper and clearer than untangling
history that was never really shared.

## 19. Briefing a coding agent to write docs/comms about in-progress infra: pin down current-state facts yourself first, then audit the diff for premature "done" claims

Delegating documentation or team-comms writing about a system that's mid-migration
(a feature flag partially rolled out, a retirement in progress, a fallback path
still live) has a specific failure mode: the coding agent's natural drift is to
describe the END state as already true, because that's what the surrounding
code and PR titles suggest the work is "about." A generic instruction like
"document the recent architecture changes" is not enough to prevent this.

**Before writing the brief:** verify the exact current-state facts yourself by
reading the real source (`grep`/`read_file` the actual flag defaults, actual
deploy script branches, actual current main — not memory of what a related PR
claimed to do). Identify every claim that would be true post-completion but is
NOT true yet (e.g. "the in-process fallback is removed" when it's still the
default-unset code path; "the Linux host is retired" when that cutover is a
separate unmerged draft PR).

**In the brief itself:** state each such fact as an explicit constraint, not
just background — "the in-process fallback still exists and is the CURRENT
default-unset path; document it as present, do NOT say it is removed" reads
very differently to a doc-writing agent than leaving it implicit. Pair every
"describe X as done" risk with an explicit "must NOT describe Y as done."

**After the agent reports done — verify, don't trust the self-report** (this is
the docs-writing form of §14's "read the artifact, not the narrative"):
`git diff <base>..HEAD` the actual files changed, then `grep` the diff itself
for the forbidden claim patterns before accepting the PR as accurate, e.g.:
```bash
grep -rniE "fallback.{0,40}(removed|eliminat|gone|no longer)" docs/
grep -rniE "<subsystem>.{0,30}(retired|removed|decommissioned|is gone)" docs/
```
A clean grep plus a spot-read of the new sections is the actual verification —
"the agent said it followed the constraint" is not.

## 20. Stray side-fix PRs opened outside the tracked task go unnoticed until someone asks "why is this open"

A coding session working one task sometimes discovers an unrelated real bug in
a dependency mid-flight and ships it as a SEPARATE PR stacked on the same base
branch, instead of folding the fix into its assigned task's PR. Observed: while
switching an SVG-generation component's model, the session found that a
sanitize-retry call path had the OLD model hardcoded (bypassing the new
configurable param entirely) and opened a standalone one-line-fix PR for it.
That PR carried no kanban task_id, never showed up in `hermes kanban list`,
and sat open and forgotten for the rest of the workstream — surfaced only when
a human spotted it days later and asked why it was still open.

This is a real gap, not a false alarm: the PR fixed a genuine bug (an edit-mode
call site would otherwise have silently kept running the pre-switch model), so
closing it without merging would have been wrong too. The failure mode is
purely about VISIBILITY, not correctness — a PR the tracking system doesn't
know about is a PR nobody is accountable for merging.

**Rule for anyone driving a stacked-PR workstream (T1 or T2):** periodically
cross-check `gh pr list --repo <org>/<repo> --state open --json
number,headRefName,baseRefName,title` against your tracked stack's branches.
Any open PR whose `baseRefName` is one of your stack's branches but whose
`headRefName` isn't a branch you're actively tracking is a stray. Read its
diff (`gh pr view <N> --json commits` / `gh pr diff <N>`), confirm the fix is
real and still needed against the current tip (not stale/superseded by a
later change), and merge or close it explicitly — don't leave it to be
discovered by someone else asking "why is this open."

**Prevention:** when briefing a coding session for a task, tell it explicitly
that any side-fix PR it opens for a bug found outside its assigned scope must
be commented onto the task it was discovered from (PR link + one-line reason),
so the tracking system has a pointer to it even though it isn't itself a
tracked task.

## 14. A session's own evidence artifact can contradict its prose summary — read the artifact, not the narrative

Never accept a coding/e2e session's chat description of its own evidence file
as equivalent to reading the file. Observed: a live e2e scenario's evidence
JSON recorded `duration_s: 430.4` and the "drive completed" assertion as
`FAIL`, while the session's own summary reported "17/17 PASS (11.8s)" — a
detailed, specific-sounding, and simply wrong narrative built on top of a
correct artifact. The mismatch only surfaced because an independent re-run
was done and it failed identically (2/2), which then traced to a real root
cause (a drive spawned without the gateway auth env + model slug, so an
auth-error result with no `stop_reason` was misclassified as success by the
harness's completion check).

**Rule:** whenever a session reports a pass/fail count or timing for
something that also wrote an evidence artifact (JSON, log, report file), open
that artifact and check the actual field values yourself before accepting the
summary — regardless of how confident or granular the summary sounds. Treat a
detailed self-report as a claim to verify, same weight as a bare "tests
pass," not as evidence in itself. If artifact and narrative disagree, the
artifact is the fact and the disagreement itself is a signal to independently
re-run before trusting anything else the session reported in that turn.
  githubstatus.com — wastes a fix-and-repush cycle chasing a non-existent bug.
- Chasing a hung/failing test as a real diff regression without first re-running
  it in a sanitized env and diffing against base — see §7. A stray shadowing
  package or your own supervising shell's `PYTHONPATH` produces failures
  indistinguishable from a real regression until you isolate the env variable.
- Repeatedly force-pushing/rerunning during a confirmed outage — doesn't help,
  and produces a pile of wedged runs to sort through once Actions recovers.
- Writing "post-merge verification" as prose reassurance ("this should work
  once deployed") instead of literal runnable steps + a concrete pass criterion.
- Advancing the tracking task past its parked state, or merging, without the
  human's explicit go-ahead once they've said to wait for it.
- Declaring a PR clean based on the last `gh pr checks` you happened to look at
  — checks from apps outside your own workflow file (security scanners, etc.)
  can flip red on a later push without you noticing; always re-pull the full
  list on demand.
- Hand-editing source directly as T2 "because it's tiny" — no size threshold
  makes this okay under the T2 boundary rule; always route through a coding
  session.
- Fixing CI-only undeclared-dependency failures one push per missing package —
  grep the full import graph (including subprocess/hook scripts the new tests
  invoke) against the component's declared deps in one pass instead.
- Trusting `--delete-branch`'s single combined error when run from a worktree —
  check `gh pr view --json state,mergedAt` before assuming the merge itself
  failed; it's usually just the branch-delete half that choked on the worktree.
- Calling `hermes kanban heartbeat`/review-transition verbs on a manually-driven
  task and treating the `ready`-status rejection as a real blocker — it's a
  status-model quirk (claim doesn't set `running`); track progress via comments
  instead of chasing the "correct" transition command.
- Accepting a session's prose description of its own evidence artifact instead
  of opening the artifact — a detailed, specific-sounding summary can still
  contradict the actual pass/fail fields and durations recorded in the file it
  generated.
- Treating a deploy run's own `exit 1` as proof of a NEW defect without first
  checking the box's real state — §16: if the log ends silently right after an
  expected echo (no error text) and the box already shows the correct
  post-deploy state, it's an SSH-transport drop after the work succeeded, not
  a second script bug to chase.
- Accepting `claude_orchestrate gate`'s `impl:fail`/"zero changes" verdict at
  face value and re-dispatching Phase 2 — §17: check `git log`/`git diff
  --stat` against base in the real worktree first; a stale-rundir capture
  during a resume/reclaim can report zero changes over 30+ real commits.
- Opening a fresh PR without checking for a stale one from a prior run first —
  §18: `gh pr list --head <branch>` + check any older PR on the same task before
  assuming a clean slate; a docs-only stub built on an unmerged base needs to be
  superseded and closed with a pointer, not left dangling alongside a new PR.
- Briefing a coding agent to write docs/comms about in-progress infra without
  pinning current-state facts yourself first — §19: verify flag defaults/rollout
  status against real source before writing the brief, bake "must NOT describe
  Y as done" constraints explicitly, then grep the actual diff for forbidden
  claim patterns before trusting the "I followed the constraint" self-report.
- Trusting `hermes kanban list`/board state alone as the complete picture of
  open work on a stack — §20: a side-fix PR a coding session opened for an
  unrelated bug it found mid-task has no task_id and won't appear there;
  periodically diff `gh pr list` against your stack's tracked branches to
  catch these before a human has to ask "why is this open."
