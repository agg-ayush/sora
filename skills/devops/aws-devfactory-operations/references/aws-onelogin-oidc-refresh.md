---
name: aws-onelogin-oidc-refresh
description: Refresh DevFactory AWS CLI credentials via OneLogin OIDC (trilogy-aws-key.py) — replaces saml2aws/Keycloak, which DevFactory is retiring.
version: 1.1.0
metadata:
  hermes:
    tags: [aws, onelogin, oidc, credentials, migration]
---

# aws-onelogin-oidc-refresh — replaces saml2aws/Keycloak

DevFactory is retiring DevConnect (Keycloak SAML) in favor of OneLogin OIDC. The
replacement tool is `trilogy-aws-key.py` (tracked in
`~/hermes-setup/scripts/trilogy-aws-key.py`, deployed per host to
`~/.hermes/scripts/trilogy-aws-key.py`). It uses the **same corporate password** as the old
saml2aws login.

## Two auth paths in the script

1. **Password grant (`--password "$PW"`)** — OIDC Resource Owner Password grant, fully
   non-interactive, no browser. This is the unattended path; it does not depend on any cached
   id_token, so it renews indefinitely. Source the password from a 600-mode file or the OS
   keychain, never inline in a committed script.
   - **For this user's account the grant returns `Password login failed: MFA is required for
     this user`** (verified on the remote box). The script then falls back to the browser flow.
     There is no IP allow/deny filtering, so do not explain MFA differences by egress IP.
   - **A "successful" grant run that printed `Opening browser for OneLogin authentication...`
     did NOT succeed via the grant**: the grant failed and the browser flow completed off an
     existing SSO session. Only call the grant working if no browser line appears in stderr.
   - **Touch ID on macOS is the local keychain releasing the stored password**; do not infer the
     OneLogin factor from it. The factor was then observed directly on the OneLogin login page
     (see "Probing the login page" below): after username + password the SPA shows
     `WebAuthn — Verifying your WebAuthn authenticators now.` So the account's browser-flow MFA
     is WebAuthn; a server with no authenticator cannot complete it, and the grant's MFA wall
     has no typed-OTP escape unless an OTP factor gets enrolled on the account.
   - Constraints that are settled: IT asks are off the table; the Mac is not always on, so a
     Mac-as-token-source bridge fails the unattended goal.
   - The Mac "works unattended" only because its browser holds a live OneLogin SSO session
     cookie, so the browser fallback auto-completes. That cookie is the key-holding mechanism;
     reproduce it on the remote box (see "SSO-cookie browser path" below) instead of fighting
     the grant.
2. **Browser authorization_code (PKCE)** — interactive; caches an id_token at
   `~/.aws/onelogin-id-token.json` that lives ~120 min (check `exp`). `--smart` reuses it
   headlessly only while valid. No `offline_access`, no refresh_token, so no silent renewal
   past the window. `--headless` only prints a URL for a human to open.
   - On a remote box always add `--headless`: without it the script waits on a
     `localhost:12345/callback` that no browser on the box will ever hit, and hangs. With
     `--headless` the user opens the URL locally, completes OneLogin, and pastes the failed
     localhost redirect URL back into the pane. Verified working cold-start path.
   - The user reaches the remote box through a WezTerm mux pane; give commands to run in
     that pane, not `ssh devbox` wrappers. Never pass placeholder values like `--password
     dummy`; let the script prompt.

## Correct invocation (wrapper form)

```bash
PW=$(cat ~/.config/saml2aws/.trilogy-password)   # or `security find-generic-password -w ...` on macOS
timeout 90 python3 ~/.hermes/scripts/trilogy-aws-key.py \
  --credential-process --quiet \
  --role admin --select-role "RAM-AWS-Prod-DevFactory-devflows-Admin" \
  --profile-name trilogy --login ayushaggarwal018@gmail.com \
  --password "$PW" --min-refresh-time 15 < /dev/null 2>>"$LOG"
