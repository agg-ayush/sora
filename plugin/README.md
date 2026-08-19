# claude-orchestrate

Registers one tool, `claude_orchestrate`, for driving interactive Claude Code
sessions inside tmux. Requires `tmux` and `claude` on PATH.

## Actions

### `start`
Params: `task_id` (required), `prompt` (required), `workdir` (required),
`worktree` (optional — name of a git worktree+branch to create off `workdir`
and run in instead; omit to run in `workdir` directly), `dangerous` (bool,
default `true` — passes `--dangerously-skip-permissions`).

Refuses if a tmux session named `task_id` already exists. Writes
`prompt.md`/`status.md`/`meta.json` to
`C:/Users/Ayush/AppData/Local/hermes/tasks/<task_id>/`, launches `claude` in
a detached tmux session sized 160x50, and pipes the pane to `tmux.log` in
the artifact dir. The prompt is extended with an instruction for Claude to
write its phase (`investigating`/`implementing`/`testing`/`blocked`/
`complete`) to `status.md` and its final summary to `result.md`.

### `status`
Params: `task_id` (required), `tail` (int, default 60 — lines of pane to
capture). Returns whether the session is alive, the raw `status.md`
contents, the captured pane, a `❯`-prompt-based `waiting_for_input` guess,
and `done` (true once `status.md` == `complete`).

### `steer`
Params: `task_id` (required), `message` (required). Sends `message` into
the session literally, followed by Enter.

### `result`
Params: `task_id` (required). Returns `status.md`, `result.md`, and (if the
run dir is a git repo) `git status --porcelain` / `git diff --stat`.

### `stop`
Params: `task_id` (required), `keep_worktree` (bool, default `true`). Sends
`/exit`, waits briefly, then kills the tmux session. Artifacts are left on
disk. If `keep_worktree` is `false` and a worktree was created, it's removed
with `git worktree remove --force`.

### `list`
No params. Lists live tmux sessions with each one's `status.md` contents,
if an artifact dir exists for it.
