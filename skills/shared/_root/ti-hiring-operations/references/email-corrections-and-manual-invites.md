# Corrected-email cohorts and manual invites

Use when candidates report a wrong email in their application (correction form/survey) and need rescheduling + fresh invites.

## Procedure (in this order, one confirmed step at a time)
1. **Map survey -> batch sheet by NAME, not email.** The batch sheet holds the WRONG email by definition; email matching reports false "not in sheet". Normalize names (case, spacing, partial/initials), use email/roll only as a tiebreak. Pull the sheet as a JSON grid, never TSV line parsing: multi-line cells shift rows.
2. **Show the mapping as plain text and stop.** Name, correct email, original batch/row. When the user says "show me"/"map"/"simple textual", do zero API calls.
3. **Classify against ORIGINAL bookings**, not post-patch state: already ran / original slot before the cutoff batch / already in later batches / never booked.
4. **Fix the email before (or together with) any slot move.** A slot reschedule on a session that still carries the wrong email is useless. Cleanest path: cancel the old sessions, re-book fresh with the corrected email.
5. **Present the full target list (name, email, batch) and wait for approval** before booking. Batch capacity is not a constraint unless the user says so.
6. Book with `sendEmail` exactly as the user specifies. The default is false: moving slots and sending invites are separate decisions, so never send because a booking happened. Verify by direct per-session lookup (the list endpoint is flaky); bookings can sit as "scheduling attempt" under the pacer and commit later. Re-check those individually rather than rebooking.
7. Verify delivery in the startgreat Sent folder (`gog --account <ops-mailbox> --client startgreat gmail search 'to:<email> newer_than:1d'`), searches ~12s apart; quota throttling is common, run it as a background subagent, never foreground sleeps.

## Manual invite fallback
If orchestrator sends don't land (re-firing via session PATCH `sendEmail: true` can return 200 without delivering), send manually from startgreat:
- Pull the **HTML** block from the locked mail template doc (`gog --account ayushaggarwal018@gmail.com docs cat <internal-doc-id>`), fill `{candidate_name}`, `{assessment_date}`, `{assessment_start}`, `{assessment_end}`, `{join_deadline}` (start+10 min, IST).
- Send with `gog --account <ops-mailbox> --client startgreat gmail send --to <email> --subject 'TI Assessment: your technical assessment' --body-html-file <file>`. Never `--body` plain text: the user rejects barebones mails; the styled card + button is required.
- Dry-run once (`--dry-run`), then run the loop as a background process with notify (13s pacing), stop on first failure, keep an already-sent skip set so a resume never double-sends.
- Link is the bare site URL only.

## Status questions mid-operation
- "Are these on the new mails?" / "booked already?" / "mails sent?" get a yes/no first line, then at most one line of detail. Answer from state you already have. Don't start a new multi-call investigation before replying.
