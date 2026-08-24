# Tool evaluation notes (vetted against a kanban-based tier-orchestration architecture)

Context: the architecture being evaluated against is a stateless-dispatcher
Tier-1 (per repo) + Tier-2 (per issue, design+implementation supervisor) system,
coordinated via Hermes-native kanban, driving Claude Code/Codex CLI sessions in
tmux, with a native web dashboard.

## beads (github.com/gastownhall/beads)

What it is: a distributed graph issue tracker built for AI agents — persistent,
structured issue/dependency graph, meant to survive across agent sessions/context
resets.

Verdict: not adopted. Our kanban backend already provides the durable
task/dependency/state layer (link/unlink for dependency graphs, attachments for
design docs, claim locks with TTL, review status). Beads' core value
proposition (a durable, structured task graph across agent runs) is something
we already have natively. No concrete gap identified that beads closes.

## amux (github.com/mixpeek/amux, formerly cmux/cc)

What it is: a layer over Claude Code/Codex/Gemini — spawns and manages those
same CLIs inside tmux, with a phone-accessible web dashboard (own port, own
control plane) and a self-healing watchdog that detects specific CLI failure
modes (context compaction, a "redact" hang pattern, wedged sessions) and
auto-responds instead of just killing.

Verdict: NOT a replacement for the tier system (same underlying CLIs, but a
totally separate, incompatible worker/state model — see below). Two things
were considered for borrowing:

1. **Self-healing watchdog pattern — adopted.** Ported the failure-mode
   detection + auto-respond behavior into our own orphan-reaper script (upgrade
   from kill-only to detect-and-heal specific patterns before killing). This
   was the genuinely valuable piece.
2. **Phone dashboard — evaluated, NOT usable for our sessions.** Initially
   documented (wrongly, without testing) as "a mobile view over the same tmux
   sessions our tier system spawns." When actually installed and run: amux's
   dashboard only shows workers it spawned ITSELF — it has no mechanism to
   discover or adopt pre-existing arbitrary tmux sessions (like our T1-spawned
   T2 sessions). To use it as a dashboard for tier work you'd have to register
   tier sessions as amux workers, which would hand ownership of session
   lifecycle to a second orchestration layer that would then conflict with our
   own (T1 spawning T2s, T2 self-terminating, our reaper healing). Concluded:
   don't use amux for mobile monitoring of the tier system; our Telegram
   notifications (`kanban notify-subscribe` + `hermes send`) are the mobile
   channel instead.

Lesson generalized into the main SKILL.md: verify a tool's claimed
compatibility with your own live system by actually running it against real
data, before writing the claim into a doc as fact.

## beads, re-evaluated for a different architecture (lesson-qc-auto-checker)

Second, independent evaluation — this time not against the tier-orchestration
kanban but against `components/lesson-qc-auto-checker/`, a pipeline of ~12
LLM-judge agents (coordinator.py fans out language/visual/pedagogy/etc. agents,
each running one multi-check prompt per call). The proposed use was narrower
and sharper than the first eval: enforce that every issue/check gets an
explicit per-item judgment (a "checkmark every issue" pattern), because
multi-check-in-one-prompt is exactly what causes verdicts to flip between
runs — the model diffuses attention across bundled checks instead of judging
each on its own merits.

Verdict: still not adopted, for a *different* reason than the tier-system
case. Beads (or any task-graph tracker) can guarantee every check gets a
closable row in a queue; it cannot guarantee the LLM actually judged that
check well when closing it. An agent that bundles 5 checks into one sloppy
pass and then closes all 5 beads is fully "compliant" and just as flaky as
before — the noise lives in the judgment step, which is downstream of
whatever tracks task state. Completeness-of-bookkeeping and quality-of-judgment
are different axes; beads only addresses the first.

Constraint that shaped the alternative: true per-check LLM calls (one call per
check id) DO fix the diffusion problem, but the user explicitly ruled this out
on cost/rate-limit grounds ("we barely care about cost — we will surely hit
rate limits") for a ~12-agent x multi-check x per-slide fan-out. So the
recommended design had to get most of the per-check isolation benefit without
multiplying call count:

1. Schema-enforced coverage: diff returned check-verdict keys against the
   expected set; missing/vague verdicts trigger a small targeted re-prompt for
   just those checks, not a full re-run. Zero extra cost in the happy path.
2. Serial per-check verdict structure inside the SAME single prompt/call
   ("for each check below, state verdict + evidence, then move to the next")
   instead of one blended JSON blob — cheapest lever, most of the
   attention-diffusion fix, no added latency.
3. Issue fingerprinting — `(check_id, slide_id, evidence-hash)` — to make
   run-to-run verdict flips measurable, then selective vote@k (re-judge only
   checks with an observed historical flip rate) rather than voting on
   everything. This was the one piece of the original pitch the user
   endorsed outright.
- Explicitly rejected as a recommendation base: citing the repo's own existing
  `_stabilize_verdict` majority-of-3 pattern (`dataset/golden_eval/scorer.py`)
  as reusable precedent. User's correction: "forget stabilize verdict, just
  cause anything is in this repo doesnt mean it works; it has a lot of bad
  code." Generalized into the main SKILL.md pitfalls.
