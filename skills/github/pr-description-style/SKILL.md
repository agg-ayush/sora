---
name: pr-description-style
description: "Write collaborator-facing PR descriptions: relevant context + before/after behavior, no internal workflow narrative."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Pull-Requests, Writing, Documentation]
    related_skills: [github-pr-workflow, github-code-review]
---

# PR Description Style

Governs what goes into a PR title/description/body, regardless of which repo, `gh`/`curl` mechanics, or CI setup is in play (those live in `github-pr-workflow`). Applies whenever creating or editing a PR description — including editing an existing PR's body with `gh pr edit`.

## Ayush's standing rule

A PR description is for collaborators on the project, not a log of how the author got there. Write it **definitive**: what changed and why it matters to someone reading the repo, never how the change was produced.

## Include

- **Relevant context** — the problem or prior state that motivates the change. If this PR reverts, restores, or repairs a previous PR, name that PR and state briefly why it broke: `PR #<N> introduced <X>. It was reverted by #<M> after <Y> broke <Z>. This PR restores <X> and fixes <Y>.` That lineage is real product/repo history collaborators need — keep it.
- **Behavior change** — pre-merge vs post-merge behavior, as bullet lists. This is the core of the description.
- **Deployment/config requirements** — anything a human must do outside the repo (dashboard settings, allowlists, env vars, migrations) before or after merge. State it as a requirement, not a caveat.
- **Validation** — concrete results only: which commands were run and what they reported (e.g. "`npx vitest run` — 276 tests passed"). No adjectives, no process description.

## Exclude — internal workflow narrative

None of this belongs in the description, even if true and even if it took real effort:

- Internal review process ("fixed after our own review pass", "five parallel reviewers found...", "`/pr-review-toolkit:review-pr` run against this PR").
- Agent/session/task mechanics (which agent did what, turn limits, background processes, orchestration).
- Iteration or discovery history ("first agent got X wrong, second agent fixed it").
- Anything framed as *why the author revisited the code* rather than *what changed for someone reading it*.

The line: prior-PR lineage (#236/#237-style history) is relevant because it's part of the project's actual history and explains scope. The author's own review/iteration process is not — it's how the sausage got made, not what the sausage is.

## Reusable shape (fix/restore PRs)

```
## Context
<problem + prior-PR lineage if applicable>

## Behavior change
Before this PR:
- ...
After this PR:
- ...

## Deployment requirement
<only if manual out-of-repo config is needed; omit section otherwise>

## Validation
- `<command>` — <concrete result>
```

## Self-authored PRs during a fast infra-fix loop are the highest-risk case

When you (not a delegated T2/review gate) write a PR body yourself in the
middle of a live debugging/firefighting session — chasing a crash-loop,
running a batch, root-causing a deploy failure — the body is usually typed
straight out of your own diagnostic train of thought, and internal-narration
leaks in without you noticing:

- **Live operational counts as justification**: "we hit exactly this when the
  batch's 167 jobs sat unconsumed behind 100 crash-looping boxes" — a real
  fact, but it's *how you found the bug*, not what the fix does. Keep the bug
  mechanism, drop the anecdote: "A fleet box's golden-AMI editable install can
  point at a stale package, so fresh boxes crash-loop on
  ModuleNotFoundError... The worker's boot wrapper now reinstalls it if not
  importable."
- **Hedging "Note:" asides that narrate your own process** ("Note: this only
  raises the ceiling; the live value is set separately") — fold the fact into
  the main behavior description as a plain statement, not a caveat appended
  after the fact.
- **Self-referential cross-PR narration** ("Pairs with #N: a generated lesson
  now reaches the CDN without a manual republish pass") — "manual republish
  pass" is a description of what YOU had to do this session, not of the
  system's behavior. State the dependency plainly ("Requires #N (adds
  --publish)") without narrating the workaround it replaces.

Before merging a PR you wrote yourself under time pressure, re-read the body
once against the Exclude list above — it takes 10 seconds and catches this
class of leak before it ships, rather than needing a later cleanup pass.

## Auditing already-merged PRs for poor descriptions

When asked to review a batch of already-merged PRs for description quality
(after the fact, across a session or a date range): read every body in full
before touching anything. Most concise problem+behavior+verification bodies
are already fine — only edit the ones that actually violate the Exclude list
above (session/task narration, internal run-id-led framing, "we hit this
when..." anecdotes). Don't blanket-rewrite a batch just because you were
asked to check it; over-editing already-good PRs wastes the edit and can
strip real context (e.g. legitimate prior-PR lineage) that belonged there.
State which ones you left alone and why, not just which you fixed.

## Editing an existing PR's body

`gh pr edit <N> --body '...'` on Windows/git-bash: multi-line strings with `` ` `` (backtick code spans) or `$(...)`-looking text break single-quoted inline bodies because the outer shell still interprets `` ` `` inside single quotes is safe in bash, but embedded literal newlines and backticks through `--body` as a flag argument are fragile across the WSL/zsh boundary — use a heredoc into `--body-file -` instead:

```bash
gh pr edit 239 --body-file - <<'EOF'
## Context
...
EOF
```

This avoids word-splitting/quoting corruption when the description contains backticks, URLs, or code spans.
