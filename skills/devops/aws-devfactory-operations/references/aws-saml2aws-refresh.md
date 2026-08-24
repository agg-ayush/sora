---
name: aws-saml2aws-refresh
description: Refresh expired DevFactory AWS CLI credentials via saml2aws in a detached tmux session. Use when any `aws` command fails with ExpiredToken / InvalidToken / "security token expired" errors.
version: 1.0.0
metadata:
  hermes:
    tags: [aws, saml2aws, credentials, automation]
---

# aws-saml2aws-refresh — headless DevFactory AWS credential refresh

Ayush's DevFactory AWS access uses Keycloak SAML (no AWS SSO). `saml2aws` is configured with the
password in macOS Keychain, so a refresh is fully headless — no browser, no button-clicking.

## When to use

- Any `aws` CLI call fails with `ExpiredToken`, `InvalidToken`, "The security token included in
  the request is expired/invalid", or an SSO/credentials-expired error.
- Ayush says "aws token expired" / "refresh aws creds" / "aws login".

**Do NOT** reach for `aws login` (the browser flow) — that path is superseded by this skill.

## Quick path (90% of cases)

```bash
/Users/ayush/.hermes/scripts/aws-creds-refresh.sh
```

- saml2aws self-throttles: if creds are still fresh it no-ops and exits 0.
- On success it prints `AWS credentials OK (saml2aws trilogy)` and mirrors `[trilogy]` → `[default]`
  in `~/.aws/credentials`, so bare `aws` commands work with no `--profile` flag.

Force a fresh login even when creds look valid (e.g. after a password change):

```bash
/Users/ayush/.hermes/scripts/aws-creds-refresh.sh --force
```

Verify afterwards:

```bash
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/bin:/bin" aws sts get-caller-identity
```

Should return `arn:aws:sts::<aws-account>:assumed-role/RAM-AWS-Prod-DevFactory-devflows-Admin/ayushaggarwal`.

## How it works (for debugging)

1. Spawns detached tmux session `saml2aws-refresh` running `saml2aws login -a trilogy [--force]`.
2. Watches the pane; sends `Enter` at the `Username` and `Password` prompts (keychain supplies
   the password, so both prompts just need Enter).
3. On `Logged in as:` it kills the tmux session and copies `[trilogy]` → `[default]` in
   `~/.aws/credentials` via python3.

Logs: `/tmp/saml2aws-refresh.log`.

## Auto-refresh hook

A `post_tool_call` shell hook (`~/.hermes/agent-hooks/aws-token-refresh.sh`) watches `terminal`
tool output for AWS token-expiry errors and fires the refresh script in the background, injecting
a `context` note telling the agent to wait ~10-15s and retry. No manual invocation needed in that
path — the hook is the auto-invoke mechanism.

## One-time setup (already done on Ayush's Mac)

- `brew install saml2aws` (2.36.x)
- `~/.saml2aws` `[trilogy]` account:
  - provider `KeyCloak`, url `https://<idp-host>/auth/realms/devfactory/protocol/saml/clients/aws`
  - username `ayushaggarwal018@gmail.com`, MFA `Auto`
  - role `arn:aws:iam::<aws-account>:role/RAM-AWS-Prod-DevFactory-devflows-Admin`
  - session-duration **3600** (role's MaxSessionDuration rejects 43200 — do not raise)
  - aws_profile `trilogy`, region `us-east-1`
- Password in Keychain: `security add-generic-password -s saml2aws -a ayushaggarwal018@gmail.com -w <pw>`
  (script: `~/.hermes/scripts/saml2aws-keychain-setup.sh`, run inside tmux — needs a real TTY)

## Long-running scripts (S3 migrations, batch loops, multi-minute SSM waits)

The token is a **1-hour session** (`session-duration 3600`, cannot be raised — see setup below).
Any script/loop that runs longer than that on borrowed creds (parallel threads, a `for` loop over
dozens of S3 prefixes, a multi-hour SSM poll) WILL hit `ExpiredToken` mid-run, and every in-flight
thread/step fails at once — you don't get a clean stopping point.

**Design long-running AWS scripts to survive this, don't just retry after the fact:**

- Call `aws-creds-refresh.sh` **inside the loop, once per iteration/lesson/batch-item** — not once
  at script start. It self-throttles (no-ops if still fresh), so calling it every iteration is cheap.
- Make each iteration's AWS work **idempotent** (e.g. `aws s3 sync` instead of `cp`, check-before-write)
  so a mid-run expiry only costs the in-flight item, and a plain re-run of the same script resumes
  correctly instead of redoing or corrupting completed work.
- Avoid a single `--force`-refreshed token shared across many parallel background threads for a
  long op — a thread pool that all reads the same soon-to-expire token dies in lockstep at the
  1-hour mark. Prefer a sequential loop with per-item refresh over a big parallel fan-out when the
  total wall time could exceed ~1 hour, or refresh from a supervisor between parallel batches.

## Pitfalls

- **Empty keychain entry**: if the password prompt ever shows and Enter fails with an auth error,
  the keychain entry is empty/corrupt — re-run `saml2aws-keychain-setup.sh` inside a real tmux attach.
- **`Credentials are not expired. Skipping.`**: not an error — saml2aws no-op. Use `--force` to override.
- **MFA**: account has MFA `Auto`, but DevFactory Keycloak currently completes with password only.
  If Keycloak starts demanding an OTP, the tmux session will sit at a token prompt — attach with
  `tmux attach -t saml2aws-refresh`, type it, and the script picks up from there.
- **`aws login` browser flow**: still present on the system (AWS CLI 2.36 feature) but unused by
  this skill. Don't mix the two — `aws login` writes to `~/.aws/login/cache/`, not `credentials`.
