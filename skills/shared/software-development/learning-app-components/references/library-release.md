---
name: library-release
description: "Release @<org>/learning-app-components from a merged PR: add a customer-facing changeset, merge, wait for the changesets action to raise its chore version PR, merge that, wait for publish, then bump the consumer app. Use when Ayush asks to 'add a changeset', 'release the library', or run the full merge→chore-PR→publish→app-bump flow. Custom mode auto-runs the whole chain end to end. Includes a deterministic merge-when-CI-green script."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [changeset, release, npm, github, library, learning-app-components]
    related_skills: [library-update, github-pr-workflow, pr-description-style]
---

# Release @<org>/learning-app-components

Repo: `/Users/ayush/Trilogy/library`. Package: `@<org>/learning-app-components` (public, published to GitHub Package Registry). Consumer app: `/Users/ayush/Trilogy/app` (pins `^<version>`).

## When to use

- Ayush asks to "add a changeset" / "release the library" / "ship this".
- A feature/fix PR on the library is ready to merge and needs a release entry.
- Ayush asks for the full chain: merge → chore version PR → publish → bump the app.

## The release flow (how this repo ships)

Changesets (`@changesets/cli`) + `changesets/action@v1` in `.github/workflows/ci.yml` (runs on push; the action runs only on `refs/heads/main`):

1. **Feature branch** carries a changeset file `.changeset/<slug>.md` (added alongside the code change, in the same PR).
2. **Merge to main** → the action runs `pnpm run version` (`changeset version`): consumes the changeset, bumps `package.json` version, appends to `CHANGELOG.md`, **deletes the changeset file**, and opens/updates a **"chore: version packages"** PR.
3. **Merge the chore PR** → the action runs `pnpm run release` (`changeset publish`) → publishes the new version to GitHub Package Registry. The chore PR's merge commit is the release point.
4. **Bump the consumer app** → in `/Users/ayush/Trilogy/app`, run the `library-update` skill to pin the newly published version, open a PR, and merge it once CI is green.

The changeset is authored on the feature branch; the actual version bump + changelog + publish happen via the chore PR that GitHub Actions raises after the feature PR merges. You do NOT run `changeset version` or `changeset publish` locally.

**The action reuses one chore PR across cycles.** It updates the same open "chore: version packages" PR (branch `changeset-release/main`) each time new changesets land on main, rather than creating a new PR. So a stale chore PR can accumulate if a release isn't merged — when you search for it, match by title, and verify its body shows the version you expect, not an older one.

## Merging — always via the green-check script

**Never merge a PR with a bare `gh pr merge`.** Always use the deterministic script in this skill's `scripts/merge-pr-when-green.sh`. It waits for all CI checks to finish and merges (squash + delete branch) **only if every check is SUCCESS/pass**. `gh pr checks --watch` returns exit 0 even on failures (unreliable), so the script re-reads the final check states as JSON and refuses to merge on any fail/pending/cancel/neutral.

```bash
# from this skill's directory:
./scripts/merge-pr-when-green.sh <pr-number> [--repo owner/name] [--interval 10]
```
- Exit 0 = merged (all green, mergeable). Non-zero = not merged (prints why).
- Works on macOS bash 3.2 (no `mapfile`).

This replaces the per-PR approval gate for the *mechanism* of merging — but Ayush's approval rule still applies to *whether* to merge a given PR. The script only enforces "CI must be fully green before the merge happens." Get his explicit per-PR (or custom-mode chain) approval first, then run the script.

## Authoring a changeset file

Create `.changeset/<descriptive-slug>.md` on the feature branch:

```markdown
---
"@<org>/learning-app-components": <patch|minor|major>
---

<one concise customer-facing sentence describing what the user experiences.>
```

### Bump type

- **patch** — fix to existing behavior (wrong rendering, bug, regression). Precedents: `fix-currency-dollar-latex` (4.12.2), `numeric-keypad-visuals` (4.12.1), SSR fix (4.7.7), list-rendering fix (4.7.5).
- **minor** — new opt-in capability or new behavior with a backward-compatible default. Precedents: `drag-video-overlay` (4.14.0), `numeric-decimal-comma-support` (4.12.0), `full_screen` overlay (4.13.0). The "defaults to false, existing lessons continue…" pattern signals minor.
- **major** — breaking change to the public API. None in recent history; ask Ayush before using.

When unsure between patch and minor: patch if it fixes wrong behavior; minor only if it adds a new capability learners/consumers couldn't do before.

### Change-note writing style (customer-facing only)

Read 3-5 recent entries in `CHANGELOG.md` before writing. The notes Ayush ships all follow:

- **What the end user experiences**, never implementation/fix/internal detail. No `KaTeX`/`react-katex`/`useEffect`/`DOM`/`regex` jargon. No bug/error narration ("fix a bug where…", "previously crashed"). No internal session/task/agent/process references.
- **One concise summary sentence**, optionally a short follow-up paragraph with a concrete example or the backward-compat reassurance ("the flag defaults to `false`, so existing lessons continue to render in the sidebar").
- **Verify claims of new capability** against what already existed — don't credit a feature with functionality other code paths already had.
- **Author attribution** (`Thanks @agg-ayush!`) and PR/commit links are auto-added by `@changesets/changelog-github` — do NOT write them in the changeset file.
- **Internal-only changes** (test-runner config, build tooling, dev deps) that are invisible to library consumers get **no changeset entry**. If a PR is entirely internal, it still needs at least a patch changeset for the version bump — write a minimal customer-adjacent note or ask Ayush.

Good patch precedent (closest style template):

