# Verify a task already resolved by another PR

A card comment claiming 'fixed in PR #N' is evidence to check, not a reason to re-implement or close blind. Read GitHub's merged state and merge commit, fetch the actual target branch, and test ancestry with `git merge-base --is-ancestor <merge-sha> <target-ref>` (or inspect the merged changes directly when squash/rebase changed SHAs). A matching PR title or a full-SHA grep against abbreviated `git log --oneline` is insufficient.

Use an isolated detached worktree at the target branch's **specific SHA**; do not run tests from a sibling's dirty tree. Install or reference dependencies only when compatible with that revision. For a flaky or hanging test, run the named test repeatedly and the containing suite multiple times, capturing **exit status** and the test runner's labeled summary; grep text alone can mark a failed command as passed. State the number of actual runs and remaining statistical uncertainty rather than asserting a flaky bug is 'proved gone.'

If the merged mechanism and reproduction both match the card's acceptance criteria, close it through the supported board command with PR/SHA and test evidence, and read the card back. Otherwise leave it open with a precise gap. Remove only your clean verification worktree; do not force-remove a directory containing new work or change the shared checkout.
