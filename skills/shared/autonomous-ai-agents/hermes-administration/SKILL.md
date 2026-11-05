---
name: hermes-administration
description: Administer Hermes hosts, skills, sessions and plugins.
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, admin, skills, cli, memory]
---

# Hermes Administration

## When to Use

Administer or audit a Hermes host, cross-host setup, skills, memory, sessions, plugins, routing, MCP, gateway or scheduled jobs. Load the matching reference below before acting; check current Hermes CLI/help or official docs for version-dependent facts.

## Operating rules

- Use native config/extension seams before modifying installed Hermes source. For a genuine upstream bug, inspect current upstream fixes and request approval for a local source patch; use targeted tests and track any approved local modification in the setup repo. A deliberate subsystem replacement may use an out-of-tree plugin. Never restart the process hosting the current chat without warning and approval.
- A configuration experiment is complete only when exact requested keys were changed, read back on each named host and tested live. On a model change preserve exact provider/model IDs and requested roles; do not cross billing groups or silently alter auxiliary/reviewer models. A green reply can come from fallback: confirm the serving provider and fallback events in logs/session usage. See `references/model-routing-and-latency.md` and `references/model-alias-troubleshooting.md`.
- Do not serialize an already redacted config object back into `config.yaml`: masked secrets can overwrite real values. Keep credentials in `.env` and reference them by variable, prefer `hermes config set` for supported keys, back up before direct edits and check edited secrets *without printing values*. A provider config change may not reach existing sessions; confirm fresh-session behavior.
- Process command lines and environment can expose keys. Never dump raw `ps eww`, full process argv or `.env` into a transcript. Before recommending rotation, determine whether a key reached a different principal or shared log; local same-user visibility alone is not new exposure.
- Run risky failover probes against an isolated scratch `HERMES_HOME` on the Mac, never the live remote gateway. Remove secret-bearing scratch copies afterward. Test optional dependencies with Hermes's venv interpreter, not bare system Python. On a copied config, check for host-specific absolute paths before restarting anything.
- A plugin/skill edit is not live merely because disk content changed: diff the source, tracked repo and runtime plugin, rerun the failing probe, and compare process start to plugin mtime when the old exception persists. Ask before restarting the process that owns this conversation.
- For UI/display and TUI keybinding questions, inspect actual CLI docs/help or source; do not invent hotkeys. The preference is thinking hidden while tool activity remains visible. Busy-input `interrupt|queue|steer` and `/queue` are different controls; verify current behavior before proposing a toggle.
- A dashboard feature may be plugin-provided rather than in the dashboard's App source. On `cannot import name` after an update, test a fresh venv import before blaming install corruption; restart only the stale process, not an unrelated gateway.
- Host audits: for every cron, watchdog or plugin proposed for removal/repair, say what it reads/writes, last success/failure and whether its target project remains active. Scope first: identify whether a warning belongs to a host, a task card or a live session. Avoid deleting a live user's process. See `references/host-disk-cleanup.md`, `references/stale-notification-triage.md`.
- Before relying on cron, check `hermes cron status`/gateway ticker. Updates may restart gateway/TUI; inspect `hermes update --plan`, preserve local diffs and verify installed version, scripts and services afterward. Don't launch updates as a side effect of answering whether one is worthwhile.

Additional detailed host-specific rules: `references/administration-operational-rules.md`.

## References by task

- Skill inventory, provenance, imports, cross-host hash reconciliation: `references/hermes-skill-library-management.md`. Repo-tracked skill linking and third-party provenance: `references/skill-repo-sync.md`.
- Memory classification, multi-host dedupe, separator pitfalls: `references/hermes-memory-hygiene.md`, `references/memory-consolidation-pitfalls.md`. External provider, per-host defaults and verification: `references/external-memory-provider-multihost.md`.
- Persistent CLI/tmux and task supervision: `references/hermes-session-cli-launch.md`. SQL live-WAL reads and DB recovery: `references/sqlite-wal-reads.md`. Recent-session friction audit: `references/recent-session-friction-audit.md`.
- Model switching, aliases, cost, fallbacks and attribution: `references/model-routing-and-latency.md`, `references/model-alias-troubleshooting.md`.
- MCP: `references/mcp-server-setup.md` plus remote OAuth handoff `references/mcp-server-oauth-setup.md`.
- Gateway, Telegram conflicts and pairing: `references/gateway-telegram-troubleshooting.md`; alert and cron triage: `references/stale-notification-triage.md`.
- Install/update review: `references/hermes-update-review.md`; remote migration: `references/remote-backend-migration.md`; disk and stale task cleanup: `references/host-disk-cleanup.md`.
- Claude Code config parity: `references/claude-code-config-parity.md`; desktop plugin operations: `references/hermes-desktop-plugins.md`.

## Verification

Read back exactly the changed target on the affected host, then exercise a live, non-destructive probe. A disk diff, CLI exit 0, status label or subagent self-report alone is not proof. Do not claim both hosts are in sync until file hashes and behavior match on both.
