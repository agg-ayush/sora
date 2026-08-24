---
name: fix-verification-audit
description: "Independently audit whether a list of previously-identified findings (bugs, audit items, 'C1/C2/H1'-style codenamed issues) are GENUINELY fixed — root cause addressed and production-wired, not just code-present or unit-tested-in-isolation. Also covers proving a SINGLE fix is the architecturally right one before a merge decision: mechanism walkthrough, alternatives rejected, honest residual risks, and mutation-revert proof that regression tests actually catch the bug. Use when asked to re-audit a fix pass, confirm findings are CLOSED, justify a fix before merge, or independently verify a delegated coding agent's claimed remediation before it's trusted or merged."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-review, audit, verification, testing, pr-review, root-cause]
    related_skills: [requesting-code-review, github-code-review, systematic-debugging, python-monorepo-worktree-testing]
---

# Fix Verification Audit

Independent audit that a checklist of findings is genuinely CLOSED — not just
"code exists that looks related." Distinct from `requesting-code-review`
(which verifies YOUR OWN new diff before committing) and from
`github-code-review` (which comments on a PR's diff quality). This skill is
for scoring someone else's (or a delegated agent's) claimed remediation of a
**specific, enumerated list of prior findings** against reality, then
producing a structured verdict artifact.

## When to use

- "Audit the fixes on branch X and confirm every finding is CLOSED"
- "Re-audit" — a second pass after an earlier audit already flagged issues
  and a fix pass supposedly addressed them
- Verifying a delegated coding-agent session (claude-code/codex) actually
  fixed what it claims to have fixed, before trusting/merging its output
- Any request whose deliverable is a pass/fail verdict against a checklist,
  not a general "review this diff" ask

## Core principle

**Never accept "code exists" or "a test passes" as proof of closure.** Three
independent bars, all must clear per finding:

1. **Root cause, not symptom.** The mechanism that caused the original
   failure is gone, not papered over with a special case that happens to
   pass the reported repro.
2. **Production-wired.** The fix is actually reachable from the real
   invocation path (cron entrypoint, CLI, request handler) — not just
   exercised by a unit test that calls the fixed function directly with
   hand-built inputs while the real caller still uses the old path.
3. **Not a stub/no-op left behind.** Watch for a constructor call added but
   fed `None`/`no-op` for the exact parameter that made it inert (e.g. the
   client is now instantiated but injected with `llm=None`, or a runner is
   built but never invoked). This is the single most common "looks fixed,
   isn't" pattern — the addition is real but not connected.

## Step-by-step workflow

### 1. Pin down the checklist
Get the exact findings list (previous audit report, PR description headline
items, issue tracker). This is the rubric you score against — re-read the
ORIGINAL wording of what was broken for each item; don't substitute your own
guess at what "should" have been wrong.

### 2. Scope the diff
```bash
git log --oneline <base_sha>..<head>
git diff <base_sha>..<head> --stat
```
Know exactly what changed before reading any file in detail.

### 3. Kick off the real test suite in the background immediately
Start it before deep-reading code so it runs in parallel with your review,
not after:
```bash
terminal(command="... pytest ... 2>&1 | tail -40", background=true, notify_on_complete=true)
```
Then batch independent `read_file`/`search_files` calls in the same turn
while it runs. Poll/wait on it later — never fabricate a suite result; if it
didn't finish, say so.

**If you must run in the foreground** (e.g. quick spot-checks of a subset
rather than the full suite), don't hand one giant `pytest tests -q` call a
300s foreground budget in a monorepo component with real subprocess/lock/lease
timing tests — a handful of legitimately-slow tests (multi-minute lease
expiry, real subprocess spawn/reap) will blow the timeout and tell you
nothing about the rest. Split into file-level batches instead so fast files
report immediately and only the genuinely slow files need a long timeout on
their own:
```bash
python -m pytest tests/test_a.py tests/test_b.py -q      # fast, seconds
python -m pytest tests/test_slow_lease.py -q              # isolate, can take minutes
```
A 240s timeout on a 5-file batch usually means one file is a real multi-minute
test, not a hang — bisect to the slow file rather than assuming a hang.

### 4. Per finding: read the actual fix, not the commit message
For each item, locate the real code and confirm all three bars in "Core
principle" above. Cite `file:line` — a verdict without a location is not
evidence.

### 5. Treat source-level stub-absence tests as strong evidence
A wiring test that asserts BOTH the fix construct is present AND the old
stub pattern is absent is gold — it's the same check you'd do by hand,
already pinned so a regression fails CI:
```python
assert "SomeClient(" in src         # the real thing was built
assert "llm=None" not in src        # ...and not fed the inert stub
```
If no such test exists for a finding, that's worth noting even if the
finding still checks out manually — it means the fix isn't guarded.

