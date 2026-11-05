# Stakeholder-doc workflow rules (distilled)

Condensed always-on rules extracted from the umbrella SKILL.md. Read the
SKILL.md first; use this file as the quick-rule reference when drafting or
auditing.

## Reader matching
- Write for the ACTUAL named reader, not a "zero-context stranger" persona —
  named stakeholders already know the project, org tool names, and who's
  building it. Default to less explaining; over-explaining draws correction.
- When auditing with a subagent, name the real reader + what they already
  know, and ask only for the specific failure modes you care about — never
  "review as a VP with zero context".
- Treat audit output as candidate findings to filter and confirm with the
  user one by one, never a checklist to bulk-apply.

## Audit modes
- Fact-check against code: for docs asserting "today the system does X" —
  verify each claim at file:line.
- Completeness-check against plan: for build/decisions/scope docs — check
  coverage of the agreed build surface, not the live codebase.
- Tell the auditor which mode applies before dispatching.

## Decision filters (run every candidate decision bullet through all of these)
1. Real fork between materially different outcomes — not mechanical wiring
   (repointing an input, renaming a field, moving where a job runs).
2. This team actually made the call — not a consequence of the system
   existing, not a handed-down boundary.
3. Not the obvious/only-sane implementation or a hardening add-on — look one
   level up for the actual fork (e.g. soft-gate vs hard-gate, not the
   detection mechanism).
4. Reader doesn't already own the subsystem the decision was made in —
   restating their own design choices back to them is padding.
5. Verify ownership before attributing: "pre-existing" ≠ "built by someone
   else" — your own team's standing component is still yours.

## Structure
- Default section order: what we're building → what the end user sees (only
  if asked) → definition of done (customer-facing outcomes) → hard problems
  (problems only, no solutions/codenames) → main decisions → cost/scale →
  v2 scope → asks (LAST unless told otherwise).
- "What changes" docs: two tiers — capability-level changes on top, small
  behavioral details as flat bullets below. Never one blended list.
- Decisions + Pending + Confidence are three separate buckets; Pending (a
  decision blocked on something else) gets its own heading before
  Confidence. Confidence lines state risk reads only — cut clauses that
  don't change the reader's sense of risk.
- Prose-heavy sections default to headings + short bullet lists, not
  paragraphs.
- Decision bullets state the reason as a clipped fragment riding the main
  clause ("no shared component to take down every candidate at once"), not a
  full "because..." sentence.

## Writing discipline
- Self-contained: no "as discussed" / "the plan" / "previously" — grep for
  backward-looking phrases and rewrite each into a plain direct statement.
- Cut "today X, becomes Y" scaffolding from high-level bullets; state the
  change itself.
- After a batch of approved fixes, grep the whole doc for every other place
  the same fact is restated and reconcile all of them.
- Recency-bias check before finalizing a "what changed" list: re-scan the
  full decision trail — structural/early-settled decisions go in tier 1
  regardless of how much airtime they got at the end.
- Don't detail a part owned by another team — one-clause dependency mention,
  real estate goes to your own team's changes.
- When told "you missed something we discussed", re-pull the actual meeting
  notes doc (primary source) — don't reconstruct from lossy conversation
  history.
- Multi-part question sets: answer only the question in scope; don't pre-
  draft later answers as context.
- Don't reintroduce cut content across rewrites; live-meeting decisions need
  a one-line "why" preserved even in the shortest version.

## Hard gates
- Never push an audit fix into the stakeholder-facing doc without explicit
  per-item approval — audit findings are candidates, not authorization. Keep
  the last user-approved full text on hand so a revert is an exact write-
  back. Internal working docs have no such gate.
- A full-doc rewrite of a Google Doc can wipe previously-added tabs — always
  target `--tab <name>` explicitly and verify tab structure after any full
  rewrite (see `gog-cli` skill for the tab mechanics).
