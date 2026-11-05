# Eval review: pulling reports/captures and serving a filtered review list

Use when Ayush wants a batch's transcript-eval results filtered and served for review (list page + per-candidate viewer + rendered prompts).

## Sources
- Eval reports live in the GCS eval bucket (one report.json + triage.json per candidate/assignment). If `gcloud`/`gsutil` needs interactive re-auth, use the transcript-eval repo's own Node GCS client (`NODE_PATH=<repo>/transcript-eval/node_modules node <script>`), which already has working creds. Cache locally once, then serve from the cache.
- A batch is the full session set from the admin API (hundreds), not just the rows where someone hand-filled an eval column in the sheet. Check the sheet's full row count before filtering.
- Session captures (prompts.txt etc.) are in S3 under the prefix `ti-ses-<uuid>`: strip the `ses_` from the session id. Building `ti-` + `ses_<uuid>` gives a key that does not exist and returns 404 on every object.
- On an S3 404/AccessDenied, `aws s3 ls` the parent prefix first to confirm the key exists before suspecting credentials. A 404 on a wrong key looks exactly like flaky auth; retry-grinding it wastes the session. If creds really expired, run the aws-creds-refresh script once, then re-test.

## Filtering
- Each candidate may have two eval runs (focused and combined). Default rule Ayush settled: per rubric signal take best(focused, combined), then keep candidates where all three signals are at least mixed/yellow. Show the per-signal chip that won.
- Manually added candidates (rows added by hand at the bottom of the sheet) may be missing from the session list or the filter; include them explicitly when asked and say which rule each extra failed.

## Serving
- Two viewer versions exist in transcript-eval. The main-branch viewer has a sidebar list and boots from hash URLs `#<candidate_id>/<assignment_id>`; the newer working-copy viewer is single-candidate and reads `?candidate_id=&assignment_id=` query params with no list. Check both before claiming a capability is missing, and check which one is running before building links; a query-param link into the hash viewer shows the empty drop-files page.
- Layout Ayush wants: port 8787 is the filtered list (front door, filtered set only, never all reports), with per-row buttons opening the viewer on 8788 and a "Prompts" button opening a rendered prompts page; Ayush reaches both via an SSH tunnel from his laptop. Put features on the server itself (buttons, list rows), not as link lists pasted into chat.
- Prompts page: header with candidate name/email/assignment, each prompt as a numbered, readable block (not a raw text dump).
- Each list row also carries the candidate's Recall bot id (from `/v1/sessions/:id/detail` `recall_bot_id`; the list shape lacks it) as a hyperlink to `https://ap-northeast-1.recall.ai/dashboard/explorer/bot/<id>?order=desc&experience=new`, opening in a new tab.

## Operating
- No long sleeps or long-timeout waits. Run downloads in the background with notify, keep working on independent parts (filter, viewer config) meanwhile.
- Verify each server with a curl of the actual page/row count before telling Ayush it's up.