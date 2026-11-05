# delegate_task watcher aborting during a provider outage

Symptom: a `delegate_task` watcher armed to poll a T2/background job comes
back with:

> The batch did not complete successfully: Delegation owner exited before
> recording a terminal result; outcome unknown.

This does NOT mean the watched task (T2, background process) failed or died.
It means the **delegation dispatch layer itself** had an outage (observed
cause: the LLM provider backing delegated subagents — e.g. fireworks —had
expired/broken credentials or was down) and the watcher subagent never
actually got to run and observe anything. The message carries zero signal
about the real task state.

## What NOT to do

Don't re-arm another `delegate_task` watcher immediately in a retry loop —
if the provider is still down it will likely abort the exact same way,
burning cycles without new information.

## What to do

1. Fall back to a direct, non-delegated check: `terminal()` calls hitting
   `tmux capture-pane -t <session>`, `gh pr list`, or reading the task-dir
   `status.md`/`outcome.md` directly. These don't route through the
   delegation-provider path and work even while it's down.
2. If you need continued bounded polling, use
   `terminal(background=true, notify_on_complete=true)` running a real
   sleep+check script (see the main `background-task-polling` SKILL.md
   pattern) instead of `delegate_task` — this only depends on the shell,
   not on an LLM provider being up.
3. Resume delegate-based watchers once the provider is confirmed healthy
   again — e.g. a `[System: active model changed to ... via provider ...]`
   notice, or after a small delegate_task call actually succeeds.

This was hit while babysitting a long-running persistent-T2 workstream
(script-image-gen regen-routing PR) — the T2 itself stayed alive and kept
working through the outage on a fallback executor; only the *watcher*
dispatch failed.
