# Issue-to-fix-location mismatch (T2 pitfall)

Trigger: a T2 (or T1 handoff) receives a GitHub issue describing a dangling
reference / bug / regression, and the natural first move is "create a fix
branch off `origin/main`." Stop and verify the premise first.

## The mistake

Assuming the offending code lives on `origin/main` just because the issue was
filed against the repo. Issues get filed against work that is still in flight
on open, unmerged PR branches — the bug may have zero footprint on main.

Concretely observed: issue named `knowledge/judges/*.md` relative-path
references in `workflow.yaml` as dangling. `git grep` on `origin/main` and
`git log` history showed those references were **removed** on main already —
main was clean. The actual dangling refs existed only on two still-open,
unmerged PR branches (`fix-30-judge-instructions`, `fix-29-dossier-sections`)
that had introduced them. The initial plan — spin a new branch off main,
"fix" nothing (there was nothing to fix there), and close the issue with a
no-op PR — was wrong twice over:
1. It doesn't touch the actual bug at all (main was never broken).
2. The bug ships the moment either of the real PR branches merges, because
   nothing on those branches changed.

The user caught this mid-session and issued a hard stop + correction: delete
the no-op branch, fix directly on the two branches that introduced the
problem, and update their existing PR descriptions — not open a third PR.

## The check (do this before creating any fix branch from an issue)

1. `git grep -n '<the exact string/path the issue names>' origin/main` (or
   `git show origin/main:<path>` if you know the file). Zero hits → the
   pattern isn't live on main.
2. Fetch the relevant remote refs and inspect open PR heads explicitly
   (`gh pr list` and `gh pr view`); `git log --all` alone sees only refs already
   present locally. Use `git log --all --oneline -- <path>` or
   `git log -p -S'<pattern>' --all` for a corroborating history, and check
   every open PR that may contain the behavior, not only the newest one.
3. If the pattern is absent from main but present on N open PR branches → the
   fix belongs on those N branches, each as its own commit, with each PR's
   description updated to note the fix. Do NOT create a new PR off main for
   an issue whose root cause hasn't landed on main yet.
4. If genuinely absent everywhere (already fixed, or issue is stale) → that's
   a real "nothing to do here" case; confirm with the user before closing,
   don't unilaterally close an issue you can't reproduce.

## Prompt-templating gap → inline over reference

Related failure mode from the same session: a workflow engine ran model-step
prompts with `cwd` set to a run directory, and did NOT template the `prompt`
field (only shell `verify.command` fields got variable substitution). A
prompt referencing an instruction file by relative path
(`knowledge/judges/red_flags.md`) therefore dangled at runtime — from the
model's cwd, that relative path resolves to nothing.

The catch: this doesn't fail loudly every time. Transcript inspection showed
the model sometimes recovers by exploratory search (`find <guessed-root>
-name red_flags.md`) and finds the file anyway — so a handful of test runs
can look fine while the underlying contract is not guaranteed. Never treat
"the model found it once" as proof the reference resolves.

Fix pattern: when the target runtime doesn't template prompt/agent text
fields, inline the load-bearing instruction content directly into the prompt
string itself, and keep the referenced `.md`/file as the cited authored
source of truth (for provenance and future editing) rather than the sole
delivery mechanism. Before deciding a `{{workflow_dir}}`-style path
substitution is available, check what the engine actually templates —
grep its source/docs for which fields get variable substitution before
assuming prompts do.
