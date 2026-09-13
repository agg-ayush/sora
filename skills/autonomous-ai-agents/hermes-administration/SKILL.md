---
name: hermes-administration
description: "Administer Hermes: skills, memory hygiene, CLI launch."
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [hermes, admin, skills, cli, memory]
---

# Hermes Administration

Umbrella for administering a Hermes install: auditing/pruning the skill library, keeping global memory clean and correctly scoped, launching persistent skill-preloaded sessions via tmux, and writing desktop plugins.

## When to Use

- Asked to audit/prune/enable/disable Hermes skills, find dead-weight skills, or install from the catalog.
- Hermes memory is full or near capacity; asked "what's in memory", "split memory per repo", or "clean up memory without losing anything".
- Spawning a durable background Hermes session (tier1→tier2 handoff, any detached interactive worker) via tmux.
- Building a desktop-app UI pane, statusbar widget, command, or theme without modifying the app itself.

## Procedure

### Skill library management (references/hermes-skill-library-management.md)

Cross-reference three sources before recommending any change:
1. **Enabled/disabled state** — `hermes skills list` or `skills.disabled` in `~/.hermes/config.yaml`.
2. **Usage telemetry** — `~/.hermes/skills/.usage.json` (`use_count`, `last_activity_at`). Zero `use_count` + stale `last_activity_at` is the strongest "not useful" signal.
3. **Full catalog** — installed + the optional catalog from the Hermes skills-catalog docs.

Present findings as three buckets (enabled-but-unused, useful-but-missing, healthy-keep) and let the user pick per-item — don't blanket-cut.

**Applying changes:** `hermes skills config` is interactive-only (no `--disable` flag). Edit `skills.disabled` in `~/.hermes/config.yaml` directly — and it MUST be a YAML **list**, not a comma string. `hermes config set skills.disabled "a,b,c"` looks like it worked but writes a string that silently disables nothing. Write via Python `yaml.safe_load`/`safe_dump`, then verify the type:

```bash
python3 -c "import yaml; d=yaml.safe_load(open('/Users/ayush/.hermes/config.yaml')); v=d['skills']['disabled']; print(type(v).__name__, len(v))"
# expect: list N
```

Install non-interactively: `echo "y" | hermes skills install official/<category>/<name>` (no `--yes` flag exists).

**Verify after any batch:** re-run `hermes skills list` and grep the exact names — don't trust the `config set` success message.

### Memory hygiene (references/hermes-memory-hygiene.md)

Don't just raise the limit or prune blindly. Classify each entry:
- **Keep in global memory:** standing workflow preferences, cross-repo infra topology, user identity/role, durable lessons about how the agent should operate generally.
- **Migrate to a repo context file (`.hermes.md` or `AGENTS.md`):** repo build/test/lint commands, repo conventions, machine-specific toolchain quirks, infra detail specific to one box. `.hermes.md` walks up from cwd to the git root (use for repo-wide or home-wide facts); `AGENTS.md` is cwd-only but also read by Claude Code/Codex/Cursor (use for repo-root conventions other tools should see). Git-exclude via `.git/info/exclude`, never `.gitignore`.
- **Drop entirely (no persistent store):** active task state — in-flight migrations, current fix plans, ticket numbers. Looks repo-scoped but goes stale the moment the task ends; leave for `session_search` to recover.

Compact-in-place when everything belongs globally but is verbose: group by topic under headers, strip narrative to the rule, one batched `memory(operations=[...])` call. Verify with `hermes memory status`.

### Persistent session CLI launch (references/hermes-session-cli-launch.md)

Correct tmux invocation for a detached, skill-preloaded Hermes worker:

```bash
tmux new-session -d -s <session-name> -x 200 -y 50 'hermes chat -s <skill-name> --tui'
```

`-s <skill-name>` is a flag of the **`chat` subcommand**, not top-level `hermes` — `hermes -s <skill>` parses but is NOT the interactive chat path and silently misbehaves. See the reference for wedged-session recovery, `steer` no-op on finished sessions, and the T2 dispatch-discipline rule (a supervisor never hand-edits target-repo code — dispatch via `claude_orchestrate` for the full lifecycle).

### Desktop plugins (references/hermes-desktop-plugins.md)

Create `$HERMES_HOME/desktop-plugins/<name>/plugin.js` from the skill's `templates/plugin.js` — plain-JS ESM, no build step. The app watches that directory and hot-reloads on save (fallback: ⌘K → **Reload desktop plugins**). Import surface is only `@hermes/plugin-sdk` + `react` (use `jsx()` calls, no JSX syntax). Full API in the reference.

## Pitfalls

- `skills.disabled` written as a comma-joined string — silently disables nothing; always write a YAML list and verify the type.
- Assuming a named profile's config lives under `~/.hermes/profiles/<name>/config.yaml` — that file may not exist; check `hermes config path` before editing.
- Migrating active task state ("currently porting X", a PR number) into a repo context file — that's transient, not durable, and misleads the next session. Drop it, don't migrate it.
- Editing `.git/info/exclude` without verifying — a typo silently no-ops; always `git check-ignore -v <file>`.
- Launching `hermes -s <skill>` (no `chat`) in tmux — accepted by argparse but not the interactive session you meant to spawn.
- Trusting a `config set` success message as proof the change took — re-list and grep.

## Verification

- Skill library: `hermes skills list` shows the exact enabled/disabled state intended; `.usage.json` cross-checked.
- Memory: `hermes memory status` usage drops; migrated facts land in the right context file; `git check-ignore -v` confirms exclusion.
- Session launch: `tmux ls` shows the detached session; the pane is running `hermes chat` interactively with the skill preloaded.
- Desktop plugin: appears in the app within seconds of save; no error toast.

## References

- `references/hermes-skill-library-management.md` — full audit workflow, string-vs-list bug transcript.
- `references/hermes-memory-hygiene.md` — full classification table, context-file discovery rules, migration batching.
- `references/hermes-session-cli-launch.md` — full tmux/tmux-recovery runbook, T2 lifecycle pitfalls.
- `references/hermes-desktop-plugins.md` — full plugin API surface.
- `references/audit-session-example.md` — worked real audit-and-apply transcript.
