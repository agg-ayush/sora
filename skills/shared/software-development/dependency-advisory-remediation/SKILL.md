---
name: dependency-advisory-remediation
description: Use when clearing Dependabot or npm audit advisories.
version: 0.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Security, Dependencies, npm, Dependabot]
    related_skills: [tier2-orchestration, github-pr-workflow, pr-description-style]
---

# Dependency advisory remediation

Clear a batch of Dependabot / `npm audit` advisories in one coordinated PR,
with zero dismissals unless the user explicitly allows them.

## When to Use

- A repo has open Dependabot alerts or a non-zero `npm audit` to clear.
- Grouping several Dependabot PRs into one coordinated upgrade.

## Procedure

1. **Baseline.** On a clean checkout of the PR base (detached worktree, not a
   stash cycle), record `npm audit --json` counts by severity and the full test
   suite result. This is the comparison point for "no new failures".
2. **Map each advisory to its fix route** before touching anything:
   - Direct dependency with a patched release → bump it. When the advisory
     range covers the whole current major (e.g. all of 3.x), the minimal fix is
     the next major; read its migration notes and budget for compat edits.
   - Transitive with a parent that has a newer release pulling the fix → bump
     the parent.
   - Transitive where every consumer pins a vulnerable range → `overrides` in
     package.json. Check `npm view <consumer> dependencies` for each consumer
     first; an override that violates a consumer's declared range still
     installs but can break that consumer at runtime.
   - Fixable within existing ranges → regenerate the lockfile entry
     (`npm update <pkg>`) before reaching for overrides.
3. **Apply, then iterate `npm audit` to 0.** After each change run `npm ls
   <pkg>` to confirm every copy resolved to the patched version; `npm ls`
   marks overrides that didn't take as `invalid`.
4. **Verify fully, yourself:** `npm ci` (clean install from the lockfile) on
   the CI Node major, then test, type-check, lint, format check and build.
   Lint/build exercise toolchain packages the test suite never loads, so an
   override in the ESLint tree only fails there.
5. **PR body:** per-advisory-group what moved and why that version is the
   minimum, any override with its reason, deviations from plan, and
   post-merge smoke suggestions for runtime-native packages (sharp, etc.).

## Pitfalls

- **Before accepting "package vN breaks consumer X", read the actual error and
  the package's `exports`/`main` (`npm view <pkg>@<ver> exports main type`).**
  A dual-format package can be fine under `require` but fail under an ESM
  default import. Fix the importing side, not the override: e.g. if an ESM
  entry of a config helper default-imports a now-named-export-only dependency,
  load the helper's CommonJS entry via `createRequire` in the config file, with
  a one-line comment saying why.
- **A newer major of the consumer is not automatically the fix** — check that
  the new major's own dependency range is outside the advisory, and that the
  rest of the toolchain's peer ranges accept it.
- **Floating tags (`"latest"`) in package.json resolve differently per install**;
  replace with a caret pin at the smallest version that type-checks against the
  other bumps.
- **Type-check after every SDK bump** — sibling packages of an SDK family
  (client + SSR helper, plugin + bundler) often need lockstep bumps that only
  `tsc` or a peer-range error reveals.
- **Tool engine floors:** a bump may raise `engines.node`. Confirm it matches
  CI and deploy Node, and call it out in the PR body.
- **No patched release exists and the only consumer is dead tooling:** pin
  below the advisory range via override and state that in the PR, rather than
  dismissing the alert.
