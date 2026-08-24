---
name: background-task-polling
description: "Poll a local tmux/task dir on interval until terminal state."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [polling, tmux, background-jobs, monitoring, terminal]
    category: devops
    requires_toolsets: [terminal]
    related_skills: [watchers, hermes-session-cli-launch, tier2-orchestration]
---

# Background Task Polling

For polling a *local* thing (a tmux pane, a `~/.hermes/tasks/<id>/` status/outcome
file, a PID, a log file) on a fixed interval for a bounded duration until it
hits a terminal state. This is distinct from the `watchers` skill, which polls
*external* feeds/APIs with watermark dedup — no external fetch or dedup state
here, just "check local state every ~60s, stop when done or timed out."

## When to Use

- "Poll session `<name>` every ~60s for up to N minutes; report when it reaches
  a terminal state."
- Watching a coding-agent task dir (`~/.hermes/tasks/<task_id>/status.md` +
  `outcome.md`) for completion.
- Babysitting any long-running background command until it exits or a
  condition file changes.

## The pattern

1. **Never implement the sleep-loop in `execute_code`.** That tool has a hard
   ~5-minute cap. A loop doing `sleep 60` for 20+ minutes gets killed mid-run
   with no salvageable state. Write the polling loop as a real shell script on
   disk and run *that* via `terminal(background=true, notify_on_complete=true)`.

2. **Write the script with `write_file`, not an inline terminal heredoc.**
   `terminal()` rejects any command containing a trailing `&` used to
   background it — and critically, the rejection happens for the **entire**
   command string, so a `cat > script.sh <<EOF ... EOF; chmod +x script.sh;
   ./script.sh &` all-in-one call writes nothing at all, not even the heredoc
   part. Split into: (a) `write_file` the script, (b) `terminal` to `chmod +x`
   it, (c) `terminal(background=true)` to launch it — no `&`, no heredoc.

3. **Use a task-specific script + report filename, never a generic reused
   path** like `/tmp/poll.sh` or `/tmp/report.txt`. If a write to that path is
   ever skipped (e.g. via the `&`-rejection above, or a prior unrelated
   polling task left a script there), the OLD script at that path will
   silently execute instead of the new one — you'll get plausible-looking but
   wrong output. Before launching, `cat`/`head` the script file to confirm its
   content actually matches what you intended, especially if the path could
   have been reused across tasks.

4. **`process(action='wait', timeout=...)` is server-side clamped** — a
   request for e.g. `timeout=1800` can silently return after ~600s even though
   the background process is still running, with no error, just an early
   return. Don't treat one `wait` call as covering your full requested
   duration. Either issue repeated `wait`/`poll` calls until the process
   actually exits, or rely on `notify_on_complete=true` and check back — don't
   assume a single wait blocked for as long as you asked.

5. **Have the script write its own running report file**, one line per tick
   (elapsed time + observed state), plus a final summary block when it exits.
   Read that file back with `read_file` — don't try to reconstruct the poll
   history from `process(action='log')`, which only shows recent stdout and
   won't survive across multiple wait/poll calls cleanly.

6. **Terminal-state detection for a Hermes coding-task dir**: check
   `outcome.md`'s first line against the known tokens (`DONE`,
   `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`) **and independently**
   check whether the tmux session still exists (`tmux has-session -t <name>`).
   A session can crash (provider drop, uncaught exception) without ever
   writing an outcome token — `status.md` stuck on a non-terminal value like
   `implementing`, `outcome.md` still `PENDING`, tmux session gone. Treat that
   silent-crash combination as its own terminal state to report immediately
   (with the last known artifact contents and last pane snapshot), not as
   "still pending, keep waiting."

7. **When the polled pane is itself a Hermes CLI/TUI session (a T2/T3 you're
   watching from outside), don't keyword-match the whole pane for a "blocked"
   signal.** The Hermes TUI renders a persistent status-bar footer
   (`⚕ ❯ msg=interrupt · /queue · /bg · /steer · Ctrl+C cancel`) on every
   single frame regardless of what the session is doing — a naive regex like
   `waiting|interrupt|stuck` matches that chrome immediately and reports
   "blocked" on frame one even though the agent is actively working. Two
   fixes, use both: (a) restrict the blocked-regex to only genuinely
   ambiguous/approval phrases (`needs input`, `permission denied`,
   `\[y/N\]`, `\(y/n\)`, `proceed\?`, `authentication failed`) and explicitly
   exclude the known footer tokens; (b) when hashing recent pane lines to
   detect "quiet" (no progress), strip volatile UI chrome (percentages,
   elapsed timers, token counts, and the status-bar line itself) before
   hashing — otherwise a live spinner keeps the hash "changing" forever and
   masks real quiet, or the footer's static parts keep it "unchanged" and
   mask real progress underneath.

