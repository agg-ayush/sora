# AWS credential refresh: OneLogin OIDC (current path)

The current Trilogy AWS login is the OneLogin OIDC script `trilogy-aws-key.py`
(passkey/WebAuthn MFA, STS AssumeRoleWithWebIdentity). It supersedes the
saml2aws/Keycloak path in `aws-saml2aws-refresh.md`. When the user says "use
the refresh script" or "onelogin", this is the one.

## Locate

- Installed at `~/.local/bin/trilogy-aws-key.py` (uv script, deps self-declared;
  run with `uv run`).
- Canonical source: `~/hermes-tier-setup/scripts/trilogy-aws-key.py`.
- If not found, grep: `grep -ril onelogin ~/hermes-tier-setup ~/.local/bin`.
  Do not fall back to the saml2aws script without asking.

## Procedure (headless box)

0. On the headless Linux box (sora), do not start here: run the unattended
   saml2aws refresh (`bash ~/.hermes/scripts/aws-creds-refresh-linux.sh`, see
   SKILL.md) first. Use this OneLogin flow only if that fails.
1. Check state first:
   ```bash
   unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
   aws sts get-caller-identity --profile <profile>
   ```
   Always pass `--profile`: on an EC2 box a bare call returns the instance
   role and looks healthy even when every user profile is expired.
   Decode `exp` of the cached id_token at `~/.aws/onelogin-id-token.json`
   (JWT payload). If still valid, `--smart` refreshes with no login.
2. Check which profile names the box's tooling reads
   (`grep '^\[' ~/.aws/credentials`); on macOS it is `[trilogy]` plus
   `[default]`, on sora `[devflows]`/`[eswlegal]` only. Default `--profile-name` is `saml`, so always pass it.
3. Launch in a background PTY (the prompt must survive across turns):
   ```bash
   uv run ~/.local/bin/trilogy-aws-key.py --headless --profile-name trilogy \
     --select-role <aws-account>:RAM-AWS-Prod-DevFactory-devflows-Admin
   ```
   (terminal background=true, pty=true). Poll once with process_manage to read
   the printed auth URL.
4. Send the user the auth URL and the exact ask: open it, passkey login, COPY
   THE FULL `http://localhost:12345/callback?...` URL from the address bar
   (the page failing to load is expected), paste it back.
5. Feed it with process_manage `submit` to the same session, wait for exit.
6. Mirror `[trilogy]` to `[default]` if bare `aws` commands must work, then
   verify with `aws sts get-caller-identity` (expect the devflows-Admin
   assumed-role ARN).

## Useful flags

- `--smart`: skip auth if the profile's creds are still fresh
  (`--min-refresh-time`, default 15 min).
- `--duration SECONDS`: longer STS session if the role's MaxSessionDuration
  allows; script falls back to the cap automatically.
- `--credential-process`: JSON output for an AWS `credential_process` entry.
- `--logout`: drop the cached id_token.

## Pitfalls

- The id_token lives ~120 min and covers any number of role switches; after
  that a browser passkey login is required again, so unattended long runs
  cannot self-refresh past it. Plan long jobs inside that window or with
  `--duration`.
- `--keyring` is useless under enforced passkey (password grant cannot
  authenticate) and the script refuses plaintext keyring backends on headless
  Linux; rely on the id_token cache instead.
- The `state` in the pasted callback must match the running process; if the
  process died or was relaunched, the old URL is dead. Relaunch and resend.
