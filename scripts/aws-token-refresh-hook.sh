#!/usr/bin/env bash
# Hermes post_tool_call hook: after a `terminal` tool call, if output shows an
# expired/invalid AWS token, fire the OneLogin refresh (trilogy-aws-key.py)
# in the background and tell the agent to retry.
# stdin: Hermes hook JSON payload. stdout: JSON response ({} = no-op).
set -u

payload="$(cat)"
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"
[[ "$tool" == "terminal" ]] || { printf '{}\n'; exit 0; }

# tool result content is in .tool_output / .tool_result depending on event shape; check both
out="$(printf '%s' "$payload" | jq -r '(.tool_output // .tool_result // .output // "") | tostring' 2>/dev/null)"

if printf '%s' "$out" | grep -qiE 'ExpiredToken|InvalidToken|token.*expired|SSO.*expired|AuthorizationHeaderMalformed|credentials.*expired|The security token included in the request is (expired|invalid)'; then
  "$HOME/.hermes/scripts/aws-creds-refresh.sh" >/dev/null 2>&1 &
  printf '{"context":"AWS token expired. OneLogin refresh (trilogy-aws-key) started in background; new creds land in ~/.aws/credentials [default] within ~15s (if the cached id_token is valid; otherwise the keep-hot cron alert fires). Wait ~15s then retry the failed command."}\n'
  exit 0
fi

printf '{}\n'
