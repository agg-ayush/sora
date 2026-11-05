# `gog sheets` — reliable read/write patterns

## Multi-column reads: always pass `-p` (plain/TSV), never the default table view

`gog sheets get <id> "<Tab>!A2:Q182"` WITHOUT `-p` renders a fixed-width text
table that's hard to parse reliably in code — columns don't line up cleanly
once cell content varies in length. With `-p` the same range comes back as
one tab-separated line per row, trivially split with `.split("\t")` and
indexed by column position — this works fine even for wide 15+ column pulls,
no need to fall back to one-column-per-call. Redirect straight to a file
(`gog sheets get ... -p > "$TMPDIR/x.tsv"`) and read/split lines in Python.

If a `gog` read looks broken/garbled, check first whether `-p` was omitted —
that's the actual problem far more often than gog itself being broken. Only
fall back to pulling **one column per call** with a narrow range
(`"<Tab>!N2:N182"`) if a `-p` multi-column pull still won't parse cleanly
(e.g. cell values containing literal tabs/newlines).

## Listing tab names/gids before reading a specific tab

`gog sheets get` needs a tab NAME in its range (`"<Tab>!A1:Z5"`), but a
spreadsheet URL only gives you a `gid=<number>`. There's no `gog sheets`
subcommand to list tabs — use the raw API escape hatch (see main SKILL.md):

```bash
gog api call sheets v4 spreadsheets.get \
  --params '{"spreadsheetId":"<id>","fields":"sheets(properties(title,sheetId))"}' \
  --account <acct>
```

Match the `gid=` from the URL against the returned `sheetId` to get the real
tab title, then use that title in `gog sheets get "<Title>!A1:Z5"`. Do this
before reading a sheet whose URL points at a specific tab — guessing a tab
name ("Master", "Sheet1") wastes calls and can silently read the wrong tab.

## Matching rows between two sheets: key on a stable identifier, not row number

When copying data from one spreadsheet to another that are *expected* to
mirror each other (same form, same rows), don't assume row N in sheet A is
row N in sheet B. Pull a stable identifying column (email, ID) from both,
build `email -> row_number` maps independently for source and destination,
and join on the key. Row numbers can drift even when the sheets look
aligned; the key join catches it for free and costs nothing extra.

**When the two sources can legitimately use different emails for the same
person (a candidate registers for an assessment with a personal gmail, but
a college/roster sheet lists their institute email), a raw email join will
report most of the population as "missing" when they aren't.** Before
concluding anyone is absent from the destination sheet: normalize and join
on phone number as the primary fallback key (`re.sub(r'\D','',phone)[-10:]`
to strip formatting/country-code differences), then on lowercased full name
as a second fallback. Only the rows that fail BOTH the email join and the
phone/name fallback are genuinely missing. Report the breakdown explicitly
(e.g. "96 missing by email, 87 of those matched by phone under a different
address, 9 truly missing") — collapsing straight to "96 missing" and adding
duplicate rows for people already present under another email is the
expensive mistake this check prevents.

## Reconciling a full source population against a tracking sheet before writing results

When asked to "make sure everyone from list X is in the master sheet, then
write result Y for each of them" (e.g. writing pass/fail outcomes for every
candidate from a cohort roster into a shared funnel tracker):

1. Pull the full source population (every row of the cohort/roster tab, not
   just the ones you have a verdict for) and the full destination tab.
2. Join source -> destination using the identifier fallback chain above
   (email, then phone, then name) — never assume "not found by email" means
   "not in the sheet yet."
3. Only the rows that fail every fallback are real gaps — add exactly those
   as new destination rows, carrying over whatever fields the source
   provides (name/email/phone/college) plus any funnel-stage flag that's
   true for the whole cohort (e.g. "Sent = Yes" if the batch was sent to
   everyone).
4. Write the result/outcome column for the FULL reconciled set (existing
   matched rows + newly added ones), not just the rows you happened to find
   on the first email-only pass — a candidate added in step 3 still needs
   the same result write as everyone else in the batch.

## Writing into existing named columns: derive the letter from the header row, never count by eye

When the ask is "write X into the sheet's <Batch>/<Start> columns" on a tab that already has those headers, pull row 1 with `-p`, find each target header's index programmatically (`headers.index("ADD batch")`), and convert index to letter (`chr(ord('A')+i)` for i<26) before building ranges. Counting columns visually or from a partial read is off by one easily (a hidden or blank column shifts everything), and the write lands in the neighbouring column silently. After writing, read back the header plus 2-3 data rows of the exact range and assert the value sits under the intended header. If a wrong-column write happened, clear only the wrongly written cells (snapshot them first; they may have held real data) before rewriting to the correct letters.

