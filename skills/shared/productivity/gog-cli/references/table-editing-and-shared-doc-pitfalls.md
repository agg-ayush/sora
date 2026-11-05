# Editing gdocs that contain tables, or that a counterparty is reviewing

## Full-body delete/rewrite fails once the doc has a table

`docs edit` (find/replace) and any range-delete through `gog` silently balk
once the target range spans a table's cell boundaries — a whole-body delete
on a doc containing a table (e.g. a DOK1 facts table) gets rejected or only
partially applies. Doing it piecemeal (anchor-deleting each cell's text
occurrence by occurrence) is fragile: if the doc has two structurally similar
tables (e.g. an old one being replaced and a new one already inserted),
occurrence-matching can misfire and delete text from the *wrong* table,
progressively damaging both. Don't chase stragglers cell-by-cell — that's
whack-a-mole that degrades a live shared doc further with each pass.

**Reliable fix:** go around `gog`'s range-delete entirely and hit the Docs
API directly for the destructive step:

1. Mint a Google OAuth access token with Docs scope (reuse the local
   credential flow `gog` already authenticates with — check for a cached
   token/refresh path before assuming new OAuth setup is needed).
2. Call `documents.batchUpdate` with a single `deleteContentRange` spanning
   the entire body (index 1 to the doc's reported end index minus 1) — this
   wipes prose *and* tables atomically in one request, sidestepping the
   cell-boundary limitation that blocks it through `gog`.
3. Verify the body is empty (`gog docs cat <id>` returns nothing but the
   doc's title/metadata).
4. Reinsert clean content the normal way: `gog docs insert --markdown --file
   <md>` (renders headings/tables correctly, unlike raw `docs update`).
5. Verify end-to-end: table count, section order, and a few known-unique
   strings all present — confirm no orphan structure survived.

This is the move the moment a delete is fighting table structure — don't
spend multiple passes on anchor-text whack-a-mole first.

## Shortening/rewriting a doc while keeping images and formatting intact

"Shorten this doc" / "humanize this doc" almost always means: cut prose
fluff, keep everything else exactly where it is — every inline image at
its original position, every table, heading, and list format untouched.
The user will treat a formatting/image loss as a failed deliverable even if
the text content is otherwise correct and well-trimmed.

**Do not use `docs cat`/text-export + `docs create`/`docs insert --markdown`
for this.** That path round-trips through plain text: inline images,
table cell styling, and most rich formatting are silently dropped on the
way out and never come back on the way in. This looks like it worked (the
new doc reads fine) until the user checks it against the original.

**Correct procedure:**

1. `gog docs copy <sourceDocId> "<New Title>" -a <acct>` — a Drive-level
   duplicate. This is the only path that carries every image, table, and
   style forward exactly, because nothing is round-tripped through a text
   export.
2. Read the duplicate's prose with `gog docs cat <newId>` to get exact
   sentence text (hyphenation, punctuation, capitalization must match
   character-for-character for step 3 to hit).
3. Apply shortened sentences one at a time via `gog docs edit <newId>
   '<exact find>' '<replace>' -j`, checking `replacements == 1` for each
   (0 means the find string didn't match verbatim — re-copy it from the
   `docs cat` output rather than retyping from memory; >1 means it matched
   more than one location, e.g. a heading and a table both containing the
   same label — inspect both hits with `grep -n` on a fresh `docs cat`
   dump before deciding it's fine to leave as-is).
4. Verify before handing back: `gog docs images list <newId>` count
   matches the original doc's count exactly, grep the before/after text
   dumps for every load-bearing number/citation/name to confirm none were
   dropped, and check for Oxford commas / em-dashes / curly quotes
   introduced by the edits if the user has a house style banning them.
5. Clean up any earlier wrong attempt (e.g. a text-only tab or doc that
   lost images) — delete it — once the corrected version is verified good,
   so the user isn't left with a broken artifact alongside the right one.

## Don't edit a doc the counterparty is already reviewing, without being told to

If a doc already has a reviewer's comments on it (went to a stakeholder for
feedback) and the ask is a substantial rewrite, do the rewrite in a **new
duplicate doc**, not in place on the original — even when technically
capable of editing it cleanly. This preserves the original with its live
comment thread intact, and lets the user diff old vs. new before deciding
what to push back into the reviewed doc. Only write into the original once
the user explicitly says to replace/sync it. Default to "new doc for the
rewrite, old one untouched" whenever a shared/reviewed doc is the source
being reworked.
