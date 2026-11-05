# Ticoons platform mechanics

- No draft state: `revenue_plan_proposal_create` submits a live pending proposal to the nominated decider. Keep drafts in a local file until the user says to put them up.
- One proposal = one item with one dollar value. A multi-item revenue plan is several proposals (e.g. Alpha Coaching V2 has five). Don't try to bundle items into a single proposal.
- Proposals together should add up to the trilovation tier value. If you change the tier (`trilovation_update` value), check that the proposal sum still matches it.
- `trilovation_list` is alphabetical and paginated (default page of 50). Pass the full cursor value, not a truncated one.
- "Build context from X" means read-only. Don't write repo URLs or anything else into trilovation fields (e.g. project_context_urls) unless the user explicitly asks.
- Proposal items must state a behavior or outcome that a named counterparty confirms. Leave out how the product works: implementation detail turns the item into something the team can mark done themselves.
