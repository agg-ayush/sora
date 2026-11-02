#!/bin/bash
# Deny-guard hook for T3 coding sessions — structurally blocks dangerous
# commands regardless of what the prompt says. Runs as a Claude Code
# PreToolUse hook (reads the tool-call JSON on stdin, exits 2 to block).
#
# Blocks: git push, gh pr create/merge, gh release, gh repo create, rm -rf /,
# sudo, cat/less/head/tail on .env/credentials/secrets files, and any command
# that would exfiltrate to a non-allowlisted host. The tier system's merge
# gate is the broker — the T3 agent edits+commits, never pushes/merges.
#
# Install: reference from the T3 session's settings.json:
#   { "hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [ { "type":
#     "command", "command": "~/.hermes/scripts/deny-guard.sh" } ] } ] } }

set -euo pipefail

# Read the tool-call JSON on stdin
INPUT=$(cat)

# Extract the command from the tool-call JSON
# The PreToolUse hook receives: {"tool_name":"Bash","tool_input":{"command":"..."}}
COMMAND=$(echo "$INPUT" | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input',{}).get('command',''))
except Exception:
    print('')
" 2>/dev/null || echo "")

# Normalize whitespace for matching
NORM=$(echo "$COMMAND" | tr -s ' \t\n' ' ')

# Block patterns (exit 2 = block the tool call)
block() { echo "BLOCKED by deny-guard: $1" >&2; exit 2; }

# git push / force-push / any push
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)git\s+push\b'; then
  block "git push — the merge gate is the broker; the T3 agent edits+commits, never pushes"
fi

# gh pr create / merge / close / reopen / edit (PR lifecycle is the broker's)
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)gh\s+pr\s+(create|merge|close|reopen|edit)\b'; then
  block "gh pr create/merge — the merge gate is the broker; the T3 agent edits+commits, never PRs"
fi

# gh release / gh repo create (shared-infra)
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)gh\s+(release|repo)\s+(create|delete)\b'; then
  block "gh release/repo create/delete — shared-infra, the broker owns it"
fi

# rm -rf / or rm -rf ~ (catastrophic)
if echo "$NORM" | grep -qE 'rm\s+-rf\s+(/|~|\$HOME)\b'; then
  block "rm -rf / or ~ — catastrophic"
fi

# sudo
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)sudo\s'; then
  block "sudo — not in a T3 session"
fi

# cat/less/head/tail on secrets files
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)(cat|less|head|tail|more)\s+.*(\.env|credentials|secrets?|\.pem|\.key|id_rsa|id_ed25519)\b'; then
  block "reading a secrets file — the T3 agent doesn't need to read credentials"
fi

# aws/gcloud/az destructive (delete/remove/destroy)
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)(aws|gcloud|az)\s+.*(delete|remove|destroy|terminate)\b'; then
  block "cloud destructive command — the broker owns infra mutations"
fi

# curl/wget to non-allowlisted hosts (exfil surface) — allow the common ones
if echo "$NORM" | grep -qE '(^|\s|&&|\|\|)(curl|wget)\s'; then
  # allow api.github.com, github.com, seatbelt, TF gateway, fireworks, the local hosts
  if ! echo "$NORM" | grep -qE '(api\.github\.com|github\.com|raw\.githubusercontent\.com|<model-gateway>|<model-gateway>|<llm-gateway>.truefoundry.cloud|api\.fireworks\.ai|api\.anthropic\.com|localhost|127\.0\.0\.1)'; then
    block "curl/wget to a non-allowlisted host — potential exfil"
  fi
fi

# Not blocked — allow the tool call
exit 0
