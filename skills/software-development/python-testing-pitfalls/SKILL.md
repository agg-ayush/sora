---
name: python-testing-pitfalls
description: Fix Python mock/patch footguns and worktree test issues.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [python, testing, e2e, mock, worktree, pytest]
---

# Python Testing Pitfalls

Deep-dives on subtle Python testing footguns: mock/patch delegation that silently no-ops, hermetic subprocess E2E tests, and git-worktree + editable-install shadowing in monorepos.

## When to Use

- A `unittest.mock.patch` test where a mock is supposed to delegate part of its behavior to "the real" class/method, and the delegation silently never fires (no error, no side effect, debug prints inside the target never appear).
- Building a genuinely hermetic E2E test that shells out (`subprocess.run`) to run real pipeline code against a scratch copy of source with edits applied.
- Running tests in a Python monorepo checked out as a **git worktree** (PR review sandbox, parallel branches) with `pip install -e` editable installs — symptoms like `AttributeError` on a function you can clearly see in the source, or mocks behaving as if old code is running.
- A test failure touches a file the task marked out-of-scope — verify it's pre-existing before reporting.

## Procedure

### 1. The `from module import X` inside `with patch(...)` footgun (references/python-mock-patch-pitfalls.md)

**Root cause:** `from pkg.module import X` re-resolves `X` off `pkg.module`'s CURRENT attribute value at the moment the import executes. If that attribute is presently patched, the import returns the mock — even though the code visually reads as "grab the real class":

```python
with patch("pkg.module.RealClass", some_mock):
    from pkg.module import RealClass as _Real   # BUG: binds the MOCK
    some_mock._copy_method = _Real._copy_method  # delegates to the mock, not the real impl
```

**Fix:** capture the real reference BEFORE entering the patch scope:

```python
from pkg.module import RealClass as _Real      # capture BEFORE patching
_real_method = _Real._copy_method

with patch("pkg.module.RealClass", some_mock):
    some_mock._copy_method = _real_method       # now delegates to the real impl
```

Every layer checks out in isolation — only the order of operations relative to the patch scope is wrong. Burn the cheap check first.

The reference also covers hermetic subprocess E2E construction: env scrubbing, `sys.path` depth, scratch-copy import loading.

### 2. Monorepo worktree + editable-install shadowing (references/python-monorepo-worktree-testing.md)

`pip install -e <path>` writes an absolute path pointer (`.pth` / `direct_url.json`) into the venv — it tracks THAT exact directory, not "the repo". A shared venv's editable installs point at whichever worktree was active when `pip install -e` last ran — usually the main worktree, not the PR-review worktree you're in. Both worktrees share history up to the branch point, so the code looks nearly identical and the failure is subtle.

**Workflow:**
1. Before running any tests, check what path each in-repo dependency resolves to — for EVERY in-repo package the code under test imports, not just the top-level one:
   ```bash
   pip show <package-name> | grep -E "Location|Editable project location"
   ```
2. If any editable install points at the wrong worktree, reinstall from the correct path with `--no-deps` (repoint only, don't pull dependency churn):
   ```bash
   pip install -e "<correct-worktree-path>/components/<package>" --no-deps
   ```
3. Re-run failing tests only after confirming installs are correct — don't debug a "test failure" from Phase 1 of systematic-debugging until this environment issue is ruled out (it's cheap to check, expensive to debug blind).
4. If a failure touches an out-of-scope file, confirm it predates the change before reporting:
   ```bash
   git checkout origin/main -- path/to/file.py
   python -m pytest path/to/test_file.py::test_name -v
   git checkout HEAD -- path/to/file.py    # restore
   ```
   Fails identically against base → pre-existing; report it explicitly as pre-existing, don't silently drop it, don't "fix" an out-of-scope file to make the suite green.

The reference also covers porting already-implemented work from one branch to a fresh branch off main without dragging in unrelated diffs.

## Pitfalls

- Debugging a mock-delegation no-op by staring at the delegation assignment, the staticmethod body, and the call site — all correct independently; the bug is the `from ... import` line's position relative to `with patch(...)`.
- Debugging an `AttributeError` / "function doesn't exist" test failure as a code bug before checking `pip show` for editable-install shadowing.
- Reinstalling only the top-level package in a worktree — transitive in-repo deps (A imports B imports C) stay stale; check every in-repo package.
- `pip install -e` without `--no-deps` when repointing — pulls dependency version churn you didn't ask for.
- Reporting an out-of-scope test failure as caused by the current diff without the base-branch swap check — or silently dropping it from the summary.
- A pytest collection ERROR isn't proof of a broken test file — check editable-install shadowing first before writing it off as "environment, can't verify".

## Verification

- Mock delegation: with the fix applied, the real method's side effect/debug print fires inside the `with patch(...)` integration test; a regression test asserting the delegation exists.
- Worktree testing: `pip show` for every in-repo package the tests touch points at the current worktree; the previously-failing tests pass without code changes after repointing.
- Out-of-scope failure: same test run against `origin/main`'s version of the file produces the identical failure, and the file is restored afterward (`git status` clean of it).

## References

- `references/python-mock-patch-pitfalls.md` — full footgun taxonomy, hermetic subprocess E2E construction (env scrubbing, sys.path, scratch-copy loading).
- `references/python-monorepo-worktree-testing.md` — full worktree workflow, branch-porting procedure, additional worktree traps.