```

- `--select-role` takes the **bare role name only**, no `<aws-account>:` prefix. The prefixed
  form fails with an error that reads like a bad password ("Invalid user credentials").
- Success output is a `credential-process` JSON blob
  (`Version`/`AccessKeyId`/`SecretAccessKey`/`SessionToken`/`Expiration`). The wrapper writes it
  to `[trilogy]` and mirrors `[default]` in `~/.aws/credentials` (chmod 600).
- Keep the wrapper path `~/.hermes/scripts/aws-creds-refresh.sh` so the `post_tool_call`
  auto-refresh hook needs no rewiring; `--force` sets `--min-refresh-time 0`.

## Switching a host to OneLogin

1. Deploy the script to the host; check `python3 -c 'import boto3, requests'`.
2. Run the password grant by hand with stderr visible. If it says MFA is required, do not rewire
   that host to the grant; use the SSO-cookie browser path (target) with keep-hot as the bridge.
3. Rewrite the wrapper, run it with `--force`, then `aws sts get-caller-identity --profile
   trilogy` must return the `RAM-AWS-Prod-DevFactory-devflows-Admin` assumed-role ARN. Verify
   the access key changed, not just that a call succeeded (an older key may still be valid).
4. Repeat per host; a working Mac says nothing about a remote box.

## Wrapper pitfalls

- **Never combine a pipe with a heredoc on the same python**: `printf "$out" | python3 - <<EOF`
  feeds the heredoc as stdin and the piped JSON is lost, so credentials silently never get
  written while the script exits 0. Use `python3 -c '...'` reading `sys.stdin`.
- **Do not discard the script's stderr** (`2>/dev/null`); the MFA-required and role errors only
  appear there. Append it to the log.
- **Always wrap in `timeout` with `< /dev/null`**: on password-grant failure the script falls back
  to opening a browser and blocks forever in a cron/hook.
- **Call it as `python3 /path/trilogy-aws-key.py`**, not via its `uv run --script` shebang; `uv`
  is often absent from cron/hook PATH.
- **Validate stdout is JSON before writing**; a deprecation warning can precede the blob.
- **`--save-keychain`/`--keyring` prompt interactively even with `--login`/`--password`.** Seed
  the macOS keychain with `security add-generic-password -s <service> -a <email> -w <pw> -U`
  after confirming the service/account names the script reads.
- stock macOS `python3` needs `pip3 install --user boto3 requests`.

## SSO-cookie browser path (target for MFA-gated remote hosts)

The script's browser flow binds `localhost:12345/callback` and calls `webbrowser.open(url)`.
Python's `webbrowser` honors `$BROWSER` verbatim, so no script change is needed: export
`BROWSER="/usr/bin/google-chrome --headless=new --user-data-dir=$HOME/.aws/onelogin-chrome
--no-first-run --disable-gpu"` in the wrapper and run with `--browser` (forces the browser path;
without it a valid cached id_token short-circuits and the browser path is never exercised).
Verified pieces: `$BROWSER` is picked up, headless Chrome loads the OneLogin auth page, the
callback server waits. Without a session cookie it times out after 2 min (expected).

- Bootstrap once: start Chrome on the box with the same `--user-data-dir` plus
  `--remote-debugging-port=9223` (run it backgrounded; foreground blocks the tool call), tunnel
  `ssh -N -L 9223:127.0.0.1:9223 devbox`, user drives the login via `http://localhost:9223`.
- Lifetime is then bounded by OneLogin's SSO session, not the 2h id_token. Until an unattended
  mint with a dead cache is observed, report this path as pending, not working.
- The login inside the remote Chrome hits the WebAuthn step, and the user's authenticator lives on
  their Mac, not the box, so the DevTools-tunnel bootstrap cannot finish the login by itself. How
  to seed the cookie is still open; do not present any bootstrap as working until it is observed.

## Probing the login page (observe the MFA step instead of guessing)

Drive the real OneLogin SPA from the box with Hermes' bundled `agent-browser` CLI against a
Chrome you start on the persistent profile:

