---
name: qc-dashboard-perf-triage
description: "Triage 'the deployed lesson agent is slower / behaves differently than local' reports on the alpha-learn QC dashboard Lightsail box, AND audit Drive-sync correctness bugs (reverted edits/renders, stale artifacts shipped) on the same box. Covers the SSH access pattern, the ordered checklist (box resources -> container -> model routing -> Drive sync), the known aggressive Drive push/pull architecture that is the most common root cause for both slowness and silent reverts, and why a Windows+Drive-mount migration is not a clean fix. Use whenever asked to investigate agent slowness, tool-call cadence drops, resource/latency questions, or a lesson shipping with a stale/reverted artifact on the qc-dashboard box."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [alpha-learn, qc-dashboard, lightsail, performance, ppt-copilot, drive-sync, trilogy]
    related_skills: [content-pipeline-data-layers, aws-iam-credential-rotation]
---

# QC Dashboard Perf Triage (alpha-learn-content-gen)

Class of task: a dev/user reports the **deployed** lesson-generation agent
(ppt-copilot, running inside the `qc-dashboard` container on the Lightsail
QC-dashboard box) is slower, or makes noticeably fewer tool calls per unit
time, than the same agent run locally. Also covers general "is the box
resource-constrained" questions on that host.

## Access

```bash
ssh -i /Users/ayush/Trilogy/docs/keys/qc-dashboard-key.pem -o StrictHostKeyChecking=no ubuntu@<qc-host-ip> "<cmd>"
```

Container name: `qc-dashboard` (docker). Exec into it with
`sudo docker exec qc-dashboard sh -c '<cmd>'`. `LESSON_BASE_PATH=/data/drive`
is **local NVMe disk**, not a live network/FUSE mount — don't assume Drive
API latency shows up on ordinary file reads.

## Triage order — don't skip ahead

Each step rules a class of cause in/out cheaply before you go looking at the
expensive one (Drive sync). Run them in this order; stop and report as soon
as one step shows the smoking gun.

1. **Box resources** — CPU/RAM/disk/network on the host. `free -h`, `top -bn1`
   (check `%st` steal — nonzero means the *host* is throttled by the
   hypervisor), `df -h`, `dd`-based disk read/write probe (see below),
   `speedtest-cli` for network. Healthy numbers here (which is the common
   case) rule out "linux box is underpowered" — don't stop the investigation
   here, this just narrows scope.
2. **Container resource limits** — `docker stats`, `docker inspect` for
   Memory/CpusQuota. A container without explicit limits sharing a healthy
   host is not the bottleneck.
3. **What's actually running** — `ps aux | grep claude_agent_sdk` (or
   `claude|node|agent`). The deployed agent is the **Claude Agent SDK**
   (`claude_agent_sdk` python package) spawning the bundled `claude` CLI per
   lesson session, in `--output-format stream-json` mode, orchestrated by
   `auto_orchestrator` (`AUTO_INVOKE_ORCHESTRATOR=1`). Note the `--model`
   flag on each process — this tells you the actual model/routing in use for
   *that* run, don't assume it matches settings.json's default.
4. **Model routing / gateway latency** — deployed runs go through the
   TrueFoundry gateway (`$TFY_BASE_URL`, e.g. `https://<llm-gateway>`)
   rather than Anthropic direct. Compare TTFB:
   `curl -o /dev/null -s -w "ttfb:%{time_starttransfer}\n" $TFY_BASE_URL/`
   vs `https://api.anthropic.com/v1/models`. A gap of 100+ms here compounds
   across every turn of an agentic run and shows up as "fewer tool calls in
   the same wall clock" even though the box itself is fine.
5. **Drive sync (usually the dominant cause)** — see below. Check this even
   if steps 1-4 look clean; a blocking Drive round-trip inside the agent's
   own request path is the single biggest deployed-vs-local latency gap
   because it literally stalls the next tool call.

### Disk I/O probe (step 1)

