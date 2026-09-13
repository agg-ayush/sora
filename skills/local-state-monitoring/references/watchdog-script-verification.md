---
name: watchdog-script-verification
description: "Build/verify silent-unless-new watchdogs on internal DBs."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [monitoring, watchdog, canary, dedup, watermark, sqlite, testing, verification, devops]
    category: devops
    requires_toolsets: [terminal]
    related_skills: [watchers, background-task-polling, python-testing-pitfalls]
---

# Watchdog Script Verification

For writing a **new** script that watches internal automation state — a
session/usage SQLite DB, a kanban board DB, a log directory — and alerts only
when something is actually wrong, staying silent otherwise. Distinct from the
hub `watchers` skill (RSS/JSON/GitHub external feeds with a shared
`_watermark.py` helper) and from `background-task-polling` (polling a single
local process/tmux pane to a terminal state). This skill is for the class of
"is my infra healthy" scripts: auth canaries, dead-supervisor/dead-man's-switch
checks, doom-loop detectors — anything that reads a DB/log on an interval and
should only ever speak up when it finds something new and bad.

## When to use

- Asked to build a canary/watchdog/health-check script against a local
  SQLite state DB, kanban DB, or log directory.
- Extracting one narrow alerting behavior out of a larger existing script
  (e.g. pulling just the "zero-output-tokens" check out of a bigger
  cost-guard/budget script, dropping the unrelated cost logic).
- Verifying that a watermark-dedup contract (silent baseline, alert on new
  finding, dedup on repeat) actually holds for a script before shipping it.

## The contract (same shape as `watchers`, applied to internal state)

1. Fetch/query the current state (SQLite `SELECT`, log tail, etc.)
2. Compare found "findings" against a watermark file of previously-alerted
   IDs (keyed by an explicit `--name`, stored under `WATCHER_STATE_DIR`,
   defaulting to `$HERMES_HOME/watcher-state/`)
3. First run ever (no watermark file) records a baseline and emits **nothing**
   — never replay pre-existing state as if it were new
4. Emits one markdown block per genuinely new finding; **empty stdout** when
   there's nothing new
5. Non-zero exit (with a stderr message, not just a stack trace) when the
   underlying data source itself is missing/unreachable — distinct from "zero
   findings", which is exit 0 + empty stdout

Match the target repo's existing conventions for exit codes / stderr wording
by grepping sibling scripts before inventing your own (e.g. check what the
existing alert watcher in the repo does on a missing DB, and mirror it exactly
rather than picking a plausible-looking convention).

## Extracting a narrow check from a larger script

When the ask is "pull just concept X out of script Y, drop everything else":

- Read both the conceptual description (often called out in a comment block
  near the top) and the actual implementation lines separately — the comment
  may describe the general problem while the implementation has the specific
  thresholds/queries you need to keep.
- Drop unrelated logic wholesale (don't leave dead imports/config for the
  parts you didn't keep) but preserve the exact table/column names, thresholds,
  and error-handling style from the source — those encode institutional
  knowledge (what a "healthy" value actually looks like) that's easy to get
  subtly wrong if you rewrite from the concept alone.
- Confirm any DB columns you depend on actually exist in the target schema
  before writing the query (`.schema <table>` or read the migration/creation
  SQL) — don't assume the source script's schema matches this repo's.

## Verifying the contract before shipping

Don't eyeball the output — the baseline-silent behavior specifically hides
bugs. A script with a broken `SELECT` also prints nothing on a busted first
run, identical to "working correctly." Build a throwaway harness, run it, then
delete it (verification artifact, not part of the deliverable):

1. Fixture state (SQLite DB, log file) in a tmpdir standing in for
   `HERMES_HOME`, with its own `WATCHER_STATE_DIR` — never touch the real one.
2. Run the script as a **real subprocess** (not an import) with that env, so
   you're testing the actual CLI/exit-code contract, not internals. Pin the
   interpreter explicitly (e.g. `/opt/homebrew/bin/python3.14`) if the repo's
   code needs a newer Python than whatever `python3` resolves to on PATH —
   check with `ls /opt/homebrew/bin/python3*` when a script that should be
   fine throws a syntax-looking error unrelated to your change.
3. Exercise in order: missing source → non-zero exit + stderr; healthy state
   → exit 0, empty stdout; unhealthy state on a **fresh** watermark → exit 0,
   empty stdout (baseline, not a bug — this is the step people forget and then
   wrongly report the script as broken); **reset only the watermark's
   `seen_ids` list** (not the whole state file, not the source data) and
   re-run → this is what forces the alert path without waiting out a real
   time window; re-run again unchanged → dedup, empty stdout again.
4. Clean up the tmpdir in a `finally` regardless of pass/fail, and delete the
   harness script itself once done — it's disposable, not a deliverable.

See `scripts/verify_watermark_watcher.py` for a template harness (SQLite
fixture builders, watermark reset helper, subprocess runner, pass/fail
tally) — copy it, swap in your fixture-builder and finding-string assertions.

## Pitfalls

- **Testing via `importlib` instead of subprocess** hides real CLI-contract
  bugs (argv parsing, exit codes, stderr wording) — always shell out to the
  actual script for the verification pass, even if the checked-in unit tests
  use `importlib`.
- **Forgetting the first-run-is-silent step** and concluding a script is
  broken because it printed nothing on your first fixture run — check whether
  a watermark file already exists before assuming that's a bug.
- **Resetting the whole watermark file** instead of just `seen_ids` when
  forcing a re-alert — if the watermark also carries other state (last-run
  timestamp, window bucket), wiping it can change which time bucket the next
  run falls into and produce a different (still real, but confusing) result.
- **Not confirming DB schema before writing the query** — a source script's
  column names (e.g. `last_heartbeat_at`) may or may not exist in this repo's
  actual table; check the CREATE TABLE / migration before assuming parity.
