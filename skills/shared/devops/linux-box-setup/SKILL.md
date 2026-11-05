---
name: linux-box-setup
description: Use when migrating Ayush's env to a new Linux box or EC2.
version: 1.0.0
---

# Linux box setup / migration checklist

Verified end-to-end on the Sep 2026 Mac → EC2 (Ubuntu 24.04) migration. Order matters: AWS creds before devpod provider work; gog last (needs a human OAuth step).

## 1. Baseline

- `hermes doctor` — core health. Expect 2 findings on a fresh box: Bedrock ExpiredToken (fix is #3) + missing optional keys.
- Missing-binary sweep: `for b in gog gh aws devpod claude hermes node python3 uv docker rg saml2aws flow; do command -v $b; done`
- `gh auth status`, `aws sts get-caller-identity`, `gog auth doctor --check` — the three auth pillars.

## 2. GitHub (human does the device flow)

`gh auth login` → HTTPS → web browser. Then `gh auth refresh -s read:packages -s project` (private npm scope for `@<org>/*`). Then agent: write `~/.npmrc` with `@<org>:registry=https://npm.pkg.github.com` + the gh token as `_authToken`, chmod 600.

## 3. AWS saml2aws (no keychain on Linux)

- Password file at `~/.config/saml2aws/.trilogy-password` (chmod 600) — one-time human entry.
- Refresh: `~/.hermes/scripts/aws-creds-refresh.sh` — tmux-drives `saml2aws login`, types password from file, mirrors `[trilogy]` → `[default]`.
- Auto-refresh hook `~/.hermes/agent-hooks/aws-token-refresh.sh` must be (a) `chmod +x` — migration strips exec bits, (b) registered: `hermes config set hooks.post_tool_call '[{"matcher": "", "command": "/home/ubuntu/.hermes/agent-hooks/aws-token-refresh.sh", "timeout": 10}]'`, (c) approved — first `hermes hooks test post_tool_call` with `HERMES_ACCEPT_HOOKS=1`, or ask the user to approve the prompt.
- Verify: `env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin:/bin:/snap/bin aws sts get-caller-identity` (aws is /snap/bin — plain sanitized PATH misses it).

## 4. Git plumbing

- `git config --global user.name/email` BEFORE any commit or the author is `Ubuntu <ubuntu@...>`.
- `core.hooksPath=~/.git-hooks` with a no-main-branch `pre-commit` guard; negative-test by attempting an empty commit on main (expect exit 1).
- `ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts`.
- Remote URLs must never embed `gho_` tokens: `git remote set-url origin https://github.com/<o>/<r>.git` (gh credential helper covers auth).

## 5. devpod — LOCAL DOCKER provider

Do NOT `provider add aws` — isolation now = local container, no second EC2.

- `sg docker -c "devpod provider add docker && devpod provider use docker"` (plain `docker` fails: user not in docker group until re-login; `usermod -aG docker ubuntu` for future sessions).
- Workspace: `~/devbox/.devcontainer/{devcontainer.json,post-create.sh,setup-hermes.sh}` from hermes-tier-setup/devbox/.
- `sg docker -c "devpod up ~/devbox --provider docker --ide none"` — background + notify (5-10 min first build).
- Gotcha: stale `/home/devpod/.devpod` agent state from a previous devpod-target life causes `permission denied` writing workspace.json. Fix: `sudo chown -R devpod:devpod /home/devpod/.devpod`. If provider config gets wiped during cleanup: `devpod provider delete docker` (ignore the not-exist error), re-add, re-use.
- Verify inside: `docker exec <container> bash -lc 'node --version; claude --version; hermes --version'`. `devpod ssh devbox -- <cmd>` (non-interactive) has a tunnel quirk in v0.6.15 — use docker exec for scripted checks.
- Human, inside container, when first needed: `gh auth login`, `~/setup-hermes.sh`, one `claude` OAuth.

## 6. gog (Google Workspace)

- Binary: single release tarball from `openclaw/gogcli` → `~/.local/bin/gog`.
- Auth needs a DESKTOP-type `client_secret*.json` (type `installed`, loopback redirects allowed). A web-type client fails with `Error 400: redirect_uri_mismatch` and no file fix can help — redirect URIs are enforced server-side. If the bundle only has client_id, ask for the desktop secret specifically.
- Headless keyring: `GOG_KEYRING_PASSWORD` must be set (store in `~/.hermes/.env` + sourced in rc from `~/.config/gogcli/.keyring-pw`, chmod 600). The gog config DIR needs 755/700 (traverse bit), not 600.
- Flow: `gog auth credentials set <secret.json>` → `gog auth add <email> --services ... --remote --step 1` (paste URL to human) → human returns `127.0.0.1:<port>` redirect URL → `--remote --step 2 --auth-url '<that url>'`. Port is random per attempt — consent page and step 2 must use the same URL/mint.
- Scopes Mac-parity+chat: `calendar,drive,docs,sheets,slides,gmail,chat,contacts,tasks,meet`. `--services user` is not a valid value (email/openid are implicit).
- Verify: `gog auth doctor --check`, then live `gog --readonly drive ls --max 3` + `docs cat`.

## 7. Mac handoff bundle pattern

When migrating FROM the Mac, one consolidated ask to the local agent: gog config dir + client_secret desktop json, `~/.ti-eval-teams-token`, `grep -E "GOG_|TFY_|ANTHROPIC_|NPM_|AWS_" ~/.zshrc` output. Never ask for keychain/keyring dumps — non-transferable, everything re-mints. Shred the bundle immediately after import. AppleDouble `._*` files and `LIBARCHIVE.xattr` tar warnings are noise.

## 8. ti-hiring evaluator

Repo `<org>/ti-hiring` → `~/ti-hiring`. flow lives in `evaluator-workflow/` (NOT repo root — root package.json is husky-only). Needs `read:packages` npmrc (see #2). esbuild postinstall needs `npm install-scripts approve esbuild`. Evaluator RUNS additionally need `~/.ti-eval-teams-token` (chmod 600) with the env-i invocation from memory — never ANTHROPIC_BASE_URL/API_KEY.