#!/usr/bin/env bash
# Hermes post_tool_call hook: after a `terminal` tool call, if output shows an expired/invalid
# AWS token, fire the saml2aws refresh script in the background and tell the agent to retry.
# stdin: Hermes hook JSON payload. stdout: JSON response ({} = no-op).
set -u

payload="$(cat -)"
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"
[[ "$tool" == "terminal" ]] || { printf '{}\n'; exit 0; }

# tool result content is in .tool_output / .tool_result depending on event shape; check both
out="$(printf '%s' "$payload" | jq -r '(.tool_output // .tool_result // .output // "") | tostring' 2>/dev/null)"

if printf '%s' "$out" | grep -qiE 'ExpiredToken|InvalidToken|token.*expired|SSO.*expired|AuthorizationHeaderMalformed|credentials.*expired|The security token included in the request is (expired|invalid)'; then
  # already running? skip
  if tmux has-session -t saml2aws-refresh 2>/dev/null; then
    printf '{"context":"AWS token expired; saml2aws refresh already running in tmux (session saml2aws-refresh). Retry the command in ~15s."}\n'
    exit 0
  fi
  /Users/ayush/.hermes/scripts/aws-creds-refresh.sh >/dev/null 2>&1 &
  printf '{"context":"AWS token expired. saml2aws refresh started in background (tmux session saml2aws-refresh); new creds land in ~/.aws/credentials [default]. Wait ~10-15s then retry the failed command."}\n'
  exit 0
fi

printf '{}\n'
