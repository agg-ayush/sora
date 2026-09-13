---
name: pr-verification-audits
description: Audit diff hygiene, verify fixes, and triage PR issues.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [review, diff, testing, git, QA]
---

# PR Verification and Audits

Procedures for verifying code changes during or after a coding session, especially autonomous AI-driven development. Covers five audit shapes: fix verification against a findings checklist, scope proportionality, lint/format baseline triage, no-test-suite ad-hoc verification, and CI-signal/deploy-only verification.

## When to Use

- "Audit the fixes on branch X and confirm every finding is CLOSED" / re-audit a fix pass / verify a delegated agent's claimed remediation before trusting or merging it.
- "Is this PR/component over-engineered for its stated goal" / "does this need to be this big".
- A whole-file lint/format check fails on a file you only partially edited — decide pre-existing debt vs your regression before reformatting.
- The changed file has NO canonical test/lint/build command — "no suite" is not license to skip verification.
- A wave of red/stuck CI checks — decide real failure vs GitHub platform outage before reacting; or the fix can only be proven post-deploy and needs a written verification recipe.

## Procedure

### Fix verification audit (references/fix-verification-audit.md)

Score a claimed remediation of an enumerated findings list against reality. **Never accept "code exists" or "a test passes" as proof of closure** — three bars, all must clear per finding:
1. **Root cause, not symptom** — the failure mechanism is gone, not papered over.
2. **Production-wired** — reachable from the real invocation path (cron entrypoint, CLI, request handler), not just a unit test calling the fixed function directly.
3. **Not a stub/no-op** — watch for a constructor fed `None`/no-op for the exact parameter that made it inert; the most common "looks fixed, isn't" pattern.

Workflow: pin the exact findings list (re-read the ORIGINAL wording) → scope the diff (`git log --oneline <base>..<head>`, `git diff --stat`) → **kick off the real test suite in the background immediately** (poll later, never fabricate a result) → per finding, read the actual fix and cite `file:line` → treat a stub-absence wiring test (`assert "SomeClient(" in src` AND `assert "llm=None" not in src`) as gold evidence → live-probe the fixed function with production-shaped inputs where feasible → hunt for regressions the fix pass itself introduced → write a structured verdict artifact (verdict/confidence/suite header + per-finding `id/status/evidence` + `new_issues`) and mirror it inline in the chat reply.

For a single-fix "prove this is the RIGHT fix before merge" ask: four parts, don't skip any — mechanism walkthrough with line-level citation of pre-fix vs fixed, alternatives considered and rejected with concrete reasons, honest residual risks, and **mutation-revert proof** (apply the reverse of the fix, confirm the regression tests FAIL, restore, confirm green, verify tree byte-identical). For N-fix batches, the cheaper equivalent: `git stash push -- <only modified SOURCE files>` (keep tests), rerun the suite, confirm the new tests fail pre-fix, `git stash pop`, confirm green.

### Scope proportionality audit (references/scope-proportionality-audit.md)

1. Pin the STATED goal verbatim in one sentence — that's the yardstick; don't substitute your own guess.
2. `git diff main...HEAD --stat` + read every source file in the new component (proportionality needs full coverage).
3. Build a line-count **bucket table** (core mechanism / adjacent feature riding along / deploy-ops scaffolding / platform-parity) with an explicit yes/no against the stated goal, and state the percentage NOT required by it.
4. Distinguish legitimate goal-creep (relocated necessity) from true bloat — and do NOT default to "split into follow-up PRs" for relocated-necessity bulk; if bucket B's tests can't pass on main without bucket A, they're one PR.
5. Propose materially simpler alternatives with real trade-offs priced in lines saved AND capabilities lost — not "could use library X".
6. Hunt OS/library-duplicated effort (hand-rolled locks, retry loops, bespoke RPC, unbounded buffers, single-host OS-parity branches).
7. End with a scoped CUT LIST (file → cut/simplify → estimated lines) and a bottom-line verdict: OVER-ENGINEERED / RIGHT-SIZED / UNDER-ENGINEERED against the STATED goal, then a second sentence on whether the broader actual scope is separately justified.

### Lint/format baseline triage (references/lint-format-baseline-triage.md)

A whole-file check failing on a partially-edited file is NOT automatically yours to fix by reformatting — reformatting untouched code is diff-churn. Core check:
```bash
git stash            # (-u if untracked new files would pollute the clean side)
<the exact check>    # prettier --check / eslint / mypy / black --check
git stash pop
```
Fails identically on clean HEAD → pre-existing debt; note it and move on, do NOT bulk-reformat. Passes clean, fails with your diff → fix your own hunk only, not a whole-file `--write`. Verify your own hunk is formatter-stable in isolation by extracting it and piping through the formatter. Report both cases explicitly ("fails identically on pre-change HEAD — not introduced by this change").

