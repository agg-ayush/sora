#!/usr/bin/env bash
# Refresh AWS creds via saml2aws (trilogy account), fully headless.
# Runs inside a detached tmux session (saml2aws uses a TTY prompt; keychain supplies the password).
# After login, copies [trilogy] -> [default] in ~/.aws/credentials so bare `aws` works.
# saml2aws skips login when creds are still fresh; --force overrides that.
set -u

SESSION="saml2aws-refresh"
LOG="/tmp/saml2aws-refresh.log"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

# already running?
if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "refresh already in progress"
  exit 0
fi

saml2aws_args=(login -a trilogy)
(( FORCE == 1 )) && saml2aws_args+=(--force)

log "starting refresh (force=$FORCE)"
tmux new-session -d -s "$SESSION" -x 200 -y 50 \
  "saml2aws ${saml2aws_args[*]} 2>&1; echo SAML2AWS_EXIT=\$?; sleep 120"

# wait for prompts / terminal states
deadline=$((SECONDS + 90))
sent_user=0
sent_pass=0
ok=0

while (( SECONDS < deadline )); do
  pane=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || true)

  # fast-path: saml2aws exited because creds still valid (no prompt shown)
  if [[ "$pane" == *"SAML2AWS_EXIT=0"* ]] && (( sent_user == 0 && sent_pass == 0 )); then
    ok=1
    log "creds still fresh, saml2aws no-op"
    break
  fi

  case "$pane" in
    *"Logged in as:"*) ok=1; log "login success"; break ;;
    *"SAML2AWS_EXIT=1"*|*"Error "*) break ;;
  esac

  if (( sent_user == 0 )) && [[ "$pane" == *"Username"* ]]; then
    tmux send-keys -t "$SESSION" Enter; sent_user=1; sleep 1; continue
  fi
  if (( sent_user == 1 && sent_pass == 0 )) && [[ "$pane" == *"Password"* ]]; then
    tmux send-keys -t "$SESSION" Enter; sent_pass=1; sleep 1; continue
  fi
  sleep 1
done

# let credentials file flush
sleep 2
tmux kill-session -t "$SESSION" 2>/dev/null

if (( ok == 1 )); then
  # mirror trilogy -> default so bare `aws` works
  python3 - <<'PYEOF'
import configparser, os
p = os.path.expanduser('~/.aws/credentials')
c = configparser.ConfigParser()
c.read(p)
if 'trilogy' in c:
    c['default'] = dict(c['trilogy'])
    with open(p, 'w') as f:
        c.write(f)
PYEOF
  log "refresh OK"
  echo "AWS credentials OK (saml2aws trilogy)"
  exit 0
else
  tail3=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null | grep -v '^$' | tail -3 | tr '\n' ' ')
  log "refresh FAILED ($tail3)"
  echo "saml2aws refresh FAILED — see $LOG" >&2
  exit 1
fi
