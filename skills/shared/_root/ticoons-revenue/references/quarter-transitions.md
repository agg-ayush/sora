# Quarter transitions / reviving a paused Trilovation

Full procedure for closing a quarter and opening a new Trilovation. Load when
a quarter ends or a paused Trilovation is revisited.

## New quarter = new Trilovation

- A new quarter means **creating a new Trilovation** (e.g. "<Name> Q4"), not
  reviving the old one. The old one stays PAUSED as the closed record.
- A new Trilovation starts as BOOTSTRAPPING; `trilovation_update` only
  accepts ACTIVE/PAUSED/ABANDONED/SOLD/INBACKLOG, so BOOTSTRAPPING cannot be
  set by hand. The first investment makes it ACTIVE.
- Met revenue is recorded on the Trilovation that earned it and needs
  `revenue:write` (admin/investor); don't carry old items into the new one.
- Fundability clocks start at creation: >3 days with no revenue plan or >7
  days with no milestones means "not fundable".
- **Never flip to ACTIVE with zero or thin capital.** ACTIVE burns daily; a
  deficit day counts against it and four deficit days auto-mark it
  ABANDONED. Secure funding first; BOOTSTRAPPING/PAUSED do not burn.
- An ACTIVE Trilovation is forced "not fundable" if, after a few days, it
  lacks a revenue plan, investor narrative or milestones - have all three
  drafted before activation.

## Decision log

- Decision-log entries are permanent (no edit/delete) and are the only place
  progress evidence lives. A quarter transition takes two CEO decisions: a
  close-out on the old Trilovation (goal reached, evidence, work continues
  in the new one, old stays PAUSED) and a founding entry on the new one
  (the quarter goal, why, starting point). Keep each to the decision plus
  its reason; status detail is not a decision.

## Milestones and revenue item

- Milestones and the revenue item are separate pieces: milestones are the
  dated events (a named person confirms a round ran clean; N users came
  through the self-serve path), the revenue item is the outcome they prove,
  with its deadline at the latest milestone it depends on. Take milestone
  order and dates from the user. See `plan-mutability-and-milestones.md`.
- **Milestone-to-item links must be direct.** Link a milestone only to
  revenue items whose named confirmer actually benefits from it. If asked
  how a link relates, admit an indirect or weak link plainly and propose
  dropping it.
- **Milestone revenue-impact lines: one plain, self-contained line** on
  what the milestone does for the item, readable cold, naming the item by
  what it requires, not internal shorthand. No dependency scaffolding.
- A met revenue item with no `record_revenue` entry is invisible to
  investors; include the revenue record in the draft set, stating precisely
  what was delivered vs what the item promised (who committed, which date).

## Carrying the narrative over

- After the proposal text changes, re-audit description and value delta
  against it (description still saying "no scheduling" when the plan has
  candidates scheduling themselves; value delta still claiming last
  quarter's gain). Value delta must state this quarter's change.
- When carrying a narrative into the new quarter, re-check every field with
  the user one by one; buyer/competitors may carry over unchanged, but hard
  problems and the goal usually shift. Ask, don't copy wholesale.
- Before drafting competitors for the new quarter, pull several
  Trilovations' `narrativeCompetitors` (not one) from `trilovation_list` and
  quote the closest matches. See `narrative-fields.md` for the settled
  competitor shape.

## Process discipline

- List the whole set that needs to change (status, narrative refresh with
  real numbers, revenue record for any met item, next-quarter proposal,
  milestones, CEO decision log entry, funding ask) so nothing gets
  forgotten, but then work through it **one piece at a time**: draft one
  piece, get the user's edits, settle it, then move to the next. Dumping
  the full drafted set at once gets rejected as rushing.
- The Trilovation is a black box to TiCoons; only outcomes matter.
  Milestones and revenue items must be outcome-level, never internal
  engineering metrics or incident classes. Don't mention internal incidents
  or fixes in the narrative either.
- Use the user's own deadlines exactly; don't round to "two weeks"-style
  windows of your own.
- When the user's request conflicts with a platform constraint (e.g. asks
  to set BOOTSTRAPPING), explain the constraint in two or three plain
  sentences before drafting anything further. Don't keep relaying
  agent-to-agent jargon past a confused user.
