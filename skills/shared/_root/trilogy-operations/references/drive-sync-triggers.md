# Drive sync trigger table (alpha-learn-content-gen qc-dashboard)

Source: `/app/.claude/scripts/utils/drive_sync.py` (`is_deployed()` gates
everything on `DEPLOYED_MODE=1`; every function below is a no-op locally).

| Trigger | File:call | Drive op |
|---|---|---|
| `UserPromptSubmit` hook, every prompt mentioning a lesson ID, when a backup already exists | `hooks/on_prompt.py` -> `session.py pull-drive` | full pull (`rclone copy athena:... -> local`, whole lesson dir) |
| `UserPromptSubmit` hook, first touch of a lesson (no backup yet) | `hooks/on_prompt.py` -> `session.py init` -> `sync_lesson_from_drive` | full pull + `acquire_lesson_lock` |
| `session.py pull-drive` (manual/explicit) | `tools/session.py:pull_drive` | full pull, recreates backup + watermark |
| `session.py push-drive` (manual/explicit, or auto-fixer) | `tools/session.py:push_drive` | full push, gated by `QC_AUTO_FIXER_PUSH_DRIVE` env (default on) and `is_lesson_stale` |
| QC scoring run | `tools/qc.py:91,95` -> `sync_lesson_from_drive` | full pull before scoring |
| `Stop` hook — every time the agent finishes a turn AND local files changed since last sync | `hooks/on_stop.py:75-80` -> `lesson_changed_since_sync` + `sync_lesson_to_drive` | full push |
| Auto-orchestrator job start/end (`job_runner.py`) | lines 153, 186, 224, 283 | pull before, push after (both directions, both start and end) |
| Dashboard server periodic + on-demand metadata sync | `server.py:85,93` -> `sync_drive_metadata` | `rclone copy athena:/ --fast-list` — **whole remote**, filtered to `slides.yaml` / `qc_report*.json` / `videos_per_slide/*.mp4` |
| Dashboard API: manual per-lesson push/pull-reports | `routes/api.py:62,78` | `bg.add_task(sync_lesson_to_drive)` / `sync_lesson_reports_from_drive` |
| Fixer API push after auto-fix | `routes/fixer_api.py:337` | `asyncio.to_thread(sync_lesson_to_drive)` |

## Mechanics worth knowing when debugging a specific stall

- `sync_lesson_from_drive` / `sync_lesson_to_drive` both call the private
  `_rclone()` helper via `subprocess.run(..., capture_output=True)` — this
  **blocks** the calling Python process (and therefore the agent turn) until
  rclone exits. No timeout on the full lesson pull/push; `sync_lesson_reports_from_drive`
  is the only bounded one (`--contimeout 10s --timeout 30s`, `timeout=45`
  on the subprocess call).
- Pull uses `copy --update` (never clobbers a local file newer than remote —
  protects in-progress local edits). Push also uses `copy --update` (never
  clobbers a Drive file newer than local — protects e.g. a dashboard rating
  written directly to Drive).
- `_touch_local_modtimes()` runs after every pull/push and does an
  `os.walk` + `os.utime` over every file in the lesson dir, so the *next*
  push's `--update` modtime comparison behaves correctly — this is extra
  local FS traffic on top of the rclone call itself, though it's cheap next
  to the NVMe numbers on this box.
- A failed pull sets a `.drive_stale` marker (`mark_lesson_stale`) which
  then **blocks all pushes** for that lesson until a successful pull clears
  it (`clear_lesson_stale`) — if a push silently no-ops, check this marker
  before assuming rclone itself is broken.
- Lesson-level lock (`.drive_lock`, 2h stale timeout) means two sessions
  touching the same lesson ID will have one blocked/erroring rather than
  racing — relevant if "slow" turns out to actually be "blocked waiting on
  another session's lock."
