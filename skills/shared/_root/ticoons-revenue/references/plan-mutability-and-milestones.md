# Plan mutability and milestones

## Platform constraints
- Approved revenue items are immutable. No endpoint edits their text or dollar value. Only pending proposals can be edited.
- When the main investor funds a Trilovation, pending proposals may already be approved into items. Run `revenue_plan_item_list` before assuming anything is still pending.
- `trilovation_update` cannot set the tier below the sum of active items. It fails with 422 `revenue_dollar_value_exceeds_trilovation_value`. Shrinking the plan or tier requires the investor to restructure. CEO-side field edits cannot do it.
- New proposals can still be added. That can only raise the sum.

## Milestone procedure
1. Anchor on the real deadline (usually quarter end, or the revenue items' measurement period) and work backwards. Ask the user for actual dates instead of filling generous guesses. Small engineering steps such as a PoC take days, not weeks; padded dates get rejected.
2. Calibrate against accepted milestones before drafting text: `milestone_list` on two or three ACTIVE Trilovations with recent plans (ADD SelfServe, Alpha Coaching Dashboard V2). Patterns they share:
   - Short plain titles stating the outcome for a person ("colleague can book assessments herself", "Release guide view to guides"), not engineering descriptions.
   - `benefit` says concretely what the beneficiary now does or gets ("She books assessments in her own UI in 3-4 clicks, without asking a developer").
   - `revenue_impact` is one line tying the milestone to the item, sometimes with buffer math before the item deadline.
3. Prerequisites and admin steps are not milestones: API access, credentials, account tiers. A PoC can be one if it is a dated, demonstrable event, but it is the least platform-typical entry; flag it as a judgment call.
4. Split a large "real build" step into dated, outcome-level steps each proving one piece of the items live (signer completes a signing through the page; the admin's sends go out with the summary attached; a feature runs on a real document), ending with the measurement period itself when the items measure a period.
5. Beneficiary: a named person or a buyer group using the exact buyer-field labels. Never the team itself (no "<Product> team"); leave it blank instead. Take the user's pick when a milestone serves more than one group.
6. Present the final pass as the complete field set per milestone (title, due date, beneficiary, benefit, revenue impact, linked item ids), so the user approves exact text. Then create one at a time and read each back before the next.
7. Keep the milestone set matching the scope communicated to the investor. When scope gains a piece (e.g. an admin ticket view) after milestones exist, propose one more dated milestone for it before the investor's review, since he approves the set he sees.
8. Milestones stay editable: `milestone_update` changes title, beneficiary, benefit, due date, completed flag and the linked item set (supplying `revenue_item_ids` replaces the whole set). Re-date and reframe in place instead of delete-and-recreate, and mark a milestone `completed` once its event has happened (e.g. PoC merged).
9. When the build order changes, re-date milestones to match. Sequence pieces whose reviewers are reachable first (e.g. the legal-admin view before the signer page when the signatory is hard to reach), keeping everything inside the measurement deadline.
10. A tier you can't lower (items immutable) is the investor's decision: offer him restructuring as investor, keeping it as is, or a new Trilovation at the smaller tier.
