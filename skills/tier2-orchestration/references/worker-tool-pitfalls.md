# Tier-2 worker tool pitfalls

- `kanban_create` may echo the current task's env `task_id`, not the newly
  created card's ID. Before recording `created_cards` in `kanban_complete`,
  read the board's `~/.hermes/kanban/boards/<board>/kanban.db` `tasks` table
  ordered by `created_at DESC` and identify the actual child card.
- In kanban-worker sessions, `tool_call` JSON payloads can be corrupted with
  `Expecting ',' delimiter` when a board/repo substring (e.g. `sign-sure`)
  appears twice in one call, or a `claude_orchestrate start` prompt contains
  `<kanban-task-id>...review` (such as a review brief path). Keep start prompts
  short: stage the brief at `~/.hermes/tasks/<session-id>/` and point to it;
  include the board substring at most once per payload. Use `steer` for long
  follow-ups. A worker's `hermes kanban` CLI refuses mutations; use the
  `kanban_*` tools instead.
- On the remote host's `gh` 2.45.0, `gh pr checks --json` is unsupported, so
  `pr-wait.py` fails. Use `gh pr checks <N> --watch --fail-fast` from the
  branch checkout. A detached HEAD also breaks `gh pr merge --delete-branch`.
- To steer a Tier-2 Hermes TUI in tmux, send the text and a separate
  `tmux send-keys ... Enter` call. Text plus Enter in a single send-keys
  call can leave the prompt unsubmitted; verify it cleared before waiting.
