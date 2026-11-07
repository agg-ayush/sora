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
hosts/      per-host profiles (mac, sora): host-only scripts, systemd/launchd units, cron-jobs.json, watchdog.json, plugins.txt, config-overrides.yaml
```

## Install / Sync (Mac or Ubuntu EC2 `sora`)

Run the idempotent setup script (`devbox/setup-hermes.sh`) — it installs sidelined tools (`ruff`, `oxlint`, `smem`), wires the `claude-orchestrate` and `synapse-mem` plugins, syncs all tier skills, scripts, and agent-hooks (`subagent-ledger.py`, `aws-token-refresh.sh`, `t3-stop-gate.py`), symlinks `~/.hermes/claude-seatbelt-config` (`CLAUDE.md`, `skills/`, `plugins/`) to `~/.claude` with all plugins enabled, patches `pr-review-toolkit`, and sets global gitignore (`.serena/`, `.ui-flow/`):

```bash
git clone git@github.com:agg-ayush/hermes-setup.git ~/hermes-setup
bash ~/hermes-setup/devbox/setup-hermes.sh
```

What `devbox/setup-hermes.sh` sets up:
1. **Sidelined CLI binaries:** `ruff` (`uv tool install ruff`), `oxlint` (`npm install -g oxlint`), and `smem` (`~/repos/synapse-mem/integrations/install/install-smem.sh` if cloned).
2. **Hermes plugins & memory:** Symlinks `~/hermes-setup/plugin` → `~/.hermes/plugins/claude-orchestrate` and activates `synapse-mem` (`memory.provider: synapse-mem`).
3. **Hermes skills:** Symlinks `tier1-suborchestration`, `tier2-orchestration`, and the Claude Code `ui-flow` skill; copies `skills/devops/aws-devfactory-operations`.
4. **Scripts & hooks:** Copies repo scripts into `~/.hermes/scripts/` (matching host variant `aws-creds-refresh.sh` on Mac vs `aws-creds-refresh-linux.sh` on Linux so `watchdog.py` sees zero script drift) and hooks into `~/.hermes/agent-hooks/`.
5. **Claude Code seatbelt sync:** Symlinks `~/.hermes/claude-seatbelt-config/{CLAUDE.md,skills,plugins}` → `~/.claude/`, copies the `state-transition-reviewer` specialist into `pr-review-toolkit`, and enables all installed plugins in seatbelt's `settings.json`.
6. **Global gitignore:** Adds `.serena/`, `.ui-flow/`, and `**/.claude/settings.local.json`.

## Host profiles (`hosts/<mac|sora>/`)

Everything that exists on only one machine lives in a profile; `setup-hermes.sh` (step 9, `devbox/host-profile.sh`)
installs it **only when absent** — it never overwrites, restarts, enables or disables anything that exists.

| Item | Where | Installed when |
|---|---|---|
| host-only scripts | `scripts/` -> `~/.hermes/scripts/` (real copies) | file missing |
| helper binaries | `bin/` -> `~/.local/bin/` | file missing |
| systemd / launchd units | `systemd/`, `launchd/` (`reference/` = not installed) | unit file missing; only newly installed units are enabled/started. A leading `# requires: <path>` line gates a unit on that path. |
| cron jobs | `cron-jobs.json` | no job with that name (recorded enabled/paused state kept) |
| plugins | `plugins.txt` (`name [identifier]`) | missing from `hermes plugins list` |
| `watchdog.json` | profile root | missing |
| config keys | `config-overrides.yaml` | only when `config.yaml` was created from the template in the same run |
| gateway service | not copied; `hermes gateway install --if-missing` | no gateway service installed (never on a Mac that has a Telegram token) |

Profile = `mac` on Darwin, `sora` on Linux; override with `HERMES_HOST_PROFILE=<name>`; skip with `HERMES_SKIP_HOST_PROFILE=true`.
No chat ids or secrets are stored: scripts read `TELEGRAM_HOME_CHANNEL` / `TI_CONCERN_TELEGRAM_CHAT` / `TI_HIRING_TRACKER_DOC_ID`
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