## Appending rows: `sheets append` can land in the wrong columns — write an explicit range instead

`gog sheets append <id> '<Tab>' --values-json ...` lets Sheets detect the "table" to append to, and on a tab with extra data blocks to the right (e.g. batch/start columns at O:P filled for existing rows) it can anchor to that block and write the new rows starting at column O instead of A. The response says so (`Appended N cells to Tab!O306:Y308`), so read the returned range before trusting it. For adding rows to a tab with known headers, find the next empty row from column A (`sheets get '<Tab>'!A:A`), then `sheets update '<Tab>'!A<n>:<lastCol><m> --values-json` at that explicit range, and read back columns A-C of those rows to confirm. If an append already landed offset, `sheets clear` the offset range and rewrite at the explicit range.

## Batch-writing scattered cells: `gog sheets batch-update`

For writing many non-contiguous single cells (e.g. one column value per
matched row across dozens of rows) in one API call:

```bash
# Build a JSON array of {range, values} objects, one per target cell:
# [{"range": "Sheet1!N15", "values": [["weak_hire"]]}, ...]
python3 -c "... build data list ..." > /tmp/batch.json

gog --account <acct> sheets batch-update --data-json=@/tmp/batch.json \
    <spreadsheetId> --include-values-in-response -j
```

`--data-json` accepts either an inline JSON string or `@<path>` to a file —
use the file form once you have more than a couple of cells, it's easier to
build and inspect than shell-escaping inline JSON. `values` is always a
list-of-rows-of-cells (`[["single value"]]` for one cell), even for a single
cell write.

**Pitfall — the payload is a bare array of ValueRange objects, never wrapped
in `{valueInputOption, data: [...]}`.** That wrapper shape is the raw Sheets
API `batchUpdate` request body, and passing it to `gog sheets batch-update
--data-json` fails with `invalid JSON data: json: cannot unmarshal object
into []*sheets.ValueRange`. gog's own CLI already expects the inner `data`
array directly — `[{"range": "Sheet1!A1", "majorDimension": "ROWS",
"values": [[...], [...]]}, ...]` — so a single `{range, majorDimension,
values}` object writing a whole grid in one shot (e.g. pushing a full CSV as
one range starting at `A1`) works exactly like the scattered-cells example
above, just with one multi-row entry instead of many single-cell entries.
Don't reach for the raw `gog api call sheets v4 spreadsheets.batchUpdate`
escape hatch for a plain full-grid write — the friendly `sheets batch-update`
verb already takes this shape directly.

## Rule-based bulk column fills ("where col X is V, set col Y to W")

For conditional fills across a whole tracking tab (e.g. Submitted=No -> Result `-`, Result=Failed -> Feedback text), this procedure worked first try on 2k+ rows:

1. List tabs via `spreadsheets.get` and pull headers of every tab; pick the tab whose headers actually contain the named columns (a workbook can have several look-alike tabs). If more than one tab qualifies, ask.
2. Snapshot the full target columns to a scratch JSON (`sheets get ... "'<Tab>'!A1:J<rowCount>" -j > before.json`). `-j` omits trailing empty cells, so index rows with a `len(r)>i` guard, never `r[i]`.
3. Print `Counter`s of the condition and target columns first. Match conditions on stripped, casefolded values so stray whitespace/case variants are caught.
4. Build the payload from only the cells whose current value differs from the target, so reruns are no-ops. Save any nonempty values about to be overwritten to a chmod-600 scratch file for rollback. Report that count; overwriting existing text is the risky part of the change.
5. Chunk into files of about 400 single-cell ValueRanges, then run `sheets batch-update --data-json=@file` per chunk from `terminal`. Assert each response's `totalUpdatedCells` equals the chunk length.
6. Re-read the same range and diff every row against the expected transform: condition rows must hold the new value, and every other cell must be unchanged. Require zero mismatches. Report rows changed per column plus mismatches (0).

Chained rules (a later ask like "where Result is `-`, set Feedback to `-` too") run the same procedure against a fresh snapshot, never against a snapshot from an earlier step.

## Pitfall: a shared roster sheet mixes multiple populations — don't eyeball the head rows

A "grab the <college/cohort> dataset" ask is often pointed at ONE tab of a
form-response sheet that actually pools submissions from many colleges/
cohorts, differentiated only by a `College`/`Cohort` column value (with messy
free-text variants like `IIT Gandhinagar `, `IIT GANDHINAGAR`, `IIT
Gandhinagar\xa0`). Reading only the first ~20-50 rows and observing they're
all one college is not evidence the whole sheet is that college — the target
rows can be anywhere in a 1000+ row sheet.

Before concluding "this dataset isn't in this sheet":

