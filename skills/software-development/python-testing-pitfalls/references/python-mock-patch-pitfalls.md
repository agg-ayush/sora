---
name: python-mock-patch-pitfalls
description: "Diagnose Python unittest.mock/patch footguns that produce silent no-op delegation, and build hermetic subprocess-based E2E tests correctly (env scrubbing, sys.path depth, scratch-copy import loading). Use when a mock delegates to 'the real' class/method and it silently never fires, or when building a true end-to-end test that shells out to run part of a pipeline in a subprocess against a scratch copy of source."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [python, mock, patch, testing, e2e, subprocess, hermetic-tests]
    related_skills: [test-driven-development, systematic-debugging, python-monorepo-worktree-testing]
---

# Python mock/patch pitfalls + hermetic subprocess E2E tests

Class of task: a `unittest.mock.patch`-based test where a mock is supposed to
delegate part of its behavior to "the real" implementation, and the delegation
silently never fires — OR building a genuinely hermetic end-to-end test that
shells out to run real pipeline code (via `subprocess.run`) against a scratch
copy of source with edits applied.

Both classes of bug are expensive precisely because every layer checked in
isolation "looks correct" — the bug is about *timing* (when an import
statement executes relative to a patch scope) or *environment* (what the
subprocess inherits), not about the code you're staring at.

## 1. The `from module import X` inside `with patch(...)` footgun

**Symptom:** a mock's attribute is assigned to delegate to "the real" class's
staticmethod/classmethod (partial-mock pattern), an isolated unit test of just
that delegation assignment passes fine, but inside the actual `with
patch(...)` integration test the delegated call silently never executes (no
error, no side effect, nothing) — while any debug print placed inside the
target method never appears.

**Root cause:**

```python
with patch("pkg.module.RealClass", some_mock):
    from pkg.module import RealClass as _Real   # BUG
    some_mock._copy_method = _Real._copy_method  # binds the MOCK's method, not the real one
```

`from pkg.module import X` always re-resolves `X` off `pkg.module`'s *current*
attribute value at the moment the import statement executes. If
`pkg.module.RealClass` is presently patched when that line runs, the import
returns the mock — even though the code visually looks like "grab the real
class". This is easy to burn 10-20+ tool calls on, because the delegation
assignment itself, the staticmethod body, and the call site all check out fine
independently; only the *order of operations relative to the patch scope* is
wrong.

**Fix:** capture the reference to the real object BEFORE entering the `with
patch(...)` block:

```python
from pkg.module import RealClass as _Real     # capture BEFORE patching
_real_method = _Real._copy_method

with patch("pkg.module.RealClass", some_mock):
    some_mock._copy_method = _real_method       # delegate using the pre-captured ref
    ...
```

**Debugging checklist when you suspect this bug:**
1. Find every `from <same module being patched> import <same name>` statement
   textually located inside the `with patch(...)` block (or any function called
   from inside it). Any such import is suspect regardless of how many times you
   already "fixed" a nearby one — duplicate/leftover import lines from earlier
   edit passes are a common way this recurs even after the first fix.
2. Move the capture above the `with` block, or capture via
   `sys.modules['pkg.module'].__dict__['RealClass']` read before patching.
3. Re-verify with a debug print directly inside the target method — if the
   print fires only after the fix, that confirms the diagnosis.

**HARD RULE — this bug class has now caused test-file corruption FIVE separate
times across sessions, even after the rule was written down and even after the
user handed the agent the exact one-line fix. Judgment-based "stop and
rewrite, eventually" does not work here. Do not use `patch` on this bug class
at all — go straight to a full-function rewrite:**

The moment you recognize the task as "delegate a mock's staticmethod/
classmethod to the real class's version inside a `with patch(...)` scope":

1. **Before touching the file**, `search_files` it for the capture identifier
   pattern you're about to introduce (e.g. `_Real`, `as _Real`, `_real_<method>`).
   If ANY match already exists, the file is already corrupted from a prior
   attempt — you are not starting fresh.
2. **Do not open a `patch`/`old_string` call for this bug class, ever, on any
   attempt.** `read_file` the whole enclosing test function once, then rewrite
   it in a single `write_file` call with the real-class capture placed exactly
   once, above the `with` block, referenced once inside it. The incremental
   patch tool call is itself the failure mode here — not the wording, not the
   match uniqueness, not the attempt number. Skipping straight to a full
   rewrite is faster and safer than any amount of targeted patching.
