---
name: agent-tool-adoption
description: Evaluate third-party agent tools against a live workflow.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tool-evaluation, orchestration, third-party, verification]
    related_skills: [tier1-suborchestration, tier2-orchestration, infra-migration-staged-rollout]
---

# Agent tool adoption evaluation

Governs the class of task "should we adopt/borrow from third-party tool X for
our agent architecture" — distinct from actually building the tier pipeline
(that's `tier1-suborchestration`/`tier2-orchestration`). This skill is about
the research → judge → verify loop when a new tool enters the picture.

## Step-by-step

1. **Research the tool's real architecture, not its pitch.** `web_search` +
   `web_extract` the repo/docs. Answer concretely: is it a replacement runtime,
   or a layer over the same underlying CLIs (Claude Code/Codex) you already
   use? Does it manage its OWN state/workers, or does it attach to arbitrary
   external state? These distinctions decide whether "adopt wholesale" is even
   coherent, before comparing feature lists.

2. **Evaluate against your architecture's actual constraints, not a feature
   checklist.** For each capability the tool advertises, ask "does our system
   already have an equivalent, and if not, is the gap real enough to justify
   the switch/dependency cost?" Give an honest yes/no verdict when asked
   directly — don't hedge with "it depends" once you've done the comparison.

3. **Prefer borrowing the specific pattern over adopting the whole tool** when
   only one feature is genuinely valuable and the rest of the tool would
   duplicate or conflict with your own orchestration (state ownership,
   lifecycle management). Port just that mechanism into your own scripts/skills.

4. **CRITICAL — verify any claimed integration/compatibility by actually
   running it against your real system, before writing it into docs as
   "available" or "built."** A tool's README/feature description describing
   what it does in ITS OWN terms does not mean it interoperates with YOUR
   existing state. Concretely: install it, point it at your real
   sessions/data, and check.
   - **Observed failure:** amux was documented in a repo README as "a
     mobile-accessible dashboard view over the same tmux sessions" the tier
     system spawns. When actually installed and run, amux only displayed
     workers it spawned itself — it does not discover pre-existing arbitrary
     tmux sessions. The documented claim was wrong until someone asked "did we
     build this?" and it got tested for real.
   - The fix pattern: "we evaluated X and it looks compatible" is a hypothesis,
     not a documented fact. Only write "supports Y" into a README/reference
     doc after you've run Y and watched it work — same standard as any other
     shipped claim.
   - This applies just as much to your OWN system's claimed capability, not
     just the third-party tool's. When the adoption question hinges on
     whether your existing setup "already has" a feature the candidate tool
     offers (e.g. "we already have dependency graphs via kanban link"),
     don't conclude that from `--help` text or command references alone —
     spin up a scratch instance (a throwaway board/repo/branch) and exercise
     the actual mechanic (create the edge, query the filtered view, confirm
     the result) before writing the "no gap" verdict. A `--help`-only
     comparison can miss that a primitive exists but a *convention* for using
     it doesn't — which is a real, closable gap even though no new feature is
     needed.

5. **On an ambiguous/unanswered `clarify` for a decision that has real side
   effects (installing software, cloning a repo, starting a background
   server/process), do not guess the most action-generating interpretation.**
   If `clarify` returns empty, retry once; if still empty, default to the
   *safer, reversible* option (document/plan only) and say explicitly what you
   defaulted to and why, rather than silently proceeding to install/run. This
   mirrors the empty-`clarify` handling in `infra-migration-staged-rollout`
   (escalate via a durable channel, don't proceed on a guess) — the same
   discipline applies outside migrations, any time the ambiguous branch
   triggers a side effect that's non-trivial to undo (a cloned repo, a
   listening server process, a spawned worker).

6. **Clean up speculative installs immediately if the evaluation is negative.**
   If you install a candidate tool to test it and it turns out not to fit,
   kill any process it started and remove the clone — don't leave dead
   evaluation artifacts lying around "in case." When the negative verdict
   also means removing a reference to the tool from docs you'd already
   written it into (README, reference doc, audit response), do the removal
   AND bump that doc's own "last updated"/date-stamp line in the SAME pass
   — a stale date next to freshly-changed content is its own inconsistency
   the next reader will trip over. Don't rely on being asked twice.

7. **When the candidate is a fork/derivative of YOUR OWN system** (a
   colleague adopted your setup and modified it, rather than an unrelated
   third-party tool), establish the fork point BEFORE diffing or dispatching
   comparison subagents: `git log --reverse --oneline | head -1` on their
   clone to find their first/base commit, then `git log --oneline --after=
   <that date>` on your own repo to count what you've shipped since. A raw
   file diff can't distinguish "their genuine improvement," "their
   regression," and "stale content that predates a fix you already made" —
   without the fork-point check, an LLM diffing subagent will misclassify
   your own subsequent progress as either their innovation (if it happens to
   differ) or their bug (if their code is just old). Do this check first,
   not after dispatching audits — if audits are already running when you
   realize the divergence, `delegate_task(action='steer', ...)` each one
   immediately with the fork date + a summary of what shipped since, and
   instruct it not to recommend regressing to anything that's simply an
   older version of your own code.

   **Same-system fork diffs (skill files, config, prompts) also need a**
   **per-hunk categorization scheme**, not just a fork-point date check —
   even within "their side changed this," you still need to split
   "identical/cosmetic," "our content unchanged," "their edit of our
   content" (assess: improvement/lateral/regression), "content they added
   that we lack," and "our content they don't have" (assess: predates their
   fork vs. we deliberately dropped it). Report at that granularity — a
   flat "N differences found" summary hides which direction each one cuts.

   **Verify referenced artifacts exist before crediting a text addition as a**
   **real improvement.** A forked skill/prompt/doc can describe a mechanism
   ("run `ask-readers.py`", "check `cost-guard-state.json`", "the
   `state-transition-reviewer` agent") that's just prose in their fork with no
   backing script/file, OR document something that already exists silently on
   your side. For every new script/agent/config path the fork's text leans on,
   `ls`/`search_files` it on BOTH sides before writing a verdict:
   - Exists on your side too, undocumented → their version is a genuine
     **doc improvement** (write it up on your side; the mechanism is real).
   - Exists only in their fork → a genuinely novel **idea with real backing**,
     but adopting it means porting the artifact, not just the prose — flag as
     "requires building infra," not a drop-in doc merge.
   - Referenced by neither side's filesystem → aspirational text; note it but
     don't rank it as a proven improvement.
   Skipping this check means a diff-only reading can't distinguish "they
   invented and built something real" from "they wrote a nice paragraph about
   a script that doesn't exist," and both look identical in the text diff.

8. **When the task's output contract requires a single raw JSON object**
   (a validator rejects prose or malformed JSON, e.g. "Reply with ONLY the
   corrected JSON object... no prose"), build the object as a Python dict
   inside `execute_code` and serialize it with `json.dumps(...)` rather than
   hand-typing the JSON text in your final message. Evaluation reports for
   this skill are long, multi-paragraph, and full of quotes/apostrophes —
   hand-authoring JSON at that length is exactly what produces the delimiter
   errors ("Expecting ',' delimiter") a strict validator bounces. Constructing
   the dict in code and printing `json.dumps(report)` guarantees valid escaping
   and lets you inspect the exact string before it becomes the final answer.

9. **Verify claimed "bug fixes" by tracing the actual control flow, not by**
   **trusting the fork's own framing.** A fork's commit message or comment
   calling something a bug fix is a claim, not a verdict. Read the base
   version's logic path that the fix touches and construct the concrete
   failure scenario yourself (e.g. "what happens when this branch is hit with
   an empty set / a clean worktree / a missing key") before agreeing it's a
   real bug. Two outcomes to watch for, both real in the same session:
   - The claimed bug doesn't reproduce in your environment at all (e.g. a
     path-resolution "fix" for a `profiles/` directory structure you don't
     use) — real for them, irrelevant for you. Say so plainly rather than
     porting it anyway.
   - The claimed bug is real and reproducible in your own base code once you
     trace it (e.g. a status-complete check that fails when a worker already
     committed its changes and left a clean worktree — the exact state a
     *finished* agent produces). Confirm by reading your own file at the
     matching line number, not by assuming the fork wouldn't have touched it
     if it weren't broken.

10. **Verify claimed "improvements" that reference a CLI flag or command**
    **behavior by invoking `<command> --help` (or running it) yourself**,
    not by trusting the fork's skill/doc prose. A fork's SKILL.md asserting
    "`hermes send -t telegram` delivers to the home channel, no chat-id
    needed" or "`kanban complete` takes `--summary`/`--metadata`" is only
    confirmed once you've run the actual `--help` output and read the flag
    description — the same discipline as verifying a referenced script exists
    (step 7), applied to CLI surface area instead of files on disk.

11. **When adopting the tool (verdict positive), deploy to parity with the
    previous state, nothing more.** Replace what the old system did on each
    host; do not add capabilities the old setup never had (e.g. cross-host
    memory sync, extra repos, sync crons) just because the new tool supports
    them. Each extra piece is new infra the user must own; propose it as a
    separate option instead of building it.

12. **Make integrations shareable when that is in scope.** If users need to
    reuse adapters across harnesses, choose one maintained source of truth,
    document supported installation routes, and avoid duplicated copies.
    Fork upstream or create a public `integrations/` hub only with appropriate
    ownership and publishing authorization.

13. **Swapping a model into an existing route: check protocol and catalog**
    **first.** Before promising a model in a tier route, (a) list what the
    gateway actually serves (`/v1/models` on the TF gateway) and compare only
    against models we can call, at the same reasoning level for all; (b)
    check the route's wire protocol: routes that drive the Claude Code CLI
    need an Anthropic-compatible endpoint, while OpenAI-protocol-only
    gateway models need a Hermes-native or Codex-style runner. Verify with a
    real completion through Hermes (`-m <alias>`), not just curl, and give
    each new model an alias plus per-model `context_length`.

14. **Do not leave adoption work latent on a branch.** After verification,
    publish the intended PR or handoff artifact and report its actual state.
    Merge or commit directly to main only when the user/repository policy
    authorizes that route; approval and a pushed branch alone are not a
    blanket merge authorization.

## Pitfalls

- Diffing a colleague's fork of your own architecture against your current
  HEAD without first checking how long ago they forked — flags your own
  subsequent fixes as "differences" with no signal on which side is stale.
- Accepting a fork's "this is a bug fix" or "this is an improvement" label at
  face value — trace the control flow yourself for bug claims, and run the
  actual `--help`/command for CLI-capability claims, before crediting either
  in the final report.
- Crediting a fork's prose addition as a proven improvement without checking
  whether the script/agent/config it references actually exists on either
  side — text describing a mechanism and a working mechanism look identical
  in a diff; only a filesystem check tells them apart.
- Hand-typing a long JSON verdict/report directly in prose when the output
  contract demands strict JSON — build it as a dict and run it through
  `json.dumps` instead; manually-escaped quotes in multi-paragraph fields are
  the recurring cause of "not valid JSON" rejections on these reports.
- Writing "tool X gives us Y" into a reference doc from the tool's own
  documentation alone — always a hypothesis until tested against your real
  system.
- Citing existing code IN THE TARGET REPO as validated precedent just because
  it exists and does something structurally similar to what you're proposing
  (e.g. "there's already a majority-vote stabilizer here, extend that
  pattern"). Presence in the codebase is not evidence of quality — a repo can
  have plenty of bad code. Don't launder an unverified internal pattern into a
  recommendation by treating "it's already there" as if it were "it already
  works." If you haven't read the code closely enough to vouch for it, say
  "there's a similar pattern at path:line, unverified" rather than proposing
  to build on it as though it were known-good.
- Treating "it's a layer over the same CLIs we use" as "it's fully compatible
  with our state model" — a layer over the same underlying tool can still
  have a totally separate, non-interoperable state/worker model.
- Defaulting to the most work-generating interpretation of an ambiguous/empty
  `clarify` response (e.g. "install and run" vs. "just document") — default to
  the reversible option and flag the assumption instead.
- Recommending full replacement of a working, deeply-integrated internal
  system just because a newer tool has a slicker feature list — weigh
  migration cost and check for a narrower "just borrow the one good pattern"
  option first.

## Support files

- `references/tool-evaluations.md` — condensed evaluation notes (beads,
  amux) from sessions that vetted these against a kanban-based tier
  orchestration architecture; useful as a template for the next tool eval.
