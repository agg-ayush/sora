---
name: library-update
description: "Bump @<org>/learning-app-components to its latest version and raise a PR. Handles GitHub Package Registry auth via `gh auth token`, updates package.json + BOTH lockfiles (pnpm-primary repo; CI runs npm ci, so package-lock.json must be synced too), verifies with `npm ci`, and opens a conventional-commit PR. Use when Ayush asks to 'update'/'bump'/'upgrade' learning-app-components."
version: 0.5.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [npm, dependencies, github, pr, maintenance]
    related_skills: [library-release, github-pr-workflow, github-auth]
---

# Bump @<org>/learning-app-components + Raise a PR

Bump `@<org>/learning-app-components` to its latest published version,
update `package.json` + BOTH lockfiles (`pnpm-lock.yaml` AND `package-lock.json`),
verify reproducibly, and open a PR. The package is published to GitHub Package
Registry (GPR), which needs an auth dance — this skill encodes it so you don't
have to rediscover the token flow each time.

## Prerequisites

- Repo: `/Users/ayush/Trilogy/app` (has `package.json` + `pnpm-lock.yaml` + `package-lock.json`).
- `gh` CLI authenticated with `read:packages` scope (`gh auth status`).
- Clean working tree, `main` branch up to date.
- Never commit on `main` — always branch first.

## Repo conventions (read before touching anything)

The app is **pnpm-primary** — `pnpm-lock.yaml` is the live lockfile developers
install from. BUT the Code Quality CI workflow (`.github/workflows/quality.yml`)
runs **`npm ci`** against `package-lock.json`. Two hard rules follow:

1. **Both lockfiles must stay in sync.** `pnpm install` updates only
   `pnpm-lock.yaml`; it does NOT touch `package-lock.json`. After bumping, run
   `npm install` to sync `package-lock.json`, or CI fails with `EUSAGE
   ("lock file's X does not satisfy Y")`.
2. **CI needs `.npmrc` for GPR.** The workflow uses sparse-checkout; `.npmrc`
   (which maps `@<org>` scope to `https://npm.pkg.github.com`) MUST be
   in the sparse-checkout list, else `npm ci` falls back to registry.npmjs.org
   and 404s on `@<org>` packages. It is included as of the 4.14.1 bump
   — if you edit `quality.yml` and remove it, CI breaks again.

## Step 1 — Current version

```bash
cd /Users/ayush/Trilogy/app
grep '"@<org>/learning-app-components"' package.json   # e.g. "^4.12.2"
```

## Step 2 — Resolve auth + look up the latest version

The repo's `.npmrc` points the `@<org>` scope at GPR and references
`${GITHUB_TOKEN}`, which is usually NOT exported in the shell. Derive it from
`gh` (which has `read:packages`) and export it for every npm call in this flow:

```bash
export GITHUB_TOKEN="$(gh auth token)"
npm view @<org>/learning-app-components version        # latest, e.g. "4.13.0"
```

- E401 → token lacks `read:packages`; run `gh auth refresh -s read:packages`.
- E404 → registry/namespace mismatch; confirm `.npmrc` maps `@<org>`
  to `https://npm.pkg.github.com`.

## Step 3 — Bump the spec in package.json

Use `patch` to change only the version spec line. Preserve the existing range
operator (`^` unless the repo uses something else):
```
old: "@<org>/learning-app-components": "^4.12.2"
new: "@<org>/learning-app-components": "^4.13.0"
```

## Step 4 — Install + verify reproducibility (sync BOTH lockfiles)

The bump must update both `pnpm-lock.yaml` and `package-lock.json`. Run all of
these; the first two are the install, the last is the reproducibility proof:

```bash
export GITHUB_TOKEN="$(gh auth token)"
pnpm install                    # updates pnpm-lock.yaml (primary)
npm install                     # syncs package-lock.json to the same version
npm ci                          # must exit 0 — proves package-lock.json is in sync (CI runs this)
grep -A2 'node_modules/@<org>/learning-app-components"' package-lock.json | head -3
```

`npm ci` exiting 0 is the exact command CI runs — if it fails locally with
`EUSAGE`, `package-lock.json` is stale; re-run `npm install`.

**`pnpm install` also edits `pnpm-workspace.yaml` — do NOT commit it.** pnpm
auto-appends the bumped package to `minimumReleaseAgeExclude` in
`pnpm-workspace.yaml` (e.g. adds `@<org>/learning-app-components@4.14.2`).
That file is **untracked** in this repo (never committed) — leave it untracked
and out of the commit. The commit in Step 5 must be ONLY `package.json`,
`pnpm-lock.yaml`, `package-lock.json`. If `git status` shows
`pnpm-workspace.yaml` (or `.gitattributes`) as modified/untracked after install,
that's expected — don't `git add` it, and don't be alarmed.

