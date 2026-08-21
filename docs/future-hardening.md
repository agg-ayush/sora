# Tier-System Hardening: Reactive → Deterministic

Patterns that currently depend on the T1/T2 *remembering* to do something, and
how each could be enforced structurally. Ordered by impact.

## 1. Watcher arming at T2 dispatch — SKILL-MANDATED, not code-enforced

**Current:** T1 skill says "THEN ARM THE WATCHER — mandatory." But it's a skill
instruction; a T1 that skips it leaves a T2 unwatched. (Fixed in 5a72313 at the
skill level; not yet code-enforced.)

**Deterministic:** `claude_orchestrate start` (the plugin action that spawns a
T2) auto-arms a watcher for the spawning session. The plugin knows the task_id
and board; it can register the watcher at spawn time. No T1 step to skip.

## 2. Watcher re-arm on "no events" — T1 must remember to re-arm

**Current:** the watcher is bounded (~25 min); on a quiet window it exits with
"no events" and the T1 must re-arm a fresh one. If the T1's turn is busy or it
misses the injected turn, the watch lapses silently.

**Deterministic:** the watcher subagent itself re-arms on a quiet window (the
delegate_task result carries a "re-arm" flag; the T1's next turn sees it and
re-arms). OR: the plugin's `_wait`/`_gate` auto-heartbeat (already wired) could
also emit a "no watcher active" warning when a session has outstanding T2s and
no live watcher.

## 3. Merge verification — T1 must poll `gh pr view` after auto-merge

**Current:** T2 sets auto-merge, then the T1 is told to "keep polling until it
actually merges." The T1 has to remember to poll; if it doesn't, the task sits
in `review` forever.

**Deterministic:** a kanban watcher on `review_requested` could also poll the
PR state and auto-complete the task when the merge lands. The T2's Phase 5
already does this, but T2s often exit before Phase 5. A board-level cron (like
the CI watcher) could poll open `review`-state tasks and auto-complete merged
ones.

## 4. Design doc attach — T2 must remember before Phase 2

**Current:** "Forgetting to attach the accepted design doc before Phase 2" is a
listed pitfall. The T2 must `hermes kanban attach` the doc and verify it.

**Deterministic:** the T2's Phase 2 entry could gate on attachment presence —
the plugin's `_gate` action checks whether a design doc is attached before
allowing the implementation phase to start. If missing, it blocks with a clear
message.

## 5. Brief submit verification — T1 must re-check the pane

**Current:** "THEN VERIFY the brief was actually submitted — do not assume."
The T1 must capture the pane after ~5s and re-send Enter if the submit failed.

**Deterministic:** the `claude_orchestrate start` action could verify the brief
landed (capture the pane, check for "working" state) before returning success.
If the brief didn't land, it re-sends automatically.

## 6. Task close after merge — T1 must do it if T2 exits first

**Current:** T2s often exit in `review` (Phase 4 hands off "awaiting merge" and
the session stops). The T1 must close the task manually.

**Deterministic:** same as #3 — a board-level cron that polls `review`-state
tasks, checks the PR merge state on GitHub, and auto-completes.

## 7. Kanban heartbeat — already structural (auto-heartbeat in the plugin)

**Current:** the plugin auto-heartbeats from inside `wait`/`gate` (60s throttle).
This one is already deterministic — no T1/T2 step to skip.

## 8. Stall detection — already structural (`_session_state` polls activity)

**Current:** `_session_state` classifies a session as working/stalled/done from
the pane + status.md. The `_wait` loop returns on stall. Already deterministic.

---

**Theme:** the pattern is "the skill says to do X, but nothing enforces it."
The fix is always the same: move the check into the plugin (the code that runs
the spawn/wait/gate), not the skill (the instructions the model reads). The
plugin is the trust boundary; the skill is the hint.
