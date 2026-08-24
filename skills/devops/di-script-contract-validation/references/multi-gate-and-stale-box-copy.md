# Two recurring causes of "still failing after the repair" in this pipeline

Both of these caused repeated (4-5x) redrive cycles on an 84-script batch in
one session. Check both before writing a new bug report or looping into
another repair pass.

## 1. The pipeline enforces multiple independent gates — passing one does not mean the script ships

This repo's live pipeline chains at least two structurally different checks
on the same script, and a repair that satisfies one can still fail the
other:

1. **Format/shape gate** (ingest structural rules) — e.g. a staged block
   (`[v1.1]`, `[v1.2]`...) must not also have a bare marker of the same base
   id (`[v1]`) in the same slide; `vN states K stage(s)` must match how many
   distinct markers the narration actually carries.
2. **Resolvability gate** (voiceover timing) — every declared element needs
   a marker that resolves to a *unique, non-empty* `trigger_phrase`/
   `trigger_word` per the word→sentence→uniqueness algorithm (see main
   SKILL.md "How the parser resolves a marker").

A script can pass gate 1 and still fail gate 2 (or vice versa) — they check
different things on the same marker set. In one batch, a "uniqueness" repair
pass validated only against gate 1's parser, requeued 84 scripts, and they
failed again on gate 2's `missing trigger_phrase` error — a regression back
to the *original* symptom the batch was supposed to have already fixed.

**Before dispatching any repair batch:** identify every gate the live
pipeline stage actually enforces (grep the stage's source for every
validator/parser it calls, not just the first one you find failing in the
log), and validate a known-failing + a known-passing script against ALL of
them. Only report a script "fixed" once it clears every gate — not just the
one whose error message you last saw.

## 2. A live "still failing" can mean the box's local copy is stale, not that the script is still broken

The pipeline runs against whatever `script.md` copy currently sits in the
worker box's batch working directory (e.g. `batch-g3-rerun`) — not against
Drive directly. That local copy is a **snapshot from whenever it was last
pulled**, and after several repair rounds it is very easy to re-queue a
batch whose box-side files are one or more repair-rounds behind the current
Drive content. Symptom: the exact same failure message reappears after a
"fix", even though the Drive copy is provably correct when re-checked
directly.

Before concluding a redrive genuinely still fails:

1. Pull the box's *current* copy of the specific failing lesson and diff it
   byte-for-byte against the current Drive copy. If they differ, the box is
   stale — re-sync the whole batch folder from Drive (not just the one
   lesson) and redrive before doing any further diagnosis.
2. Only treat a failure as real once you've confirmed the box's copy matches
   Drive's current copy at the moment of the failing run.
3. When reproducing a gate offline to sanity-check a fix instead of waiting
   on a live box run, make sure the offline check reads the **same exact
   bytes** the box will run against (Drive-current, not a locally
   hand-repaired working copy, not an older pull) — an offline "PASS" proves
   nothing if it validated different content than what actually shipped to
   the box.

This stale-copy loop was the single biggest source of repeated back-and-forth
in the session that produced this note — rule it out first before assuming
the repair itself is wrong.
