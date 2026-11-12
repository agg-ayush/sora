# Implementer brief template

Copy to `<card-dir>/impl-brief.md`, fill the `<...>` fields, and start the
implementation session with the prompt "Read `<card-dir>/impl-brief.md` and follow it
for unit `<unit-id>`." Never paste the design into the prompt. Prepend the
auto-promoted error rules (`python3 ~/.hermes/scripts/error-journal.py inject claude`)
to the prompt when that command prints any.

---

## Task

Unit `<unit-id>`: `<unit description>`. Worktree `<rundir>`, branch `<branch>`.

Read first:
- Approved design: `<design-path>` (tier `<tier>`; none means the task file is the spec: `<card-dir>/task.md`)
- Existing tests that touch the change: `<card-dir>/evidence/test-impact.txt`
- System guide and graph: the `## Context pack` section of `<card-dir>/task.md`
- Adopted review suggestions that are now acceptance criteria: `<NB ids and text, or none>`

The guide and graph are for navigation. Cite file:line you read in this session; confirm
consumer lists by grep.

## Protocol (in this order)

1. **Tests first.** Write or change the tests the design's verification table assigns to this
   unit. Run them on the unchanged code and save the failing run to
   `<card-dir>/evidence/red-<unit-id>.txt` with `capture-evidence.sh`, used as shown under
   "Evidence capture for the implementer" in `plugins/hermes-dev-process/README.md` (harness
   repo): first line is the exact test command, then the raw runner output. The run must fail for the right reason: the new
   behaviour is absent, not a syntax, import or setup error. Edit no source file before
   this file exists.
2. **Immutable tests.** Once RED is saved, do not edit, skip or delete those tests or
   weaken an assertion. Existing assertions that the change legitimately alters are changed
   in step 1, each listed with its reason under `Changed assertions` in `result.md`. A test
   that cannot be satisfied or looks wrong is a design gap: stop (see Escalation).
3. **Implement** until the tests pass. Save the passing run to
   `<card-dir>/evidence/green-<unit-id>.txt` the same way (the green command also runs the
   tests in `test-impact.txt`). Commit the unit.
4. **Run rules.** Iterate with the targeted tests and the tests in `test-impact.txt`.
   Do not run the full suite or the whole browser suite: the supervisor runs them at the
   gate. A UI card may run one targeted browser spec at a time. A flaky failure gets its
   cause fixed, never a rerun until green.
5. **Navigation.** For cross-file references, implementations and renames use Serena
   (`mcp__serena__*` via `tool_search`, `activate_project` with the repo root first);
   `read_file` and ripgrep are faster for single-file reads and greps.

## May decide alone / must escalate

Decide alone: anything the design lists under "May decide alone" and purely internal
choices (private names, local structure, helper extraction inside the files the design names).

Escalate (stop, do not guess): anything contract-visible that the design does not settle or
settles wrongly: exported names, schemas, API or data shapes, persisted formats,
user-visible text, error behaviour, a consumer the design missed, a state or transition it
omits, a claim about existing code that reality contradicts. Also stop when the task is
bigger than designed.

## Code comments and docstrings

Code comments/docstrings: terse, present-tense, necessary only; no restating what the
code shows, no issue/PR references, no narrating past/fixed behavior. Docstrings: only
what's necessary (what it does plus the non-obvious caller contract); no design-rationale
or 'why' narration the code already shows. Prefer no comment over a noisy one.

## Finish

Write `result.md` for the supervisor. It lists what changed, `Changed assertions` with
reasons (or `none`), and ends with exactly one status line followed by its payload:

```
STATUS: DONE
STATUS: DONE_WITH_CONCERNS
<each concern, one line, with file:line>
STATUS: NEEDS_CONTEXT
<what is missing and where you looked>
STATUS: BLOCKED
<for a design gap: DESIGN GAP | section | claim | what you observed (file:line)>
<otherwise: why you are blocked>
```

Use `NEEDS_CONTEXT` or `BLOCKED` when the task is bigger than designed and say so.
Never push or open a PR: the deny-guard blocks both and the supervisor does it.

## Fix protocol (fix sessions only)

Accepted findings: `<card-dir>/review/accepted-r<round>.md`. For each finding, in order:
write a test that reproduces it and save the failing run to
`<card-dir>/evidence/red-fix<round>-<F#>.txt`; fix the code; save the passing run to
`<card-dir>/evidence/green-fix<round>-<F#>.txt`. Fix every finding in one session.
Do not weaken or delete existing tests. Fix only what the findings name. If a finding
looks like a design defect, stop and report it as a design gap instead of working
around it. End `result.md` with the status line.
