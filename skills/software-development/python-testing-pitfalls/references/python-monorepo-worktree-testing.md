---
name: python-monorepo-worktree-testing
description: "Run/verify tests correctly in Python monorepos checked out as git worktrees (PR review, parallel branches) — avoid stale editable-install shadowing and misattributed failures. Also covers porting already-implemented work from one branch to a fresh branch off main without dragging in unrelated diffs."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, git, worktree, testing, pip, editable-install, pr-review, monorepo]
    related_skills: [github-code-review, requesting-code-review, systematic-debugging]
---

# Python Monorepo + Git Worktree Testing

## When to use

Any time you run Python tests against a codebase that:
- Is checked out into a **separate git worktree** from the repo's main clone (e.g. `<repo>/.claude/worktrees/pr-<n>-review/`, or any `git worktree add` layout) — common for isolated PR review, parallel feature branches, or CI-style review sandboxes.
- Is a **monorepo with multiple in-repo Python packages** installed via `pip install -e` (editable installs), where package A imports package B and both live in the same repo.

This combination is a trap: a single shared venv usually has editable installs pointing at whichever worktree was active when `pip install -e` was last run — almost always the main worktree, not the one you're currently reviewing.

## The core problem

`pip install -e <path>` writes an absolute path pointer (`.pth` file / `direct_url.json`) into the venv. It does NOT track "the repo" abstractly — it tracks *that exact directory*. If you then `cd` into a different worktree of the same repo and run pytest, Python still imports from the *original* editable-install path. Because both worktrees share git history up to the branch point, the code often looks nearly identical, so the failure is subtle: a function added in the PR branch appears "missing" via `AttributeError`, or mocked call patterns behave as if the old code is running — because it is.

## Step-by-step workflow

### 1. Before running any tests, check what path each dependency resolves to

```bash
pip show <package-name> | grep -E "Location|Editable project location"
```

Do this for **every in-repo package the code under test imports**, not just the top-level one — transitive in-repo dependencies get shadowed too (e.g. package A imports package B imports package C; if only A is reinstalled, B and C may still be stale).

### 2. If any editable install points at the wrong worktree, reinstall from the correct path

```bash
pip install -e "<correct-worktree-path>/components/<package>" --no-deps
```

Use `--no-deps` to avoid pulling in dependency version churn — you're just repointing the editable install, not upgrading anything.

### 3. Re-run the failing tests only after confirming installs are correct

Don't debug a "test failure" from Phase 1 of systematic-debugging until you've ruled out this environment issue — it produces symptoms (AttributeError, unexpected mock behavior, "function doesn't exist" when you can clearly see it in the source) that look exactly like real code bugs. Cheap to check first (`pip show`), expensive to debug blind.

### 4. When a failure touches a file marked out-of-scope, verify it's pre-existing before reporting it

