---
name: content-repo-docs-map
description: "Locate, attach, and audit architecture/design documentation inside the Trilogy/content repo (alpha-learn-content-gen) — the docs/ tree, component-level ITD/IPD-style design docs, and dated design-spec archives. Use whenever asked 'where's the doc for X', 'do we have a design doc/ITD/IPD for Y', to attach new context/docs matching house style, or to audit existing docs for staleness/gaps against the current system."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [trilogy, content-repo, documentation, architecture, itd, ipd, git-archaeology]
    related_skills: [content-pipeline-data-layers]
---

# Trilogy/content Repo — Documentation Map

Class of task: find or confirm what design/architecture documentation exists
for a given part of the `/Users/ayush/Trilogy/content` pipeline (generation
workers, script workers, video export, interactions, QC, deploy, etc.), or
verify a documentation *convention* (e.g. "are we attaching ITD/IPD docs to
docs/?"). Docs in this repo are NOT all in one place and move over time —
don't assume `docs/` is exhaustive; always verify against the live tree.

## Where documentation actually lives (as of Aug 2026)

1. **`docs/architecture/`** — numbered, stage-by-stage pipeline architecture:
   `00-overview.md`, `01-article-fetch.md`, `02-planner-builder-validator.md`,
   `03-voiceover-animations.md`, `04-yaml-to-pptx.md`, `05-interactions.md`,
   `06-agent-layer.md`, `07-qc.md`. This is the primary "how the pipeline
   works" reference — read the numbered file matching the stage in question
   before searching further.
2. **`docs/info/`** — operational/working knowledge: `01-running-tests.md`,
   `02-validating-changes.md`, `03-deployment-layers.md` (canonical map of
   Supabase/S3/Review-API data layers — also referenced by
   `content-pipeline-data-layers`), `DebugLesson.md`.
3. **`docs/brainlifts/`** — educational source-of-truth specs (what a *good*
   lesson looks like), e.g. `ideal-di-math-video-spec.md`.
4. **`docs/superpowers/specs/` and `docs/superpowers/plans/`** — dated
   design-spec + implementation-plan archive (format:
   `YYYY-MM-DD-<feature>-design.md` / `YYYY-MM-DD-<feature>.md`). This is
   where Claude-Code-authored design docs + their paired implementation
   plans get committed for the record.
5. **Component-level `architecture.md` / `design/` dirs — NOT under `docs/`.**
   Several components keep their own doc, tagged **"ITD"** (Implementation/
   Infra Technical Design) in the doc title itself, not the filename:
   - `ppt-generator/architecture.md` — "ITD — Move lesson generation off
     developer laptops" (SQS worker + EC2 base sizing/cost decision).
   - `components/lesson-qc-auto-checker/design/architecture.md` +
     `healer-architecture.md` + `design/adr/001..009-*.md` (numbered ADRs).
   - `components/qti-converter/docs/IMPLEMENTATION_SUMMARY.md`,
     `FIELD_MAPPING.md`.
   - `infra/article-generation/RUNBOOK.md`, `infra/script-generation/RUNBOOK.md`,
     `infra/render/RENDER_FLEET.md` — per-fleet operational runbooks
     (bring-up, cutover, gate checklist, rollback, retirement) living next to
     the fleet's own CFN/scripts, not under `docs/`.
   - `lesson-dashboard-architecture.md` (repo root) — local asset-management
     dashboard architecture.
   **These will not show up under a `docs/` search.** If asked to find "all
   docs related to X," always also check the component's own directory for
   an `architecture.md`, `design/`, `docs/`, or `RUNBOOK.md` next to the code
   it documents.

## Attaching a new doc to docs/ (matching house style)

When the task is "write/attach our missing context as a doc" rather than
just finding one, don't invent a new format — mirror the conventions
already established by recent doc-adding PRs (check `git log --oneline
--grep='doc'` and `git log -p -- docs/` for the last few doc PRs, e.g.
PR #1384, to confirm current style before writing):

1. **Opening scope-boundary blockquote** on every doc: "Owns: X. Consumes:
   Y. Not here: Z." — states what the doc covers and explicitly what it
   doesn't, so readers don't assume it's exhaustive.
2. **"What it does (one line)"** section near the top.
3. **Mermaid diagrams** for topology/flow where it clarifies structure
   (fleet diagrams, pipeline stage diagrams).
4. **`path/file.py::symbol` anchors**, never line numbers (line numbers rot).
5. **No absolute Windows paths** in prose (fine inside fenced code blocks
   for literal commands, e.g. AWS CLI examples targeting a Windows worker).
6. **Cross-link, don't duplicate**: add a one-line pointer from the nearest
   relevant existing doc (e.g. `docs/architecture/00-overview.md`,
   `docs/info/03-deployment-layers.md`) to the new doc instead of restating
   its content inline.
7. Update `docs/overview.md`'s folder map if a new subfolder (e.g.
   `docs/infra/`) is introduced.
8. Port source content from wherever it actually lives (component
   `architecture.md`, `RUNBOOK.md`, personal reference `.md` files) rather
   than writing from scratch — copy, adapt to house style, leave the
   original in place unless asked to move it.
9. Commit on a feature branch, never main; the user reviews the PR before
   merge (don't merge unprompted even if CI is green).

There is currently no `ITD`/`IPD` string in any filename — the convention is
a doc *titled* "ITD" inline (`# ITD — <topic>`), not filename-tagged. Don't
`search_files` for the literal string `ITD` in filenames; grep file contents
instead, or rely on the git-log technique below.

## How to find docs for a topic when the location isn't obvious

Docs get moved/renamed across PRs (e.g. PR #1384 relocated
`ideal-di-math-video-spec.md` from `docs/` root into `docs/brainlifts/`, and
`DebugLesson.md` into `docs/info/`). A path remembered from a past session
may be stale. In order of speed:

1. **Check the live tree first, not memory:** `git ls-tree -r HEAD --name-only`
   piped through a grep for the topic/keyword — cheap and always current.
2. **Grep commit messages for the doc-adding commit:**
   `git log --all --oneline --grep='<keyword>'` — doc-adding commits in this
   repo tend to name what they added in the message body (e.g. "Add
   ppt-generator/architecture.md (ITD doc)"), which surfaces docs that moved
   or were renamed since.
3. **`git log --all --oneline -- '<path-glob>'`** (e.g. `'**/architecture.md'`,
   `'infra/DEPLOY.md'`) to trace a specific file's full history including
   renames — use `git show --stat <sha>` on the hit to see exactly what
   changed.
4. Only fall back to `search_files` content search across the whole repo
   once git history hasn't surfaced it — it's slower and won't catch
   docs that were deleted/moved without the keyword still present.

## Don't port dated spec/plan archives as deliverable docs

When attaching new context to `docs/`, only port *synthesized, current-state*
docs (architecture, runbooks, reference). Do NOT include files from
`docs/superpowers/specs/` or `docs/superpowers/plans/` in the same PR just
because they exist — those are working-history archives (design docs +
implementation plans as they were proposed at the time), not maintained
reference material. Ayush explicitly rejected one when it rode along in a
docs PR ("remove the specs docs, that isnt needed"). If a spec's content is
still relevant, fold the *decision* into the relevant architecture/runbook
doc; don't ship the dated spec file itself as a deliverable.

## Auditing existing docs for staleness (post-write pass)

After attaching/writing docs, or when asked to "audit the docs" for a
component, work each doc against this rubric rather than just re-reading it:

1. **Correct against live code, not memory or the doc's own prior text.**
   For any concrete claim (a file path, an endpoint shape, an env var, a
   queue name), grep the actual current source
   (`search_files`/`grep -rn`) before trusting what the doc says — e.g. a
   dashboard doc's audio-file path claim was verified against
   `audio_sync_service.py`, and a queue-ownership claim was corrected to
   `alpha-article-generation-queue` by checking the real fleet config.
2. **Completed procedural sections become history, not live procedure.**
   A runbook section describing a cutover/migration/rollback that already
   happened should collapse into a short "Migration history (completed)"
   note, not stay written as an actionable checklist — otherwise a reader
   thinks it's still something to execute.
3. **Fix stale cross-references** (`§4 B3`, `§7`, etc.) left dangling after
   collapsing sections — grep the doc for `§` or numbered-section refs after
   any structural edit and re-check each one resolves.
4. **Add missing CI/CD/deploy-workflow documentation** if a fleet/component
   has a `.github/workflows/*.yml` that isn't mentioned anywhere — check
   trigger paths and job chain (e.g. "no CFN redeploy of a live baseline;
   SSM `--update` bootstrap refreshes code, optional AMI rebake repoints the
   fleet") and note any workflow that's a hollow/stub job so readers don't
   assume automation exists where it doesn't.
5. **Make it MCP-query-friendly**: prefer tables and one-line "what it does"
   summaries over prose paragraphs, so a query like "which queue does fleet X
   use" or "is script-gen still an experiment" resolves directly.
6. Update the folder-map / overview doc's one-line descriptions to match
   the corrected content (a stale "experiment" or "cutover" framing in the
   overview index is as misleading as one in the doc itself).

### Pitfall: don't loop on incremental greps while auditing

When scanning many docs for a dangling reference (e.g. checking whether a
removed section is still referenced elsewhere), don't repeat
`head -N`-style commands with N incrementing call-by-call to "look a bit
further" — that's a loop a user will call out ("i think you're in a loop").
Instead run one bounded check that answers the question directly, e.g.
`grep -c "<term>"` across the target files (0 means clean, done) or
`search_files` with a generous limit up front, and act on that single
result.

## Pitfall

Don't conclude "no doc exists for X" from an empty `docs/` search alone —
this repo's design docs are split across at least four different locations
(see above), and component-level docs are the ones most likely to be missed
by a `docs/`-scoped search.

## Post-merge local cleanup in this repo

After `gh pr merge` lands a docs PR, cleaning up the local clone of
`/Users/ayush/Trilogy/content` can hit two snags because this repo has
tool-managed local files (`.claude/settings.json`,
`.claude/scripts/_bootstrap.py`) that drift independently of your PR branch:

1. **"local changes would be overwritten by checkout"** on a shared config
   file even though you didn't touch it in the PR. Check
   `git diff main -- <file>` before assuming it's your PR's change — if
   main's version already matches/supersedes the local diff,
   `git checkout main -- <file>` to discard the local copy, don't stash it.
2. **"divergent branches" on `git pull`** if local `main` picked up stray
   commits not on `origin/main`. Once confirmed nothing local on `main` is
   needed, `git reset --hard origin/main` is faster and correct — don't
   configure a pull.rebase strategy for a one-off.

Then `git branch -d <merged-branch>` (use `-D` if git says it's not merged
into local HEAD — expected right after a squash-merge, since the squash
commit differs from the branch tip) and `git fetch origin --prune`.
