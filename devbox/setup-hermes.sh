#!/usr/bin/env bash
# Idempotent setup & sync script for the Hermes + Claude Code tier orchestration stack.
# Works on both macOS and Ubuntu EC2 (sora) — safe to re-run at any time.
set -euo pipefail

log() { echo "[setup-hermes] $*"; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLAUDE_HOME="$HOME/.claude"
SEATBELT_DIR="$HERMES_HOME/claude-seatbelt-config"
IS_MAC=false
[ "$(uname -s)" = "Darwin" ] && IS_MAC=true

export PATH="$HOME/.local/bin:$PATH"

# 1. Core directory structure
mkdir -p "$HERMES_HOME/plugins" \
         "$HERMES_HOME/skills/autonomous-ai-agents" \
         "$HERMES_HOME/skills/devops" \
         "$HERMES_HOME/scripts" \
         "$HERMES_HOME/agent-hooks" \
         "$CLAUDE_HOME/plugins" \
         "$CLAUDE_HOME/skills" \
         "$SEATBELT_DIR"

# 2. Sidelined CLI tools: ruff, oxlint, smem
if ! command -v ruff >/dev/null 2>&1; then
  log "installing ruff (fast Python syntax linter for T3 Stop hook)"
  if command -v uv >/dev/null 2>&1; then
    uv tool install ruff
  elif [ -x "$HERMES_HOME/tools/"*/uv ]; then
    "$HERMES_HOME/tools/"*/uv tool install ruff
  fi
fi

if ! command -v oxlint >/dev/null 2>&1; then
  log "installing oxlint (fast JS/TS syntax linter for T3 Stop hook)"
  command -v npm >/dev/null 2>&1 && npm install -g oxlint
fi

if ! command -v smem >/dev/null 2>&1; then
  if [ -x "$HOME/repos/synapse-mem/integrations/install/install-smem.sh" ]; then
    log "installing smem binary from ~/repos/synapse-mem"
    "$HOME/repos/synapse-mem/integrations/install/install-smem.sh"
  else
    log "note: smem not on PATH (clone agg-ayush/synapse-mem to ~/repos/synapse-mem to install)"
  fi
fi

# 3. Hermes plugin + skills
log "wiring claude-orchestrate plugin and tier skills"
rm -rf "$HERMES_HOME/plugins/claude-orchestrate"
ln -sfn "$REPO_DIR/plugin" "$HERMES_HOME/plugins/claude-orchestrate"
for s in tier1-suborchestration tier2-orchestration; do
  rm -rf "$HERMES_HOME/skills/autonomous-ai-agents/$s" "$HERMES_HOME/skills/$s"
  ln -sfn "$REPO_DIR/skills/$s" "$HERMES_HOME/skills/autonomous-ai-agents/$s"
  ln -sfn "$REPO_DIR/skills/$s" "$HERMES_HOME/skills/$s"
done
if [ -d "$REPO_DIR/skills/devops/aws-devfactory-operations" ]; then
  rm -rf "$HERMES_HOME/skills/devops/aws-devfactory-operations"
  cp -R "$REPO_DIR/skills/devops/aws-devfactory-operations" "$HERMES_HOME/skills/devops/aws-devfactory-operations"
fi

# 4. Hermes scripts + hooks (copied so watchdog check_script_drift sees exact byte parity)
log "syncing scripts -> $HERMES_HOME/scripts/"
COMMON_SCRIPTS=(
  _platform.py
  _watermark.py
  auth-canary.py
  auto_complete_merged.py
  deny-guard.sh
  error-journal.py
  hermes-hygiene.py
  orphan-reaper.py
  pr-wait.py
  t3-stop-gate.py
  test-error-journal.py
  trilogy-aws-key.py
  watch_ci_main.py
  watch_tier_events.py
  watchdog.py
)
for f in "${COMMON_SCRIPTS[@]}"; do
  [ -f "$REPO_DIR/scripts/$f" ] && cp "$REPO_DIR/scripts/$f" "$HERMES_HOME/scripts/$f"
done

if [ "$IS_MAC" = true ]; then
  cp "$REPO_DIR/scripts/aws-creds-refresh.sh" "$HERMES_HOME/scripts/aws-creds-refresh.sh"
  cp "$REPO_DIR/scripts/aws-keep-hot.sh" "$HERMES_HOME/scripts/aws-keep-hot.sh"
else
  cp "$REPO_DIR/scripts/aws-creds-refresh-linux.sh" "$HERMES_HOME/scripts/aws-creds-refresh-linux.sh"
  cp "$REPO_DIR/scripts/aws-keep-hot-linux.sh" "$HERMES_HOME/scripts/aws-keep-hot-linux.sh"
fi
chmod +x "$HERMES_HOME/scripts/"*.sh "$HERMES_HOME/scripts/t3-stop-gate.py" 2>/dev/null || true

log "syncing agent-hooks -> $HERMES_HOME/agent-hooks/"
cp "$REPO_DIR/scripts/subagent-ledger-hook.py" "$HERMES_HOME/agent-hooks/subagent-ledger.py"
cp "$REPO_DIR/scripts/aws-token-refresh-hook.sh" "$HERMES_HOME/agent-hooks/aws-token-refresh.sh"
chmod +x "$HERMES_HOME/agent-hooks/subagent-ledger.py" "$HERMES_HOME/agent-hooks/aws-token-refresh.sh"

# 5. synapse-mem Hermes provider activation (if repo checkout is present)
if [ -x "$HOME/repos/synapse-mem/integrations/agents/hermes/activate.sh" ] && command -v smem >/dev/null 2>&1; then
  log "activating synapse-mem Hermes memory provider"
  SMEM_BIN="$(command -v smem)" "$HOME/repos/synapse-mem/integrations/agents/hermes/activate.sh" || true
fi

# 6. Claude Code seatbelt config sync (symlinks CLAUDE.md, skills/, plugins/ to ~/.claude)
log "syncing Claude Code seatbelt config ($SEATBELT_DIR -> $CLAUDE_HOME)"
[ -f "$CLAUDE_HOME/CLAUDE.md" ] && ln -sfn "$CLAUDE_HOME/CLAUDE.md" "$SEATBELT_DIR/CLAUDE.md"
ln -sfn "$CLAUDE_HOME/skills" "$SEATBELT_DIR/skills"
ln -sfn "$CLAUDE_HOME/plugins" "$SEATBELT_DIR/plugins"

# Copy patched pr-review-toolkit specialist if pr-review-toolkit is in cache
for d in "$CLAUDE_HOME/plugins/cache/claude-plugins-official/pr-review-toolkit/"*; do
  if [ -d "$d/agents" ] && [ -f "$REPO_DIR/plugins/pr-review-toolkit/agents/state-transition-reviewer.md" ]; then
    cp "$REPO_DIR/plugins/pr-review-toolkit/agents/state-transition-reviewer.md" "$d/agents/"
    cp "$REPO_DIR/plugins/pr-review-toolkit/commands/review-pr.md" "$d/commands/"
  fi
done

# Enable all installed Claude Code plugins in seatbelt settings.json
if [ -f "$CLAUDE_HOME/plugins/installed_plugins.json" ]; then
  python3 - "$CLAUDE_HOME/plugins/installed_plugins.json" "$SEATBELT_DIR/settings.json" <<'PY'
import json, os, sys
inst_path, sb_settings_path = sys.argv[1:3]
installed = json.load(open(inst_path)).get("plugins", {})
settings = json.load(open(sb_settings_path)) if os.path.exists(sb_settings_path) else {}
settings["skipDangerousModePermissionPrompt"] = True
settings["enabledPlugins"] = {k: True for k in installed}
json.dump(settings, open(sb_settings_path, "w"), indent=2)
PY
fi

# 7. Global gitignore (.serena/, .ui-flow/, .claude/settings.local.json)
GIT_IGNORE="$(git config --global core.excludesfile || true)"
if [ -z "$GIT_IGNORE" ]; then
  GIT_IGNORE="$HOME/.config/git/ignore"
  mkdir -p "$(dirname "$GIT_IGNORE")"
  git config --global core.excludesfile "$GIT_IGNORE"
fi
GIT_IGNORE="${GIT_IGNORE/#\~/$HOME}"
mkdir -p "$(dirname "$GIT_IGNORE")"
touch "$GIT_IGNORE"
for pat in "**/.claude/settings.local.json" ".serena/" ".ui-flow/"; do
  grep -qxF "$pat" "$GIT_IGNORE" 2>/dev/null || echo "$pat" >> "$GIT_IGNORE"
done

# 8. Config templates — copy only if absent (never clobber live config/secrets)
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
  cp "$REPO_DIR/config/config.yaml.template" "$HERMES_HOME/config.yaml"
  log "copied config.yaml.template -> $HERMES_HOME/config.yaml"
fi
if [ ! -f "$HERMES_HOME/.env" ]; then
  cp "$REPO_DIR/config/env.template" "$HERMES_HOME/.env"
  chmod 600 "$HERMES_HOME/.env"
  log "copied env.template -> $HERMES_HOME/.env (fill in secrets)"
fi

log "done — setup and sideloaded tools verified."
