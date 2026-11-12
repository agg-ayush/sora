# Anti-patterns

Failure categories that designs and design reviews keep missing. Each entry gives what it looks like, why review misses it, what catches it and labelled examples. Examples come from one product's card history and are examples only; the categories are generic.

## 1. Missing behaviour model on async or concurrent paths

Looks like: a design analyses the happy path of a latch, ref, polling loop or async flow and says nothing about failure, retry, unmount mid flight, a second tab or an identity change.

Why review misses it: a reviewer checks the claims the design makes, not the transitions it omits. Each hunk looks right alone.

Catches it: the behaviour-model section with a transition table; the lens agent's state inventory and four adversarial paths; one verification row per transition.

EXAMPLES (web app):
- A latch kept a box visible after an action but was analysed only in the stay-visible direction. A record loaded in its final state never showed the box after the action and a refresh.
- A hook that converged a cancel died when the user switched tab and returned. It took four review rounds to find because no transition for "returns later" existed.

## 2. Consumer not enumerated

Looks like: the design changes a component, helper, flag or string and lists one caller. Siblings and tests that use it are not named.

Why review misses it: reviewers verify the listed consumers, not the unlisted ones.

Catches it: a consumer table built by grep in grounding; the reviewer's own grep in step 4; the lens agent's consumer inventory; the change-impact bundle.

EXAMPLES (web app):
- A locked-name component rendered in three places. Only the card that was named got the layout reservation; the other two kept the old layout.
- A draft flag was handled in the send path. A second caller, the reconcile path, called the same function without the flag and finished immediately.

## 3. Missing interaction contract

Looks like: a new control is specified by what it shows and one line for how it opens. Keyboard, touch, focus return, dismissal and widths are left to the implementer.

Why review misses it: reviewers check copy and visual rules, and check ARIA only at the attribute level.

Catches it: the UI module's per-control contract (keyboard map from the ARIA Authoring Practices pattern, touch path, focus return, Escape and tap dismissal, accessible name that includes the visible label, sizes that matter) and a verification row for each.

EXAMPLES (web app):
- A date picker declared non-modal while its design trapped Tab between three elements. Reviewers checked only the modal attribute.
- A hover-only tip had no Escape dismissal and a phone tooltip closed itself 1.5 seconds after a tap although it was the only route to that text.

## 4. Verification that cannot fail

Looks like: named tests that pass on the baseline code, assert a class name or source string, sit inside a conditional, run with the control closed, use one fixture value or render a hand-built copy of the component.

Why review misses it: reviewers check that tests exist and that a red-green sequence is listed, not whether each test discriminates.

Catches it: the verification table's "wrong implementation caught" column; the reviewer's step 5 audit naming a mutant per row; the red-before-green evidence; the mutation probe at code review.

EXAMPLES (web app):
- Removing all three out-of-order guards from a response handler still passed 28 of 28 tests: the design said "stale responses are dropped" and listed no out-of-order, late-reject or unmount case.
- An e2e test ran with a menu closed while the target was a menu item, so the assertion could never fail.
- A sticky-position test would still pass if the sticky rule were removed.

## 5. Conflated data concepts

Looks like: two values that sound alike but mean different things share a field, a comparison or a name. One is used where the other is meant.

Why review misses it: the design never defines the two terms, so the reviewer has nothing to compare against.

Catches it: the interfaces section defines each field's meaning and source; the reviewer asks for the source of every compared value; a verification row uses fixtures where the two values differ.

EXAMPLES (web app):
- Two timestamp kinds were compared as one. A patch advanced the "generated" time past the "built" time and the staleness check fired on every patch. It was raised in three successive review rounds.
- A bounce set derived in the design differed from the existing flag that the dashboard already used for the same concept.

## 6. Wrong claims about existing code affirmed by review

Looks like: the design says a function preserves a value, a route is idempotent or a type has a field. The code does not. The review repeats the claim.

Why review misses it: the reviewer reads the design's citation list, not the code behind it. It also shares the author's model family and blind spots.

Catches it: the "verify at least five citations" rule; reading the cited lines in this session; tagging uncited claims about existing code as unverified; the grounding_verified coverage field.

