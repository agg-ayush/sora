---
name: di-script-contract-validation
description: "Fix DI script.md voiceover marker gate failures."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [alpha-learn, content-pipeline, trilogy, script-md, voiceover, parser, drive]
    related_skills: [content-pipeline-data-layers, content-repo-docs-map]
---

# DI Script Contract Validation (alpha-learn-content-gen)

## When to Use

- Asked to fix/repair a batch of `script.md` DI lesson scripts reported as
  failing the "voiceover timing gate" / "markers missing" / "the lesson was
  not spoken through" checks.
- Asked to audit whether `[tN]`/`[vN]`/`[iN]` animation markers are correctly
  placed in narration for one or more alpha-learn-content-gen lessons.
- Any request to validate a `script.md` against `script_to_json.py` or the
  DI script authoring contract before it ships.

Class of task: a batch of `script.md` files (Direct-Instruction lesson
scripts, one per Drive lesson folder) is reported as failing the voiceover
timing gate — the narration doesn't carry every on-screen element's animation
marker (`[t1]`, `[v2.3]`, `[i1]`, replay markers `[sN.iM.start/end]`), so the
runtime can't time when text/visuals/interactions appear. The task is to make
every element's marker land in the narration per the contract, validated
against the real parser.

**Read the contract and parser before touching any script:**
- Contract: `docs/brainlifts/scripts/inputs/contract.md` in the content repo
  (`/Users/ayush/Trilogy/content`) — the authored-syntax rules (`[SAY]`,
  `[TEXT tN]`, `[VISUAL vN]`, `[INTERACTION type]`, `[Stage n]`, pause tags).
