# Session booking, reconciliation and candidate monitoring

Read before booking sessions (single or bulk), reconciling bookings against a sheet, or answering how the team finds out about candidate issues.

## Booking
- Individual booking is `POST /v1/sessions` through the admin helper. It works whether or not the scheduling intake route is enabled, so use it when intake is unavailable.
- A booking can return `status: pending` with no session id because the meet/recall pacer deferred it. Poll `/v1/scheduling-attempts/<key>/status` until `committed` (a leftover `lastError` on a committed attempt is harmless). Then find the session with `GET /v1/sessions?email=<email>`, filtered to `scheduled`/`active` near the requested start. Don't re-POST while the attempt is still being retried.
- The scheduler/sweeper owns retries for bulk runs. Send one POST per idempotency key and let the sweeper handle deferrals, rather than having a subagent retry the Meet calls. An attempt shown as `failed` that still has a future `nextAttemptAt` is still retrying, not dead.
- Each candidate can hold only one active session, so a booking 409 means they already have one. For Ayush's own test sessions, force-destroy the old one and rebook without asking. For a student with duplicate sheet rows, keep one session. To switch it, terminate it and rebook; never double-book.
- Bulk booking for a cohort is mechanical work: give it to a subagent with a resumable manifest and log, and never re-send candidate mails unless told to.

## Reconciliation
- Compare start times as parsed instants, never as strings. The API returns `.000Z` suffixes, so a string compare reports false mismatches.
- Match emails case-insensitively, or booked students show up as missing.
- Report distinct students and sheet rows separately, because duplicate form submissions exist.
- Slot times with no meridiem: confirm AM or PM before booking (default zone is IST).

## Candidate issue monitoring
- Concern submissions and "I'm having trouble" exits are stored as `concern_submitted` and `trouble_exit` session events.
- The orchestrator has a DB alert outbox, but the production Notifier only writes to the logs. Nobody is pushed a notification by default.
- For real-time awareness in the short term, run a background watcher that polls the admin API for those events and pings Telegram. The durable fix is a push Notifier implementation (webhook, Telegram or Slack) plugged into the existing outbox.

## DB access
- The prod DB is in a private VPC with no direct access by design: all changes go through the orchestrator admin API, which prevents accidental changes. Giving anyone direct or read-only access means a security-group rule or making the DB publicly accessible, both shared-infra changes. Don't attempt them close to a live batch; offer admin API access (the stakeholder has the token doc) instead.
