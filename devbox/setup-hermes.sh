#!/usr/bin/env bash
# One-time hermes wiring — run after `gh auth login` on the devbox.
# Clones hermes-setup and wires plugin/skills/scripts per its README.
set -euo pipefail

log() { echo "[setup-hermes] $*"; }

if [ ! -d "$HOME/hermes-tier-setup" ]; then
  log "cloning hermes-setup"
  gh repo clone agg-ayush/hermes-setup "$HOME/hermes-tier-setup"
fi

mkdir -p "$HOME/.hermes/plugins" "$HOME/.hermes/skills/autonomous-ai-agents" "$HOME/.hermes/scripts" "$HOME/.hermes/agent-hooks"

ln -sfn "$HOME/hermes-tier-setup/plugin" "$HOME/.hermes/plugins/claude-orchestrate"
ln -sfn "$HOME/hermes-tier-setup/skills/tier1-suborchestration" "$HOME/.hermes/skills/autonomous-ai-agents/tier1-suborchestration"
ln -sfn "$HOME/hermes-tier-setup/skills/tier2-orchestration" "$HOME/.hermes/skills/autonomous-ai-agents/tier2-orchestration"
ln -sfn "$HOME/hermes-tier-setup/scripts/orphan-reaper.py" "$HOME/.hermes/scripts/orphan-reaper.py"

# Hermes hooks live in ~/.hermes/agent-hooks/ (not ~/.hermes/scripts/) — symlink repo hooks there
ln -sfn "$HOME/hermes-tier-setup/scripts/subagent-ledger-hook.py" "$HOME/.hermes/agent-hooks/subagent-ledger.py"
ln -sfn "$HOME/hermes-tier-setup/scripts/aws-token-refresh-hook.sh" "$HOME/.hermes/agent-hooks/aws-token-refresh.sh"

# Config templates — copy only if absent (never clobber filled-in values)
if [ ! -f "$HOME/.hermes/config.yaml" ]; then
  cp "$HOME/hermes-tier-setup/config/config.yaml.template" "$HOME/.hermes/config.yaml"
  log "copied config.yaml template"
fi
if [ ! -f "$HOME/.hermes/.env" ]; then
  cp "$HOME/hermes-tier-setup/config/env.template" "$HOME/.hermes/.env"
  log "copied .env template"
fi

log "done. Next: fill in ~/.hermes/.env (TFY_API_KEY, TRUEFOUNDRY_API_KEY, TELEGRAM_BOT_TOKEN)"
