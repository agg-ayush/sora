#!/bin/bash
# Render compositions: ./render.sh [Composition...]  (default: Launch)  -> out/<C>.mp4
#
# Bundles once, renders every composition from that bundle, and always deletes it. All Remotion temp
# files go into one private dir (TMPDIR=$WORK) removed on EXIT, INT, TERM and HUP. The Remotion CLI
# alone does not clean up on SIGTERM. SIGKILL cannot be trapped.
set -e
cd "$(dirname "$0")"
[ $# -ge 1 ] || set -- Launch
mkdir -p out

WORK=$(mktemp -d "${TMPDIR:-/tmp}/remotion-webpack-bundle-run.XXXXXX")
CHILD=

kill_tree() {
  local p
  for p in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$p"; done
  kill -TERM "$1" 2>/dev/null || true
}
cleanup() {
  trap - EXIT
  [ -n "$CHILD" ] && kill_tree "$CHILD"
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'cleanup; exit 143' INT TERM HUP

# Run in the background and wait, so a signal reaches the trap immediately instead of after the child.
run() { "$@" & CHILD=$!; wait "$CHILD"; local rc=$?; CHILD=; return $rc; }

BROWSER_ARGS=()
[ -f .browser ] && BROWSER_ARGS=(--browser-executable="$(cat .browser)")

TMPDIR="$WORK" run npx remotion bundle src/index.ts --out-dir="$WORK/bundle" --log=warn
for C in "$@"; do
  TMPDIR="$WORK" run npx remotion render "$WORK/bundle" "$C" "out/$C.mp4" --concurrency=8 --crf=16 --audio-bitrate=256k "${BROWSER_ARGS[@]}"
done
