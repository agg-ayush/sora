#!/usr/bin/env bash
# Platform detection shared by setup-hermes.sh, host-profile.sh and bootstrap-wsl.sh. Source it.
# HERMES_PROC_OSRELEASE / HERMES_PROC_VERSION replace the /proc paths and HERMES_WSL_MNT the /mnt
# automount root, for tests.

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

# True for a path on a Windows drive (/mnt/c/...); WSL's own /mnt/wsl/... is not one.
hermes_on_windows_drive() {
  case "$1" in
    "${HERMES_WSL_MNT:-/mnt}"/[A-Za-z]|"${HERMES_WSL_MNT:-/mnt}"/[A-Za-z]/*) return 0 ;;
  esac
  return 1
}

hermes_gateway_installed() {
  [ -e "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" ] \
    || [ -e "$HOME/.config/systemd/user/hermes-gateway.service" ] \
    || [ -e /etc/systemd/system/hermes-gateway.service ]
}

# The watchdog alerts when the gateway is down, so the wsl profile schedules it only alongside a gateway.
hermes_wants_watchdog() {
  [ "$(hermes_host_profile)" != wsl ] || [ "${HERMES_INSTALL_GATEWAY:-false}" = true ] || hermes_gateway_installed
}

HERMES_WSL_BROWSER_MARK="# hermes-setup: WSL login browser"

# WSL checks run once per install: $1 = repo dir, $2 = "persist" to write the BROWSER default to shell rc files.
# Exports HERMES_WSL_PREFLIGHT_DONE=true so a nested setup-hermes.sh does not repeat them.
hermes_wsl_preflight() {
  local repo_dir="$1" persist="${2:-}" rc
  if hermes_on_windows_drive "$repo_dir"; then
    echo "[wsl] WARNING: the repo is on the Windows filesystem ($repo_dir). That is slow and breaks file"
    echo "[wsl]   permissions; clone it into your Linux home instead: git clone <repo-url> ~/hermes-setup"
  fi
  if ! hermes_has_user_systemd; then
    echo "[wsl] systemd is not running in this distro, so systemd user units are skipped and a gateway"
    echo "[wsl]   stops when its WSL session closes. To enable it, add these lines to /etc/wsl.conf:"
    echo "[wsl]     [boot]"
    echo "[wsl]     systemd=true"
    echo "[wsl]   then run 'wsl --shutdown' from Windows, reopen the distro and re-run devbox/setup-hermes.sh"
    echo "[wsl]   (prefix it with HERMES_INSTALL_GATEWAY=true to install the gateway as a systemd service)."
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
        # shellcheck disable=SC2016
        if { printf '\n%s\nif [ -z "${BROWSER:-}" ] && command -v wslview >/dev/null 2>&1; then export BROWSER=wslview; fi\n' \
               "$HERMES_WSL_BROWSER_MARK" >> "$rc"; } 2>/dev/null; then
          echo "[wsl] added the wslview BROWSER default to $rc"
        else
          echo "[wsl] WARNING: could not add the wslview BROWSER default to $rc; add it yourself: export BROWSER=wslview"
        fi
      done
    fi
  else
    echo "[wsl] note: wslview not found; install wslu (sudo apt-get install wslu) so login flows open the Windows browser"
  fi
  export HERMES_WSL_PREFLIGHT_DONE=true
}
