# Hermes Tier Setup

Custom Hermes Agent tier orchestration: plugin, skills, scripts, reference docs,
and config templates for the multi-tier autonomous coding pipeline.

## Structure

```
plugin/     claude-orchestrate plugin (pure tmux session manager)
plugins/    pr-review-toolkit patches (state-transition-reviewer specialist)
skills/     tier1-suborchestration + tier2-orchestration skills
scripts/    orphan-reaper.py (self-healing watchdog) + hermes-hygiene.py (weekly storage/health) + error-journal.py (failure capture) + watch_ci_main.py (CI watcher) + deny-guard.sh (T3 hook) + subagent-ledger-hook.py (subagent_stop hook → delegation ledger) + aws-token-refresh-hook.sh (post_tool_call hook → auto saml2aws refresh) + hermes-state.py (host-state audit, compare, export, restore)
docs/       hermes-tiers-reference.md (canonical architecture) + audit.md
config/     config.yaml.template (current routing, regenerated from the live Mac config), env.template, zshrc-snippet.sh, watchdog launchd/systemd units, state-manifest.yaml (classification of host state for hermes-state.py) (NO secrets)
patches/    local Hermes source patches applied by setup-hermes.sh
hosts/      per-host profiles (mac, sora, wsl): host-only scripts, systemd/launchd units, cron-jobs.json, watchdog.json, plugins.txt, config-overrides.yaml
```

## Install / Sync (Mac or Ubuntu EC2 `sora`)

Run the idempotent setup script (`devbox/setup-hermes.sh`) — it installs sidelined tools (`ruff`, `oxlint`, `smem`), wires the `claude-orchestrate` and `synapse-mem` plugins, syncs all tier skills, scripts, and agent-hooks (`subagent-ledger.py`, `aws-token-refresh.sh`, `t3-stop-gate.py`), links `~/.hermes/claude-k3-config` (`CLAUDE.md`, `skills/`, `plugins/`) to `~/.claude` with all plugins enabled, patches `pr-review-toolkit`, and sets global gitignore (`.serena/`, `.ui-flow/`):

```bash
git clone https://github.com/agg-ayush/sora.git ~/hermes-setup
bash ~/hermes-setup/devbox/setup-hermes.sh
```

What `devbox/setup-hermes.sh` sets up:
1. **Sidelined CLI binaries:** `ruff` (`uv tool install ruff`), `oxlint` (`npm install -g oxlint`), and `smem` (`~/repos/synapse-mem/integrations/install/install-smem.sh` if cloned).
2. **Hermes plugins & memory:** Symlinks `~/hermes-setup/plugin` → `~/.hermes/plugins/claude-orchestrate` and activates `synapse-mem` (`memory.provider: synapse-mem`).
3. **Hermes skills:** Symlinks `tier1-suborchestration`, `tier2-orchestration`, and the Claude Code `ui-flow` skill; copies `skills/devops/aws-devfactory-operations`.
4. **Scripts & hooks:** Copies repo scripts into `~/.hermes/scripts/` (matching host variant `aws-creds-refresh.sh` on Mac vs `aws-creds-refresh-linux.sh` on Linux so `watchdog.py` sees zero script drift) and hooks into `~/.hermes/agent-hooks/`.
5. **Claude Code setup:** Links `~/.hermes/claude-k3-config/{CLAUDE.md,skills,plugins}` → `~/.claude/`, enables installed plugins in the isolated Fireworks `settings.json`, and copies the `state-transition-reviewer` specialist into `pr-review-toolkit`.
6. **Global gitignore:** Adds `.serena/`, `.ui-flow/`, and `**/.claude/settings.local.json`.

## Install on Windows (WSL2)

Sora runs entirely inside a WSL2 Linux distro; nothing is installed on the Windows side.

**Prerequisites:** WSL2 with an Ubuntu distro already set up (`wsl --install -d Ubuntu` from Windows), and a
shell open inside it as your normal user. Clone into the Linux home directory, not under `/mnt/c/`.

```bash
git clone https://github.com/agg-ayush/sora.git ~/hermes-setup && bash ~/hermes-setup/devbox/bootstrap-wsl.sh
```

`devbox/bootstrap-wsl.sh` is idempotent (re-run it at any time; `--dry-run` shows what it would do and exits 2
when something would be installed, 0 when nothing is missing) and installs only what is missing:

1. **apt packages** via `sudo apt-get` (it lists them first): `git`, `curl`, `ca-certificates`, `tmux`, `python3`,
   `python3-venv`, `jq`, `wslu`.
