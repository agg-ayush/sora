# QC dashboard: Linux → Windows migration assessment (condensed)

Context: dashboard + ppt-copilot agent run in a `qc-dashboard` Docker
container on a Lightsail Linux box (`<qc-host-ip>`). Agent is designed by
a dev who works on Windows locally; deployed-only Drive rclone sync
(`DEPLOYED_MODE=1`) is the mechanism that doesn't exist locally. This doc
is the fuller platform survey behind the one-paragraph verdict in
SKILL.md's "Alternative-architecture question" section.

## Current deploy/runtime facts (verified by reading source, not assumed)

- `Dockerfile` comment header states the platform constraint explicitly:
  PPTX→MP4 export uses PowerPoint COM (Windows-only); on Linux it's
  unsupported locally and delegated to a remote EC2 Windows render worker
  via SQS (`components/lesson-deployer/src/lesson_deployer/remote_render.py`,
  `remote_render or os.environ.get("DEPLOYED_MODE") == "1"` gates
  `use_remote`). Devs deploy from local Windows machines.
- QC service (`lesson_qc_checker.cli:main`, FastAPI/uvicorn on :8801 behind
  oauth2-proxy on :8800) has **zero Linux-specific imports** — no fcntl,
  pywin32, pwd, grp. Confirmed portable.
- `.github/workflows/deploy-dashboard.yml`: builds a Docker image, pushes to
  ECR, then SSHes into the Lightsail box and does
  `docker rm -f qc-dashboard && docker run ...`. This **force-kills the
  container and every in-flight agent session** on every dashboard push —
  this is the actual cause of "redeploy kills running agents," and it is a
  deploy-mechanism property, not a Lightsail/Linux property. Any platform
  where the agent lives inside the redeployed unit has this problem unless
  fixed.
- State mounted into the container: `/data/drive` (28G lesson tree, local
  NVMe ext4 — not a live network mount), `/data/claude-sessions` (2.6G
  Claude Agent SDK transcripts), `/data/claude-temp` (51G session scratch,
  much of it stale gate-run copies per the #1051 incident).

## Platform candidate survey

| Option | Verdict | Disqualifying/deciding fact |
|---|---|---|
| **EC2 Windows Server 2022/2025** | ✅ Recommended | Real desktop OS: Drive for Desktop installs, PowerPoint COM available (though intentionally not used here — video stays remote), full control over process model so agent sessions can run detached from the dashboard web process. SSM agent already running → clean SSM Run Command CI/CD target instead of SSH+docker. |
| **Lightsail** | ❌ Disqualified | No Windows Server images exist on Lightsail at all — Linux/Unix blueprints only. Not a "restart disadvantage" question, it's simply not a candidate. |
| **AWS Fargate (Windows containers)** | ❌ Disqualified | Two independent hard facts: (1) "This isn't supported for Windows containers on AWS Fargate" — ephemeral storage config; EFS for Windows tasks is limited/awkward. (2) Can't run a Drive-for-Desktop client or an unattended desktop session inside a Fargate task at all. Also: Office/PowerPoint COM automation is explicitly unsupported by Microsoft in Windows Server Core containers (needs full Office GUI install, not Core). |
| **Amazon WorkSpaces (Personal/Core)** | ⚠️ Wrong shape | Fully-managed persistent Windows desktop, Drive for Desktop works fine on it — but it's a per-user DaaS product with an entitlement/streaming-gateway model, not a headless always-on service host. Abusing it as a server host is awkward; no ops advantage over plain EC2 for this workload. |
| **Azure VM / GCP Compute Windows** | ❌ Lateral move, no upside | Same "Windows VM you manage" burden as EC2, but splits from the existing AWS-native wiring (S3 buckets, SQS render queue, ECR, CloudFront, IAM) into a second cloud control plane for zero functional gain. |
| **Stay on Linux, replace rclone sync with `rclone mount` (FUSE)** | ⚠️ Band-aid baseline | Kills the revert-on-pull bug class without a platform migration. But rclone mount on Linux for an 82GB active workload has a shaky reliability reputation (cache consistency) — arguably the same class of bug you're fleeing — and leaves the Windows-authoring/Linux-deploy portability debt unresolved. Worth naming as the "do nothing structural" option, not recommending as the fix. |

## Open risks if EC2 Windows is pursued (spike these, don't assume)

1. **Drive for Desktop unattended reliability.** Proven for interactive
   human use; not proven for a headless always-on service context (session
   logoff can drop the mount). Mitigation: auto-logon + Drive-for-Desktop
   startup + a watchdog that relaunches the client — same autologon pattern
   already used for the PowerPoint-COM render worker. Fallback: `rclone
   mount` via WinFsp on Windows if Google's client proves flaky — still
   removes the pull/push sync layer even without Google's client. **Spiked
   and confirmed viable — see "Spike validation" below, and built to a
   production candidate — see "Production build" below.**
2. **Video-export scope boundary.** If the user says "don't fold video
   export migration into this," the remote-render path (SQS → existing EC2
   Windows render worker) must stay untouched — no PowerPoint install on
   the new dashboard host, no code change to `remote_render.py`. The one
   thing worth verifying: the `use_remote` gate in `lesson_deployer/cli.py`
   must still resolve `True` once the dashboard host itself becomes
   Windows, so it doesn't silently prefer local COM just because a
   platform-sniff condition now matches Windows. Pin this with an explicit
   env/config check rather than relying on OS-sniffing. **Verified on the
   production candidate box**: `platform.system()=="Windows"` +
   `DEPLOYED_MODE=1` + `RENDER_MODE=remote` still resolves `use_remote=True`,
   `can_render_locally=False` — the gate held.
