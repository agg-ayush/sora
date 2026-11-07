#!/usr/bin/env bash
# Host-profile step of setup-hermes.sh: installs the host-only state captured under hosts/<profile>/.
# INSTALL-IF-ABSENT ONLY. Never overwrites, restarts, enables or disables anything that already exists.
#
# Inputs (exported by setup-hermes.sh, or set by hand for a dry run on a scratch HOME):
#   REPO_DIR, HERMES_HOME, FRESH_CONFIG=true (config.yaml was created from the template in this run)
#   HERMES_HOST_PROFILE   profile dir under hosts/ (default: mac on Darwin, sora on Linux)
#   HERMES_SKIP_HOST_PROFILE=true skips everything
set -euo pipefail

log() { echo "[host-profile] $*"; }

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
FRESH_CONFIG="${FRESH_CONFIG:-false}"
export PATH="$HOME/.local/bin:$PATH"

if [ "${HERMES_SKIP_HOST_PROFILE:-false}" = true ]; then
  log "skipped (HERMES_SKIP_HOST_PROFILE=true)"
  exit 0
fi
if [ -n "${HERMES_HOST_PROFILE:-}" ]; then
  HOST_PROFILE="$HERMES_HOST_PROFILE"
elif [ "$(uname -s)" = "Darwin" ]; then
  HOST_PROFILE=mac
else
  HOST_PROFILE=sora
fi
PROFILE_DIR="$REPO_DIR/hosts/$HOST_PROFILE"
if [ ! -d "$PROFILE_DIR" ]; then
  log "no hosts/$HOST_PROFILE profile in the repo; skipping host step"
  exit 0
fi
log "host profile: $HOST_PROFILE"

HELPER="$REPO_DIR/devbox/host_profile.py"
PY=python3
[ -x "${HERMES_AGENT_DIR:-$HERMES_HOME/hermes-agent}/venv/bin/python" ] && PY="${HERMES_AGENT_DIR:-$HERMES_HOME/hermes-agent}/venv/bin/python"
MAC_FLAG=()
[ "$HOST_PROFILE" = mac ] && MAC_FLAG=(--mac)