2. **uv** (Astral installer), **Node.js LTS** via nvm, **Hermes Agent** (official installer, non-interactive) and
   **Claude Code** (native installer), all under your home directory. Windows copies of these tools that WSL
   exposes from `/mnt/c/...` are ignored. An nvm default that is already Node 18 or newer is kept.
3. **`devbox/setup-hermes.sh`**, which selects the `wsl` host profile automatically.

Afterwards open a new terminal, run `claude` once to sign in, and run `hermes setup` to choose a model provider
(keys go in `~/.hermes/.env`). `BROWSER` defaults to `wslview` (from `wslu`) so login pages open in the Windows
browser; a `BROWSER` you set yourself is kept. If a step fails, the bootstrap stops with an error that says what to
fix and how to re-run.

**systemd:** with systemd enabled in the distro, user units are installed as on Linux. Without it, units are
skipped and setup continues. To enable it, add this to `/etc/wsl.conf`, run `wsl --shutdown` from Windows, reopen
the distro and re-run `devbox/setup-hermes.sh` (with `HERMES_INSTALL_GATEWAY=true` if you want the gateway):

```ini
[boot]
systemd=true
```

**Gateway:** the `wsl` profile does not install the Hermes gateway service by default, and Hermes cron jobs only
run while a gateway is running. Opt in with `HERMES_INSTALL_GATEWAY=true bash ~/hermes-setup/devbox/setup-hermes.sh`.
The watchdog timer, which reports on the gateway, is installed only together with it. If the opt-in fails, setup
prints an error block with the re-run command and exits 3. Without systemd the gateway falls back to running under
`nohup` and stops when its WSL session closes. A gateway unit installed before systemd was turned on is not enabled
automatically; setup prints the `systemctl --user enable --now hermes-gateway.service` command to run.

**`/mnt/c` checkouts:** a clone on the Windows filesystem is slow and loses Linux file permissions; the scripts
warn about it. Clone into `~` instead. `.gitattributes` forces LF line endings, so a clone made by Windows git
with `core.autocrlf=true` still runs.

## Host profiles (`hosts/<mac|sora|wsl>/`)

Everything that exists on only one machine lives in a profile; `setup-hermes.sh` (step 9, `devbox/host-profile.sh`)
installs it **only when absent** — it never overwrites, restarts, enables or disables anything that exists.

| Item | Where | Installed when |
|---|---|---|
| host-only scripts | `scripts/` -> `~/.hermes/scripts/` (real copies) | file missing |
| helper binaries | `bin/` -> `~/.local/bin/` | file missing |
| systemd / launchd units | `systemd/`, `launchd/` (`reference/` = not installed) | unit file missing; only newly installed units are enabled/started. A leading `# requires: <path>` line gates a unit on that path. |
| cron jobs | `cron-jobs.json` | no job with that name (recorded enabled/paused state kept) |
| plugins | `plugins.txt` (`name [identifier]`) | missing from `hermes plugins list` |
| `watchdog.json` | profile root | missing (on `wsl`, an existing one that alerts via Telegram gets a warning) |
| config keys | `config-overrides.yaml` | only when `config.yaml` was created from the template in the same run |
| gateway service | not copied; `hermes gateway install --if-missing` | no gateway service installed (never on a Mac that has a Telegram token; on `wsl` only with `HERMES_INSTALL_GATEWAY=true`) |

Profile = `mac` on Darwin, `wsl` under WSL (detected from the kernel release or `WSL_DISTRO_NAME`), `sora` on other Linux; override with `HERMES_HOST_PROFILE=<name>`; skip with `HERMES_SKIP_HOST_PROFILE=true`.
No chat ids or secrets are stored: scripts read `TELEGRAM_HOME_CHANNEL` / `TI_CONCERN_TELEGRAM_CHAT`
from `~/.hermes/.env` (names in `config/env.template`). Repo copies of sora scripts are parameterized, so they differ from the live
files only in hardcoded paths, chat ids and the tracker doc id. `tests/test_host_profiles.py` enforces this.

## Usage

```bash
holo 1      # start Tier-1 (per-repo dispatcher)
holo 2      # start Tier-2 (per-issue supervisor, usually spawned by T1)
holo dash   # open the web dashboard (localhost:9119)
```

## Self-healing watchdog

The `orphan-reaper.py` cron (every 30 min) doesn't just kill idle sessions — it
**heals recoverable failure modes** before considering a session idle:

- **Context compaction prompt** → auto-answer "y" (compact the conversation)
- **`redacted_thinking` corruption** → kill + supervisor respawns (targeted kill)
- **Rate-limit prompt** (`/rate-limit-options`) → auto-press option 1 (stop + wait)
- **Stuck prompt** (y/n question) → auto-answer "y" (proceed)

