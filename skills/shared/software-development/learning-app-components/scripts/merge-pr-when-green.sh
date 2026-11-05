#!/usr/bin/env bash
# Wait for a PR's CI checks to complete, then merge (squash + delete branch)
# ONLY if every check is green. Exit non-zero with a clear message otherwise.
#
# Usage:
#   merge-pr-when-green.sh <pr-number> [--repo owner/name] [--interval 10]
#
# Requires: gh CLI authenticated against the repo.
# Determinism: parses gh pr checks --json state for ALL checks; merges only
# when every state is SUCCESS/pass. Any fail/pending/cancel/skipping -> no merge.

set -euo pipefail

PR=""
REPO_FLAG=""
INTERVAL=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_FLAG="--repo $2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    *) PR="$1"; shift ;;
  esac
done

if [[ -z "$PR" ]]; then
  echo "Usage: $0 <pr-number> [--repo owner/name] [--interval 10]" >&2
  exit 64
fi

GH="gh $REPO_FLAG"

# Wait for all checks to reach a terminal state (pass/fail/cancel).
# gh pr checks --watch blocks; its exit code is unreliable (returns 0 on
# failures), so we only use it to block, then re-read the final state as JSON.
echo "Waiting for PR #$PR checks to complete (interval ${INTERVAL}s)..."
$GH pr checks "$PR" --watch --interval "$INTERVAL" >/dev/null 2>&1 || true

# Read the final state of every check. (No mapfile — macOS ships bash 3.2.)
STATES_JSON=$($GH pr checks "$PR" --json state 2>/dev/null || echo "[]")
STATES=$(printf '%s' "$STATES_JSON" | /usr/bin/python3 -c 'import json,sys; [print(s["state"]) for s in json.load(sys.stdin)]' 2>/dev/null || true)

if [[ -z "$STATES" ]]; then
  echo "error: no checks found for PR #$PR (is CI configured?)" >&2
  exit 70
fi

PASSING=0
FAILING=0
PENDING=0
while IFS= read -r s; do
  [[ -z "$s" ]] && continue
  case "$s" in
    SUCCESS|pass|PASS) PASSING=$((PASSING+1)) ;;
    FAIL|fail|FAILURE|ERROR|CANCELLED|cancel|SKIPPED|skip|NEUTRAL) FAILING=$((FAILING+1)) ;;
    PENDING|pending|QUEUED|queued|IN_PROGRESS|starting|WAITING) PENDING=$((PENDING+1)) ;;
    *) echo "unrecognized check state: $s" >&2; FAILING=$((FAILING+1)) ;;
  esac
done <<< "$STATES"

echo "checks: $PASSING passed, $FAILING failed/not-green, $PENDING still pending"

if [[ "$PENDING" -gt 0 ]]; then
  echo "error: $PENDING check(s) still pending after watch — not merging" >&2
  exit 75
fi
if [[ "$FAILING" -gt 0 ]]; then
  echo "error: $FAILING check(s) not green — NOT merging PR #$PR" >&2
  exit 1
fi

# All green. Confirm mergeable, then merge.
MERGEABLE=$($GH pr view "$PR" --json mergeable --jq '.mergeable' 2>/dev/null || echo "UNKNOWN")
if [[ "$MERGEABLE" != "MERGEABLE" ]]; then
  echo "error: PR #$PR mergeable state is '$MERGEABLE' (needs MERGEABLE) — not merging" >&2
  exit 76
fi

echo "All checks green and PR is mergeable. Merging PR #$PR (squash, delete branch)..."
$GH pr merge "$PR" --squash --delete-branch
echo "Merged PR #$PR."
