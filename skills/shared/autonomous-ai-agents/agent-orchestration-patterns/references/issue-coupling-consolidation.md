# Coupled issues: don't file a new umbrella issue, just scope one T2 across them

Trigger: two or more GitHub issues already exist independently, later turn out
to share one root cause / one fix location (e.g. both live in the judge step
and judge.md), and the next step is dispatching a T2 to fix them.

## The mistake

Filing a brand-new "umbrella" issue that restates/merges the content of the
existing issues, closing the originals into it, and then dispatching the T2
against the new issue. Concretely observed: issues #36 (judge
misattribution/contradiction) and #37 (ungrounded citations) were both
judge-reliability failures sharing the judge step. Instead of dispatching one
T2 scoped to `#36` + `#37` directly, a new issue #55 was filed to consolidate
them, and #36/#37 were closed into it. The user's correction: "we didnt need
a new issue, just a t2 on both issues would have worked."

This is extra ceremony with no payoff: it doesn't change what gets fixed, it
just adds a fourth GitHub object to track, and it destroys the two original
issues' standalone identity/history for no reason — a reviewer looking at #36
or #37 later now has to follow a redirect instead of seeing the fix land
against the number they filed against.

## The distinction that matters

- **Coupled sub-items that have NOT yet been filed as separate issues** (e.g.
  a bulleted list of findings like "Group A: A1...A8" from a review pass) —
  filing ONE cluster issue per coupling group at the point of first filing is
  correct; that's the natural single filing point, not consolidation-after-
  the-fact. (This is what "split them based on coupling" produced for A1+A2+A5
  → #38, A3+A6 → #39, A4 → #40 — each cluster got exactly one new issue,
  filed once, because none of A1-A8 had a prior standalone issue.)
- **Issues that ALREADY exist independently** and are later found to be
  coupled — do NOT file a new issue to merge them. Just dispatch one T2 whose
  brief names both/all issue numbers as its scope (e.g. "GitHub issues #36
  and #37, both closed... treat X as the spec" is backwards — better: leave
  both open, brief the T2 to read both and fix both). The PR that lands can
  carry `Fixes #36, Fixes #37` references if the PR targets the default
  branch and the repository's linking rules recognize them; verify the
  closure after merge rather than assuming the trailer always auto-closes.

## Fix

When you notice N already-filed issues are coupled and about to be worked
together:
1. Do NOT create a new issue.
2. Write the T2 brief to name all N issue numbers as its combined scope, with
   one line describing why they're coupled (so the T2 doesn't treat them as
   accidentally-duplicate work).
3. Dispatch ONE T2 against that multi-issue brief.
4. The resulting PR body references every issue (for example `Fixes #36`,
   `Fixes #37` when merging into the default branch supports auto-close).
   Read back each issue after merge; cross-repository refs and non-default
   base branches may require explicit closure.