```bash
AB=~/.hermes/tools/agent-browser-*-linux-x64/bin/agent-browser-linux-x64   # binary name has the arch suffix
nohup /usr/bin/google-chrome --headless=new --user-data-dir=$HOME/.aws/onelogin-chrome \
  --remote-debugging-port=9224 --no-first-run --disable-gpu about:blank >/tmp/chrome-ol.log 2>&1 &
$AB connect 9224
$AB open https://<idp-host>/login
$AB snapshot -i                 # refs: Username textbox, Continue button
$AB fill @eN "<email>"; $AB click @eM; $AB snapshot -i   # then Password textbox
$AB fill @eN "$PW";     $AB click @eM
$AB get text body               # shows the MFA step text; snapshot -i only lists links there
```

- Re-snapshot after every click; refs go stale on each page change.
- Use `get text body` (not `text`/`url`, which are not commands) to read status pages.
- Before concluding the account has no alternative factor, wait out the WebAuthn step and
  snapshot again for any "other options"/factor-picker link; one screen is not proof of absence.
- Kill the probe Chrome afterwards so it does not hold the profile lock.

## Keep-hot design (bridge, not the solution)

The user treats keep-hot + Telegram-alert-on-lapse as a workaround. Do not present it as
solving MFA or close the topic on it; keep pursuing a no-human path (SSO cookie above).

One MFA'd login mints a ~120-min id_token; STS re-mints within that window need no OneLogin
auth. So an hourly refresh keeps it alive indefinitely while the host ticks.

- Script `~/.hermes/scripts/aws-keep-hot.sh` per host: run `aws-creds-refresh.sh`; on failure
  decode `exp` from `~/.aws/onelogin-id-token.json`; if TTL > 15 min just retry next tick, else
  (remote box) send a Telegram alert containing the `--headless` login command, (Mac) log that
  the next interactive use will prompt Touch ID.
- Schedule as a no-agent Hermes cron: `hermes cron create --name <host>-aws-keep-hot --script
  aws-keep-hot.sh --no-agent "0 * * * *" "AWS creds keep-hot"`. `--script` takes a bare
  filename relative to `~/.hermes/scripts/`; absolute paths are rejected.
- Only a fully cold token (host off/token lapsed >2h) needs the user, once, via the headless URL.
- Wrap remote `hermes cron create` in `timeout 60`; a first run of the keep-hot script inside the
  same ssh call can exceed the tool timeout and the cron never registers. Verify with
  `hermes cron list`.

## Diagnosing auth from scratch (evidence ledger)

When the auth picture gets confused or the user says to start over, drop all prior conclusions
and rebuild facts on one host only:
1. Have the user run the script bare (`python3 ~/.hermes/scripts/trilogy-aws-key.py
   --profile-name trilogy`, plus `--headless` on a remote box) and let it prompt in its own order.
2. Record each observed outcome as a numbered fact (grant result, token `exp`, wrapper exit,
   `aws sts get-caller-identity` ARN). Mark everything else explicitly as unknown.
3. After a fresh mint, run the wrapper before testing `aws sts`: `~/.aws/credentials` still holds
   the stale keys until the wrapper writes, so an `ExpiredToken` right after login is not a failure.

Do not cross-correlate hosts, propose fixes, or explain mechanisms until the ledger supports
them; speculative explanations (IP policy, passkey MFA) were repeatedly wrong and rejected.
When inferring from absence (e.g. no `MFA OTP token:` prompt means OneLogin sent no
`mfa_token`), say it in one line; do not pile on case trees or extra debug runs unless asked,
the user flags that as overcomplicating.

## Answering lifetime questions

Answer from the script source and OneLogin docs, never inference: grep for `grant_type`,
`offline_access`, `refresh_token`, `mfa_token`. Speculation ("probably renews silently") gets
rejected. When the user asks for truly unattended operation, try the password grant first; if the
host is MFA-gated, fall back to the keep-hot cron above. Short answers when asked "short":
one line yes/no plus the reason.
