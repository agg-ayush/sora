# Multi-lens parallel gap-analysis before finalizing a decision doc

## The technique

Before sharing/finalizing a decision doc (ITD, execution plan, design doc),
dispatch N parallel subagents, each auditing the SAME doc through a
DIFFERENT lens, rather than one generic "find issues" pass. Effective split
for an infra/product build doc: security (attacker mindset), operations
(what breaks in prod), candidate/user experience, engineering (what's
actually unbuilt), cost & compliance. Each task gets the doc path plus a
tight numbered list of the specific questions that lens should answer (10
questions per lens worked well) — the numbered list keeps the subagent from
wandering into a generic checklist and produces answers the orchestrator can
walk through 1:1 with the user afterward.

This is a stronger last-mile QA pass than a single "review this doc" agent:
each lens surfaces gaps the others don't (security won't think about
timezone handling; UX won't think about egress). Run them as a single
delegate_task batch (tasks: [...]) so they execute concurrently — five
20-150s subagent runs in parallel costs about as much wall-clock as the
slowest one.

## Pitfall: findings are proposals to negotiate, not a mandatory action list

The instinct after the batch returns is to treat every flagged gap as
something that must be fixed in the doc. It isn't. The subagents only know
what's in the doc — they don't have the full context of prior decisions,
what's actually being protected, or what's someone else's problem. In
practice, roughly half of the findings in one real run were beaten back by
the user with one-line context the subagent didn't have:

- *"why is this needed at all?"* — the flagged risk (ttyd auth) turned out
  to be substantially mitigated by a decision already made elsewhere in the
  doc (our own domain in front of the sandbox) that the security lens didn't
  cross-reference.
- *"candidate will exfiltrate what?"* — the flagged risk (no egress policy)
  assumed there was something sensitive to steal; there wasn't (no secret
  assignment questions, the repo/transcript are already ours).
- *"that will run outside the candidate's sandbox right"* — a flagged
  tampering risk was already handled by an existing decision (capture script
  runs via `sandbox.runCommand()` from outside), the subagent just didn't
  know operational detail from earlier in the doc/conversation.
- *"Is this compliance review in scope?"* — assess the real data flow,
  applicable jurisdictions, contracts, and assigned owner before declaring a
  privacy/compliance issue in or out of scope. Deployment geography alone
  does not settle it.

So the correct sequence is: **present findings grouped by lens, walk them
one at a time (or let the user fire rapid-fire responses per item), and for
each one either (a) explain why it's already mitigated by an existing
decision — cite the specific decision, (b) accept it and write the
resolution into the doc, or (c) mark it accepted-risk / out-of-scope with a
one-line reason.** Don't pre-filter what you show the user assuming you know
which ones matter — surface all of them, since a "trivial" gap to the agent
(e.g. timezone handling) may be exactly the one the user wants explicitly
recorded as "not needed" rather than silently dropped.

## Handling terse rapid-fire user responses to a finding list

When the user responds to a numbered finding list with equally short,
numbered answers ("1. no wait, i dont wanna skip this" / "2. i dont even
know what X means" / "3. yes"), two different response types are being
mixed and need to be told apart before you act:

1. **A real decision** ("yes", "their fault", "so what? update it") — write
   this straight into the doc as a resolution.
2. **A request to explain a concept or re-derive the reasoning** ("why is
   this needed at all?", "what would they exfiltrate?", "i dont even know
   what X means") — this is not consent to close the item. Answer the
   question first, grounded in the *specific* facts already established
   earlier in this conversation/doc (not generic security-101 explanations)
   — then let the user's follow-up settle whether it's needed. Closing the
   item on the strength of your own explanation, without the user's next
   response, repeats the premature-closure mistake (see
   `premature-closure-in-decision-conversations.md`).

After a full round of resolutions lands, write all of them into the tracker
doc in one batch update (per `decision-record-tracker-mechanics.md` /
gog-cli's "write decisions as they're settled" rule) — don't leave verbal
resolutions unwritten while moving to the next topic.