## Step 5 — Branch, commit, push, open PR

```bash
git checkout -b chore/bump-learning-app-components
git add package.json pnpm-lock.yaml package-lock.json
git commit -m "chore: bump @<org>/learning-app-components to ^<new-version>"
git push -u origin HEAD
```

Verify `git diff --stat` shows `package.json` + `pnpm-lock.yaml` +
`package-lock.json` (the version-line change in each; `package-lock.json`
should be a small delta, `pnpm-lock.yaml` may be larger due to transitive
peer-resolution churn).

Create the PR with a minimal, collaborator-facing body (what changed + test plan
only — no internal narration):

```bash
gh pr create --title "chore: bump @<org>/learning-app-components to ^<new-version>" --body "$(cat <<'EOF'
## Summary
- Bumps `@<org>/learning-app-components` from `^<old>` to `^<new>`.

## Test Plan
- [ ] `npm ci` succeeds from a clean checkout (this is what CI runs)
- [ ] `pnpm install` resolves `@<org>/learning-app-components@<new>`
EOF
)"
```

## Step 6 — Watch CI, then merge via the green-check script

**Never merge with a bare `gh pr merge`.** Use the deterministic
`merge-pr-when-green.sh` script from the `library-release` skill (it owns the
script and documents why the raw `gh pr checks --watch` exit code is
unreliable). It merges (squash + delete branch) **only if every check is
SUCCESS/pass**; on any fail/pending/cancel it exits non-zero and does not merge.

```bash
~/.hermes/skills/software-development/library-release/scripts/merge-pr-when-green.sh <N> --repo <org>/learning-app
```

Exit 0 = merged. Non-zero = not merged (prints why). Get Ayush's explicit
per-PR approval first (or run under the `library-release` custom-mode chain,
which pre-approves the app bump PR merge), then run the script. After it
merges:

```bash
git checkout main && git pull origin main
```

## Pitfalls

- **`GITHUB_TOKEN` not in env** → `npm view`/`npm install` hit E401 against GPR
  even though `gh` works fine. Always `export GITHUB_TOKEN="$(gh auth token)"`
  for the npm commands in this flow.
- **`package-lock.json` out of sync (THE recurring one)** → the repo is
  pnpm-primary but CI runs `npm ci`. `pnpm install` updates only
  `pnpm-lock.yaml`; `package-lock.json` stays stale, so CI fails with `EUSAGE
  ("lock file's X does not satisfy Y")`. Always run `npm install` after
  `pnpm install` to sync it, and verify `npm ci` exits 0 locally before pushing.
- **`.npmrc` missing from CI sparse-checkout** → `@<org>` scope doesn't
  map to GPR in CI, `npm ci` falls back to registry.npmjs.org and 404s. Keep
  `.npmrc` in the `quality.yml` sparse-checkout list (added in the 4.14.1 bump;
  don't remove it when editing that workflow).
- **Committing on `main`** → pre-commit hooks reject it; always branch first.
- **`pnpm run lint` crashes once with `ERR_UNHANDLED_REJECTION`** → the committed
  `.npmrc` carries a project-level GPR credential that pnpm refuses to expand
  ("Ignored project-level auth setting … environment variables are not expanded
  in registry credentials that come from a project .npmrc"). That warning path
  can sporadically surface as a Node `ERR_UNHANDLED_REJECTION` crash with
  `[ELIFECYCLE] Command failed` — NOT a lint finding. Rerun once; a clean run
  prints "No ESLint warnings or errors". If it's the auth warning, it's
  transient/unrelated to your bump — don't chase it as a code problem.
- **Reformatting a lockfile** → `npm install`/`pnpm install` should only change
  this one package's entries (plus its transitive peer-resolution churn in
  `pnpm-lock.yaml`). If `git diff --stat` is far larger than expected for one
  dependency, something rewrote the whole lockfile — investigate before committing.
- **Wrong range operator** → keep the original `^` (or whatever the repo uses);
  don't silently loosen or tighten the spec.
- **Editing a workflow file without the `workflow` scope** → pushing a change to
  `.github/workflows/*` is rejected unless the git credential has the `workflow`
  OAuth scope. `gh auth refresh -s workflow` (complete the device flow in a
  browser), then update the OSX keychain git credential so the push picks up the
  new token.
