# Scheduling intake API (batch booking)

Use for any batch of candidate bookings. A batch script should be a thin producer (sheet -> deduped rows -> intake), never a client-side loop that creates sessions and mails candidates itself.

## Call
`POST /v1/scheduling/intake` with `{ "rows": [...] }`, admin/operator token, max 500 rows per call. Response is per row: `rowRef`, `status` (`accepted` | `rejected` | `replay`), `error`.
Status afterwards: `GET /v1/scheduling/status?rowRefs=a,b,c`.

## Row fields
- `rowRef` (unique key), `op` (`upsert` | `cancel`), `email`
- `name`: required when `sendEmail` is true
- `scheduledStartIst`: `YYYY-MM-DD HH:mm`, 24h IST. The API converts to UTC; do not pre-convert.
- `durationMinutes` (optional), `assignment` or `assignments` (not both; random pick when omitted)
- `sendEmail`: explicit boolean. Ask the user the batch default before submitting.
- `rowVersion`: idempotency key is `sheet:<rowRef>:<rowVersion>`; bump it to resubmit an edited row.

## What the server does per accepted row
Skips the row (noop + alert) if the candidate has an active or direct session or an in-flight direct attempt; resolves the assignment; creates the session; books the Meet space plus Calendar event (the calendar invite carries the Meet link); times the Recall bot; sends the invite mail through the paced Gmail path when `sendEmail` is true; retries with backoff, dead-letters after max attempts, defers rows that hit the Gmail daily cap to the next UTC day.

## Pitfalls
- Diff the server invite body (`buildInviteEmail`, `orchestrator/src/scheduling/session-ops.ts`) against the locked invite template doc before relying on it; the built-in invite has lagged the template. Flag the gap rather than claiming the API sends the template.
- Dedup across alternate emails before building rows (merge by phone or name+college), since candidates register with one inbox and join with another; each distinct email gets its own session otherwise. Log merges for the user.
- Keep scripts college-agnostic: sheet link and college as inputs, nothing hardcoded.
- Old per-college batch scripts predate both this API and the current template; check them against both before reuse.
