---
name: code-simplification-audit
description: "Read-only audit for dead code, duplication, oversized fns."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, dead-code, duplication, refactoring, audit, read-only]
    related_skills: [scope-proportionality-audit, github-code-review, fix-verification-audit, systematic-debugging]
---

# Code Simplification Audit

Judge whether an existing component's code carries removable weight — dead
code, duplicated logic, oversized functions, untested check paths — without
a stated external goal to score against (contrast `scope-proportionality-audit`,
which scores a diff against a literal stated goal). This is a maintenance/
health audit of code that already exists and already ships.

## When to use

- "Run a code-simplification audit on `<component>`"
- "Is there dead code / duplication in `<path>`?"
- "Could this be simplified?" with no PR-goal context to score against
- Read-only reviews explicitly flagged as "do NOT modify any code"

## Reading the target without touching the working tree

When the mandate is read-only (very common for these audits — the user is
asking for analysis, not a fix), do not `git checkout`/`git pull` the target
branch into the repo's working tree. Instead:

```bash
git -C <repo> fetch origin <ref>            # ref = branch/PR/tag
mkdir -p /tmp/<audit-name>
for f in $(git -C <repo> ls-tree -r --name-only origin/<ref> -- <subdir>); do
  mkdir -p "/tmp/<audit-name>/$(dirname "$f")"
  git -C <repo> show "origin/<ref>:$f" > "/tmp/<audit-name>/$f"
done
```
This extracts every file at that ref into a scratch dir you can grep/read
freely, while the actual repo working tree and index are never touched —
satisfies a strict read-only mandate and avoids clobbering whatever the user
currently has checked out locally.

## Core method

### 1. Read every in-scope file fully before judging
Same discipline as scope-proportionality-audit: partial reads produce
indefensible verdicts. Read source AND its test files — test coverage is
one of your primary signals (step 4).

### 2. Cross-file symbol-usage scan → dead code
For every function/constant/class defined in the src files, regex-count
its usages across the rest of src AND the test files. Zero uses outside its
own definition = dead code, safe to flag for removal. Do this systematically
(a small script), not by eyeballing — dead constants and superseded methods
hide easily in files of 1000+ lines.

### 3. Test-coverage-as-signal → the untested-but-shipped smell
Grep for the distinguishing string/id of each logical unit (a check name, a
feature flag, a branch condition) across all test files and count mentions.
A src-side unit with **zero** test mentions is a specific, valuable finding:
it shipped without verification. This is NOT automatically "delete it" —
frame it as a decision point:
- if it's genuinely dead (also zero call sites in src) → safe to delete
- if it's live but untested → flag as "either delete (if speculative/stale)
  or add minimal tests," and say so explicitly. Do not silently recommend
  deletion of code that's still wired into production behavior just because
  tests don't cover it — that's a product/risk call, not a refactor call.

### 4. Duplicate-logic scan
Search for the same regex pattern, the same literal string (error messages,
header text, a magic constant), or the same small algorithm defined more
than once across files. Common finds: a parsing regex rewritten 3 times
with cosmetic differences, a feedback-formatting string duplicated between
a "generate" path and a "critique" path, a `ThreadPoolExecutor(timeout=...)`
idiom hand-copied at multiple call sites. Each duplicate is one line in your
cut list: "extract into `_shared_helper`, ~N LOC saved."

### 5. Oversized/over-complex function scan
Grep for lint-suppression comments (`noqa: PLR0912`, `eslint-disable`,
`# type: ignore` clusters) — these are the codebase's own admission that a
function tripped a complexity/size linter and someone silenced it rather
than split it. Cross-reference with line count. A 150+ line function
carrying 2+ suppressions is a structural finding, not a style nit: propose
a concrete split into named sub-functions along its own internal phase
boundaries (the function's own comments/blank-line groups usually mark
these).

### 6. Build a summary table ordered by value/effort
Same format as scope-proportionality-audit's cut list:

| # | Location | Issue | Suggested simplification | Est. LOC saved | Risk |
|---|---|---|---|---|---|

Order by value/effort, not by file order — the highest-value, lowest-risk
items (pure dead code) go first; the "big lever but needs a product
decision" items go in the middle; the "biggest but riskiest, defer" items go
last.

### 7. "What NOT to simplify" section — mandatory
Explicitly call out code that LOOKS like duplication/complexity but is
defect-hardened: whitespace-preservation logic tied to a specific past bug,
a hand-rolled parser solving a different problem than an available library
despite surface similarity, literal test fixtures that intentionally
reproduce real defect geometries rather than being compressible boilerplate.
Naming these prevents the audit from being read as "delete everything that
looks reducible" — some of the ugliest-looking code is there because a
simpler version already broke once.

### 8. Bottom-line verdict + ranked top N
Close with one paragraph verdict (healthy/accreting/needs-attention, and
where specifically) plus a ranked "top 3 worth doing" list distinct from the
full table — the table is the reference, the top-3 is the actionable ask.
Flag anything with a "medium/high risk" or "needs a product decision" tag
as something to defer until the low-risk items land, not to bundle together.

## Pitfalls

- Don't recommend deleting an untested code path just because it's
  untested — untested-but-live is a "decide: delete or test" finding, not
  an automatic deletion. Say this explicitly in the writeup.
- Don't flatten "defect-hardened complexity" and "genuine duplication" into
  the same bucket — the "what NOT to simplify" section is not optional
  padding, it's what keeps the audit credible.
- Don't skip reading test files — they're often where the real signal is
  (which checks are covered, which fixtures are literal-for-a-reason vs.
  copy-pasted boilerplate that could be parametrized).
- When the mandate is read-only, never `checkout`/`pull`/modify the actual
  repo working tree to inspect a different ref — extract via `git show
  <ref>:<path>` into a scratch dir instead (see extraction method above).
- Distinguish this from `scope-proportionality-audit`: that skill needs a
  stated goal to score against ("is this proportional to X"); this skill
  needs no goal — it scores the code against its own redundancy/coverage/
  complexity. If the user gives you a stated goal to score against, that's
  the other skill.
