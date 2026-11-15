# Hermes Tier Setup

Custom Hermes Agent tier orchestration: plugin, skills, scripts, reference docs,
and config templates for the multi-tier autonomous coding pipeline.

## Structure

```
plugin/     claude-orchestrate plugin (pure tmux session manager)
plugins/    pr-review-toolkit patches (state-transition-reviewer specialist)
skills/     tier1-suborchestration + tier2-orchestration skills
scripts/    orphan-reaper.py (self-healing watchdog) + hermes-hygiene.py (weekly storage/health) + error-journal.py (failure capture) + watch_ci_main.py (CI watcher) + deny-guard.sh (T3 hook) + subagent-ledger-hook.py (subagent_stop hook → delegation ledger) + aws-token-refresh-hook.sh (post_tool_call hook → auto saml2aws refresh)
docs/       hermes-tiers-reference.md (canonical architecture) + audit.md
config/     config.yaml.template (current routing, regenerated from the live Mac config), env.template, zshrc-snippet.sh, watchdog launchd/systemd units (NO secrets)
patches/    local Hermes source patches applied by setup-hermes.sh
hosts/      per-host profiles (mac, sora, wsl): host-only scripts, systemd/launchd units, cron-jobs.json, watchdog.json, plugins.txt, config-overrides.yaml
```

## Install / Sync (Mac or Ubuntu EC2 `sora`)

Run the idempotent setup script (`devbox/setup-hermes.sh`) — it installs sidelined tools (`ruff`, `oxlint`, `smem`), wires the `claude-orchestrate` and `synapse-mem` plugins, syncs all tier skills, scripts, and agent-hooks (`subagent-ledger.py`, `aws-token-refresh.sh`, `t3-stop-gate.py`), symlinks `~/.hermes/claude-seatbelt-config` (`CLAUDE.md`, `skills/`, `plugins/`) to `~/.claude` with all plugins enabled, patches `pr-review-toolkit`, and sets global gitignore (`.serena/`, `.ui-flow/`):

```bash
git clone https://github.com/agg-ayush/sora.git ~/hermes-setup
bash ~/hermes-setup/devbox/setup-hermes.sh
```

What `devbox/setup-hermes.sh` sets up:
1. **Sidelined CLI binaries:** `ruff` (`uv tool install ruff`), `oxlint` (`npm install -g oxlint`), and `smem` (`~/repos/synapse-mem/integrations/install/install-smem.sh` if cloned).
2. **Hermes plugins & memory:** Symlinks `~/hermes-setup/plugin` → `~/.hermes/plugins/claude-orchestrate` and activates `synapse-mem` (`memory.provider: synapse-mem`).
3. **Hermes skills:** Symlinks `tier1-suborchestration`, `tier2-orchestration`, and the Claude Code `ui-flow` skill; copies `skills/devops/aws-devfactory-operations`.
4. **Scripts & hooks:** Copies repo scripts into `~/.hermes/scripts/` (matching host variant `aws-creds-refresh.sh` on Mac vs `aws-creds-refresh-linux.sh` on Linux so `watchdog.py` sees zero script drift) and hooks into `~/.hermes/agent-hooks/`.
5. **Claude Code seatbelt sync:** Symlinks `~/.hermes/claude-seatbelt-config/{CLAUDE.md,skills,plugins}` → `~/.claude/`, copies the `state-transition-reviewer` specialist into `pr-review-toolkit`, and enables all installed plugins in seatbelt's `settings.json`.
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

## Local upstream mods

We carry a small number of local patches to the live `~/.hermes/hermes-agent`
clone that are NOT pushed upstream (Seatbelt Claude Teams OAuth route identity,
session-bubble fix). They live in `patches/*.patch` and `devbox/setup-hermes.sh`
applies them idempotently. See `docs/local-upstream-mods.md` — re-run setup
after every `hermes update`.
