# Narrative fields (description / buyer / value delta / competitors)

Rules for drafting and revising the narrative fields. Load this when drafting,
reviewing or revising any narrative field.

## What each field is for

- Each field answers **"what can't they do without us,"** not "who they are"
  or a role bio. A buyer line that restates a job title/relationship fails
  review; it must name the specific capability gap or pain.
- **description** = what the system is, what it fully automates (don't
  understate it), track record, and the quarter-end goal.
- **value delta** = concrete benefits in short lines (hours replaced, reach
  widened), each answering "so that what?" for its group, leading with the
  outcome ("sign faster: they no longer wait on..."), not the feature. The
  outcome must match the description's aims line so the fields tell one
  story. If the description names an aim, it also needs one sentence saying
  how today's gaps cause that problem, or the aim floats unconnected.
- **value delta states the customer's gain, never what the system does.**
  When a reviewer suggests a feature-phrased addition ("we manage signing
  order, it moves to the next signer automatically"), convert it to what the
  person no longer spends time on and fold it into that group's existing
  line. Taking a feature line verbatim gets rejected.
- **hard problems** = what is still hard now, stated at outcome scale (e.g.
  N concurrent users) - not already-solved problems, internal incidents, or
  build tasks the team can simply engineer. Things hard only outside our
  build effort qualify: trust (a personally liable signer acting on machine
  context), access (getting the key user's time for feedback). Plans and
  scope additions never go in buyer - those go in milestones.
- **description holds no roadmap.** Next steps and planned features go in
  milestones. When the build plan is undecided, state the problem, what is
  live, and one aims line naming the problems it sets out to solve without
  pinning undecided specifics. Use the user's wording where they place it;
  plain statements, no marketing phrasing.
- **"Current state" = the live operational flow, stated first and exactly:**
  what actually runs in production today and who does what with its output.
  Don't blend in alpha-platform features or the revival plan - those go
  under a separate "built but not wired" or "next" heading.
- **Verify what a live system's output contains from its source** (the
  prompt, template or code), not from a stakeholder's email describing it.
  Don't restate a pain the live system already solved as today's problem;
  the problem is the gap that remains.

## Provenance and voice

- **Every claim must trace to a source** (transcript, thread, repo, live
  prompt). Before writing any field or proposal, check each clause's
  provenance; if asked where something came from, say plainly you made it
  up, list every artifact it reached (platform fields, pending proposals,
  local draft files) and offer to strip it from all of them.
- **"Audit" means a clause-by-clause provenance check, not a style pass:**
  list each claim with its source, flag any claim without one (or wrongly
  attributed) as a defect with a proposed fix, and only then give a verdict.
- Don't invent competitors, numbers, or facts not true of the project's
  current state. A placeholder competitor list carried from a stale draft
  was wrong and had to be cleared.
- **Write in the user's voice: short, flat, plain sentences.** Strip
  AI-tells: narrative arcs, abstract nouns ("hardening"), em-dash asides,
  cute verbs, summary flourishes. If a phrase isn't something a busy
  engineer would type, rewrite it. Expect the user to flag individual
  phrases; replace exactly those, don't rewrite the whole piece.
- **Re-audit carried-over clauses whenever knowledge changes.** After a
  discovery meeting or research, every unchanged sentence is a fresh claim:
  check who does each step, where the output actually lives, and whether
  the pain still holds. Replace internal jargon with what the reader
  experiences.
- **No unbacked color.** Durations, frequencies and history must come from
  a source. Run the provenance audit on your own draft before showing it,
  including em dash removal.

## Field shapes this user settled on

- **Buyer:** a numbered list of buyer groups only, each with its org and
  primary named person by full name, no job title ("1. Signatories at
  Trilogy, represented by signer"). No plans or scope additions.
- **Value delta** reuses the buyer field's exact numbered group labels with
  each group's gain line; mismatched labels between the two fields get
  flagged in review.
- **Present narrative text as the complete assembled field, never
  fragments** - the user can only judge a description as a whole.
- **Revising a settled field after a scope change:** show the old text
  verbatim, then each proposed change as its own numbered item. Don't
  declare a line dead without checking every way its gain survives. New
  gains for an existing group append to that group's line. Merge changes
  that turn out to be one mechanism seen from two ends. State the work that
  disappears, not the mechanism.
- **Investor-suggested wording for description/aims is the user's call,
  including verbatim.** Point out vague phrasing and offer a concrete
  alternative, but list "use the investor's wording as-is" as an option and
  apply it exactly if picked.
- **Name spellings once corrected stay corrected everywhere** - including
  local files, chat summaries and casual references; flip-flopping back got
  called out. After a spelling correction, scan local draft files for the
  wrong form and re-read your own reply before sending.

## Competitors

- **Competitors depend on the product's settled shape.** If the build plan
  is undecided, offer to leave `narrative_competitors` blank until it is
  decided; the user chose blank over research against a guessed shape.
- **The status quo can be the competitor** when the investor or user says
  so. Pull several Trilovations' `narrativeCompetitors` (not one) and quote
  the closest matches. Settled shape, two paragraphs: (1) one line naming
  the incumbent concretely (actual tools and manual steps), (2) what the
  incumbent keeps doing, then where it falls short for each group in
  buyer/value delta. Don't open with "the status quo is not a competitor
  product" and don't close with a competitive-risk line.
- **Competitors carried from an earlier quarter go stale.** Research fresh
  for products with the same shape as ours (not just category big names);
  state their claims as marketing claims; name our real differentiators.
  Format: one numbered line per competitor - what it does, where it falls
  short versus us, in the user's own gap phrasing. When the user replaces
  the list, drop the old entries entirely. Check no line claims a strength
  the quarter's plan is removing.
- **Check what the incumbent tool already does before proposing features
  for its users.** A planned feature the existing tool already covers is
  dead, not "refine later". When a stakeholder demos their current tool,
  list which planned features it already provides and drop those.

## Scope and boundaries

- **State project boundaries the way the user draws them, in every field.**
  A sister app leverages the incumbent platform, never replaces it; its
  primary customer is the signatory. Don't over-read "the incumbent covers
  X" into killing a whole group - separate what the tool covers from the
  stakeholder's stated remaining pain. Signing order is a suggestion the
  legal admin accepts or adjusts, never automatic dispatch. Never imply we
  build what the sister system owns; drop ideas owned by the other project
  instead of parking them as "later".
- **Discovery-meeting findings are input, not scope.** Report what was
  learned grouped by theme with who said it, then name what it invalidates
  in settled fields/proposals. Do not propose adding newly surfaced pains as
  scope or fold them into fields; the user decides. Integration feasibility
  for a sister app is a research question to dispatch before claiming any
  admin-side value.
- **A scope piece added as a milestone also needs its gain in value delta
  and its gap in competitors** - append a short clause to the matching
  group's value delta line rather than leaving the milestone the only
  mention.

## Platform comparison as input

- **A platform comparison is input, not an override.** When asked to check
  a field against other Trilovations, report what differs; don't rewrite an
  already-settled version into the platform's dominant style unless asked.
- **When asked to compare a field across the platform,** pull every
  Trilovation's description (`trilovation_list` paginates at 50: follow
  `nextCursor` or split calls by `status` until all are covered, then parse
  the saved JSON offline), weight ACTIVE and recently written ones over
  one-line legacy entries, and report matches, deviations and a restructure
  as a proposal. See `accepted-description-patterns.md`.

## Process rules

- **Never write a field into the tool as final until the user has
  explicitly picked that exact text.** Present 2-3 phrasing options first;
  writing a not-yet-approved draft into the live record is jumping ahead.
- **Check the investor's chat before finalizing fields or proposals.**
  Field feedback, approval/funding timing and meeting plans arrive in Google
  Chat DMs, not on the platform; read the latest messages (newest-first, see
  the gog-cli skill) and apply requested edits before the investor approves.
- **Messages to the investor carry only what is his:** decisions he owns and
  routing asks. Questions about a customer's tool account go to the account
  holders. No recaps of meetings he attended, no status that doesn't need
  him. Typical content: a pointer to what to review/approve with a deadline,
  the scope change in one line, dependencies we need from others, his
  decision. If the user sends their own version first, accept it and only
  flag what the platform now lacks against it.
- **Before framing the project's stage, ask what is actually true** rather
  than inferring from a possibly stale record; a live, adopted system can
  look still-waiting-for-adoption in an old narrative.