1. Pull the FULL range, not a small head window — `gog sheets get <id>
   "A1:Z<generous-row-count>" --plain` (pad the row bound well past any
   expected size; check the returned line count against the bound to catch
   truncation).
2. Identify the discriminating column programmatically (find the header
   whose name matches college/cohort/etc.), then filter case-insensitively
   with a regex tolerant of whitespace/case variants — never by scanning
   visually.
3. Only report "not in this sheet" after a real filter over the full row
   set returns zero matches on both the college-name column AND a plausible
   email-domain check (an institute's rows can carry an inconsistent/wrong
   college label while the email domain still gives it away). If both come
   back empty, say so plainly and ask whether there's a different tab/sheet
   for that cohort — don't guess at a second sheet without asking.

## Pitfall: write commands need a real TTY for the keyring backend, even when reads work fine

`gog sheets update`/`batch-update` (and other write verbs) can fail from a
non-TTY caller (e.g. `execute_code`, a piped subprocess) with `read OAuth
client secret from keyring: ... no TTY available for keyring file backend
password prompt; set GOG_KEYRING_PASSWORD` — even though `gog sheets get`
against the same spreadsheet with the same account just worked. Reads and
writes hit the keyring differently; a working read is not proof the write
will go through the same execution path. Set `GOG_KEYRING_PASSWORD` in the process environment from the host secret store without printing it. A terminal invocation may not provide a TTY; use PTY only if the CLI actually requires one. Retry the write and verify exact cells.

## Growing a sheet past its current grid size before a batch write

`gog sheets update <id> "<Tab>!A<start>:Q<end>"` fails with `Google API
error (400 badRequest): Range ... exceeds grid limits. Max rows: <N>` when
the target range extends past the tab's current row count — this is a hard
grid-size limit, not a permissions or payload issue. Grow the tab first via
the raw API escape hatch, then retry the same write unchanged:

```bash
gog api call sheets v4 spreadsheets.batchUpdate \
  --params '{"spreadsheetId":"<id>"}' \
  --body '{"requests":[{"appendDimension":{"sheetId":<tab_gid>,"dimension":"ROWS","length":600}}]}' \
  --account <acct> --allow-write -y
```

Two things that trip this up: (1) any `gog api call` for a POST-based method
(`batchUpdate`, `create`, etc.) refuses with `method ... uses POST; pass
--allow-write to opt in` unless `--allow-write` is passed explicitly —
that's a deliberate safety gate, not an error; (2) `--params` is for the
URL/path parameters (here just `spreadsheetId`), the actual request payload
goes in `--body` (inline JSON or `@file`) — passing the whole request body
via `--params` gets rejected as an unexpected argument. `sheetId` in the
body is the tab's numeric gid (same number as `gid=` in the browser URL),
not its name.

When writing a large backfill in row-chunked batches (e.g. 200 rows per
`gog sheets update` call to stay under range-size limits), check each
chunk's start/end against the tab's current row count before firing the
batch loop — growing the sheet once for the full expected row count up
front avoids re-running failed batches after a mid-loop grid-limit error.

## Deriving cross-field consistency rules when backfilling a tracking sheet from messy sources

When building a master/tracking sheet from multiple messy source forms (e.g.
merging a "sent/submitted/result/feedback" funnel from several intake
sheets), the source data is frequently self-inconsistent — a status column
says "No" while an adjacent feedback/notes column contains real feedback
text, because the two columns were populated by different processes at
different times. Don't write the raw source values straight across; derive
and enforce the implication chain instead:

1. **Feedback/output existing implies the upstream steps happened.** If a
   feedback or result field is non-empty, the corresponding "Submitted"
   field must be Yes, and "Sent" must be Yes in turn (you can't submit
   something never sent). Walk the chain outward from the most-concrete
   field (feedback/result text) toward the least-concrete (sent), not the
   other direction.
2. **Watch for a specific-negative phrase inside the feedback text that
   inverts the naive rule** — e.g. feedback literally saying "did not take
   the assessment" is still non-empty text, but it means Submitted=No, not
   Yes (the feedback is describing a no-show, not an outcome). Grep the
   feedback column for negation phrases ("did not", "no show", "n/a") before
   applying the blanket "feedback exists -> submitted yes" rule, and carve
   those rows out to the opposite value plus a Result of Failed.