Only kills genuinely idle sessions (no active work, no recoverable failure, no
prompt to answer). Never kills an actively-working session or a session at a
prompt waiting for a steer.

See `docs/hermes-tiers-reference.md` for the full architecture reference.

## Moving to a new host

`scripts/hermes-state.py` classifies everything under `~/.hermes`, `~/.claude` and `~/.smem` with
`config/state-manifest.yaml` and moves the personal part between hosts. Run it with the Hermes venv
interpreter, which carries PyYAML (the system `python3` does not):

```bash
PY=~/.hermes/hermes-agent/venv/bin/python
$PY ~/.hermes/scripts/hermes-state.py audit              # unclassified entries + fingerprint (--json for machines)
$PY ~/.hermes/scripts/hermes-state.py compare a.json b.json
```

**On the old host.** Stop Claude Code and Hermes sessions, then export. gpg asks for the passphrase
at its own prompt; there is no passphrase flag. `export` refuses while `audit` reports unclassified entries.

```bash
$PY ~/.hermes/scripts/hermes-state.py export --out /safe/place/hermes-state.gpg
# add --include-secrets to also carry .env, auth.json, mcp-tokens, config.yaml and the backup trees
```

History (`state.db`, `~/.claude/projects`) may hold pasted secrets, so treat every bundle as sensitive.
`~/.claude.json` is not carried; the first `claude` login recreates it, and its user-scope MCP servers
need re-adding. `~/.claude/projects/*` dirs keep the old path in their names.

**On the new host**, in this order:

1. Install the prerequisites. On WSL: `sudo apt-get install lsof gnupg`. Copy the bundle and its `.sha256`.
2. Run `devbox/setup-hermes.sh` (the repo checkout, scripts and manifest land first).
3. Stop everything that holds state open: close all Claude Code sessions (smem's MCP server keeps
   `~/.smem/smem.db` open) and stop the gateway the first setup may have started, with
   `systemctl --user stop hermes-gateway` on Linux. Restore refuses while the gateway runs or a SQLite file is held open.
4. Preview, then restore:
   ```bash
   $PY ~/.hermes/scripts/hermes-state.py restore --from /safe/place/hermes-state.gpg --dry-run
   $PY ~/.hermes/scripts/hermes-state.py restore --from /safe/place/hermes-state.gpg
   ```
   Every file it overwrites is first moved to `~/.hermes/state-restore-backups/<timestamp>/`. The source
   home path is rewritten in text config files. The smem store replaces the destination `smem.db`; rows are never merged.
5. Run `devbox/setup-hermes.sh` again so setup re-creates the repo links and installs the host profile.

**Direct cable or WSL, without gpg.** For a wired move where gpg is a hurdle, both sides can opt into a plaintext
gzip bundle. The default stays the encrypted bundle above; pass `--unencrypted` to `export` and to `restore`:

```bash
$PY ~/.hermes/scripts/hermes-state.py export --unencrypted --out /safe/place/hermes-state.tar.gz
$PY ~/.hermes/scripts/hermes-state.py restore --unencrypted --from /safe/place/hermes-state.tar.gz --dry-run
$PY ~/.hermes/scripts/hermes-state.py restore --unencrypted --from /safe/place/hermes-state.tar.gz
```

With `--unencrypted` gnupg is not needed on either host. Keep the bundle outside any git checkout, and copy the
`.sha256` along with the bundle; restore refuses without it. The bundle is not encrypted and may hold secrets and
history: do not upload it. After restore, delete the bundle, its `.sha256`, `.lock` and any `.partial` on both hosts.
A bundle written without the flag is refused with the flag, and the reverse, so give both commands the same choice.
6. Run `audit`. Exit 0 means every entry is classified; restore itself exits 3 when its closing audit is not clean.

Things restore tells you about, and what to do:

- **Telegram.** Only one host may poll the bot (`TELEGRAM_BOT_TOKEN` in `.env`, or `platforms.telegram.enabled`).
  Restore warns by key name when a non-gateway host receives a Telegram-enabled config; do not start a second poller.
- **Plugins.** Restored `plugins/<name>` entries missing from `hosts/<profile>/plugins.txt` are listed; each needs `hermes plugins install`.
- **Config overrides.** Setup applies `hosts/<profile>/config-overrides.yaml` only to a new config, so a restored
  `config.yaml` from another profile does not get the destination's overrides; review the file by hand.
