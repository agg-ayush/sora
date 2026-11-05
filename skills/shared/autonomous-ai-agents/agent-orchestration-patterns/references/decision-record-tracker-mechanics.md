# Decision-record tracker mechanics (see `hiring-eval-report-generation.md`)

Same class of work (evaluator report review for a hiring pipeline), new
failure modes from a later session running the same pattern.

## Retrieving "I left comments" on request: filter by timestamp, don't ask which candidate

The user will repeatedly say just "left comments" (no candidate name
attached) as they move through a batch of N candidate reports. Don't ask
which candidate — pull the notes file (e.g. `notes.jsonl`), filter using a stable note ID/cursor (not timestamp alone, which can miss
late-arriving or backdated notes), and group new entries by
candidate (usually one, but not always — a late note can land on an earlier
candidate they scrolled back to). Log the full quote + the user's comment
into the tracker verbatim, grouped under that candidate's detail section,
then give a short read of the overall lean (hire/no-hire/uncertain) the notes
point to — don't re-litigate notes already logged in a prior turn.

## The final deliverable is a defensible decision record, not a summary

When this review is being done to support a real hire/no-hire call the user
will have to justify to others (their own words: "people are gonna come at
me so I need to be stringent on why I'm passing someone... it should help me
defend my position"), the end artifact for each candidate must chain
**verdict → the user's own stated reasoning → the specific evidence that
backs it** (highlighted quotes, transcript line refs, eval scores/flags that
corroborate) — not a paraphrase of the evaluator's report. Structure each
candidate's tracker section so a reader lands on the verdict, sees the reason
in the user's own words, and can click straight through to the primary-source
evidence (the transcript, the exact quote) without having to trust a summary.
Same "link to primary sources, don't summarize away detail" bar as any
compact dashboard/report.

## Pitfall: appending a new candidate section via a text-anchor patch can corrupt the decision table

When the tracker is a running markdown file with one summary table (one row
per candidate) followed by per-candidate detail sections, and rows +
sections get added incrementally as each candidate is reviewed, an
old-string anchor on a table row (to insert the next row right after it)
will frequently land the new detail section's prose **inside** the table
markup instead of after it — markdown tables have no explicit closing
delimiter, so a naive anchor/insert splits the table in two. This happened
repeatedly in one session (had to be fixed 3 separate times as new rows kept
getting added). Fix: after any append to a tracker like this, immediately
grep for the table's row-marker pattern (e.g. `^\| (name1|name2|...) \|`)
and confirm exactly the expected row count appears contiguously, with detail
sections appearing only after the last row — don't assume the edit landed
where intended just because the tool reported success.
