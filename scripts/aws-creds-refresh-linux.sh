#!/usr/bin/env bash
# Refresh AWS creds on sora (Linux). PRIMARY: saml2aws/KeyCloak, plain
# non-interactive flags (--skip-prompt --password from the 0600 file) — no tmux.
# FALLBACK for eswlegal (automatic): OneLogin OIDC via trilogy-aws-key.py while
# the cached id_token (~/.aws/onelogin-id-token.json, ~2h lifetime) is valid.
# KeyCloak/saml2aws is being RETIRED by Trilogy — when it dies the saml2aws
# mints fail and OneLogin becomes the sole path (eswlegal then needs periodic
# --headless WebAuthn logins; the keep-hot alert says so).
# Profiles: [devflows] = RAM-AWS-Prod-DevFactory-devflows-Admin (<aws-account>)
#           [eswlegal] = RAM-AWS-Int-CentralFunctions-ESWLegal-Admin (<aws-account>)
# No default/trilogy alias: every aws call must name --profile explicitly.
set -u

LOG="/tmp/aws-creds-refresh.log"
PASS_FILE="$HOME/.config/saml2aws/.trilogy-password"
DF_ARN="arn:aws:iam::<aws-account>:role/RAM-AWS-Prod-DevFactory-devflows-Admin"
ESW_ARN="arn:aws:iam::<aws-account>:role/RAM-AWS-Int-CentralFunctions-ESWLegal-Admin"
LOGIN="ayushaggarwal018@gmail.com"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

mint_saml() {  # mint_saml <role-arn> <profile> — non-interactive KeyCloak mint
  [ -r "$PASS_FILE" ] || return 2
  saml2aws login -a trilogy \
    --role "$1" -p "$2" \
    --skip-prompt --force \
    --username "$LOGIN" --password "$(cat "$PASS_FILE")" \
    >/dev/null 2>>"$LOG"
}

token_valid() {
  python3 -c "
import json,base64,time
try:
    d=json.load(open('$HOME/.aws/onelogin-id-token.json'))
    p=d['id_token'].split('.')[1]; p+='='*(-len(p)%4)
    c=json.loads(base64.urlsafe_b64decode(p))
    raise SystemExit(0 if c.get('exp',0)-time.time() > 900 else 1)
except Exception:
    raise SystemExit(1)
" 2>/dev/null
}

mint_esw_onelogin() {
  token_valid || return 2
  local out
  out=$(python3 "$HOME/.hermes/scripts/trilogy-aws-key.py" \
    --credential-process --quiet \
    --role admin --select-role "RAM-AWS-Int-CentralFunctions-ESWLegal-Admin" \
    --profile-name tmpmint --login "$LOGIN" \
    --password "$(cat "$PASS_FILE")" 2>/dev/null) || return 1
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
' 2>/dev/null
}

# ---------- devflows ----------
if ! mint_saml "$DF_ARN" devflows; then
  log "FAIL: devflows saml2aws exit $? — KeyCloak retired/unreachable; leaving existing creds"
  echo "AWS refresh FAILED (devflows saml2aws exit $?) — see $LOG" >&2
  exit 1
fi
log "devflows refreshed via saml2aws"

# ---------- eswlegal ----------
ESW_SRC="saml2aws"
esw_saml_rc=0
mint_saml "$ESW_ARN" eswlegal || esw_saml_rc=$?
if (( esw_saml_rc != 0 )); then
  log "eswlegal saml2aws exit $esw_saml_rc — falling back to OneLogin"
  if mint_esw_onelogin; then
    ESW_SRC="onelogin"
    log "eswlegal refreshed via OneLogin fallback"
  else
    log "FAIL: eswlegal both paths failed — needs one --headless onelogin login"
    echo "AWS refresh: eswlegal needs a headless onelogin login on this host" >&2
    exit 3
  fi
fi

# keep exactly devflows + eswlegal; drop anything saml2aws wrote under other names
python3 - <<'PYEOF'
import configparser, os
p = os.path.expanduser("~/.aws/credentials")
c = configparser.ConfigParser(); c.read(p)
keep = {"devflows", "eswlegal"}
for s in list(c.sections()):
    if s not in keep:
        del c[s]
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "w") as f: c.write(f)
os.chmod(p, 0o600)
PYEOF

echo "AWS credentials OK (devflows + eswlegal via saml2aws/$ESW_SRC)"