```bash
dd if=/dev/zero of=/data/drive/.speedtest bs=1M count=256 oflag=direct 2>&1 | tail -1; rm -f /data/drive/.speedtest
dd if=/dev/urandom of=/tmp/.st bs=1M count=256 2>/dev/null; sync
echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
dd if=/tmp/.st of=/dev/null bs=1M iflag=direct 2>&1 | tail -1; rm -f /tmp/.st
```

## Drive sync — the known aggressive latency source

`/app/.claude/scripts/utils/drive_sync.py` wraps `rclone` calls to the
`athena:` Google Drive remote, gated by `DEPLOYED_MODE=1` (a no-op locally —
this is *why* local runs never see this cost). It fires far more often than
"a periodic background sync": pulls/pushes are triggered synchronously
**inside the agent's own request path** — on every user prompt that mentions
a lesson ID, on session init, on QC runs, and on every Stop-hook turn
boundary. See `references/drive-sync-triggers.md` for the full trigger table
and source-file line references — read that before re-deriving this from
scratch on a repeat audit.

Practical implication: pull-on-prompt and pull-on-init are genuinely
**blocking** — `subprocess.run(["rclone", ...])` inside `on_prompt.py`, no
`emit_allow()` ahead of it, so the agent cannot start the turn until rclone
returns. This is consistent with the "slower" / "fewer tool calls" symptom
on its own.

**Correction (verified by reading `on_stop.py` source, not assumed):**
push-on-stop does **not** block the agent turn. `on_stop.py` calls
`emit_allow()` as its *first* line, before the Drive push even starts —
the hook explicitly documents "never blocks the turn." The push still costs
real wall-clock time and Drive-API load in the background, but it is not
something the agent is waiting on. Don't cite push-on-stop as part of the
per-turn blocking latency budget — only pull-on-prompt/init, and the
synchronous pulls inside QC/job_runner paths, actually stall the caller.
When auditing a hook for blocking behavior, always check whether it calls
an `emit_allow()`/ack-early pattern before the slow work; don't infer
blocking just because a call sits on the hot path.

Measured cost on a real 229-file/82MB lesson (best case, nothing to
transfer): remote `rclone lsf` listing alone ~3.9s, `pull-drive` ~9.1s,
`push-drive` ~28.1s (0 bytes transferred — pure `--update` per-file modtime
compare overhead, not bandwidth). The fixed listing/compare cost dominates;
bandwidth is not the bottleneck on this box (confirmed via speedtest-cli:
~1 Gbit/s down, ~770 Mbit/s up).

To get a concrete number instead of just diagnosing the mechanism, time one
real pull/push cycle for an active lesson:

```bash
sudo docker exec qc-dashboard sh -c 'time python "$TOOLS/session.py" pull-drive <lesson_id>'
```

## Correctness bugs, not just latency — check these too

Drive sync isn't only a speed problem: unscoped full-lesson pulls/pushes can
silently **revert in-progress work**, independent of whether the box is
slow. If a dev reports a lesson shipped with a stale artifact, or an edit
tool reported success but the file on disk is unchanged, suspect a Drive
sync stomping the write rather than the edit tool itself:

- `sync_lesson_from_drive` / `sync_drive_metadata` pull the **whole lesson
  dir** (only `agent*` provenance excluded on the lesson pull; the 5-min
  metadata sync also includes `videos_per_slide/*.mp4`). A scoped operation
  like `deploy.py build --video-slides 4` still triggers/rides a full pull
  at process start, which can clobber freshly-rendered sibling videos
  (`slide_02.mp4`, `slide_03.mp4`) that were never in scope for that build —
  confirmed via mtime + md5 match against pre-change backups in a live
  incident (see GitHub issue #1051 comment history, lesson
  `TEKS.MATH.CONTENT.3.8.A+2`, 2026-08-06).
- If a write-then-pull ordering exists anywhere in a tool's flow (edit,
  then a later pull before returning), a `--update`-based pull can revert
  the just-written edit before the tool reports success. The durable fix
  pattern: **pull once at process start, never after a write** — never pull
  as a "let me make sure this landed" step after mutating local state.
