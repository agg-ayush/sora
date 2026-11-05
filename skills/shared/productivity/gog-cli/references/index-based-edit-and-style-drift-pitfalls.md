# Index-based edit corruption and paragraph-style drift

## Sequential index-based deletes/restyles corrupt text (indices shift)

`docs` API operations (delete text range, update paragraph style) address a
range by character index into the CURRENT document body. If you issue several
such ops in one plan computed from a single earlier `docs get`/`docs cat`
snapshot — e.g. "delete range 40-60, then delete range 120-140" — the first
delete shifts every index after it left by the deleted length, so the second
op now hits the wrong text. This silently corrupts the doc (wrong characters
removed, duplicated/mismatched sections) rather than erroring.

**Fix:**
- **Apply index-based ops in a single pass ordered highest-index-first**
  (process from the end of the doc backward), so earlier deletes never shift
  the indices of ops still queued.
- **Or re-fetch the doc and recompute indices after every single op** instead
  of batching a plan against a stale snapshot.
- **Or avoid index arithmetic entirely** for anything beyond a one-line
  find/replace: use `docs find-replace` (literal, no index math) for small
  fixes, and the recreate-from-markdown flow (see main SKILL.md "Iterative
  find/replace edits" section) for structural rewrites.
- If a doc ends up corrupted mid-edit, don't try to patch the corruption with
  more index-based ops — restore from the source markdown / a known-good copy
  and start over.

## Recipe: rewrite one section in place and style it natively

Use this when only one section (typically the trailing one) of an existing doc
must change and everything above it (credentials, tables, comments) must stay
byte-identical. Verified working end to end.

1. Snapshot: `gog docs cat <id>` (save the text before the section as the
   invariant prefix) and `gog docs structure <id> -j` → `{paragraphs:[{num,
   startIndex, endIndex, type, bullet, text}]}`.
2. Locate the section's first paragraph by an exact marker string; require
   exactly one match. Range = `startIndex` of that paragraph to
   `last_paragraph.endIndex - 1` (the API rejects ranges that include the
   body's terminal newline).
3. Replace with PLAIN text: `gog docs update <id> --replace-range START:END
   --file -` (stdin). Do not put markdown here — `update` inserts it literally.
4. Style each new paragraph by text match, one call each:
   - heading: `gog docs format <id> --match "<exact line>" --named-style=HEADING_2`
     (`--heading-level` takes an integer like `2`, not `HEADING_2`).
   - bullets: `gog docs format <id> --match "<exact line>" --bullets`.
5. Verify: re-run `cat` (prefix unchanged, removed text absent) and
   `structure -j` (heading paragraph `type == HEADING_2`, list paragraphs have
   a truthy `bullet`). For a doc holding secrets, also confirm each secret
   value still appears in the doc text, without printing the values.

Run the whole thing in one Python script with `subprocess` so indices are read
and used in the same pass, and print only booleans/indices, never doc text that
may contain secrets.

## Removing a wrongly-placed block from a tab that has live comments

When a block was appended to the wrong tab/location and that tab has live
unresolved comments elsewhere in the body, a full `--replace` is not an
option (see the `--check-orphans` pitfall in `multi-tab-doc-editing.md` —
it would orphan every comment in the tab, not just near the block). The
safe alternative is a **precise, minimal `deleteContentRange` scoped to
exactly the appended block**, computed like this:

1. Get the exact start index of the block from the write/insert response
   that created it (e.g. `docs insert` returns `atIndex`) or from
   `docs structure -j` — don't estimate it by eyeballing `docs cat` output.
2. Get the exact end index either from the same response (`atIndex +
   inserted` chars) or from `structure -j` paragraph `endIndex` values.
3. **Never guess the end index as "end of document."** A `deleteContentRange`
   with an end index larger than the actual block deletes everything after
   the block too — dry-run the delta first (compute `end - start` and sanity
   check it against the known block size) before issuing the real delete.
4. The Docs API rejects a range ending exactly at the document's terminal
   newline — if the block sits at the very end, use `end - 1`.
5. Verify afterward by re-reading the tab and confirming it ends where it
   should, and that the comment count elsewhere in the tab is unchanged.

## Paragraph style can drift silently on copy-paste

Content copied between docs can carry the wrong paragraph style invisibly —
e.g. bullet/heading text pasted in as `HEADING_2` when it visually reads as
plain body text. This is invisible to a `docs cat`/`docs get` check that only
confirms *section headings* are H2 — it does not confirm body content isn't
*also* tagged H2.

If the user reports "wrong font" / "not normal text" after a copy-paste or
restructure, check each line's `type` in `gog docs structure <id> -j` rather
than assuming "headings are H2" implies "everything else is NORMAL_TEXT".
