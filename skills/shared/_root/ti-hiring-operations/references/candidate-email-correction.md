# Candidate email-correction cohorts

Use when students report a wrong email from the application form and need re-slotting or re-inviting.

- Match survey respondents to batch-sheet rows by NAME first (normalized, letters only), with email/roll as backup. The batch sheet holds the WRONG email, so matching on email alone misses people and makes them look absent.
- Pull sheets as a JSON grid, not TSV. TSV breaks on newlines inside cells.
- Orchestrator sessions may sit under variant emails (personal gmail and college roll@iitism). When sweeping a cohort, match sessions on survey wrong email, corrected email, roll substring and candidateName.
- Before patching or rescheduling, snapshot each session's ORIGINAL scheduledStartAt to a file. PATCH overwrites it and the user will ask for the original picture later.
- Do not reschedule or rebook until the email fix is applied. Moving slots while the session still carries the wrong email defeats the purpose.
- Cancel endpoint: POST /v1/sessions/:id/cancel (admin auth, pre-join only, idempotent). Verify with a fresh GET /v1/sessions read: zero scheduled/live left for the cohort, endReason=cancelled.
- Batch slot times (Oct 2026 ISM cohort, UTC): B1 10:30, B2 11:15, B3 12:00, B4 12:45, B5 13:30, B6 14:15, B7 15:00. IST = UTC+5:30.
