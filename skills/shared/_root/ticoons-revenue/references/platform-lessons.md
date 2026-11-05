# Ticoons platform lessons

## Platform mechanics
- One revenue plan proposal = one item with one dollar value. A multi-item plan is several proposals.
- There is no draft state. `revenue_plan_proposal_create` submits a live proposal to the nominated decider. Keep drafts in a local file until the user says to post.
- Approved revenue items are immutable. Changing them is a restructure, and only the investor can decide that.
- The trilovation value (tier) cannot drop below the sum of approved items. The API returns 422 `revenue_dollar_value_exceeds_trilovation_value`. Lowering the tier means the investor restructures the plan first.
- Funding by the main investor can approve pending proposals and flip the trilovation to ACTIVE. Re-read state before assuming proposals are still pending.

## Milestones
- Revenue impact is a one-liner of 10 to 25 words: what this milestone delivers, feeds or enables for which item. Accepted examples (ADD SelfServe, Alpha Coaching V2) are single clauses. Short item references such as "item 2" are fine.
- Never put shorthand coined during the conversation (for example "the December window") into platform text. A cold reader must understand it.
- Admin or prerequisite steps such as getting API access are not milestones. Milestones are dated outcomes that prove revenue items.
- Size dates to the real effort. The user rejects padded timelines. A PoC takes days, not weeks.

## Field writing
- Description: current state plus an aims line. No undecided plans. Next steps go in milestones.
- Buyer: who the buyer is. Gains go in value delta. Use the same labels in buyer and value delta.
- Value delta: what the customer gains, never a feature description. Example: "no longer needs to handle moving agreements from signer to signer", not "we manage signing order".
- Never add claims the sources do not support. Trace every clause to a transcript, email or the repo before writing it.

## Messages to stakeholders
- Route each question to the person who actually knows the answer. Tenant or admin facts go to the account owners. The investor gets routing asks and decisions that belong to them.
- Leave out anything the recipient already heard in a meeting they attended.
- Do not overstate scope conclusions from a meeting. Distinguish "this feature is redundant with the vendor tool" from "this whole customer or surface is out". Quote what the customer said their pain was.
