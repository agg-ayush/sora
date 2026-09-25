#!/usr/bin/env bash
# Refresh AWS creds via trilogy-aws-key.py (OneLogin OIDC), fully headless.
# Uses --credential-process for JSON output, --smart to skip if still valid.
# First run requires browser auth; subsequent refreshes use cached id_token.
set -u

SCRIPT="$HOME/hermes-tier-setup/scripts/trilogy-aws-key.py"
LOG="/tmp/aws-creds-refresh.log"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

args=(--credential-process --quiet --role admin --select-role "RAM-AWS-Prod-DevFactory-devflows-Admin" --profile-name trilogy --login ayushaggarwal018@gmail.com --headless)
if (( FORCE == 1 )); then
  args+=(--force)
else
  args+=(--smart)
fi

log "starting refresh (force=$FORCE)"

output=$(python3 "$SCRIPT" "${args[@]}" 2>&1)
exit_code=$?

if (( exit_code == 0 )); then
  # credential-process outputs JSON with AccessKeyId etc — write to ~/.aws/credentials
  # The script may print warnings before the JSON — extract the last JSON line
  json_line=$(echo "$output" | grep -E '^\{.*\}$' | tail -1)
  if [[ -z "$json_line" ]]; then
    log "refresh FAILED: no JSON in output"
    echo "AWS creds refresh FAILED — no JSON output, see $LOG" >&2
    exit 1
  fi
  python3 -c "
import json, sys, configparser, os
cred = json.loads(sys.stdin.read())
p = os.path.expanduser('~/.aws/credentials')
c = configparser.ConfigParser()
c.read(p)
c['trilogy'] = {
    'aws_access_key_id': cred['AccessKeyId'],
    'aws_secret_access_key': cred['SecretAccessKey'],
    'aws_session_token': cred['SessionToken'],
}
c['default'] = dict(c['trilogy'])
with open(p, 'w') as f:
    c.write(f)
" <<< "$json_line"
  log "refresh OK"
  echo "AWS credentials OK (trilogy-aws-key.py)"
  exit 0
else
  log "refresh FAILED: $output"
  echo "AWS creds refresh FAILED — see $LOG" >&2
  echo "$output" >&2
  exit 1
fi
