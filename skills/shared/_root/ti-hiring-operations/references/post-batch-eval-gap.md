# Post-batch eval gap

A completed batch does not automatically get eval reports: teardown archives captures to S3, but nothing copies them into the GCS eval bucket or fires the Cloud Run eval. After a batch, verify before assuming reports exist.

1. List sessions via `/home/ubuntu/.local/bin/ti-hiring-admin.sh GET '/v1/sessions?limit=2000'`, filter by `scheduledStartAt` window. Only `ended` sessions need evals; `terminated` ones are labeled `forfeited`.
2. Compare ended sids against `transcript-eval/cache/<SID>/` (reports) and `transcript-eval/captures/<SID>/` (inputs) in `<gcs-bucket>`, and spot-check S3 `ti-hiring-captures-<aws-account>` key `captures/ti-ses-<uuid>/<sid>.tar.gz` (dash after `ti-ses`, never `ti-ses_`).
3. Backfill by S3 -> GCS copy, sha256, `gcloud run jobs execute transcript-eval-eval` (SESSION_ID always set), in waves of ~20, through a background subagent with a resumable state file. Never block the main chat on the copy/poll loop.
4. If the subagent's background process is SIGTERM'd, dispatch a new subagent to resume from the state file.