```
---
"@<org>/learning-app-components": patch
---

Fix currency dollar signs being parsed as LaTeX delimiters

Sentences like "$12.10 minus $1.80 equals $10.30" were being partially
rendered as KaTeX math instead of plain text. Applies the pandoc
closing-delimiter rule: a closing `$` immediately followed by a digit is
not a valid inline-math delimiter.
```

That example names a mechanism ("pandoc closing-delimiter rule") because it's customer-adjacent (affects what learners see). Pure implementation mechanism (useEffect, DOM selectors) stays out.

## Modes

### Default mode — just the changeset + merge

Use when Ayush says "add a changeset" and wants to merge the feature PR, but will handle the chore PR / publish / app bump separately.

1. Author the changeset file on the feature branch (above).
2. Commit + push it as part of (or alongside) the feature PR.
3. Verify the feature PR: `gh pr view <N> --json state,mergeable,mergeStateStatus` — must be `MERGEABLE`, `CLEAN`.
4. **Merge only with Ayush's explicit, per-PR approval**, then via the script:
   ```bash
   ./scripts/merge-pr-when-green.sh <N> --repo <org>/learning-app-library
   ```
5. Stop. Tell Ayush the chore version PR will appear shortly; he can merge it when ready (or ask for custom mode).

### Custom mode — the full chain (auto)

Use when Ayush asks to "merge and release" / "ship it" / "do the full release flow" / "merge, wait for chore PR, merge that, then update the app". Runs the whole chain end to end after he approves merging the feature PR.

**Gate: do not start without explicit approval to merge the feature PR.** The custom-mode pre-approval covers: merging the library feature PR, merging the generated chore version PR, and merging the consumer-app bump PR (all via the green-check script). Once he says merge it:

1. **Merge the feature PR** (green-check script):
   ```bash
   cd /Users/ayush/Trilogy/library
   ./scripts/merge-pr-when-green.sh <N> --repo <org>/learning-app-library
   git checkout main && git pull origin main
   ```

2. **Wait for the chore version PR.** The `changesets/action` runs on the push to main and opens/updates a "chore: version packages" PR within ~1-3 min. Poll:
   ```bash
   gh pr list --repo <org>/learning-app-library --state open --search "chore: version packages" --json number,title,headRefName,createdAt
   ```
   Match by title. If none appears within ~5 min, check `gh run list --branch main --limit 3` — the action may have found no pending changesets (means the changeset wasn't on the merged branch; go back and fix).

3. **Verify the chore PR's contents** before merging:
   ```bash
   gh pr view <choreN> --repo <org>/learning-app-library --json files,body
   ```
   It should touch `package.json` (version bump), `CHANGELOG.md` (new entry), and delete the `.changeset/<slug>.md` file. Confirm the version number and changelog entry are correct. This PR is generated, not hand-written — still verify it.

4. **Merge the chore PR** via the green-check script:
   ```bash
   ./scripts/merge-pr-when-green.sh <choreN> --repo <org>/learning-app-library
   ```

5. **Wait for publish.** Merging the chore PR triggers another `changesets/action` run which this time hits the `publish: pnpm run release` branch and publishes to GPR. Confirm:
   ```bash
   export GITHUB_TOKEN="$(gh auth token)"
   npm view @<org>/learning-app-components version   # must show the new version
   ```
   Retry for ~2-4 min after the chore PR merges until it reflects the new version. If it doesn't advance after ~10 min, check `gh run list --branch main --limit 3` for a failed publish run.

6. **Bump the consumer app.** Load and run the `library-update` skill in `/Users/ayush/Trilogy/app` — it patches `package.json`, syncs both lockfiles, verifies `npm ci` locally, opens a PR, and **merges that PR via the same green-check script once CI is fully green** (the `library-update` skill references this skill's `scripts/merge-pr-when-green.sh`). The custom-mode pre-approval covers merging the app bump PR too.

## Verification

- After the feature PR merges: `git -C /Users/ayush/Trilogy/library log --oneline -2` shows the squash merge on main.
- The chore PR exists and its diff is exactly: `package.json` version bump + `CHANGELOG.md` entry + deleted changeset file.
- After the chore PR merges: `npm view @<org>/learning-app-components version` returns the new version.
- The app bump PR's `git diff --stat` shows only `package.json` + both lockfiles.
- Every merge in the chain was done via `merge-pr-when-green.sh` (all checks green).

## Common pitfalls

1. **Running `changeset version` / `changeset publish` locally.** Don't — the action does it on merge. Local runs corrupt the version/changelog state. You only author the changeset file and merge PRs.
2. **No changeset on the feature branch.** If the feature PR merges without a changeset file, the action finds nothing to version and opens no chore PR (or leaves the stale one unchanged). Always confirm `.changeset/<slug>.md` is committed on the feature branch before merging.
3. **Customer-facing note leaks implementation detail.** Re-read the note; strip any `KaTeX`/`DOM`/`useEffect`/regex/bug-narration. Compare to recent CHANGELOG entries for tone.
4. **Wrong bump type.** A fix is `patch`; a new opt-in capability is `minor`. When unsure, patch — a too-small bump is recoverable, a too-big one mis-signals.
5. **Stale `npm view` (GPR propagation).** Right after publish, `npm view` may still return the old version for a minute or two. Retry with a short delay rather than assuming publish failed.
6. **`GITHUB_TOKEN` not exported for `npm view`/`npm install` against GPR.** Always `export GITHUB_TOKEN="$(gh auth token)"` before any npm command that hits `@<org>` scope (see `library-update` skill).

## Related skills

- `library-update` — the consumer-app bump step (step 6 of custom mode loads this; it also uses this skill's `merge-pr-when-green.sh` to merge the app PR).
- `github-pr-workflow` — general PR lifecycle.
- `pr-description-style` — for the app bump PR body.