### 6. Live-probe where feasible, don't just trust a mocked unit test
Call the fixed function/module directly against production-shaped inputs
and read the real output — this catches over-mocked tests that pass while
the real path is still broken:
```bash
python -c "
from pkg.module import the_fixed_function
print(the_fixed_function(real_shaped_input))
"
```
This is cheap and catches the class of bug where a unit test mocks exactly
the boundary that's actually broken.

### 7. Explicitly hunt for regressions the fix pass itself introduced
Always populate a "new issues" section from an actual look (diff scan for
anything outside the findings' scope, a skim of touched files not in the
checklist) — don't default it to empty without checking.

### 8. Write a structured verdict artifact
Markdown with a YAML-flavored header block works well: overall verdict,
confidence, the literal test-suite result line, then one entry per finding
with `id / status (CLOSED|OPEN|PARTIAL) / evidence` (file:line + mechanism,
not just "yes"), a `new_issues` field, and a closing notes section for
non-blocking observations. See `templates/verdict-template.md`.

### 9. Mirror the verdict structure in the chat reply
Don't just say "done, see file" — enumerate each finding's status inline in
the summary too, so the verdict is legible without opening the artifact.

## Proving a fix is the RIGHT fix, not just A fix (single-fix pre-merge justification)

A distinct ask from checklist audits: "prove this one fix is architecturally
correct before we merge it" (e.g. a T2 supervisor asked to justify a PR before
the human's merge decision). Same trust bar as the core principle, applied to
one change instead of a findings list. Structure the answer in four parts —
don't skip any, especially the honest-limitations one:

1. **Mechanism walkthrough with line-level citation.** Name the exact state or
   condition that caused the original failure — not "there was a bug in X" but
   "line N measured value V while state S was already applied, so the
   comparison was against the wrong baseline." Read the pre-fix version
   (`git show <base_sha>:<path>`) side-by-side with the fixed version so the
   causal chain (trigger → wrong state read → wrong output) is concrete, not
   paraphrased from the commit message.
2. **Alternatives considered and rejected, with concrete technical reasons.**
   List the other plausible approaches (a different data structure, a
   CSS-only fix, an offscreen/clone measurement, a different observer
   pattern, etc.) and say precisely why each is inferior for THIS bug — cost,
   incorrectness for the domain, race conditions introduced, complexity vs.
   the chosen minimal fix. A justification that only defends the chosen
   approach without naming rejected ones reads as post-hoc rationalization.
3. **Residual risks / edge cases NOT covered — be honest.** Explicitly name
   what the fix does not handle (a later async event after the fix's settle
   window, a resize mid-operation, a markup/schema rename that silently
   no-ops the fix, environments where the fix's guard makes it inert like
   SSR/jsdom). Never claim total coverage; an audit that only lists wins is
   not independent.
4. **Mutation-revert as proof the regression tests are real** (do this
   yourself, don't trust that tests "look" like they'd catch it):
   - `cp` the fixed file to a scratch path as a restore point.
   - Apply the REVERSE of the fix (delete/comment the specific line(s) the fix
     added — e.g. via `perl -0pi -e 's/.../.../'` or a targeted `patch`) so the
     file matches the pre-fix behavior for that one causal element.
   - Run the exact regression test(s) tied to this fix and confirm they FAIL
     with the expected assertion (not an unrelated error) — this is the
     evidence the test suite actually exercises the bug, not just the happy
     path.
   - Restore from the scratch copy immediately, re-run the suite, confirm
     green again, and `git status`/`git diff --stat` to confirm the tree is
     byte-identical to the committed state before reporting results. Never
     leave a mutated file sitting in the worktree.
   - If the fix has multiple independent causal elements (e.g. two separate
     root causes patched together), mutate and verify EACH independently —
     one mutation passing doesn't cover a second, unrelated fix in the same
     diff.
5. Post the four-part writeup as a kanban/PR comment; keep the task in
   `review` — a justification is not a merge decision, the human still
   decides.

## Batch RED-GREEN proof when a brief asks for N tests across N fixes

Single-fix mutation-revert (above) doesn't scale when a fix session was
dispatched against a *list* of findings (an edge-case audit, PR review
comments), each with its own new test — manually reverting N causal elements
one at a time is slow and easy to skip under time pressure, which is exactly
when a tautological test (one that encodes the buggy behavior as correct, so
it passes trivially against both fixed and unfixed code) slips through.

