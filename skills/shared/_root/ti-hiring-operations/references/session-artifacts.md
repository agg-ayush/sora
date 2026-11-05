# Session artifacts: what goes to Drive and how to change it

Standing design decisions for infra (sandbox-backend) sessions. Check these before proposing or carding any change to the capture/teardown/Drive pipeline.

## Settled design
- Workspace capture stays at its S3 URI. Never pull from S3 to push into Drive; the round-trip is waste. The DB row records the URI and the summary links to it.
- The Recall recording stays on Recall (7-day retention is acceptable). Uploading the video to Drive is optional behind an orchestrator env flag that defaults to off; the prod task definition does not set it. With the flag off, the video leg records a skipped status/event and never sets `finalize_error`.
- Drive gets one `<sessionId>-summary.json` per session with a durable capture: the full reviewable session metadata from the DB row plus events (timeline, candidate notes including trouble/concern notes, artifact links, capture reference, Recall bot id, teardown/video status). Secrets (SSH info, keypairs, idempotency keys, claims) are excluded.
- Candidate notes (trouble-exit note, submit-with-concerns) live in the DB first; the summary JSON is how they reach Drive.

## Rules for changes
- `finalize_error` is reserved for failures that lose candidate work (capture, destroy). Any auxiliary leg (video, summary, transcript) must record its own status/event and alert, never set `finalize_error`, and never gate teardown completion. Otherwise the candidate UI shows the generic error screen and blocks orthogonal paths like submitting concerns.
- An auxiliary leg must re-read the row or resolve dependencies on demand (e.g. create the Drive folder), not trust the row read at teardown claim time; a sibling leg may create the dependency later in the same teardown.
- When the user says a leg is no longer needed, the default implementation is an env flag defaulting to off, not deleting the code path, unless they ask for removal. Name the flag in the PR body.
- When explaining what a PR does to a leg, quote the PR body to distinguish "made non-blocking" from "removed"; the user asks precisely which one.
- The summary JSON is a snapshot taken at teardown, and teardown can finish before the candidate submits the concerns form (Finish freezes the row, capture/summary run within seconds, the concern POST lands later). Any change to the summary leg must re-upload or patch the summary when a candidate note arrives after it was written; otherwise the concern is in the DB but missing from Drive.

## Verifying a candidate note reached the DB and Drive
When asked "did my concern go through" or "did the teardown JSON land":
1. Admin `GET /v1/sessions/<id>/detail` and filter `events` for `concern_submitted` / trouble events: the note text is in `detail_json.note`. The row's `concernNote`/`setupTroubleNote` fields can read null while the event holds the note, so check events before calling it lost.
2. Find `session_summary_uploaded` in the same events: `detail_json.fileId` is the Drive file. Download it (`gog --account ayushaggarwal018@gmail.com drive download <fileId> --out <scratch>.json`) and read it; never report the summary as complete from the event alone.
3. Compare timestamps: if the concern event is later than the summary upload, report that the note is safe in the DB but missing from the Drive JSON (ordering gap), not that the summary is broken.
4. State both answers separately: DB (yes/no, with the event timestamp and text) and Drive (landed/complete, which fields are present, and whether the note is in it).
