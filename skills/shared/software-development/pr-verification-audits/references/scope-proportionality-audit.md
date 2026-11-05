---
name: scope-proportionality-audit
description: "Assess whether a PR/diff/new component is over-engineered relative to its STATED goal — build a line-count bucket table (essential vs speculative vs goal-creep), compare against materially simpler alternatives with concrete trade-offs, flag OS/library-duplicated effort, and produce a scoped cut list with a bottom-line verdict. Use when asked 'is this over-engineered', 'is this proportional to what it's supposed to do', 'does this component need to be this big', or any size-vs-goal review of a large diff/component."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, architecture, over-engineering, scope, pr-review]
    related_skills: [github-code-review, fix-verification-audit, library-feature-scoping]
---

# Scope Proportionality Audit

Judge whether a diff/component's size and complexity is justified by its
STATED goal. Distinct from `github-code-review` (correctness/security/style
of a diff) and `fix-verification-audit` (did a claimed fix actually land) —
this is specifically about proportionality: is the thing bigger than the job
requires, and if so, by how much and where.

## When to use

- "Is PR #N's new component over-engineered for [narrow stated goal]?"
- "Does this need to be this complex?" / "why is this N thousand lines for X?"
- Pre-merge sanity check on a component whose size looks disproportionate to
  its one-line description.

## Core method

### 1. Pin down the STATED goal in one sentence, verbatim
Get the narrow, literal goal as the user or PR description states it — this
is the yardstick. Don't substitute your own guess at what the component
"should" do. Write it down before reading code.

### 2. Get the shape before the detail
```bash
git diff main...HEAD --stat                    # whole PR
git diff main...HEAD --stat -- ':!some/dir'     # excluding a known subtree
find <component> -name '*.py' | xargs wc -l     # or grep -c 'def ' per file
```
Read every source file in the new component (not just a sample) before
judging — proportionality calls need full coverage, not spot checks.

### 3. Build a line-count BUCKET TABLE, not a prose impression
Classify every substantial file/module into buckets, each with an estimated
line count and an explicit yes/no against the stated goal:

| Bucket | Files | Lines | Needed for the stated goal? |
|---|---|---|---|
| Core mechanism | ... | ... | Yes — essential |
| Adjacent feature riding along | ... | ... | No — pre-existing feature relocated |
| Deploy/ops scaffolding | ... | ... | No — orthogonal concern |
| Platform-parity code (e.g. Windows branch) | ... | ... | Partial |

Then state the percentage of the diff that is NOT required by the stated
goal. This number is the headline of the verdict — arrive at it by actually
summing buckets, don't eyeball it.

### 4. Distinguish "goal creep is legitimate" from "true bloat"
A PR's *actual* scope is often broader than its one-line description (e.g.
"keep a process alive across restart" really means "split the service into
two deployable units," which drags in locking/session-registry/versioning
that must live SOMEWHERE once ownership moves). Call this out explicitly as
relocated necessity, separate from genuinely speculative/YAGNI additions.
Don't let honest scope-broadening get scored as bloat, and don't let bloat
hide behind "well the PR did more than the ticket said."

### 4b. Don't default to "split into follow-up PRs" for relocated-necessity bulk
When a bucket is "relocated necessity" (code that had to move because the PR
shifts ownership of something), do NOT recommend splitting it into a separate
PR just because it's large or wasn't in the one-line description. Check
dependency direction first: if the relocated piece cannot function, or
cannot even be exercised by its own tests, until the core mechanism exists
(e.g. locks/session-registry/versioning that only had to move because a
service split ownership of the process), it is NOT independently shippable —
splitting it out creates artificial sequencing and a half-migrated state in
main between merges. In that case the correct recommendation is "keep it in
one PR, trim only the genuinely optional/speculative sub-parts" (e.g. an
OS-parity branch that's dev-only today, an unbounded buffer, a deploy-tooling
feature that doesn't depend on the core change and could equally well ship
before or after it). Reserve "split into separate PRs" for buckets that are
both large AND genuinely independent — able to merge in any order without the
other. When in doubt, ask whether bucket B's tests would pass on `main` alone
without bucket A; if not, they're one PR. This mirrors the standing rule that
everything needed for a feature to actually work belongs in one PR, not
deferred to a follow-up — proportionality critique should produce a trim
list, not a fragmentation plan, whenever the extra scope is load-bearing.