- Rule out clock skew before trusting an "remote newer" `--update` warning:
  check host and container UTC clocks directly (`date -u` on both) — in the
  one incident audited they matched exactly, so the warning was `--update`
  correctly comparing Drive-set modtimes, not a skew artifact. Don't spend
  time chasing NTP/skew fixes without checking this first.
- **Push-side `--update` skip is a separate bug class from the pull-after-write
  revert above, and it fails silently (no error, no exception — just a
  skipped upload).** `sync_lesson_to_drive` is `rclone copy local->Drive
  --update`, which skips uploading any local file whose mtime isn't strictly
  newer than Drive's copy. This repo has **three independent actors** that
  can each pull/push/touch the same lesson folder on their own clock with no
  shared coordination: the agent host (Stop-hook push), the QC dashboard
  server (`job_runner.py` pull+push around every run, plus the 5-min
  `sync_drive_metadata` tick), and the remote video-render worker (writes to
  S3, not Drive — the agent host downloads from S3 then relies on the Stop
  hook to push to Drive). If the QC server's own pull/push of a slide's video
  lands on Drive with a *server*-side mtime newer than the agent host's local
  copy of that same file, the agent's next push silently no-ops for that file
  under `--update` — the video never reaches Drive, and every later pull
  (QC or otherwise) keeps re-serving the stale Drive copy. This reproduced in
  a real incident: after a multi-slide re-render, only the slide whose local
  file had the newest touch-time actually got a fresh Drive revision: the
  others silently kept their pre-incident Drive revision even though the
  local copy was fresh, because a QC-side sync had touched them more
  recently on Drive than the agent host's local mtime.
- **Diagnosing this requires per-host mtime forensics, not just "check Drive
  revision history."** Confirm the theory by comparing, per affected file:
  (a) the local file's mtime on the agent host at push time, (b) the Drive
  file's revision timestamp, and (c) whether `_warn_skipped`'s push-side
  detection (`nothing to transfer` / per-file `Skipping as --update is set`
  in rclone stderr) actually fired and got logged anywhere retrievable — if
  the push ran inside a Stop hook or background task whose stderr isn't
  captured, the skip event leaves no trace and you're limited to inferring
  it from mtime-vs-revision-timestamp mismatches after the fact.
