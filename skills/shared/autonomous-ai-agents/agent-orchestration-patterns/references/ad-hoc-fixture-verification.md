# Ad-hoc real-fixture verification for parsing/normalization fixes

When a bug is reported against a real input file (a real session export, a
real payload, a real transcript) and the fix touches parsing/normalization
logic, the unit test suite alone under-proves the fix: it exercises the
function against fixtures the author controls, not the exact format that
triggered the report. Before calling a gate/review passed, run one additional
ad-hoc verification pass:

1. **Write a small standalone script that imports the fixed function
   directly** — not through the CLI/runner harness, which usually needs
   unrelated run-state (a run id, a config file, an output dir) that has
   nothing to do with what you're checking. Import straight from the
   worktree's built/compiled output by absolute path.
2. **Run it against BOTH:**
   - the real fixture file that triggered the original bug report (pull it
     from wherever it actually lives — a real submission dir, a real log
     export — not a synthetic stand-in), and
   - a synthetic edge case that isolates the exact trigger (e.g. the precise
     line-ending style, marker text, or field format named in the bug
     report), so the assertion isn't accidentally validated by something
     else in the real file.
3. **Assert concrete before/after facts**, not "it ran without throwing":
   event/record count, a breakdown by kind/type, non-empty attributed
   text/fields, absence of a fallback/error bucket that should no longer
   fire. Print the concrete numbers so they can be quoted as evidence
   (e.g. "before: events=1 kind={meta:1}; after: events=4
   kind={candidate_prompt:2, agent_message:2}").
4. **Write the script under the configured scratch directory** (`$TMPDIR`
   here, or a tool-provided scratch path), never inside the worktree. Delete the scratch dir
   immediately after capturing output. Never leave a throwaway verify
   script sitting in the worktree/repo:
   - it can get swept into `git add -A` or show up in `git status` and
     look like a stray uncommitted file to the next reviewer,
   - in a shared checkout used by multiple concurrent sessions (see the
     tier2-orchestration shared-checkout pitfall), an uncommitted file in
     one session's tree can bleed into another session's `git status` view
     and cause confusion about which files belong to which change.
5. This is an ADDITIONAL check, not a replacement for the real test suite,
   typecheck, and code review gates — run it after those pass, as the final
   "does this actually fix the reported case" confirmation.

Observed case: a normalize.ts fix for an unrecognized transcript marker
format (`## User Prompt` / `## Copilot Response`, CRLF line endings) had
16/16 unit tests green and a clean typecheck, but the real evidence that
mattered was a one-off script run against the actual reported session file
showing `events=1 kind={meta:1}` (broken, pre-fix) vs `events=4
kind={candidate_prompt:2, agent_message:2}` (fixed) — this became the PR's
verification section, not the unit test count.
