#!/usr/bin/env bash
# Refresh AWS creds on sora (Linux), fully unattended.
# Two providers, two accounts:
#   [devflows] = RAM-AWS-Prod-DevFactory-devflows-Admin (<aws-account>)
#     -> saml2aws via KeyCloak (tmux-driven, password from
#        ~/.config/saml2aws/.trilogy-password). Password-only, no MFA,
#        zero-touch. saml2aws writes [trilogy]; we rename it to [devflows].
#   [eswlegal] = RAM-AWS-Int-CentralFunctions-ESWLegal-Admin (<aws-account>)
#     -> trilogy-aws-key.py OneLogin STS mint, best-effort: works only while
#        the cached id_token (~/.aws/onelogin-id-token.json, 2h lifetime) is
#        valid; when it lapses it needs ONE interactive --headless login
#        (WebAuthn/Touch ID — no unattended path exists) and the keep-hot
#        cron alerts Telegram with the command. ESWLegal is NOT offered via
#        KeyCloak SAML (assertion holds only the DevFactory role).
# No default/trilogy alias: every aws call must name --profile explicitly.
set -u

LOG="/tmp/aws-creds-refresh.log"
PASS_FILE="$HOME/.config/saml2aws/.trilogy-password"
KEY="trilogy"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

# ---------- 1. devflows via saml2aws (required) ----------
if [ ! -r "$PASS_FILE" ]; then
  log "FAIL: no password file $PASS_FILE"
  echo "AWS refresh FAILED: password file missing" >&2
  exit 2
fi

SESSION="saml2aws-refresh"
tmux kill-session -t "$SESSION" 2>/dev/null || true
# plain shell + send-keys (the command-form of new-session dies instantly here)
tmux new-session -d -s "$SESSION" -x 200 -y 50
sleep 1
tmux send-keys -t "$SESSION" "saml2aws login -a $KEY --force" Enter
sleep 3
# username prompt: accept the default from ~/.saml2aws
tmux send-keys -t "$SESSION" Enter
sleep 2
tmux send-keys -t "$SESSION" -l "$(cat "$PASS_FILE")"
tmux send-keys -t "$SESSION" Enter

ok=0
deadline=$((SECONDS + 90))
while (( SECONDS < deadline )); do
  pane=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null || true)
  case "$pane" in
    *"Logged in as:"*) ok=1; break ;;
    *"EXIT=1"*|*"Error validating"*|*"failed to authenticate"*) break ;;
  esac
  sleep 2
done
tmux kill-session -t "$SESSION" 2>/dev/null || true

if (( ok != 1 )); then
  log "FAIL: saml2aws login did not complete"
  echo "AWS refresh FAILED (saml2aws devflows)" >&2
  exit 1
fi

# rename saml2aws's [trilogy] section -> [devflows]
python3 - <<'PYEOF'
import configparser, os
p = os.path.expanduser("~/.aws/credentials")
c = configparser.ConfigParser(); c.read(p)
if "trilogy" in c:
    c["devflows"] = dict(c["trilogy"])
    del c["trilogy"]
c.pop("default", None)
with open(p, "w") as f: c.write(f)
os.chmod(p, 0o600)
PYEOF
log "devflows refreshed via saml2aws"

# ---------- 2. eswlegal via OneLogin (best-effort) ----------
ESW="stale"
TOKEN_OK=$(python3 -c "
import json,base64,time
try:
    d=json.load(open('$HOME/.aws/onelogin-id-token.json'))
    p=d['id_token'].split('.')[1]; p+='='*(-len(p)%4)
    c=json.loads(base64.urlsafe_b64decode(p))
    print(1 if c.get('exp',0)-time.time() > 900 else 0)
except Exception:
    print(0)
" 2>/dev/null || echo 0)

if [ "$TOKEN_OK" = "1" ]; then
  out=$(python3 "$HOME/.hermes/scripts/trilogy-aws-key.py" \
    --credential-process --quiet \
    --role admin --select-role "RAM-AWS-Int-CentralFunctions-ESWLegal-Admin" \
    --profile-name tmpmint --login ayushaggarwal018@gmail.com \
    --password "$(cat "$PASS_FILE")" 2>/dev/null)
  if [ -n "$out" ] && printf '%s' "$out" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
    ESW="ok"
    printf '%s' "$out" | python3 -c '
import json, sys, configparser, os
blob = json.load(sys.stdin)
p = os.path.expanduser("~/.aws/credentials")
c = configparser.ConfigParser(); c.read(p)
c["eswlegal"] = {
    "aws_access_key_id": blob["AccessKeyId"],
    "aws_secret_access_key": blob["SecretAccessKey"],
    "aws_session_token": blob["SessionToken"],
}
with open(p, "w") as f: c.write(f)
os.chmod(p, 0o600)
'
    log "eswlegal refreshed via OneLogin"
  else
    log "eswlegal mint failed (id_token valid but mint error)"
  fi
else
  log "eswlegal skipped: OneLogin id_token expired/lapsed"
fi

# ---------- done ----------
if [ "$ESW" = "ok" ]; then
  echo "AWS credentials OK (devflows via saml2aws, eswlegal via onelogin)"
else
  echo "AWS credentials OK (devflows via saml2aws; eswlegal STALE - needs one --headless onelogin login)"
fi
exit 0
