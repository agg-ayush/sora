#!/usr/bin/env bash
# Platform detection shared by setup-hermes.sh, host-profile.sh and bootstrap-wsl.sh. Source it.
# HERMES_PROC_OSRELEASE / HERMES_PROC_VERSION replace the /proc paths for tests.

hermes_is_wsl() {
  [ "$(uname -s)" = Linux ] || return 1
  [ -n "${WSL_DISTRO_NAME:-}" ] && return 0
  local f
  for f in "${HERMES_PROC_OSRELEASE:-/proc/sys/kernel/osrelease}" "${HERMES_PROC_VERSION:-/proc/version}"; do
    [ -r "$f" ] || continue
    if grep -qi microsoft "$f" || grep -q WSL "$f"; then
      return 0
    fi
  done
  return 1
}

# Profile dir under hosts/: HERMES_HOST_PROFILE wins, then mac (Darwin), wsl (WSL), sora (other Linux).
hermes_host_profile() {
  if [ -n "${HERMES_HOST_PROFILE:-}" ]; then
    echo "$HERMES_HOST_PROFILE"
  elif [ "$(uname -s)" = Darwin ]; then
    echo mac
  elif hermes_is_wsl; then
    echo wsl
  else
    echo sora
  fi
}

hermes_has_user_systemd() {
  command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}

HERMES_WSL_BROWSER_MARK="# hermes-setup: WSL login browser"

# WSL checks run once per install: $1 = repo dir, $2 = "persist" to write the BROWSER default to shell rc files.
# Exports HERMES_WSL_PREFLIGHT_DONE=true so a nested setup-hermes.sh does not repeat them.
hermes_wsl_preflight() {
  local repo_dir="$1" persist="${2:-}" rc
  case "$repo_dir/" in
    /mnt/[A-Za-z]/*)
      echo "[wsl] WARNING: the repo is on the Windows filesystem ($repo_dir). That is slow and breaks file"
      echo "[wsl]   permissions; clone it into your Linux home instead: git clone <repo-url> ~/hermes-setup"
      ;;
  esac
  if ! hermes_has_user_systemd; then
    echo "[wsl] systemd is not running in this distro, so systemd user units are skipped and a gateway"
    echo "[wsl]   stops when its WSL session closes. To enable it, add these lines to /etc/wsl.conf:"
    echo "[wsl]     [boot]"
    echo "[wsl]     systemd=true"
    echo "[wsl]   then run 'wsl --shutdown' from Windows, reopen the distro and re-run devbox/setup-hermes.sh."
  fi
  if command -v wslview >/dev/null 2>&1; then
    if [ -z "${BROWSER:-}" ]; then
      export BROWSER=wslview
      echo "[wsl] BROWSER=wslview for login flows"
    fi
    if [ "$persist" = persist ]; then
      for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [ -f "$rc" ] || [ "$rc" = "$HOME/.bashrc" ] || continue
        grep -qF "$HERMES_WSL_BROWSER_MARK" "$rc" 2>/dev/null && continue
        printf '\n%s\nif [ -z "${BROWSER:-}" ] && command -v wslview >/dev/null 2>&1; then export BROWSER=wslview; fi\n' \
          "$HERMES_WSL_BROWSER_MARK" >> "$rc"
        echo "[wsl] added the wslview BROWSER default to $rc"
      done
    fi
  else
    echo "[wsl] note: wslview not found; install wslu (sudo apt-get install wslu) so login flows open the Windows browser"
  fi
  export HERMES_WSL_PREFLIGHT_DONE=true
}
