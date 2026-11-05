---
name: github-issues
description: "Create, triage, label, assign GitHub issues via gh or REST."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [GitHub, Issues, Project-Management, Bug-Tracking, Triage]
    related_skills: [github-auth, github-pr-workflow]
---

# GitHub Issues

## When to Use

Create, find, triage, update, or close issues in a GitHub repository. For authentication setup, load `github-auth`; for the linked PR lifecycle, load `github-pr-workflow`.

## Prerequisites

Use `terminal` to check `gh auth status` and `gh repo view --json nameWithOwner --jq .nameWithOwner`. Outside a repository, pass `-R OWNER/REPO` explicitly to each `gh issue` command. Never infer the repo or owner from the current directory name. If `gh` is unavailable, obtain an authenticated `GITHUB_TOKEN` using `github-auth`; do not display the token or embed it in a remote URL. For REST, set `OWNER_REPO=owner/repo` explicitly and use `curl -fsS -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" "https://api.github.com/repos/$OWNER_REPO/..."`. Check HTTP failures before parsing JSON. The Issues REST listing also contains PRs: filter entries with a `pull_request` key. Follow pagination (`Link: rel="next"` or `gh --limit`) before claiming a complete list.

## Procedure

1. **Find the exact issue and read its body/comments before changing it.**
   ```bash
   gh issue list -R OWNER/REPO --state open --label needs-triage --limit 100
   gh issue list -R OWNER/REPO --state all --search 'authentication error'
   gh issue view 42 -R OWNER/REPO --comments
   ```
   REST equivalents: `GET /repos/{owner}/{repo}/issues`, `GET /repos/{owner}/{repo}/issues/{number}`, `GET /search/issues?q=...+repo:{owner}/{repo}`. Search results are not proof that a numbered issue exists; read the exact target.

2. **Write reviewer-agnostic issue text.** State the problem, location, expected/actual behavior, reproduction or acceptance criteria, and verification. Remove session references, internal tracker IDs, batch/round names, person/candidate names in third-party evaluations, and milestone/phase labels. Describe their actual meaning instead; for deferred work, state the feature-dependent trigger in domain language. Use `templates/bug-report.md` or `templates/feature-request.md` as needed; replace placeholders before filing. Do not repeat an internal plan in public issue prose.

3. **Create an issue with explicit title, body, and relevant existing labels.**
   ```bash
   gh label list -R OWNER/REPO
   gh issue create -R OWNER/REPO --title 'Login redirect ignores next parameter' \
     --body-file issue-body.md --label bug
   ```
   For REST use `POST /repos/{owner}/{repo}/issues` with JSON `title`, `body`, `labels`, and optional `assignees`. Do not assume a requested label exists. Read back the new issue number and body.

4. **Triage or edit only the named issue(s).** Classify bug/feature, set an actual repo label and priority when supported, assign when ownership is clear, and comment only if the comment adds a decision or progress. On an internal team issue, write a brief first-person update about the work; avoid an artificial teammate-versus-us ownership boundary unless it is the decision requested.
   ```bash
   gh issue edit 42 -R OWNER/REPO --add-label 'priority:high,bug' --remove-label needs-triage
   gh issue edit 42 -R OWNER/REPO --add-assignee username
   gh issue comment 42 -R OWNER/REPO --body 'Identified the redirect middleware; fixing it.'
   gh issue view 42 -R OWNER/REPO --json state,labels,assignees,comments
   ```
   REST: `PATCH /issues/{number}`, `POST /issues/{number}/labels`, `DELETE /issues/{number}/labels/{name}`, `POST /issues/{number}/assignees`, `POST /issues/{number}/comments` (all prefixed `/repos/{owner}/{repo}`). Check results before claiming changes.

5. **Close or reopen with the intended reason, then verify state.**
   ```bash
   gh issue close 42 -R OWNER/REPO --reason completed
   gh issue close 43 -R OWNER/REPO --reason 'not planned'
   gh issue reopen 42 -R OWNER/REPO
   gh issue view 42 -R OWNER/REPO --json state,stateReason --jq '{state,stateReason}'
   ```
   REST `PATCH /repos/{owner}/{repo}/issues/{number}` accepts `state: closed/open` and closed `state_reason: completed/not_planned`. A merged PR closes an issue only when a closing keyword such as `Closes #42` or `Fixes #42` is in the PR body or commit on the repository's default branch; verify issue state after merge. Use `gh issue develop 42 -R OWNER/REPO --checkout` to create an issue branch if appropriate.

## Bulk Operations and Pitfalls

- Before bulk edits, enumerate the **full** candidate set, exclude PRs from REST issue lists, and confirm scope. For a large set, paginate and print the exact numbers first; avoid a blind `xargs` close of the first page. Then perform the approved edits and re-read each target.
- For REST JSON payloads, use a JSON encoder or `gh api --input` rather than interpolating untrusted issue text into shell-quoted JSON.
- A successful CLI exit is not proof of the intended body, label, assignment, comment, or state. Read back the exact issue and distinguish API failure responses from empty results.

## Verification

Report the issue URL/number and the exact state or fields read back. For triage, report how many candidates were examined versus changed and any issues left unresolved.
