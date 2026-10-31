#!/usr/bin/env bash
# Refresh AWS creds via OneLogin OIDC (trilogy-aws-key.py password grant), fully unattended.
# Password comes from the macOS keychain (service "trilogy-aws", account ayushaggarwal018@gmail.com);
# no browser, no TTY, no tmux. Replaces the saml2aws wrapper (DevFactory is retiring saml2aws/Keycloak).
# Maintains TWO account profiles, both minted from the same cached id_token (pure STS):
#   [devflows] = RAM-AWS-Prod-DevFactory-devflows-Admin
#   [eswlegal] = RAM-AWS-Int-CentralFunctions-ESWLegal-Admin
# No default/trilogy alias: every aws call must name --profile devflows|eswlegal explicitly.
# --force bypasses the min-refresh-time skip.
set -u

SCRIPT="$HOME/hermes-setup/scripts/trilogy-aws-key.py"
LOG="/tmp/aws-creds-refresh.log"
KEYCHAIN_SERVICE="trilogy-aws"
LOGIN="ayushaggarwal018@gmail.com"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

PW=$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$LOGIN" -w 2>/dev/null)
if [ -z "$PW" ]; then
  log "FAIL: no keychain password for $KEYCHAIN_SERVICE/$LOGIN"
  echo "AWS refresh FAILED: keychain password missing" >&2
  exit 2
fi

MIN_REFRESH=15
(( FORCE == 1 )) && MIN_REFRESH=0

mint() {  # mint <role-name> -> credential-process JSON on stdout
  python3 "$SCRIPT" \
    --credential-process --quiet \
    --role admin --select-role "$1" \
    --profile-name tmpmint --login "$LOGIN" \
    --password "$PW" \
    --min-refresh-time "$MIN_REFRESH" 2>/dev/null
}

A=$(mint "RAM-AWS-Prod-DevFactory-devflows-Admin")
B=$(mint "RAM-AWS-Int-CentralFunctions-ESWLegal-Admin")

if [ -z "$A" ] || ! printf '%s' "$A" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  log "FAIL: devflows mint produced no credential JSON"
  echo "AWS refresh FAILED (devflows)" >&2
  exit 1
fi
if [ -z "$B" ] || ! printf '%s' "$B" | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
  log "FAIL: eswlegal mint produced no credential JSON"
  echo "AWS refresh FAILED (eswlegal)" >&2
  exit 1
fi

# write profiles: devflows + eswlegal only (no default/trilogy alias)
A="$A" B="$B" python3 -c '
import json, os, configparser
df = json.loads(os.environ["A"])
es = json.loads(os.environ["B"])
p = os.path.expanduser("~/.aws/credentials")
c = configparser.ConfigParser()
c.read(p)
def sec(b):
    return {
        "aws_access_key_id": b["AccessKeyId"],
        "aws_secret_access_key": b["SecretAccessKey"],
        "aws_session_token": b["SessionToken"],
    }
c["devflows"] = sec(df)
c["eswlegal"] = sec(es)
for legacy in ("trilogy", "default"):
    c.pop(legacy, None)
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, "w") as f:
    c.write(f)
os.chmod(p, 0o600)
'

log "refresh OK (devflows + eswlegal)"
echo "AWS credentials OK (devflows + eswlegal)"
