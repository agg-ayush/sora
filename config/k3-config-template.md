# kimi-k3 isolated config template — copy to ~/.hermes/claude-k3-config/ and fill in.
# This is the Claude Code config for kimi-k3 sessions (routed via Fireworks).
# The plugin sets CLAUDE_CONFIG_DIR=~/.hermes/claude-k3-config/ for the fireworks path.
#
# Copy the user's real Claude Code settings + skills + plugins, with the
# TF-gateway env vars removed (the plugin overrides ANTHROPIC_BASE_URL +
# ANTHROPIC_AUTH_TOKEN to Fireworks).

# settings.json — merge the user's real settings minus the TF-gateway env vars.
# Keep skipDangerousModePermissionPrompt. The plugin pre-seeds .claude.json
# (onboarding + API-key approval) on first run.
{
  "env": {
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
    "OPENAI_API_KEY": "",
    "CLAUDE_API_KEY": "",
    "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
    "GEMINI_API_KEY": "",
    "FIREWORKS_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "LESSON_ROOT_DIR": "/path/to/your/lessons",
    "ATHENA_UPLOAD_USERNAME": "",
    "ATHENA_UPLOAD_PASSWORD": "",
    "GRAPHQL_ENDPOINT": "",
    "AWS_USER_POOLS_WEB_CLIENT_ID": ""
  },
  "skipDangerousModePermissionPrompt": true
}

# CLAUDE.md — copy the user's global CLAUDE.md (comment conventions, never-commit-to-main, etc.)
# cp ~/.claude/CLAUDE.md ~/.hermes/claude-k3-config/CLAUDE.md

# skills/ — copy the user's Claude Code skills
# cp -R ~/.claude/skills ~/.hermes/claude-k3-config/skills

# plugins/ — copy the user's Claude Code plugins
# cp -R ~/.claude/plugins ~/.hermes/claude-k3-config/plugins
