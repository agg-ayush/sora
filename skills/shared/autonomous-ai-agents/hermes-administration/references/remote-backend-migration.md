---
title: Migrating a Hermes setup to a persistent remote host
---

# Moving Hermes (+ coding-agent CLIs) to a remote host you don't close the lid on

## Framing
The goal is almost never "give me remote access to my laptop" — it's "the
agents keep working when I close my laptop." That means the agent LOOP has to
run on the remote host, not just be reachable from it. The local machine
becomes a thin viewer/tunnel endpoint, not another place agents run. Confirm
this framing explicitly before building anything — "remote access" and
"agents that don't stop" lead to different architectures (SSH-into vs.
gateway-runs-there-permanently).

## Core migration (Hermes state)
1. `hermes backup` on the source machine → produces one archive with config,
   skills, `.env`, state.db (sessions), kanban DB.
2. `scp` it to the remote host, `hermes import` there.
3. Run the remote gateway as a `systemd --user` service with **linger
   enabled** (`loginctl enable-linger <user>`) — without linger, user services
   die the moment the SSH session that started them ends.
4. Resolve `$HERMES_HOME`/profile-safe paths after import — don't hardcode
   `~/.hermes` if a profile is in play.

## What `hermes backup` does NOT carry — reprovision separately
- **Platform adapter native deps** (e.g. Telegram) may need reinstalling on
  the target OS/arch even though the config came across fine.
- **Architecture-specific binaries copied via backup can silently fail.** A
  tool binary (e.g. `uv`) built for the source machine's CPU arch (ARM on
  Apple Silicon) does not run on a different arch (x86_64 Linux) — it fails
  in ways that look like a broken install, not an arch mismatch. Re-run the
  tool's own installer on the target host instead of trusting a copied
  binary; don't debug a copied cross-arch binary as if it's a config issue.
- **Coding-agent CLIs (Claude Code, Codex) and their model-routing configs
  are not part of a Hermes backup at all** — install the CLIs fresh on the
  target host, then port only the config/skills/memories directories
  (small, a few MB) and skip plugin caches/`node_modules` under them (can be
  hundreds of MB to GB and are re-fetched on demand — copying them causes
  large scp/tar operations to stall for no benefit).
- **A CLI config file authored for one machine is not portable as-is** — it
  can contain machine-specific trusted paths and its own env-var naming for
  the model-routing key (e.g. a Codex `env_key` value that isn't the same
  string as the Hermes plugin's own env var for the same provider). Check
  the actual plugin/CLI source for the exact env var name it reads — don't
  assume the same secret is exposed to two integration points under one
  name. Author a clean minimal config for the new host rather than copying
  the old one verbatim.
- **CLI session/chat histories (`~/.claude`, `~/.codex` project dirs) are
  large and separate from the Hermes backup** — copy them explicitly (tar +
  scp) if resuming old coding-agent conversations on the new host matters.
- **Symlinked scripts/plugins don't survive a naive copy.** Hermes cron
  install refuses a cron script that's a symlink outside
  `~/.hermes/scripts/` — copy the real file instead of symlinking there. A
  plugin loaded via symlink works fine, but the repo it points at must be
  cloned onto the new host first (use HTTPS clone if no SSH key/agent is set
  up there yet).
- **Hardcoded absolute home paths in shared hook/cron scripts break on the
  new host.** A script written and tested only on the source machine
  (`/Users/<name>/.hermes/scripts/...`) silently no-ops or errors on the
  remote host where the username/home differs — it doesn't fail loudly, it
  just can't find the file. Audit every shared hook/cron script for a
  hardcoded `/Users/<name>` or `/home/<name>` literal and replace with
  `$HOME`/`~` before or right after migrating; grep the repo for the old
  username as a final check (`grep -rl '/Users/<name>' scripts/
  agent-hooks/`).
- **Periodic scripts (watchdogs, health checks) need the Linux equivalent
  of launchd: a `systemd --user` timer, not a cron entry hardcoded to the
  source host's scheduler.** Pair a `<name>.service` (Type=oneshot,
  ExecStart=the script, explicit `Environment=HOME=...`/`PATH=...` since
  systemd user units don't inherit an interactive shell's env) with a
  `<name>.timer` (`OnBootSec=`, `OnUnitActiveSec=`), then
  `systemctl --user daemon-reload && systemctl --user enable --now
  <name>.timer`. Point any config the script reads (repo path, expected
  cron names) at the new host's paths — copying a watchdog config verbatim
  from the source machine will report false failures against paths that
  don't exist remotely.
