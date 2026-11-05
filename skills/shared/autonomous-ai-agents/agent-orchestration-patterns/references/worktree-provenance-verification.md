# Worktree provenance verification

A new branch created without an explicit start point inherits the current checkout's HEAD, which may be another task's branch. Before dispatch, fetch the intended base and create the worktree with an **explicit** verified start point: `git worktree add -b <branch> <worktree-path> <base-ref-or-sha>` (check installed Git syntax). Record the base SHA and inspect `git log <base>..HEAD`; on a new branch it should be empty. Do not assume `origin/main` is the target base.

If unexpected commits appear, inspect `git worktree list`, reflog/history, dirty tracked and untracked files, and whether a worker has begun. Do not run `git reset --hard` as a default repair: it destroys local changes. If no work began, create a fresh branch/worktree from the correct base; otherwise preserve a backup ref/patch and agree on the safe rebase or cherry-pick. Verify every branch's actual diff and provenance before pushing or presenting a PR as scoped.

Related: `iterative-fix-loop-conflict-resolution.md` handles legitimate sibling changes to the same region; this reference catches accidental ancestry contamination before implementation.