### 5. Propose materially simpler alternatives — with real trade-offs, not slogans
For each major subsystem, ask "what's the smallest thing that meets ONLY the
stated goal" and price it in lines saved AND capabilities lost. A credible
alternative names what breaks, not just what shrinks:
- "systemd/supervisord instead of hand-rolled process supervision" often
  looks like a big win but only replaces the "is the supervisor itself kept
  running" piece — the per-session spawn/attach/resume/ring-buffer logic
  still has to be hand-written either way. Compute the ACTUAL line delta,
  not the naive "just use X" claim.
- Prefer concrete deltas: "≈300 lines saved, but loses seq-cursor resume
  semantics no off-the-shelf library provides" over "could use a library."

### 6. Hunt explicitly for OS/library-duplicated effort
Common tells: hand-rolled file-lock envelopes when `fcntl`/`filelock` cover
it, custom retry/backoff loops, a bespoke correlation-id RPC protocol where
JSON-RPC/gRPC would do, unbounded-growth buffers where a capped `deque` +
existing disk fallback would do, full OS-parity code (e.g. a Windows ACL/
keyring branch) for a single-host trusted deployment. Flag each with a
concrete swap and estimated line delta.

### 7. Produce a scoped CUT LIST
End with a concrete list: file/module → what to cut or simplify → estimated
lines removed. Sum it to a total, and separately state what's left as
"honest cost of the real (possibly broader-than-stated) goal." This is the
artifact that makes the verdict actionable instead of just critical.

### 8. Bottom-line verdict format
State the verdict as OVER-ENGINEERED / RIGHT-SIZED / UNDER-ENGINEERED against
the STATED goal specifically, then a second sentence noting whether the
actual delivered scope (if broader) is separately justified. Don't blend the
two judgments into one number.

## Pitfalls

- Don't score against your own inferred "real" goal instead of the literal
  stated one — state both when they diverge, and label which you're scoring.
- Don't treat "could use library X" as a valid simplification unless you've
  worked out what capability is lost and roughly how many lines the
  hand-rolled part uniquely needs to keep (e.g. custom resume/cursor
  semantics that no generic RPC/process-manager provides).
- Read every file in the new component before writing the bucket table —
  a proportionality verdict from partial reading is not defensible.
- Always turn the critique into a cut list with estimated line counts, not
  just prose criticism — "this feels big" isn't an actionable finding.
- Don't conflate "this bucket wasn't in the one-line stated goal" with "this
  bucket should be a separate PR." Check whether it's independently shippable
  first (see 4b) — most relocated-necessity bulk isn't, and recommending a
  split there just fragments one atomic change into an unshippable sequence.
- Don't trust `git diff -w` to catch import/destructuring expansion churn — it
  only ignores whitespace-only diffs, not content reflowed across new lines.
  Diff the actual content against main to find pure-expansion hunks.
- Don't stop an expansion-churn audit after cleaning the files the user
  pointed at — apply the same collapse check to every file in the diff, or the
  user will find the next instance and flag the audit as half-done.

## Related: comment/docstring verbosity as a proportionality smell

On large multi-agent/orchestrated PRs, verbosity often shows up in comments and
docstrings, not just line count. Two patterns to flag when auditing or when the
user calls a PR's comments "too verbose":

