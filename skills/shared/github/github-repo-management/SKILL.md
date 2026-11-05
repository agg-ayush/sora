---
name: github-repo-management
description: "Clone/create/fork repos; manage remotes, releases."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [GitHub, Repositories, Git, Releases, Secrets, Configuration]
    related_skills: [github-auth, github-pr-workflow, github-issues]
---

# GitHub Repository Management

## When to Use

Use to inspect, clone, create, fork, configure, or release GitHub repositories; manage Actions workflows and secrets. Use `github-auth` for credentials, `github-pr-workflow` for PR lifecycle, and `github-issues` for issue operations.

## Prerequisites

Use `terminal` to check `gh auth status` and `gh api user --jq .login`; for an existing repo check `gh repo view OWNER/REPO --json nameWithOwner,defaultBranchRef,viewerPermission`. Do not guess the owner or the default branch from a directory name or assume `main`. If `gh` is unavailable, use `git` plus authenticated REST (`GITHUB_TOKEN`) as in `github-auth`. Pass an explicit `OWNER/REPO`; handle HTTP errors and pagination. The endpoint list is in `references/github-api-cheatsheet.md`. Do not print credentials or place tokens in remotes or command arguments.

## Procedure

1. **Inspect or clone an existing repository.** Confirm exact owner/repo and permissions before actions. Use `gh repo view OWNER/REPO`, `gh repo list OWNER --limit 100`, or `gh search repos QUERY`; then `gh repo clone OWNER/REPO [directory]` (or `git clone https://github.com/OWNER/REPO.git`). For a shallow checkout, `gh repo clone OWNER/REPO -- --depth 1`. Use `git remote` to confirm remote names and `gh repo view --json nameWithOwner` to confirm the target; do not print credential-bearing remote URLs.

2. **Create only after confirming owner (personal vs org), name, visibility, initialization, and source.** Never test permission with a create endpoint: a supposed dry-run `POST /orgs/ORG/repos` creates a real repo. Use read-only membership or permission checks (`gh api orgs/ORG/memberships/USERNAME --jq .role` or `gh api repos/ORG/EXISTING --jq .permissions`) and ask if the target owner is genuinely ambiguous. Examples:
   ```bash
   gh repo create OWNER/NEW_REPO --private --description 'Purpose' --clone
   gh repo create OWNER/NEW_REPO --private --source . --push
   gh repo create OWNER/NEW_REPO --template OWNER/TEMPLATE --private --clone
   gh repo view OWNER/NEW_REPO --json nameWithOwner,visibility,url
   ```
   For REST: `POST /user/repos`, `POST /orgs/{org}/repos`, or `POST /repos/{owner}/{template}/generate` with explicit `name`, `private`, and initialization settings. Do not initialize a remote with README and then blindly push a divergent local history; choose source/push vs initialized/clone deliberately. Confirm actual repo URL and visibility by read-back. A repo created in the wrong owner can require board and agent remapping; do not silently move it.

3. **Fork and sync using the real default branch.**
   ```bash
   gh repo fork UPSTREAM/REPO --clone
   gh repo view YOUR_OWNER/REPO --json nameWithOwner,parent,defaultBranchRef
   gh repo sync YOUR_OWNER/REPO --branch DEFAULT_BRANCH
   ```
   Alternatively `git remote add upstream https://github.com/UPSTREAM/REPO.git`, `git fetch upstream`, then merge/rebase the appropriate default branch and push after checking divergence. REST `POST /repos/{owner}/{repo}/forks` is asynchronous; poll for fork existence instead of assuming an arbitrary sleep is enough. Re-read the fork state/HEAD.

4. **Change settings or protection only for the explicit repo and branch.** Read current settings/protection first; use `gh repo edit OWNER/REPO --description '...' --enable-issues`, `--enable-auto-merge`, or an authenticated `PATCH /repos/{owner}/{repo}`. `PUT /repos/{owner}/{repo}/topics` replaces the full topic list; read current names before changing them. Branch protection `PUT /repos/{owner}/{repo}/branches/{branch}/protection` replaces protection configuration; include all required fields and preserve unrelated existing settings. When CI jobs are renamed, synchronize required-check names as described in `github-pr-workflow`. Read back the exact repo/branch after mutation.

5. **Manage Actions secrets without exposing values.** `gh secret list -R OWNER/REPO` reads names/metadata only. For a user-authorized value, prefer the secure `gh secret set NAME -R OWNER/REPO` interactive flow or supply bytes from an approved secret source without displaying them. Never print secret values, put them in a URL, add them to a tracked file, or include them inline in shell history. REST secret updates require the repository public key and libsodium sealed-box encryption (`GET /actions/secrets/public-key`, `PUT /actions/secrets/{name}`); use `gh` if encryption tooling is unavailable. Verify the name's presence/updated timestamp, not the secret value.

6. **Publish a release only for an approved tag, notes, and assets.**
   ```bash
   gh release create v1.0.0 --repo OWNER/REPO --title v1.0.0 --generate-notes
   gh release create v2.0.0-rc1 --repo OWNER/REPO --draft --prerelease --generate-notes
   gh release view v1.0.0 --repo OWNER/REPO --json tagName,url,isDraft,isPrerelease
   ```
   If attaching artifacts, check build output before `gh release upload`; REST uses `POST /repos/{owner}/{repo}/releases`, then the separate `uploads.github.com` asset endpoint. A release operation creates public or private externally visible state; verify exact tag, draft/prerelease flags, URL, and assets by reading it back.

7. **Inspect and dispatch Actions only when requested.**
   ```bash
   gh workflow list -R OWNER/REPO
   gh run list -R OWNER/REPO --limit 10
   gh run view RUN_ID -R OWNER/REPO --log-failed
   gh workflow run ci.yml -R OWNER/REPO --ref DEFAULT_BRANCH
   gh run rerun RUN_ID -R OWNER/REPO --failed
   ```
   REST equivalents are `GET /actions/workflows`, `GET /actions/runs`, `POST /actions/workflows/{id}/dispatches` (explicit `ref`/`inputs`), and `POST /actions/runs/{id}/rerun-failed-jobs`. Read the new run ID/status after dispatch/rerun; a 204 only confirms request acceptance.

## Pitfalls

- Deleting a repository needs permission and a token with `delete_repo` scope (for classic tokens). Do not archive instead of deletion without authorization. Confirm exact repo and destructive scope before requesting extra scope or proceeding.
- API list endpoints paginate, and a zero-length page does not necessarily mean no data if filtering/pagination was mishandled. Always distinguish error JSON from valid empty data.
- Use read-only permission checks; never create, fork, dispatch, rotate secrets, or publish as a permission probe.

## Verification

Report exact repository URL, visibility, default branch, and the changed setting/release/run ID read back. If a write could not be verified, state that explicitly rather than claiming completion.
