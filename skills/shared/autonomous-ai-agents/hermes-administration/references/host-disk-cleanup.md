# Reclaiming disk on a Hermes host

A full disk makes `hermes update` hang in I/O waits and breaks tempfile
creation ("No usable temporary directory"). Free space before retrying an
update; do not kill a mid-flight updater unless it is clearly dead.

## Procedure
1. `df -h /` for the real total, then `du -xh --max-depth=2 ~ | sort -h | tail`
   for home-tree hogs.
2. If `du` of `/` is well below `df` used, the gap is almost always outside
   home: Docker (`docker system df`) or a local database server. Check
   `sudo du -sh /var/lib/postgresql /var/lib/docker /var/lib/containerd`
   before anything else. Deleted-open files are rare; `lsof +L1` only to
   confirm.
   - Postgres bloat from test fixtures: count DBs by prefix
     (`select count(*) from pg_database where datname like 'orch_test_%'`).
     Integration suites that mint a DB per run and never drop it can leave
     1000+ x ~8MB DBs. List non-fixture DBs first and keep them; drop the
     fixture set in a loop (`psql -t -A -c "select datname ..." > list;
     while read db; do psql -q -c "DROP DATABASE IF EXISTS \"$db\""; done`).
     Report that it will regrow unless the suite's teardown drops its DB.
3. Confirm protected scope with the user before deleting (e.g. an active
   project repo and its live task worktrees). Ask once, then act.
4. Safe targets, roughly largest first:
   - Docker: `docker system prune -a --volumes -f` if the host no longer
     needs containers (ask).
   - Agent git worktrees (`.worktrees/`, `.orchestrate-worktrees/`): each
     carries its own `node_modules`, so many worktrees dwarf the repo. Keep
     ones with commits younger than a week; remove others via
     `git worktree remove --force` + `git worktree prune`. Worktree parent
     dirs like `feat/` and `fix/` are containers; inspect children.
   - Package caches: `~/.npm`, `~/.npm/_npx`, `~/.cache/uv`, pip caches.
   - Hermes: old `~/.hermes/state-snapshots/*`, stale `~/.hermes/installs/*`
     copies, orphaned `~/.hermes/tasks/<id>` workspaces whose id is not on the
     kanban board, sessions older than a week (files plus `state.db` rows).
   - Kanban board workspaces (`~/.hermes/kanban/boards/<slug>/workspaces/<task>`):
     look up each big one's task status in `kanban.db` (read-only); delete
     `done`/`archived` ones, keep anything `running`/`review`/`blocked`.
   - Recovery leftovers (corrupt-DB forensics copies, recovery scratch dirs):
     keep until the user confirms the recovered data looks right, then offer
     to drop them in the same report rather than leaving them indefinitely.
5. Re-run `df -h /` and report before/after plus what was kept.

## Agent scratch and one-off files (/tmp and home dir)
Agent sessions leave repo copies, mktemp dirs, probe scripts, batch
JSON/CSV/log outputs and research dumps in `/tmp` and directly in `~`. When
the user asks to clear "tmp one-off files / random logs", audit both hosts
(remote box and Mac) in one pass:
1. Size it: `du -sh /tmp/* | sort -rh | head -20` and a count of flat files
   older than two days (`find /tmp -maxdepth 1 -type f -mtime +2`). On macOS
   use `/private/tmp`.
2. Build the keep list from live processes first: `lsof +D <dir>` and
   `ps aux | grep <dir>` for each big dir, plus logs of running dev servers
   and watchers. Anything held open stays; a dev server running from a real
   repo path (not /tmp) is unaffected.
3. Big dirs are usually stale repo copies from review/mutation rounds
   (`build-*`, `*-baseline`, `tmp.XXXX`) and Claude Code's per-user temp dir
   (`/tmp/claude-<uid>`, can hold an orphan venv). Delete when nothing holds
   them.
4. Flat files: `find /tmp -maxdepth 1 -type f -mtime +2 ! -name <live> ...
   -delete`, excluding each live file by name.
5. Home-dir loose files (`~/*.py|json|md|txt|log|csv|sh`): list with age and
   size, then classify. Delete batch artifacts, watcher scripts and research
   dumps. A doc whose canonical copy lives in a tracked repo is a stale
   duplicate; delete the home copy. Keep files referenced by skills, memory
   or docs (grep for the filename) such as setup scripts for another machine.
6. Report per-host: before/after `/tmp` size, `df -h /` free, categories
   deleted, and the explicit keep list with why.

## Retiring a finished project (board, worktrees, sessions)
When the user says a project is done ("remove X-related files, kanban
board, code"), sweep every host that may hold it, not just the one in
focus:
1. Find the board: `ls ~/.hermes/kanban/boards/` and `_archived/` on each
   host. Read task status counts from `kanban.db` read-only; an open
   `review`/`running` task gets named in the report, not silently dropped.
2. Repoint the active board BEFORE removing it: grep `config.yaml` for the
   board slug (`current_board:` and any other refs) and rewrite
   `~/.hermes/kanban/current` to a live board. A dangling pointer makes
   kanban CLI/dashboard resolve a missing board.
3. Remove: hard-delete an already-archived board dir; for a live board,
   move it into `_archived/<slug>-<epoch>` unless told to delete, and offer
   the hard delete in the report.
4. Same pass: kill long-lived tmux sessions/Claude workers whose task is
   done/blocked or whose cwd is a deleted worktree (the session reaper only
   evicts in-gateway sessions, not external tmux panes), then remove the
   project's repo copies and worktrees, keeping one clean main checkout if
   the user wants it.
5. Leave unrelated boards untouched and list what remains per host.

If an out-of-band cleanup request arrives mid-task, finish and report the
in-flight task first in one line, then start the audit.

## Pitfalls
- Never run `pkill -f <pattern>` inside an `ssh host '...'` command string: the pattern also
  matches the remote shell running your own command line, so it kills the session and every
  later step silently never runs. Use `pgrep -f` to list PIDs, filter out `$$`, then kill by PID,
  or run the kill as its own separate SSH call. Re-check state after any SSH exit 255.
- Docker reclaim: run `docker system df` and `docker ps` first. Keep any image backing a running
  container (e.g. the browser backend); prune only build cache (`docker builder prune -af`) and
  volumes with zero active users, listing their names before `docker volume rm`.
- Memory reclaim pairs with disk: finished tmux sessions often hold headless chrome swarms
  (dozens of processes). Kill the session, the orphan agent PIDs, then the chromes, and report
  `free -h` before/after alongside `df -h /`. Verify gateway/dashboard `is-active` and crons
  after the sweep.
- T2 worktrees are not auto-removed at task completion; expect accumulation.
- Kanban/session DB size comes from event and message history, not artifacts;
  pruning old sessions shrinks it, deleting worktrees does not.
- `state.db` growth is mostly compaction-archived rows (`messages.active = 0`):
  the model reads only `active = 1`, so deleting old `active = 0` rows beyond
  the newest N per session (keep every `_compressed_summary = 1` row) loses no
  model context and shrinks `/resume` payloads. Use a window function
  (`ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY id DESC)`); a
  correlated subquery per row times out on large DBs. Put it in the weekly
  hygiene script, not a one-off.
- Native session retention: `sessions.auto_prune: true`,
  `sessions.retention_days` (default 90) and `sessions.auto_archive: true`.
  For an immediate sweep use `hermes sessions prune --older-than <N>d --yes`
  (only ended sessions are touched).
