#!/usr/bin/env bash
# Idempotent setup & sync script for the Hermes + Claude Code tier orchestration stack.
# Works on macOS, Ubuntu EC2 (sora) and Ubuntu under WSL2 — safe to re-run at any time.
set -euo pipefail

log() { echo "[setup-hermes] $*"; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
CLAUDE_HOME="$HOME/.claude"
SEATBELT_DIR="$HERMES_HOME/claude-seatbelt-config"
IS_MAC=false
[ "$(uname -s)" = "Darwin" ] && IS_MAC=true
# shellcheck source=devbox/platform.sh
. "$REPO_DIR/devbox/platform.sh"

export PATH="$HOME/.local/bin:$PATH"

# Claude-only mode reconciles skills without touching Hermes skills, plugins,
# settings, scripts or any running service.
link_claude_skill() {
  local src="$1" dest="$2" name
  name="$(basename "$dest")"
  if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
    return 0
  fi
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    local backup
    backup="$(mktemp -d "$HERMES_HOME/cache/$name-$(date +%Y%m%d-%H%M%S)-XXXXXX")"
    mv "$dest" "$backup/$name"
    log "backed up Claude Code $name to $backup/$name"
  elif [ -L "$dest" ]; then
    rm "$dest"
  fi
  ln -s "$src" "$dest"
}

link_claude_skills() {
  local src name public_skills
  mkdir -p "$CLAUDE_HOME/skills" "$HERMES_HOME/cache" "$SEATBELT_DIR"
  for src in "$REPO_DIR"/skills/claude/*; do
    if [ ! -d "$src" ] || [ ! -f "$src/SKILL.md" ]; then
      continue
    fi
    name="$(basename "$src")"
    link_claude_skill "$src" "$CLAUDE_HOME/skills/$name"
  done
  public_skills="${PUBLIC_SKILLS:-$HOME/repos/public_skills}"
  if [ ! -f "$public_skills/brainlift/SKILL.md" ]; then
    git clone -q https://github.com/<stakeholder>/public_skills.git "$public_skills" || log "public_skills clone failed; Claude Code brainlift unavailable"
  fi
  if [ -f "$public_skills/brainlift/SKILL.md" ]; then
    link_claude_skill "$public_skills/brainlift" "$CLAUDE_HOME/skills/brainlift"
  else
    log "Claude Code brainlift source missing: $public_skills/brainlift"
  fi
  # Shared skills that Claude Code also loads (single source under skills/shared; Hermes links them below).
  for rel in creative/launch-video research/research; do
    name="$(basename "$rel")"
    src="$REPO_DIR/skills/shared/$rel"
    if [ -f "$src/SKILL.md" ]; then
      link_claude_skill "$src" "$CLAUDE_HOME/skills/$name"
    else
      log "Claude Code $name source missing: $src"
    fi
  done
  if [ ! -L "$SEATBELT_DIR/skills" ] || [ "$(readlink "$SEATBELT_DIR/skills")" != "$CLAUDE_HOME/skills" ]; then
    link_claude_skill "$CLAUDE_HOME/skills" "$SEATBELT_DIR/skills"
  fi
}

if [ "${CLAUDE_SKILLS_ONLY:-false}" = true ]; then
  link_claude_skills
  log "Claude Code skills linked (Claude-only mode)"
  exit 0
fi

# Shared local skills: link category-preserving repo copies on every host.
# Skills-only mode avoids unrelated Claude Code skill changes during reconciliation.
if [ -d "$REPO_DIR/skills/shared" ]; then
  mkdir -p "$HERMES_HOME/cache"
  while IFS= read -r skill_md; do
    src="$(dirname "$skill_md")"
    parent="$(dirname "$src")"
    nested=false
    while [ "$parent" != "$REPO_DIR/skills/shared" ]; do
      if [ -f "$parent/SKILL.md" ]; then
        nested=true
        break
      fi
      parent="$(dirname "$parent")"
    done
    if [ "$nested" = true ]; then
      continue
    fi
    rel="${src#"$REPO_DIR/skills/shared/"}"
    case "$rel" in _root/*) rel="${rel#_root/}" ;; esac
    dest="$HERMES_HOME/skills/$rel"
    mkdir -p "$(dirname "$dest")"
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$src" ]; then
      continue
    fi
    if [ -e "$dest" ] && [ ! -L "$dest" ]; then
      mv "$dest" "$HERMES_HOME/cache/$(basename "$dest")-$(date +%Y%m%d-%H%M%S)-$$"
    elif [ -L "$dest" ]; then
      rm "$dest"
    fi
    ln -s "$src" "$dest"
  done < <(find "$REPO_DIR/skills/shared" -name SKILL.md -type f)
  if [ ! -f "$HERMES_HOME/skills/software-development/design/SKILL.md" ]; then
    log "WARNING: $HERMES_HOME/skills/software-development/design does not resolve; /design-review falls back to the repo path"
  fi
fi
if [ "${HERMES_SKILLS_ONLY:-false}" = true ]; then
  log "shared skills linked (skills-only mode)"
  exit 0
fi

if hermes_is_wsl && [ "${HERMES_WSL_PREFLIGHT_DONE:-false}" != true ]; then
  hermes_wsl_preflight "$REPO_DIR" persist
fi

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
  if [ -f "$HOME/repos/synapse-mem/integrations/install/install-smem.sh" ]; then
    log "installing smem from ~/repos/synapse-mem"
    "$HOME/repos/synapse-mem/integrations/install/install-smem.sh"
  else
    log "note: smem not on PATH (clone agg-ayush/synapse-mem to ~/repos/synapse-mem to install)"
  fi
fi

if command -v hermes >/dev/null 2>&1 && ! ls "$HERMES_HOME"/tools/agent-browser-* >/dev/null 2>&1; then
  log "installing agent-browser via hermes pm"
  hermes pm install agent-browser
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
mkdir -p "$HERMES_HOME/skills/software-development"
PRT_LINK="$HERMES_HOME/skills/software-development/pr-review-toolkit"
if [ -e "$PRT_LINK" ] && [ ! -L "$PRT_LINK" ]; then
  mv "$PRT_LINK" "$HERMES_HOME/cache/pr-review-toolkit-$(date +%Y%m%d-%H%M%S)"
fi
ln -sfn "$REPO_DIR/skills/pr-review-toolkit" "$PRT_LINK"

link_skill() {
  local src="$1" dest="$2"
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    mv "$dest" "$HERMES_HOME/cache/$(basename "$dest")-$(date +%Y%m%d-%H%M%S)"
  fi
  ln -sfn "$src" "$dest"
}
link_skill "$REPO_DIR/skills/brainlift-writer" "$HERMES_HOME/skills/brainlift-writer"
PUBLIC_SKILLS="${PUBLIC_SKILLS:-$HOME/repos/public_skills}"
if [ ! -d "$PUBLIC_SKILLS/.git" ]; then
  git clone -q https://github.com/<stakeholder>/public_skills.git "$PUBLIC_SKILLS" || log "public_skills clone failed; brainlift review/render unavailable"
fi
if [ -f "$PUBLIC_SKILLS/brainlift/SKILL.md" ]; then
  link_skill "$PUBLIC_SKILLS/brainlift" "$HERMES_HOME/skills/brainlift"
fi

# 3b. Local Hermes source patches (patches/*.patch; see docs/local-upstream-mods.md).
# Per file: already applied (reverse check passes) -> skip; applies cleanly -> apply; else warn loudly
# and continue. Never forces, 3-way merges or overwrites. Re-run after `hermes update`.
# HERMES_SKIP_PATCHES=true skips; HERMES_AGENT_DIR points at another checkout (testing).
HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-$HERMES_HOME/hermes-agent}"
apply_hermes_patches() {
  local patch name file applied=0 skipped=0 failed=0
  if [ "${HERMES_SKIP_PATCHES:-false}" = true ]; then
    log "skipping Hermes source patches (HERMES_SKIP_PATCHES=true)"
    return 0
  fi
  if ! git -C "$HERMES_AGENT_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    log "WARNING: $HERMES_AGENT_DIR is not a git checkout; Hermes source patches NOT applied"
    return 0
  fi
  for patch in "$REPO_DIR"/patches/*.patch; do
    [ -f "$patch" ] || continue
    name="$(basename "$patch")"
    while IFS= read -r file; do
      [ -n "$file" ] || continue
      if git -C "$HERMES_AGENT_DIR" apply --reverse --check --include="$file" "$patch" >/dev/null 2>&1; then
        skipped=$((skipped + 1))
      elif git -C "$HERMES_AGENT_DIR" apply --check --include="$file" "$patch" >/dev/null 2>&1; then
        if git -C "$HERMES_AGENT_DIR" apply --include="$file" "$patch"; then
          log "applied $name: $file"
          applied=$((applied + 1))
        else
          log "WARNING: $name failed to apply to $file; continuing"
          failed=$((failed + 1))
        fi
      else
        log "WARNING: !!! $name does NOT apply to $file (upstream drift or conflicting local edit) — resolve by hand; patch skipped for this file"
        failed=$((failed + 1))
      fi
    done < <(git -C "$HERMES_AGENT_DIR" apply --numstat "$patch" 2>/dev/null | awk -F'\t' '{print $3}')
  done
  log "Hermes source patches: $applied applied, $skipped already applied, $failed need attention"
}
apply_hermes_patches || log "WARNING: Hermes source patch step errored; continuing"

# 3c. hermes-session-reset-policy plugin: config.yaml's session_reset policy does nothing without it.
if command -v hermes >/dev/null 2>&1; then
  # Capture output first: `grep -q` on a pipe SIGPIPEs hermes and fails the pipeline under pipefail.
  plugin_rows="$(hermes plugins list --plain 2>/dev/null || true)"
  if printf '%s\n' "$plugin_rows" | grep -Eq "^enabled[[:space:]].*[[:space:]]hermes-session-reset-policy$"; then
    log "hermes-session-reset-policy plugin already installed and enabled"
  elif printf '%s\n' "$plugin_rows" | grep -Eq "[[:space:]]hermes-session-reset-policy$"; then
    log "enabling installed hermes-session-reset-policy plugin"
    hermes plugins enable hermes-session-reset-policy \
      || log "WARNING: could not enable hermes-session-reset-policy; session_reset policy inactive"
  else
    log "installing hermes-session-reset-policy plugin"
    hermes plugins install hermes-session-reset-policy --yes-deps --enable \
      || log "WARNING: hermes-session-reset-policy install failed; session_reset policy inactive"
  fi

  # 3d. hermes-hygiene weekly cron (storage/health sweep, script-only). Created only if no job has that
  # name; an existing job (e.g. the remote's Telegram-delivered one) is left alone.
  cron_rows="$(hermes cron list --all 2>/dev/null || true)"
  if printf '%s\n' "$cron_rows" | grep -Eq "Name:[[:space:]]+hermes-hygiene[[:space:]]*$"; then
    log "hermes-hygiene cron already present"
  elif [ -f "$HERMES_HOME/scripts/hermes-hygiene.py" ] || [ -f "$REPO_DIR/scripts/hermes-hygiene.py" ]; then
    mkdir -p "$HERMES_HOME/scripts"
    [ -f "$HERMES_HOME/scripts/hermes-hygiene.py" ] || cp "$REPO_DIR/scripts/hermes-hygiene.py" "$HERMES_HOME/scripts/hermes-hygiene.py"
    log "creating hermes-hygiene cron (0 4 * * 0, local delivery)"
    hermes cron create "0 4 * * 0" --name hermes-hygiene --script hermes-hygiene.py --no-agent --deliver local \
      || log "WARNING: hermes-hygiene cron creation failed"
  fi
fi

# 4. Hermes scripts + hooks (copied so watchdog check_script_drift sees exact byte parity)
log "syncing scripts -> $HERMES_HOME/scripts/"
COMMON_SCRIPTS=(
  _alert_relay.py
  _platform.py
  _watermark.py
  auth-canary-relay.py
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
  watch_ci_main.json
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
cp "$REPO_DIR/scripts/red-gate-hook.py" "$HERMES_HOME/agent-hooks/red-gate.py"
cp "$REPO_DIR/scripts/capture-evidence.sh" "$HERMES_HOME/agent-hooks/capture-evidence.sh"
chmod +x "$HERMES_HOME/agent-hooks/subagent-ledger.py" "$HERMES_HOME/agent-hooks/aws-token-refresh.sh" "$HERMES_HOME/agent-hooks/red-gate.py" "$HERMES_HOME/agent-hooks/capture-evidence.sh"

# 5. synapse-mem Hermes provider activation, only from an up-to-date main checkout
SMEM_REPO="${SMEM_REPO:-$HOME/repos/synapse-mem}"
if [ -x "$SMEM_REPO/integrations/agents/hermes/activate.sh" ] && command -v smem >/dev/null 2>&1; then
  smem_branch="$(git -C "$SMEM_REPO" branch --show-current 2>/dev/null || true)"
  if [ "$smem_branch" != "main" ]; then
    log "skipping synapse-mem activation: $SMEM_REPO is on '${smem_branch:-detached}', not main"
  elif ! git -C "$SMEM_REPO" pull -q --ff-only origin main; then
    log "skipping synapse-mem activation: $SMEM_REPO cannot fast-forward to origin/main"
  else
    log "activating synapse-mem Hermes memory provider from main ($(git -C "$SMEM_REPO" rev-parse --short HEAD))"
    SMEM_BIN="$(command -v smem)" "$SMEM_REPO/integrations/agents/hermes/activate.sh" || true
  fi
fi

# 6. Claude Code seatbelt config sync (symlinks CLAUDE.md, skills/, plugins/ to ~/.claude)
log "syncing Claude Code seatbelt config ($SEATBELT_DIR -> $CLAUDE_HOME)"
link_claude_skills
[ -f "$CLAUDE_HOME/CLAUDE.md" ] && ln -sfn "$CLAUDE_HOME/CLAUDE.md" "$SEATBELT_DIR/CLAUDE.md"
ln -sfn "$CLAUDE_HOME/plugins" "$SEATBELT_DIR/plugins"

# Copy patched pr-review-toolkit specialist if pr-review-toolkit is in cache
for d in "$CLAUDE_HOME/plugins/cache/claude-plugins-official/pr-review-toolkit/"*; do
  if [ -d "$d/agents" ] && [ -f "$REPO_DIR/plugins/pr-review-toolkit/agents/state-transition-reviewer.md" ]; then
    cp "$REPO_DIR/plugins/pr-review-toolkit/agents/state-transition-reviewer.md" "$d/agents/"
    cp "$REPO_DIR/plugins/pr-review-toolkit/commands/review-pr.md" "$d/commands/"
  fi
done

# hermes-dev-process: agents and commands for the design-led dev process. This repo is registered
# as a local directory marketplace (hermes-setup); directory plugins are read in place, so repo
# edits apply at the next Claude Code session start. Installing at user scope enables it in
# ~/.claude/settings.json; the block below mirrors it into the seatbelt settings.
install_dev_process_plugin() {
  local mp="hermes-setup" id="hermes-dev-process@hermes-setup" registered state
  if ! command -v claude >/dev/null 2>&1; then
    log "claude CLI not found; skipping hermes-dev-process plugin"
    return 0
  fi
  [ -f "$REPO_DIR/.claude-plugin/marketplace.json" ] || return 0
  registered="$(claude plugin marketplace list --json 2>/dev/null | python3 -c '
import json, sys
for m in json.load(sys.stdin):
    if m.get("name") == "hermes-setup":
        print(m.get("path", ""))
' 2>/dev/null || true)"
  if [ "$registered" = "$REPO_DIR" ]; then
    claude plugin marketplace update "$mp" >/dev/null
  else
    if [ -n "$registered" ]; then
      log "re-registering $mp marketplace ($registered -> $REPO_DIR)"
      claude plugin marketplace remove "$mp" >/dev/null || true
    fi
    claude plugin marketplace add "$REPO_DIR" >/dev/null
  fi
  state="$(claude plugin list --json 2>/dev/null | python3 -c '
import json, sys
state = "missing"
for p in json.load(sys.stdin):
    if p.get("id") == "hermes-dev-process@hermes-setup":
        state = "enabled" if p.get("enabled") else "disabled"
print(state)
' 2>/dev/null || echo missing)"
  case "$state" in
    enabled) log "$id already installed and enabled" ;;
    disabled) log "enabling $id"; claude plugin enable "$id" >/dev/null ;;
    *) log "installing $id"; claude plugin install "$id" >/dev/null ;;
  esac
}
install_dev_process_plugin || log "WARNING: hermes-dev-process plugin install failed; run: claude plugin marketplace add $REPO_DIR && claude plugin install hermes-dev-process@hermes-setup"

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

# 6b. Machine-wide Claude Code managed hook: blocks Claude Code on the TrueFoundry LLM gateway
# (pay-per-token anthropic-primary billing). Needs root; without passwordless sudo, print the
# one-line command for the owner and continue.
if sudo -n true 2>/dev/null; then
  if sudo -n sh "$REPO_DIR/config/claude-code/install-managed-hook.sh"; then
    log "installed Claude Code managed hook (blocks TrueFoundry endpoint)"
  else
    log "WARNING: Claude Code managed hook install failed; run: sudo sh $REPO_DIR/config/claude-code/install-managed-hook.sh"
  fi
else
  log "NOTE: Claude Code managed hook not installed (no passwordless sudo). Run once: sudo sh $REPO_DIR/config/claude-code/install-managed-hook.sh"
fi

# 7. Global gitignore (.serena/, .ui-flow/, .graphify/, graphify-out/, .claude/settings.local.json)
GIT_IGNORE="$(git config --global core.excludesfile || true)"
if [ -z "$GIT_IGNORE" ]; then
  GIT_IGNORE="$HOME/.config/git/ignore"
  mkdir -p "$(dirname "$GIT_IGNORE")"
  git config --global core.excludesfile "$GIT_IGNORE"
fi
GIT_IGNORE="${GIT_IGNORE/#\~/$HOME}"
mkdir -p "$(dirname "$GIT_IGNORE")"
touch "$GIT_IGNORE"
for pat in "**/.claude/settings.local.json" ".serena/" ".ui-flow/" ".graphify/" "graphify-out/"; do
  grep -qxF "$pat" "$GIT_IGNORE" 2>/dev/null || echo "$pat" >> "$GIT_IGNORE"
done

# 8. Config templates — copy only if absent (never clobber live config/secrets)
FRESH_CONFIG=false
if [ ! -f "$HERMES_HOME/config.yaml" ]; then
  cp "$REPO_DIR/config/config.yaml.template" "$HERMES_HOME/config.yaml"
  FRESH_CONFIG=true
  log "copied config.yaml.template -> $HERMES_HOME/config.yaml"
fi
if [ ! -f "$HERMES_HOME/.env" ]; then
  cp "$REPO_DIR/config/env.template" "$HERMES_HOME/.env"
  chmod 600 "$HERMES_HOME/.env"
  log "copied env.template -> $HERMES_HOME/.env (fill in secrets)"
fi

# 9. Host profile (hosts/<mac|sora|wsl>/): host-only scripts, units, cron jobs, plugins, watchdog.json and, only
# when config.yaml was freshly created above, per-host config overrides. Install-if-absent only; see
# devbox/host-profile.sh. Skipped in the Claude-only/skills-only modes (they exit earlier) and with
# HERMES_SKIP_HOST_PROFILE=true. HERMES_HOST_PROFILE=<name> overrides the mac/sora/wsl auto-selection.
host_rc=0
REPO_DIR="$REPO_DIR" HERMES_HOME="$HERMES_HOME" FRESH_CONFIG="$FRESH_CONFIG" \
  bash "$REPO_DIR/devbox/host-profile.sh" || host_rc=$?
if [ "$host_rc" -eq 3 ]; then
  log "finished WITH ERRORS: the gateway requested with HERMES_INSTALL_GATEWAY=true is not installed (see the ERROR block above)."
  exit 3
fi
[ "$host_rc" -eq 0 ] || log "WARNING: host profile step failed; continuing"

# 10. Watchdog scheduler (every 30 min). Runs after the host profile, which is what installs a wsl gateway.
# Install only if absent; never overwrite an existing unit.
# watchdog.py itself is synced in step 4; its config (scripts/watchdog.json) is host-specific and not managed here.
if ! hermes_wants_watchdog; then
  log "watchdog timer not installed: on wsl it is installed with the gateway, which it reports on"
elif [ "$IS_MAC" = true ]; then
  WD_PLIST="$HOME/Library/LaunchAgents/ai.hermes.watchdog.plist"
  if [ -f "$WD_PLIST" ]; then
    log "watchdog launchd agent already installed"
  elif [ -f "$REPO_DIR/config/ai.hermes.watchdog.plist" ]; then
    mkdir -p "$HOME/Library/LaunchAgents" "$HERMES_HOME/logs"
    sed "s|/Users/ayush|$HOME|g" "$REPO_DIR/config/ai.hermes.watchdog.plist" > "$WD_PLIST"
    log "installed watchdog launchd agent"
    launchctl bootstrap "gui/$(id -u)" "$WD_PLIST" 2>/dev/null || log "note: load the watchdog with: launchctl bootstrap gui/$(id -u) $WD_PLIST"
  fi
elif command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  WD_DIR="$HOME/.config/systemd/user"
  if [ -f "$WD_DIR/hermes-watchdog.timer" ] && [ -f "$WD_DIR/hermes-watchdog.service" ]; then
    log "watchdog systemd timer already installed"
  elif [ -f "$REPO_DIR/config/hermes-watchdog.timer" ]; then
    mkdir -p "$WD_DIR"
    for u in hermes-watchdog.service hermes-watchdog.timer; do
      [ -f "$WD_DIR/$u" ] || cp "$REPO_DIR/config/$u" "$WD_DIR/$u"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now hermes-watchdog.timer \
      && log "installed watchdog systemd timer" \
      || log "WARNING: could not enable hermes-watchdog.timer"
  fi
fi

log "done — setup and sideloaded tools verified."
