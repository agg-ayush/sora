#!/usr/bin/env bash
# Save a RED or GREEN test run as card evidence.
# Usage: capture-evidence.sh <red|green> <unit> [--task-dir DIR] -- <test command...>
# Writes <task-dir>/evidence/<kind>-<unit>.txt: first line the exact command, then the raw runner output.
# Task dir defaults to $HERMES_TASK_DIR. Exits with the test command's status, then checks the expectation:
# red must fail (exit 3 if it passed), green must pass.
set -uo pipefail

kind="${1:-}"; unit="${2:-}"
[ -n "$kind" ] && [ -n "$unit" ] || { echo "usage: $0 <red|green> <unit> [--task-dir DIR] -- <command...>" >&2; exit 64; }
shift 2
task_dir="${HERMES_TASK_DIR:-}"
if [ "${1:-}" = "--task-dir" ]; then task_dir="${2:-}"; shift 2; fi
[ "${1:-}" = "--" ] && shift
[ -n "$task_dir" ] || { echo "capture-evidence: set HERMES_TASK_DIR or pass --task-dir" >&2; exit 64; }
[ "$#" -gt 0 ] || { echo "capture-evidence: no test command given" >&2; exit 64; }
case "$kind" in red|green) ;; *) echo "capture-evidence: kind must be red or green" >&2; exit 64 ;; esac

mkdir -p "$task_dir/evidence"
out="$task_dir/evidence/$kind-$unit.txt"
printf '%s\n' "$*" > "$out"
"$@" 2>&1 | tee -a "$out"
status="${PIPESTATUS[0]}"

if [ "$kind" = red ] && [ "$status" -eq 0 ]; then
  echo "capture-evidence: RED run passed; the new tests do not fail on the unchanged code ($out)" >&2
  exit 3
fi
if [ "$kind" = green ] && [ "$status" -ne 0 ]; then
  echo "capture-evidence: GREEN run failed ($out)" >&2
  exit "$status"
fi
echo "capture-evidence: saved $out" >&2
exit 0