3. **Process decoupling.** Dashboard web process and agent sessions must
   not share a lifecycle — agent sessions as independent OS processes
   (Windows: detached `Start-Process`/scheduled task/small supervisor
   service) with their state on the Drive mount, so redeploying the
   dashboard doesn't reap live agent sessions. This is required regardless
   of platform; it's the actual fix for "rebuild stops the agent."
4. **Docker or native on the Windows host?** Once Drive is mounted and the
   agent runs natively, the container mostly loses its reason to exist
   (Windows containers + Office COM is also the exact combination that's
   unsupported per the Fargate row above). Leaning toward dropping Docker
   and running natively on the host — simplifies the process-decoupling
   fix — but confirm with the user before committing, since it changes the
   CI/CD build step from `docker build` to a source-pull + `pip install -e`
   model. **Production build (below) did go native (no Docker)** — NSSM
   services running the venv Python directly.
5. **CI/CD target change.** `deploy-dashboard.yml`'s SSH+docker block would
   be replaced by SSM Run Command hitting the EC2 Windows box (SSM agent
   already installed/running there per the snap unit check), restarting
   only the dashboard service — not tearing down agent processes.

## Spike validation: EC2 Windows + rclone-mount (WinFsp), 2026-08

Ran a throwaway `m6i.xlarge` Windows Server 2022 box via the `trilogy`
saml2aws admin profile (see `aws-saml2aws-refresh` skill), reached entirely
via SSM Run Command (`AWS-RunPowerShellScript`) — no RDP/key needed. Pulled
the same Drive SA JSON (`/tmp/drive-sa.json`) the deployed Linux box uses
out of the `qc-dashboard` container and configured an identical `athena:`
rclone remote on the Windows box.

### What worked

- `rclone` itself (no mount) against `athena:` from the Windows box:
  confirmed real Drive connectivity, listed the actual `Grade 3/Grade
  4/...` tree.
- Raw rclone-CLI op cost (process spin-up + cold Drive round-trip, no
  cache) for a real 235-file lesson: `lsf -R` ~2.2s, `cat slides.yaml`
  ~2.7s, `cat voiceover.mp3` (~few MB) ~4.0s, `rcat` small write ~4.9s.
  This is the *no-mount* ceiling — same order of magnitude as the Linux
  box's per-invocation rclone cost, unsurprising since it's the same API.
- **WinFsp installs fine headless via `msiexec /qn`** — the earlier stall
  was from a malformed inline PowerShell heredoc, not an actual WinFsp
  install problem (see pitfalls below). Confirmed via `Get-Service
  WinFsp.Launcher` → `Running`.
- **`rclone mount athena: R: --vfs-cache-mode full`** mounted cleanly and
  is the decisive result:

  | Operation | Latency | Note |
  |---|---|---|
  | Walk lesson dir, cold (first touch) | 8.04s | one-time per-lesson Drive metadata pull |
  | Walk lesson dir, warm (VFS cache) | 0.03s | 268x faster than cold |
  | Read `slides.yaml`, warm | 0.057s | the agent's hottest file |
  | `stat` a file, warm | 0.021s | |

  Steady-state warm numbers (~0.02–0.06s) are effectively local-disk
  speed — this is the number that answers "would replicating local-Windows
  + Drive-mount on the deployed box remove the latency," and it does. The
  Drive round-trip only shows up once per lesson (cold touch), not per
  agent turn.

### Soak test: 8-way parallel load (2026-08, same spike box before teardown)

Ran 8 concurrent lessons against the mount simultaneously (cold walk → 20x
`slides.yaml` read → 5x small write to `temp/` → re-walk each), simulating
the real orchestrator pattern of multiple agent sessions hitting different
lessons at once.

- **8/8 lessons succeeded**, mount process stayed stable (single rclone
  process, no crash/restart).
- **Steady-state reads stay fast under concurrency**: per-lesson read
  medians 29–292ms even with 8 lessons hitting Drive at once — same order
  of magnitude as the single-lesson warm numbers above.
- **Writes are confirmed async**: log shows `vfs cache: queuing for upload
  in 5s` — the write returns to the caller immediately, upload happens in
  the background. This is the desired behavior (agent isn't blocked on the
  Drive round-trip for a write).
- **Two real caveats surfaced, not blockers but must be engineered around
  before prod cutover:**
  1. **Cold-walk burst under concurrency is worse than single-lesson.**
     Single-lesson cold walk was ~1–8s; under 8-way parallel load it
     ranged 1–33s (Drive API rate/metadata throttling when many lessons
     start cold at once). Mitigation: pre-warm the cache for a lesson
     when its agent session starts, off the agent's own path, rather than
     letting the first real operation eat the cold-walk cost.
  2. **Tail latency spikes**: several lessons saw `read_max` up to
     ~1.8–2.3s and `write_med` up to ~530–680ms under load (cache-miss /
     rate-limit moments), vs. the ~20-60ms medians. Mitigation: tune VFS
     cache flags (`--vfs-cache-max-size`, `--dir-cache-time`, buffer
     sizing) rather than assuming the median number is what an agent will
     always feel.