8. **Never name a shell variable `TMUX` when it holds the tmux binary path**
   (e.g. `TMUX=/opt/homebrew/bin/tmux`). `TMUX` is tmux's own reserved env var
   — inside an active tmux client it holds `socket_path,pid,session`, and if
   you overwrite it with a plain binary path, every subsequent
   `tmux has-session`/`tmux ls` call in that shell fails immediately with
   `error connecting to /opt/homebrew/bin/tmux (Socket operation on
   non-socket)`. In a polling loop this reads as "tmux session gone" on tick
   one, which combined with the outcome file still being `PENDING` produces a
   false CRASH terminal state and an incorrect report — even though the real
   tmux session is alive and progressing fine. Fix: name the variable
   something else (`TMUXBIN`) and `unset TMUX` at the top of the script before
   using it, or just call the plain `tmux` command relying on PATH instead of
   storing its path in a variable at all.

9. **`claude_orchestrate wait` can itself throw a plugin-side NameError**
   (observed repeatedly: `artifact_dir` NameError on the `wait` action,
   across multiple unrelated sessions/tasks — not a one-off). Don't treat one
   NameError as fatal or retry `wait` in a tight loop: fall back to polling
   the `status` action (or the on-disk `status.md`/`outcome.md` files
   directly) on an interval until terminal state, exactly as this skill
   already prescribes for the non-plugin case. Retry `wait` itself once after
   a delay — it sometimes clears — but don't depend on it clearing.

10. **A `claude_orchestrate` build variant may expose `outcome.md` (plain
    `PENDING`/`DONE`) alongside `status.md`, plus `start`-time params like
    `effort`, `executor`, `kanban_board`, `kanban_task_id`, `model_provider`.**
    When present, the `start` response includes `watcher_needed: true` —
    treat that as an explicit instruction to arm a watcher/poll loop
    immediately, not an optional hint. On this variant `wait` has been
    observed to hang; fall back straight to a plain terminal poll
    (`sleep N && cat <artifact_dir>/outcome.md <artifact_dir>/status.md`)
    against `~/.hermes/tasks/<task_id>/` until `outcome.md` reads `DONE`,
    same as the NameError fallback in point 9. Run
    `tool_describe(name='claude_orchestrate')` at the start of a session to
    check which param/response shape is actually live before assuming a
    prior session's shape still holds — this plugin varies per environment.

11. **A gate/verdict check reporting "impl fail" or "no diff found" right
    after a coding session reports done can be a false negative, not a real
    failure** — if the session committed its own work (`git commit` inside
    the run), the working tree is clean and there's no *uncommitted* diff to
    see, even though the change is real and present in `git log`. Before
    treating a fail-to-detect-changes signal as genuine, check
    `git log --oneline -3` and `git show --stat HEAD` in the run directory;
    if the expected commit is there, proceed and just note the false
    negative rather than re-dispatching the work.

12. **Squash-merged PRs make a still-checked-out pre-merge branch look "ahead"
    of the base by all its original commits**, even though their content is
    already on the base via one new squash commit. Symptom: you land one more
    small follow-up commit on the same branch, then `gh pr create`/diff
    against the base shows it trying to re-include everything from the
    already-merged PR. Fix — don't reuse the old branch:
    ```bash
    git fetch origin <base-branch>                        # pulls in the squash commit
    git checkout -b <new-branch> origin/<base-branch>      # fresh branch off updated base
    git cherry-pick <new-commit-sha>                       # only the genuinely new commit
    git log origin/<base-branch>..HEAD --oneline           # sanity check: just the new commit(s)
    git push -u origin <new-branch>
    gh pr create --base <base-branch> ...
    ```
    Find `<new-commit-sha>` by comparing `git show --stat` on your candidate
    commit against `git show --stat` on the squash commit — if its file diff
    isn't a subset of the squash commit's diff, it's genuinely new.

