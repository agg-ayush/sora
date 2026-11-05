## Writing a batch-incident RCA / issue tracker for a stakeholder

When a stakeholder (e.g. a VP) asks for a post-batch RCA and issue list, or
you're consolidating candidate-reported issues into a stakeholder-facing
doc:

- **If a peer team already published an RCA for their half of the same
  batch (e.g. the interview/VVA side when you own the technical/ADD side),
  read it first and mirror its structure** — run-in-numbers table, then
  three tables (what people reported / what you personally observed /
  anticipated-and-known issues) each with columns `issue | disposition
  (fixed and deployed / will fix / won't fix) | why`, then a numbered RCA
  subsection per major issue with scale, root cause, evidence, and fix, and
  a closing "what I would not run another batch without" list. This is the
  bar the stakeholder is already calibrated to; matching it reads as rigor,
  reinventing a different structure reads as not having checked.
- **State the disposition as one of exactly three values** — fixed and
  deployed / will fix / won't fix — and always pair "won't fix" with the
  actual reason (deliberate tradeoff, not our infra, not a real issue), not
  a bare dismissal.
- **Every RCA claim needs a number behind it**, not a description — scale
  (how many sessions/candidates), the relevant limit/threshold vs what was
  actually placed on it, and what the logs/evidence show. "We hit rate
  limits" is not an RCA; "live limit was 22M TPM, batch drew ~24.5M TPM at
  peak concurrency" is.
- **Attribute a fix to the change that actually caused the effect, not the
  change that was adjacent to it in the same PR/timeframe.** A safety gate
  getting "pinned" doesn't fix a symptom if a *different* change in the same
  window (e.g. disabling the gate's permission-prompt path entirely) is what
  actually removed the blocking behavior — crediting the wrong change reads
  fine until someone who knows the mechanism spots it, and it's the kind of
  error that undermines the whole RCA's credibility. Trace each claimed fix
  to the specific commit/PR that changed the actual failing code path before
  writing it into a stakeholder-facing table, don't infer from "these PRs
  landed around when the symptom stopped."
- **If two systems both report the same symptom (e.g. "rate limit") with
  opposite ground truth (one team's investigation found no rate limit was
  ever hit, yours found a real one), say so explicitly in your own RCA** —
  name that they're different vendors/infra so the two docs don't read as
  contradicting each other to a reader who sees both.
- **When a fix row says a control was "upgraded" from passive detection to
  active enforcement (e.g. a violation used to only be logged/counted
  toward a strike limit, now it terminates on its own), pull the exact
  pre-fix behavior from the actual PR body/diff, not a generic "wasn't
  strictly enforced" phrase.** The precise before-state changes the
  reading: "was already logged and counted toward the two-strike limit,
  now terminates immediately on its own" is a real upgrade; a vague
  "wasn't fully enforced" reads as if there was no detection at all
  before, which both undersells the prior state and overstates the gap
  the fix closed.
- Write it as a new tab in the existing shared triage doc (see gog-cli
  skill for `add-tab` + `write --tab ... --replace --markdown
  --check-orphans`), not a separate doc — keeps the whole issue picture in
  one place the stakeholder already has open.
- **An RCA's forward-looking recommendation (a ramp size, a rate-limit
  mitigation number, a batch cadence) goes stale the moment ops actually
  settles on a different number in practice** — e.g. the doc says "ramp
  with ~20/hour" from the spike, but the real operating decision later
  becomes "max 100 concurrent per batch." When a live ops decision
  supersedes a number already written into a published RCA, go fix that
  exact line (`gog docs find-replace --tab "<rca tab>" <docId> "<old
  number/sentence>" "<new decision>"` — see gog-cli skill) rather than
  leaving the doc showing the superseded figure. Don't touch the
  historical numbers describing what actually happened during the
  incident (e.g. "batch ramped to ~346 concurrent") — only the
  forward-looking recommendation line changes.
- **Never write a claim that overstates evidence you don't have — but also
  never claim you lack a capability you actually have.** Two distinct
  failure directions on the same axis: (1) don't assert a fix as the
  confirmed root cause of a reported symptom when it was really proactive
  hardening for a theoretical bug never confirmed to have hit that symptom
  — say "hardening, cause of the reported symptom not confirmed" instead of
  presenting a reproduced-in-a-sandbox bug as what the candidate actually
  hit; (2) don't write "we don't have X yet" / "needs further review" for
  something the org already has (e.g. session recordings from Recall) —
  that undersells capability to the stakeholder. If per-case attribution is
  pending, say "we're reviewing the recordings per case," not "we lack the
  data to tell."
- **Don't restate a row's own table membership inside its "why" text**
  (e.g. writing "anticipated bug we caught" inside a row that already lives
  in the "anticipated issues" table, or "candidate reported" inside a
  row already in the "what people said" table). It's redundant and reads
  as padding; the why field should only carry the causal explanation.
- **When merging two reported symptoms into one row because they look the
  same to the candidate (e.g. "can't type" and "connection lost" both
  presenting as an unresponsive terminal), state the fix in terms of what
  was actually shipped for the confirmed cause, not for every theoretical
  cause that could produce the same symptom.** If the confirmed fix was
  "extended the reconnect window," say that — don't also credit an
  unrelated hardening change (e.g. an agent-launch health check) unless
  that specific session type was mechanism-confirmed, not just plausible.