- Still not tested: VFS cache eviction under sustained memory pressure
  (only ran ~1min of load), and Drive push (write-back) latency once a
  large volume of local edits accumulates and drains. Soak longer before
  prod cutover if that matters.
- After finishing a soak/spike test, **clean up any test-write artifacts
  left on the real Drive tree** (e.g. `temp/_soak_write.txt` dropped into
  real lesson dirs) before terminating the spike box — verify removal via
  a follow-up SSM command listing/deleting each path, don't just assume
  the throwaway box's teardown also cleans the shared Drive remote.

### What didn't / caveats

- Only single-lesson steady-state and one ~1min 8-way parallel soak were
  tested. **Still not stress-tested**: sustained memory pressure on the
  VFS cache, or Drive push (write-back) latency once a large volume of
  local edits accumulates and drains over a longer window.
- Used `rclone mount` + WinFsp, **not Google's own Drive-for-Desktop
  client**. rclone mount is arguably the better always-on choice for a
  headless service (runs via the WinFsp launcher service, no interactive
  Google OAuth login needed, reuses the existing SA) — but if the plan
  specifically wants Google's client for parity with local dev, that needs
  its own unattended-login spike (interactive OAuth doesn't have an
  equivalent headless path the way the SA does for rclone).

### Pitfalls hit during the spike (SSM/PowerShell mechanics, not infra facts)

- **Don't hand-escape multi-variable PowerShell one-liners through
  `aws ssm send-command --parameters "commands=[...]"` shell quoting.**
  Nested `$CONF`/`$L` variable interpolation inside a JSON-embedded,
  bash-double-quoted, PowerShell-double-quoted string gets mangled — the
  visible symptom is PowerShell treating a variable's *value* as a
  literal command name (`The term '\your-path\' is not recognized...`).
  Write the PowerShell to a local `.ps1` file with `write_file`, base64 it,
  and have the SSM command `[IO.File]::WriteAllText(...)` it onto the box
  before invoking — this sidesteps all shell/JSON/PowerShell tri-layer
  escaping entirely. This is now the standard pattern for any SSM
  PowerShell beyond a trivial one-liner.
- **PowerShell's `<`/`>` are reserved and will throw
  `RedirectionNotSupported` even for things that look like plain
  comparisons or redirects** (e.g. `rclone rcat ... < $tmp`). Use
  `Get-Content $tmp -Raw | rclone rcat ...` (pipe) instead of shell-style
  input redirection.
- **A WinFsp MSI that looks "stuck" in `InProgress` for minutes via SSM may
  just be a slow `Invoke-WebRequest` download**, not a hung installer.
  Don't `cancel-command` and declare it broken — check `(Get-Item
  file).Length` for download progress first, and use
  `$ProgressPreference = "SilentlyContinue"` before `Invoke-WebRequest` on
  Windows (its default progress-bar rendering is extremely slow over SSM's
  non-interactive output capture and can look like a hang).
- **`Test-Path "C:\Program Files\WinFsp"` returning `False` does not mean
  the install failed** — check the actual `WinFsp.Launcher` Windows service
  state (`Get-Service`) instead of guessing an install path; the real
  install directory can differ from what you'd assume.
- SSM sessions on a fresh instance can sit `Pending` for a few minutes on
  the very first command (Windows SSM agent cold start / association
  propagation) — don't conclude the SSM role/setup is broken from one slow
  first command; send a trivial second command to confirm the channel is
  actually live before troubleshooting IAM/associations.
- The AWS CLI session/token used for `aws ssm` calls is time-boxed (this
  account's saml2aws session is 1h, see `aws-saml2aws-refresh` skill) —
  a spike that runs long will need a mid-spike refresh; don't mistake an
  expired-token failure mid-poll for an SSM/instance problem.

## Production build: full staging host bring-up, 2026-08

Went beyond the spike — built and e2e-validated a real production-candidate
host on a staging branch (PR kept open, unmerged; Linux box left serving
prod throughout). EC2 `m6i.2xlarge`, Windows Server 2022, ap-south-1 (region
choice + DNS zone are user calls, not fixed facts). Full flow: IAM role +
instance profile, security group (443+8800 only), 49 secrets seeded to SSM
SecureString (mirrored 1:1 from the Linux box's `.env`), userdata pulls
`setup.ps1` from the target git branch, EIP + Route53 A record for a stable
DNS target before the box's ephemeral public IP could be trusted.

Went **native, no Docker** — NSSM services running the venv Python directly
(`qc-dashboard`, `oauth2-proxy`, `rclone-athena`), matching the "leaning
toward dropping Docker" open question above.

### Real defects hit and fixed on the branch (not environment quirks — actual script bugs)

1. **oauth2-proxy binary resolution.** The v7.6.0 Windows tarball extracts
   to a directory whose exact name doesn't match a hardcoded `Copy-Item`
   target, and the binary inside has no `.exe` extension in some
   packagings. Fix: resolve the binary via `Get-ChildItem -Filter
   "oauth2-proxy*"` inside the extracted dir instead of a hardcoded path.
2. **AWS CLI v2 missing on the WS2022 AMI.** `Sync-QcDotEnv` (SSM
   `get-parameters-by-path`) and the Drive mount config both shell out to
   `aws`, but the base AMI doesn't ship it and the setup script never
   installed it. The failure mode is misleading: the wrapper swallows the
   real `CommandNotFoundException` and reports a generic "`.env` not
   found," which sent troubleshooting down the wrong path (SSM
   permissions) before the real cause (`aws` missing from PATH) surfaced.
   Fix: install AWS CLI v2 via `AWSCLIV2.msi` early in `setup.ps1`, and
   don't trust a wrapper's stated failure reason over checking whether the
   underlying binary exists.
3. **Non-ASCII characters break PowerShell string parsing.** Em-dashes and
   arrows (typed by an agent authoring the scripts) inside `throw "..."`
   strings in `lib.ps1`/`rclone-mount.ps1`/`services.ps1` render as mangled
   multi-byte sequences (`â€"`) when the file is fetched/re-encoded across
   the git→SSM→disk path, and this **breaks the string terminator**,
   producing a PowerShell parse error that looks unrelated to the actual
   throw message. Fix: keep all `.ps1`/`.bat` infra scripts pure ASCII —
   no em-dashes, curly quotes, or arrows, even in comments/error strings.
   Grep for high-byte characters (`[^\x00-\x7F]`) across the infra script
   dir as a pre-flight check before pushing PowerShell changes.
