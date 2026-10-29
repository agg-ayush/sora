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

mint_onelogin() {  # mint_onelogin <select-role> <profile> — OneLogin OIDC STS mint
  token_valid || return 2
  local out
  out=$(python3 "$HOME/.hermes/scripts/trilogy-aws-key.py" \
    --credential-process --quiet \
    --role admin --select-role "$1" \
    --profile-name tmpmint --login "$LOGIN" \
    --password "$(cat "$PASS_FILE")" 2>/dev/null) || return 1
  printf '%s' "$out" | PROFILE="$2" python3 -c '
import json, sys, os, configparser
blob = json.load(sys.stdin)
p = os.path.expanduser("~/.aws/credentials")
c = configparser.ConfigParser(); c.read(p)
c[os.environ["PROFILE"]] = {
    "aws_access_key_id": blob["AccessKeyId"],
    "aws_secret_access_key": blob["SecretAccessKey"],
    "aws_session_token": blob["SessionToken"],
}
with open(p, "w") as f: c.write(f)
os.chmod(p, 0o600)
' 2>/dev/null
}

# refresh <role-arn> <select-role> <profile>: saml2aws first, OneLogin fallback.
# Both roles map to the same AD user — identical method priority for both.
refresh() {  # returns 0 on success (either source), nonzero if both fail
  local arn="$1" sel="$2" profile="$3" rc=0 src="saml2aws"
  mint_saml "$arn" "$profile" || rc=$?
  if (( rc != 0 )); then
    log "$profile saml2aws exit $rc — falling back to OneLogin"
    if mint_onelogin "$sel" "$profile"; then
      src="onelogin"
      log "$profile refreshed via OneLogin fallback"
    else
      log "FAIL: $profile both paths failed — needs one --headless onelogin login"
      return 3
    fi
  else
    log "$profile refreshed via saml2aws"
  fi
  SOURCES[$profile]="$src"
  return 0
}

declare -A SOURCES

refresh "$DF_ARN" "RAM-AWS-Prod-DevFactory-devflows-Admin" devflows || DF_RC=$? || true
DF_RC=${DF_RC:-0}
refresh "$ESW_ARN" "RAM-AWS-Int-CentralFunctions-ESWLegal-Admin" eswlegal || ESW_RC=$? || true
ESW_RC=${ESW_RC:-0}

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

if (( DF_RC != 0 || ESW_RC != 0 )); then
  echo "AWS refresh: one or both profiles need a headless onelogin login on this host (see $LOG)" >&2
  exit 3
fi

echo "AWS credentials OK (devflows via ${SOURCES[devflows]}, eswlegal via ${SOURCES[eswlegal]})"
