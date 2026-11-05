# Getting a drafted proposal in front of the decider, and doc separation

## Nominating an investor to a drafted proposal

`revenue_plan_proposal_create` needs `revenue-plan:govern` scope you likely
don't have as the drafting agent — draft it anyway (the tool still lets you
create as `pending`), then get it to an actual investor:

- **`revenue_plan_proposal_nominate` requires all three of `trilovation_id`,
  `proposal_id`, AND `nominated_ticoon_id`** even though the proposal object
  already carries its trilovation internally — the call is rejected with a
  missing-argument error if you only pass `proposal_id` +
  `nominated_ticoon_id`. Look up the trilovation id first (`trilovation_list`
  / `trilovation_get`) if you don't have it handy, or read it off the
  proposal object if you already fetched one.
- **There is no public/shareable URL for a proposal** — it only exists
  inside TiCoons. To get it in front of a stakeholder: nominate them as the
  decider (they see it in their own TiCoons view when they log in) or hand
  them the raw proposal id / full text directly (e.g. in a DM). Don't imply
  a browser-shareable link exists.

## Raw brainstorm vs. stakeholder-facing docs — keep them separate

When the user is thinking out loud (their own ideas, or relayed from a
side conversation with a colleague) about the broader methodology/product,
don't fold those raw thoughts directly into a doc meant for the external
stakeholder (e.g. a customer, an investor, a CEO). Maintain two docs:

- A **raw ideas doc** — unfiltered, chronological capture of brainstormed
  points, SPOV/outcome candidates that haven't been vetted, notes from side
  conversations. This is the working scratchpad; write everything down,
  including half-formed or contradictory points, don't pre-filter.
- The **stakeholder-facing doc** (brainlift, proposal writeup, narrative) —
  only the refined, vetted subset that survived review, in the polished
  tone/structure the stakeholder expects.

Don't refine-and-publish raw brainstorm in the same pass it's captured.
Capture first, ask which parts graduate to the polished doc, only then draft
that version. Similarly, when the user says "let's prepare content before
sending" a nomination/approval ask, that's a request to draft supporting
docs alongside the proposal — not a request to draft or send the actual
outbound message yet. Hold off on the message itself until the user
explicitly says the content is ready.