- **Not-yet-seeded hosts.** The manifest is seeded from the Mac. A first `audit` on sora or WSL may list unclassified
  entries; `export` stays refused until a follow-up manifest PR classifies them.

The weekly `hermes-hygiene` run reports unclassified entries and fingerprint changes. Creating
`<state dir>/hermes-state-audit.off` (default `~/.hermes/watcher-state/`) turns that step off on one host.
On WSL hygiene only fires while a gateway runs, so run `audit` by hand there.

## Local upstream mods

We carry a small number of local patches to the live `~/.hermes/hermes-agent`
clone that are NOT pushed upstream (TrueFoundry tool-call ID compatibility,
Claude Teams/direct-Anthropic OAuth identity, session-bubble fix). They live in
`patches/*.patch` and `devbox/setup-hermes.sh`
applies them idempotently. See `docs/local-upstream-mods.md` — re-run setup
after every `hermes update`.

## Public mirror (agg-ayush/sora)

`agg-ayush/sora` is a generated, scrubbed public copy of this repo. Make public changes here and never directly in sora:
a hand edit to sora stops the generator (it refuses to publish over commits it did not make) until the change is ported
here and the sora head is committed as the accepted base in `scripts/public-mirror/accepted-base.txt`.

`.github/workflows/public-mirror.yml` runs the suite on every push and pull request. On a push to `main` (or a dispatch on
`main`) the `mirror` job, in the `public-mirror` environment, runs `scripts/public-mirror/publish.py`: it builds the public tree
from the commit's git objects (exclude list, secret scrub rules, public rewrites), gates the result for leaks, and pushes one
commit on top of sora main with a deploy key. It never force-pushes. The generator itself (`.github/`, `scripts/public-mirror/`,
its test) is not published.

### Mode

The repository variable `PUBLIC_MIRROR_MODE` selects what a push or dispatch on `main` does:

| Value | Effect |
|---|---|
| `off` | tests only, the `mirror` job does not run |
| `dry-run` (also when unset) | build and gate, print the summary and diff stat, push nothing |
| `publish` | a push to `main` publishes; a dispatch publishes when `dry_run` is false |

Any other value fails the run. Branches and pull requests run the tests only; preview a branch locally with
`python3.11 scripts/public-mirror/publish.py --source HEAD --sora-git ~/repos/sora --rules-dir <rules dir> --dry-run`.

A later push replaces an older pending publish run, and its newer main carries the earlier content. If a manual re-run of an old
run publishes older content (the run prints `warning: newer main <sha> exists`), recover by running the workflow on `main`
with a dispatch whose `dry_run` input is false (mode `publish`): it publishes the newest main.

### Leak gate findings

The gate fails the run with exit 1 and prints `path:line class` (never the value). A `path-name <fingerprint> <class>` finding
hides the path itself; locate it locally with the same dry-run command plus `--show-paths`, then rename or exclude the file.
Message findings clear with the next push. For a known-safe value in a file, add a reviewed baseline entry in a PR:

```bash
python3.11 scripts/public-mirror/publish.py baseline add --from HEAD --rules-dir <rules dir> \
  --select <path>:<line>:<class> --reason "<why it is public>"
```

Add `:<k>` (1-based, left to right) when the line holds several findings of that class. Classes a and i, path names,
messages and private clone URLs can never be baselined. `baseline prune --from HEAD --rules-dir <rules dir>` drops entries no
finding uses; it never adds one. The baseline stays in this private repo.

### Pinned GitHub host keys

`.github/public-mirror/known_hosts` pins GitHub's SSH host keys (`StrictHostKeyChecking=yes`). If GitHub rotates a host key the
fetch fails with a host key mismatch. Refresh the file in a PR from `gh api meta --jq '.ssh_keys[]'` (prefix each line with
`github.com `), not from an unauthenticated scan.

### Rotating the mirror credentials

`SORA_DEPLOY_KEY` and `PUBLIC_MIRROR_RULES` are secrets of the `public-mirror` environment, whose only deployment branch is
`main`. Every `gh secret set` below carries `--env public-mirror -R agg-ayush/hermes-setup`; a repository-level copy would be
readable from branch workflows and must not exist.

**Deploy key.** Work in a mode-700 temp dir and never print the private key:

```bash
umask 077; KDIR="$(mktemp -d)"
ssh-keygen -q -t ed25519 -N '' -C public-mirror -f "$KDIR/key"
ssh-keygen -q -t ed25519 -N '' -C never-added -f "$KDIR/never"
gh repo deploy-key add "$KDIR/key.pub" --allow-write -R agg-ayush/sora -t public-mirror
SSH_OPTS="-F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=.github/public-mirror/known_hosts"
```

