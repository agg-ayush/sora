# Repo-Targeting Before Dispatch (T1/T2 orchestration)

## The failure

A workstream description said "invite/scheduling" without naming a repo. The
T1 dispatcher defaulted to its own home board's repo (`ti-hiring`) and spawned
a T2 there. A T2 built the feature, opened a PR, tests passed, review approved
— all correct work, on the wrong repo. The user caught it only after the PR
was already up: "wait 66 shouldnt be on cn-hr-automation... no no i dont need
it to be in ti-hiring, we can change the code on cn-hr-automation" — because
`cn-hr-automation` was the actual pre-existing system this workstream was
meant to extend (the old invite automation, discovered earlier in the same
session). Fix required closing the wrong-repo PR, cloning the correct repo,
and redispatching a fresh T2 — a full throwaway build cycle.

## Root cause

The task board/session had a "home repo" (wherever the orchestrator's board
lives), and absent an explicit repo in the task text, the dispatcher silently
assumed home-repo == target-repo. That assumption is only safe for genuinely
new, standalone components. It's wrong whenever the task's own wording implies
an existing system — "extend X", "reuse X's pattern", "add this to X",
"we already have X, just wire into it" — because X is very often a DIFFERENT
repo than wherever today's board happens to live.

## The rule

Before creating a kanban task or spawning a T2/coding session for any
workstream, check the task's own description for a reference to an existing
system, service, or automation by name. If one exists:
1. Identify which repo that named system actually lives in (ask the user if
   ambiguous — don't guess-search GitHub for "something related to X").
2. Create the task and dispatch the coding session against THAT repo, not
   the orchestrator's default/home repo.
3. Only fall back to the home repo when the task is a genuinely new,
   standalone component with no named predecessor to extend.

This is cheap to check up front (one clarifying question or a quick repo
lookup) and expensive to fix after a PR is already open on the wrong repo.

## Applies to

Any T1/T2 orchestration, or any `delegate_task`/coding-agent dispatch, where
the task text references an existing named system without an explicit repo.
Also applies to plain (non-tiered) delegated coding work — the same
default-to-home-repo trap applies whenever a dispatcher has its own "home"
context and the task references something external to it.
