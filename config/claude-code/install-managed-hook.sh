#!/bin/sh
# Install the Claude Code managed hook that blocks the TrueFoundry LLM gateway.
# Must run as root (use sudo). Idempotent; merges into an existing
# managed-settings.json, never overwrites other keys or hooks.
#
#   Linux: /etc/claude-code/{managed-settings.json,hooks/block-truefoundry.sh}
#   macOS: /Library/Application Support/ClaudeCode/{managed-settings.json,hooks/block-truefoundry.sh}
set -eu

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$(uname -s)" = "Darwin" ]; then
  DEST="/Library/Application Support/ClaudeCode"
else
  DEST="/etc/claude-code"
fi
HOOK="$DEST/hooks/block-truefoundry.sh"
SETTINGS="$DEST/managed-settings.json"

if [ "$(id -u)" != 0 ]; then
  echo "install-managed-hook: must run as root: sudo sh $SRC_DIR/install-managed-hook.sh" >&2
  exit 1
fi

mkdir -p "$DEST/hooks"
cp "$SRC_DIR/block-truefoundry-hook.sh" "$HOOK.tmp"
chmod 755 "$HOOK.tmp"
mv -f "$HOOK.tmp" "$HOOK"

python3 - "$SRC_DIR/managed-settings.json" "$SETTINGS" "$HOOK" <<'PY'
import json, os, sys
tmpl_path, dest_path, hook = sys.argv[1:4]
tmpl = json.load(open(tmpl_path))
# Quote the path inside the command string (the macOS path contains a space).
for entries in tmpl["hooks"].values():
    for entry in entries:
        for h in entry["hooks"]:
            h["command"] = h["command"].replace("__HOOK_PATH__", '"%s"' % hook)
cur = {}
if os.path.exists(dest_path):
    try:
        cur = json.load(open(dest_path))
    except ValueError:
        sys.exit("existing %s is not valid JSON; refusing to overwrite" % dest_path)
hooks = cur.setdefault("hooks", {})
for event in list(hooks):
    # drop our previous entries (any event), keep everything else
    hooks[event] = [e for e in hooks[event] if "block-truefoundry" not in json.dumps(e)]
    if not hooks[event]:
        del hooks[event]
for event, entries in tmpl["hooks"].items():
    hooks[event] = hooks.get(event, []) + entries
tmp = dest_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(cur, f, indent=2)
    f.write("\n")
os.chmod(tmp, 0o644)
os.replace(tmp, dest_path)
PY
echo "install-managed-hook: installed $HOOK and updated $SETTINGS"