- **There is more than one parser in this repo — do not assume which one is
  the live gate.** Two have been seen so far:
  - `ppt-generator/script_to_json.py` (may live only on a branch, e.g.
    `origin/script-to-video` — `git show <ref>:<path>` it out if not on the
    checkout you're on).
  - `stages/ingest/src/parser.py` (`Script.parse`, `anchor()`) — this is the
    one the actual voiceover **ingest** stage imports and runs at ship time.
  A prior repair pass in this codebase validated against `script_to_json.py`
  and produced edits that still failed the real ingest gate later — the task
  wording or the pipeline stage name ("ingest", "voiceover stage") tells you
  which is authoritative for THIS request; when in doubt, grep the actual
  pipeline stage's source for which module it imports rather than reusing
  whichever parser a previous session happened to use. Trust the live import,
  not a mental model of what "correct markers" means, and not the parser used
  last time without re-confirming it's still the same one enforced downstream.
- **`stages/ingest/src/parser.py` needs Python 3.12+** (nested same-quote
  f-strings on the violation-message lines). The sandbox/system `python3` may
  be older (seen: 3.9). Find and use the content repo's own venv instead,
  e.g. `/Users/ayush/Trilogy/content/venv/bin/python` — check
  `venv/bin/python --version` before assuming it's new enough.

## How the parser resolves a marker (read this before writing fixes)

Both known parsers enforce the same underlying contract (word → sentence →
uniqueness), just under different function/field names — the mechanics below
apply conceptually to either; check the specific module for exact names
(`script_to_json.py` uses `_land()`/`cue_at()`/`phrase_at()`;
`stages/ingest/src/parser.py` uses `anchor()` and resolves into each stage's
`trigger_word`/`trigger_phrase` dict entries directly).

For each stage/interaction, the parser finds the marker word in the narration,
then:
1. `cue_at(word)` walks forward from the marker until the resulting phrase
   is **unique within its sentence** — that becomes `trigger_word`.
2. `phrase_at(word)` returns the whole sentence containing the marker —
   that becomes `trigger_phrase`, but only if that sentence's text is not
   **repeated verbatim elsewhere in the narration** (repeats make the phrase
   ambiguous and the parser rejects it).
3. A marker on the last word of the narration is rejected (nothing follows
   it to time against).
4. Every declared `[TEXT tN]`/`[VISUAL vN]` stage must have exactly one
   matching marker (numbered per stage if the block has multiple `[Stage n]`
   entries); every `[INTERACTION]` needs exactly one `[iN]` marker, placed
   at the end of the sentence that closes right before it fires.

Fixing "missing marker" reports means: insert the marker at a word inside a
sentence that is (a) not the last word of the narration and (b) sits in a
sentence unique in the whole narration block — not just anywhere plausible.

Two ready-to-run fixer scripts ship with this skill:
`scripts/duplicate_phrase_marker_fixer.py` (normal marker density — nudge
one bad marker at a time, recheck globally) and
`scripts/simultaneous_boundary_assignment_fixer.py` (high marker density,
i.e. a segment has more markers than words — simultaneous even-spacing
assignment + overflow, then the same repair loop on top). See the pitfalls
below for which to reach for.

## Workflow

1. **Get the real failed-list and map lesson IDs to Drive folders.** The
   Grade-level Drive folder can paginate silently — if you expect N lessons
   and `gog drive ls` returns fewer, check for a `--max`/pagination flag
   before concluding the folder is short. Build `{lesson_id: folder_id}` by
   listing subfolders, then find `script.md`'s file id inside each.
2. **Download every `script.md` to a scratch dir**, one lesson per file
   named after the lesson id — batch this, don't fetch one at a time in
   separate calls.
3. **Run the actual parser against every file**, not a hand-rolled marker
   regex — `parse(text)` returns `(lesson_json, bad_list)`; `bad_list` empty
   means the contract holds. Collect this into a JSON audit report keyed by
   lesson id so partial progress survives interruptions.
4. **Also assert the actual downstream invariant**, not just "parser raised
   no violations": walk the parsed JSON and confirm every text/visual stage
   has a non-empty `trigger_phrase` (text stages also need non-empty
   `trigger_word`), and every interaction has a non-empty `trigger_phrase`.
   The parser can pass with zero `bad` entries in theory while a stage still
   lands emptied depending on how you call it — always check the actual
   output fields the voiceover stage consumes, don't just check `bad == []`.
5. **Only edit files with real violations.** For each violation string
   (e.g. `"slide 03: t2 states 1 stage(s), and the narration marks []"`),
   locate the named element's sentence in the `[SAY]` block and insert the
   marker at a word satisfying the uniqueness rules above, then re-run the
   parser on that one file before moving to the next.
6. **Re-run the full batch parser again at the end** to confirm 100% clean,
   and diff word-for-word against the original narration text to prove the
   edit was marker-insertion-only (content-preserving, no rewording).
7. **Upload fixed files back to Drive and round-trip-verify.** Local repair
   is not the deliverable — the Drive `script.md` is. For each lesson, find
   its file id inside the lesson folder (`gog drive ls --parent <folderId>
   --plain`, match the row whose name is `script.md`) and push with
   `gog drive upload <local> --replace <fileId> --force --no-input` (`--replace`
   keeps the same file id / shared link / permissions instead of creating a
   new file — do not use plain `upload` without `--replace` on an existing
   lesson file). Parallelize across lessons with a small thread pool; it's
   independent per file. Then re-download at least one uploaded file and
   re-run the checker/parser against the downloaded copy to prove the upload
   actually landed the fixed content, not just that the local file was right.
8. **Verify content-preservation two ways before declaring done**, not just
   "checker now passes": (a) strip all `[marker]` tags and `<break>` tags
   from old vs. new narration and diff — spoken words must be byte-identical
   except for legitimately newly-added markers for elements that had none;
   (b) confirm no single marker id appears twice inside the same slide's
   `[SAY]` block — a duplicate-within-slide is a sign the fixer looped and
   re-inserted a marker instead of moving it.

## Pitfall: auditing "does every trigger resolve uniquely" needs the parser's OWN sentence split, not a naive re-split

`bad == []` (or the ingest parser's `Findings` being empty) only proves the
parser didn't raise — it does not by itself prove every phrase is externally
verifiable as unique unless you check the resolved fields. When writing an
*independent* stricter check (e.g. "does this trigger_phrase repeat verbatim
elsewhere in the narration"), don't recompute sentences by re-splitting
`slide.voiceover` or similar convenience fields — they may have pause/break
tags stripped or preserved differently than the string the parser actually
tokenized (`self.spoken` in `stages/ingest/src/parser.py` strips `<break>`
tags; `slide.voiceover` does not). A naive re-split will show every phrase as
"0x occurrences" — a false alarm caused by string-normalization mismatch, not
a real gate failure. The reliable way: reconstruct the same object the parser
built (e.g. call `Voiceover.parse()` on the same raw per-slide `[SAY]` block
the real parse path used) and read its `.sentences` back, rather than
guessing at how narration text was normalized.

## Pitfall: hand-nudging one marker at a time to break a duplicate-phrase tie cascades into new collisions

Some gate variants (e.g. a standalone `marker-resolve-check.py` that checks
"does the phrase after this marker, up to the next marker or `<break>`,
occur exactly once in the whole cleaned narration") fail not because a
marker is *missing* but because two markers land on **identical** phrases
(e.g. `[t4]` and `[t11]` both resolve to "their opposite sides are
parallel."), or because a marker sits flush against another marker/a
`<break>` tag and resolves to an **empty** phrase.

The tempting quick fix — "move the losing marker one word to the left" —
is unsafe as a single-shot heuristic: shifting one marker can silently
break a *different* marker that was previously fine (its phrase now
absorbs new words and stops being unique, or a marker ends up flush
against a break and resolves empty). Applying that heuristic file-by-file
without re-checking the whole slide produced *new* UNRESOLVED entries that
weren't there before ("fixed" 3 markers, broke 4 others) — always re-run
the full checker after each nudge, never assume a local fix is safe in
isolation.

**Reliable algorithm** (implemented in
`scripts/duplicate_phrase_marker_fixer.py` — run it directly rather than
re-deriving this by hand):
1. Parse the narration's markers and `<break>` tags; for a given marker,
   its "phrase" is the substring from just after it to the next marker or
   break tag.
2. For each still-unresolved marker (empty phrase, or phrase occurring
   ≠1 times in the whole cleaned narration — cleaned = markers stripped,
   breaks collapsed to spaces): remove it, then try re-inserting it before
   every word position in the slide's narration.
3. Accept a candidate insertion point only if it **strictly reduces** the
   total count of unresolved markers in the slide (not just "target now
   resolves" — must also re-check every marker that was previously fine,
   since the move can regress others). Take the first such point.
4. Iterate slide-wide until no unresolved markers remain or no candidate
   improves the count (cap iterations, e.g. `len(elems) * 4`, to avoid
   infinite loops on a genuinely unfixable slide).
5. Re-run the real checker/parser on the whole file afterward — never
   trust the in-memory "all_resolve" bookkeeping as the final word.

This is content-preserving (only marker *position* moves, no wording
changes) and works for both the sentence-uniqueness contract described
above and the simpler whole-narration-phrase-uniqueness variant.

## Pitfall: when relocating multiple broken markers in one slide, track claimed PHRASES not just positions — or the fixer oscillates forever

If you write your own marker-repair script (rather than hand-editing), and a
slide has several markers whose phrase is empty/non-unique, the naive greedy
algorithm is: remove each broken marker, find the nearest position whose
resulting phrase is unique in the whole narration, reinsert there. This looks
correct per-marker but fails as soon as two broken markers in the same slide
are near each other (a common authoring pattern — e.g. `[t14] [t15]` placed
back-to-back before "D, nine times three."). Both markers' "nearest unique
phrase" resolves to the *same* sentence, because uniqueness is checked
against narration text, not against what other markers-in-flight are about
to claim. Symptom: re-running the fixer in a loop shows the same one or two
marker ids being reinserted at the same position pass after pass, forever
(check for this exact oscillation signature in a dry-run diff/debug log
before assuming the fixer is just slow to converge).

Fix: maintain a `taken_phrases` set seeded with the phrases already used by
markers that resolve correctly, and when assigning insertion points to the
batch of currently-broken markers, exclude any candidate point whose phrase
is already in `taken_phrases` or already claimed by another marker in this
same assignment pass (add to the set as each marker is assigned, not only
after the whole batch is written back). Assign greedily by distance to each
marker's original position, but always dedupe against phrase-uniqueness, not
positional distinctness — two different character offsets can still resolve
to the identical sentence/phrase and collide.

## Pitfall: a "fix N failing items" task can turn out to need zero fixes — verify before assuming the premise is wrong

If every item in the failed list parses clean and every element resolves a
trigger, don't conclude your parser/audit must be missing something and
start guessing at subtler failure modes. Check whether the artifacts were
**already repaired after the failure was reported**, before this session
started:

```bash
gog drive ls --parent <lesson_folder_id> --plain   # shows MODIFIED timestamp
```

Compare the `script.md` `MODIFIED` timestamp against the *parent folder's*
creation/modified time (or any other known "as of" marker for when the
failure list was generated). If the file was touched materially later,
you're looking at a stale failure list, not a live bug — a prior pass (human
or another agent run) already fixed it. In one such audit, folder creation
was `10:01` and every `script.md` had `MODIFIED` timestamps `15:16-15:37`
the same day — a ~5 hour gap that lines up with an earlier repair pass, not
noise.

**Report this precisely**: state the count that parsed clean out of the box,
say plainly that the failure list appears stale (with the timestamp
evidence), and recommend re-running the actual voiceover gate rather than
fabricating edits to "prove" work was done. Do not silently no-op without
explaining why — and do not invent marker placements on files that already
have correct ones just to show diff activity. Idempotent + content-preserving
means: if it already passes, touching it is the wrong move, not a
formality to skip.

## Pitfall: extreme marker density (more markers than words in a segment) breaks the nudge-one-marker algorithm entirely — needs a different first pass

The "reliable algorithm" above (nudge each unresolved marker to the nearest
word position that strictly reduces the slide's bad count) assumes there's
roughly one marker per word-ish. It breaks down completely when a single
`<break>`-delimited segment has to host **more element markers than it has
words** — seen in practice: 19 `[tN]` markers all needing to anchor inside
"Each group has six objects." (6 words). It is mathematically impossible for
19 markers to each get a unique non-empty phrase out of 6 words in that one
segment; some *must* end up anchored in other segments.

Symptom of using the nudge algorithm here: it "fixes" a few markers by moving
them into a neighboring segment, but then their phrases collide with markers
that already legitimately live there — whack-a-mole across segment
boundaries, and iteration count balloons without converging (11/17 → stuck,
or worse, a naive sequential-insert rewrite regressed 17 files from 7/17
passing down to 1/17 because inserting marker N shifts the text every
later-inserted marker's phrase is computed against).

**Working two-phase approach** (implemented in
`scripts/simultaneous_boundary_assignment_fixer.py` — run this FIRST on
high-density slides, before falling back to the nudge algorithm for
leftovers):

1. Strip every element marker (`[tN]`/`[vN]`) from the narration entirely —
   don't try to move markers incrementally, rebuild from scratch. Leave
   words, `<break>` tags, and `[sN.iM.start/end]` markers untouched.
2. For each `<break>`-delimited segment, count its word tokens `W`. Take the
   markers that originally lived in that segment (in their original relative
   order) and assign them **evenly spaced** boundary indices in `[0, W-1]`
   (`b = k * W // M` for the k-th of M markers) — this is a single
   simultaneous assignment, not a sequence of one-at-a-time inserts, so no
   earlier assignment's phrase is invalidated by a later one.
3. If a segment has more markers than words (`M > W`), the excess overflow
   into whichever *other* segment still has free capacity (fewer markers
   assigned so far than its word count); only dump them on the last segment
   regardless of capacity as a final fallback.
4. Rebuild the narration once from this complete assignment (insert all
   markers at their assigned word-boundaries in one pass), THEN run the
   existing uniqueness-repair loop (pitfall above / `duplicate_phrase_marker_
   fixer.py`'s `fix_slide`) on top of it to resolve any remaining collisions
   by searching every boundary in every segment (own segment first) for a
   placement that doesn't just resolve the target marker but doesn't
   increase the slide's total bad count.
5. Verify two ways before trusting it: (a) run the real checker/parser, and
   (b) diff spoken words (markers + breaks stripped) old vs. new — must be
   byte-identical, proving only marker *positions* changed. On a 17-file
   batch with this two-phase approach, this hit 17/17 resolved with 0 word
   diffs, where the single-phase nudge approach alone had plateaued at
   11/17 and a naive sequential rewrite regressed to 1/17.

Use `duplicate_phrase_marker_fixer.py` alone when density is normal
(markers-per-segment roughly ≤ words-per-segment); reach for the two-phase
`simultaneous_boundary_assignment_fixer.py` when any segment's marker count
approaches or exceeds its word count.

## Pitfall: staged element + stray BARE marker — the fix is delete-only, and ingest ALSO requires staged markers in ascending order

A slide whose `[VISUAL vN]` block has k `[Stage n]` entries must carry exactly
`[vN.1] .. [vN.k]` in its `[SAY]`, **in ascending stage order**, and nothing
else. Two authoring breakages show up together:

1. A stale **bare `[vN]`** sits alongside the staged markers (leftover from
   before the visual was split into stages). Both the ingest parser ("states k
   stage(s), narration marks ['vN', 'vN.1', ...]") and any staged-aware marker
   checker flag it. The fix is to **delete the bare token only** — do NOT
   redistribute/re-derive the staged markers, which are usually already
   correct; rewriting them destroys working placements.
2. Any fixer that then moves staged markers for phrase uniqueness can leave
   them **out of order** (e.g. `[v1.2]` before `[v1.1]`). The ingest parser
   compares the landed stage sequence to `list(range(1, k+1))` — order matters,
   not just presence. Phrase-nudging must therefore be **order-constrained**:
   candidate placements that invert two staged markers of the same element are
   invalid even when every phrase is unique. Add an order penalty to the
   candidate scoring, or expect a residual finding you must hand-swap.

Also note: a checker variant that runs the bare-marker phrase check
unconditionally (`find("[vN]")`) can NEVER pass a staged element — if every
staged script in a batch reports "marker [vN] not in narration" right after
you dropped the bare one as instructed, suspect the checker predates staged
support and confirm with the task owner before contorting the scripts.

## Pitfall: chaining sequential hand-written string-replace patches on the same region silently corrupts text

When hand-fixing a handful of stubborn markers (rather than running the two
fixer scripts), it's tempting to plan a multi-step relocation in your head —
"move t6 here, then t7 lands on 'the number', so shift it to 'the'" — and
issue each edit as a separate `old_string`/`new_string` replace based on what
you *intended* the previous edit to have produced, rather than what actually
landed on disk. This diverges silently: one edit inserted `[t6] the [t7]
number`, the very next edit's `old_string` assumed `[t6] the` was still
followed by `[t7] number five hundred...` but actually duplicated the word
("the number [t7] number five hundred forty is [t8] true?") because the
intended text and the real text had already drifted by one step. The checker
then reports a *new*, confusing failure ("lands on 'the number' which appears
2x") that looks like a fresh collision but is really a self-inflicted typo.

Fix/prevention: after every hand-applied relocation in a multi-step manual
sequence, `grep`/read back the exact current substring around the edit
before writing the next replace's `old_string` — don't chain edits from
memory of what you meant to write. If a checker failure after a hand-edit
looks structurally odd (a repeated word, not just a repeated phrase), suspect
the edit itself introduced the duplication before assuming it's a new
marker-placement collision to solve.

## Pitfall: fixing markers one-at-a-time in isolation causes whack-a-mole regressions

When several markers in the same slide have conflicting placements (clustered
runs, duplicate-phrase collisions), do not write a fixer that processes each
bad marker independently and moves on — moving marker A to a new word
position changes the sentence/phrase boundaries that marker B's placement
depends on, so "fixing" B can silently re-break A. Symptoms: a fix loop that
plateaus at a small nonzero failure count across iterations, or fixed counts
that oscillate instead of monotonically decreasing.

The reliable structure is a **global convergence loop per slide**, not a
per-marker one-shot pass:

1. Spread any obvious marker clusters/runs across following words first
   (cheap, does most of the work).
2. Insert any genuinely missing markers.
3. Loop: recompute the *whole slide's* issue list from scratch (not just the
   one marker you last touched). If empty, stop. Otherwise take the first
   remaining issue's marker, and do a **direct search** — try placing it at
   every word position in the slide's narration, and for each candidate
   re-check the *whole slide's* issue count. Only accept a candidate whose
   placement gives that marker a unique phrase **and** does not increase the
   slide's total issue count (prefer strictly decreasing; leftmost such spot
   is a fine tiebreaker). Repeat.
4. Cap iterations (e.g. 200) to guarantee termination; if truly stuck, fall
   back to nudging the marker one word forward rather than looping forever.

This "recompute global state, accept only non-regressing local moves" pattern
is the one that actually converges — a queue of independent per-marker fixes
does not, because it has no way to notice it just broke something it already
fixed.
