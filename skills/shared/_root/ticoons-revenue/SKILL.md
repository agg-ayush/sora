---
name: ticoons-revenue
description: Draft Ticoons trilovation narratives and revenue plans.
---

# Ticoons narrative + revenue-plan authoring

Two coupled artifacts live on every Trilovation: the **narrative** (description / buyer / value delta / competitors — the story) and the **revenue plan** (the measurable proof the story is true). Both go through the `mcp__ticoons__*` tools. This skill is about the *drafting discipline*, not the tool mechanics (see `mcp__ticoons__get_platform_guide` for domain concepts/behavior rules — read it once per new Trilovation before touching fields).

## Before touching anything

0. Find the Trilovation id with `mcp__ticoons__trilovation_list` passing `query` (short name fragment) and `scope: "all"`; the unfiltered list is paginated at 50 and silently omits later names. Each `mcp__ticoons__*` call goes through its own `tool_call` (local MCP tools cannot be batched). `whoami` gives the caller's ticoonId and scopes.
1. `mcp__ticoons__trilovation_get` — read the current narrative in full. Never overwrite a field you haven't read.
2. Pull `mcp__ticoons__get_investor_report` too: one call returns status, capital, runway, milestones, revenue plan text and recorded revenue, which is the state an investor actually sees. Use it to list every gap before drafting.
3. **Ground every claim in the project's full delivery history, not the latest event.** Pull the complete record from the product's own data (e.g. sessions per cohort/day since go-live, completions) before framing progress or revenue. Anchoring on the most recent batch undersells the work and misstates the track record.
3a. **"Build/get context" means read-only.** When the user points at a repo, transcripts or docs and asks for context, only read and report back an understanding. Don't draft fields, and don't write anything to the Trilovation, not even `project_context_urls`, until the user explicitly asks for that write. Reading context and wiring it into the record are separate requests; doing the second unasked gets a sharp correction. If you did write something unasked, say so and offer to revert, don't defend it.
3b. **Reporting context from transcripts/meetings:** read only the timestamp ranges the user gives (other speakers' segments are unrelated projects). Report grouped by theme (origin/current state, who it's for and what they care about, core feature, current build state, plan, open questions, priority), attributing each point to who said it and when, with no drafting and no recommendations mixed in. Mark what is stated vs inferred.
3c. **Find the original problem statement in its source.** Before framing a description, look for the stakeholder thread where the pain was first described (often an email chain forwarded by the investor/sponsor) and read it bottom-up. The signer's or buyer's own words (volume, missing context, hours lost, their fallback if nothing changes) are the grounding; meeting recaps are secondhand. An investor's message asking for the Trilovation also tells you who approves the revenue plan.
3d. **Field-level drafting rules** (what each field is for, the settled field shapes, provenance/voice rules, competitor and boundary rules, investor-comms rules) live in `references/narrative-fields.md` — load it whenever drafting, reviewing or revising a narrative field. Headline rules: every claim traces to a source; "current state" = the live operational flow, stated first and exactly; the description holds no roadmap; write in the user's plain voice, never marketing phrasing.
3e. **When the user says "give me the pointers, I'll write it myself",** return grounded bullet pointers grouped by theme (problem, what the stakeholder said it must carry, what's live, gaps/next, field-writing constraints), each attributed to its source. No draft options, no assembled text.
4. If updating rather than authoring fresh, identify exactly what scope/content the existing text carries — a rewrite must fold the old scope in, not silently drop it.

## Revenue-plan proposals

1. **Calibrate against already-approved plans before drafting anything new.** Pull `revenue_plan_item_list` for a few other trilovations (`trilovation_list` first to find ACTIVE/BOOTSTRAPPING ones) and read what actually got accepted. This is the single highest-leverage step — it reveals the real acceptance bar, which is narrower than it looks from first principles.
   - See `references/accepted-revenue-plan-patterns.md` for worked examples (older bundled (a)/(b)/(c) items and the newer single-sentence style) and the pattern extracted from them. Prefer the newer style when drafting; the reference says how to find more ACTIVE plans quickly.
   - Check your own draft against rule 6 below before showing it: a bundled "(b) no request had to be pulled back" clause is a guard clause the user didn't ask for.
2. **The observed pattern:** a named person **confirms** ((a) a specific behavior/outcome happened, and (b) no negative escalation occurred), plus sometimes a technical-soundness confirmation from a second named person. Not a process description, not an internal metric nobody outside the team would check.
3. **Present candidate outcomes as a flat numbered list**, one line each, so the user can accept/reject/edit per item in one pass without you re-explaining context per item. This is how the user wants to triage a list of options generally — don't bundle several candidate metrics into one paragraph.
4. **Hard filter — cut anything not in our control.** If an outcome depends on another party's future behavior or an unmeasurable internal state ("stakeholder saves N hours" — we don't know his baseline or control his time; "teams fix what we flag" — depends on the team, not us), it gets rejected. Reserve outcomes to things we can directly measure and are accountable for delivering (e.g. our own response latency, our own audit-flag coverage, an audit trail we generate).
   - Corollary: **don't put "what we don't control" into the revenue plan proposal itself**, not even as a caveat section. If it's worth flagging, it's an internal risk note, not part of the customer/investor-facing plan.
