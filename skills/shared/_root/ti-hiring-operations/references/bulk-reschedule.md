# Bulk reschedule of booked sessions

Use when moving a set of candidates out of their booked slots (e.g. wrong-email corrections, batch moves). Invites/booking emails are often handled separately: pass `sendEmail:false` unless told otherwise.

## Procedure
1. Identify candidates by NAME (roll number / email fragment as backup), never by email alone: in wrong-email cases the sheet email and the corrected email differ by definition. Pull sheets as a JSON grid, not TSV (multi-line cells shift TSV rows).
2. `GET /v1/sessions?limit=2000` via `ti-hiring-admin.sh` returns several concatenated JSON docs plus `[http...]` log lines: drop the log lines, decode with `json.JSONDecoder().raw_decode` in a loop, flatten lists. Match ids by full id or `startswith(prefix)`; an exact-match lookup on a prefix you printed truncated earlier silently returns zero.
3. List ALL sessions per candidate and take the one in `scheduled`. A session already `ended`/`terminated` for the current batch cannot be PATCHed forward; it needs a fresh `POST /v1/sessions`.
4. Build an occupancy table (`scheduledStartAt` x status) for future slots before choosing targets. Waves are ~84 each, 45 min apart, batch N = Nth wave of the day; the earliest wave may already be running. Unless the user named an exact time, present target options with occupancy and let them pick; never overfill a wave on your own judgment.
5. `PATCH /v1/sessions/:id {"scheduledStartAt":<UTC ISO>,"sendEmail":false}`. Patchable fields are only scheduledStartAt, durationMinutes, assignment, candidateName, sendEmail; `candidateEmail` is not patchable, so fixing the email itself requires a fresh booking.
6. Verify with a fresh sessions read. Echo IST and UTC for every time.
