#!/usr/bin/env bash
# Devbox bootstrap: hermes + claude code. Idempotent — safe on rebuilds.
# Repo clone + symlinks live in ~/setup-hermes.sh (needs gh auth, done once
# after first login).
set -euo pipefail

log() { echo "[post-create] $*"; }

# Node feature installs under /usr/local/share/nvm; non-login hooks don't get
# it on PATH. Source nvm explicitly.
export NVM_DIR=/usr/local/share/nvm
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Claude Code CLI — user-global (nvm dir is user-writable, no sudo)
if ! command -v claude >/dev/null 2>&1; then
  log "installing claude code"
  npm install -g @anthropic-ai/claude-code
fi

# Hermes Agent — official installer
if ! command -v hermes >/dev/null 2>&1; then
  log "installing hermes agent"
  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash -s -- --non-interactive
fi
export PATH="$HOME/.local/bin:$PATH"
grep -q '.local/bin' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

# ripgrep — hermes file search uses it when present
if ! command -v rg >/dev/null 2>&1; then
  log "installing ripgrep"
  sudo apt-get install -y -qq ripgrep >/dev/null
fi

# First-login setup helper (repo clone + symlinks, needs gh auth)
cp "$(dirname "$0")/setup-hermes.sh" "$HOME/setup-hermes.sh"
chmod +x "$HOME/setup-hermes.sh"

log "done — run ~/setup-hermes.sh after 'gh auth login' to finish wiring"