# 1. Host-only scripts -> ~/.hermes/scripts (real copies: Hermes refuses symlinked cron scripts).
mkdir -p "$HERMES_HOME/scripts"
copied=0 present=0
if [ -d "$PROFILE_DIR/scripts" ]; then
  for src in "$PROFILE_DIR"/scripts/*; do
    [ -f "$src" ] || continue
    dest="$HERMES_HOME/scripts/$(basename "$src")"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      present=$((present + 1))
    else
      cp "$src" "$dest"
      case "$dest" in *.sh) chmod +x "$dest" ;; esac
      log "installed script $(basename "$src")"
      copied=$((copied + 1))
    fi
  done
fi
log "scripts: $copied installed, $present already present"

# 1b. Host-only helper binaries -> ~/.local/bin
copied=0 present=0
if [ -d "$PROFILE_DIR/bin" ]; then
  mkdir -p "$HOME/.local/bin"
  for src in "$PROFILE_DIR"/bin/*; do
    [ -f "$src" ] || continue
    dest="$HOME/.local/bin/$(basename "$src")"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      present=$((present + 1))
    else
      cp "$src" "$dest"
      chmod +x "$dest"
      log "installed bin $(basename "$src")"
      copied=$((copied + 1))
    fi
  done
  log "bin: $copied installed, $present already present"
fi

# 2. watchdog.json (host-specific alert channel / expected jobs)
if [ -f "$PROFILE_DIR/watchdog.json" ]; then
  if [ -e "$HERMES_HOME/scripts/watchdog.json" ]; then
    log "watchdog.json already present"
  else
    cp "$PROFILE_DIR/watchdog.json" "$HERMES_HOME/scripts/watchdog.json"
    log "installed watchdog.json"
  fi
fi

# 3. Plugins: install + enable only names missing from `hermes plugins list`.
if [ -f "$PROFILE_DIR/plugins.txt" ] && command -v hermes >/dev/null 2>&1; then
  plugin_rows="$(hermes plugins list --plain 2>/dev/null || true)"
  while read -r pname pident _; do
    case "$pname" in ''|\#*) continue ;; esac
    if printf '%s\n' "$plugin_rows" | grep -Eq "[[:space:]]${pname}$"; then
      log "plugin $pname already present"
    else
      log "installing plugin $pname"
      hermes plugins install "${pident:-$pname}" --yes-deps --enable \
        || log "WARNING: plugin $pname install failed"
    fi
  done < "$PROFILE_DIR/plugins.txt"
fi

# 4. Cron jobs: created only when no job with that name exists (recorded enabled/paused state kept).
if [ -f "$PROFILE_DIR/cron-jobs.json" ] && command -v hermes >/dev/null 2>&1; then
  "$PY" "$HELPER" cron "$PROFILE_DIR/cron-jobs.json" ${MAC_FLAG[@]+"${MAC_FLAG[@]}"} \
    || log "WARNING: cron job step errored; continuing"
fi

# 5. Service units. Install only a missing unit file, then start ONLY what was just installed.
unit_requirement_ok() { # $1 = unit source file; honors a leading "# requires: <path>" line
  local req
  req="$(sed -n '1s/^# requires: //p' "$1")"
  [ -z "$req" ] && return 0
  req="${req//%h/$HOME}"
  [ -e "$req" ]
}

if [ -d "$PROFILE_DIR/systemd" ]; then
  if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    UNIT_DIR="$HOME/.config/systemd/user"
    new_units=()
    present=0
    for src in "$PROFILE_DIR"/systemd/*.service "$PROFILE_DIR"/systemd/*.timer; do
      [ -f "$src" ] || continue
      u="$(basename "$src")"
      if [ -e "$UNIT_DIR/$u" ]; then
        present=$((present + 1))
      elif unit_requirement_ok "$src"; then
        mkdir -p "$UNIT_DIR"
        cp "$src" "$UNIT_DIR/$u"
        new_units+=("$u")
      else
        log "skipping unit $u: prerequisite from its '# requires:' line is missing"
      fi
    done
    if [ "${#new_units[@]}" -gt 0 ]; then
      systemctl --user daemon-reload
      for u in "${new_units[@]}"; do
        systemctl --user enable --now "$u" \
          && log "installed + started $u" \
          || log "WARNING: could not enable $u"
      done
    fi
    log "systemd units: ${#new_units[@]} installed, $present already present"
  else
    log "systemd user instance unavailable; units under hosts/$HOST_PROFILE/systemd not installed"
  fi
fi

if [ -d "$PROFILE_DIR/launchd" ]; then
  if command -v launchctl >/dev/null 2>&1; then
    AGENT_DIR="$HOME/Library/LaunchAgents"
    new=0 present=0
    for src in "$PROFILE_DIR"/launchd/*.plist; do
      [ -f "$src" ] || continue
      p="$(basename "$src")"
      if [ -e "$AGENT_DIR/$p" ]; then
        present=$((present + 1))
      elif unit_requirement_ok "$src"; then
        mkdir -p "$AGENT_DIR"
        sed "s|__HOME__|$HOME|g" "$src" > "$AGENT_DIR/$p"
        launchctl bootstrap "gui/$(id -u)" "$AGENT_DIR/$p" 2>/dev/null \
          && log "installed + loaded $p" \
          || log "installed $p; load it with: launchctl bootstrap gui/$(id -u) $AGENT_DIR/$p"
        new=$((new + 1))
      fi
    done
    log "launchd agents: $new installed, $present already present"
  else
    log "launchctl unavailable; agents under hosts/$HOST_PROFILE/launchd not installed"
  fi
fi

# 6. Gateway service: never raw-copied. Use Hermes's own installer, and only when none exists.
#    The Mac never polls Telegram (standing rule), so it is skipped when a bot token is present.
gateway_installed=false
if [ -e "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist" ] \
   || [ -e "$HOME/.config/systemd/user/hermes-gateway.service" ] \
   || [ -e /etc/systemd/system/hermes-gateway.service ]; then
  gateway_installed=true
fi
if [ "$gateway_installed" = true ]; then
  log "gateway service already installed"
elif ! command -v hermes >/dev/null 2>&1; then
  log "hermes CLI not on PATH; gateway service not installed"
elif [ "$HOST_PROFILE" = mac ] && grep -Eq '^TELEGRAM_BOT_TOKEN=.+' "$HERMES_HOME/.env" 2>/dev/null; then
  log "WARNING: Mac has TELEGRAM_BOT_TOKEN set; not installing the gateway (Mac must not poll Telegram)"
else
  log "no gateway service found; running 'hermes gateway install --if-missing'"
  hermes gateway install --if-missing || log "WARNING: hermes gateway install failed"
fi

# 7. Per-host config overrides: ONLY onto a config.yaml created from the template in this same run.
if [ -f "$PROFILE_DIR/config-overrides.yaml" ]; then
  if [ "$FRESH_CONFIG" = true ] && [ -f "$HERMES_HOME/config.yaml" ]; then
    "$PY" "$HELPER" overrides "$HERMES_HOME/config.yaml" "$PROFILE_DIR/config-overrides.yaml" ${MAC_FLAG[@]+"${MAC_FLAG[@]}"} \
      || log "WARNING: config overrides not applied"
  else
    log "config overrides not applied (config.yaml was not freshly created; live config left untouched)"
  fi
fi

log "host step done"