If a test fails on a file that the task explicitly said not to touch (or on any file you're unsure the current diff affected), confirm the failure predates the change:

```bash
git checkout origin/main -- path/to/file.py     # swap in the base branch's version
python -m pytest path/to/test_file.py::test_name -v
git checkout HEAD -- path/to/file.py            # restore
```

If it fails identically against the base-branch version, it's pre-existing — report it explicitly as a known pre-existing failure, don't silently drop it from the summary, and don't "fix" an out-of-scope file just to make the suite green.

### 5. Module-level env-var reads can break "offline" test suites

Watch for `KeyError` tracebacks that occur at **import time** (module-level code, not inside a test function body) — this means a module unconditionally reads `os.environ["SOME_VAR"]` at import, even though the tests themselves don't need network/that credential. Treat this as a fixture/environment gap, not a real failure:

```bash
SOME_BASE_URL="http://localhost:9999" SOME_API_KEY="test-key" python -m pytest ...
```

Check the repo's test `conftest.py` for a `.env`-loading bootstrap first — the fix may belong in `.env` rather than being passed ad hoc, but for verification purposes a dummy value in the invocation is enough to unblock the run.

## When `uv` + relative-path sibling deps break the reinstall fix

Step 2 above (`pip install -e <correct-path> --no-deps`) assumes a normal pip
venv. Two variants that break it:

- **The shared venv resolves to a since-deleted stale path entirely**, not
  just the wrong worktree — e.g. an editable install pointing at an old
  `/tmp/suite-run6.<hash>` throwaway test-run checkout from a previous gate
  run. `pip show` still reports a `Location`/`Editable project location` even
  though the target may be gone or diverged; treat any non-worktree,
  non-main-repo path as suspect and don't assume reinstalling the top package
  is enough (see the transitive-dependency note above).
- **`uv pip install` on a package whose `pyproject.toml` declares a sibling
  in-repo dependency via a relative path** (e.g. `some-pkg = {path =
  "../sibling-pkg"}` or `file:../sibling-pkg`) fails during build isolation —
  `uv` builds in an isolated temp dir and can't resolve `../sibling-pkg` from
  there, so `pip install -e --no-deps` doesn't apply cleanly either. Workaround:
  skip building/installing the sibling package's own metadata; instead
  `uv pip install -r ../sibling-pkg/requirements.txt` (or equivalent) to get
  just its runtime deps, then run tests with `PYTHONPATH=src` so Python
  resolves your worktree's own `src/` directly — no editable install needed
  for the package under test at all. Full recipe:
  ```bash
  uv venv <worktree>/.venv312 --python 3.12   # isolated, don't reuse the polluted main venv
  uv pip install -r ../sibling-pkg/requirements.txt --python <worktree>/.venv312/bin/python
  PYTHONPATH=src <worktree>/.venv312/bin/pytest tests/
  ```
  This guarantees you're testing the worktree's actual modified code, never a
  stale editable-install target.

## Cross-worktree editable-install shadowing during T2/orchestrated recovery

When recovering or verifying a diff left behind in a worktree by a died/dead
coding-agent session (see `tier1-suborchestration`'s "Recovering a T2 that
died mid-work"), the shared venv's editable install can point at a THIRD,
unrelated worktree — not just "main vs this worktree" as the rest of this
skill assumes. In one case a shared venv's `script_generation_worker`
editable install resolved to a completely different in-flight worktree
(`.orchestrate-worktrees/script-gen-batch-driver/...`), so a test written
and passing against the worktree under review was silently exercising a
different branch's code, and a new test asserting a just-added CLI flag
kept failing for no visible reason. Confirm the resolved path explicitly
before trusting any test result on a recovered/orchestrated worktree:
```bash
python3 -c "import script_generation_worker.worker as w; print(w.__file__)"
```
If it doesn't start with the worktree path you're verifying, either
reinstall editable from the correct path (`pip install -e <correct-path>
--no-deps`) or run with `PYTHONPATH=<worktree>/.../src` prepended so the
worktree's source wins regardless of what's installed. This is the same
root mechanism as the rest of this skill (a `.pth`/`direct_url.json` pointer
tied to an absolute path), just triggered by concurrent orchestrated
worktrees rather than a single PR-review worktree — check it any time
multiple worktrees of the same repo are in flight at once, not only during
manual PR review.

## Related: porting already-implemented work to a fresh branch off main

Not a worktree scenario, but the same monorepo git hygiene applies when the ask is "this work already exists complete on branch X, put it on a new branch off `main`" (e.g. main moved past where the feature branch forked, and a clean single-purpose PR is wanted instead of the whole feature branch history):

```bash
git fetch origin && git checkout main && git pull origin main
git checkout -b feat/new-branch-name
git checkout <source-branch-or-sha> -- path/to/file1.py path/to/dir2/
```

Pitfalls:
- **Don't blind-checkout shared/registration files.** A new module usually needs a shared file updated too (a router-mounting `server.py`, a `pyproject.toml` dependency list, an `__init__.py` export list). If that shared file has diverged between `main` and the source branch beyond the one relevant change, checking it out wholesale drags in unrelated edits. Diff it first (`git diff main <source-branch> -- path/to/shared_file`) and hand-apply only the relevant lines with `patch`/manual edit instead.
- **Check `git status --short` immediately after the branch switch, before doing anything else.** Modified-but-uncommitted files you didn't intend to touch are leftovers from whatever branch/commit was checked out previously in that working tree. `git diff` them to confirm they're unrelated to your task, then `git checkout -- <file>` to discard. Also watch for untracked directories left on disk (e.g. `__pycache__/`) from a prior checkout that aren't actually tracked on the target branch — compare against `git ls-files` and delete stragglers so they aren't mistaken for real changes.
- **Re-run `git status --short` right before committing** as a final accounting — it catches both files you meant to include but forgot, and unrelated leaked changes you meant to exclude.

## Provisioning a FRESH editable-install venv in a new worktree (not just repointing an existing one)

The sections above assume a venv already exists and points at the wrong
place. When instead you're provisioning a brand-new worktree's venv from
scratch (a fresh T2/T3 coding-session worktree), a different set of
failures shows up, all in the dependency-resolution machinery rather than
path-pointer staleness:

1. **`pip install -e . --no-build-isolation` needs the build backend
   pre-installed in the venv.** If the package's `pyproject.toml` declares
   `build-backend = "hatchling.build"` (or similar), `--no-build-isolation`
   skips pip's normal isolated-build step and expects `hatchling` to already
   be importable in the target venv — install it first
   (`pip install hatchling`) or the editable install fails outright.
2. **Hatchling's editable build additionally needs the `editables` package**
   to write the `.pth`/proxy module — a hatchling-backed `pip install -e`
   with `--no-build-isolation` can fail with an import error for
   `editables` even after `hatchling` itself is present. Install both
   upfront: `pip install hatchling editables`.
3. **An editable reinstall does NOT pull a sibling in-repo package's
   transitive runtime deps.** In a monorepo where package A's code imports
   package B (also in-repo, also editable-installed), reinstalling A
   editable does not fetch B's OWN third-party dependencies declared in B's
   `pyproject.toml`/`requirements.txt` (e.g. a `google.genai` SDK import
   deep in B). Symptom: `import A` succeeds but raises `ModuleNotFoundError`
   for a transitive third-party name that has nothing to do with A. Fix:
   explicitly `pip install -r <sibling-package>/requirements.txt` (or
   equivalent) for every in-repo sibling the code under test imports, not
   just the top-level package being tested.
4. **Verify with a real import + a baseline test run, not just "install
   exited 0."** After provisioning, `python -c "import pkg_a, pkg_b"` for
   every in-repo package the work touches, then run the full existing test
   suite once before dispatching any coding session — a green baseline here
   is what lets you trust a later red result as a real regression instead of
   an environment artifact.

## Related: recovering a follow-up branch after the source PR was squash-merged

A variant of the "porting to a fresh branch" scenario above: you have a
worktree with several commits, an earlier subset of them was already opened
as a PR and got **squash-merged** into the base branch, and now you need to
push a small additional commit made in that same worktree afterward. Squash
merges collapse the entire PR's commit history into ONE new commit on the
base — your worktree's pre-squash commits are still there locally but no
longer match the base branch's actual history. Diffing or opening a PR
straight from the old branch re-surfaces the entire already-merged history
as if it were new.

```bash
# 1. Confirm the earlier PR merged, and that it was a squash (not merge/rebase)
gh pr view <PR1_NUMBER> --json state,mergeCommit,mergedAt

# 2. Find which local commit(s) are the NEW work, not part of the squash
git log --oneline <base_branch>..<old_branch>   # new work = the tail commit(s)

# 3. Branch fresh off the now-updated base
git fetch origin <base_branch>
git checkout -b <new_branch> origin/<base_branch>

# 4. Bring over only the new commit(s)
git cherry-pick <new_commit_sha>

# 5. Confirm the diff is minimal before pushing
git diff origin/<base_branch>...HEAD    # should show ONLY the follow-up change
```

Run the full test suite on the new branch before pushing — a cherry-pick onto
a different base tip can silently pick up merge artifacts if the squash
touched overlapping lines. This pattern recurs any time a kanban/orchestration
follow-up task reuses a worktree whose earlier task's PR already merged.

## Pitfalls

- **Don't assume a clean `pip install -e .` in the review worktree fixes everything at once.** Each in-repo package with its own `pyproject.toml`/`setup.py` needs its own reinstall; a monorepo umbrella install doesn't always repoint every sub-package.
- **`pip show` output can carry unrelated warnings** (e.g. `WARNING: Ignoring invalid distribution ~esson-qc-...` from a corrupted dist-info directory) — don't let this mask the `Editable project location` line you actually need; grep specifically for it.
- **Re-verify after fixing, don't assume**: reinstalling one package can reveal that a second, transitively-imported package is also stale. Iterate `pip show` checks until every failure clears or is confirmed as a real code issue.
