---
name: learning-app-components
description: Maintain and release learning-app-components.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [Library, NPM, Node, React, Trilogy]
---

# learning-app-components

Maintain and release `@<org>/learning-app-components` — the headless React/XState lesson-player library (repo `/Users/ayush/Trilogy/library`, published to GitHub Package Registry). Consumer app: `/Users/ayush/Trilogy/app`.

## When to Use

- **Feature scoping** — a customer/product ask lands as "can the player do X" / "block/allow Y behavior" and needs an honest capability + boundary answer before design/ETA.
- **Release** — Ayush asks to "add a changeset", "release the library", "ship it", or run the full merge → chore version PR → publish → app-bump chain.
- **Consumer bump** — Ayush asks to "update"/"bump"/"upgrade" learning-app-components in the app.

## Procedure

### 1. Feature scoping (references/library-feature-scoping.md)

Turn a vague ask into a precisely-scoped answer. Never assert capability from memory or a single web search — grep the source first:
- **Config surface:** `LearningPlayerProviderProps*` in `src/context/LearningPlayerProvider.tsx` (`debugMode`, `playbackSpeedPreset`, `autoAdvance`, etc.).
- **Behavior:** the relevant machine in `src/machines/` for the event/guard that would gate it.
- **Persistence:** grep `localStorage|sessionStorage|persist|storage` — the library has none today.

Draw the **library-vs-platform boundary explicitly every time**: the library is a headless, single-lesson-instance component (no `userId`, no storage, no "other lessons"). Anything needing state to survive a remount, span lessons, or know who the student is is **structurally the consuming platform's job** — say so plainly. If the user pushes back with "don't we already have a flag for this", re-search with a more targeted pattern before repeating the claim.

### 2. Release flow (references/library-release.md)

Changesets + `changesets/action@v1` in CI:
1. Feature branch carries `.changeset/<slug>.md` in the same PR.
2. Merge to main → action opens/updates a "chore: version packages" PR (reuses ONE chore PR across cycles — match by title, verify body shows the expected version).
3. Merge the chore PR → action publishes to GPR. **Never run `changeset version`/`publish` locally.**
4. Bump the consumer app via the `library-update` skill.

**Never merge with a bare `gh pr merge`** — always use `./scripts/merge-pr-when-green.sh <N> --repo <org>/learning-app-library` (waits for all-green, refuses on fail/pending/cancel; `gh pr checks --watch` exit code is unreliable). Ayush's explicit per-PR approval still gates *whether* to merge; the script only enforces CI-green.

**Changeset authoring:** bump type — `patch` for a fix to existing behavior, `minor` for a new opt-in capability with a backward-compatible default, `major` only after asking Ayush. Change note is **customer-facing only**: what the end user experiences, no `KaTeX`/`useEffect`/`DOM`/regex jargon, no bug narration, no internal session/task references. Read 3-5 recent `CHANGELOG.md` entries for tone. Author attribution and PR links are auto-added by `@changesets/changelog-github` — don't write them. Internal-only changes (test config, build tooling) still need at least a patch changeset for the version bump.

**Custom mode (full chain):** after Ayush approves merging the feature PR, the pre-approval covers the whole chain — merge feature PR → poll ~1-3 min for the chore PR → verify chore PR diff (package.json + CHANGELOG.md + deleted changeset) → merge chore PR → confirm `npm view @<org>/learning-app-components version` advances (retry 2-4 min for GPR propagation) → run `library-update` in the app and merge its PR via the same script.

### 3. Consumer bump (references/library-update.md)

Repo is **pnpm-primary** (`pnpm-lock.yaml` live) but CI runs `npm ci` against `package-lock.json` — **both lockfiles must stay in sync**, and `.npmrc` must be in the `quality.yml` sparse-checkout list or CI 404s on `@<org>` packages.

```bash
cd /Users/ayush/Trilogy/app
export GITHUB_TOKEN="$(gh auth token)"          # required for every npm call against GPR
npm view @<org>/learning-app-components version
# patch package.json spec line, preserving the range operator
pnpm install          # updates pnpm-lock.yaml
npm install           # syncs package-lock.json
npm ci                # must exit 0 — this is exactly what CI runs
```

`pnpm install` also edits `pnpm-workspace.yaml` (auto-appends to `minimumReleaseAgeExclude`) — that file is **untracked**; do NOT commit it. Commit only `package.json` + `pnpm-lock.yaml` + `package-lock.json` on a `chore/bump-learning-app-components` branch, open a minimal conventional-commit PR, then merge via the `library-release` skill's `merge-pr-when-green.sh` (with Ayush's approval, or under custom-mode chain pre-approval).

## Pitfalls

- Asserting "the library doesn't have X" from memory — grep the provider props and machine source first; a wrong claim repeated after pushback is worse than a wrong claim once.
- Running `changeset version`/`publish` locally — corrupts version/changelog state; the action does it on merge.
- Feature PR merged without a `.changeset/<slug>.md` — no chore PR appears; the stale one sits unchanged.
- Changeset note leaking implementation detail — strip `KaTeX`/`useEffect`/bug-narration before shipping.
- Merging with bare `gh pr merge` or trusting `gh pr checks --watch` exit 0 — use `merge-pr-when-green.sh`.
- **`package-lock.json` out of sync (THE recurring one)** — `pnpm install` doesn't touch it; CI's `npm ci` fails with `EUSAGE`. Always run `npm install` after `pnpm install`, verify `npm ci` exits 0 locally.
- Committing `pnpm-workspace.yaml` — untracked by design; leave it out.
- `GITHUB_TOKEN` not exported → E401 against GPR even though `gh` works.
- Editing a workflow file without the `workflow` OAuth scope → push rejected; `gh auth refresh -s workflow` first.
- Crediting a feature with capability another code path already had — verify the claim against existing code.

## Verification

- Scoping: every capability claim cites `file:line` in provider props or machine source; the library-vs-platform boundary is stated in the answer.
- Release: chore PR diff is exactly `package.json` + `CHANGELOG.md` + deleted changeset; `npm view ... version` returns the new version post-merge; every merge in the chain went through `merge-pr-when-green.sh`.
- Consumer bump: `npm ci` exits 0 locally; `git diff --stat` shows only `package.json` + both lockfiles; CI green on the PR before merge.

## References

- `references/library-feature-scoping.md` — full triage workflow, boundary language, scope-creep patterns.
- `references/library-release.md` — full release flow, changeset style guide with precedents, custom-mode chain.
- `references/library-update.md` — full consumer-bump procedure, dual-lockfile rules, GPR auth dance.