Cheaper equivalent that scales to N: `git stash push -- <only the modified
SOURCE files>` (explicitly list them — do NOT stash the test files), rerun the
full affected test suite, confirm the new tests FAIL against the pre-fix
source, then `git stash pop` to restore the fixes and confirm green again.
This is the same causal-proof idea as mutation-revert but done once across all
N fixes instead of N separate patch/restore cycles, because git stash cleanly
separates "test files" (keep) from "source files" (temporarily reverted).

When dispatching a multi-finding fix brief yourself (via `claude_orchestrate`/
`delegate_task`), put this in the brief explicitly rather than hoping the
fixer infers rigor from "add a failing-then-passing test": *"After all fixes
are in, stash ONLY the modified source files (keep the new tests), rerun the
affected suite and confirm the new tests fail, then restore and confirm green
again. Report which tests failed pre-fix as your proof."* Don't just trust a
self-reported "tests pass" — this is cheap enough that you (the auditor/T2
supervisor) can also demand and re-verify it yourself if the fixer didn't do
it unprompted.

## Blast-radius audit when a bug is mode/config-specific

A stateful gating bug reported in ONE mode or config (e.g. "reviewMode" vs.
default student mode; a feature flag on vs. off) is NOT closed just because the
reported mode is fixed and regression-tested. The mechanism that broke in that
mode (an admission gate, a completion latch, a contiguity/chain check) is
usually SHARED code reachable from sibling modes too — the fix needs a separate
pass asking "does this bug class generalize to the modes that weren't reported."

This is a distinct question from the regular fix audit (which asks "is the
reported bug fixed") and from a PR's diff review (which is scoped to what
changed, not to what's structurally still exposed in code the diff didn't
touch). Dispatch a READ-ONLY, high-effort adversarial audit of the sibling
mode(s) that traces each LEGITIMATE, non-adversarial user scenario against the
gate's actual code (file:line evidence per scenario) — not "does the fix look
safe elsewhere," but "can any realistic flow in the sibling mode hit the same
wedge." Scenario families worth enumerating for a timing/gating bug: straight
happy path, long pause / tab-hidden throttling, a dialog/prompt pausing
mid-flow, a speed/rate change mid-flow, a buffering/stall interruption, an
undo-then-redo path (e.g. backward-seek-then-rewatch), repeat-after-already-
complete (latch re-entry), and state restored from a persisted/ceiling value
with no fresh chain. Output a table (scenario | completes/wedges | mechanism
file:line | severity if wedges) and a one-line yes/no verdict on whether a
legitimate wedge exists in the sibling mode.

Example (forward-scrub / review-mode wedge in a media player library):
`handleContentComplete` gated media-end admission on a contiguity/latch check
with no mode bypass. A reviewer's legitimate free-seek broke the chain →
`CONTENT_END_REJECTED` → the state machine forced `paused` and never fired the
completion transition (play/pause dead, timeline gone). The blast-radius audit
confirmed default/student mode was structurally safe: forward seeks are
clamped/rejected *before* touching the chain, and the contiguity bound is
wall-clock × rate, so real playback timing irregularities (pause, throttle,
stall, speed change) only loosen the bound, never violate it — only a
*permitted* forward jump past the watched frontier (reviewMode, or a consumer
disabling the forward-seek block) could trigger it. Citing that structural
argument WITH the file:line evidence is what makes "student mode is safe" a
verified claim instead of a hopeful one.

## Pitfalls

- **A `DONE`/`DONE_WITH_CONCERNS` self-report on a large multi-file implementation is not evidence — verify the claimed file list, not just the pass/fail claim.** Observed: a multi-file refactor (4 source files, ~350 lines) touching a shared class's public API reported completion, but (1) the session claimed to have added regression test files that did not exist anywhere in the diff or on disk (`git diff --stat` showed zero test files touched), and (2) the refactor renamed/removed a method another module still called, so the package failed to `import` before any test could even collect. Neither defect was visible from the diffstat's line/file counts alone — both required actually cross-checking claimed content against real content. Before trusting ANY session's completion report: (a) `git diff --stat HEAD` (or `<base>..HEAD`) and cross-check every file the self-report claims to have added/changed — a claimed new test file absent from the diff is an automatic fail, not a "concern to note and proceed past"; (b) run the actual test command fresh yourself — never reuse a "tests passed" claim voiced mid-session before the final commit; (c) on an import/collection error specifically, don't default to "environment issue" — `search_files` the codebase for the failing attribute/method name first, since large refactors on a shared class routinely leave one caller still pointed at a since-renamed or since-removed member.
- **A pytest collection ERROR (not a test failure) is not proof of a broken
  test file — check for editable-install shadowing before reporting "could
  not verify."** In a monorepo where one component's tests import a sibling
  in-repo component (e.g. a dashboard package's tests importing a supervisor
  package from a neighboring `components/` dir), a stale `pip install -e`
  pointer left over from a different worktree/branch checkout is the classic
  cause. Run `pip show <sibling-package> | grep -i editable` before writing
  off the file as unverifiable, and don't let a bounded-iteration limit force
  you to conclude "environment gap" without that one check — it's usually a
  one-line `pip install -e <correct-path> --no-deps` fix (see
  `python-monorepo-worktree-testing`), not a real defect and not something to
  silently drop from the verdict either way — name it explicitly as
  "unresolved due to local env, not exercised" if you truly run out of turns
  before checking.
