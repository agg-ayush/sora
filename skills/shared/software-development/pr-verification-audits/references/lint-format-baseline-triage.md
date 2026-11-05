---
name: lint-format-baseline-triage
description: "Judge whether a lint/formatter check (prettier --check, eslint, mypy, black --check, etc.) failing on a file you touched reflects pre-existing debt or a regression your edit introduced — before deciding whether to reformat the whole file. Use whenever a whole-file style/lint check fails during a pre-commit review, PR gate, or CI-parity check on a file you only partially edited. Complements requesting-code-review and tier2-orchestration's exit gate without editing them (protected/manually-authored)."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [code-review, formatting, lint, diff-hygiene, gate]
    related_skills: [requesting-code-review, tier2-orchestration, github-pr-workflow, pr-description-style]
---

# Lint/Format Baseline Triage

A whole-file lint/format check failing on a file you edited is NOT automatically
something you must fix by reformatting. The failure may come from lines you never
touched. Reformatting untouched code inflates the diff with unrelated churn and
violates diff-churn hygiene (no reindent/reflow beyond your actual edit) — a
common review rejection.

## Core check: is the debt pre-existing or introduced by you?

1. Stash your working diff (keep any staged subset if relevant):
   ```bash
   git stash            # or: git stash --keep-index
   ```
2. Re-run the exact same check against the now-clean tree:
   ```bash
   pnpm exec prettier --check path/to/file.tsx
   # or: eslint path/to/file.ts / mypy path/to/file.py / black --check path/to/file.py
   ```
3. Restore your changes:
   ```bash
   git stash pop
   ```
4. Compare:
   - **Fails identically on clean HEAD** → pre-existing debt, not yours to fix.
     Note it in your summary/PR/gate comment (name the file, name the check) and
     move on. Do NOT bulk-reformat the file to silence it.
   - **Passes on clean HEAD, fails with your diff applied** → your edit
     introduced the regression. Fix your own hunk only — do not run a
     whole-file `--write`/`--fix` pass, which will also reflow untouched lines.

## Verifying your own hunk is formatter-stable (without reformatting the file)

Even when the whole file still fails the check (pre-existing debt), you still
want proof your OWN addition doesn't add new debt on top of it:

```bash
# Extract just your new lines to a scratch file
sed -n '<start>,<end>p' path/to/file.tsx > /tmp/hunk.tsx
# Pipe through the formatter and diff against the original extraction
pnpm exec prettier --parser typescript /tmp/hunk.tsx | diff - /tmp/hunk.tsx
```

Expect either an exact match, or a diff whose only difference is the formatter
echoing back added/adjacent context it needed to parse (e.g. a wrapping
`describe(...)` block) — not an actual reflow of your lines. If the formatter
reflows content inside your own hunk (re-wraps a line, re-indents a block),
that's real debt you introduced — fix it in your hunk, not the whole file.

## Reporting

When a whole-file check still fails after this triage, say so explicitly and
distinguish the two cases in whatever surface reviews the change (PR comment,
kanban gate comment, code-review summary):

> "`prettier --check` fails on `X.tsx` identically on pre-change HEAD — not
> introduced by this change. The new hunk (lines N-M) is prettier-stable in
> isolation."

This lets a human reviewer decide whether to fix the pre-existing debt
separately, without conflating it with your change's correctness.

## Related: expansion-churn hygiene (distinct from lint/format failures)

A separate class of diff bloat that lint/format checks won't flag as failing but a
human reviewer will call out: a single-line import/destructuring/JSX-prop list that
got exploded to multi-line mid-session even though the real edit only added or
changed one item. `git diff -w` (whitespace-insensitive) UNDER-REPORTS this —
expansion splits content across physical lines, so every added line still reads as
"content changed," not whitespace, to a line-based diff. This is a shape problem,
not a formatting-correctness problem, so it survives a clean `prettier --check` and
a clean lint pass.

Audit by SHAPE: for each expanded hunk, would the original single-line form (from
`main`/base) still fit under the project's print width with the new item added? If
yes, collapse back to that exact single-line shape (content-identical — verify with
`git diff --ignore-all-space` afterward that nothing semantic moved). If the line
would now exceed print width, multi-line is legitimate — the formatter requires it;
don't fight it back into an over-length single line.

Audit the WHOLE diff for this class in one pass once you've spotted a single
instance — fixing files one at a time as a user points each one out separately
reads as an incomplete/half-done pass, even when each individual fix is correct,
because it implies the same defect exists elsewhere and wasn't searched for.
Re-verify the full suite/lint/typecheck yourself after any such collapse — a
cleanup pass's self-reported line-count reduction is a claim, not evidence.

Comment bloat (narrating obvious code, "fixed X" process narration, restating what
the next line already shows) is a related but separate audit — same principle
(sweep the whole diff in one pass, don't wait for each instance to be flagged), but
judged on content necessity rather than line shape.

## Pitfalls

- Running `--write`/`--fix` on the whole file "just to make CI green" — this
  silently absorbs pre-existing debt into your diff and gets flagged as
  scope creep / diff churn in review.
- Trusting `git stash` blindly when there are also untracked new files (e.g. a
  new test file with no prior committed version) — stash won't hide an
  untracked file by default; use `git stash -u` if the check would otherwise
  see your new file on the "clean" side too, or just skip the stash dance for
  brand-new files (there is no pre-existing state to compare against — any
  failure is 100% yours).
- Assuming a fresh `--check` failure means the check ran cleanly before your
  session started — always verify against the actual clean tree, don't infer
  from CI history or memory.
