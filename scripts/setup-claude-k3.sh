#!/usr/bin/env bash
# Wire Claude Code to use Kimi K3.1 Pro via Fireworks on this machine.
# Creates ~/.hermes/claude-k3-config/ and sets the env vars.
# Requires: claude CLI installed, ~/.hermes/.env with FIREWORKS_API_KEY.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
K3_DIR="$HERMES_HOME/claude-k3-config"
ENV_FILE="$HERMES_HOME/.env"

# Check prerequisites
command -v claude >/dev/null || { echo "claude CLI not found — install it first"; exit 1; }
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE — run hermes setup first"; exit 1; }
grep -q "FIREWORKS_API_KEY" "$ENV_FILE" || { echo "FIREWORKS_API_KEY not in $ENV_FILE"; exit 1; }

mkdir -p "$K3_DIR"

# Initialize JSON without dropping session history or plugin settings.
python3 - "$K3_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for name in (".claude.json", "settings.json"):
    path = root / name
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(f"expected a JSON object in {path}")
    if name == ".claude.json":
        data.setdefault("env", {})
    else:
        data["model"] = "accounts/fireworks/models/kimi-k3p1-pro"
        env = data.get("env", {})
        if not isinstance(env, dict):
            raise SystemExit(f"expected env to be an object in {path}")
        for key in (
            "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL",
            "ANTHROPIC_API_KEY_BACKUP", "BACKUP_ANTHROPIC_API_KEY",
        ):
            env.pop(key, None)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

# CLAUDE.md — seed defaults without overwriting existing or linked rules.
if [ ! -e "$K3_DIR/CLAUDE.md" ] && [ ! -L "$K3_DIR/CLAUDE.md" ]; then
  cat > "$K3_DIR/CLAUDE.md" << 'CLAUDEEOF'
# Global rules

- **Never commit directly to main.** Always work on a branch. Committing and pushing on non-main branches is fine without an explicit ask — but main is off-limits; open a PR instead.

- **Worktree branch naming.** After `EnterWorktree` creates a worktree, immediately rename the branch to follow conventional naming: `git branch -m <new-name>` where `<new-name>` uses a `fix/`, `feat/`, `chore/`, etc. prefix. The `EnterWorktree` tool hardcodes a `worktree-` prefix that must be stripped.

- **Subagents only for truly parallel work.** Execute sequential tasks inline in the main session — do not dispatch subagents for work you would do one-after-another anyway (they're slower and lack the session's context). Use subagents only when tasks are genuinely independent and can run concurrently.

- **Code comments: terse, present, necessary only.** Write a comment only when it explains something non-obvious about what the code currently does or why. Never reference issue/PR numbers, never narrate past/fixed behavior. When in doubt, prefer no comment over a noisy one.

- **Never commit tracking docs/plans into a PR.** Files like `docs/superpowers/plans/*` are internal-only — useful for me and future sessions, not for reviewers. Never `git add`/commit them as part of a PR's diff. Keep them as local uncommitted/untracked files instead.

- **AWS: use the `aws` CLI, never the shell's ambient IAM user.** For any AWS command, read or write, invoke it through the `aws` CLI explicitly.

- **Google Docs/Sheets/Slides/Drive/Gmail/Calendar: use `gog`, not a raw fetch.** These are gated behind OAuth, so a direct WebFetch/HTTP call will fail. Use `gog` (on PATH as `gog`) instead — it's authorized as ayushaggarwal018@gmail.com covering gmail, calendar, drive, docs, sheets, and slides.
CLAUDEEOF
fi

# Copy missing skills if the source exists; linked and existing files stay untouched.
SKILL_SRC="$HERMES_HOME/skills"
if [ -d "$SKILL_SRC" ] && [ ! -L "$K3_DIR/skills" ]; then
  for skill_dir in "$SKILL_SRC"/*/SKILL.md; do
    [ -f "$skill_dir" ] || continue
    skill_name=$(basename "$(dirname "$skill_dir")")
    mkdir -p "$K3_DIR/skills/$skill_name"
    skill_dest="$K3_DIR/skills/$skill_name/SKILL.md"
    [ -e "$skill_dest" ] || [ -L "$skill_dest" ] || cp "$skill_dir" "$skill_dest"
  done
fi

echo "K3.1 Pro config written to $K3_DIR"
echo ""
echo "To use K3.1 Pro for a Claude Code session:"
echo "  unset ANTHROPIC_CUSTOM_HEADERS ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY"
echo "  export CLAUDE_CONFIG_DIR=$K3_DIR"
echo "  export ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference"
echo "  export ANTHROPIC_AUTH_TOKEN=\$(grep FIREWORKS_API_KEY $ENV_FILE | cut -d= -f2)"
echo "  export ANTHROPIC_API_KEY="
echo "  export ANTHROPIC_MODEL=accounts/fireworks/models/kimi-k3p1-pro"
echo "  claude"
echo ""
echo "Or add this alias to your shell:"
echo "  alias claudek3='unset ANTHROPIC_CUSTOM_HEADERS ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY; CLAUDE_CONFIG_DIR=$K3_DIR ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference ANTHROPIC_AUTH_TOKEN=\$(grep FIREWORKS_API_KEY $ENV_FILE | cut -d= -f2) ANTHROPIC_API_KEY= ANTHROPIC_MODEL=accounts/fireworks/models/kimi-k3p1-pro claude'"
