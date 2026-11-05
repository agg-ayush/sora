# Claude Code user skills

`CLAUDE_SKILLS_ONLY=true bash devbox/setup-hermes.sh` links every directory here with a `SKILL.md` into `~/.claude/skills` and keeps the seatbelt `skills` link pointed at it. Existing real skill directories are moved to `~/.hermes/cache/<name>-<timestamp>-<suffix>/<name>` before replacement. The Claude-only mode does not modify Hermes skills, plugins, settings, or running services.

`ui-flow`, `graphify`, and `task-observer` are user-authored. `composition-patterns`, `react-best-practices`, and `web-design-guidelines` are installed Vercel skill snapshots; `ui-styling` is an installed ClaudeKit snapshot; `ui-ux-pro-max` and `impeccable` are third-party snapshots. Their license and attribution files are retained. These snapshots are intentionally versioned in this repo, so an upstream update cannot silently create cross-host drift.

`brainlift` is **not copied here**: the setup script links `~/.claude/skills/brainlift` directly to `~/repos/public_skills/brainlift`, cloning `https://github.com/<stakeholder>/public_skills` if absent. Keep that vendored skill in its upstream checkout. The remote's separate `~/.hermes/claude-k3-config` is not changed by the setup script.