5. **"Revenue item" and "specific outcomes" are different fields with different content** — revenue item is the one-line WHAT (the goal), specific outcomes are the measurable confirmations that PROVE it happened. If they read as the same sentence restated, split them: state the goal once, then list the outcome(s) that would confirm it.
6a. **Proposal shape: a separate context line, then the plan as one claim.** Structure that got accepted by the user:
   - `Context:` one line defining the thing the plan depends on (e.g. what the platform does). Kept apart so the plan isn't polluted by context. Use future tense if it isn't live yet ("in Q4 the platform goes live"), since approved items are permanent and a wrong "is live" contradicts the milestones.
   - The plan: `By <date>, <named person> confirms that <outcome for a defined set>`, plus one baseline line ("Today she does X herself; on the platform, Y").
   - No feature bullets in the plan (a feature list is rung-2 capability, not an outcome), no guard clauses, no edge-case sentences. Each review round tempts you to bolt on another clause; that accretion turned a proposal into an essay and got rejected loudly. Don't add requirements nobody asked for ("in writing").
   - When the review agent proposes a "fix", check it doesn't re-merge context and guards back into the plan before relaying it.
   - Fact-check the review agent's example wording against sources before adopting it. It only sees the platform, so its "for example" sentences invent mechanisms and drop the user's settled format. Keep its structural point, replace its facts with verified ones and its format with the settled one, and say which parts you changed and why.
6b. **Milestone revenue-impact lines: one plain, self-contained line on what the milestone does for the item.** Each line must read cold, without the other milestones: name the item by what it requires, not by internal shorthand coined in chat. No dependency scaffolding ("without it, Y can't happen"). Accepted shape: "Delivers the booking half of the revenue item and leaves 10 days before Oct 23 for her to use it on real batches." See `references/plan-mutability-and-milestones.md` for the full milestone procedure.
6. **Default to no guard clause.** The named person's confirmation already carries the quality check (they won't confirm if users got blocked), and accepted items exist without one. Only add a negative-condition line if the user asks for it, and then as its own line, not folded into the metric.
7. Don't assume unstated relationships/facts when writing someone else's story. If a claim about who talks to whom, who decides what, or who is blocked is not something the user explicitly said, ask rather than assert it.
7a. **Platform shape: one proposal = one revenue item.** `revenue_plan_proposal_create` takes a single text and a single dollar value; a plan with N items is N proposals (each maps to its own `revenueItemId` on approval). If the user expects "one proposal with two items", explain this rather than merging items into one all-or-nothing proposal. There is no draft state: create sends a pending ask to the nominee, editable via `proposal_edit` until decided. Keep drafts local until the user says to put them up; if they explicitly say "just add it" after hearing the hold reason, that overrides the hold. Give the hold reason once in two or three lines, then do what they say; don't re-argue.
7b. **Proposal values must sum to the Trilovation's value tier.** `dollar_value` isn't checked against the cap until approval, so an over-cap plan submits silently and fails later. When the agreed plan total differs from the tier set at creation, flag it and change the tier with `trilovation_update` (`value`) once the user says so; confirm the new value from the update response.
8. **Get the proposal reviewed before submitting it.** infra lead (Ticoons admin) requires every revenue-item proposal to be reviewed first: either by the built-in TiCoons agent, which knows the review bar, or with the review skill he shared. He rejects agent-written "LLM slop" and treats the text as the author's own thinking and reputation. Ayush may run the review himself through the TiCoons agent. Hand him the exact final text and wait for his sign-off. When he wants to review with the TiCoons/infra lead agent, prepare the draft for the current piece as concrete text plus the specific questions to ask the agent about what that field needs. The agent decides whether the text aligns with the field; we don't finalize field shape ourselves. The review agent lives on the TiCoons platform side and the user relays its replies; don't simulate it. Never call `revenue_plan_proposal_create`/`edit`, `trilovation_update` or `milestone_create` before that review happens, and that includes status flips and URL fields. See also `references/proposal-review-bar.md` and `references/proposal-nomination-and-doc-separation.md`.

### Relaying to the TiCoons/infra lead agent

