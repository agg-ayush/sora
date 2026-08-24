---
name: gog-cli
description: "Create/read/edit Google Docs, Drive, Sheets, Gmail, and Calendar via the `gog` CLI — the authenticated tool of choice in this environment, preferred over the bundled google-workspace (gws) skill for quick Docs/Drive/Sheets work."
version: 1.0.0
metadata:
  hermes:
    tags: [Google, Docs, Drive, Sheets, gog, CLI]
---

# gog CLI

`gog` (`/opt/homebrew/bin/gog`) is a pre-authenticated Google API CLI. For this
user, prefer it over the bundled `google-workspace` skill's `gws`/Python
backend for Docs/Drive/Sheets tasks — no OAuth setup needed, it's already
authorized for `ayushaggarwal018@gmail.com`.

Every command takes `--account <email>` (or `-a`). Add `-j` for JSON output,
`-p` for plain TSV. Discover flags with `gog <noun> --help` and
`gog <noun> <verb> --help` — the CLI surface is large (tables, chips,
footnotes, section breaks); don't guess a flag, look it up.

## Creating a Google Doc from a local markdown file

This is the standard "move this local doc/report into a gdoc" flow:

```bash
ACCT=ayushaggarwal018@gmail.com

# 1. Create the (empty) doc, capture its Drive file id
gog --account "$ACCT" docs create "Doc Title" -j
# => {"file": {"id": "...", "mimeType": "...", "name": "...", "webViewLink": "..."}}
# The id is nested under .file.id — NOT a top-level "documentId"/"id" field.

DOC_ID="<paste the id from .file.id>"

# 2. Insert the markdown content — gog converts markdown to native Google Docs
#    formatting (headers, bold, links, code blocks) in one call.
gog --account "$ACCT" docs insert "$DOC_ID" --markdown --file /path/to/doc.md -j
# => {"atIndex": 1, "documentId": "...", "inserted": <chars>, "markdown": true, "requests": <n>}

# 3. Verify it landed
gog --account "$ACCT" docs get "$DOC_ID"
```

`docs insert` also accepts `--index` for positional inserts and `-` via
`--file -` for stdin instead of a file path.

## Pitfall: don't assume gog's JSON shape matches gws's

The bundled `google-workspace` skill's Python wrapper (`gws`/`google_api.py`)
returns `{status: "created", documentId, title, url}` for doc creation. `gog`
is a different tool with a different JSON contract — `docs create` returns
`{file: {id, mimeType, name, webViewLink}}`. If a one-liner that pipes
`gog ... create -j` into `json.load(...)["documentId"]` fails, that's why —
parse `.file.id` instead. Don't cross-apply field names between the two
tools.

## Full lifecycle: local scratch file → gdoc → cleanup

When the ask is "put this in a gdoc, not a local file" (i.e. the gdoc is the
deliverable, not a mirror of a repo file):

1. Create the doc, insert the markdown content, verify with `docs get`.
2. Delete the local scratch file (and its now-empty parent dir if it was
   created solely to hold that file) so nothing lingers in the repo/working
   tree — the gdoc is the sole copy, not a duplicate.
3. Hand back the `webViewLink`/edit URL, not the file content — the user
   asked for the doc, not a summary of it.

## Iterative find/replace edits on an existing doc

`docs edit <docId> '<find>' '<replace>' -j` does a literal find/replace and
returns `{find, replace, replacements}` — check `replacements` is 1 (or the
expected count), not 0, before assuming the edit landed. This is the right
tool for trimming fluff / fixing a typo / tightening wording across several
small spots in a doc that already exists, one call per distinct change.

Pitfall: `docs get <docId>` returns doc metadata, not body content — there is
no clean "diff the whole body" or "replace the entire body in one call" path
via `docs get` + `docs edit`. For a full-body rewrite (e.g. "cut half the
doc, restructure"), it's more reliable to: write the new markdown to a local
scratch file, `docs create` a fresh doc, `docs insert --markdown --file` the
new content in, verify with `docs cat`, then `gog drive delete <old-id>
--force` the old doc (delete without `--force` refuses non-interactively)
and hand back the new doc's URL. Don't try to force a targeted find/replace
to do a structural rewrite — it gets fragile once wording shifts.

**Pitfall — `docs update --file` inserts markdown literally; it does NOT
render it.** Only `docs create <title> --file <md>` (on doc creation) and
`docs insert --markdown --file <md>` (on an existing doc) convert `#`/`##`/
`- ` into real headings/bullets. `docs update <id> --file <md>` (used to
patch/replace a range on an existing doc) inserts the raw markdown text
verbatim — the doc ends up showing literal `#`, `##`, `- ` characters
instead of formatted headings and lists. If you need to push fresh markdown
content into a doc that already exists, don't reach for `docs update` —
either use `docs insert --markdown --file` at the target index/range, or
(simpler, and the reliable path for a full-body swap) recreate: `docs create
--file` a new doc from the markdown (renders correctly), verify with
`docs cat`, then `gog drive rm <old-id> --force` the broken one and hand
back the new URL. Don't try to "fix" a literally-inserted-markdown doc with
more `docs update` calls — recreate it.

## Writing docs that cite code (proposals, scoping docs, RFCs)

When a doc quotes or references source code as evidence:

1. **Verify the citation is literal before writing it.** Read the actual
   file/line range with the read tool first. Never paraphrase what a prompt
   or function "effectively says" and present it in the doc as if it were a
   quote — the user will check, and catching a fabricated quote is a hard
   correction, not a stylistic nit.
2. **Attach a GitHub permalink to every code citation**, not just a bare
   `path:line` string: `git rev-parse HEAD` for the current SHA, build
   `https://github.com/<org>/<repo>/blob/<sha>/<path>#L<start>-L<end>`, and
   fold it into the citation text (e.g. `agents/foo.py:149-156 (<link>) —
   ...`) so every claim is one click from its source.
3. **Inline external links** (a mentioned tool/repo, e.g. a suggested
   library) directly next to the name — `beads (https://github.com/...)` —
   rather than leaving it as a bare parenthetical or a separate reference.

## Drive is mounted locally — prefer filesystem edits, but verify completeness first

When Drive is mounted on the local filesystem (path visible via macOS —
typically `/Users/<user>/Library/CloudStorage/GoogleDrive-<account>/`), a
batch edit across many files/folders (e.g. rewriting a heading in every
`script.md` under a folder) is much simpler done as a plain filesystem walk
+ edit than via `gog drive download`/`upload` round-trips per file.

**Pitfall — the local mount can silently be a partial view of the target
folder.** A folder name that looks right under `My Drive/...` may actually
be a different, older folder, or reachable only via a shortcut-target path
that mirrors just a subset of the real folder's children (seen: a shortcut
mount showing 16 subfolders when the real Drive folder — confirmed via
`gog drive ls --parent <id>` — had 168). Before trusting a local-mount path
as the batch target:

1. Get the true child count from the API: `gog --account <acct> drive ls
   --parent <folder_id> --plain --max=500` (paginate on `--page` if there's
   a "Next page" token), and count entries.
2. `ls` the candidate local-mount path and compare counts. If they don't
   match, the mount path is not authoritative — do not batch-edit through
   it. Either find the correct mount path (check for multiple candidates:
   direct path, shortcut-targets folder, shared drives) until counts match,
   or fall back to the `gog drive` API path for the whole job.
3. When in doubt, drive the batch by folder ID from the API listing (ground
   truth), not by a filesystem path you found by guessing/searching.

Only use the filesystem-walk shortcut once the mount is confirmed to expose
every item the API reports for that parent id.

## Batch rewrite of many Drive files via the API (resumable, idempotent)

For a "rewrite field X in every Y under folder Z" job scoped by Drive
**folder ID** (not a local path) — e.g. rewriting the title-heading lesson
id in every `script.md` under N subfolders — the reliable pattern is:

1. **Enumerate ground truth**: `gog --account <acct> drive ls --parent
   <folder_id> --plain --max=500`, following `--page <token>` until no
   "Next page" line remains. Save the full subfolder list (id + name) to a
   scratch TSV — this is the authoritative work list, not anything derived
   from a local mount guess.
2. **Per folder**: `gog drive ls --parent <subfolder_id>` to find the
   target file id, `gog drive download <file_id>` to a scratch dir, edit
   the specific line/field in Python (never touch anything else — diff
   before/after to confirm exactly one line changed), run any available
   parser/validator against both before- and after-content and require
   `new_violations == []` before uploading, then `gog drive upload --replace
   <file_id> <local_path>` (preserves the file id and any sharing links —
   this is the flag that matters; a plain re-upload would create a new id).
3. **Make the run resumable and idempotent.** Append one JSON record per
   folder to a `results.jsonl` (`{folder_id, folder, action, ...}`) as you
   go, with `action` one of `renamed` / `already-suffixed` (skip, no-op) /
   `no-<file>` (nothing to edit — record and move on, don't fail the batch).
   On every run (including retries after a kill/timeout), load
   `results.jsonl` first and skip any folder id already recorded with a
   terminal action — this lets a long batch be killed and re-launched
   without redoing work or double-uploading.
4. **Run long batches in the background** (`terminal(background=true)` +
   `process` poll/wait), since N folders × 2-3 `gog` calls each is minutes,
   not seconds, and a foreground call will hit the tool timeout.
5. **Verify at the end** by loading `results.jsonl` and checking: total
   record count == expected folder count, `Counter` of `action` values sums
   to that total, and every `renamed` record has `uploaded: true` and no
   `new_violations`. Report the action breakdown, not just "done."

## Writing bug/issue handoff reports (for another dev to investigate)

When the ask is "write up this issue in a doc" for a teammate to pick up
(not a design/scoping doc, not a status update) — keep it to bare
confirmed facts only:

1. **State the issue + the exact evidence** — the specific file/lesson/id
   affected, the missing/wrong artifact, and a verbatim log extract (with
   timestamps) that shows it. Nothing more.
2. **Link to the source** (job log path, CloudWatch stream, PR, etc.) so
   the recipient can pull the rest themselves.
3. **Cut everything else**, specifically:
   - Root-cause theorizing/diagnosis beyond what's directly confirmed in
     the evidence — "the pipeline probably..." reads as guessing to a
     dev who will investigate it properly themselves.
   - Restating domain facts the team already knows (e.g. "MCQ popups
     don't have a solution step" is common knowledge to this team — do
     not explain it in the doc).
   - Aggregate stats/counts derived from a broad heuristic scan unless
     they were independently confirmed against the actual data model
     (a raw file-count comparison across interaction types can look like
     a systemic trend but actually just reflects which interaction types
     legitimately don't emit that artifact — verify against the schema,
     not just presence/absence counts, before asserting a trend).
   - Framing/explainer paragraphs, caveats, or "what this means" sections.
4. If an earlier draft over-explained, don't patch it with `docs update`
   (see the literal-markdown pitfall above) — recreate clean via `docs
   create --file` and delete the old one.

## Other gog nouns available (not yet exercised in depth here)

`gog drive ...`, `gog sheets ...`, `gog gmail ...`, `gog calendar ...` follow
the same `--account` + `-j`/`-p` + per-verb `--help` pattern. Extend this
skill with a `references/` note if a session works through one of those in
enough depth to be worth capturing.
