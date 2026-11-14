#!/usr/bin/env bash
# Installs Sora inside a WSL2 Ubuntu distro: apt prerequisites, uv, Node LTS, Hermes Agent and
# Claude Code when missing, then runs devbox/setup-hermes.sh. Idempotent; safe to re-run.
#   --dry-run   report what would be installed and the host profile; change nothing
set -euo pipefail

log() { echo "[bootstrap-wsl] $*"; }
die() { echo "[bootstrap-wsl] ERROR: $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=devbox/platform.sh
. "$REPO_DIR/devbox/platform.sh"

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

APT_PACKAGES=(git curl ca-certificates tmux python3 python3-venv jq)
NODE_MIN_MAJOR=18
NVM_VERSION=v0.40.3
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export PATH="$HOME/.local/bin:$PATH"

hermes_is_wsl || die "not running inside WSL; on macOS or plain Linux run devbox/setup-hermes.sh"
[ "$(id -u)" -ne 0 ] || die "run as your normal WSL user, not root; sudo is used only for apt-get"

# WSL interop appends Windows PATH entries; a Windows binary under /mnt/<drive>/ does not count.
have() {
  local p
  p="$(command -v "$1" 2>/dev/null)" || return 1
  case "$p" in
    /mnt/*) log "ignoring Windows $1 at $p"; return 1 ;;
  esac
}

load_nvm() {
  [ -s "$NVM_DIR/nvm.sh" ] || return 0
  set +eu
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  set -eu
}

node_ok() {
  have node || return 1
  local major
  major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [ "$major" -ge "$NODE_MIN_MAJOR" ] 2>/dev/null
}

install_uv() { curl -LsSf https://astral.sh/uv/install.sh | sh; }

install_node() {
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | bash
  fi
  load_nvm
  set +eu
  nvm install --lts && nvm alias default 'lts/*'
  local rc=$?
  set -eu
  return "$rc"
}

# Non-interactive: the installer's own setup and gateway stages are left to the user and host-profile.sh.
install_hermes() { curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --non-interactive; }

install_claude() { curl -fsSL https://claude.ai/install.sh | bash; }

# ensure <label> <install function> <check command...>
ensure() {
  local what="$1" fn="$2"
  shift 2
  if "$@"; then
    log "$what present"
    return 0
  fi
  if [ "$DRY_RUN" = true ]; then
    log "(dry run) would install $what"
    return 0
  fi
  log "installing $what"
  "$fn"
  hash -r
  "$@" || die "$what install finished but it is still not usable on PATH; open a new shell and re-run"
}

missing_packages() {
  local pkg status
  for pkg in "${APT_PACKAGES[@]}"; do
    status="$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)"
    [ "$status" = "install ok installed" ] || echo "$pkg"
  done
}

if [ "${HERMES_WSL_PREFLIGHT_DONE:-false}" != true ]; then
  if [ "$DRY_RUN" = true ]; then
    hermes_wsl_preflight "$REPO_DIR"
  else
    hermes_wsl_preflight "$REPO_DIR" persist
  fi
fi

missing=()
while IFS= read -r pkg; do
  [ -n "$pkg" ] && missing+=("$pkg")
done < <(missing_packages)
if [ "${#missing[@]}" -eq 0 ]; then
  log "apt packages present: ${APT_PACKAGES[*]}"
else
  log "will install with sudo apt-get: ${missing[*]}"
  if [ "$DRY_RUN" = true ]; then
    log "(dry run) apt-get not run"
  else
    command -v apt-get >/dev/null 2>&1 || die "apt-get not found; this bootstrap supports Ubuntu/Debian WSL distros"
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}"
  fi
fi

load_nvm
ensure "uv" install_uv have uv
ensure "Node.js >= $NODE_MIN_MAJOR" install_node node_ok
ensure "Hermes Agent" install_hermes have hermes
ensure "Claude Code" install_claude have claude

log "host profile: $(hermes_host_profile)"
if [ "$DRY_RUN" = true ]; then
  log "(dry run) would run devbox/setup-hermes.sh"
  exit 0
fi

bash "$REPO_DIR/devbox/setup-hermes.sh"

log "done. Next steps:"
log "  1. open a new terminal so PATH changes apply"
log "  2. run 'claude' once to sign in to Claude Code"
log "  3. run 'hermes setup' to pick a model provider; put keys in ~/.hermes/.env"
log "  4. optional, to run Hermes cron jobs: HERMES_INSTALL_GATEWAY=true bash $REPO_DIR/devbox/setup-hermes.sh"
