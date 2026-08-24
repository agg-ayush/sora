---
name: agent-tool-adoption-evaluation
description: "Evaluate a third-party AI-agent/orchestration tool (e.g. beads, amux, a new CLI coding agent) for adoption into an existing multi-agent architecture — full adoption, borrowing one pattern, or skip. Use whenever asked to research 'other tools like X', assess whether something 'replaces our arch', or decide if a tool's advertised feature (dashboard, watchdog, tracker) is worth wiring in. Covers the research→evaluate→verify methodology and the specific trap of documenting a tool's claimed capability as working before actually testing it against the real system."
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

## Pitfalls

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
