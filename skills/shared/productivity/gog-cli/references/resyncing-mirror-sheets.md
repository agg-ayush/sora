# Re-syncing "mirror" sheets: diff every column, don't replay an old mapping

When a sheet was already synced once from a source ("copy") sheet into a
destination tracker (e.g. voice-assessment verdicts copied from a working
sheet into a shared hiring tracker), and the user later asks to "copy the
fields" again, don't assume the source is unchanged and don't reuse a stale
in-session value mapping from the earlier sync. Source working sheets get
revised between syncs — e.g. raw tokens like `weak_hire`/`abandoned` get
cleaned into a proper `Yes`/`No` plus a new prose-feedback column after the
first sync lands. Before writing anything on the second pass:

1. Pull matching column ranges from both sheets and diff **every** column
   pairwise, not just the one you assume changed. This catches drift you
   weren't expecting — e.g. a feedback column that was blank at the first
   sync now has content, or a verdict column's vocabulary changed shape
   entirely (raw enum tokens → clean Yes/No).
2. Expect your own prior writes to show up as "diffs" too (dest has your
   earlier value, source is blank for that column) — that's the normal
   footprint of a one-way sync, not a signal to re-copy that column in the
   other direction. Read the diff for *which* columns changed and *in which
   direction* before deciding what to overwrite.
3. Re-confirm row alignment by a stable key (email/ID) even though it was
   verified in the earlier sync — don't reuse cached row numbers from a
   previous turn; the sheet may have grown or been resorted.
4. When scope is ambiguous ("copy the fields" — all rows or just the ones
   already touched, overwrite-in-place or fill-blanks-only), clarify the
   exact columns and direction before writing — especially when a
   full-column overwrite would replace values you wrote earlier in the same
   session under a since-superseded convention (e.g. raw verdict tokens you
   synced first, now superseded by the source's cleaned-up Yes/No values).

See `references/sheets-cli-patterns.md` for the underlying read/diff/
batch-write mechanics (one-column-per-call reads, key-based row joins,
`batch-update` payload shape).