3. **After the rewrite**, `read_file` the function again and confirm there is
   exactly one capture block and no orphaned syntax (stray braces, unclosed
   docstrings) before rerunning the test.
4. **If the single rewrite doesn't make the test pass**, stop calling edit
   tools on that file for this bug. State the exact diagnosis and the exact
   line(s) needing the fix in your reply and hand it back rather than
   attempting a second rewrite pass — repeated iteration here (observed up to
   7 stacked attempts in one session) is what produces the corruption, and it
   has twice required the user to manually rewrite the file by hand before
   work could continue.

Observed failure signature when this rule is skipped: each individual `patch`
call "succeeds" (matches and applies) while a slightly-reworded capture
block/comment stacks on top of the previous attempt's version, producing
multiple duplicate `from ... import X as _Real` / `_real_x = _Real.x` blocks
plus a stray leftover bracket or a broken docstring closer — nothing signals
the accumulating damage until a full re-read, by which point the file no
longer parses.

## 2. Hermetic subprocess-based E2E tests: environment and path traps

When a "true" E2E test shells out to run real pipeline code
(`subprocess.run([sys.executable, "-c", ...])`) against a scratch copy of
source with edits applied, expect to hit several of these — check them
systematically rather than one at a time when the subprocess hangs, times out,
or silently produces no signal:

- **The subprocess inherits the full parent environment by default**,
  including real API keys picked up from `.env`/shell export (e.g.
  `TFY_API_KEY`, `OPENAI_API_KEY`). If the code under test has LLM-backed
  branches, the subprocess makes REAL network calls and hangs instead of
  failing fast. Fix: explicitly scrub known LLM/API-key env vars before the
  subprocess call. But before scrubbing, check whether any of those same vars
  (or a *different*-looking one, e.g. a `_BASE_URL` companion var) is also read
  at **module import time** by an unrelated client class — scrubbing too much
  turns a hang into a new `KeyError` at import, which looks like a different
  bug. Scrub the minimum set (credentials only), keep companion config vars
  (base URLs) that gate import success.
- **`sys.path` depth for a scratch/copy tree is easy to get one level off.**
  When copying a package directory to a scratch location before running edited
  code, be explicit: the path that makes `import package_name` work (the
  PARENT of the package dir) is not the same path used for `copytree` (the
  package dir itself). Conflating the two produces `ModuleNotFoundError` or
  `ImportError: attempted relative import with no known parent package`.
- **`importlib.import_module(mod_path)` returns the cached module from
  `sys.modules` if the real package is already imported in the process** — it
  does NOT load your scratch copy, even if you pass the scratch path on
  `sys.path`. To actually exec a scratch copy while the real package is
  already imported elsewhere in the same process, use
  `importlib.util.spec_from_file_location` + `module_from_spec` directly, or
  run it in a genuine subprocess (fresh interpreter, no cached `sys.modules`
  entry).
- **`json.dumps(None)` round-trips to JSON `null`, not Python `None`.** If an
  inline `-c` runner script parses fixture JSON and compares fields against
  Python `None`/`True`/`False` sentinels, remember the deserialized values are
  JSON-native `null`/`true`/`false` — verify comparisons handle those forms,
  not just literals typed into the template string.
- **A fake/mock check function must return the exact domain-object shape the
  real dispatch expects**, not a convenience shortcut (e.g. a plain string
  instead of an `Issue`/`CheckResult`-style object the real caller
  `.extend()`s into a list). This passes when tested against the fake in
  isolation but throws a pydantic/type validation error the moment it flows
  through the real aggregation path in the full E2E run.
- **Multi-second/minute native `timeout` isn't reliably available cross-platform
  in a `terminal` invocation on macOS bash** — prefer a test-runner-level
  timeout (`pytest-timeout`, or a signal-based timeout inside the script) over
  wrapping the whole command in a shell `timeout` binary that may not exist.

## 5. A fix proven on one code path can leave a sibling path unfixed — check for duplicate implementations of the same operation

