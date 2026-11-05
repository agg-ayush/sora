# Orchestrator admin API (book / cancel / reschedule / override)

The admin API is token-gated. Token file: `~/.ti-hiring-admin-token` (0600, mirrors the live `/ti/orchestrator/ADMIN_TOKEN` SSM parameter). Never print the token value.

## Command

```
ti-hiring-admin.sh <method> <path> [json-body]
```

On 401/403 refresh from SSM and rewrite the file, then `chmod 600`:
`aws --profile trilogy --region ap-south-1 ssm get-parameter --name /ti/orchestrator/ADMIN_TOKEN --with-decryption --query Parameter.Value --output text > ~/.ti-hiring-admin-token`

The admin token is also accepted for operator-scoped routes; use `/ti/orchestrator/OPERATOR_TOKEN` (same SSM pattern) for a dedicated operator token.

## Operations

- **Book**: `POST /v1/sessions {candidateEmail, candidateName, scheduledStartAt, durationMinutes, assignment, idempotencyKey}` → 201/202, then poll `/v1/scheduling-attempts/:key/status`. Make exactly ONE POST per idempotency key and persist its result before continuing; the scheduler/sweeper owns transient Meet-pacer deferrals. Never resend while an attempt is non-terminal — `status: failed` with a future `nextAttemptAt` is still retrying. Before issuing a fresh `-rN` key, GET each original key's live status: snapshots go stale, and `committed`/`failed` with a future `nextAttemptAt` is not terminal.
- **Get**: `GET /v1/sessions/:id`.
- **Terminate**: `POST /v1/sessions/:id/override {"action":"force_destroy","reason":"..."}` (works from ready; post-freeze rows need the retention sweep or a freeze-aware override).
- **Cancel (pre-join)**: `POST /v1/sessions/:id/cancel {}`.
- **Reschedule**: `PATCH /v1/sessions/:id {"scheduledStartAt":...}`.

## Re-fire a booked session's locked invite email

1. Confirm the right session first: `GET /v1/sessions/lookup?email=<URL-encoded-email>` — check name and start time.
2. `PATCH /v1/sessions/:id {"candidateName":"<exact name>","sendEmail":true}` — the name is required for the mail.
3. The helper appends `[http NNN]` to stdout on its own line; strip it before parsing JSON and check the HTTP status.
4. **Never infer delivery from a successful PATCH.** Verify with `gog --account <ops-mailbox> --client startgreat gmail search 'in:sent to:<email>' --max 3` (load `GOG_KEYRING_PASSWORD` from `~/.hermes/.env` first). Check the DATE column — older mail to cancelled sessions is stale. Pace Gmail searches ≥12s apart; back off 90s on quota 403.
5. If PATCH fails, preserve the full output and retry at most once after 60s. A successful PATCH can coexist with no sent-mail record when the async mail queue is stuck — report that honestly instead of repeating the PATCH.

## Recover a terminated session's missing workspace capture

- First read `/v1/sessions/:id/detail` for `sandbox_id`, `infra_capture_s3_uri`, and status. **Never invoke `/v1/admin/reconcile` to recover capture** — its sweeps include destructive orphan-sandbox cleanup and it does not mint workspace archives. `retry_upload` in the override route needs an existing spool and is not a capture route.
- When no non-destructive API route can mint the capture, use the Vercel sandbox command API on the verified running sandbox. Read `/ti/orchestrator/VERCEL_TOKEN` from SSM into a private process variable; never print or log it. `POST https://api.vercel.com/v2/sandboxes/sessions/{vercelSessionId}/cmd?teamId=<team>` with `{"command":"sh","args":["-c","cd /workspace && tar czf /tmp/workspace.tar.gz --exclude node_modules . && base64 -w0 /tmp/workspace.tar.gz"],"wait":true,"logs":true}`. The response is `application/x-ndjson`: concatenate `data` from records where `stream` is `stdout`, require final `command.exitCode == 0`, base64-decode and validate the gzip tarball. Never print its full stdout/base64.
- Check an existing capture's real key before upload — the production layout is `s3://ti-hiring-captures-<aws-account>/captures/ti-ses-{uuid}/ses_{uuid}.tar.gz` (dash form, not a `ses_<uuid>/workspace.tar.gz` suffix). Confirm the target key doesn't exist, upload with `aws s3 cp`, then verify nonzero `s3api head-object` ContentLength and the exact `aws s3 ls` key. Clean up local archives after verification.
- The S3 upload alone does **not** populate `infra_capture_s3_uri` or the candidate-facing `infraCapture`. Read `/v1/sessions/:id` back; if null remains, hand off the URI for a separately authorized DB/API backfill. Never destroy a restored sandbox as part of capture rescue.