4. **WinFsp Launcher never actually starts a registered filesystem.**
   Despite `fsreg.bat`-verified correct registration (present in the
   64-bit registry view, `HKLM\SOFTWARE\WinFsp\Services`), the
   `WinFsp.Launcher` service running clean as LocalSystem, and manually
   running `rclone mount ... --config <path>` working perfectly outside
   the Launcher — `launchctl list` stubbornly returns empty and no rclone
   process/log ever appears when the Launcher should have spawned it. This
   consumed 7+ iterations (quoting the Executable value, adding
   `--config` explicitly, WOW6432Node vs. native registry view,
   `fsreg.bat` re-registration) with zero error surfaced anywhere. Root
   cause not found this session. **Workaround that is now the
   recommendation over WinFsp Launcher**: supervise `rclone mount`
   directly with NSSM (same SYSTEM-context, globally-visible drive letter,
   auto-restart-on-failure, boot-persistent service — functionally
   equivalent to what the Launcher would provide, just a different
   supervisor). If revisiting the Launcher path specifically, get WinFsp's
   own source/GitHub issues involved before another blind iteration
   round — this looks like a WinFsp version/AMI-specific bug, not a config
   mistake in the reproduced registration.
5. **`rclone-mount.ps1`'s `CommandLine` didn't pass `--config`.** When
   WinFsp Launcher runs rclone as LocalSystem, rclone's default config
   path resolves to a different user profile than the one holding
   `rclone.conf` — the mount silently looks for a config that "exists" but
   is empty/wrong. Always pass `--config <explicit path>` when a service
   supervisor runs rclone as a system account, don't rely on rclone's
   default resolution. (This fix is necessary but wasn't sufficient to fix
   defect #4 above — the Launcher never got that far.)
6. **oauth2-proxy hardcoded the prod public hostname.** `services.ps1`'s
   generated oauth2-proxy wrapper hardcoded
   `--redirect-url=https://<internal-host>/oauth2/callback` (prod's
   hostname) with no `--cookie-domain` at all — copied verbatim from the
   Linux box's config, which is correct there but wrong on any other public
   hostname. Symptom on a real human login attempt: Google OAuth completes,
   but the callback comes back `403 Forbidden — Unable to find a valid CSRF
   token` (the CSRF cookie was set for/expected on the wrong domain). Fix:
   made the public hostname configurable via a `QC_PUBLIC_HOST` env var
   (defaults to prod's hostname for backward compat), driving both
   `--redirect-url` and `--cookie-domain` off it; the staging host's
   `env.ps1` sets it to its own hostname. **This class of bug won't show up
   in healthz checks or a `Get-Process` command-line inspection alone** —
   it only surfaces on an actual OAuth login attempt, so a migration
   validation plan needs a real login pass, not just "services are
   Running + healthz 200," before declaring auth wired correctly.

### TLS-termination parity — a gap config alone won't fix

Fixing the redirect-url/cookie-domain (defect #6 above) is necessary but was
**not sufficient** — a real login attempt still failed after that fix,
because the staging host has **no TLS termination at all**: nothing listens
on port 443, and oauth2-proxy serves plain HTTP on :8800 with
`--cookie-secure=true`. The browser won't send a secure cookie back over
plain HTTP, so the callback still breaks. Checking what fronts prod
(`aws cloudfront list-distributions`) confirmed prod's oauth2-proxy
terminates TLS **itself** (it holds a cert) — CloudFront does not front it.
That fact was not carried over to the new host at all.

**Lesson: when migrating a service that sits behind an oauth2-proxy/SSO
wall, explicitly identify what terminates TLS on the OLD system before
assuming an app-level config fix (redirect-url, cookie-domain) is the whole
story.** A host can look fully fixed — correct command line, healthz 200 on
every service — while the actual browser login path is still structurally
broken because the new host is missing a layer (a cert, a CloudFront
distribution, a load balancer) the old one had. Resolving this is a real
decision with trade-offs (plain-HTTP staging with `cookie-secure=false`;
terminate TLS on the host with a cert; front with CloudFront) — surface it
to the human as a decision, don't default to weakening cookie security
silently.

### SSM PowerShell escaping bites even on single-line edits, not just full scripts

The existing "write `.ps1` to a file, base64 it, `WriteAllText` it onto the
box" rule (see Spike pitfalls above) is not just for multi-variable
one-liners or full scripts — it applies to **any** PowerShell content pushed
through `aws ssm send-command`, including a single `Add-Content -Value
'...'` line to append an env var. Interpolating a backtick-escaped
PowerShell string (`` `$env:X = "..." `` meant to produce a literal
`$env:X = "..."` in the target file) through a Python string passed into the
SSM `commands` JSON array let the backtick escape character leak through
literally into the file on disk, instead of being consumed. The result:
`env.ps1` had a stray backtick before `$env:QC_PUBLIC_HOST`, which broke
dot-sourcing wherever that file was loaded — the wrapper script threw
`CommandNotFoundException` for `` `$env:QC_PUBLIC_HOST `` and a downstream
service silently sat `Paused`. Symptom looked like a service-start failure
with no obvious link to the env-file edit that caused it. Don't assume a
"just append one line" edit is simple enough to skip the safe file-write
pattern — any backtick, quote, or `$`-interpolation inside content destined
for a `.ps1` file needs the same treatment as a full script push.

### NSSM finalized as the mount supervisor (2026-08, decided — stop revisiting WinFsp Launcher)

The WinFsp-Launcher-vs-NSSM question above is now **closed**. Decision: NSSM
supervises `rclone mount` permanently; WinFsp stays installed only as the
FUSE layer rclone needs, with the Launcher itself left unused. Do not spend
further iterations trying to make the Launcher spawn the filesystem — that
investigation already burned 7+ iterations with zero root cause found (see
defect #4 above) and the user explicitly closed it: "keep the working NSSM
rclone-athena service. Do NOT keep debugging the WinFsp Launcher."

Baked into the scripts so a **fresh host rebuild reproduces the working
mount with no manual steps**:
- `rclone-mount.ps1` installs/repairs the `rclone-athena` NSSM service
  (`nssm install`, `SERVICE_AUTO_START`, `AppExit Default Restart`,
  `--config <explicit path>` passed to rclone — see defect #5).
- `setup.ps1`'s mount section header and comments describe NSSM as the
  supervisor; WinFsp is documented as "installed but unused" (its FUSE
  layer is still a real dependency, just not via the Launcher).
- The mount watchdog (`setup.ps1`'s scheduled canary task) restarts the
  `rclone-athena` **service**, not `WinFsp.Launcher`, on failure.
- `README.md` service table + verify-step service list updated to
  `rclone-athena` in place of `WinFsp.Launcher`.

Verified by re-running the updated `rclone-mount.ps1` on the live staging
host via SSM after pushing: fresh run produced `Registered NSSM service
rclone-athena` → `rclone-athena: START: The operation completed
successfully` → `Mount live at L:\`, and `Get-Service
qc-dashboard,oauth2-proxy,rclone-athena` showed all three `Running`/
`Automatic` with both healthz endpoints returning 200 afterward. That's the
proof bar for "idempotent, rebuild-safe" on this class of infra script —
don't just eyeball the diff, actually re-run the changed script against the
real target and check the end state it claims to produce.

### E2e validation performed on the built host (real runs, not inference)

- `drive_sync_enabled()==False` with `DEPLOYED_MODE=1` +
  `DRIVE_SYNC_DISABLED=1` set — confirms no rclone pull/push fires on the
  agent's own path once mounted; only the mount's own VFS-cache activity
  appears in `rclone-mount.log`.
- Mount latency warm: `slides.yaml` read 0.015s, dir walk 0.016s, small
  write 0.015s — consistent with the spike's numbers above.
- Render gate (`use_remote`/`can_render_locally`) still resolves correctly
  under `platform.system()=="Windows"` — see risk #2 above.
- Full test suites run **on the host itself** (not just macOS/CI) via SSM:
  `.claude/scripts` (101+), lesson-deployer render tests (23), qc-checker
  component (1246) — remaining failures/errors cross-checked against
  unmodified `main`'s code on the same host to separate real regressions
  from pre-existing environmental issues (Athena-fetcher import collision,
  live-LLM-fixture tests).
- **Windows-specific test-isolation bug found and fixed**: a test file
  (`test_session_drive.py`) had an autouse fixture that cleared
  `DEPLOYED_MODE` but not `DRIVE_SYNC_DISABLED` between tests. On macOS
  this never leaked (ambient `DRIVE_SYNC_DISABLED` was never set locally);
  on the actual mounted Windows host, where `DRIVE_SYNC_DISABLED=1` is
  genuinely set process-wide, mirror-mode tests earlier in the same file
  left it set and later tests silently ran in the wrong mode. Any test
  fixture that clears one deployed-mode env flag but not its sibling is a
  latent Windows-only leak — clear the full set together in one autouse
  fixture, and when a test passes on macOS/CI but fails only against a
  real deployed-mode host, suspect env-leak-via-ambient-state before
  assuming a platform code bug.

## Agent-behavior parity bugs found via real usage, post-launch (2026-08)

The infra/OAuth bring-up above gets the host serving; it does NOT prove the
**agent** behaves the same on the mounted host as on Linux/local. A distinct
bug class showed up only once a real user drove real lesson sessions through
the deployed dashboard. Don't consider a Linux→Windows host migration done
after infra validation alone — budget a real-usage pass and expect deployed-
path bugs like these:

1. **A visible `cat` of an operating-contract file leaked into chat.** The
   chat system prompt told the agent "use `.claude/agents/<name>.md` as your
   operating contract" as prose pointing at a file to read — but the agent
   already runs *as* that subagent (Claude Agent SDK `setting_sources=
   ["project"]` auto-loads `.claude/agents/*.md` as the subagent's own
   instructions), so the file is already injected. The prose prompted a
   redundant, visible `cat` the user then saw in the transcript. **General
   lesson: if the SDK/runtime already auto-loads a contract file via its own
   mechanism, don't also tell the agent in prose to go read it — that's an
   invitation to a needless visible tool call.** Fix: state explicitly in
   the prompt that the contract is already loaded and NOT to cat it.
2. **A raw option token (`--help`) got treated as a lesson id and spawned a
   session.** Root cause was two missing layers, not one: the extraction
   regex (`LESSON_ID_RE.search(...)`) had no word boundary so it could
   partial-match unexpected input, AND the actual spawn boundary
   (`/ws/{lesson_id}`) had zero format validation of its own — it only
   rejected empty/path-traversal. **General lesson: an id-extraction regex
   run against free text is not a validator; the actual trust boundary
   (wherever the id is used to spawn/allocate a resource) needs its own
   `fullmatch` validation independent of wherever the id first came from.**
   Fixed both layers (word-anchored the regex + added boundary validation)
   rather than just tightening the regex.
3. **Self-lock false positive: the owning session refused its own
   re-entry.** The documented flow (`session.py init LESSON_ID`, called bare,
   no `--session-id`) writes an **anonymous** lock (`session_id=""`), which
   by definition is never reentrant — so when the same logical session later
   touched the lesson again, the reentry check (`holder == session_id`)
   failed against its own prior anonymous lock. **General lesson: any lock/
   reentry mechanism keyed on an explicit session-id parameter needs a
   resolution fallback (e.g. look up the lesson's current session from a
   registry like `sessions.json`) for the common bare-invocation case where
   the caller never passes one — don't assume every call site supplies the
   id explicitly.** Fix: `init` resolves the session id from `sessions.json`
   when not passed.
4. **Deployed-Windows hooks used a POSIX shell form.** `settings.deployed.
   windows.json` hook commands were `. "venv/Scripts/activate"; python ...`
   — `.`/`source` and the `;` chaining are POSIX shell syntax that doesn't
   work under the Windows hook runner. Fix: call `venv/Scripts/python.exe`
   directly, no activate step. **A staleness check regressed the same way**:
   it compared a Drive-preserved `.init_stamp`/mtime across sessions, but in
   mounted mode nothing rewrites those on pull (there is no pull), so an old
   stamp reads as stale against a brand-new session. Fixed by skipping the
   cross-session stamp/mtime comparison specifically in mounted mode (the
   per-lesson lock already provides the concurrency guard there).
5. **`claude` CLI resolved locally but not from the deployed agent path.**
   `npm install -g` run under the SYSTEM account lands in the SYSTEM
   profile's own npm prefix, which is never on the machine PATH other
   accounts/services see. Fix: `setup.ps1` explicitly appends the npm-global
   bin dir to the **Machine**-scope PATH (not just the installing shell's
   session PATH).
6. **Follow-on, found while verifying #1-5 with a real headless spawn:**
   the repo workspace wasn't trust-accepted for the SYSTEM profile
   (`.claude.json` `hasTrustDialogAccepted` unset for the repo path under
   that profile), so a real agent spawn hit a headless trust prompt instead
   of running — and separately, `permissions.allow` entries phrased as
   `Write(...)`/`MultiEdit(...)` are silently ignored by the SDK's file
   permission checker (only `Edit(path)`-form rules match file-editing
   tools) — worth an audit pass over `settings.deployed.windows.json`'s
   permission rules for the same silently-ignored-rule shape, not just a
   one-off fix of the trust flag.

6. **Transcript/session-history tooling resolves the wrong profile under the
   Windows service account.** `session.py get-lesson-sessions-details` (and
   anything else that resolves the Claude "projects" transcript dir from
   `HOME`) returned empty (`session: []`) for sessions actually run on the
   Windows staging host. Root cause: the agent runs there as the Windows
   service account (NSSM/LocalSystem), so real transcripts land under
   `C:\Windows\system32\config\systemprofile\.claude\projects\` — a
   completely different profile than whatever `HOME`/projects-dir the
   tooling resolves. This is the same *class* of gap as defect #6's trust-flag
   issue above (SYSTEM-profile state diverging from the profile tooling
   assumes), just hitting session-history/audit tooling instead of the trust
   dialog.

   **FIXED and live-verified (2026-08 follow-up, PR against #1423's branch).**
   `claude_agent_sdk` resolves the projects dir via `CLAUDE_CONFIG_DIR` (else
   `Path.home()/.claude`), so pin it to ONE location every reader/writer
   agrees on: `env.ps1.template` (service wrappers dot-source it),
   `run-dashboard.ps1` (default), and `setup.ps1` at **Machine** scope
   (covers ad-hoc shells too). `setup.ps1` also migrates pre-pin transcripts
   from `systemprofile\.claude` AND any `C:\Users\*\.claude` into the pinned
   dir via `robocopy /XO` (idempotent) and reprovisions the trust-accepted
   `.claude.json` there. **Don't stop at the host-wide pin** — anything with
   its own headless-session env builder (this repo's `session.py`
   `_headless_env()`) must ALSO set `CLAUDE_CONFIG_DIR` explicitly, or the SDK's
   preference for `CLAUDE_CONFIG_DIR` over `HOME`/`USERPROFILE` means a
   headless spawn that clears/overrides env can silently escape the pin and
   leak sessions back into a per-account dir. Live-verified on
   `<internal-host>` via SSM: after pull + rerunning the service
   installer + service restart, `_get_projects_dir()` resolves to the pinned
   dir, the migration swept all 37 pre-existing project dirs, and
   `get-lesson-sessions-details` on a real lesson returned an actual
   transcript (not `[]`). Don't trust `Get-Service`/healthz alone for this
   class of fix — the proof is the tooling actually returning real data
   end-to-end, same as the OAuth-login lesson above.

**Verification pattern that worked**: rather than spawn a full agent session
per bug (slow, needs SDK auth context this SYSTEM-profile spawn didn't have),
confirm each fix by asserting the specific changed behavior directly (regex
non-match/match, session-id resolution helper present and wired, hook JSON
command string form, mounted-mode early-return present) plus a handful of
targeted on-host SSM probes (regex behavior, lock reentry, live hook command
string, PATH resolution) — faster feedback than waiting on a live spawn, and
each assertion maps 1:1 to the actual root cause instead of a black-box
pass/fail.

## Mining the shared #1051 audit-log issue for Windows-specific parity bugs

GitHub issue #1051 is a running per-run debug log an automated audit agent
posts to after every lesson session, across **both** the Linux prod box and
the Windows staging host, with no explicit column/label marking which host
produced a given comment. When asked to check whether any #1051 entries are
Windows-deployment-related, don't guess from content topic alone (most
findings — animation-anchor bugs, blind-schema JSON probing, unpack/repack
detours — are ordinary agent/pipeline issues that occur on either host and
are NOT Windows-specific just because they happened to run there). Identify
the host from telltale **evidence markers** the audit agent's own notes
report, not from the finding's subject matter:

- `C:\Windows\system32\config\systemprofile\.claude\projects\` — the
  Windows service-account transcript path (see parity bug #6 above); its
  presence in an audit comment's evidence note is a strong host signal by
  itself even when unrelated to the bug being reported that run.
- `L:\Grade N\...` (the Windows Drive-mount drive letter) vs. `/data/drive/...`
  or `/home/appuser/...` (Linux paths) in file-path evidence.
- `<internal-host>` vs. `<internal-host>` if the hostname
  is mentioned directly.

Grep the comment bodies for these markers (`gh issue view <N> --json comments
--jq '.comments[] | select(.body | test("<markers>";"i"))'`) rather than
reading all comments in full — #1051 accumulates hundreds of entries and most
are irrelevant to a host-scoped question. This surfaced the transcript-path
defect (#6 above) as a real, previously-unfixed Windows parity bug purely
from an audit agent's incidental evidence note in an otherwise unrelated
animation-timing report — i.e. the shared audit log is itself a parity-bug
discovery channel, complementary to the "Real-usage parity audit methodology"
section above (which mines the OLD host's transcripts for a usage inventory;
this mines the audit log's own byproduct evidence for platform bugs on the
NEW host).

## Staging/prod isolation bug: two hosts mounting the SAME Drive tree can double-spawn on one lesson

A distinct bug class from the 6 agent-behavior parity bugs above, surfaced by
running staging (Windows host) and Linux prod side by side against the same
`athena:` Drive tree for validation. Symptom: a real session saw **two live
transcripts with identical prompts on the same lesson**, plus a lock that had
already been "misread" as another session's (this is the deeper structural
cause behind parity bug #3 above, not just the anonymous-lock-token issue).

**Root cause, confirmed by reading source, not assumed**: `.claude/temp`
(`sessions.json` + `.locks`) is genuinely **host-local** — `TEMP_DIR =
REPO_ROOT / ".claude" / "temp"` under each host's own repo checkout, never
under the shared `LESSON_BASE_PATH` mount (verified: `L:\.claude` doesn't
exist on the Windows host). So the two hosts were never sharing mutable lock
state directly. The actual mechanism: the **auto-orchestrator**
(`AUTO_INVOKE_ORCHESTRATOR=1`) was enabled on **both** hosts, both watching
the same mounted lesson tree for trigger conditions — and because each host's
lock is host-local, neither host's lock can see the other's, so both spawned
a session for the same lesson independently. The lock isn't "misreading" a
foreign session as its own; it's structurally blind to any other host
entirely.

**Fix (generalizes beyond this one migration — applies to ANY design where
multiple independent hosts share one mutable resource tree but keep separate
local coordination state):**
1. **Only one host role should run the auto-orchestrator against a shared
   resource tree.** Added a `QC_HOST_ROLE` env var (`production` default,
   `staging` override) that forces the orchestrator's `enabled` flag to
   `False` on staging regardless of `AUTO_INVOKE_ORCHESTRATOR` — staging is
   validation-only, prod keeps live lesson traffic. This is the cheapest fix:
   it doesn't require making locks cross-host-visible at all, it just ensures
   only one side ever tries to auto-spawn.
2. **Make the lock token host-aware even though the lock itself stays
   host-local**, so a reentry check can't accidentally treat a same-named
   session id from a DIFFERENT host as "our own session" if the two hosts
   ever do end up racing (defense in depth, not the primary fix): holder
   token becomes `host_id:session_id` (via `QC_HOST_ID`/hostname) instead of
   bare `session_id`. Same-session (same host + same session id) reentry is
   still honored; a different session id is still refused. Legacy unprefixed
   tokens still parse for back-compat.
3. **Add a startup guard asserting `TEMP_DIR` never resolves under the
   mounted `LESSON_BASE_PATH`** — cheap insurance so this invariant (lock
   state is host-local, resource tree is shared) can't silently regress in a
   later change without a hard failure at boot.

**General lesson: when validating a migration by running the new host
alongside the old one against a shared backing store (a Drive mount, a
shared DB, a shared queue), audit every "watches the shared tree and takes
autonomous action" mechanism for whether it's now double-enabled** — this
class of bug doesn't show up in per-host testing (each host's own lock/tests
pass), only in the side-by-side arrangement, and it manifests as duplicate
work rather than a crash, so it's easy to miss unless you're specifically
looking for two hosts converging on the same resource.

## Real-usage parity audit methodology: mining the OLD host to validate the NEW one (2026-08)

After infra bring-up + the agent-behavior parity bugs above were fixed, the
final gate before cutover was a **parity audit against real prod usage**,
not another round of synthetic probes. Read-only on the Linux box throughout
(SSH, no writes) — this is the template for any future "does the new host
really cover what prod actually does" question:

1. **Mine the durable usage record on the OLD host, not its current live
   state.** Prod's `/data/claude-sessions` (Claude Agent SDK transcripts,
   thousands of real sessions) is the ground truth for "what commands/tools
   actually get invoked in practice" — far more reliable than reading code
   and guessing, or grepping current `docker logs` (which get wiped on every
   container recreate). Grep transcripts for `$TOOLS/*.py` invocations and
   rank by frequency to build a real usage inventory, not a theoretical one.
2. **Diff the live API surface exactly, not just spot-check a few routes.**
   Pull both hosts' `openapi.json` (FastAPI exposes this for free) and diff
   the route lists verbatim. An exact N/N match with 0 missing/0 extra is a
   much stronger parity signal than "I checked the endpoints I could think
   of."
3. **Classify every apparent gap as FIXED, BY-DESIGN, or REAL** before
   reporting — don't just list findings. A dep that's "missing from PATH"
   might be unused by any code path (verify by grepping for the actual call
   site, e.g. `shutil.which(...)`, before installing it); a behavioral
   difference might be an intentional isolation fix (e.g. auto-orchestrator
   off on staging) rather than a gap. Only escalate what's left as REAL.
4. **A real dep gap surfaced this way: LibreOffice (`soffice`) + poppler
   (`pdftoppm`) were missing on the Windows host.** They power the QC
   slide-text-quality agent's PPTX renderer (`pptx_renderer`: soffice →
   PDF → pdftoppm → PNG per slide); prod's container has both baked in.
   Without them the renderer's `is_available()` check silently degrades
   that one QC check to an XML-only fallback — no error, no crash, just a
   quieter/weaker check. **Choco's `poppler` package ships source only, no
   built `.exe`** — use the prebuilt `oschwartz10612/poppler-windows`
   GitHub release zip instead (`Expand-Archive` it under
   `C:\Program Files\poppler`, add `.../Library/bin` to Machine PATH).
   LibreOffice installs fine via winget/choco (`libreoffice-fresh`). Proved
   the fix, not just installed it: called `pptx_renderer.is_available()` →
   `True` and rendered real slides from a real lesson's PPTX on the host.
5. **When adding a dep-install block to a PowerShell setup script, run the
   ASCII grep on it explicitly as part of verification, not from memory.**
   Writing a plain English comment above a new `Install-Package` line
   re-introduced an em-dash into `setup.ps1` on this exact task — the same
   bug class documented in defect #3 above, on the same file, by the same
   kind of edit (an explanatory comment) that caused it the first time.
   The existing "grep before pushing" pitfall is necessary but is easy to
   forget to actually run on a *small* edit that doesn't feel like "editing
   infra scripts." Bake the ASCII check into whatever ad-hoc verification
   script runs against a `.ps1` diff (`all(ord(c) < 128 for c in text)`) so
   it fires automatically rather than relying on remembering a prose rule.
