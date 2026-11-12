# Design contract

A design is decision level, not line level. It states what to build, the interfaces and states, the tests that prove it and what the implementer may decide alone. The implementer follows it test-first.

## Header

The file starts with a fenced block, before any heading:

```
design-meta: tier=<light|full> modules=<ui,risk|none>
revision: 1
```

`revision` starts at 1 and goes up by one on each revision after a review or an amendment. The tier and modules equal the ones in `process.json`. A document without this block is a legacy document and fails the pre-check.

## Required sections (light and full)

Heading text must contain the words shown. Every section is non-empty; write `None.` where nothing applies.

1. **Problem, goals and non-goals**, then **Requirements** with ids R1, R2 and so on. Each requirement is testable: a number, a named state or an observable. Copy the card's binding decisions into the problem section as a list.
2. **Grounding**: existing patterns to follow, the consumer table (location, changing or unchanged), existing tests and measured upstream limits. Every claim cites `path:line` read this session. Light needs at least one citation, full at least three.
3. **Approach**. Full: 2 to 3 real alternatives, the pick, why the others lose and the assumptions with how each was verified. Light: one paragraph.
4. **Behaviour model**. Required whenever the change has states, async work, retries or concurrent actors. Otherwise write `n/a:` and the reason in one line. Rules in the next section.
5. **Interfaces and data shapes**: contracts other code or users see. Shapes and meanings, not code.
6. **Verification**: the table described below.
7. **May decide alone and must escalate**: the two lists described below.
8. **Build sequence**, **Failure modes**, **Rollback** and **Open questions**. One combined heading or four separate ones both pass; all four phrases must appear in headings.

## Behaviour model

Trigger: any state, async work, retry, cancellation or concurrent actor. A one-state change with none of these writes `n/a`.

Content: a transition table with ids T1, T2 and so on. Columns: id, transition (from state to state), trigger and what happens on failure, retry, cancellation, repeated or concurrent action, identity change and stale data. For each piece of state, list where it is set, read and cleared and which identities it can hold. Name every transition the design leaves open as an open question, not as silence.

The four adversarial paths must each have an answer for every state:
- failure then retry: does the second attempt recover?
- reset coverage: does every identity the state can hold have a reachable reset?
- in-flight work when identity or config changes: does it finish under the old one or corrupt?
- two writers or two sources of truth: can they disagree, and what wins?

Every T id must appear in the verification table.

## Verification table

One row per requirement and per behaviour transition. Columns, in this order:

| Id | Test | Level | Observable asserted | Wrong implementation caught |
|---|---|---|---|---|

- Id: one or more R and T ids.
- Test: the test file and name, or the name to create.
- Level: unit, integration, e2e or live.
- Observable asserted: what the assertion reads (a value, an element, a call count), never a class name or source string alone.
- Wrong implementation caught: the plausible mutant this row turns red, for example removing a guard, flipping a condition or dropping a state reset.

Rules:
- No assertion inside a conditional. A check that can be skipped cannot fail.
- Fixtures must distinguish right from wrong: more than one item, distinct timestamps, null and empty values, widths that differ.
- Test the real component, not a hand-built copy of its markup.
- Never weaken or delete an existing assertion without a written reason in the row. The code reviewer checks it.
- Every row must fail on the baseline code or on its named mutant. Rows that pass today say so and name the mutant that fails them.
- Add a negative-control line under the table for the two or three guards that matter most.

## May decide alone and must escalate

May decide alone (internal choices): names of internals, file layout, helper structure, algorithm, a library already in use, timer or storage mechanics inside the stated contract.

Must escalate (anything contract-visible): the shape of an interface, API or message; persisted data shapes and migrations; status values and their meaning; user-visible copy the card pins; behaviour named by a requirement; any new dependency; time or size limits the card states; anything the consumer table marks as changing for another team.

The implementer stops on a must-escalate item and returns the section, the claim and what it observed. Tier 2 sends it to the author as a scoped amendment.

## Modules

Declared in `design-meta`. Each adds one non-empty section.

**UI module**
- Surface states: no data, loading, error with data, error without data, partial, busy, success, disabled with reason, stale.
- Per-control interaction contract: keyboard map (cite the ARIA Authoring Practices pattern for the role), touch path (nothing reachable only by hover), focus return, dismissal (Escape and tap), accessible name that includes the visible label.
- Sizes that matter: the widths or containers where layout can break, with the test that asserts each.

**Risk module**
- Failure-mode table: failure, what the user sees, recovery.
- Time budgets set against measured upstream latency and timeouts, with the measurement cited.
- Idempotency of every repeatable write.
- Rollback including data effects: reversible migrations, data written by the new code, kill switch, forward and backward compatibility.

## Frozen intent and amendments

Problem, goals, non-goals and requirements are frozen once approved. Everything else may be amended. An amendment that changes frozen intent goes to the owner, not to a review round.

After a review or an implementer-reported gap, the author revises in place and adds a **Changes since review** section:
- Every non-blocking id (NB1, NB2) gets one line: `NB<n> adopted: <what changed and where>` or `NB<n> rejected: <reason>`.
- Every blocking id (B1, B2) gets one line saying what changed.
- For an amendment, a line with the section, the claim that was wrong and what was observed.
- `revision` goes up by one.

Adopted non-blocking ids become acceptance criteria in the implementation brief. The pre-check fails a revision of 2 or more without this section.

## Detail limit

Name decisions, not code. No pasted code and no exact class or function names unless they are the contract. A design longer than the code it describes has written the code instead (adapted from the plan-detail rule in obra/superpowers, MIT). If a section needs more than a table and a few lines, the detail belongs in the code or in a test.

## Skeleton

Copy the headings; fill every one.

```
design-meta: tier=full modules=risk
revision: 1
# Design: <title>
## Problem, goals and non-goals  (binding decisions, then Requirements R1..)
## Grounding
## Approach
## Behaviour model
## Interfaces and data shapes
## Verification
## May decide alone and must escalate
## Build sequence, failure modes, rollback and open questions
## Risk module
```