Related: **expansion-churn** — a single-line import/destructuring exploded to multi-line when only one item changed. `git diff -w` under-reports this. Audit by SHAPE: would the original single-line form still fit print width with the new item? If yes, collapse back (content-identical, verify with `git diff --ignore-all-space`). Sweep the WHOLE diff in one pass, not just flagged files.

### No-test-suite verification (references/no-test-suite-verification.md)

When the changed file genuinely has no suite (check first — don't assume): write a small real ad-hoc check that exercises the ACTUAL changed code (regex/AST-extract the real function, don't re-implement its logic), run it, delete it, and report it as ad-hoc verification explicitly ("5/5 checks passed; component has no test suite for this file") — never phrase as suite-green. Cover the boundary the diff touches PLUS untouched sibling behavior that must keep working (e.g. clipboard copy of an untruncated value). On macOS, write temp scripts via `terminal` heredoc under `$TMPDIR` or via `execute_code` + `tempfile.mkstemp` — `write_file` blocks `/private/var/...` and `/tmp/...` paths.

### CI signal triage + deploy-only verification (references/ci-signal-triage-and-deploy-verification.md)

Outage signature: many/all jobs fail identically at the setup phase (`Failed to resolve action download info`, `Service Unavailable`), or runs sit `queued` with zero progress across the whole matrix. Confirm before reacting:

```bash
curl -s https://www.githubstatus.com/api/v2/components.json | python3 -c "
import json,sys
cs={c['name']:c['status'] for c in json.load(sys.stdin)['components']}
print('Actions:', cs.get('Actions'))"
```

During a confirmed outage: stop force-pushing / cancel-rerunning to "unstick" the queue. For fixes that can only be proven deployed (server-side timing, cron ticks, environments CI can't reach), write a concrete post-merge verification recipe into the PR so a human or later agent turn can actually prove it worked.

## Pitfalls

- Accepting a DONE self-report on a multi-file implementation without cross-checking the claimed file list against `git diff --stat` — a claimed new test file absent from the diff is an automatic fail.
- Reusing a "tests passed" claim voiced mid-session — run the suite fresh yourself on the final commit.
- Treating a pytest collection ERROR as a broken test file before checking editable-install shadowing (`pip show <pkg> | grep -i editable`).
- Auditing an async race claim without an explicit await-point map — a coroutine with zero awaits between two events runs atomically.
- A "swap public call for internal/unguarded variant to bypass a new gate" edit silently dropping side effects the public call carried (popup dismissal, analytics events) — diff both call paths' full bodies.
- Running whole-file `--write`/`--fix` to make CI green — absorbs pre-existing debt into your diff.
- Re-implementing a function's intended behavior in an ad-hoc test instead of extracting the real code — proves your mental model is self-consistent, not that the diff works.
- `exec()`-ing a whole standalone script with a top-level run loop / `sys.exit` — `SystemExit` isn't an `Exception` subclass and kills the harness before assertions run.
- Calling a script's real entry point for ad-hoc verification when it performs live mutations — exercise the pure helpers instead.
- Scoring proportionality against your own inferred "real" goal instead of the literal stated one.
- Force-pushing/cancelling CI during a confirmed GitHub Actions outage.

## Verification

- Fix audit: every finding has a `CLOSED|OPEN|PARTIAL` verdict with `file:line` evidence; the real suite result is quoted verbatim (never fabricated); new-issues section populated from an actual look.
- Proportionality: bucket table sums to the diff's total; verdict states the not-required percentage; cut list has per-file line estimates.
- Lint triage: clean-HEAD vs with-diff results both recorded; your hunk proven formatter-stable in isolation.
- Ad-hoc verification: reported as ad-hoc with a check count and coverage named, never blurred with suite-green.
- CI triage: outage confirmed against githubstatus.com before any queue-poking; deploy-only fixes carry a written post-merge verification recipe.

## References

- `references/fix-verification-audit.md` — full checklist-audit + single-fix-justification + batch RED-GREEN + blast-radius procedures.
- `references/scope-proportionality-audit.md` — full bucket-table method, comment/docstring verbosity smells, expansion-churn audit.
- `references/lint-format-baseline-triage.md` — stash-dance mechanics, hunk-isolation verification, reporting templates.
- `references/no-test-suite-verification.md` — extraction patterns, macOS temp-file traps, SystemExit trap, live-mutation trap.
- `references/ci-signal-triage-and-deploy-verification.md` — full outage signature list, deploy-verification recipe format.
- `references/coding-agent-diff-hygiene-audit.md` — (empty placeholder; the hygiene content lives in the lint/format and proportionality references).