- **Docstrings narrating WHY instead of WHAT.** A docstring should state what
  the function/class does and any non-obvious caller contract. If it instead
  walks through the reasoning ("X calls Y on Z's return... rebuilt becomes a
  deny, never a pass-through") that's design-rationale prose belonging in a
  design doc, not the code. Trim to the terse what-it-does form.
- **Internal design-doc cross-references left in code** (e.g. a `§7.4`-style
  section pointer to a design doc). A code reader won't have that doc open —
  these read as unexplained noise. Strip the reference; drop the whole comment
  if the §-ref was its only content.

When a review or audit surfaces this, hand the cleanup to the PR's own T2/agent
as a dedicated comments-and-docstrings-only pass (no behavior change), re-run
the test suite to confirm nothing broke, then push. Don't fold it into the same
push as a functional fix — keep a pure-comment diff easy to spot-check.

## Related: import/destructuring expansion churn inflates diffs without any real change

On agent-authored diffs (especially a rename/refactor that touches many call
sites), a large fraction of the added-lines count can be pure **formatter-
triggered reflow** that carries zero semantic change: a single-line import or
destructuring statement gets exploded to multi-line because the agent's edit
touched that statement (even just adding one new named import), or a whole
block gets reindented as a side effect of a nearby edit. This inflates the
diff exactly the way described above but is easy to miss because `git diff -w`
(whitespace-insensitive) does NOT catch it — expansion splits content across
NEW lines, so each added line reads as "real" content to a whitespace diff,
not whitespace noise.

**Audit method — do this for every file where added-line count looks high
relative to the described change, not just the files a user happens to flag:**
1. For each such file, diff against main with the actual content (not `-w`):
   isolate hunks where the only difference from main's single-line/compact form
   is line-breaking, added/removed trailing commas, or one token added/removed
   inside an otherwise-unchanged statement (e.g. one new named import added to
   an existing `import { a, b, c } from 'x'`).
2. Classify each such hunk: **pure-expansion** (byte-for-byte identical content,
   just reflowed — collapse back to main's form) vs. **shape-driven** (the
   statement genuinely needs multi-line because it now exceeds the project's
   print width — leave it, don't fight the formatter) vs. **real change**
   (actual new/removed content, not just reflow).
3. For pure-expansion hunks: rewrite to match main's original single-line
   shape, keeping only the token-level change (e.g. add the one new import
   name inline rather than accepting the whole statement's multi-line
   explosion). Verify line width still fits the project's formatter config
   before collapsing — if it doesn't, that hunk is actually shape-driven, not
   pure-expansion, and multi-line is correct.
4. **Audit ALL files this way, not just the first one or two flagged as
   examples.** A partial pass (catching the files a user's screenshot happened
   to show, or the ones a first collapse pass flagged as "pure content-
   identical") leaves the same pattern live elsewhere in the diff — the user
   will find the next instance and call out that the audit was incomplete.
   "Even a one-import addition doesn't justify exploding the whole statement"
   is the standard to hold every file to, not just the loudest offenders.
5. Verify after each collapse pass: full test suite green, lint clean, tsc/
   build clean, and the file's own formatter check accounted for (a collapsed
   single-line import may now trip `prettier --check`/equivalent if it's
   genuinely too long — check before committing, don't just eyeball it).
6. Route the actual collapse through the PR's coding session/subagent, not a
   direct hand-edit, if you're operating as T2 (see the T2 boundary rule) —
   this is still a source-code change even though it's semantically a no-op.

## Related: two PRs sharing a mechanism

If your proportionality audit surfaces a sub-component that exists mainly for
platform parity (e.g. an OS-specific auth/transport branch) and a SEPARATE PR
is migrating production to that platform, flag the coordination risk even if
the two PRs don't touch overlapping files: the parity branch that looked like
low-priority dev-convenience bloat in PR A becomes the production mechanism
once PR B ships. Concretely: check whether PR B's rollout depends on the
exact mechanism PR A built (port/socket binding, token provisioning, ACL
model) and have both owners confirm they agree on it before either merges —
this catches drift that a file-diff overlap check alone would miss.