13. **A bare tmux session with no task-dir plumbing (no `status.md`/`outcome.md`,
    just an input file like `ids.txt`) gives you zero local artifact to fall
    back on if it dies.** If you're asked to watch `tmux capture-pane -t
    <name>` and the session vanishes (`tmux ls` shows no match, `capture-pane`
    errors "can't find pane"), first do ONE quick re-check after a short delay
    to rule out a transient tmux hiccup or session rename, and do a broad
    `find <task-dir-root> -newer <input-file>` sweep for any report/log the
    job might have been writing outside the obvious path. If both come back
    empty, that's the terminal state — report it immediately as
    "session disappeared, no recoverable local state" rather than continuing
    to sleep/re-poll for the rest of the requested duration on the hope it
    reappears; repeated 90–120s waits past the second confirmation just burn
    time without new information. Crucially: if the job was mutating an
    external system (S3 objects, CloudFront invalidations, a DB), say
    explicitly in the report that completion/partial-progress can only be
    confirmed by checking that system directly (e.g. `aws s3 ls` on the
    target bucket, `aws cloudfront list-invalidations`) — do not imply the
    move/job silently failed or silently succeeded; the local watcher simply
    lost visibility.

14. **Watching a Hermes subagent delegation transcript
    (`~/.hermes/cache/delegation/live/deleg_*/task-*.log`) for completion needs
    a structural anchor, not a keyword grep across the tail.** These logs are
    line-tagged (`HH:MM:SS think   |`, `tool     |`, `result   |`, `final    |`)
    and the subagent's own debugging narrative routinely contains the exact
    words you'd naively grep for as "done" or "error" signals while it's still
    mid-task: e.g. a variable/file literally named `failed-lessons.txt` or a
    log line `"failed count: 84"` will match a `grep -qE "failed"` terminal
    check on tick one, and a subagent that hits and *recovers* from a real
    Python `Traceback (most recent call last)` (e.g. a syntax error, retried
    with a different interpreter) will falsely trip a `grep -qE "Traceback"`
    stop condition even though it kept working productively afterward. Both
    produced a false "done"/"error" verdict in-session before the actual
    finish. Fix: anchor on the transcript's own terminal-state marker instead
    of prose content — the harness emits a dedicated
    `final    | status=completed ... summary: ...` line followed by
    `final    | end status=completed exit_reason=completed` (or
    `status=failed` / `status=error`) when the subagent actually stops. Grep
    for `^[0-9:]+ final\s+\| status=` (or just `"final    | end status="`) as
    the sole terminal-state trigger; only fall back to task-specific
    final-report vocabulary (e.g. "total processed", "already resolved") as a
    secondary check, and even then scope it to require it appear *within the
    same block as* a `final` line, not anywhere in a 50-line tail that still
    contains earlier debugging chatter.

## Pitfalls (recap)

- `execute_code`'s 5-min cap will kill a long sleep-loop — use a real
  background script instead.
- `terminal()` silently drops an entire command (heredoc included) if it
  contains a trailing `&` — write the script file first with `write_file`.
- Reusing a generic script/report path across unrelated polling tasks risks
  running stale content — use per-task filenames and verify content before
  launching.
- `process(action='wait')`'s timeout can be silently clamped below what you
  requested — don't treat a single wait as proof of full-duration coverage.
- A dead tmux session with no outcome token is a terminal state (crash), not
  a "keep polling" state — report it, don't wait out the rest of the budget.
- When polling a Hermes TUI pane, the persistent status-bar footer
  (`msg=interrupt · /queue · /bg · /steer`) is always present — never include
  it (or its keywords) in a "blocked" regex, and strip it plus other volatile
  chrome (timers, %, token counts) before hashing the pane for quiet-detection.
- Do not store the tmux binary path in a variable literally named `TMUX` —
  that env var is reserved by tmux itself and overwriting it breaks
  `has-session`/`ls` with a "Socket operation on non-socket" error, causing
  a live session to be misreported as crashed/gone.
- Grepping a delegation transcript tail for prose keywords ("failed",
  "error", "Traceback") produces false stops — a subagent's own debugging
  narrative routinely contains those words mid-task and while recovering
  from a handled error. Anchor on the structural `final    | status=...` /
  `final    | end status=...` marker line instead.
