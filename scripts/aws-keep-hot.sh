#!/usr/bin/env bash
# Keep-hot (Mac): refresh AWS creds hourly inside the OneLogin id_token 2h window.
set -u
LOG="/tmp/aws-creds-refresh.log"
TOKEN_FILE="$HOME/.aws/onelogin-id-token.json"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

if bash ~/.hermes/scripts/aws-creds-refresh.sh >/dev/null 2>&1; then
  log "keep-hot: refreshed"
  exit 0
fi

TTL=$(python3 -c "
import json,base64,time
try:
    d=json.load(open('$TOKEN_FILE'))
    p=d['id_token'].split('.')[1]; p+='='*(-len(p)%4)
    c=json.loads(base64.urlsafe_b64decode(p))
    print(max(0,int(c.get('exp',0)-time.time())))
except Exception:
    print(0)
" 2>/dev/null || echo 0)

if [ "$TTL" -gt 900 ]; then
  log "keep-hot: refresh failed but token TTL ${TTL}s - retry next tick"
  exit 0
fi
log "keep-hot: token lapsed (TTL ${TTL}s) - next interactive use will prompt Touch ID"
