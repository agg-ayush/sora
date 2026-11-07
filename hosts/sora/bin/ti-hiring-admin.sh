#!/usr/bin/env bash
# ti-hiring admin API helper. Reads the stored token, makes the call, never prints the token.
# Usage: ti-hiring-admin.sh <METHOD> <PATH> [JSON_BODY]
# On a 401/403 it refreshes the token from SSM and retries once.
set -euo pipefail
TOKEN_FILE="$HOME/.ti-hiring-admin-token"
SSM_PARAM="/ti/orchestrator/ADMIN_TOKEN"
BASE="https://<internal-host>"

refresh_token() {
  $HOME/.hermes/scripts/aws-creds-refresh.sh >/dev/null 2>&1 || true
  aws --profile trilogy --region ap-south-1 ssm get-parameter \
    --name "$SSM_PARAM" --with-decryption --query Parameter.Value --output text > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
}

call() {
  local token; token=$(cat "$TOKEN_FILE")
  local args=(-sS -X "$METHOD" -H "Authorization: Bearer $token" -o "$OUT" -w '%{http_code}')
  [ -n "$BODY" ] && args+=(-H 'Content-Type: application/json' --data "$BODY")
  curl "${args[@]}" "$BASE$PATH_"
}

[ $# -lt 2 ] && { echo "usage: $0 <METHOD> <PATH> [JSON_BODY]" >&2; exit 2; }
METHOD=$1; PATH_=$2; BODY=${3:-}
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT

[ -f "$TOKEN_FILE" ] || refresh_token
code=$(call)
if [ "$code" = "401" ] || [ "$code" = "403" ]; then
  refresh_token
  code=$(call)
fi
cat "$OUT"
printf '\n[http %s]\n' "$code"
