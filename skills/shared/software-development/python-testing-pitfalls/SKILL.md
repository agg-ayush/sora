---
name: python-testing-pitfalls
description: "Fix Python mock/patch footguns and worktree test issues."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, testing, e2e, mock, worktree, pytest]
    related_skills: [github-code-review, requesting-code-review, systematic-debugging]
---

# Python Testing Pitfalls

## When to Use

Debugging subtle Python test failures that look like code bugs but are
environment/machinery issues: mock/patch delegation, git-worktree editable-
install shadowing, hermetic subprocess E2E, and monorepo dependency
resolution. Also for porting already-implemented work between branches and
recovering follow-up work after a squash-merge.

## Playbooks

- `references/python-monorepo-worktree-testing.md` — running/verifying tests
  in monorepos checked out as git worktrees: stale editable-install
  shadowing (the shared venv points at the wrong worktree's code, producing
  failures that look exactly like real bugs), fresh-venv provisioning
  pitfalls (hatchling/editables, transitive sibling deps), porting work to a
  fresh branch off main, and recovering a follow-up branch after a
  squash-merge.
- `references/python-mock-patch-pitfalls.md` — mock/patch delegation
  footguns and hermetic subprocess E2E testing issues.

## The one rule to always-on before debugging a "test bug" in a worktree

Check what each in-repo dependency resolves to first
(`pip show <pkg> | grep -E "Location|Editable project location"`) — a shared
venv's editable installs point at whichever worktree was active at
`pip install -e` time, and code imported from the wrong worktree produces
failures indistinguishable from real bugs. Cheap to check, expensive to
debug blind.
