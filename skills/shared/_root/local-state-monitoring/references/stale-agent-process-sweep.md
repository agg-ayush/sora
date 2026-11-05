# Stale agent process / host-clutter sweep

Use when asked "any long-lived T2/T3 or anything that should be dead?", "clean up tmp/one-off files", or a host feels memory-heavy.

## Why things linger (explain this when asked "why didn't the reaper catch it")
- Hermes's TUI-gateway reaper (`tui_gateway/session_reaper.py`, TTL = `session_ttl_seconds`, default 12h) only evicts agent sessions held in the gateway's own memory. It never kills OS processes.
- Interactive `hermes chat --tui` instances, tmux-wrapped T2s and `claude_orchestrate` Claude/Codex panes are separate OS processes. Only the tier system (T1 watcher, claim TTL) or a human ends them. If the supervising watcher dies first, the child lives forever.
- A gateway restart drops its in-memory sessions but leaves sibling processes running.

## Procedure
1. Inventory: `tmux list-sessions`, then inspect process PID, elapsed time and RSS with host-supported `ps` flags (Linux/macOS syntax differs); redact tokens from process arguments.
2. For each candidate, collect three liveness signals:
   - age (`etime`), plus the last activity in its pane (`tmux capture-pane -p -t <s>`).
   - cwd: On Linux inspect `/proc/<pid>/cwd`; on macOS use `lsof -a -p <pid> -d cwd`. A deleted worktree indicates a stale external process.
   - owning kanban task status: query the board DB directly (`sqlite3 ~/.hermes/kanban/boards/<board>/kanban.db "select id,status,title from tasks where ..."`). Match by task id in the session name or by title. `done` means safe to kill.
3. Classify each entry as keep (gateway, the dashboard, servers bound to live ports, recent TUI sessions) or kill (task done, cwd deleted, idle for weeks). Present it as a table: session, age, task status, state.
4. Kill the process tree, then the tmux session. Remember the orphaned `node --expose-gc` TUI wrappers and stray `claude` children that survive `tmux kill-session`. Re-list processes afterwards and check that host-appropriate memory metrics show whether resources were reclaimed.
5. Leave the user's live interactive conversation alone, even if it is broken (for example a stale-module ImportError). Name the PID and give the relaunch command (`hermes chat --resume <id> --tui`). If the user has already said they can kill or restart it, give the command right away and stop investigating.

## Files and dirs (/tmp, home one-offs)
- Before deleting anything, check that no process holds it: `lsof +D <dir>` or check the process cwds from step 2. Keep the logs and state files of servers that are still listening (`ss -ltnp`).
- Repo worktrees: keep the one the user names (usually main), delete the rest and rename only when asked. Kill any worker cwd'd inside them first.
- Never delete a canonical working copy (for example a repo's docs) just because an older duplicate exists elsewhere. Confirm which copy is live by path and mtime.
- Run the same audit on the other host when the user says clutter exists on both.

## Durable fix
This class of leftover belongs to a periodic sweep in the tier watcher or a cron: flag `claude`/`node` processes whose cwd is deleted or whose kanban task is `done`. Don't rely on Hermes's reaper for it.
