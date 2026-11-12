# hermes-dev-process

Claude Code plugin for the design-led dev process: reviewer agents and the review commands. Spec: `docs/dev-process-v2.md`.

| Piece | File |
|---|---|
| `/card-review` | `commands/card-review.md`: one review session, parallel subagents, two verdicts |
| `/design-review` | `commands/design-review.md` |
| `conformance-reviewer` | diff against design: missing, extra, misunderstood, boundaries, test quality, verification promises |
| `mutation-probe` | at most 5 mutants in a throwaway worktree, impacted tests only |
| `design-lens`, `change-impact-bundle` | design review lenses |

Marketplace id `hermes-setup` (the repo root, `.claude-plugin/marketplace.json`), plugin id `hermes-dev-process@hermes-setup`. `devbox/setup-hermes.sh` registers the marketplace, installs and enables the plugin, then mirrors it into the Seatbelt `settings.json`. The marketplace is a directory source, so the plugin is read in place from the repo: edits apply at the next session start with no reinstall.

Agent names carry the plugin prefix when launched: `hermes-dev-process:conformance-reviewer`, `hermes-dev-process:mutation-probe`.

## Run a review

```
/hermes-dev-process:card-review <design-path|none> range=<base>..<head> task_dir=<dir> round=<n> tier=<light|full|none>
```

Run it inside the card worktree. Round 1 defaults to `base_commit` from `process.json` up to HEAD; round 2 and later default to the HEAD recorded by the previous round (fix diff only). It writes `<task-dir>/review/<agent>-r<round>.md` per agent and `<task-dir>/code-review-r<round>.md` with the verdict block. Headless on the Seatbelt route: `claude --dangerously-skip-permissions -p "/hermes-dev-process:card-review ..."`.

## TDD enforcement

Verdict on nizos/tdd-guard: not adopted.

- It asks an LLM on every source edit (`maxTurns: 1`, default `claude-sonnet-4-6`, through the Claude Agent SDK), which adds seconds and tokens per edit and needs a Seatbelt model id override.
- It fails closed: a model or parse error returns `block("Error during validation: ...")` (`src/validation/validator.ts:24-28`), so any model hiccup wedges the session.
- It needs a test reporter in the project (`tdd-guard-vitest`, `tdd-guard-jest` or `tdd-guard-pytest` plus `projectRoot` config), which edits product repo config files.
- Its plugin hooks run `npx tdd-guard@latest` on every event, a network fetch and unpinned code in each hook.
- The author now points new projects to a successor (Probity).

The replacement is a deterministic red gate with no model call: `scripts/red-gate-hook.py` (installed as `~/.hermes/agent-hooks/red-gate.py`). It denies Write, Edit, MultiEdit and NotebookEdit on source files until `<task-dir>/evidence/red-*.txt` exists, is non-empty and its output shows a failing test. Tests, docs, config and anything under the task dir are always allowed. Any error inside the hook prints a warning and allows the edit. `HERMES_RED_GATE=off` disables it. Bash edits are not intercepted; the plugin gate that requires red and green files at code review start is the backstop.

### Steps for tier 2 (implementation sessions in card worktrees only)

Apply to cards with `kind` feature or bugfix and tier light or full, and to bugfix at tier none. Skip refactor, test, copy and config cards.

1. Before launching the implementer, write `<worktree>/.claude/settings.local.json` (globally git-ignored, never committed):

```json
{"hooks": {"PreToolUse": [{"matcher": "Write|Edit|MultiEdit|NotebookEdit",
  "hooks": [{"type": "command",
    "command": "python3 $HOME/.hermes/agent-hooks/red-gate.py <task-dir>", "timeout": 10}]}]}}
```

   Use the absolute task dir (`~/.hermes/tasks/t2-<id>`). If the file already exists, merge the hook into it.
2. Tell the implementer the evidence commands below. It must save RED before any source edit.
3. Delete the file when implementation ends, before launching review sessions in the same worktree.
4. Fix rounds: move the previous `evidence/red-*.txt` and `evidence/green-*.txt` into `evidence/r<N>/`, then repeat steps 1 to 3. The fix starts with a reproducing test and a new RED file.

The hook loads in headless `claude -p` runs (checked) and in interactive sessions through the same project settings.

## Evidence capture for the implementer

`scripts/capture-evidence.sh` (installed as `~/.hermes/agent-hooks/capture-evidence.sh`) saves the exact command on line one and the raw runner output after it, then checks the expectation: red must fail (exit 3 if the run passed), green must pass.

```bash
export HERMES_TASK_DIR=~/.hermes/tasks/t2-<id>
CE=~/.hermes/agent-hooks/capture-evidence.sh

# 1. write the tests from the design's verification table, then on the unchanged code:
$CE red <unit> -- npx vitest run src/foo.test.ts          # or: python -m pytest -q tests/test_foo.py
# 2. edit source until the tests pass, then:
$CE green <unit> -- npx vitest run src/foo.test.ts src/bar.test.ts
```

One red and one green file per unit (`evidence/red-<unit>.txt`, `evidence/green-<unit>.txt`). The green command runs the new tests plus the impacted tests from `evidence/test-impact.txt`. Existing assertions are immutable once RED is saved: a change needs a written reason in the commit message.
