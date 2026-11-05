---
name: hermes-memory-hygiene
description: "Audit Hermes persistent memory for capacity pressure, classify entries as durable cross-session facts vs repo/environment-specific facts vs transient task state, and either migrate repo-scoped facts into the correct project context file (AGENTS.md or .hermes.md) with a git-exclude, or compact/dedupe verbose entries in place, or drop transient task state entirely. Use whenever memory usage is high, the user asks 'what's in memory' / 'can we split memory per repo' / 'clean up memory without losing anything', or a memory entry turns out to only matter inside one repo/machine or only matters for the current task."
version: 1.0.0
author: agent
metadata:
  hermes:
    tags: [hermes, memory, agents-md, context-files, hygiene, config]
    related_skills: [hermes-agent, hermes-skill-library-management]
---

# Hermes Memory Hygiene

Governs the class of task: "memory is full / cluttered — decide what
actually belongs in global cross-session memory vs what belongs in a
repo- or machine-scoped context file, then move it correctly." Distinct
from `hermes-skill-library-management` (which governs the skills list,
not memory content) and from the bundled `hermes-agent` skill (general
reference — its "Project Context Files" section is the authoritative
source for the discovery mechanics used here; don't duplicate it, read it).

## When memory is at capacity

Global memory (and the user profile store) have a hard character budget
(`hermes memory status` shows current/limit). Symptoms this skill applies to:
- A memory `add` gets rejected because the store is full.
- Usage sits near the cap (e.g. >90%) even without a rejection yet.
- The user asks about splitting memory "per repo/folder" instead of one
  global dump.

**Don't just raise the limit or prune blindly.** Most bloat in a global
memory store is repo-specific or machine-specific facts that were saved
there only because there was nowhere else convenient to put them at the
time. Those belong in a project context file, not global memory.

## Classification: does this entry belong in global memory?

For each memory entry, ask: **does this fact matter in every session
regardless of which repo/directory Hermes is running in?**

| Keeps in global memory | Migrates to a context file |
|---|---|
| User's standing workflow preferences (style, review cadence, approval rules) | Repo build/test/lint commands |
| Cross-repo infra topology the user references from anywhere (e.g. "AWS fleet X lives in region Y, detail in file Z") | Repo-specific conventions (package manager, lockfile sync, directory layout) |
| Facts about the user (identity, role, standing corrections) | Machine-specific toolchain quirks (which `python3` binary has which deps) |
| Durable lessons about *how the agent should operate* generally | Infra/service operational detail specific to one deployed box |

If an entry is genuinely repo- or machine-scoped, migrate it — don't just
leave a duplicate in both places (that's exactly the bloat this skill
exists to remove).

**Third bucket — belongs in neither store, migrate to nothing.** Some
entries are neither durable-global nor durable-repo: they're *active task
state* (an in-flight migration, a bug ticket's current fix plan, "we're
mid-way through porting X to Y", a PR/issue number). This looks
repo-scoped at first glance, which tempts you to migrate it into that
repo's `.hermes.md`/`AGENTS.md` — don't. Context files are for durable
conventions ("what the repo IS"), not live status ("what's HAPPENING in
it right now") — status goes stale the moment the task finishes and then
sits there misleading the next session. The right destination for this
class is **no persistent store at all** — it's recoverable via
`session_search` when needed. Ask: "will this still be true/relevant in
a month regardless of task progress?" If no, drop it, don't migrate it.

**Fourth bucket: already enforced or covered elsewhere, delete or move
into a skill.** The user's standing rule: memory holds only facts that no
code, config, `SOUL.md` or skill already enforces or covers. For each
entry check, with a real grep/read and not from recall:
- Duplicates a `SOUL.md` rule (BLUF, never-main, absolute paths)? Drop
  that clause only, keep the rest of the entry. Check whether a rule
  is actually in `SOUL.md` before dropping it; style rules like
  "no Oxford comma / no em dash" may be absent there.
- Enforced in code (a launcher that sets env/model ids, a guard hook) or
  read from config (current default/fallback models, a config key now
  at its safe value)? Drop it. Keep only the approval/judgment part that
  code cannot enforce (e.g. "model GROUP changes need explicit approval").
- A procedure or gotcha for one class of task (a CLI's write quirk, a PR
  tool failure, worker tool-call quirks)? Move it into the skill that
  loads for that task, after grepping that skill so you only add what is
  missing, then delete it from memory. Repo-tracked skills get the edit in
  the setup repo and a pull on every host.
- Cross-task environment facts (SSH alias semantics, venv location,
  alert chat id, approval chains, stakeholder identity) stay.

## Compacting without migrating

Sometimes every entry genuinely belongs in global memory — the bloat is
just accumulation-by-accretion (verbatim user quotes, restated
justifications, near-duplicate entries on the same topic added months
apart) rather than misplaced scope. This is a different fix from
migration: **rewrite in place, don't relocate.**

1. Read the full memory file once (`read_file` on the memories path, not
   repeated small reads).
2. Group entries by topic and merge duplicates under one header per
   topic (e.g. `MODEL CONFIG:`, `GIT/PR HYGIENE:`) — a header prefix
   makes future scanning/appending target the right bucket instead of
   grepping a flat list.
3. Strip narrative to the rule: drop direct quotes, drop the "why" once
   the "what" is unambiguous, drop enumeration of failure modes that all
   reduce to the same root cause. Keep the actionable constraint, not the
   story behind it.
4. Do the whole rewrite as one batched `memory(operations=[...])` call
   (replace old_text with the merged/compacted version) — this can cut
   usage 50%+ with zero information loss when the store's problem was
   verbosity, not scope.
5. Sanity-check afterward that nothing in the compacted version is
   secretly task-state (see the third bucket above) — a rewrite pass is
   also the moment task-state entries surface, since compacting forces
   you to actually read every line.

## Choosing the destination file

Hermes discovers context files in a fixed priority order (first match
wins per session) — see the bundled `hermes-agent` skill's "Project
Context Files" section for the authoritative discovery rules and size
caps (20k chars, head+tail truncation). The two that matter for
migration decisions:

- **`.hermes.md`** — walks up from cwd to the git root, so a copy at the
  *repo root* is visible from any subdirectory inside that repo, and a
  copy at **`$HOME/.hermes.md`** is visible from any non-git directory
  under home (the walk stops at the nearest git root, so it never leaks
  into a repo that has its own file). Use this for: machine-wide facts
  (home-level) or repo-wide facts that subdirectories should inherit.
- **`AGENTS.md`** — **cwd-only**, no parent walk. Also read by other
  coding agents (Claude Code, Codex, Cursor via `.cursorrules`), so it's
  the portable choice when multiple tools work the same repo. Use this
  for repo-root-scoped conventions when the session's cwd is reliably
  the repo root (the common case for this user's repos).

Rule of thumb: if the fact needs to reach subdirectories or a bare home
directory, use `.hermes.md`. If the fact is repo-root scoped and other
agent tools should also see it, use `AGENTS.md`. When a repo already has
one of the two, extend that one rather than adding the other (avoid
splitting one repo's rules across both files).

## Git-excluding the file

These are personal agent-notes files, not something to commit or expose
to collaborators. Add them to `.git/info/exclude` (per-clone, local-only
— never `.gitignore`, which would be a tracked/shared change):

```bash
grep -q '^AGENTS.md$' .git/info/exclude || echo 'AGENTS.md' >> .git/info/exclude
git check-ignore -v AGENTS.md   # verify it's now ignored
```

If the file was already untracked (`git status --porcelain` shows `??`),
excluding it just silences it from `git status` going forward — no
history to worry about. If it was already tracked/committed, excluding
it going forward does NOT remove it from history or the index; that
needs an explicit `git rm --cached` (confirm with the user before doing
that — it's a shared-visible change once pushed).

## Executing the migration

1. Read every existing context file at the target path first (don't
   overwrite/duplicate an existing section).
2. Write or append the migrated fact with `write_file`/`patch`.
3. Git-exclude the file (see above), verify with `git check-ignore -v`.
4. Remove the entry from global memory. Batch the removals + any
   necessary re-additions (e.g. a short pointer line referencing the new
   file's absolute path) into a **single** `memory(operations=[...])`
   call — the char-budget check runs on the final result of the whole
   batch, so a batch can free room and add a pointer atomically even
   when a lone add would have overflowed.
5. Verify: re-run `hermes memory status` (or check the tool's returned
   `usage` field) to confirm the drop.

## Multi-host trims

Mac and the remote host keep separate `MEMORY.md`/`USER.md` that
overlap. Apply the same decisions to both, then verify:
1. Back up each file first (`~/.hermes/cache/memories-backup-<ts>-<label>/`).
2. Entries are separated by `\n§\n`. Split and rewrite with python, never
   awk: macOS awk can't use a multi-character record separator. Write via
   temp file + `os.replace`.
3. List each host's entries by header (`Nn (chars): first 95 chars`) and
   grep for removed headers and for must-keep keywords (chat id, model-group
   rule, approval rules, style rules).
4. `USER.md` should be identical on both hosts. Compare md5. If they
   differ, diff per entry (`repr(x[-40:])`); trailing-newline drift is a
   common cause, so normalize with `rstrip("\n")` per entry.
5. Grep each moved item's key phrase in its destination skill on every
   host where it was moved.

When a subagent does the trim, check its result yourself. Common misses:
it leaves an entry in memory after copying it into a skill (a duplicate),
writes a new entry with a hardcoded value that a config/channel already
supplies, or drops a preference entry on one host only.

## Pitfalls

- After removal by text, inspect `removed_entries`: a match crossing a `§` separator can swallow the adjacent entry. Re-read and restore unintended deletions.
- Reconcile migrated rules against existing repo-local rules; retain explicit carve-outs. Strip incident anecdotes while moving lessons.


- Don't migrate active task/project state (in-flight fixes, ticket
  numbers, "currently migrating X") into a repo context file just
  because it mentions that repo — it reads as repo-scoped but it's
  actually transient. It belongs in neither global memory nor the
  context file; leave it for `session_search` to recover. Caught this
  live: moved a GH-issue migration status into a repo `.hermes.md`
  during a hygiene pass, user immediately rejected it ("let the session
  handle that, not the per-repo mem") — reverted. Check the third-bucket
  question above *before* writing, not after.
- Don't leave a stale pointer in memory to a file that no longer exists
  or was renamed — if you rename `AGENTS.md` to `.hermes.md` for
  discovery-semantics reasons, update the pointer text in the same pass.
- Batch classification and migration for all candidate entries in one
  pass rather than one entry at a time — each `memory` tool call is a
  full read-modify-write against the char budget; consolidate.
- Verify `git check-ignore -v <file>` after editing `.git/info/exclude`
  — a typo (missing newline, wrong path) silently no-ops.