When a pipeline has two independent implementations of the same conceptual
step (e.g. an in-repo-worktree PR creation path vs. a separate
`_create_pr_via_clone` path that clones the repo fresh and reapplies edits),
fixing and verifying the bug against ONE path does not mean the other path is
fixed — even if both are supposed to produce the same end result. In one case
an "empty PR ships" bug was fixed and verified (true E2E green) against the
in-worktree path, but the clone-based path had no equivalent handling of
`fix_design_edits` at all and shipped empty PRs when that path was taken. The
re-audit that caught it treated the original fix as fully void, not adjusted.

When you find and fix a bug of this shape:
1. Grep for other methods/functions that produce the same conceptual output
   (search by the field/attribute the bug involves — e.g. every place a
   "create PR" or "stage and commit" method exists) before declaring the class
   of bug closed.
2. Apply the identical fix logic to every sibling implementation, not just
   the one your test exercises. If only one path has a hermetic E2E test,
   that's a gap to flag, not a reason to assume the other path is fine.
3. State explicitly in the fix summary which paths were checked and fixed,
   so a reviewer doesn't have to independently discover the untouched sibling.

## Related: python-monorepo-worktree-testing

For stale-editable-install shadowing across git worktrees (a different class
of "looks like a code bug but is an environment bug"), see the
`python-monorepo-worktree-testing` skill.

## 6. A constructor/signature change can ship broken even with green tests, if the class lives in another component

When a change adds or edits a constructor/function argument on a class defined
in a DIFFERENT file or component than the one under test (e.g. a caller starts
passing `SVGGenerator(model=X)` to a generator class whose real `__init__`
takes no arguments), a test suite that mocks the constructor will stay green
regardless of whether the real signature accepts the new argument — the mock
never raises `TypeError`, so nothing signals the mismatch. Observed: a model
config-swap PR added `SVGGenerator(model=LLM.CLAUDE_5_SONNET)` at the call
site and a passing test for it, but `SVGGenerator.__init__(self)` in the
actual class took zero arguments — the real code would `TypeError` on first
use, invisible to the whole test suite because the test mocked the
constructor rather than instantiating the real one.

**Check whenever a diff adds/changes a keyword argument to a class or function
that lives in a different file than the edited call site:** `search_files` the
real `def __init__`/`def <fn>` and confirm the parameter is actually declared
there — a green test suite is not sufficient proof when the constructor itself
was mocked. If the parameter isn't accepted by the real class, either the real
class needs the parameter added (a second, real edit) or the test needs a
non-mocked instantiation check (`ClassUnderTest(model=...)` constructed for
real, not through a mock) to catch this class of bug going forward.

## 3. Why it's worth pushing a true E2E through to green, not stopping at a mocked-green suite

A fully-mocked unit/integration suite going green does not prove a pipeline's
production wiring emits the observability events it claims to. In one case, a
genuinely hermetic E2E test (real subprocess QC run, real ledger, no mocked
stage callables) that finally ran end-to-end exposed that several pipeline
stages (e.g. `ts_promoted`, `coached`, `pr_created`) were silently never
emitted in production code — every existing test had mocked around the exact
gap. The fully-mocked tests were all green throughout; only the true E2E
caught it. Treat "the true E2E test still won't pass" as a signal worth
chasing all the way to fixed, not just re-mocking around the failure —
the last mile of a hermetic E2E is disproportionately where real
production bugs (not test-harness bugs) surface.

## 4. Rebasing a long-lived branch onto main can reopen already-"fixed" findings

A finding that was fixed and verified green (even via a genuine true E2E, not
just a mocked suite) is only proven for the commit it was tested at. If the
branch later rebases onto an upstream `main` that touched the same component
(e.g. an audit/upgrade PR landed on the same files), treat every prior
fix/verification as VOID until re-run against the rebased tip — a fix can
"reopen under a new mechanism": the original code path that was broken is
now fine, but upstream's changes altered a different part of the same flow
(e.g. a helper the fix depended on, a default that changed, a re-ordering)
and the same user-visible bug (e.g. "PR ships empty") comes back through a
different route. Concretely: after any rebase that crosses commits touching
the same files your fix touched, re-run the FULL suite AND the true E2E
against the new tip before reporting anything fixed or asking for merge
approval — do not extrapolate a pre-rebase green run forward across the
rebase.