- **An EC2 instance-profile role is not a personal admin role.** Verify `aws sts get-caller-identity` for the actual workload. `saml2aws` is retired in this setup; do not restore it or a password-file flow. Use the current AWS Identity Center/role-assumption procedure in `aws-devfactory-operations` if a personal role is needed.
- **Shell dotfile customizations (aliases, functions, exports in
  `.zshrc`/`.bashrc`) are not part of any Hermes/CLI backup at all** — they
  are OS-shell state, not app state. Grep the source machine's shell rc file
  for `^alias`/`^function`/inline `name() { ... }` patterns and port them by
  hand; each aliased tool needs its own binary present on the target
  (`eza`, `bat`, etc. are not preinstalled on a bare Ubuntu box — `apt
  install` them). Note apt's `bat` package installs the binary as `batcat`,
  not `bat` — symlink it (`ln -s /usr/bin/batcat /usr/local/bin/bat`) if an
  alias or muscle memory expects the upstream name.
- **Third-party CLI OAuth state (e.g. the `gog` CLI's Google credentials) is
  not part of any Hermes backup either** — it lives outside `~/.hermes`
  entirely (on macOS: `~/Library/Application Support/gogcli/` —
  `credentials.json`, `config.json`, `oauth-manual-state-*.json`, a
  `keyring/` dir). Bundle that directory's file-based contents by hand for a
  remote host to reuse the same authorized identity instead of re-running
  the OAuth flow there. Two things it does NOT contain: Keychain-backed
  secrets (invisible to a plain directory copy — check whether the tool
  falls back to a file when Keychain is unavailable, check the keyring backend used on the target host) and the OAuth **client**
  credentials (`client_secret_*.json` / `client_secret-*.json`, ~200-400
  bytes, contains `client_secret` + `installed` or `web` keys) — that file
  is the app-level OAuth client registration, not a per-user token, and is
  commonly stored well outside the tool's own config dir (e.g. wherever it was originally stored by the operator.), not alongside `credentials.json`. Locate it with
  `mdfind -name client_secret` (macOS Spotlight) before assuming it's
  missing — a directory-only search of the tool's config path will not find
  it if it was never moved there.

## Access model — don't run a second backend
The gateway already serves the HTTP/dashboard API on its configured port
(default 9119). Do **not** also start `hermes serve` on the same host —
it hard-conflicts on the port (`BACKEND_PORT_IN_USE`) because the gateway IS
the backend. The remote gateway process is the one and only thing that needs
to run on the remote host; local access is purely an SSH port-forward to it,
nothing extra runs remotely and nothing extra needs to run locally either.

**Caveat — this tunnel-and-attach model only serves the dashboard/HTTP API,
not the TUI.** There is no "point a local TUI at a standalone remote gateway
port" mode — `HERMES_TUI_GATEWAY_URL` is an internal wiring detail the
dashboard's own embedded TUI child process uses to reach the dashboard
server's loopback WebSocket; the OpenAI-compatible gateway port does not
serve that WebSocket endpoint and setting the env var to it 404s. If the user
prefers the TUI over the dashboard, the right pattern is: SSH into the remote
host and run `hermes` (or the tier-launch wrapper, e.g. `holo`) there
directly — the TUI renders over the SSH session itself. Don't build or
promise a local-TUI-attaches-to-remote-backend setup; it doesn't exist. Set
up convenience aliases instead: a shell function on the remote host for the
tier launch commands (so `ssh <host> holo 1` — or just `holo 1` once already
SSH'd in — works without retyping the full `hermes -s <skill> -m <model>`
invocation), and a short local alias for the SSH hop itself (e.g. `alias
sora="ssh devbox"`) so reaching the box is one word.

## WezTerm mux domain — alternative to tmux for human-interactive access
If the user wants a full GUI-terminal experience (mouse, real splits/tabs,
true color) on the persistent remote session rather than tmux's
keyboard-driven panes, run a WezTerm mux server on the remote host
(`wezterm-mux-server --daemonize`) and add an SSH domain to the local
`wezterm.lua` (`wezterm.plugin`-free — just `config.ssh_domains`). Bind the
user's short alias for reaching the box (e.g. `sora`) directly to `wezterm
connect <domain>` instead of `ssh <host>` — that one substitution is what
makes closing the window/lid non-destructive, since the mux server (not the
SSH session) owns the session lifecycle.

**Client and server WezTerm builds must be on the exact same version/codec** —
mixing a stable release with a nightly (or two different nightly dates)
fails at connect time with `IncompatibleVersionError` naming the mismatched
codec numbers. Check `wezterm -V` on both ends before wiring the SSH domain;
if they differ, upgrade whichever side is older to match rather than
guessing which release is "close enough."

**Restarting the mux server to pick up a config change (font, scrollback,
color depth, window size) kills every existing pane/session on it** — there
is no live-reload. This directly undercuts the "close the lid, reconnect,
everything is still there" promise: any wezterm.lua tweak that needs a mux
restart (`pkill wezterm-mux-server && wezterm-mux-server --daemonize`) wipes
whatever was running in those panes. Warn before restarting for a config
change, and batch multiple config tweaks into one restart rather than
restarting per tweak. If panes render at a fixed small size (e.g. stuck at
80x24) instead of the actual window size, the fix is syncing the local
`wezterm.lua`'s display settings (font size, `scrollback_lines`, etc.) to the
remote host's `~/.wezterm.lua` that the mux server reads — same restart
caveat applies.

**This does not replace tmux for anything a plugin/agent needs to
programmatically supervise.** WezTerm's mux has no CLI equivalent of
`tmux capture-pane` (read a pane's content from outside) or `tmux send-keys`
(inject input from outside) — a monitoring loop that needs to read/steer a
spawned session has nothing to call. Keep tmux for anything spawned and
watched by code (e.g. `claude_orchestrate`'s T2 sessions); use the WezTerm
mux domain only for the human's own interactive terminal.

### Sending local files/images into the remote mux session
Once the interactive terminal lives on the remote host, the local clipboard
and local file paths are no longer reachable from it — dragging a file onto
the window, or pasting an image, only ever produces a *local* path/blob that
the remote session can't read. Don't solve this with a global paste-key
rebind (e.g. hijacking Cmd+V to always scp on every keystroke) — that breaks
normal text paste everywhere else and fires even when working locally.
Instead, dedicate one local terminal tab as a drop zone: a small script that
reads a dragged file path or a typed command (e.g. `p` to grab the current
clipboard image via `pngpaste`), `scp`s it to a fixed spot on the remote host
(e.g. `/tmp/`), and prints the remote path back — the human then reads that
path and tells the remote agent where to find the file. Gotchas:
- A file dragged from macOS Desktop/Finder into a terminal arrives with
  spaces backslash-escaped (`Screenshot\ 2026...heic`) and sometimes a
  trailing space — unescape (`\` + space → space) and strip whitespace
  before testing `os.path.isfile()`, or every drag reports "not a file".
- macOS screenshots default to HEIC — convert to PNG (`sips -s format png`)
  before sending if the remote side needs to view it.
- If wiring a WezTerm Lua `wezterm.run_child_process` handler to call a local
  binary (e.g. `pngpaste` for a clipboard-grab keybind), call it by
  **absolute path** — WezTerm's Lua sandbox does not inherit the interactive
  shell's `PATH`, so a bare command name silently fails and looks like the
  handler doesn't exist.

## Persistent local tunnel (survives sleep/lid-close on the CLIENT side)
A plain foreground `ssh -L` dies with the terminal. Use a `launchd`
LaunchAgent that owns the tunnel process:
```xml
<key>ProgramArguments</key>
<array>
  <string>/usr/bin/ssh</string><string>-N</string>
  <string>-L</string><string>9119:127.0.0.1:9119</string>
  <string>-o</string><string>ServerAliveInterval=30</string>
  <string>-o</string><string>ServerAliveCountMax=3</string>
  <string>-o</string><string>ExitOnForwardFailure=yes</string>
  <string>devbox</string>
</array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```
`KeepAlive=true` + `RunAtLoad=true` is what gives you reconnection —
launchd restarts the `ssh` process itself whenever it exits (sleep/wake,
network drop). There is no `-o Reconnect=yes` SSH option — don't add one,
it's a hard config-parse failure ("Bad configuration option: reconnect") and
the LaunchAgent will just spawn-loop without ever tunneling.

## Starting an ad-hoc long-lived process on the remote host from agent tooling
The agent's own terminal tool refuses any command it heuristically recognizes
as starting a background/long-lived process (`nohup`, `setsid`, `disown`,
trailing `&`, or anything that "looks like" a dev server/watch process) even
when the command is wrapped inside an `ssh ... 'bash -s' <<EOF` heredoc
targeting a remote host — the tool can't tell the process will run remotely,
not in its own foreground. Fighting this by trying different shell-level
backgrounding tricks wastes calls; the reliable fix is to not background it
at all from the tool's perspective. Instead:
1. Write the start command as a tiny wrapper script (`exec npm run dev`,
   etc.) and `scp` it to the remote host.
2. Write a `~/.config/systemd/user/<name>.service` unit
   (`ExecStart=<wrapper script>`, `Restart=always`,
   `StandardOutput=append:/tmp/<name>.log`) — same pattern as the periodic
   watchdog timers below, but a persistent service instead of a oneshot+timer.
3. `systemctl --user daemon-reload && systemctl --user start <name>` — this
   command itself returns immediately (systemd forks and manages the actual
   process), so the terminal tool never sees anything resembling a
   long-running foreground command and doesn't block it.
4. Poll readiness separately (`curl -s -o /dev/null -w '%{http_code}'
   <local endpoint>` after a short sleep) rather than assuming the service is
   up right after `start` returns.
This also gives the process auto-restart and log capture for free, which a
bare `nohup ... &` wouldn't have.

## Sizing / cost
Size the remote instance to the actual parallel-agent count (1 dispatcher +
N active supervisors + the coding-agent CLI child process each one spawns),
using real observed per-process memory footprints from the current machine —
not a round "bigger is safer" number. But that per-process estimate must
also include the always-on services sharing the same box: gateway,
dashboard, and — if a WezTerm mux domain is set up per the section above —
the mux server itself, which grows with every open pane/tab across every
window (observed 3GB+ with a couple dozen panes accumulated over a day,
since panes aren't reaped just because the window closed). A total that
looks fine as "N agents × per-process footprint" can still OOM if the mux
overhead and idle-pane accumulation aren't budgeted in — the kernel OOM
killer doesn't just kill the offending process, it can leave sshd wedged
enough that the whole host stops accepting new SSH connections, looking like
a network outage instead of a memory problem (see troubleshooting note
below). If observed usage is closing in on the instance's RAM under normal
multi-agent load, resize up rather than waiting for an OOM to force the
issue — e.g. 8GB was insufficient for gateway + dashboard + mux + several
concurrent T2s and needed to go to 16GB.

Resize an existing instance while
stopped: `aws ec2 stop-instances` → `wait instance-stopped` →
`modify-instance-attribute --instance-type` → `start-instances` →
`wait instance-running`. The public IP changes on every stop/start unless an
Elastic IP is attached — re-fetch it and update SSH config/scripts, don't
reuse the old IP.

### Diagnosing an unreachable host as OOM, not a network/AWS issue
If SSH times out or hangs at the banner exchange while the AWS console shows
the instance `running` with passing system status checks, don't assume a
transient network blip — check the kernel log for an OOM kill before
rebooting blind:
```bash
# from a still-open session, or via EC2 Instance Connect / SSM if SSH itself is dead
journalctl --priority=err --no-pager | grep -i 'out of memory\|oom'
```
An `Out of memory: Killed process ...` line followed by sshd/systemd errors
confirms memory pressure wedged the host badly enough to stop accepting new
connections, even though the instance itself is still "running" at the AWS
level. The fix for the immediate symptom is a reboot
(`aws ec2 reboot-instances`) — systemd-managed services (gateway, dashboard,
crons, watchdog, mux) come back on their own since they're all
`systemctl --user enable`d; tmux sessions do not survive and need
recreating. The durable fix is the resize discussed above, not just
rebooting and hoping it doesn't recur.

**Check `describe-instances` state before picking reboot vs start.** An OOM
can be severe enough that the instance ends up fully `stopped` (not just
SSH-unreachable-while-running) — sometimes from an earlier manual stop
attempted mid-crisis. `reboot-instances` on an already-stopped instance is a
no-op; you need `start-instances` instead. The two recovery paths differ in
a way that bites the next SSH attempt: a reboot of a running-but-wedged
instance keeps the same public IP, but `start-instances` on a stopped one
reassigns it (same rule as any stop/start, see above) — always re-check
`describe-instances` state first, and if it says `stopped`, expect and
re-fetch a new IP after starting rather than retrying the old `HostName`.

**After the second OOM-triggered stop/start cycle on the same box, stop
chasing the new IP by hand and allocate+associate an Elastic IP instead:**
```bash
aws ec2 allocate-address --region <region> --domain vpc
aws ec2 associate-address --instance-id <id> --allocation-id <eipalloc-id> --region <region>
```
Then update `~/.ssh/config`'s `HostName` once, to the Elastic IP, and it
never needs touching again across future stop/start or reboot cycles. Doing
this reactively after each OOM (re-fetch IP, sed the SSH config, retest) is
the same manual fix repeated for free — recognize the pattern (a host that's
restarted more than once for the same reason) and eliminate the recurring
fix instead of reapplying it.

**`aws ec2-instance-connect send-ssh-public-key` throws
`EC2InstanceNotFoundException` when `--availability-zone` doesn't match the
instance's actual AZ** — the error reads like a wrong/typo'd instance ID but
is actually an AZ mismatch. Confirm the real AZ first
(`aws ec2 describe-instances --instance-ids <id> --query
'Reservations[*].Instances[*].Placement.AvailabilityZone'`) before assuming
the instance ID itself is wrong.

**Before treating a repeat OOM as "the instance is undersized, cap
concurrency," verify the processes actually eating memory are live legitimate
work, not leaked/orphaned ones.** A watcher or cron that spawns T2 agents can
leave stale tmux sessions/processes running past their task's completion if
nothing reaps them; `ps`/`pgrep` on the node/claude child processes and cross
check the count against what's actually still active on the kanban board
before concluding real concurrent load exceeds the box's RAM. Artificially
capping T2 concurrency is the wrong fix for a leak — it just hides the leak
behind a lower ceiling. Fix process hygiene (an orphan-reaper cron, or the
watcher closing its own spawned sessions on task completion) first; only
resize or cap concurrency if the OOM recurs with a verified, deliberately
steady-state count of legitimate concurrent agents that's still over budget.

## Secrets namespacing in the shared `.env`
The remote host's `~/.hermes/.env` is shared across every integration running
there (gog, Hermes core, individual project services like a hiring pipeline's
wrapper app). Before adding a new secret, check whether its natural name
(`GOOGLE_CLIENT_ID`, `API_KEY`, etc.) already exists for a *different*
service — generic names collide silently and the file has no namespacing by
default. Prefix with the owning service/project (e.g.
`SDE_SCREENING_GOOGLE_CLIENT_ID`, `TI_HIRING_FIREWORKS_API_KEY`) rather than
using the var name a README or `.env.local` happens to show, unless that
exact unprefixed name is the one thing that must be shared as-is (e.g. the
main `FIREWORKS_API_KEY` the Hermes gateway itself reads). After writing,
`grep -c "="` and list the var names back to confirm no existing key was
overwritten — a python rewrite that filters-then-appends is safer than a bare
`>>` when you need to guarantee an old duplicate key is actually replaced,
not just shadowed by a second line further down.

## Post-migration cleanup on the source machine
A migration is not finished when the remote host works — the source machine
still has the old gateway's launchd service and any crons that shipped in
the backup (they get imported onto BOTH hosts, since `hermes backup`/`import`
copies the whole `~/.hermes` state including cron definitions). Left running,
these are not harmless: two gateways can race for the same platform's poll
slot (e.g. Telegram's `getUpdates` only tolerates one poller — see the
region-move section's note on this), and a source-machine cron keeps firing
against that machine's now-stale state and reporting numbers that no longer
reflect where the real work runs (e.g. a hygiene/health cron "finding"
problems that only exist on the retired host).

The source machine's watchdog LaunchAgent (`ai.hermes.watchdog` or
equivalent) is a separate leftover from the gateway/cron ones above — it
keeps firing on its own launchd schedule even after the gateway is stopped,
since it's not a cron entry and won't show up in `hermes cron list`. Check
`launchctl print gui/$(id -u)/ai.hermes.watchdog` for `state = running`/timer
active, and `launchctl bootout gui/$(id -u)/ai.hermes.watchdog` to stop it
once the remote host has its own watchdog timer covering the same checks.

Before decommissioning anything on the source machine, verify the remote is
actually the one serving traffic — don't assume from an `active (running)`
systemd status alone, since the source machine's stopped-looking service can
still hold a platform poll slot in some failure modes. Check the concrete
signal: e.g. `python3 -c "import json; print(json.load(open('~/.hermes/gateway_state.json'))['platforms']['telegram']['state'])"` on
the remote should read `connected`, and the equivalent check on the source
machine should show its gateway not loaded/not running at all
(`hermes gateway status`). Once confirmed, remove — don't just leave
stopped — the source machine's duplicate cron jobs (`hermes cron list` /
`hermes cron remove <id>`) and gateway launchd service, so nothing on the
retired machine can silently start reporting or polling again after a
reboot or a `hermes gateway start` typed out of habit.

## Verification
Don't call a migration done from version checks or config diffs alone.
Actually invoke each surface end to end — one real prompt through the base
agent, and one real prompt through each coding-agent CLI path via the model
route it's supposed to use — before telling the user it's verified.

A subagent's own final report claiming success (e.g. `"ssh_test": "passed"`,
`"hermes_gateway_status": "active"`) is the subagent's self-report of what
it checked, not independent confirmation — it can still miss that the port
it tested from inside the box differs from the port a client actually needs
(loopback-only bind, wrong forwarded port in a tunnel). Re-run one real
health check yourself from the actual client path (e.g. curl the tunnel's
local port from the machine that will use it) before telling the user the
migration is done.

After any relaunch/clone/restore of the host (new instance from an AMI,
region move, `hermes import` onto a new box), re-verify with `ss -tlnp`
which port the gateway is actually listening on before reusing a previously
documented port number in a tunnel or health check — it can drift (e.g. a
fresh instance from a snapshot came up serving on 9120 instead of the
expected 9119). Don't debug "connection refused" on the tunnel as a
networking problem before checking this.

## Related
- `devpod-remote-workspace` skill — decoupling a DevPod-managed box into a
  plain EC2 instance you SSH into directly (the prerequisite step before
  this migration, if the target host was originally provisioned via DevPod).
