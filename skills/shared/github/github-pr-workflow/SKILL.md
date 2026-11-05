---
name: github-pr-workflow
description: "GitHub PR lifecycle: branch, commit, open, CI, merge."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, CI/CD, Git, Automation, Merge]
    related_skills: [github-auth, github-code-review]
---

# GitHub Pull Request Workflow

## When to Use

Use for branching, committing, opening/updating a PR, inspecting CI, and preparing an approved merge. Use `github-auth` for credentials and `github-code-review` for reviewing someone else's PR.

## Prerequisites

Use `terminal` to check `git status --short --branch`, `gh auth status`, and `gh repo view --json nameWithOwner,defaultBranchRef` (avoid printing credential-bearing git remote URLs). Confirm the target repository and base branch rather than assuming `origin/main`. If `gh` is absent, use the authenticated REST fallback in `github-auth` with `GITHUB_TOKEN` kept out of output and URLs; set `OWNER_REPO=owner/repo` explicitly. Use `references/conventional-commits.md` for commit syntax and `templates/pr-body-feature.md` or `templates/pr-body-bugfix.md` for reviewer-ready bodies.

## Procedure

1. **Branch from the intended base and commit scoped changes.** Protect unrelated work in the tree; stage named files, not `git add .`.
   ```bash
   git fetch origin
   git switch BASE_BRANCH
   git pull --ff-only origin BASE_BRANCH
   git switch -c feat/short-description
   git add path/to/file path/to/test
   git commit -m 'feat: add described behavior'
   git push -u origin HEAD
   ```
   Name feature/fix/refactor/docs/ci branches descriptively. Commit only after running local tests relevant to the change; cite their real results.

2. **Open the PR with an explicit base and check its rendered body.** Use an actual file prepared with `write_file`, and do not leave template placeholders or unchecked boxes implying tests ran.
   ```bash
   gh pr create --base BASE_BRANCH --head "$(git branch --show-current)" \
     --title 'feat: add described behavior' --body-file pr-body.md
   gh pr view --json number,url,baseRefName,headRefName,body
   ```
   Use `--draft` if not ready; add reviewers/labels only when appropriate. In REST, `POST /repos/{owner}/{repo}/pulls` with explicit `title`, `body`, `head`, `base`, and `draft`; the response's `number` is the PR ID. A closing keyword in the body (`Closes #42`) closes the issue on merge to the default branch; `Refs #42` only links it.

3. **Edit an existing PR and verify the exact result.** `gh pr edit N --body-file pr-body.md` may exit nonzero on the deprecated GraphQL Projects-classic `projectCards` field without applying the change. Read the body back even on a zero exit; if the edit did not land, use the REST PR update route:
   ```bash
   gh pr edit N --body-file pr-body.md
   gh pr view N --json body --jq .body
   gh api repos/OWNER/REPO/pulls/N -X PATCH --raw-field body="$(<pr-body.md)" --jq .number
   gh pr view N --json body --jq .body
   ```
   The same PATCH route updates `title`; construct a JSON `--input` payload for multiline/untrusted content if needed. This is a general fallback; do not duplicate it per organization.

4. **Inspect all CI checks at the PR HEAD, not just commit status.**
   ```bash
   gh pr checks N
   gh pr view N --json headRefOid,mergeable,reviewDecision,statusCheckRollup
   gh run list --branch HEAD_BRANCH --limit 10
   gh run view RUN_ID --log-failed
   ```
   The combined commit-status REST endpoint and the separate check-runs endpoint must both be considered (`GET /repos/{owner}/{repo}/commits/{sha}/status` and `.../check-runs`). `gh pr checks --watch` is useful, but confirm a new run/commit SHA before treating a previous red check as current. `references/ci-troubleshooting.md` lists failure patterns.

5. **Diagnose failure at its source, fix, rerun, and re-read.** Check whether the base is already red before blaming a PR. A base-branch `npm audit fix` may drift lockfile toolchains past peer ranges (for example Vite major/version conflicts), causing Vitest `ERR_REQUIRE_ESM` only on the CI Node version; compare the last green resolution, keep intended manifest bumps, regenerate the lockfile, and test under the CI Node version. Do not add retries for flaky tests—fix the race, clock, or external dependency instead. After a code fix, push a specific commit, wait for a **new** CI run on that HEAD, and recheck all required jobs; after three failed repair attempts, report the blocker rather than asserting success.

6. **Check CI shape when inheriting or changing workflows.** Each concern (lint, format, typecheck, unit, e2e/component suites, build, security) should have its own self-contained parallel job when applicable; ensure all actual project suites/scripts execute rather than being commented out. Before renaming/splitting jobs, read required check names: `gh api repos/OWNER/REPO/branches/BASE_BRANCH/protection/required_status_checks`. Update branch protection to the new names **only with authorization**, otherwise an old required check can block merges indefinitely. Record whether branch protection was actually updated.

7. **Stop at the merge approval gate.** Green CI, smoke tests, and clean review mean *ready to merge*, not approved. Get explicit authorization for **this PR**, even if another PR in the batch was approved. Auto-merge also counts as a merge decision and needs that approval. Confirm the current HEAD, mergeability, reviews, checks, and requested method before executing:
   ```bash
   gh pr view N --json number,url,headRefOid,mergeable,reviewDecision,statusCheckRollup
   gh pr merge N --squash --delete-branch
   gh pr view N --json state,mergedAt,mergeCommit,url
   ```
   REST merge: `PUT /repos/{owner}/{repo}/pulls/{number}/merge` with an explicit `merge_method` and `sha` of the approved PR HEAD to prevent merging a changed head. If deleting a remote branch, confirm it belongs to this PR and is no longer needed. Re-read PR/issue state after the merge; never report a merge on the basis of exit status alone.

## Stacked / Dependent PRs

For multiple PRs blocked by one root-cause fix, merge that fix first **only after its own approval**. Refresh each dependent branch against the base, push, verify a new CI run ID and HEAD, then seek approval for each dependent PR separately. If a branch is checked out in a worktree, update it there rather than forcibly checking it out elsewhere. Merge one at a time; the previous merge can introduce a conflict in the next. Resolve modify/delete conflicts according to the base's intentional deletion, then rerun CI. Reconcile protected-branch required check names if jobs changed.

## Pitfalls

- Semgrep Cloud may flag tainted function-parameter values passed into `path.join`/`path.resolve` (`path-join-resolve-traversal`). Validate/contain the path against an allowed root or restructure safely; don't silence the finding with `nosemgrep` without a justified review.
- Do not call a pending check green, treat a stale run as new, merge despite absent required review, or silently retry an error until it disappears.
- REST calls require HTTP error handling and pagination; use encoded JSON for arbitrary PR text rather than handwritten interpolated JSON.

## Verification

Report PR URL/number, base and HEAD SHA, local tests actually run, required check and review status, and whether it is merely ready or has been explicitly approved and merged. For a merge, include the read-back `mergedAt`/merge commit; otherwise leave the PR open.
