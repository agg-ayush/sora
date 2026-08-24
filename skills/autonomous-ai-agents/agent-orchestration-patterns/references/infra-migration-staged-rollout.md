---
name: infra-migration-staged-rollout
description: "Judge and drive the merge/rollout gate for infra or platform-migration work (moving a production service to new infra: new host OS, new region, new runtime, new deployment topology). Use whenever an orchestration skill (tier1-suborchestration, tier2-orchestration, or a human directly) is deciding whether a code-complete, gate-passed, PR-approved migration branch is actually ready to merge. For this class of task, PR approval is NOT the merge trigger — live deployment + real-world validation on a staging host, with the old system kept running untouched, is the actual exit bar. Complements tier1/tier2-orchestration without editing them (those skills are manually-authored and off-limits to autonomous edits)."
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Orchestration, Infra, Migration, Rollout, Tier-2]
    related_skills: [tier2-orchestration, tier1-suborchestration, aws-worker-fleet-drift-audit]
---

# Infra/platform-migration staged rollout

Governs one specific decision point that the tier1/tier2 orchestration skills
don't cover: **when is a migration branch actually ready to merge?** For a
normal feature/bugfix PR, "gate passed + human approved the PR" IS the merge
trigger. For a task that migrates a live production service to different
infra (new host OS, new cloud region, new deployment topology, swapping a core
dependency like the filesystem/sync layer), that's necessary but **not
sufficient** — the human may require live proof before cutover.

## Trigger: how to recognize this class of task

The task is an infra/platform migration if it changes WHERE or HOW a
production service runs (not just what its code does): new host OS
(Linux→Windows), new region, containerized→VM or vice versa, swapping a
storage/sync mechanism the service depends on, etc. It is NOT this class if
it's a normal feature/bugfix that ships the same way the service always ships.

The strict-gate signal, when the human says any of:
- "don't merge until we've proven it works for real"
- "keep the old system running in parallel" / "the old one stays live"
- "give it a domain, run it under real usage, then decide"
- "once we're sure then we'll retire the old one"
- "I want it 100% accurate / 100% bug-free before we change production"

Any of these overrides the default approve→merge path from
`tier2-orchestration` Phase 4. Treat PR approval as a **checkpoint**, not the
finish line.

**This class isn't limited to literal host/region migrations.** A same-host
architectural refactor that changes WHO OWNS a production process's lifecycle
(e.g. decoupling long-running agent sessions from the dashboard process so
updates no longer kill them) carries the same risk shape as an infra
migration — a large diff, a claimed behavioral guarantee (survives restart,
reattach works, no dual-ownership races), and CI-green-with-mostly-unit-tests
that cannot actually exercise the claim. Apply this skill's gate to that case
too when the human invokes the strict-gate signal, even though no host/region
is changing.

## What the exit bar becomes

1. **PR stays open, un-merged.** It's a staging artifact, not a merge
   candidate, until live validation is confirmed.
2. **Stand up the real target infra from the branch** — actual host/
   container/service, deployed and configured, not just code review.
3. **Give it a reachable staging endpoint** (domain/subdomain) so it can be
   hit and tested the way production would be.
4. **Run the full e2e/smoke suite against the live staging deploy** and drive
   real usage on it — CI passing on the diff is not the same claim.
5. **The old production system stays live and untouched throughout.** Never
   retire or modify it as part of this phase — that's a separate, later,
   human-approved step.
6. **Deliverable of this phase is a go/no-go report on cutover**, not a merge.
   Actual merge + old-system retirement requires an explicit follow-up
   approval — don't fold it into "the design/code looked right."

## Provisioning technique notes (worked example: staging a Windows EC2 host off a migration branch)

- **Region/host choice — verify, don't guess.** Confirm IAM/service access in
  each candidate region before picking (e.g. `aws ec2 describe-vpcs --region
  <region>` must return something, and check the target AMI/service is
  available there). Break ties with real latency numbers (ping/curl
  round-trip from the relevant vantage point), not assumption. A dependency
  living in a different region than your new host (e.g. an existing SQS queue)
  is usually fine to leave cross-region for async work — don't over-index on
  co-location.
- **DNS — check before asking.** Look for an existing hosted zone
  (`aws route53 list-hosted-zones`) that already covers the desired hostname
  pattern before assuming a manual DNS handoff is needed. If the zone is
  in-account and the role can manage it, the migration session can create the
  record itself. Only surface it as a blocker if the zone is genuinely absent
  or access is denied — with the exact error, not a guess.