- Give the user the exact text to paste, nothing else: no "take this to it" instructions, no meta-notes around it.
- Settle every answer with the user before it goes into agent text. Never fill in decisions yourself (copy old narratives, a tier, a description) inside a relay message; the agent's questions come back to the user as a discussion first.
- The agent only sees the platform. Never mention internal people, group messages, deadlines from internal comms, or internal manual processes. State platform-level facts and outcomes only.
- Phrase our decisions as directives to the agent ("Create a new Trilovation for Q4"), not as questions asking whether to do them, and not as "I'm doing X".
- No long em dashes in relay text; a plain hyphen is fine.
- **The user does not read the agent's replies; they read your summary.** When they paste an agent reply, say in a few plain lines: what the agent did, what each draft it holds is FOR (which Trilovation, which decision, why it needs to exist), and the exact questions it is waiting on. Explain the purpose before any sentence-level choice.
- For each agent question, give your recommendation and let the user decide item by item. Only after every item is answered, write the relay text. Writing a ready-to-send message that bakes in your own picks (even obvious ones) gets rejected.
- **Status and next-step replies: one thing at a time.** Give only the single next action (plus the exact text if one is needed), then stop. If a request like "what's the wording" is ambiguous, prefer showing the stored artifact text over drafting a new message.
- Keep a settled-phrasing ledger in your head: when the agent returns a rewrite, diff it against every qualifier the user already settled and restore any that dropped out before relaying approval.
- Don't assert which steps of the user's process are manual vs automated; ask. A "why" built on a wrong assumption has to be redone everywhere it was used.

## CEO decision-log entries

1. Pull `decision_list` (category `ceo`) for this Trilovation and for one or two ACTIVE Trilovations with recent entries, to match the accepted style and avoid duplicating an existing entry.
2. Accepted shape: a short decision headline, one sentence stating the rule or choice as it now applies, then `Why:` with the evidence. Example: "Two bookings at a time per student. From S2, a student can hold at most two coaching bookings at once... Why: booking data showed one student with 15 calls booked within a week..."
3. Only actual decisions about how the product or build works (scope choice, build order, policy). Never a log of events: no "PR merged", test counts, review rounds or links. Never context dressed as a decision: a stance already captured in a narrative field (e.g. "the competitor is the current flow") is not a decision.
4. Keep implementation specifics out (lists of API operations, flow steps); state the decision at the level an investor reads.
5. Run the humanizer skill on each entry before showing it, then present exact text and write one at a time after approval; read back each stored body.
6. Never mark a milestone `completed`, or include "mark complete" in a proposed update batch, on proxy evidence (merged PR, simulator/mock run). Completion means the real-world event in the milestone happened (e.g. wiring proven against the actual vendor account); a user approving a batch that bundled the flip does not validate it. Ask about completion as its own question, stating what evidence exists. When completing, make the milestone text match what was actually proven (e.g. "simulated tenant" becomes "real tenant" if the proof ran against the real vendor account) in the same `milestone_update`, and read back both `completed` and the benefit.
7. When resequencing milestones, read back every returned record and flag any field text that differs from what you last wrote (others may have edited it).
8. After logging, check existing milestones and narrative fields against the new decisions; if one now reads off-decision (e.g. a milestone framed around a side the decision says we don't rebuild), propose a `milestone_update` reframe.

## Creating a new Trilovation

- Read the `trilovation_create` schema, then ask the user only for the required fields in one numbered list (name, description, CEO, value tier), with optional fields listed separately. Pull `ticoon_list_active` up front so the user can pick the CEO by name instead of supplying an id.
- A blank description is accepted (empty string) if the user wants to fill it later. Create with exactly what the user gave; don't add narratives, URLs or members on your own.

## Quarter transitions / reviving a paused Trilovation

New quarter = **creating a new Trilovation**, not reviving the old one; the old one stays PAUSED as the closed record. The full procedure — funding gates, decision-log entries, milestone/revenue-item wiring, carrying the narrative over field by field — lives in `references/quarter-transitions.md`. Load it whenever a quarter ends or a paused Trilovation is revisited.

## Final gate

9. Nothing is "Settled" in the proposal until the actual counterparty (customer/investor/stakeholder) confirms it - an internal "yeah that sounds good" from the user approves drafting it, not finalizing it as settled fact in a shared doc.

## Doctrine references (from ticoons-libre-agents)

- `references/revenue-plan-doctrine.md` - the conceptual doctrine behind revenue items: the activity/capability/standing/fortune ladder (every item lives on rung 3), the five-question test, and the traps that look like good items. Load it when drafting or judging items, before calibrating against accepted plans.
- `references/red-flags.md` - what a red flag is, its purpose, and the attitude behind recording one. Load it before writing or resolving a red flag.
