# Eval backfill execution: copying captures and keeping work alive

## S3 capture path
- The S3 session directory prefix is `ti-ses-<uuid>` (dash). Derive it by stripping `ses_` from the session id and prefixing `ti-ses-`; naive concatenation (`ti-` + `ses_<uuid>`) yields `ti-ses_<uuid>`, which 404s on every object and masquerades as flaky SAML credentials. On repeated 404s, list the parent prefix before blaming auth.
- Refresh SAML creds (`/home/ubuntu/.hermes/scripts/aws-creds-refresh.sh`) before a copy wave.

## Execution model
- Main chat: no long foreground commands, retry loops or `sleep N` polls. The user objects to being blocked. Delegate any multi-minute backfill to a subagent and end the turn.
- Subagents: a long-lived backgrounded python driver gets SIGTERMed by parent cleanup. Drive the work in short bursts (each command under ~90s): fire a wave of ~20 Cloud Run executions, poll that wave in one batched describe loop, write results to a durable state file, repeat. Each burst resumes from the state file and skips any sid that already has an execution recorded, so a kill mid-wave never double-dispatches.
- Late SIGTERM/exit notices from a superseded subagent's helper are noise: read the state-file counts once, confirm the current owner is progressing, reply in one line.

## Sheet labeling (DTU-style tracking sheets)
- V labels: `review` (all three signals mixed, best of focused/combined), `no`, `empty_transcripts` (abstained, zero transcript files), `forfeited` (terminated forfeited/ready_expired_media_gate or never typed), `eval_error` ("rendered session has no candidate or assistant turns"; do not retry). Confirm the mapping with the user before bulk relabels.
- Count cells from a structured JSON grid read, never a TSV line scan: form cells with embedded newlines split lines and undercount.
- Locate every write by session id in a fresh read immediately before writing; upstream edits shift rows between read and write. Retry single-cell writes that hit the per-minute quota, then verify by fresh read.