- **Tracing an async race/ordering concern needs an explicit await-point
  map, not "this looks concurrent so it might race."** When auditing a claim
  like "two operations could interleave and cause a gap/dup," don't stop at
  "both are async functions." Walk the exact call chain and mark every
  `await` between the two events in question — a coroutine that has zero
  await statements between capturing state A and using it (even though it's
  declared `async def` and is itself awaited by its caller) runs atomically
  on the event loop; there is no suspension point for a concurrent task to
  interleave. Conversely, a lock/context-manager `__aexit__` completing IS a
  potential yield point in some frameworks — check the specific primitive's
  semantics rather than assuming a `return` at the end of an `async with`
  block never suspends. State the conclusion as "no await between step X and
  step Y, hence atomic" or "await at line N is a real suspension point,
  hence a genuine window" — cite the line, don't hand-wave "should be fine."
- **A "swap the public call for an internal/unguarded variant to bypass a new gate" edit can
  silently drop side effects the public call carried.** When a diff adds a new gate to a shared
  entry point (e.g. a seek/navigation function gains a frontier check) and a caller that needs
  to bypass the gate gets rerouted to an internal/raw variant, that's correct for the gate itself
  but the public path may have carried OTHER effects beyond the gated behavior — dismissing an
  active popup/modal, recording a skip/analytics event, updating a ref read elsewhere. Swapping
  the call silently drops those too, and the existing test suite gives false confidence because
  it exercises the gate, not the dropped side effect. When auditing this shape of change, diff
  both call paths' full bodies side-by-side and check every OTHER caller of the old public
  function for what else it used to trigger — not just whether the new gate now applies
  correctly to the rerouted caller.
- **Path-relativity mismatch is a recurring root cause of the "silently skipped edit" class, and it hides behind a parent-exists check instead of a file-exists check.** Observed: a fix-design record's edit path was relative to the component's own package dir (e.g. `interaction_checks/deterministic.py`),
  skipped edit" class, and it hides behind a parent-exists check instead of a
  file-exists check.** Observed: a fix-design record's edit path was relative
  to the component's own package dir (e.g. `interaction_checks/deterministic.py`),
  but the PR-packager resolved it by joining against the repo root and only
  checked that the PARENT directory existed (not that the resolved file
  itself existed) — so a wrong-relative path silently resolved to a directory
  that happened to exist (a different, unrelated one) and the edit was
  dropped with no error, no exception, no failed test. This is the same
  "stub/no-op left behind" shape as core principle #3 above, but manifests as
  a path-resolution bug rather than an injected `None`/no-op dependency. When
  a finding is in the "edit didn't apply" / "empty PR" family, explicitly
  check whether the resolution logic asserts the FINAL file's existence
  (`resolved_path.is_file()`) or only the parent directory's — the latter is
  the tell that a wrong base directory can pass silently. A smoke test using
  a REPO-ROOT-relative path (e.g. `a/deterministic.py`) can pass this exact
  check while a real PACKAGE-relative path from production still silently
  fails — write the smoke test with a path shaped exactly like the real
  producer emits, not a convenient stand-in.
- **Grep-level presence isn't enough.** `"LLMLogger(" in src` passing means
  nothing if the very next check for `llm=None` would fail — always pair a
  "constructed" assertion with a "not fed the inert default" assertion.
- **A green full-suite run doesn't prove wiring.** Unit tests over mocks can
  all pass while the production entrypoint (cron script, CLI wrapper) still
  calls the old code path. Cross-check the actual entrypoint file (shell
  script, workflow YAML, `__main__` block) separately from the test suite.
- **Don't block reading on the suite finishing.** Start it backgrounded
  first, keep reading/verifying findings in parallel, poll near the end.
- **Re-audits must anchor to the ORIGINAL failure description**, not a
  fresh read of "does this look reasonable" — the earlier audit's exact
  wording of the bug is the spec you're checking closure against.
- **Cite locations.** "Confirmed" with no file:line is not an audit result,
  it's an assertion — always name where you looked.

## Support files

- `templates/verdict-template.md` — the verdict artifact skeleton (verdict/
  confidence/suite header + per-finding id/status/evidence + new_issues +
  notes section) used in `write_file` calls for the final deliverable.
