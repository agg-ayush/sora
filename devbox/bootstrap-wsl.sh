#!/usr/bin/env bash
# Installs Sora inside a WSL2 Ubuntu distro: apt prerequisites, uv, Node LTS, Hermes Agent and
# Claude Code when missing, then runs devbox/setup-hermes.sh. Idempotent; safe to re-run.
#   --dry-run   report what would be installed and the host profile; change nothing. Exits 0 when
#               nothing is missing and 2 when a package or tool would be installed.
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
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) die "unknown argument: $arg" ;;
  esac
done

APT_PACKAGES=(git curl ca-certificates tmux python3 python3-venv jq wslu)
NODE_MIN_MAJOR=18
NVM_VERSION=v0.40.3
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
export PATH="$HOME/.local/bin:$PATH"

hermes_is_wsl || die "not running inside WSL; on macOS or plain Linux run devbox/setup-hermes.sh"
[ "$(id -u)" -ne 0 ] || die "run as your normal WSL user, not root; sudo is used only for apt-get"

RERUN="re-run: bash $(printf '%q' "$REPO_DIR/devbox/bootstrap-wsl.sh")"
CHANGES=false

# WSL interop appends Windows PATH entries; a Windows binary under /mnt/<drive>/ does not count.
have() {
  local p
  p="$(command -v "$1" 2>/dev/null)" || return 1
  if hermes_on_windows_drive "$p"; then
    log "ignoring Windows $1 at $p"
    return 1
  fi
}

load_nvm() {
  [ -s "$NVM_DIR/nvm.sh" ] || return 0
  local rc=0
  set +eu
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  rc=$?
  set -eu
  if ! command -v nvm >/dev/null 2>&1; then
    die "loading $NVM_DIR/nvm.sh failed (exit $rc) and defined no nvm command; repair or remove $NVM_DIR, then $RERUN"
  fi
  [ "$rc" -eq 0 ] || log "warning: $NVM_DIR/nvm.sh exited $rc while loading (often a default alias naming an uninstalled node)"
}

node_ok() {
  have node || return 1
  local major
  major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
  [ "$major" -ge "$NODE_MIN_MAJOR" ] 2>/dev/null
}

install_uv() { curl -LsSf https://astral.sh/uv/install.sh | sh; }

major_of() { local v="${1#v}"; echo "${v%%.*}"; }

# Keeps an nvm default that already meets the floor, else points it at the newest installed node that
# does, and installs LTS only when none does.
install_node() {
  if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/$NVM_VERSION/install.sh" | bash || return 1
  fi
  load_nvm
  local current best rc
  set +eu
  current="$(nvm version default 2>/dev/null)"
  best="$(nvm ls --no-colors --no-alias 2>/dev/null | grep -Eo 'v[0-9]+\.[0-9]+\.[0-9]+' | sort -V | tail -n 1)"
  if [ "$(major_of "$current")" -ge "$NODE_MIN_MAJOR" ] 2>/dev/null; then
    log "keeping the nvm default node $current"
    nvm use default >/dev/null
  elif [ "$(major_of "$best")" -ge "$NODE_MIN_MAJOR" ] 2>/dev/null; then
    log "pointing the nvm default at the installed node $best (was: ${current:-none})"
    nvm alias default "$best" && nvm use default >/dev/null
  else
    nvm install --lts && nvm alias default 'lts/*'
  fi
  rc=$?
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
  CHANGES=true
  if [ "$DRY_RUN" = true ]; then
    log "(dry run) would install $what"
    return 0
  fi
  log "installing $what"
  "$fn" || die "installing $what failed (see the output above); fix the cause, then $RERUN"
  hash -r
  "$@" || die "$what install finished but it is still not usable on PATH; open a new shell, then $RERUN"
}

missing_packages() {
  local pkg status
  for pkg in "${APT_PACKAGES[@]}"; do
    status="$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)"
    [ "$status" = "install ok installed" ] || echo "$pkg"
  done
}

missing=()
while IFS= read -r pkg; do
  [ -n "$pkg" ] && missing+=("$pkg")
done < <(missing_packages)
if [ "${#missing[@]}" -eq 0 ]; then
  log "apt packages present: ${APT_PACKAGES[*]}"
else
  CHANGES=true
  log "will install with sudo apt-get: ${missing[*]}"
  if [ "$DRY_RUN" = true ]; then
    log "(dry run) apt-get not run"
  else
    command -v apt-get >/dev/null 2>&1 || die "apt-get not found; this bootstrap supports Ubuntu/Debian WSL distros"
    sudo apt-get update || die "sudo apt-get update failed; fix apt or sudo, then $RERUN"
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}" \
      || die "apt-get install failed; fix apt or sudo, then $RERUN"
    hash -r
  fi
fi

# After apt, so a freshly installed wslview is found.
if [ "${HERMES_WSL_PREFLIGHT_DONE:-false}" != true ]; then
  if [ "$DRY_RUN" = true ]; then
    hermes_wsl_preflight "$REPO_DIR"
  else
    hermes_wsl_preflight "$REPO_DIR" persist
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
  [ "$CHANGES" = true ] && exit 2
  exit 0
fi

setup_rc=0
bash "$REPO_DIR/devbox/setup-hermes.sh" || setup_rc=$?
if [ "$setup_rc" -eq 3 ]; then
  die "the gateway requested with HERMES_INSTALL_GATEWAY=true was not installed; see the ERROR block above"
elif [ "$setup_rc" -ne 0 ]; then
  die "devbox/setup-hermes.sh failed (exit $setup_rc); fix the error above, then $RERUN"
fi

log "done. Next steps:"
log "  1. open a new terminal so PATH changes apply"
log "  2. run 'claude' once to sign in to Claude Code"
log "  3. run 'hermes setup' to pick a model provider; put keys in ~/.hermes/.env"
log "  4. optional, to run Hermes cron jobs: HERMES_INSTALL_GATEWAY=true bash $REPO_DIR/devbox/setup-hermes.sh"