EXAMPLE (web app): a design asserted that a route preserved a first-sent timestamp through a merge helper. The helper overwrote it when the stored link held only keys. The design review affirmed the claim.

## 7. Time budgets that ignore real upstream latency

Looks like: a timeout or target chosen from taste, with no measurement of the service it waits on.

Why review misses it: a number looks plausible and there is no field that asks where it came from.

Catches it: the risk module's budget against measured latency and the upstream's own timeout, with the measurement cited; the assumptions section of the change-impact bundle.

EXAMPLE (web app): a 15 second target against a vendor timeout of 45 seconds failed on live runs while passing against a mock.

## 8. Non-blocking suggestions dropped

Looks like: review lists suggestions as non-blocking, the verdict says approved and nothing in the pipeline requires an answer. The implementer never sees them.

Why review misses it: the suggestions are by definition not blocking, so the loop moves on.

Catches it: the `Changes since review` section where every NB id is adopted or rejected with a reason; the pre-check for a revision; adopted ids copied into the implementation brief as acceptance criteria.

EXAMPLES (web app):
- A sticky-column e2e suggested as non-blocking was never adopted and came back later as a high severity test finding.
- A reviewer flagged a weak hidden-element check in a focus helper. The design was not revised and the code inherited the weakness.

## 9. Exact fix given, design skipped

Looks like: an urgent card names the change to make, so triage sends it straight to build.

Why review misses it: nothing reviews a skipped design.

Catches it: tier rules (the fix says what to change, not what it touches), a consumer grep at triage, any light trigger (state, async, shared contract, more than one consumer) moving the card to light.

EXAMPLE (web app): the heaviest cards in one audit were release-blocker fixes with the fix spelled out. Cards that skipped design averaged 4.6 review rounds against 3.1 for designed cards (a biased sample).

## 10. Reviewers missing binding inputs

Looks like: a reviewer is given the design and the task but not the standing decisions or the files the task names. It raises the same false blockers each round or contradicts a decision.

Why review misses it: a reviewer cannot see what it was not given and has no way to know it is missing.

Catches it: the binding-inputs rule (every reviewer and subagent gets the task, standing decisions and named files in full); dropping any reviewer finding that contradicts a binding input.

EXAMPLES:
- In a reviewer trial, reviewers without the task's standing decisions produced identical false blockers.
- A code review finding contradicted a recorded design decision. Following it caused a regression in the next round.

## 11. Partial failure with no recovery path

Looks like: a flow reads two sources and one fails. The user sees a message that names a problem and offers no control to fix it, or a link with no target.

Why review misses it: designs describe success and total failure; the in-between state has no row.

Catches it: the lens agent's failure-mode step (what the user sees and whether recovery exists) and the surface states in the UI module (error with data versus error without data).

EXAMPLE (web app): when only the signers fetch failed, a banner named a bounce but its fix control rendered only after the fetch succeeded.

## 12. Stale tests

Looks like: the design changes a label, selector or string and the existing tests that assert the old value are never listed, so they fail late or are loosened to pass.

Why review misses it: the design lists tests to add, not tests to change.

Catches it: the lens agent's stale-test inventory (every changed literal, label and selector grepped across unit and e2e tests, each hit listed per file); the test-impact map from grounding.

EXAMPLE (web app): a design changed heading and link text. Page tests that matched the old names and an id-chip selector were not in the design and broke at implementation.

## 13. Weakened or deleted assertions

Looks like: to make the new behaviour pass, an existing assertion is relaxed or removed with no reason.

Why review misses it: the diff shows a smaller test, which looks like a cleanup.

Catches it: the verification-table rule (a written reason for any change to an existing assertion), RED evidence recorded before source edits and the conformance review that checks changed assertions.

EXAMPLE (web app): a phone tap test for a clipped reason was cut down to a focus check, so the clipping defect it guarded could return.

## 14. Oversized design dilutes review

Looks like: a design that runs to tens of kilobytes with code-level detail. Review attention goes to checking claims line by line.

Why review misses it: size reads as thoroughness.

Catches it: the detail limit, the pre-check's length and fenced-code warnings, tables in place of prose.

EXAMPLE: sampled designs ran from about 55 to 224 KB while the reviewers read for 2 to 9 minutes.
