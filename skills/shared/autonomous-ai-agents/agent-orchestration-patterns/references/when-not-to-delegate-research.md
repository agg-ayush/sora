# Don't dispatch a research subagent for a question you can just answer

Recurring failure mode: after a round of subagent research has already landed
real findings, the user asks a follow-up that is actually a **comprehension /
explainer question** ("what is Firecracker", "what's the gotcha with X",
"why is A better than B except for cost") — and the reflex is to dispatch
more `delegate_task` researchers instead of just explaining it.

Concrete correction from a live session: after dispatching subagents for a
sandbox-provider comparison, the user asked "what even is firecracker, whats
the point / whats the gotcha with e2b / why is it better than vercel". Two
more researchers got dispatched. The user's response: **"i dont think those
questions need researchers? you can help me help me understand those?"**
Both questions were fully answerable directly — Firecracker/gVisor/Docker
isolation is stable, well-known technical background, and the E2B-vs-Vercel
tradeoff was already sitting in the just-returned research findings; it only
needed to be explained in plain language, not re-researched.

## The distinction

- **Needs a subagent:** genuinely new external facts not yet gathered —
  current pricing, a vendor's specific architecture claims, maturity/adoption
  evidence, anything that requires fetching and quoting a live source.
- **Doesn't need a subagent — just answer:** explaining a concept
  (Firecracker vs Docker vs a full VM), synthesizing/interpreting findings
  already returned by a prior research round, or answering "why does this
  matter" / "walk me through the tradeoff" once the underlying facts are
  already in hand. The orchestrator has full context (own knowledge + the
  research that already ran) and should use it instead of manufacturing a
  reason to spin up another background task.

## Rule of thumb before calling delegate_task for a "help me understand" ask

Ask: is this question asking for information I don't have and can't reason
out from what's already been gathered? If the honest answer is "I already
have or can derive this," answer directly in the reply — don't dispatch.
For a current or unverified external fact, retrieve a primary source with an
appropriate tool even when no subagent is needed. Delegate only if the new
research is genuinely independent, large, or benefits from parallel reasoning;
explain already-gathered findings directly without pretending memory is
verification.
