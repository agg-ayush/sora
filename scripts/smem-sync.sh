#!/usr/bin/env bash
# Hourly smem replica sync via the smem-sync git transport.
# Feed files are append-only per replica; git is transport only.
set -u
LOG="/tmp/smem-sync.log"
REPO="$HOME/repos/smem-sync"
DB="$HOME/.hermes/synapse/smem.db"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }
[ -x "$(command -v smem || true)" ] || [ -x "$HOME/.local/bin/smem" ] || { log "smem not found"; exit 0; }
SMEM="$(command -v smem || echo "$HOME/.local/bin/smem")"
cd "$REPO" || { log "no repo"; exit 0; }
git pull -q --rebase origin main >>"$LOG" 2>&1 || true
SMEM_DB="$DB" "$SMEM" sync >>"$LOG" 2>&1 || log "smem sync failed"
if [ -n "$(git status --porcelain feeds/ 2>/dev/null)" ]; then
  BR="sync/$(hostname -s)-$(date +%H%M)"
  git checkout -q -b "$BR" 2>/dev/null
  git add -A feeds/ && git commit -q -m "feed: $(hostname -s) hourly sync"
  git push -q "origin" "$BR" >>"$LOG" 2>&1
  git checkout -q main
  # bring main to the branch tip; rebase on any racing push and retry once
  git merge -q --ff-only "$BR" >>"$LOG" 2>&1
  if ! git push -q origin main >>"$LOG" 2>&1; then
    git fetch -q origin && git rebase -q origin/main >>"$LOG" 2>&1
    git push -q origin main >>"$LOG" 2>&1 || log "git transport push failed"
  fi
  git branch -D "$BR" -q 2>/dev/null
fi
log "sync done"
