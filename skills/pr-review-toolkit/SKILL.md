---
name: pr-review-toolkit
description: Run pr-review-toolkit specialist reviewers on a PR diff.
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
- You want a structured verdict (see "The verdict format" below) from specialist
  reviewers
- The diff introduces stateful behavior — the state-transition-reviewer fires
  conditionally (see the specialist table below)

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
    your verdict to <verdict-path> in the verdict format defined below
    ("The verdict format"). Set status complete + write DONE to your outcome
    file."
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
| state-transition-reviewer | State-transition adversarial paths (failure-then-retry, reset coverage, mid-flight config, dual-writer desync) | If the diff introduces stateful behavior — deployed from `hermes-setup/plugins/pr-review-toolkit/agents/`, not part of the stock plugin |
| code-simplifier | Polish and refine | After passing review |

The stock plugin ships six agents (no state-transition-reviewer — that one is
ours, deployed alongside the stock set into the plugin's agents dir).

## The verdict format

The review writes a structured verdict to the out-of-repo verdict-path:

```
spec: pass|fail
quality: approved|needs_fixes
confidence: <0-100>
findings: [...]
state_transitions: clean|needs_fixes   # only if the stateful reviewer fired
```

## Standalone audit mode (no PR, no diff)

The no-diff maintenance audit: "does this existing
component carry removable weight?" — dead code, duplicated logic, oversized
functions, untested-but-shipped paths — on code that already exists and
already ships, with no change to score against. Run it in the same review
session (or any Hermes session) using the method below.

### Read-only extraction

When the mandate is read-only, never `git checkout`/`git pull` the target
branch into the repo's working tree. Extract via `git show` into a scratch dir:

```bash
git -C <repo> fetch origin <ref>            # ref = branch/PR/tag
mkdir -p /tmp/<audit-name>
for f in $(git -C <repo> ls-tree -r --name-only origin/<ref> -- <subdir>); do
  mkdir -p "/tmp/<audit-name>/$(dirname "$f")"
  git -C <repo> show "origin/<ref>:$f" > "/tmp/<audit-name>/$f"
done
```

### Audit method

1. **Read every in-scope file fully before judging** — source AND its test
   files; test coverage is a primary signal. Partial reads produce
   indefensible verdicts.
2. **Cross-file symbol-usage scan → dead code**: for every
   function/constant/class defined in src, count usages across src AND
   tests (systematic script, not eyeballing). Zero uses outside its own
   definition = dead code, flag for removal.
3. **Untested-but-shipped**: grep each logical unit's distinguishing
   string/id across test files. Zero test mentions is a finding, NOT an
   automatic deletion — dead (also zero call sites) → safe to delete;
   live-but-untested → "either delete or add minimal tests," stated
   explicitly. Deleting live-untested code is a product/risk call, not a
   refactor call.
4. **Duplicate-logic scan**: same regex/literal/algorithm defined more than
   once across files. Each duplicate is one cut-list line: "extract into
   `_shared_helper`, ~N LOC saved."
5. **Oversized-function scan**: lint-suppression clusters (`noqa: PLR0912`,
   `eslint-disable`, `# type: ignore` groups) + line count. A 150+ line
   function with 2+ suppressions is a structural finding: propose a concrete
   split along its own phase boundaries.
6. **Summary table ordered by value/effort** (| # | Location | Issue |
   Suggested simplification | Est. LOC saved | Risk |), pure dead code first,
   needs-product-decision middle, risky-defer last.
7. **"What NOT to simplify" section — mandatory**: name the code that looks
   reducible but is defect-hardened (whitespace-preservation tied to a past
   bug, a hand-rolled parser solving a different problem than a lookalike
   library, literal fixtures reproducing real defect geometries). Some of
   the ugliest code is there because a simpler version already broke once.
8. **Bottom-line verdict + ranked top 3** (healthy/accreting/needs-attention,
   where specifically; the top-3 is the actionable ask, the table is the
   reference). Defer medium/high-risk items until low-risk ones land.

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
  adversarial paths go unprobed (see the specialist table for what it covers).
  Include it when the diff introduces stateful behavior.
- **Reusing the implementer session to review its own work** → always a distinct
  review session. Never reuse the implementer to review its own work.