Prove the key and the host pinning before uploading. The proof drops `~/.ssh/config` and the agent, so only the new key can
authenticate (sora is public, so any identity could otherwise read it):

```bash
git ls-remote https://github.com/agg-ayush/sora.git refs/heads/main
GIT_SSH_COMMAND="ssh $SSH_OPTS -i $KDIR/key -l git" git ls-remote ssh://github.com/agg-ayush/sora.git refs/heads/main
ssh $SSH_OPTS -i "$KDIR/key" -T -l git github.com
GIT_SSH_COMMAND="ssh $SSH_OPTS -i $KDIR/never -l git" git ls-remote ssh://github.com/agg-ayush/sora.git refs/heads/main
ssh $SSH_OPTS -i "$KDIR/never" -T -l git github.com
```

The two `ls-remote` calls with the new key must print the same sha, and its `ssh -T` greeting (it exits 1 by design) must name
`agg-ayush/sora`. The never-added key must print no sha and its greeting must not name `agg-ayush/sora`. Record only those
booleans. Then upload the key, delete the old key by id and remove the temp dir:

```bash
gh secret set SORA_DEPLOY_KEY --env public-mirror -R agg-ayush/hermes-setup < "$KDIR/key"
gh repo deploy-key list -R agg-ayush/sora
gh repo deploy-key delete <old key id> -R agg-ayush/sora
rm -rf "$KDIR"
```

**Rules.** Edit `replacements.txt`, `mailmap.txt` and `deny.txt` only in the archive rules dir `~/hermes-archive/sora-public-rules/`;
they hold the sensitive scrub rules and are never committed. Rebuild the bundle with `pack-rules` under Python 3.11.4 or
later (plain `tar` adds macOS metadata members the loader rejects); it prints counts only, including `deny patterns: <n>`:

```bash
KDIR="$(umask 077; mktemp -d)"
python3.11 scripts/public-mirror/publish.py pack-rules --rules-dir ~/hermes-archive/sora-public-rules --out "$KDIR/rules.b64"
```

Check the bundle before upload. Bring the local sora clone to sora main, confirm it equals the remote, fetch this repo, then
compare a dry-run that reads the directory with one that reads the bundle:

```bash
git -C ~/repos/sora pull --ff-only origin main
git -C ~/repos/sora rev-parse HEAD
git ls-remote https://github.com/agg-ayush/sora.git refs/heads/main
git fetch origin
python3.11 scripts/public-mirror/publish.py verify-rules --source origin/main --sora-git ~/repos/sora \
  --rules-dir ~/hermes-archive/sora-public-rules --bundle "$KDIR/rules.b64" --expect-deny <n>
```

`verify-rules` exits 0 only when both runs reach the summary, print byte-identical output, report `<n>` deny patterns and
are green; it never passes a run that stopped at the guard, and it does not depend on whether sora is at the accepted base or
at a generated commit. Pass `--allow-gate-red` only when the rotation deliberately adds a rule that must stop publishing, and say
so in the rotation's note. While sora holds a foreign commit or an unknown source, a rules rotation cannot pass: merge the
recovery PR (port the change here, commit the sora head as the accepted base) first. A key rotation is not blocked.

`<n>` is `--expect-deny` taken from the deny-count record, the latest `public-mirror deny patterns: <n>` comment on the task card.
Cross-check it against the `mirror` runs that started after the `PUBLIC_MIRROR_RULES` upload time, which
`gh secret list --env public-mirror -R agg-ayush/hermes-setup --json name,updatedAt` gives; list candidates with
`gh run list -R agg-ayush/hermes-setup --workflow public-mirror.yml --json databaseId,startedAt,attempt`. From the newest run
back, read `gh run view <id> --log`: the first log holding a `deny patterns:` line is the cross-check, and a different count means
stop and escalate on the card. A run whose logs are unavailable is skipped and its id noted, never read as 0. When no run
qualifies the record alone is used, and the note says `no run to cross-check` plus `(logs unavailable: <run ids>)` when any
run was skipped. A rotation that changes `deny.txt` passes the new count and records `<old> -> <new>`. Add one deny-count comment
per rotation.

```bash
gh secret set PUBLIC_MIRROR_RULES --env public-mirror -R agg-ayush/hermes-setup < "$KDIR/rules.b64"
rm -rf "$KDIR"
```

Finish every rotation with the repository-level listing, which must show neither name:

```bash
gh secret list -R agg-ayush/hermes-setup
```

If either name shows, `gh secret delete <name> -R agg-ayush/hermes-setup` removes that copy.
