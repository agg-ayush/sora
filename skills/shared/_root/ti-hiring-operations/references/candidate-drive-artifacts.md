# Locating candidate Drive artifact folders

Use when asked for Drive links (recordings, uploads) for a set of evaluated candidates.

## Procedure
1. Start from the authoritative candidate set (e.g. the filtered eval cache `/home/ubuntu/eval-cache-strong/<email>/<assignment>/report.json`). Check the expected count before doing anything else.
2. Map email+assignment to `session_id` using the eval run's consolidated summary JSON (`results[].session_id`). `report.json` has no Drive/URL fields, so don't look there for links.
3. Each session has one Drive folder named exactly `ti-session-<session_id>`, owned by <ops-mailbox>, under parent folder `17HGj19r4jzW40N5vjc0NOaP7W5qUDj-j`.
4. Find it with `gog --account ayushaggarwal018@gmail.com drive search 'ti-session-<session_id>' --max 10 -j`, then filter client-side on exact name, folder mimeType and parent id. Require exactly one match per candidate and fail loudly otherwise.
5. Create the sheet with `gog sheets create '<title>' --sheets <Tab> -j`. Fill it with `gog sheets update <id> '<Tab>!A1:D<n>' --values-json @- --input USER_ENTERED` (pipe JSON rows on stdin). Then run `gog sheets get` and check the readback equals the rows written.

## Older sessions (no `ti-session-` folder)
Earlier sessions have loose files named `ses_<uuid>-recording.mp4`, `-prompts.txt`, `-review-comment.txt`, `-transcript*.jsonl`, `-workspace.tar.gz` in an unnamed per-session parent. If the `ti-session-` search is empty:
1. `drive search 'ses_<8-char-prefix>' --max 8` to find the files.
2. `drive raw <fileId>` (metadata JSON; `drive get`/`raw` do not return file bodies) and take `parents[0]`.
3. Share `<internal-doc><parentId>`; confirm contents with `drive ls --parent <parentId>`.
4. When resolving a candidate by first name, list every same-name candidate in the cohort and state which ones have artifacts.

## Sharing a folder with a candidate or external email
1. Confirm the owner first (`gog drive permissions <folderId> --account ayushaggarwal018@gmail.com`); only share folders Ayush's account owns.
2. `gog drive share <folderId> --to=user --email <addr> --role reader --account ayushaggarwal018@gmail.com -j`. Default to `reader` (view/download, no reshare); use `writer` only when asked.
3. Re-run `gog drive permissions <folderId>` and quote the owner + new grant rows as proof; the share call's JSON alone is not the readback.

## Candidate interview prep pack
When asked to help a candidate prep for their follow-up interview:
1. Pull `<session>-prompts.txt` from their Drive folder (or `scripts/extract_candidate_prompts.py`).
2. Pull the assignment from the orchestrator with the per-slug admin GET (`/v1/admin/assignments/<slug>`, admin token from SSM); the statement is in `statementMd`. Save the JSON to the scratch dir and extract with python rather than truncating curl output.
3. Write one markdown pack: assignment statement, full prompts transcript verbatim, then 4-6 prep focus areas grounded in what they actually decided in the transcript (bug mechanism, design choices and the why behind each, what their verification does and does not prove). No verdict, scores or eval content.
4. Send it as a `MEDIA:` attachment with a short message addressed to the candidate. Everything upstream stays read-only.

## Pitfalls
- Artifact presence is not a verdict. Say so explicitly if you didn't read `review-comment.txt` or the review JSON.
- Local eval caches don't hold every report, so check Drive before calling artifacts missing.
- Search unscoped and check `parents` yourself. With `--parent <folderId>` added, `drive search` returned nothing for these folders even though unscoped search found each one under that exact parent.
- Don't page through `drive ls --parent` to find folders: the parent holds hundreds of session folders, so a targeted name search is faster.
- Check that candidate emails and folder URLs are both unique before writing, so a duplicate mapping can't reach the sheet.
- Sheet columns: candidate email, assignment, session ID, Drive folder link. Keep it minimal unless asked for more.
