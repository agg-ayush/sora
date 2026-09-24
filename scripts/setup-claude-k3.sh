#!/usr/bin/env bash
# Wire Claude Code to use Kimi K3 via Fireworks on this machine.
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

# .claude.json — minimal config
cat > "$K3_DIR/.claude.json" << 'EOF'
{
  "env": {}
}
EOF

# CLAUDE.md — global rules for K3 sessions
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

# settings.json — minimal settings
cat > "$K3_DIR/settings.json" << 'EOF'
{
  "model": "sonnet[1m]"
}
EOF

# Copy skills if the source exists
SKILL_SRC="$HERMES_HOME/skills"
if [ -d "$SKILL_SRC" ]; then
  for skill_dir in "$SKILL_SRC"/*/SKILL.md; do
    [ -f "$skill_dir" ] || continue
    skill_name=$(basename "$(dirname "$skill_dir")")
    mkdir -p "$K3_DIR/skills/$skill_name"
    cp "$skill_dir" "$K3_DIR/skills/$skill_name/"
  done
fi

echo "K3 config written to $K3_DIR"
echo ""
echo "To use K3 for a Claude Code session:"
echo "  export CLAUDE_CONFIG_DIR=$K3_DIR"
echo "  export ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference"
echo "  export ANTHROPIC_AUTH_TOKEN=\$(grep FIREWORKS_API_KEY $ENV_FILE | cut -d= -f2)"
echo "  export ANTHROPIC_API_KEY="
echo "  export ANTHROPIC_MODEL=accounts/fireworks/models/kimi-k3"
echo "  claude"
echo ""
echo "Or add this alias to your shell:"
echo "  alias claudek3='CLAUDE_CONFIG_DIR=$K3_DIR ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference ANTHROPIC_AUTH_TOKEN=\$(grep FIREWORKS_API_KEY $ENV_FILE | cut -d= -f2) ANTHROPIC_API_KEY= ANTHROPIC_MODEL=accounts/fireworks/models/kimi-k3 claude'"
