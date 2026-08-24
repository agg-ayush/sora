---
name: python-testing-pitfalls
description: Fix Python mock/patch footguns and worktree test issues.
metadata:
  hermes:
    tags: [python, testing, e2e, mock, worktree, pytest]
---

# Python Testing Pitfalls

This skill contains deep-dives on subtle testing footguns in Python codebases, particularly:
- Mock/patch delegation pitfalls (where a mock is supposed to delegate to the real implementation but silently fails)
- Hermetic subprocess E2E testing issues
- Git worktree testing with editable installs (stale `pip install -e` shadowing)

See the reference files for specific playbook details.