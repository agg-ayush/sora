# Drive batch operations

## Prefer the API as ground truth over the local mount

When Drive is mounted locally, a filesystem walk beats per-file
download/upload round-trips for a batch edit across many files — but the
mount can silently be a partial view of the target folder: a folder name that
looks right may be a different/older folder, or a shortcut-target path that
mirrors only a subset of the real children.

Before trusting a local-mount path as a batch target:

1. Get the true child count from the API:
   `gog --account <acct> drive ls --parent <folder_id> --plain --max=500`
   (paginate on `--page` until no "Next page" token remains) and count entries.
2. `ls` the candidate local-mount path and compare counts. A mismatch means
   the mount is not authoritative — do not batch-edit through it. Find the
   correct mount path (direct path, shortcut-targets folder, shared drives)
   until counts match, or run the whole job through the `gog drive` API.
3. Drive batches by folder ID from the API listing (ground truth), never by a
   filesystem path found by guessing or searching.

Use the filesystem-walk shortcut only once the mount is confirmed to expose
every item the API reports for that parent id.

## Resumable, idempotent batch rewrite of many Drive files

For a "rewrite field X in every Y under folder Z" job scoped by Drive
**folder ID** (not a local path):

1. **Enumerate ground truth**: `drive ls --parent <folder_id> --plain
   --max=500`, following `--page <token>` until exhaustion. Save the full
   subfolder list (id + name) to a scratch TSV — the authoritative work list,
   not anything derived from a local-mount guess.
2. **Per folder**: `drive ls --parent <subfolder_id>` for the target file id,
   `drive download <file_id>` to scratch, edit exactly the target field in
   Python (diff before/after — exactly one line changed), run any available
   parser/validator against before- and after-content and require
   `new_violations == []` before uploading, then
   `drive upload --replace <file_id> <local_path>`. `--replace` preserves the
   file id and sharing links — a plain re-upload mints a new id.
3. **Make the run resumable and idempotent.** Append one JSON record per
   folder to `results.jsonl` (`{folder_id, folder, action, ...}`) with action
   `renamed` / `already-suffixed` (skip, no-op) / `no-<file>` (nothing to
   edit — record and move on, don't fail the batch). On every run including
   retries after a kill/timeout, load `results.jsonl` first and skip folder
   ids already recorded with a terminal action, so a long batch can be killed
   and relaunched without redoing work or double-uploading.
4. **Run long batches in the background** (`terminal(background=true)` +
   `process` poll/wait): N folders × 2-3 gog calls each is minutes, not
   seconds, and a foreground call hits the tool timeout.
5. **Verify at the end** by loading `results.jsonl`: total record count ==
   expected folder count, the `Counter` of action values sums to that total,
   and every `renamed` record has `uploaded: true` and no `new_violations`.
   Report the action breakdown, not just "done".
