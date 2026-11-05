# Don't declare a decision "settled" until the user actually closes it

Context: a live back-and-forth where you dispatch subagent research, synthesize
findings, and propose moving to the next open question in a decision/ITD doc.
Recurring failure mode: after one round of research lands a plausible answer,
the orchestrator says "X is settled" / "recording is settled" / "Vercel
Sandbox it is" and pivots to the next topic — while real caveats the user
cares about (cost tradeoffs, retention, export paths, isolation) were never
surfaced or confirmed.

Two concrete instances from one session:

1. **Declared "Recording is settled"** after one research round on Recall.ai
   (storage, concurrency, per-participant events, a cost recommendation for
   batching candidates into shared Meets). The user's correction: **"wait it
   is not settled ... there are so many caveats, dont jump into decisions."**
   Unaddressed at the time: individual-Meet vs shared-Meet cost tradeoff
   (batching saves ~$0.30 total but the user's budget wasn't tight — isolation
   mattered more), retention length, and whether recordings could be exported
   to the user's own S3/GCS bucket at all. All three were real open
   questions the orchestrator's own "recommendation" had quietly closed.

2. **Dispatched research under a stale requirement frame.** Research on the
   LLM-proxy/network-isolation question was dispatched assuming "block all
   traffic except the AI API" — but the actual constraint (surfaced earlier
   in the same conversation) was "open book test," i.e. the candidate's AI
   assistant needs full internet access; only credential theft and lateral
   access to internal infra are the hard constraints. The user caught it:
   **"i think the research was done with wrong requirement in mind right?"**
   The fix required re-dispatching research with the corrected frame instead
   of patching the synthesis of the wrong-framed results.

## Rule of thumb

- After synthesizing a research round, list the residual caveats/tradeoffs
  explicitly (cost, retention, export, isolation, scale — whatever is
  relevant to the decision) as a short bullet list *before* declaring the
  topic closed. Let the user close it out; don't close it for them just
  because one plausible answer came back.
- Before dispatching a subagent for a security/compliance/architecture
  tradeoff, restate the actual hard requirement in the exact terms the user
  gave earlier in the conversation and make sure the research brief reflects
  it — requirements drift across a long conversation, and a subagent brief
  written from stale context produces well-cited but off-target research
  that has to be redone.
- "The user said 'sure' / 'good, works with us' to a specific recommendation"
  is a real close — that's different from the orchestrator unilaterally
  saying "settled" and moving on. Only the former ends the topic.

## Adjacent: avoid unexplained jargon in live explanations, not just report text

Same conversational mode surfaced a second, related correction: when
explaining a technical tradeoff directly to the user in chat (not a
compressed report one-liner — see
`hiring-eval-report-generation.md` for that variant), dense
term-dropping ("SNI", "egress", "CA", "credential brokering") drew: **"lets
use simpler language please."** Explain the mechanism in plain terms first;
introduce a technical term only alongside a one-clause explanation of what it
means, even in fast back-and-forth exchanges where terse feels efficient.