- **`_touch_local_modtimes()` (runs after every pull/push, sets every local
  file's mtime to `time.time()`) is exactly the mechanism that creates this
  race** — it makes "last host to sync wins the next `--update` comparison"
  regardless of which host's copy is actually the freshest content. This is
  the same root-cause *shape* as the pull-after-write revert bug above (an
  `--update`/mtime-only sync primitive used across hosts with no shared
  clock and no content hash), just triggered from the push side.
- **Push-side fix landed (GH-1429 / PR #1431)**, sibling to #1421's pull-side
  fix: `sync_lesson_to_drive` now runs as two passes instead of one blanket
  `rclone copy --update` — pass 1 is `--update` over everything EXCEPT
  `videos_per_slide/**` (keeps the mtime-based fast path, and still
  correctly protects a file a QC-side sync touched more recently on Drive,
  e.g. `qc_report.json`); pass 2 handles `videos_per_slide/**` with
  content/size-aware gating instead of trusting mtime at all, closing
  exactly the race described above. Verify any future push-side change
  against this shape — a single `--update` pass across the whole lesson
  tree is the anti-pattern to avoid reintroducing.
- **Regression trap found in code review when implementing this fix**:
  gating the existing "clock skew?" observability warning on pass-1's
  transfer count alone false-positives on every healthy video-only push
  (pass 1 legitimately transfers nothing when only videos changed) — which
  is exactly the signal that surfaced the original incident, so a naive
  two-pass split can silently defeat the alarm it's supposed to preserve.
  Gate the warning on the COMBINED pass-1+pass-2 result (or specifically on
  pass-2 status for video-only skips), not on either pass in isolation.
- **Post-merge live verification recipe for this bug class** (real Drive,
  not a local-dir-remote integration test): stage a throwaway lesson copy
  where local `videos_per_slide/*.mp4` are newer-content but the Drive
  copies carry a newer-or-equal mtime (reproduces the exact race), run the
  push, then confirm (a) the videos actually upload — Drive revision
  history shows new revisions with sizes matching local, (b) pass-1
  `--update` still protects a file edited on Drive after local (touch
  `qc_report.json` on Drive, confirm the stale local copy does NOT
  overwrite it), and (c) the clock-skew warning fires only on genuine
  skips, not on healthy video-only pushes. Use disposable lesson copies and
  clean up after — the same class of live check #1421 needed post-merge on
  the QC server (`<qc-host-ip>`, real `/data/drive` + `athena` remote)
  before trusting a local-dir-remote rclone test suite alone.

## Alternative-architecture question: would a Windows + Drive-for-Desktop mount fix this?

This comes up as "why not just run the deployed agent on Windows with a
real Drive mount, like local dev." **Verdict has since firmed up beyond the
one-liner below** — a real migration audit (platform survey, CI/CD map,
state inventory) concluded EC2 Windows is a legitimate fix, not just a
sync-latency trade-off. Full comparison and open risks are in
`references/windows-migration-assessment.md` — read that before re-deriving
the platform survey from scratch on a repeat ask. Summary:

- The correctness/latency case for dropping rclone still holds (kills the
  revert-on-pull bug class + the per-turn blocking pull/init cost).
- **Platform pick, if this is pursued: EC2 Windows Server, not Fargate or
  Lightsail.** Lightsail has no Windows images at all (not a "restart
  disadvantage," a hard disqualifier). Fargate Windows tasks don't support
  persistent/ephemeral storage and can't host a Drive-for-Desktop client —
  disqualified on the same "can't mount Drive" grounds. WorkSpaces is the
  wrong product shape (DaaS per-user desktop, not a headless service host).
  Azure/GCP Windows VMs are a lateral move with no upside — they'd split
  from the existing AWS-native S3/SQS/ECR/CloudFront wiring for no gain.
- **The "redeploy kills in-flight agent sessions" pain is a deploy-mechanism
  bug, not a platform property.** Today's `deploy-dashboard.yml` does
  `docker rm -f qc-dashboard && docker run` — it force-kills every live
  agent session in the container on every dashboard push, on Lightsail,
  and it would do the same on any platform if the agent lives inside the
  thing being redeployed. Fix is to decouple: agent sessions run as
  independent OS processes (not children of the dashboard web process), so
  redeploying/restarting the dashboard doesn't reap them. Do this
  regardless of which platform question is being asked.
- **Two hard risks to de-risk before committing to a Windows migration:**
  (1) Google Drive for Desktop running unattended/headless on a Windows
  Server VM is proven for interactive use, not for an always-on service
  context — session logoff can drop the mount. Mitigate with auto-logon +
  watchdog (same pattern the render fleet already uses for PowerPoint COM
  autologon), with `rclone mount` (WinFsp) as a documented fallback if the
  Drive client proves flaky unattended — that still kills the rclone
  pull/push sync layer even without Google's own client. **This fallback is
  no longer theoretical** — spiked end-to-end on a throwaway EC2 Windows
  Server 2022 box against the real `athena:` remote (same SA, same lesson
  tree), including an 8-way parallel soak test simulating multiple
  concurrent agent sessions (8/8 lessons OK, mount stable, writes confirmed
  async via VFS-cache background upload). Warm-cache reads through the
  mount ran at ~0.02-0.06s (stat/read of `slides.yaml`, dir walk) vs. 8s on
  first cold touch — i.e. local-disk speed after a one-time per-lesson
  local-disk speed after a one-time per-lesson warm-up, which directly confirms the hypothesis that a Windows+mount host
  removes the per-turn Drive latency seen on the Linux+rclone-sync deployed
  box. Under parallel load, cold-walk burst (up to ~33s) and tail-latency
  spikes (up to ~2.3s reads) showed up — not blockers, but need pre-warm +
  VFS-cache tuning before prod cutover. SSM/WinFsp setup gotchas and full
  numbers are in `references/windows-migration-assessment.md`'s "Spike
  validation" and "Soak test" sections — read those before re-running this
  spike from scratch. **A full production-candidate host has since been
  built and e2e-validated** (staging, not yet cut over) — see that
  reference's "Production build" section for the concrete script/AMI
  bring-up that worked and the real defects hit along the way (oauth2-proxy
  binary naming, missing AWS CLI on the WS2022 AMI, non-ASCII chars\n  breaking PowerShell parsing, and the WinFsp Launcher failing to spawn a\n  registered rclone filesystem — fixed by supervising `rclone mount`\n  directly with NSSM instead). Read that section before re-doing this\n  build from scratch. **A later real-login validation pass surfaced a gap\n  service-level checks (healthz 200, `Get-Process` command-line) can't\n  catch**: oauth2-proxy's redirect-url/cookie-domain were hardcoded to\n  prod's hostname (fixed via a `QC_PUBLIC_HOST` env var), and even after\n  that fix the new host had no TLS termination at all — prod's oauth2-proxy\n  terminates TLS itself (no CloudFront in front), a fact that hadn't\n  carried over. See the reference's \"TLS-termination parity\" section: when\n  migrating anything behind an auth proxy, identify what terminates TLS on\n  the OLD system before assuming an app-level cookie/redirect-url fix is\n  the whole story, and don't declare login \"fixed\" without an actual human\n  login attempt.
  (2) If video export is in scope for discussion, do NOT fold "outsourced
  to remote render worker via SQS" into the migration — that's a separate,
  intentionally-unchanged system. Only verify the render-path platform gate
  (`os.environ.get("DEPLOYED_MODE")`-style check in `lesson_deployer/cli.py`)
  still forces `use_remote=True` after the host becomes Windows, so it
  doesn't silently flip to local PowerPoint COM just because the OS check
  now matches.
- QC service Python has zero Linux-specific imports (no fcntl/pywin32/pwd) —
  confirmed portable, not a blocker either way.
- **Staging/prod isolation, when running both side-by-side against the same
  Drive tree for validation: audit every "watches the shared tree and acts
  autonomously" mechanism (auto-orchestrator, watchers, cron-like triggers)
  for double-enablement, and make cross-host lock/coordination tokens
  host-aware.** This is a distinct bug class from the 6 agent-parity bugs —
  see `references/windows-migration-assessment.md`'s "Staging/prod isolation"
  section for the concrete root cause (host-local locks + both-hosts-running
  the orchestrator) and the fix shape (host-role gate + host-aware lock token
  + a mount/temp-dir separation guard).

Don't default to "fix the sync in place, skip the migration" — that was the
old answer before the fuller audit. If the user is actively considering the
move, the EC2 Windows path above is real; surface the Drive-mount-reliability
risk as the thing to spike/de-risk first, not as a reason to reject the plan.

## Pitfalls

- Don't stop at "CPU/RAM/disk look healthy" and conclude the box is fine —
  those rule out resource starvation, not I/O-wait from blocking external
  calls in the request path. Keep going to steps 4-5.
- `rclone listremotes` run as the `ubuntu` SSH user can come back empty even
  though rclone is actively used — the remote config lives inside the
  container/app context, not the host user's rclone config. Check inside the
  container (`docker exec`) and check app source for the remote name
  (`_RCLONE_REMOTE` in `drive_sync.py`) rather than trusting the host-level
  listremotes as authoritative.
- A `ps -ef --forest | grep rclone` snapshot can miss the sync entirely if
  the rclone subprocess already exited between your snapshot and the report
  — these calls are short-lived per-invocation subprocesses, not a long-running
  daemon. Absence of a live rclone process is not evidence sync isn't
  happening; grep the *app source* for the call sites instead of relying on
  a process snapshot.
- When the user hands you a **specific** GitHub issue to check (a link, a
  number, "check the comments on #1051"), read exactly that issue's body
  and comments. Don't fan out to search/read other issues in the tracker
  on your own initiative, even via subagents "to go faster" — that's scope
  creep on a direct pointer. If related issues seem worth surfacing, name
  them as a follow-up suggestion after answering about the one given.
- **#1051 mixes audit comments from BOTH the Linux prod box and the Windows
  staging host with no explicit host label.** When asked "is anything in
  #1051 Windows-deployment-related," grep for host telltales in the evidence
  text (`C:\Windows\...\systemprofile\.claude\projects\`, `L:\Grade N\...`,
  `<internal-host>`) rather than judging by finding topic — most
  findings (animation-anchor bugs, blind JSON probing, unpack/repack detours)
  are ordinary agent/pipeline issues that occur on either host and are NOT
  Windows-specific just because a Windows-hosted comment happens to contain
  one. See `references/windows-migration-assessment.md`'s "Mining the shared
  #1051 audit-log issue" section — this is how the SYSTEM-profile transcript-
  path defect (item 6 in the parity-bugs list) was actually found.
- When the user narrows a proposed fix mid-discussion (e.g. "don't fold X
  behavior-change into this migration/fix"), don't just acknowledge and move
  on — restate the concrete implication for the plan already on the table
  (which steps drop out, what stays unchanged, what still needs a guard/
  verification so the excluded behavior doesn't get touched incidentally).
  A bare "got it" without re-deriving impact is not enough follow-through.
- When asked to survey "other/better alternatives" for an infra decision,
  actually enumerate the real candidate set (other AWS products, other
  clouds, a same-cloud lateral option, a no-migration baseline) with a
  one-line disqualifying fact each — don't just re-justify the option
  already recommended. Verify hard platform constraints (e.g. "does X even
  support Windows / persistent storage / this client") with a real search
  before asserting them; these are exactly the kind of claim Ayush expects
  checked, not assumed.
- When a migration/fix plan is ready to write up and a **related stub
  issue already exists** (thin body, no real comments), default to asking
  which of "new issue" / "expand the existing stub" / "local doc only" /
  "comment on the stub" the user wants rather than guessing — Ayush's
  answer here was to convert the existing stub (#1366) into the full plan
  rather than opening a fresh issue or leaving #1374/#1051 untouched. Don't
  assume "write up the plan" implies a brand-new issue.
- After a throwaway EC2 spike/soak box has served its purpose, tear it
  down fully before considering the task done: terminate the instance,
  delete any security group created for it (retry after a short wait if
  `DependencyViolation` fires — the SG can't be deleted until the instance
  fully reaches `terminated`), and remove any test artifacts the spike
  wrote into shared/real resources (e.g. `_soak_write.txt` files dropped
  into real lesson dirs on the production Drive remote via the mount).
  Verify the SG delete actually returned success, don't fire-and-forget it.
- When authoring/editing the PowerShell infra scripts (`setup.ps1`,
  `lib.ps1`, `rclone-mount.ps1`, `services.ps1`), grep for non-ASCII
  characters (`[^\x00-\x7F]`) before pushing — an em-dash or arrow typed
  into a comment or a `throw "..."` string breaks the string terminator
  when the file crosses the git→SSM→disk path, and the resulting parse
  error looks nothing like "there's an em-dash in this file." Keep these
  scripts pure ASCII. **This bites even after you've fixed it once**: a
  later small edit (one new `Install-Package` line + a plain-English
  comment above it) reintroduced an em-dash into the same file. Make the
  ASCII check a mechanical step in whatever ad-hoc verification you run
  against a `.ps1` diff (`all(ord(c) < 128 for c in text)`), not a rule you
  rely on remembering for "this edit is too small to matter."
- If a service supervisor (WinFsp Launcher, NSSM, Task Scheduler) runs
  `rclone` as `LocalSystem`, always pass `--config <explicit path>` —
  rclone's default config resolution differs by execution context and can
  silently target an empty/wrong config for the system account even though
  the same command works fine when run interactively.
- **WinFsp Launcher can fail to spawn a correctly-registered filesystem
  with zero error surfaced** (`launchctl list` stays empty, no process, no
  log) even when the registration itself is verified correct in the right
  registry view and a direct `rclone mount` works fine outside the
  Launcher. Don't sink more than 2-3 iterations into Launcher registry
  mechanics (quoting, WOW6432Node, `fsreg.bat`) — full root-cause detail
  and the number of iterations already burned are in
  `references/windows-migration-assessment.md`'s "Production build"
  section. Prefer supervising `rclone mount` directly with **NSSM**
  instead — functionally equivalent (SYSTEM-context, boot-persistent,
  auto-restart, globally visible drive letter) and known to work first
  try, no Launcher involved.
- Long SSM builds (a full `setup.ps1` run is ~15-20min: choco installers,
  Playwright chromium, possible WinFsp reboot) will outlast any single
  sandboxed tool call's timeout. Don't loop-poll inside one call — write a
  small bash poller script (`send-command` → loop `get-command-invocation`
  on status → print tail of stdout) to a temp file and run it via
  `terminal(background=true, notify_on_complete=true)`, then `process
  wait`/`poll` on it. This survives sandbox timeouts cleanly and gives you
  a real completion notification instead of blind re-polling.
- Any PowerShell content pushed via `aws ssm send-command`, even a single
  `Add-Content -Value '...'` line, needs the same "write to file, don't
  interpolate raw" care as a full script — a backtick meant to escape a
  `$` inside a Python string leaked through literally into the target
  `.ps1` file, corrupting a dot-sourced env file and breaking a downstream
  service with an opaque `CommandNotFoundException`. Don't assume a
  one-line env-file append is too trivial to hit the escaping pitfall.
- **Same nested-shell trap on the Linux side**: building a multi-hop command
  as `ssh host "... docker exec CONTAINER sh -c '<inner script with $VAR or
  $(...)>' ..."` via Python f-string/`json.dumps` interpolation lets the
  **host's own shell** expand `$VAR`/`$(...)` before the string ever reaches
  the container — the remote call exits 0 but returns empty/blank output
  because the vars it was supposed to compute inside the container were
  already resolved (to nothing) one layer too early. Never let a
  `$(...)`-bearing inner script cross more than one shell layer as a quoted
  string. Base64-encode it instead: `echo <b64> | docker exec -i CONTAINER
  sh -c 'base64 -d > /tmp/script.sh'`, then `docker exec CONTAINER sh
  /tmp/script.sh` — no layer gets a chance to touch `$`/quotes meant for a
  deeper one. Same fix shape as the SSM/PowerShell case above, just a
  different transport.
- When migrating a service that sits behind an oauth2-proxy/SSO wall,
  don't declare login "fixed" from a config diff + healthz 200 alone.
  Identify what actually terminates TLS on the OLD system (check e.g.
  `aws cloudfront list-distributions` — don't assume a CDN fronts it) and
  confirm the new host either replicates that or the trade-off (plain-HTTP
  staging, a host cert, a CDN) has been explicitly decided. A real human
  login attempt is the only thing that proves the whole chain (redirect-url
  + cookie-domain + cookie-secure + actual TLS) works together.
- Infra + login validation is not agent-behavior validation. A host can be
  healthz-green, OAuth-green, and still surface parity bugs only a real
  lesson session exposes: a system prompt redundantly telling the agent to
  cat a contract file the runtime already auto-loads, an id-extraction
  regex with no word boundary reaching an unvalidated spawn boundary, a
  bare-invocation lock/reentry check with no session-id-resolution
  fallback, POSIX-vs-Windows hook command forms, and SYSTEM-account
  PATH/workspace-trust gaps. Budget a real-usage pass with an actual
  end-user driving real sessions before calling a host migration done —
  see the reference's "Agent-behavior parity bugs found via real usage"
  section for the concrete bugs and general lessons.