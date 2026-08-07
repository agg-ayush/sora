# Hermes Tier Setup

Custom Hermes Agent tier orchestration: plugin, skills, scripts, reference docs,
and config templates for the multi-tier autonomous coding pipeline.

## Structure

```
plugin/     claude-orchestrate plugin (pure tmux session manager)
plugins/    pr-review-toolkit patches (state-transition-reviewer specialist)
skills/     tier1-suborchestration + tier2-orchestration skills
scripts/    kanban-review.py (status transitions) + orphan-reaper.py (self-healing watchdog)
docs/       hermes-tiers-reference.md (canonical architecture) + audit reports
config/     config.yaml.template, env.template, zshrc-snippet.sh (NO secrets)
```

## Install (new machine)

```bash
git clone git@github.com:agg-ayush/hermes-tier-setup.git ~/hermes-tier-setup

# 1. Plugin → symlink into Hermes plugins
ln -sf ~/hermes-tier-setup/plugin ~/.hermes/plugins/claude-orchestrate

# 1b. pr-review-toolkit patch → copy the state-transition-reviewer into the
# Claude Code plugin cache (adds the specialist + wires it into review-pr)
cp ~/hermes-tier-setup/plugins/pr-review-toolkit/agents/state-transition-reviewer.md \
   ~/.claude/plugins/cache/claude-plugins-official/pr-review-toolkit/*/agents/
cp ~/hermes-tier-setup/plugins/pr-review-toolkit/commands/review-pr.md \
   ~/.claude/plugins/cache/claude-plugins-official/pr-review-toolkit/*/commands/

# 2. Skills → symlink into Hermes skills
mkdir -p ~/.hermes/skills/autonomous-ai-agents
ln -sf ~/hermes-tier-setup/skills/tier1-suborchestration ~/.hermes/skills/autonomous-ai-agents/
ln -sf ~/hermes-tier-setup/skills/tier2-orchestration ~/.hermes/skills/autonomous-ai-agents/

# 3. Scripts → symlink into Hermes scripts
mkdir -p ~/.hermes/scripts
ln -sf ~/hermes-tier-setup/scripts/kanban-review.py ~/.hermes/scripts/
ln -sf ~/hermes-tier-setup/scripts/orphan-reaper.py ~/.hermes/scripts/

# 4. Config — copy templates and fill in
cp ~/hermes-tier-setup/config/config.yaml.template ~/.hermes/config.yaml
cp ~/hermes-tier-setup/config/env.template ~/.hermes/.env
# edit ~/.hermes/.env with real API keys

# 5. Shell aliases — add holo function to ~/.zshrc
cat ~/hermes-tier-setup/config/zshrc-snippet.sh >> ~/.zshrc
source ~/.zshrc

# 6. Kanban boards — bind each repo to its board (adjust paths for your machine)
hermes kanban boards create alpha-learn-content-gen
hermes kanban boards set-default-workdir alpha-learn-content-gen /path/to/your/content-repo
hermes kanban boards create learning-app
hermes kanban boards set-default-workdir learning-app /path/to/your/app-repo

# 7. Gateway service
hermes gateway setup   # configure Telegram etc.
hermes gateway install
hermes gateway start

# 8. Cron — orphan reaper (every 30 min)
# Create via the cronjob tool or:
hermes cron add "30m" --script ~/.hermes/scripts/orphan-reaper.py --no-agent

# 9. (Optional) Mobile dashboard — amux's phone-accessible control plane.
# Runs alongside the tier system (separate tool, not replacing it). Gives you
# a phone-accessible web dashboard to monitor/steer the tmux sessions the tier
# system spawns. Install amux separately if you want mobile access:
#   git clone https://github.com/mixpeek/amux && cd amux && ./install.sh
#   amux serve   # → https://localhost:8822 (phone-accessible)
# Note: amux runs its own control plane (its own kanban, its own dashboard) —
# it's a separate tool for mobile monitoring, not a replacement for the tier
# system's kanban/orchestration. The tier system's kanban + dashboard remain the
# source of truth; amux's dashboard is a mobile-accessible view over the same
# tmux sessions.
```

## Usage

```bash
holo 1      # start Tier-1 (per-repo dispatcher)
holo 2      # start Tier-2 (per-issue supervisor, usually spawned by T1)
holo dash   # open the web dashboard (localhost:9119)
```

## Self-healing watchdog

The `orphan-reaper.py` cron (every 30 min) doesn't just kill idle sessions — it
**heals recoverable failure modes** before considering a session idle:

- **Context compaction prompt** → auto-answer "y" (compact the conversation)
- **`redacted_thinking` corruption** → kill + supervisor respawns (targeted kill)
- **Rate-limit prompt** (`/rate-limit-options`) → auto-press option 1 (stop + wait)
- **Stuck prompt** (y/n question) → auto-answer "y" (proceed)

Only kills genuinely idle sessions (no active work, no recoverable failure, no
prompt to answer). Never kills an actively-working session or a session at a
prompt waiting for a steer.

See `docs/hermes-tiers-reference.md` for the full architecture reference.
