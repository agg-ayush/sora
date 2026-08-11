---
name: pr-review-toolkit
description: Use when reviewing a PR's changes in a worktree via the Claude Code pr-review-toolkit plugin. Runs specialist reviewers (code-reviewer, silent-failure-hunter, comment-analyzer, pr-test-analyzer, type-design-analyzer, state-transition-reviewer) against the diff and writes a structured verdict. This is a Claude Code plugin — invoke it via a Claude Code session, not a Hermes session.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-review, pr-review-toolkit, claude-code, verification]
    related_skills: [requesting-code-review, tier2-orchestration, github-code-review]
---

# PR Review Toolkit (Claude Code plugin)

A Claude Code plugin that runs a comprehensive PR review via specialist agents.
This is a **Claude Code plugin** — it runs inside a Claude Code session
(`/pr-review-toolkit:review-pr`), not a Hermes session. Use it when reviewing a
worktree's changes before merge.

## When to use

- Reviewing a PR's changes in a worktree before merge (the T2 gate's review step)
- You want a structured verdict (spec pass/fail, quality approved/needs_fixes,
  confidence, findings) from specialist reviewers
- The diff introduces stateful behavior (latches, refs, machine context, admission
  gates, persistence, restore/seed paths) — the state-transition-reviewer fires
  conditionally and probes adversarial paths (failure-then-retry, reset coverage,
  mid-flight config change, dual-writer desync)

**Don't use for:** a quick lint or a single-file sanity check — the toolkit is a
full review pass, overkill for trivial changes. Don't use it in a Hermes session
— it's a Claude Code plugin, not a Hermes tool.

## How to invoke it

The toolkit is a Claude Code plugin — run it via a Claude Code session (the
`claude_orchestrate` plugin's `start` action):

```
claude_orchestrate start:
  executor=claude,
  model_provider=fireworks,   # kimi-k3 via Fireworks
  workdir=<the task's worktree>,
  effort=medium,
  prompt="Run `/pr-review-toolkit:review-pr` on the changes in this worktree
    (diff base <base_sha>..HEAD) against <brief-file>. Include the
    state-transition-reviewer if the diff introduces stateful behavior. Write
    your verdict to <verdict-path> as: spec: pass|fail, quality:
    approved|needs_fixes, confidence: <0-100>, findings: [...], plus
    state_transitions: clean|needs_fixes if the stateful reviewer fired. Set
    status complete + write DONE to your outcome file."
```

Then `claude_orchestrate wait` and read the verdict file.

## The specialist reviewers

| Specialist | What it checks | When it fires |
|---|---|---|
| code-reviewer | General code quality | Always |
| silent-failure-hunter | Error handling, silent failures | If error handling changed |
| comment-analyzer | Comment accuracy | If comments/docs added |
| pr-test-analyzer | Test coverage | If test files changed |
| type-design-analyzer | Type design, invariants | If types added/modified |
| state-transition-reviewer | State-transition adversarial paths (failure-then-retry, reset coverage, mid-flight config, dual-writer desync) | If the diff introduces stateful behavior |
| code-simplifier | Polish and refine | After passing review |

## The verdict format

The review writes a structured verdict to the out-of-repo verdict-path:

```
spec: pass|fail
quality: approved|needs_fixes
confidence: <0-100>
findings: [...]
state_transitions: clean|needs_fixes   # only if the stateful reviewer fired
```

## Fallback (Claude Code auth down)

If the Claude Code auth probe fails, the toolkit can't run (it's a Claude Code
plugin). Fall back to the Hermes-native `requesting-code-review` skill — run its
specialist batch (silent-failure-hunter, code-reviewer, comment-analyzer,
type-design-analyzer, pr-test-analyzer, state-transition-reviewer) via
`delegate_task` on the diff. These run on the global delegation model (kimi-k3).
Note in the gate comment that review ran via the fallback, not the toolkit.

## Pitfalls

- **Running it in a Hermes session** → it won't work; it's a Claude Code plugin.
  Use `claude_orchestrate start executor=claude` to launch a Claude Code session.
- **Skipping the state-transition-reviewer on a stateful diff** → the
  adversarial paths (failure-then-retry, etc.) go unprobed. Include it when the
  diff introduces stateful behavior.
- **Reusing the implementer session to review its own work** → always a distinct
  review session. Never reuse the implementer to review its own work.
