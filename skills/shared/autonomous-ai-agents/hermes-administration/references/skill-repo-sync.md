---
name: skill-repo-sync
description: "Sync custom skills/scripts accumulated live under ~/.hermes/skills and ~/.hermes/scripts into a git-tracked setup repo, without leaking secrets."
---

# Syncing live skills/scripts into a tracked setup repo

Trigger: user asks to "commit the custom skills/scripts we've built up" or
similar — periodic sync of content that accumulated live in
`~/.hermes/skills/` (and adjacent `~/.hermes/scripts/`) but was never
pushed to the git repo that backs it up / is used for `skills.external_dirs`.

## Workflow

1. Diff live category dirs against what the repo already tracks
   (`git status --porcelain` in the repo after copying, or compare listings)
   to isolate genuinely new/custom skills from ones already synced.
2. Group the result into logical commits by theme, not one giant commit:
   e.g. (a) doc/content edits to already-tracked skills, (b) new
   operational scripts (credential refresh, watchers, fixtures), (c) bulk
   new skill packs. Mirrors normal diff-hygiene practice — a reviewer (or
   future you) can see what changed and why per commit.
3. Secret-scan BEFORE committing, but scan for actual key **values**, not
   words. A word-level grep for `token|secret|password|api[_-]?key` will
   hit nearly every skill doc that mentions auth conceptually and produces
   a wall of false positives that's useless to review one by one. Instead
   grep for real key-shape patterns:
   ```
   AKIA[0-9A-Z]{16}              # AWS access key id
   tfy_va_[A-Za-z0-9_-]{10,}     # TrueFoundry
   fw_[A-Za-z0-9]{10,}           # Fireworks
   gh[po]_[A-Za-z0-9]{10,}       # GitHub PAT
   xox[baprs]-[A-Za-z0-9-]{10,}  # Slack
   sk-[A-Za-z0-9]{20,}           # OpenAI-style
   BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY
   ```
   Zero hits on that pattern set across the whole batch is the actual
   "safe to commit" signal — not zero hits on the word-level grep.
4. Also grep for email addresses (`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
   and eyeball the results — the user's own work email is normally fine to
   commit, anyone else's is not.
5. Scripts that read credentials from macOS Keychain or env vars at
   runtime (never hardcoding the value) are safe to commit as-is — that's
   the correct pattern, not something to flag.
6. Run the repo's test suite after staging (if one exists) before pushing,
   same bar as any other commit.
7. The setup repo (`hermes-setup`) is the user's own infra: commit and push
   straight to its `main` on every host and leave both hosts clean and
   identical. For any other repo where work goes on a branch, never leave
   the branch latent: open the PR in the same pass.

## Linking tracked and third-party skills on every host

Don't stop at copying a skill into the setup repo. `setup-hermes.sh` has to make it live on every host, or one host keeps a stale real dir.

1. Use a single `link_skill src dest` helper. If `dest` is a real dir (not a symlink), move it to `$HERMES_HOME/cache/<name>-<timestamp>`, then `ln -sfn`. This keeps the old copy as a backup and makes a rerun a no-op.
2. For a third-party skill (someone else's public skills repo), clone the upstream into `~/repos/<repo>` if it's missing and link the skill dir from the clone. If the clone fails, `log` a warning that names the lost capability. Don't abort the setup.
3. The script runs under `set -euo pipefail`, so never write a bare `[ -f X ] && cmd` as a statement. When the test is false the line returns 1 and kills the whole setup. Use `if [ -f X ]; then cmd; fi`.
4. Verify by extracting the block (`sed -n '/^link_skill() {/,/.../p'`) and running it against a temp `HERMES_HOME` under `set -euo pipefail`. Cover a real dir being replaced and backed up, an idempotent rerun, and the upstream skill missing (must still exit 0 with no link). Then run the real setup on both hosts and check `readlink` plus `hermes skills list`.
5. Before diffing a backed-up real dir against the repo copy, strip the lines you just added (scope note, description suffix). Then confirm that nothing else differs, so no host-only edits were lost.

## Renaming the setup repo's local clone

Keep the local folder name equal to the remote repo name (the remote is
`hermes-setup`). Renaming is a cross-host change, not a `mv`:
1. `mv` the clone on every host (Mac and sora) — a one-host rename leaves
   the other host's paths dangling.
2. Rewrite references outside the repo: shell rc files, `~/.hermes/scripts/`
   (credential wrappers resolve `SCRIPT=$HOME/<repo>/scripts/...`),
   `~/.hermes/agent-hooks/`, watchdog, live skills and their references.
   Archived skills and `__pycache__` can stay.
3. Exclude agent data dirs from blanket `sed` (`.git/`, `.smem/` spools and
   other signed/append-only stores); if one was touched, run its integrity
   check (`smem verify`) before moving on.
4. Re-verify the live consumers right after: AWS refresh wrapper on each
   host, memory provider status, gateway/dashboard active.

## Publishing a shareable integration (fork as source of truth)

When integration code for someone else's tool should be reusable by other
people/agents, it does not live buried in the setup repo:
1. Fork the upstream under the user's account, same repo name.
2. Put the integration in a top-level `integrations/` dir on a feature
   branch (never the fork's `main`); upstream source stays untouched, add
   only a short pointer paragraph to its README.
3. Keep the generic layer free of machine-specific absolute paths; adapters
   may use `$HOME/.hermes`.
4. Re-run the adapter's tests from the fork clone to prove the move broke
   nothing.
5. Delete the copy from the setup repo and replace it with a one-file
   pointer doc (fork URL, branch, contents, activate one-liner) — one source
   of truth.
6. T3 workers are blocked from `git push` by the deny-guard hook (by
   design); the orchestrator pushes the branch from the main session after
   checking the commit, then verifies the branch URL exists.

## Pitfall

Don't let a word-level grep hit ("this file mentions 'password'") block a
commit or trigger a lengthy per-file secret review — check whether it's
prose about the concept or an actual credential value before treating it
as a finding.
