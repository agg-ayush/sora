# AWS credential refresh — headless saml2aws

On headless Linux (sora) this is the LIVE path: `~/.hermes/scripts/aws-creds-refresh.sh`
maintains `[devflows]` and `[eswlegal]` via two saml2aws logins (the KeyCloak
assertion carries both roles, verified 2026-10-27). On macOS the current
login is OneLogin OIDC: see `aws-onelogin-refresh.md`. The long-run survival
patterns below apply to both.

DevFactory AWS access uses Keycloak SAML (no AWS SSO). `saml2aws` is configured
with the password in macOS Keychain, so a refresh is fully headless — no
browser, no button-clicking.

## When to use

- Any `aws` CLI call fails with `ExpiredToken`, `InvalidToken`, "security token
  expired/invalid", or an SSO/credentials-expired error.
- The user says "aws token expired" / "refresh aws creds" / "aws login".

**Do NOT** reach for `aws login` (the browser flow) — it writes to
`~/.aws/login/cache/`, not `credentials`, and is superseded by this path.

## Quick path (90% of cases)

```bash
~/.hermes/scripts/aws-creds-refresh.sh
```

The script lives under `~/.hermes/scripts/` on every box (Mac and Linux/EC2);
resolve it via `~`, never a hardcoded home path.

- saml2aws self-throttles: if creds are still fresh it no-ops and exits 0.
- On success it prints `AWS credentials OK (saml2aws trilogy)` and mirrors
  `[trilogy]` → `[default]` in `~/.aws/credentials`, so bare `aws` commands
  work with no `--profile` flag.

Force a fresh login even when creds look valid (e.g. after a password change):

```bash
~/.hermes/scripts/aws-creds-refresh.sh --force
```

Verify afterwards:

```bash
env -i HOME="$HOME" PATH="/opt/homebrew/bin:/usr/bin:/bin" aws sts get-caller-identity
```

Should return `arn:aws:sts::<aws-account>:assumed-role/RAM-AWS-Prod-DevFactory-devflows-Admin/ayushaggarwal`.

## How it works (for debugging)

1. Spawns detached tmux session `saml2aws-refresh` running `saml2aws login -a
   trilogy [--force]`.
2. Watches the pane; sends `Enter` at the `Username` and `Password` prompts
   (keychain supplies the password, so both prompts just need Enter).
3. On `Logged in as:` it kills the tmux session and copies `[trilogy]` →
   `[default]` in `~/.aws/credentials` via python3.

Logs: `/tmp/saml2aws-refresh.log`.

## Auto-refresh hook

A `post_tool_call` shell hook (`~/.hermes/agent-hooks/aws-token-refresh.sh`)
watches `terminal` tool output for AWS token-expiry errors and fires the
refresh script in the background, injecting a `context` note telling the agent
to wait ~10-15s and retry. No manual invocation needed in that path.

## One-time setup (already done on Ayush's Mac)

- `brew install saml2aws` (2.36.x)
- `~/.saml2aws` `[trilogy]` account:
  - provider `KeyCloak`, url
    `https://<idp-host>/auth/realms/devfactory/protocol/saml/clients/aws`
  - username `ayushaggarwal018@gmail.com`, MFA `Auto`
  - role `arn:aws:iam::<aws-account>:role/RAM-AWS-Prod-DevFactory-devflows-Admin`
  - session-duration **3600** (role's MaxSessionDuration rejects 43200 — do
    not raise)
  - aws_profile `trilogy`, region `us-east-1`
- Password in Keychain: `security add-generic-password -s saml2aws -a
  ayushaggarwal018@gmail.com -w <pw>` (script:
  `~/.hermes/scripts/saml2aws-keychain-setup.sh`, run inside tmux — needs a
  real TTY)

## Long-running scripts (S3 migrations, batch loops, multi-minute SSM waits)

The token is a **1-hour session** (`session-duration 3600`, cannot be raised).
Any script that runs longer than that on borrowed creds WILL hit
`ExpiredToken` mid-run, and every in-flight thread/step fails at once — there
is no clean stopping point.

- Call `aws-creds-refresh.sh` **inside the loop, once per
  iteration/batch-item** — not once at script start. It self-throttles, so
  calling it every iteration is cheap.
- Make each iteration's AWS work **idempotent** (`aws s3 sync` instead of
  `cp`, check-before-write) so a mid-run expiry only costs the in-flight item
  and a plain re-run resumes correctly.
- Avoid one `--force`-refreshed token shared across many parallel threads for
  a long op — they die in lockstep at the 1-hour mark. Prefer sequential with
  per-item refresh, or refresh from a supervisor between parallel batches.

## Pitfalls

- **Empty keychain entry**: if the password prompt appears and Enter fails
  with an auth error, the keychain entry is empty/corrupt — re-run
  `saml2aws-keychain-setup.sh` inside a real tmux attach.
- **`Credentials are not expired. Skipping.`**: not an error — saml2aws
  no-op. Use `--force` to override.
- **MFA**: account has MFA `Auto`, but DevFactory Keycloak currently completes
  with password only. If Keycloak starts demanding an OTP, the tmux session
  sits at a token prompt — attach with `tmux attach -t saml2aws-refresh`, type
  it, and the script picks up from there.