3. **Apply the rule with a script over the full column, then verify in the
   live sheet after writing** — count inconsistencies with a script matching
   the same predicate used to fix them (e.g. "any row where feedback is
   non-empty and submitted != Yes") and require zero before considering the
   backfill done. Report the count fixed and the count verified, not just
   "applied."

## Recovering a missing identifier via a secondary lookup (e.g. GitHub handle from a PR link)

When a submission/reference link points at a shared org resource instead of
the candidate's own account (e.g. a take-home assignment submitted as a pull
request against the company's repo, so the naive "first path segment after
github.com/" parse yields the org name, not the candidate), don't leave the
field blank or attribute it to the org — resolve the real identity through
the resource's metadata:

```bash
gh api repos/<org>/<repo>/pulls/<number> --jq '.user.login'
```

The PR/issue author field carries the actual candidate's handle even when
the URL path only shows the org/repo. Batch this over every row whose link
matches the org-owned pattern, write the resolved handle back (as a full
profile URL, `https://github.com/<login>`, if that's the column's format
elsewhere), and only leave a field blank for rows where the source link is
genuinely empty (not recoverable at all) — report that residual count
explicitly rather than silently leaving all originally-blank rows unexplained.

## Pitfall: wrong subcommand name fails silently when piped through a parser

There is no `gog sheets values get` — the correct verb is `gog sheets get
<id> <range>` (the noun/verb table is `get (read,show)`, not `values get`).
Calling the wrong form doesn't crash loudly: it prints `unexpected argument
values` to stdout/stderr and exits, but a downstream Python parse (e.g. a
regex pulling emails out of the output) just finds zero matches on that
error text and looks like "the sheet is empty" or "this row is missing" —
a false negative that can lead to reporting a real row as absent. Before
trusting any "not found in sheet" conclusion from a piped `gog` command,
print/inspect the raw output first (or check for a plausible row count) to
rule out a command-syntax error masquerading as an empty result.

## Deleting rows/columns structurally: `delete-dimension`, never clear+rewrite

There is no `delete-rows` verb; the row-removal verb is `delete-dimension`. Plain `sheets clear` on the rows only blanks values and leaves empty rows in the middle of the sheet, which is not what "remove these rows" means.

When the ask is "remove the rows where column X is empty" (or any row/column
deletion), use `gog sheets delete-dimension --dimension=ROWS <id>
"'<Tab>'!<start>:<end>"` — it shifts the grid and preserves hyperlinks, cell
formatting, and notes on the surviving rows. Don't fall back to a
clear-and-rewrite (read all keep-rows, blank the sheet, write them back) as
the default approach: it's a value-only round trip that flattens any
hyperlinked cells (e.g. a GitHub-link column) down to plain display text and
drops per-cell notes/formatting. Reserve clear+rewrite for when the delete
set is truly non-contiguous garbage or when the sheet has no formatting worth
preserving.

Procedure:
1. Pull the full sheet with `-p`/JSON, find the empty/target rows by the
   deciding column, and collapse them into contiguous `(start, end)` runs —
   a single big empty block plus a handful of scattered singles is the
   common shape, not one row at a time.
2. Delete runs in **descending** row-number order (highest range first) so
   earlier deletions never shift the row numbers of runs still queued —
   this is why one ascending pass would corrupt later ranges.
3. Quote the tab name for `delete-dimension`'s range argument
   (`"'Master sheet'!10:427"`) — an unquoted multi-word tab name breaks the
   range parse.
4. Verify after: re-pull the sheet, confirm the deciding column now has zero
   empties and the row count matches `original - deleted`.

Don't go hunting for gog's underlying OAuth access token (exporting a
refresh token, reading keyring internals, or trying ADC) to hit the raw
Sheets API yourself for a structural edit — `gog sheets delete-dimension`
and `batch-update`/`api call ... --allow-write` already cover row/column
deletion and any other batchUpdate request without touching a secret. ADC
(`gcloud auth application-default print-access-token`) in this environment
is scoped to GCP/GCS only and has no Sheets scope regardless of which
Google account it's tied to — don't spend calls probing it for a Sheets
path. If a needed structural op genuinely has no `gog sheets` verb, use
`gog api call sheets v4 <method> --allow-write` (see the grid-growing
example below) rather than extracting credentials.

## Pitfall: read access does not imply write access — verify before building the whole payload assumption

`gog sheets get` succeeding on a spreadsheet says nothing about write
permission. A sheet can be shared **view-only**; `batch-update`/`update`
against it fails with `Google API error (403 forbidden): The caller does
not have permission`, distinct from an auth/token error.

To confirm write is actually the blocker (not a malformed payload or wrong
range), isolate with one throwaway write to an empty scratch cell far from
real data (e.g. `Z1` or a column past the last used one):

```bash
gog --account <acct> sheets update <id> "<Tab>!Z1" "" 
```

If that alone 403s, the fix is out-of-band — the sheet owner needs to grant
edit access to the account `gog` is authenticated as. Don't retry the batch
payload or suspect the JSON shape; report the permission gap and hand back
the prepared payload/file path so the write can be replayed immediately
once access is granted.
