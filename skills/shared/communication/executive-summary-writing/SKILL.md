---
name: executive-summary-writing
description: "Write/audit stakeholder docs & decks; elicit personal content."
version: 1.0.0
author: Hermes Agent
license: MIT
category: communication
metadata:
  hermes:
    tags: [communication, stakeholder-docs, exec-summary, alignment-doc]
---

# Executive/Stakeholder Summary Writing

For short alignment docs shared with a specific named person (not a generic
public audience) — e.g. "write up the plan so we're all on the same page"
requests from a VP/exec.

## Core principle: match the doc to the ACTUAL reader, not a hypothetical stranger

The single biggest failure mode here is writing (or auditing) for a
"zero-context reader" persona instead of the real, specific person who will
read it. A named stakeholder usually already knows:
- The project exists and roughly what it's for
- Common tool/product names used in your org (don't define "Vercel", "Claude
  Code", acronyms like the project codename, etc. unless the user says the
  reader genuinely doesn't know them)
- Who's building it (don't add an "ownership" section unless asked)

Before writing, or before dispatching an audit subagent, ask (or infer from
context) what the specific reader already knows. If unsure, default to LESS
explaining, not more — the user will tell you if something needs unpacking.
Over-explaining draws sharp correction ("bro we don't need to define X, this
is for [person]").

## When auditing with a subagent

Never tell the auditor "review as if a VP with zero context." That persona
produces a flood of "define this acronym / explain this tool / add an
executive summary / add ownership / add timeline / add success metrics"
findings that don't match what the real reader needs. Instead:
- Name the actual reader and state explicitly what they already know
  ("infra lead has been in the technical discussions, don't re-explain tool
  names or architecture terms he's already seen")
- Ask only for the specific failure modes you care about (self-contained
  claims, correct ordering, no leftover internal-only framing) rather than a
  generic "ruthless zero-context" pass
- Treat the audit output as candidate findings to filter, not a checklist to
  apply wholesale — walk them past the user one by one if there are several,
  don't bulk-apply everything an auditor flagged

## Two audit modes: fact-check vs completeness-check — pick the right one before dispatching

An adversarial audit of a stakeholder doc can mean two different things, and
the doc's own content tells you which applies:

- **Fact-check against the code** — for a doc asserting "today the system
  does/doesn't X" (see the "Today X" rule below), the audit's job is
  verifying each claim against the actual code, file:line.
- **Completeness-check against the plan** — for a doc describing what will
  be BUILT or CHANGED (a "what changes" / decisions / scope doc), the
  audit's job is checking whether the doc fully and accurately covers the
  build surface and scope — not grepping the live repo for contradictions.
  Ground this audit in the plan/build scope the team actually agreed to,
  not the current state of the codebase.

Tell the auditor explicitly which mode applies. A fact-check framing
dispatched against a forward-looking build/decisions doc produces
irrelevant "the code doesn't do this yet" findings — that's the doc's whole
point, it's describing what isn't true yet, on purpose.

## Section ordering (default, confirm with user if they push back)

1. **What we're building** — the solution/deliverable itself. Not a
   "problem statement" framed as "why we need this" — most stakeholders
   already know the problem; they want the plan.
2. **What the [end user/candidate] sees** — the step-by-step experience,
   only if the reader explicitly asked for this angle.
3. **Definition of done** — customer/reader-facing outcomes only, not
   internal technical artifacts (e.g. "we have the recording + transcript
   to grade the candidate", not "transcript + code tarball uploaded to
   Drive").
4. **Hard problems** — problems only, stated as questions/challenges. Do
   NOT list the solution or internal codenames/vendor names in this
   section — those belong in Decisions. A "hard problem" should be
   something a smart outsider immediately recognizes as hard; if the
   obvious answer is "well just use $COMMON_TOOL", it's not a hard problem,
   cut it.
5. **Main decisions** — the actual technical/process choices made, each as
   one bullet: what it is + how it works + main trade-off. No separate
   "options considered and rejected" subsections unless the reader asked
   for that level of rigor (see 1-3-1 skill for when they do).
   - Run every candidate decision bullet through the five filters (real
     fork between materially different outcomes; this team made the call;
     not the obvious/only-sane implementation or a hardening add-on; the
     reader doesn't already own the subsystem; ownership verified —
     "pre-existing" built by your own team is still yours) condensed in
     `references/workflow-rules.md` under "Decision filters". A first pass
     that mixes in consequences, mechanisms or handed-down boundaries
     needs a second pass to strip them out. Genuine design choices within
     a decision we own (queueing, idempotency, safe defaults) still count
     as decisions even when they look like implementation detail.
6. **Cost / scale** — merge if both are short. Don't restate internal
   discussion framing (competitor pricing, volume caps, sales-call
   friction) that the reader never saw — state the final number/limit
   plainly.
7. **v2 / future scope** — bullet list, no elaboration.
8. **What we need (asks)** — LAST, not first, unless the user explicitly
   asks for the asks to be front-loaded. Don't assume "the reader's job is
   to unblock things" — confirm before reordering for that reason.

## Conciseness: cut "today X, becomes Y" scaffolding from high-level bullets

When the user says a doc is "too verbose" even after a first trim, the
remaining fat is usually narrative scaffolding around each bullet, not the
bullets themselves — phrasing like "Today the system does X. Next time it
will do Y instead" doubles the sentence count per item. State only the
change itself as a short declarative sentence or two ("Scheduling is
automatic: HR adds candidates to a sheet; the system schedules and
invites.") and drop the before/after narration entirely — the reader
infers "today" from context. If the user has to point out the same "too
verbose" complaint twice, the fix on the second pass is removing this kind
of scaffolding, not just shortening sentences further.

## Scope: don't detail a part owned by someone else

When a "what changes" or status doc covers one team's slice of a larger
system and a change depends on another team's component (e.g. their new
environment, their new API), give it a brief one-clause mention as a
dependency — not a description of how their part works internally. Detail
belongs only in the sections describing the writer's own team's changes.
Caught directly: writing several bullets of implementation detail about
another engineer's IDE/environment component in a doc meant to describe
"our part" — the fix was cutting it to "a link to the candidate's
environment, provided by the orchestrator" and moving all real estate to
what the writer's own team's app actually does (e.g. gating that link
behind a guided verification flow).

## When told "you missed something we discussed": re-pull the actual meeting notes, don't rely on memory

If the user says the write-up is missing context from a discussion (a
meeting, a feedback session), don't try to reconstruct it from the current
conversation's own compacted history — go find and read the actual
meeting-notes doc (e.g. a Gemini notes doc, a feedback-session doc) via
`gog docs cat` and ground the missing points in it directly. The
conversation history you have may already be a lossy summary of that
meeting; the notes doc is the primary source.

## Two-tier structure when the doc is "what changes / what's new"

For a "summarize what changes for the next [cycle/drive/release]" doc,
default to two tiers, not one flat list:

1. **High level** — capability-level changes a reader would actually care
   about, each as: what it was, what it becomes, one line on why. This is
   the whole point of the doc; everything else is supporting detail.
2. **Lower-level detail** — the smaller behavioral changes, edge-case
   handling, and decisions that matter for completeness but that nobody
   reads the doc specifically to find. Keep these as short flat bullets
   under their own heading, below the high-level section.

Don't blend the two into one ordered list — the reader should be able to
stop after tier 1 and have the real picture.

## Pitfall: recency bias drops the biggest changes from a long conversation

When the doc synthesizes a long multi-topic conversation (many decisions
made across many turns), the headline list is prone to reflecting whatever
was discussed most recently or most extensively in-session, not what's
actually highest-impact. A structural/architectural change discussed early
and then settled (e.g. an API gaining new capabilities, a manual process
becoming automated) is easy to drop entirely in favor of whatever was being
litigated in the last few turns (e.g. UI/UX polish). Before finalizing a
"what changed" list, re-scan the FULL decision trail (all doc tabs/sections
written this session, not just the most recent one) and explicitly ask: of
all settled decisions, which ones are structural/capability-level — those
go in tier 1 regardless of how much airtime they got at the end of the
conversation. Caught directly: "you haven't mentioned the biggest things,
the automation and the api changes" — both had been fully designed and
locked earlier in the same conversation but never made it into the summary
because the last hour of discussion had moved on to UI details.

## Answering a stakeholder's multi-part question set

When a stakeholder asks several distinct questions (Q1, Q2, ...) and the user
wants to discuss/draft them one at a time: answer ONLY the question in scope
and stop there — do not draft or even summarize a later question's answer
while still on the current one, even as scene-setting or "context for later".
if your answer to Q1 starts pulling in material that's really the answer to
Q2, that's a sign you've drifted — cut it and wait for the user to move you
to Q2 explicitly.

## Drafting a chat reply to a stakeholder ("what do I say to X")

When the user pastes a stakeholder's message and wants a reply, the
deliverable is the reply text itself, ready to paste.

1. Answer the stakeholder's actual objection in 2-4 plain sentences inside a
   quote block. No preamble and no internal jargon (task IDs, PR numbers,
   env flags). Put any note to the user after the draft, in one line.
2. Before citing a concrete mechanism as the justification (a race, a
   feature, a failure mode), check it is in the **current release's scope**.
   If the example comes from a deferred or legacy path, the reader will
   catch the mismatch and the reply loses credibility. Justify with what is
   actually shipping. If no in-scope example exists, state the general
   principle instead.
3. When the stakeholder pushes back on a claim (for example "that should be
   impossible by design, why test it"), concede what the design guarantees.
   Then say what the test adds: it checks that the implementation actually
   enforces the guarantee. Don't argue that the design is weak.
4. If an earlier message overstated or misattributed something (for example
   "the agents were slow" when the real bottleneck was test runs), correct
   it in one clause in the reply. Don't defend the original wording.
5. If you find a scope or code problem while drafting, finish and deliver
   the reply first. Offer the side issue in one line afterward. Don't open
   kanban comments, code reads or task changes in the middle of a reply
   request. The user will cut that off ("ignore that, just give me the
   answer"), and the reply sits undelivered in the meantime.

## Drafting an outbound ask/intro message to a stakeholder

For "draft a message to X saying I'm taking up Y and need Z" requests:

1. **Match the register of the channel it will be sent in.** Ask which space or DM it goes to, read that space's recent messages (`gog chat messages list spaces/<ID> --order "createTime desc"`), and copy how people there write work updates and asks. If the space can't be found, ask for its link before falling back to a generic style.
2. **Calibrate what the reader knows, per fact, before drafting.** A reader who knows the project still needs the specific what-it-does and why (the user-facing benefit). A meeting they weren't in is mentioned by who attended and what it covered ("investor and I met X and Y and covered the specifics of their flow"), never assumed known and never described as just "I".
3. **Make the ask the reader's action, and name the exact resource.** Write "help us get access to <org>'s <tool> plan, at staging level", not "help figure out how to enable it". Delegating the diagnosis reads as offloading work; asking for the specific grant is what the sender needs.
4. Order: what you're taking up and what it does, the context touchpoint, what you're building now, then the one ask, with any self-serve route you already tried and where it failed.
5. Apply each correction as a minimal edit to the last draft and re-show the full text. When the user pastes their own edited final, review it as-is and say "send it" if it's sound; don't re-draft it.
6. **Write for everyone in the thread, not just the addressee.** In a group thread with a third party (e.g. an account admin looped in by the addressee), drop internal meeting references, dates and who-met-whom; they don't concern the other readers. State the substance (the concrete pain points, what the tooling does about each) as plain facts.
7. **HARD RULE: include only what the recipient needs to act — nothing else, from the first draft.** Name the artifact and its parameters ("an access token with X, Y, Z permissions"; "the service user email: X, display name: Y"). Cut every detail of how you set something up or verified it ("it's a Google group", "receives external mail - verified", "the email lands in the group"), how you'll handle your side, and how to produce something the reader already knows how to produce. Don't spell out expected professional ground rules, and never ask for more access than the task needs (a token, not account credentials). Test each clause: if deleting it doesn't change what the recipient does, delete it before showing the draft. The user treats a padded first draft as a repeat failure, not an iteration step.
7i. **HARD RULE: no internal lingo in external asks.** Our tool internals, product codenames and mechanism history stay out. Exception: a term the recipient works with in their own role is fine (an account admin knows Adobe's `x-api-user` header and scope levels). State consequences as neutral facts about the system ("any calls will be recorded under sign-sure only"), never phrased around the user's own concern ("nothing is recorded under your name").
7k. **Options-ask format the user prefers:** open with the fact, quoting the exact error text; no warm-up line. Then "These are the possible options:" as a flat numbered list, one line each, with "Recommended -" marked inline on the pick. State each option at its real requirement ("grant admin"), never softened ("minimum rights needed") when the minimum is admin. The recipient doesn't know what failed after their change, so say it failed and give the error; don't recap the rest of the history.
7j. **Don't re-tell the recipient context they already have.** A "consolidated ask" folds every OPEN item and option into one message; it does not recap history the recipient lived through (what they configured, earlier steps they did). Do tell them anything they can't know, such as that the step after their last change failed and with what exact error. Start from where their knowledge ends.
7f. **External-facing names use what the counterparty recognizes.** For a sender/display name seen by customers or vendors, prefer the org + function ("Trilogy Legal") over internal product or process names ("Legal Intake - Sign Sure"); internal names can still label the group or admin-side identity.
7b. **Don't ask a stakeholder for something you haven't verified you can't do.** Before a draft asks them to clean up, fix or provision something, try it with the access you have. Keep the ask only if the attempt fails, and say why in one clause ("needs an admin, my token can't").
7c. **Accept a plan the stakeholder already stated; don't relitigate it.** If they said they'll rotate creds after the PoC, write "you can rotate now as planned" plus what you'll need next, not a reason they shouldn't.
7g. **Name exact identifiers and label each claim's certainty.** When an ask concerns specific resources (AWS accounts, repos, apps), give the name plus ID, never "the old accounts". For each claim say whether it is confirmed and from where in one clause ("confirmed from the role and table ARNs in the code") or unverified ("looks like X but I could not verify"), so the recipient knows which part to correct.
7h. **When reviewing the user's own rewrite, check facts and dropped asks.** Flag wording that changes a fact ("contained" for something still live) and any ask from the earlier draft that silently disappeared; let the user decide whether the drop was deliberate.
7d. **Every fact in an outbound message needs a source the reader would accept.** Before including a date or status about a third party ("back Wednesday"), check where it came from. If it only came from the user's paraphrase or your inference, drop it or flag it; the recipient may know the real answer and a wrong one costs credibility.
7e. **Status updates to non-technical or external stakeholders are outcome-only.** State what is done and what's next in plain terms. Leave out internal milestones (for people outside the team), technical findings, fixes and the mechanics of the loop. Those stay with the team.
7a. **Acknowledgment replies stay one line.** When the stakeholder hands something over (credentials, a doc, access), thank them and state when you start. Don't echo back what they sent or restate their caveats.
8. **In a group thread, put each question to the person who owns the answer.** Don't route a question through the addressee when the third party in the thread is the one who decides it; address them directly, question first, then the specifics they need.
9. **Check that a scope clarification can't undercut the ask.** Before adding "we're not taking over X", ask whether a reader could take it to mean the requested change isn't needed. Pair it with why the ask is still required ("the admins keep running the workflow; the account move is needed because our tooling can only drive sends from an account we have API access to"). Make the scope concrete as a numbered list of the slow points removed, plus a trust-first line ("admins stay in the loop and can override; once they trust it, it can run automated").

## Explaining a thread the user wasn't part of

When the user says they lack context, first pin down WHICH part: what they drafted and sent themselves is already known to them. Explain only the exchange between the other parties: who each person is and why they were looped in, what each message proposes in plain terms (define jargon like service user, M&A, redlining inline), what the last message implies for timing, and what if anything the user needs to do. Don't recap the whole project history; the user will cut it off.

## "Decisions + confidence" tabs: three separate categories, don't blend them

When a doc/tab covers decisions made plus a confidence read ("are we
ready"), keep three distinct buckets and don't let one bleed into another:

1. **Decisions** — the judgment calls actually made (see the decision
   filters above).
2. **Pending** — a decision that is NOT yet made because it's blocked on
   something (usually another team's call landing first, e.g. "we can only
   mock up the candidate tutorial once part 3's environment decision
   lands"). This is not a confidence caveat and not a decision — it's its
   own short section, placed BEFORE confidence, not folded inside it.
3. **Confidence** — a short read on how ready/safe the plan is, one line
   per component (e.g. "our part - HIGH, mostly re-pointing existing
   pieces" / "overall system - MEDIUM, the sensitive part is the other
   team's component"). Confidence is an assessment, not a place to restate
   a decision, a dependency, or an ownership clarification already covered
   elsewhere — if a clause doesn't change the reader's sense of risk, cut
   it. Caught directly: a confidence line naming "our only dependency is
   field X on the session record" got cut with "what does this even bring
   to the table? stop mentioning irrelevant shit" — the dependency detail
   didn't inform the risk read, it was just more information for its own
   sake.

When the user says something "needs to be a pending decision, not inside
confidence," that's a category-placement correction, not a wording one —
move the whole clause into its own "Pending" heading rather than trying to
phrase it more carefully within the confidence bullet.

## Cross-check the whole doc after applying a batch of individually-approved fixes

When the user approves a numbered list of wording fixes one at a time ("1. okay do it 2. drop it 3. ..."), applying each fix in isolation can leave it contradicting a *different* bullet elsewhere in the same doc that restates the same underlying fact. Concretely: fixing bullet #1 to say the lookup-by-email endpoint already exists (just gets richer) left a separate detail-section bullet still asserting "today only create and list exist" — the same fact stated twice, only one of the two got corrected. Same pattern with an unproctored-session flag: fixing the top-line claim left a lower bullet still asserting the old (contradicting) claim. After applying an approved batch of fixes, grep the finished doc for every other place the same fact/claim is restated (a name, an endpoint, a flag, a behavior) and reconcile all of them — don't treat "applied fix #N" as done until you've checked the doc has no other sentence still stating the pre-fix version.

## Never push an audit fix to the stakeholder-facing doc without confirming first

Running an adversarial/completeness audit on a stakeholder-facing doc and then
directly applying the fixes it surfaces is a scope violation, even when the
filtering step (see "Two audit modes" above) already cut the findings down to
genuine casualties. The audit produces *candidates for the user to approve*,
not authorization to edit the doc the stakeholder will read. Concretely: after
filtering an audit to real gaps, list them to the user (claim, why it's wrong/
incomplete, the proposed fix) and stop — do not write any of them into the
infra lead-facing tab first and explain afterward. If edits already went in before
this was flagged, revert the stakeholder-facing doc/tab to exactly the content
the user last approved (not a best-guess reconstruction — keep the last
approved full text on hand, e.g. in a scratch file, specifically so a revert
is an exact write-back, not a memory-based rebuild) and hold every proposed
change for explicit line-by-line sign-off before touching that doc again.

This gate applies only to the stakeholder-facing doc itself — an internal
working/decisions doc (the one only the team reads) has no such gate; keep
iterating on it freely once the user has said as much ("do anything you want
in the internal doc").

## Retro / "why did this take so long" reports

When writing up a delivery retro, especially one answering a criticism:

1. Frame it as a reflection report on why it took long, not a defense or rebuttal. No "the claim / our response" structure, and never name or attribute the position to the person who holds it (they may not have voiced it yet). Answer their concerns as neutral questions ("Were tasks too large?") answered from the record.
2. Open with the title then a TLDR (one-sentence bullets carrying the key numbers). No meta paragraph about what the doc is or who it is for.
3. Write external-facing: give the minimum context first (what was built, how the agent workflow works), then explain every internal term inline the first time (disk type and its limit, "cards", "workers", action budgets). Never drop a bare internal event like "model change" or "gp3" without saying what it means.
4. Keep it concise: TLDR, short context, the causes, concerns answered, a timeline table, what we would do differently, one line pointing to the per-item detail "available on request". Deep per-card tables stay out of the doc.
5. Ground every claim in timestamped records (run start/end, event logs), and concede the team's own contributions; never build the narrative on assumptions about people (e.g. who was asleep or absent).

## Iteration pitfalls seen in practice

- **A summary/decision doc must be self-contained — no references to "the
  plan," "as discussed," "the earlier approach," or any other artifact the
  reader may not have seen.** State the constraint and the resolution
  directly rather than contrasting against an unstated prior belief. Grep
  the finished doc for backward-looking phrases ("as before," "still," "now
  works," "the plan," "previously," "we said") and rewrite each into a
  plain, direct statement.
- **Default format for prose-heavy sections is headings + short bullet
  lists, not paragraphs.**
- **Don't reintroduce cut content across rewrites.** A decision made live
  (in a meeting) and not in any other doc needs a one-line "why" preserved
  even in the shortest version — ask which decisions came from a meeting vs.
  written discussion before cutting "how it works" detail.
- **A full-doc `write_file` + tab rewrite can wipe a previously-added tab
  on the same Google Doc.** Always target `--tab <name>` explicitly and
  verify the tab still exists after a full doc rewrite.
- When the user says "shorten it" repeatedly, each pass should cut
  redundant framing/restated context, not information content.

Most of the workflow rules above (reader matching, audit modes, decision
filters, section ordering, hard gates) are also condensed in
`references/workflow-rules.md` for quick lookup.

## Eliciting personal/narrative deliverables section-by-section

For deliverables whose content is personal opinion, reflection or
first-person narrative (retro decks, personal workflow write-ups, opinion
pieces), gather content section by section instead of batch-drafting a full
pass — batch-drafting means guessing most sections wrong, and feedback on a
full draft is diffuse instead of sharp.

1. **Separate structure from content.** Confirm the section skeleton once
   (from a reference deck, template or explicit ask); format/layout choices
   are cheap to change and can be settled in one pass.
2. **Go section by section for content.** Ask what the user wants to say,
   let them answer in their own words, confirm, then move on. Never pre-fill
   a section with a guessed draft — ask first, draft second. Batch-draft the
   whole deliverable only after every section has real user content.
3. **If the user asks for all questions at once**, collapse to one
   consolidated list grouped by section, but still process answers section
   by section if they choose to pace it that way.
4. **A matched template tells you the shape of each section, not what THIS
   user did or believes** — structure inference from examples is fine;
   content inference is not.
5. **Reading batches of reference .pptx decks:** `python -m markitdown`
   often silently extracts nothing (the pptx extra isn't always installed);
   fall back to `scripts/dump_pptx.py` (python-pptx), which prints shape
   text, tables and speaker notes per slide. Diff the decks against each
   other — the shared skeleton (slide count, section banners, pacing) is the
   actual template being used.
6. **Build each slide from the user's own architecture, never a peer's
   framing**, even when a peer deck is structurally adjacent; point out the
   contrast instead of adapting their language. Flag any specific factual
   claim about the user's systems back for confirmation before it goes on
   stage — these decks are presented live, and an unconfirmed claim is the
   user's problem, not yours.