- **Secrets — file handoff, never inline.** Don't have the human paste secret
  values into chat or a command. Fetch/mirror the source credentials to a
  local file instead (`ssh <src-host> "sudo cat /path/.env" > /tmp/name.env`,
  or pull a service-account JSON out of a running container via `docker exec
  <container> cat <path>`), then hand the migration session the **file path**,
  not the values, with an explicit instruction to read from disk and never
  print secret values into chat/logs. Mirror them into the target's own
  secret store (e.g. SSM Parameter Store as SecureStrings) with any
  environment-specific overrides the new topology needs (e.g. disable a sync
  mechanism that only existed because of the old topology; repoint storage
  paths at the new host's mount).

## Validating real traffic through an auth-fronted staging endpoint

Once the staging host is up and healthz-green, "run real traffic against it"
needs a concrete plan when the endpoint sits behind an auth wall (oauth2-proxy,
SSO, etc.) that an automated session can't click through:

1. **Automated e2e/smoke first, direct against the backend** (bypass the auth
   proxy — hit the upstream port on localhost/the host itself, not the public
   auth-walled port). This gets you real functional + latency evidence without
   needing a human or a headless-browser OAuth flow. Treat the auth proxy
   itself as already proven separately (healthz 200 + serving the expected
   401/403 sign-in wall to unauthenticated requests is sufficient proof it's
   wired correctly).
2. **A short human-driven window through the real public domain** (actual
   login, actual UI) to validate the piece automation can't reach — the auth
   flow itself and end-user-perceived experience. Don't skip this in favor of
   (1) alone; automated backend checks don't prove the auth wall + DNS + public
   path work together.
3. Present both as the two-part validation plan and let the human choose
   sequencing/timing for (2) — don't unilaterally decide "the API checks are
   enough" and treat the migration as fully validated without a real login
   pass by an authorized human.

## When `clarify` goes unanswered mid-migration

An orchestrator session that hits a genuine decision point (region, DNS,
mount mechanism, rollout go/no-go) still needs the human's answer even if the
interactive `clarify` call comes back empty / never renders on the user's
side. Don't block silently and don't guess at the decision:

1. Retry `clarify` at most once — if it comes back empty again, stop relying
   on it for this decision.
2. Escalate through a **durable, out-of-band channel** instead: post the full
   decision (options, trade-offs, what you'll do on each choice) as a comment
   on the tracking artifact (kanban card, tracking issue, or PR) AND, if a
   notification channel is configured, ping it directly. Then hold — keep
   working on any genuinely independent sub-tasks, but do not proceed past the
   actual decision point on a guess.
3. When the human's answer does arrive (often as a plain follow-up message
   rather than a clarify response), treat it as authoritative and proceed —
   don't re-ask or re-litigate a decision that's already been made this way.

## Concrete evidence to gather for "real traffic validated" (not just healthz)

A go/no-go report is weak if it's just "smoke suite passed." Gather
quantitative, source-backed evidence of the specific thing the migration
changes:

1. **Hit the real API/app surface directly**, not just a synthetic probe —
   e.g. the actual dashboard's list/detail endpoints — and record real
   latencies (ms) and payload sizes from real data on the new infra.
2. **Run one real end-to-end workflow the service actually performs in
   production** (a full job/build/pipeline cycle, not a stub) and capture its
   wall-clock time and outcome. This is the strongest single piece of
   evidence — it exercises the new infra under the same load shape prod sees.
3. **Prove the specific risk the migration was meant to fix, numerically.**
   If the migration removes a blocking-sync step, don't just claim it's gone —
   count the relevant process (`Get-Process <name> | measure`, `pgrep -c`)
   before/during/after the real workflow and show the count never spikes.
4. **Do a write→readback round trip** on whatever storage layer changed
   (mount, DB, cache): time the write, time an immediate readback, assert the
   content matches. This proves durability and surfaces async-vs-blocking
   write behavior (e.g. a VFS cache accepting a write in ~1s while the actual
   upload happens in the background is correct, not a regression — don't flag
   it as slow without checking whether it's synchronous or queued).
5. **Run the test suite ON the target host itself**, not only on the dev
   machine that built the branch. A suite green in the worktree/CI environment
   can still fail on the real target due to host-specific ambient env (see
   pitfall below) — that gap only shows up by actually executing there.

## Process-lifecycle-decoupling refactors need a real e2e, not just gate-green

When the migration/refactor is "stop process A's lifecycle from killing
process B" (e.g. separating a supervisor's session-owning role from a
dashboard's restart cycle), "45/45 CI green" typically means unit tests
against a fake runner — it does NOT prove the actual guarantee. Before this
class of change is presented as ready to merge, insist on (or build) a test
that:

1. Starts the real components as they'll run in production (not a fake/mock
   of the owning process).
2. Spawns a REAL long-running worker (the actual CLI/agent process, not a
   stub) under the new ownership model.
3. Kills/restarts the process that used to take the worker down with it, while
   the worker is still mid-run.
4. Asserts the worker is still alive, completes normally, and that any
   viewer/reattach path sees correct, non-corrupted continuity (no
   duplicated/lost/mis-ordered state from the reattach).
5. Also proves the negative/race cases the new ownership model exists to
   prevent (e.g. two owners can't double-claim the same job; a stale lock from
   a dead owner is reclaimed, a live owner's lock is not).

Treat a PR for this class as not-ready-to-merge until this real e2e exists and
passes, regardless of unit-test coverage or review approval — this is the
same "PR approval is not the merge trigger" principle as a host/region
migration, just applied to process ownership instead of infrastructure
location.

**Verify the unattended/auto-invoked trigger path separately from the
interactive one — they can diverge even when both claim to route through the
same new ownership model.** A hand-spawned interactive session surviving a
restart does NOT prove an auto-orchestrator, scheduled trigger, or headless
drive path routes through the identical spawn/ownership code — they can use a
different spawn helper or env-injection path that only the interactive one
got updated for real (observed: a headless drive spawned without the gateway
auth env + model slug that the interactive path injected, hanging
indefinitely on an unhandled auth-error result). When a human asks "did you
test the auto-invoked path, not just a manual session?", that's a legitimate
distinct gate, not a restatement of the same test:
1. Fire it via its REAL entry point under a controlled single-shot call (a
   token-gated trigger endpoint), not by flipping on blind unattended auto-fire
   in prod.
2. Confirm the resulting worker process is parented to the new owner (`ps`
   ancestry inside the owning container), exactly like the interactive check.
3. Kill/restart the coordinator (dashboard) mid-run; confirm the unattended
   work is unaffected and completes afterward.
4. Confirm capacity/lock/lease accounting reflects the unattended session
   correctly and releases cleanly when it stops.
5. Clean up test artifacts (stop the session, confirm the lock releases)
   rather than leaving verification state on the live host.

**When the human asks "was X actually tested e2e?" about a PR that already has
an owning orchestration session (a T2/supervisor), don't personally `gh pr
view --json files`, diff the PR, or read test contents to answer it yourself.**
The owning session has full context on its own test suite and can self-audit
and fix faster and more accurately than a fresh outside read. Steer the OWNING
session with the concrete bar ("prove it survives a real restart with a real
process, not a fake runner") and let it investigate, build the missing e2e, and
report back — don't duplicate its work or risk a second writer touching the
same deliverable.

## Windows-host infra-script pitfalls (recurring across migrations to a
Windows target)

- **PowerShell scripts must be pure ASCII.** A UTF-8 em-dash/arrow/curly-quote
  saved into a `.ps1` (easy to introduce via an editor or copy-pasted prose)
  can silently break string termination inside a `throw "..."` and produce a
  cryptic parse-time FATAL far from the real cause. Grep infra `.ps1` files
  for high-byte characters before trusting a "script failed" error at face
  value; fix by re-saving as ASCII.
- **Windows Server AMIs do not ship AWS CLI v2 by default.** If any setup
  script shells out to `aws` (e.g. to sync SSM parameters into a local `.env`),
  the install step for AWS CLI itself must be explicit in the script — don't
  assume it's present just because the SSM *agent* is (the agent and the CLI
  are unrelated). A script that swallows the underlying `CommandNotFoundException`
  and reports a generic "file not found" downstream wastes a debugging cycle;
  make such wrapper functions surface the real exception.
- **When a specific OS service-registration mechanism (e.g. WinFsp Launcher)
  resists multiple fix attempts (registry view, quoting, using the vendor's
  own registration tool) and a simpler proven-working alternative exists (e.g.
  wrapping the same binary as an NSSM service)** — stop iterating on the
  original mechanism once you've tried the standard fixes, adopt the working
  alternative, and bake it into the idempotent setup script as the canonical
  path. Don't keep chasing full root-cause on the broken mechanism once a
  pragmatic, equally-correct alternative is proven live — surface it to the
  human once as a decision point, then finalize on their answer rather than
  keep iterating.
- **Verify the actual name of any AWS resource an IAM policy targets before
  writing the policy** — don't infer a queue/bucket/topic name from convention
  or a related resource's name. A guessed name (e.g. `render-jobs.fifo` vs. the
  real `video-render-jobs.fifo`) produces a policy that looks complete but is
  silently wrong until the first live call returns AccessDenied. Always
  cross-check with a `list`/`describe` API call against the actual account.
- **A fresh Windows host has NO inbound firewall rules for any new port by
  default**, regardless of the security group being open. This bites twice in
  the same migration: once for the app's own service port (e.g. oauth2-proxy
  on 8800 — SG open, but external curl times out until you add a
  `New-NetFirewallRule -Direction Inbound -Protocol TCP -LocalPort <port>
  -Action Allow`), and again for ACME's HTTP-01 challenge on port 80 (a LE
  client will time out identically if 80 isn't allowed inbound, even with the
  SG already permitting it). Add the Windows Firewall rule proactively for
  every port a setup script opens, not just the SG rule — a SG-open/timeout
  symptom pair almost always means the AWS-side rule is fine and the OS
  firewall is the actual blocker.
- **Long-running builds/polls driven via SSM `send-command` can outlast a SAML
  session token (~1h TTL).** A poller that loses creds mid-build looks like the
  *build* failed (empty output, `ExpiredTokenException` buried in stderr) when
  it's actually the poller's AWS identity that expired. Refresh credentials
  proactively before/during any poll loop expected to run close to or past the
  token TTL, and don't read "no new output" as a build failure without first
  checking the poller's own AWS call succeeded.
- **A test suite can pass on the dev machine and fail on the real target host
  due to ambient env leaking between tests** (e.g. a deployed host legitimately
  has `DRIVE_SYNC_DISABLED=1` set at the OS level; the dev machine doesn't).
  If a test file lacks an autouse fixture that resets every env var the module
  under test reads, an earlier test in the same file/run can leak that var into
  a later test and make it fail only in the ambient-env-bearing environment.
  Fix by adding/extending an autouse `clear_deployed_env`-style fixture that
  clears ALL relevant vars (not just the one the original author thought of).

## TLS-parity gap behind an auth proxy (a config-diff fix is often not the whole story)

Section 3 above says a real human login pass is required before calling
auth-fronted validation complete. When that pass fails, don't stop at the
first fix that makes the error message go away — verify the whole chain:

- **A migrated host's oauth2-proxy/SSO wrapper commonly ships with config
  copied verbatim from the old host** (redirect-url, cookie-domain hardcoded
  to the OLD public hostname). Symptom: Google OAuth completes, callback
  comes back `403 — Unable to find a valid CSRF token`, even though the
  service is healthz-green and the process command line looks plausible.
  Fix: make the public hostname configurable (env var) and drive both
  redirect-url and cookie-domain off it.
- **That fix alone can still not be sufficient.** Check what actually
  terminates TLS on the OLD system before assuming the new host just needs
  the same cookie config — query it (e.g. `aws cloudfront list-distributions`)
  rather than assume a CDN fronts it; the old proxy may terminate TLS itself
  with its own cert. If the new host has no TLS termination layer at all,
  `cookie-secure=true` will never send the cookie back over plain HTTP and
  login keeps failing regardless of the redirect-url/cookie-domain fix. This
  gap **will not show up in healthz checks or a process command-line
  inspection** — only a real login attempt proves the whole chain (redirect
  URL + cookie domain + cookie-secure + actual TLS termination) works
  together. Surface the trade-off (plain-HTTP staging, a host cert, or a\n  CDN in front) to the human as a decision, don't default to weakening\n  cookie security silently.\n- **Self-hosted-cert fix, when the human doesn't want to wait for CDN/LB\n  setup:** issue a Let's Encrypt cert directly on the host via `win-acme`\n  (Windows) using the HTTP-01 challenge on port 80, then point the auth\n  proxy's own TLS flags at it (oauth2-proxy: `--https-address=0.0.0.0:443\n  --tls-cert-file=<chain.pem> --tls-key-file=<key.pem>`), keeping the plain\n  local port (e.g. 8800) alive for host-local checks. Gate serving HTTPS on\n  cert presence (`if (Test-Path $tlsCert) { add the tls flags }`) so the setup\n  script stays idempotent whether or not the cert exists yet. HTTP-01 needs\n  port 80 reachable — see the Windows Firewall pitfall above; SG-open but\n  ACME-still-times-out means the OS firewall, not AWS, is blocking it.\n- **Prove the fix headless before asking for the human login pass**: hit\n  `GET /oauth2/start` and confirm a 302 to the IdP with the correct\n  `redirect_uri` plus a `Set-Cookie` for the state/CSRF token scoped to the\n  right `Domain` and marked `Secure`; then replay that cookie against\n  `/oauth2/callback` with a deliberately bogus `code`/`state` — if the CSRF\n  check now passes, the response changes from the CSRF `403` to a `500`/`400`\n  from the IdP's own code-exchange (e.g. `invalid_grant: Malformed auth\n  code`). That state-cookie round trip is real evidence the whole chain\n  (redirect URL + cookie domain + TLS) works, without needing an actual IdP\n  login — only the final human-credential exchange remains unverifiable\n  headless.

## Delegate investigation to the owning session, not just fixes

The "don't personally audit the PR, steer the owning T2" principle above (for
"was X tested e2e?") generalizes to ANY investigation or comparison task on a
migration under an owning T2/supervisor — not just test-coverage questions.
Examples: "check if the new host handles everything the old one does",
"search the old system's logs for usage patterns we might have missed",
"compare X between old and new." The owning session has full host access,
full context on its own implementation, and can self-verify faster and more
accurately than the parent orchestrator poking at raw logs/SSH from outside.
If you catch yourself about to `grep`/`ssh`/read logs directly to answer a
parity or investigation question about a migration that already has an owning
T2, STOP — write the investigation as a brief (what to mine, what to compare,
what evidence to produce, where to report it) and hand it to the T2 instead.
This also keeps the parent orchestrator's context clean, which matters when
it's tracking multiple concurrent migrations/tasks.

## "Test every way you can, cost no object" — the exhaustive-validation checklist

When the human explicitly asks for exhaustive validation regardless of cost
(a stronger signal than the default "prove it e2e" bar), expand a single
happy-path e2e into a full scenario battery and actually run all of them
before reporting done. For a process-lifecycle-decoupling migration (see
above), the concrete battery that worked and is worth defaulting to:

1. **Multi-session restart survival** — restart the owning process with 3+
   real concurrent workers in flight, not just one.
2. **Repeated restarts within one run** — restart 2-3x during a single long
   worker session; assert no state drift/lost turns/sequence gaps across each
   restart, not just the first.
3. **Hard-kill (SIGKILL, not graceful) of the supervisor/owner itself** —
   assert the recovery behavior the design promises (dead locks reclaimed,
   live locks never clobbered).
4. **Client reconnect after restart** (e.g. same-tab WebSocket) — the
   reattach/resume path's own consistency guarantee (no duplicated/mixed
   sequence state) under a real reconnect, not just a fresh client.
5. **A long-running, multi-turn worker** under restart — a quick single-turn
   e2e doesn't exercise mid-turn interruption realistically.
6. **Concurrency stress** — many workers spawning/completing at once, to
   catch lock-correctness and cross-entity bleed that single-session tests
   miss.
7. **At least one real end-to-end round-trip through the actual production
   dependency** (real model/API call, not a stub) so the full chain is proven
   once, not just the plumbing around it.
8. **Failure injection** — kill the worker process mid-turn (simulate a
   crash) and a slow/hung worker, asserting the owner handles both without
   deadlocking.
9. **A soak run** (sustained load over minutes, several cycles) watching for
   leaks: orphaned processes, FD growth, lock-table growth.

Have the owning T2 run every scenario for real (not just add the test files),
capture evidence per scenario, fix any real defect at root, and re-run until
clean — then report a coverage summary that also states what's still only
unit-tested / not exercised live, so the human knows the actual residual risk
rather than assuming "exhaustive" means zero gaps.

## Mining real usage for a parity comparison when live logs are ephemeral

When asked to verify a migrated host is "equivalent to or surpasses" the old
one under REAL usage (not just what your own staging tests covered), don't
rely on the live container/process log if it was recently recreated/restarted
— that only shows recent activity, not the durable usage history. Look for
the durable, persisted record instead: for an agent/session-based app this is
usually the persisted session transcripts on disk (e.g.
`projects/**/*.jsonl`-style session logs), which retain the full history of
every tool/command actually invoked across all past runs, independent of
container lifecycle. Mine those for actual command/route frequency, then
diff structurally where possible (e.g. an API route inventory via the app's
own `openapi.json` on both hosts) rather than eyeballing feature lists — an
exact route-count/route-set match is much stronger evidence than "looks
similar."

## SSM PowerShell escaping applies to single-line edits too

The general rule (write PowerShell to a file, base64 it, `WriteAllText` it
onto the box, never hand-interpolate through JSON/bash/PowerShell tri-layer
quoting) isn't just for multi-variable one-liners or full scripts — it
applies to **any** content destined for a `.ps1`/config file pushed through
`aws ssm send-command`, including a single `Add-Content -Value '...'` line.
A backtick meant only to escape a `$` in the calling language (e.g. Python)
can leak through literally into the file on disk instead of being consumed,
corrupting a dot-sourced env/config file. The failure surfaces far from the
edit: a downstream service throws an opaque `CommandNotFoundException` and
sits silently `Paused`/stopped, with no obvious link back to the "trivial"
one-line append that caused it.

## Application-layer parity bugs (the app's own tooling, not infra plumbing) — a second bug class only real dogfood usage surfaces

Everything above (TLS, PowerShell escaping, AWS resource naming, ambient env)
is infra/plumbing-level. Once the host is up and healthz-green, running the
actual APPLICATION under real usage on it (not just synthetic smoke/e2e) can
surface a separate class of bugs in the app's own tooling that assumed a
specific host OS during original development — none of these show up in a
healthz check or an automated smoke suite, only in a human actually using the
migrated app:

- **Session/lock-ownership self-mismatch.** A lock file can contain the
  session's OWN id, yet the ownership check on the new host reports it "held
  by another session." Cause is usually how the session id is generated or
  read differing subtly across host (formatting, case, path-derived vs
  explicit) — fix by making the ownership check reentrant for a
  provably-same session, and add a regression check: same session
  re-initializing a lesson/resource it already locked must never trip.
- **Mtime-based staleness checks false-positive on synced/copied state.** If
  a staleness check compares a backup/cache dir's mtime against session start,
  and that dir was populated by a sync from a remote store (Drive, S3, rsync)
  that PRESERVES the source's original mtime, the check reads as stale
  immediately after a successful init — because the copied files carry an old
  timestamp, not "now." Fix by touching local mtimes to now right after the
  sync completes (if a touch-after-sync helper already exists in the
  codebase, find why it isn't running/applying rather than re-inventing one),
  or switch the staleness signal to a sync watermark / content hash instead of
  raw mtime comparison.
- **An identifier-detection regex over-matches option-like input.** A
  parser/regex that scans free-form chat/CLI input for a domain identifier
  (lesson id, ticket id, etc.) and spawns a session/entity per match can match
  a literal CLI flag echoed in the transcript (e.g. `--help`) as if it were a
  real identifier, silently creating a phantom session/entity. Any such
  detection regex needs an explicit exclusion for leading-dash/option-like
  tokens, not just a "looks like the id format" positive match.
- **PATH/tool visibility differs between the app's own launched shell and an
  interactive login shell on the new host.** A CLI tool can be genuinely
  installed on the host yet invisible to the app because the app's own
  service/session environment (however it's started — a Windows service, a
  dashboard's spawned shell, a non-interactive launcher) doesn't inherit the
  same PATH a human's interactive shell would. Bake the tool's location into
  the environment the app's own launcher defines (e.g. the service-startup
  script), rather than relying on the shell's ambient PATH or an in-run
  PATH fixup the agent has to improvise every session.
- **Internal state/contract reads becoming externally-visible shell calls.**
  If the app loads its own internal config/contract via a mechanism that
  differs across host (an internal read vs. shelling out to `cat`), a
  file that used to load silently can start surfacing as a visible tool call
  in the app's own UI/transcript on the new host. Not a correctness bug by
  itself, but worth root-causing (PATH/shell-availability difference is the
  usual cause) and fixing rather than leaving a visible implementation detail
  in front of the end user.

**Practical response when several of these land at once from one round of dogfooding:** don't
patch them ad hoc one at a time from a screenshot — batch them into one clear brief
to the implementer with the concrete repro for each (the file, the exact
mismatch), require a root-cause fix (not a symptom-level workaround) per item,
and require re-confirmation via a real end-to-end session on the live host
before reporting the round done. This is a normal, expected outcome of Section
"Validating real traffic..." above — real usage by actual users finds bugs a
smoke suite doesn't; budget for at least one such round on any app-level
migration, don't treat it as a sign the migration is broken.

## Structuring the migration branch as dual-target + purely additive (long staging periods)

A staged-rollout migration PR often stays open for a long validation window
(days) while the old system keeps running. Two structural requirements follow
directly from that, and the human may state them explicitly as a "structure
decision" separate from the earlier "don't merge yet" gate:

1. **The migration PR must be purely additive, not a replacement, even in the
   CI/deploy plumbing.** A common mistake: rewriting the deploy workflow to
   target only the new infra deletes the old deploy job entirely. Instead,
   make the workflow **dual-target** — the old job stays byte-identical to
   main (verify literally: diff the job body against main's after stripping
   only the lines you added; it must come back empty) and remains the
   default/automatic trigger (e.g. push-to-main), while the new target is
   **opt-in** via an explicit selector (a `workflow_dispatch` input like
   `target: linux|windows|all`, default = old system). Do the same for any
   runtime code path: gate every new behavior behind a flag that defaults to
   today's behavior, never invert the default.
2. **Scope the actual old-system removal as a separate, later, draft PR** —
   don't fold "delete the old path" into the migration PR even as an unused
   branch of an if/else. Base the cutover branch on the migration branch, open
   it as a **draft PR explicitly marked DO NOT MERGE** in its title/body, and
   land only the removal-scoped diff there (drop the old deploy job, delete
   the retired old-system code paths, retire old infra) — it merges only after
   the human signs off on the staging validation from the main migration PR.
   This keeps the reviewable diff for "is the new thing additive and safe"
   completely separate from "are we sure it's safe to delete the old thing."

**Keep a long-lived staging PR mergeable throughout the validation window.**
Main keeps moving while validation runs (could be many commits over days).
Periodically (and always before reporting the PR "ready"/"still ready")
`git fetch origin && git merge origin/main` into the migration branch rather
than letting it silently drift into `CONFLICTING`. When conflicts land in
files both sides touched: take the union — keep main's latest logic verbatim
and re-apply the migration's gating around it (e.g. re-wrap main's reworked
function body in the same `if flag_enabled():` guard the migration added,
rather than reverting to the migration branch's older copy of that function).
Re-run the affected test suites after the merge and re-confirm the additive
invariant still holds (flag-off behavior unchanged) before pushing — a stale
merge that silently drops main's concurrent fixes is worse than the conflict
it avoided.

**If a SIBLING branch already resolved the identical conflict shape (same
files, same main-side rework), reuse its resolution instead of resolving from
scratch.** Two branches off the same migration effort commonly touch the same
core files (e.g. a sync/lock module both a "retire the old path" branch and a
"fix a bug on the old path" branch depend on) — if one already merged main and
committed the resolution, diff the conflicted files against THAT commit first
to confirm no newer main commits have touched them since (if none have, the
resolution is still exactly correct), then take that commit's version
verbatim for those files, and only re-apply whatever your own branch adds on
top that the reference commit doesn't have. **Always re-diff the merged result
against the reference commit afterward, not just against your own pre-merge
state** — a 3-way auto-merge can silently keep a STALE version of a file that
wasn't part of the textual conflict (e.g. a hook/adapter file using an old
lock API that the reference commit's manual resolution had already updated),
because the auto-merge only flags files with literal conflicting hunks, not
files that are merely inconsistent with the *other* resolved files. Catching
this requires reading the reference commit's full diff and checking each
touched file exists with equivalent content in your result, not just resolving
the files git marked as conflicted.

**A kanban task can drift out of `running` (claim TTL expiry) while a long
implementation/merge session is in flight.** The `--to review` /
`kanban-review.py` transition helper (and `kanban complete`) REFUSE a task
that isn't currently in the state they expect (e.g. `ready` instead of
`running`). Before calling any kanban state-transition helper, re-claim first
(`hermes kanban claim <task_id>`) if there's any chance the TTL lapsed since
your last heartbeat — cheap and idempotent — rather than debugging a
transition-refused error after the fact.

## Verify flag-name semantics before relaying a flip instruction

When the human says "flip the flag to check it works unsupervised/off/old-way"
(or similarly names the STATE they want rather than the flag's literal value),
don't relay their wording verbatim to the owning session if the flag's actual
semantics invert it. Example that occurred: the human said "flipping the flag
to check it works unsupervised," but the flag in question was
`AGENT_RUNTIME=supervised` — flag SET = new supervised arch, flag UNSET = old
unsupervised/in-process behavior. Taken literally, the instruction would have
told the T2 to verify the wrong state. Before executing or relaying: check
what the flag's set-vs-unset values actually map to in code/config, restate
the correct mapping back explicitly (flag on = X, flag off = Y), and instruct
the owning session using the flag's literal value, not the human's behavioral
description of it — mismatched naming between "what a flag is called" and
"what state a human means" is a normal source of an inverted rollout step.

## Deploy-script atomicity is part of the go-live gate — audit it before cutover, not after it bites

A staged-rollout migration commonly ships a NEW deploy-orchestration step as
part of the change itself (e.g. "on merge, also stand up a new supervisor
container alongside the existing dashboard"). That new deploy logic is itself
unvalidated production code and is exactly the kind of thing that fails on
first real run: a real incident that happened — the merge's auto-deploy
script stopped/removed the OLD dashboard container, then the NEW
supervisor-container-creation step failed (health-wait exited 1), leaving
production with **no dashboard container at all** until manually restored.
This is a deploy defect, not an application defect, and it's easy to miss
because CI never exercises the actual SSH/deploy script against a live host.

Two concrete follow-ups from this:

1. **Treat "is the deploy script itself atomic" as an explicit go-live
   checklist item**, alongside the app-level e2e battery already covered
   above — read (or have the owning T2 read) the actual deploy script for
   this specific failure shape: does it stop/remove the currently-running
   service BEFORE the replacement is confirmed healthy? If yes, that's a
   pre-existing outage risk on every future deploy, not just this one — flag
   and fix it as part of the go-live work, don't wait to hit it live.
2. **The fix pattern is reorder-and-guard, not just retry**: start/create the
   new component and confirm it healthy FIRST, only then stop the old one
   (or: never let a failure in the new-component setup step cascade into
   removing the still-good old component). Add a guard so a failure in an
   ancillary/secondary component's startup (e.g. the new supervisor) can never
   abort the primary component's (the dashboard's) deploy.
3. **When this bites during a live go-live and the human says "make sure it
   gets fixed"** (not deferred to a separate task), that's page-1 "everything
   needed for the feature to work belongs in one PR" territory even though
   the defect is in CI/CD plumbing, not app code — the owning T2 should
   root-cause and land the deploy-script fix as an in-scope follow-up
   commit/PR on the SAME rollout effort, verified via an actual dry-run of
   the deploy path that keeps the real service up throughout, not deferred
   to "someone will fix it next time it happens."
4. **"Verified" for a deploy-atomicity fix means watching a REAL re-triggered
   deploy run to full completion, not just confirming the swap step worked.**
   After merging the ordering/guard fix, the merge itself re-triggers the auto-
   deploy — have the owning T2 watch that live run end-to-end rather than
   trusting the earlier on-box dry-run alone. A dry-run in a throwaway
   container can prove the reorder logic; it does NOT prove every later step
   in the real pipeline succeeds against the real host's actual state.
   Observed: after the swap+health-gate fixed the outage-causing ordering bug
   and the dashboard came up healthy, the deploy's LAST step (a defs-publish
   container) still failed — a `mkdir -p` in the deploy script created the
   defs directory root-owned, but the publish container runs as a non-root
   `appuser` (uid 1000), so it hit `PermissionError` on write. No outage (the
   dashboard had already swapped and was healthy by that point), but "the
   deploy works now" was still false until this was fixed too (`chown
   1000:1000` on the created directory as part of the deploy step) and
   re-verified live. Treat a deploy pipeline as multiple independently-failable
   stages (image swap, health-gate, supervisor bring-up, any post-swap
   publish/activation step) — a fix for one stage's ordering bug doesn't mean
   the whole pipeline is proven; watch the ENTIRE run to a clean exit before
   reporting the deploy fixed.

## Independent blind review before final merge sign-off (distinct from "delegate investigation to the owning session")

The pitfall above — don't personally grep/SSH/diff to answer an investigation
or parity question, write a brief and hand it to the owning T2 — is about
tasks where the owning session's extra context makes it faster/better
(building a missing test, mining old-host logs, comparing behaviors). It does
**not** apply to the final go/no-go review gate itself. When the owning T2
has already self-reported "100% tested, all green, ready for merge" on a
large/high-risk PR, that self-report has confirmation bias baked in — the
same session that wrote the code also wrote (and graded) its own tests. Get a
**second, independent opinion** from a fresh subagent with **zero prior
context** on the implementation, explicitly instructed to distrust the
author's claims and verify against the raw diff, not from the owning T2
re-auditing itself.

Brief the independent reviewer with:

1. **No shared context** — don't hand it the owning session's summary or
   findings; only the repo, PR number, and the architectural claim to verify
   in your own words ("session X should survive process Y restarting,
   reattach should preserve sequence continuity" etc.).
2. **An explicit instruction to hunt for the bug classes large refactors
   actually ship**, not just "review this diff": a value produced but never
   threaded to its consumer; a name resolved at the wrong scope so a wiring
   call is a silent no-op; a path off-by-one-directory reading the wrong
   file; error paths that swallow failures or deadlock; ownership/lock-reclaim
   logic that can't correctly tell a live lock from a dead one; a
   reconnect/resume path that can mix old and new sequence/cursor state;
   resource leaks (unclosed subprocess/socket/fd) in a long-running loop.
3. **An explicit instruction to check whether the e2e tests assert on real
   production behavior or on fakes/mocks that would pass even if the real
   wiring were broken** — point to specific assertions, not just "tests
   exist."
4. **A required verdict format**: APPROVE or REQUEST-CHANGES, findings each
   tagged CONFIRMED-DEFECT / SUSPECTED / QUESTION with file:line evidence, and
   explicit residual risks it could NOT verify — not a vague "looks fine."

This is complementary to, not a replacement for, the exhaustive-validation
battery above — the battery is real e2e evidence the owning T2 produces; the
independent review is a second pair of eyes checking whether that evidence
and the surrounding code actually support the claim.

## `gate`'s impl-complete check can misfire on a mid-flight worktree switch

If the plugin resolved a coding session's rundir before its worktree was fully
checked out or reassigned (e.g. you created/repointed the worktree partway
through the session, or two tasks briefly overlapped on directory setup),
`claude_orchestrate gate`'s `impl` verdict can come back `fail` / "zero real
changes" even though the branch has real commits ahead of base. Don't take a
surprising zero-diff verdict at face value on a long multi-phase
implementation — verify manually first: `git rev-list --left-right --count
<base>...HEAD` and `git diff --stat <base>..HEAD` **in the actual worktree
path** the work landed in. If real commits/diff exist there, the gate read the
wrong directory; proceed on the manual evidence, note the misfire in your
kanban comment, and don't re-run the implementation session to "fix" a defect
that doesn't exist.

## Two worktrees can never share one branch name — reassignment is a common self-inflicted trap

A branch already checked out in one worktree cannot be checked out in a second
worktree (`git worktree list` will show the collision). This bites in
long-running multi-task orchestration when an OLDER task's worktree gets
reassigned to a NEWER, unrelated task's branch (e.g. two kanban tasks against
the same repo, worked days apart, and the second one's setup step reused the
first's worktree directory) — you can end up with a "PR's branch" that no
longer has a live worktree checked out anywhere, while the directory you
expect it in actually holds different, newer work. Symptom: reading files from
"the PR's worktree" shows stale/wrong content (e.g. an old CI workflow
referencing an already-removed deploy path) because the directory's `HEAD` is
actually on a different branch now. Fix: `git worktree list` first to see the
real branch-to-directory mapping before trusting a remembered path: if the
branch you need is checked out elsewhere, either work in that directory
directly or spin a **fresh** worktree at the branch's real current SHA
(`git fetch` then `git worktree add <new-path> <branch>` from wherever it
isn't already checked out) — never fight the existing checkout or assume a
worktree directory still holds the branch it was created for.
- Rewriting a deploy workflow / CI pipeline to target only the new infra
  instead of making it dual-target — this deletes the old system's deploy path
  out from under it while it's still supposed to be running in production.
  Verify additivity literally (diff the preserved job against main after
  removing only your added lines) rather than eyeballing it.
- Folding the old-system removal into the same PR as the migration, even
  behind a flag — scope it as a separate draft PR based on the migration
  branch, marked DO NOT MERGE, that lands only after staging sign-off.
- Letting a long-lived staging PR go stale against main until it shows
  CONFLICTING — merge main in periodically and resolve by preserving BOTH
  main's latest logic and the migration's gating, not by reverting to a
  stale copy of the conflicting function.
- Resolving a main-merge conflict from scratch when a sibling branch off the
  same effort already resolved the identical shape — reuse that commit's
  resolution (after confirming no newer main commits touched those files),
  and re-diff the merged result against the reference commit afterward to
  catch files the auto-merge silently left on a stale sibling version (not
  flagged as conflicted because it wasn't part of the textual conflict).
- Calling a kanban state-transition helper (`kanban-review.py`, `complete`)
  without re-claiming first when the task might have drifted out of
  `running` on TTL expiry — these helpers refuse from the wrong state; a
  cheap re-claim before the call avoids the error entirely.
- Retiring or mutating the old production system "just to test the cutover
  path" during the validation phase — it must stay untouched until the human
  explicitly approves cutover.
- Asking the human to hand over secret values directly instead of fetching
  them yourself to a file and pointing the session at the path.
- Guessing at region/DNS/IAM availability instead of checking it with a real
  API call before either proceeding or escalating a blocker.
- Declaring an infra script change "verified" from a diff read alone — for
  idempotent setup/mount scripts, actually re-run the changed script against
  the real target and confirm the end state it claims (service registered,
  running, port serving) rather than trusting static checks alone.
- Treating "backend API checks pass" as equivalent to "real traffic validated"
  when the production path is auth-fronted — the auth wall + DNS + public path
  interaction still needs a real human login pass before calling the staging
  validation complete.
- Assuming a green suite on the dev machine proves the target host is clean —
  ambient host env (deployed-mode flags, mount state) can leak across tests
  only on the real target; the suite must also run there.
- Fixing an auth-proxy's redirect-url/cookie-domain and calling login "fixed"
  without checking TLS termination parity with the old host — a real login
  attempt is the only thing that proves the whole chain works.
- Treating a single-line SSM PowerShell edit (e.g. one `Add-Content`) as too
  trivial to need the file-write escaping pattern — any backtick/quote/`$`
  destined for a `.ps1` file needs it regardless of edit size.
- Personally grepping/SSH-ing into old vs. new hosts to answer a parity or
  "did it cover X" question when an owning T2 already exists for that
  migration — write it as a brief and delegate instead of burning the parent
  orchestrator's own context and access.
- Treating a single happy-path e2e as sufficient once the human asks for
  exhaustive/cost-no-object validation — expand to the full scenario battery
  (multi-session restart, repeated restarts, hard-kill, reconnect, long
  multi-turn, concurrency stress, real-dependency round-trip, failure
  injection, soak) and actually run all of it.
- Accepting the owning T2's own "100% tested, all green, ready to merge"
  self-report as the final signal on a large/high-risk PR — dispatch a fresh,
  context-free subagent to independently re-verify the diff and test
  assertions before the human approves merge.
- Relaying a human's flag-flip instruction verbatim when they named the
  desired STATE ("check it works unsupervised") rather than the flag's actual
  set/unset value — verify the flag's real semantics first and instruct using
  its literal value, restating the mapping back so a naming mismatch doesn't
  invert the step.
- Treating the deploy/CI script that ships a new component (e.g. a new
  supervisor container) as safe by default just because it's part of a
  reviewed PR — deploy scripts that stop the old component before confirming
  the new one healthy are a real, recurring outage shape; audit for this
  ordering explicitly as part of the go-live checklist, and fix it in-scope
  (not as a deferred follow-up) when it actually bites during rollout.
- Declaring a deploy-atomicity fix "verified" from the on-box dry-run alone —
  a dry-run proves the reorder/guard logic; only watching the REAL
  re-triggered deploy (the merge itself fires it) to a clean exit proves
  every later pipeline stage (e.g. a post-swap publish/activation step) also
  succeeds against the real host's actual state (observed: a `mkdir -p`
  leaving a directory root-owned broke a later uid-1000 publish container
  even though the swap/health-gate fix itself was correct).
- Trusting `gate`'s zero-diff/`impl:fail` verdict on a long implementation
  session without cross-checking `git rev-list`/`git diff --stat` in the
  actual worktree — a mid-flight worktree switch can make the plugin resolve
  the wrong rundir and misreport real, substantial work as "no changes."
- Assuming a remembered worktree path still holds the branch you expect —
  `git worktree add` can silently fail or a directory can get reassigned to
  a different branch over a long multi-task orchestration run; `git worktree
  list` before trusting any path, and spin a fresh worktree rather than
  fighting an existing checkout that's on the wrong branch.
