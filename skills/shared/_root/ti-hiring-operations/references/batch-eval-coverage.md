# Batch eval report coverage

1. `gog sheets info <sheetId>` lists the tabs. Read the college tab with `--tsv`, since `-j` can come back empty for a tab that has data. "No data found" on `Q2:V` means nobody backfilled Q-V for that tab.
2. Column P (`ADD start (IST)`) holds the batch slots. Convert to UTC, pull sessions via `ti-hiring-admin.sh GET '/v1/sessions?limit=2000'` and filter on `scheduledStartAt`. Completed = `timer`/`candidate_done`. Terminated = `forfeited`, `ready_expired_media_gate`, `admin_force_destroy`, `cancelled`.
3. Check each completed SID for `transcript-eval/cache/<SID>/<ASG>/report.json` in GCS.
4. If you get `invalid_grant`/`invalid_rapt`, the ADC is past its reauth window. Ask the user to run `gcloud auth login --update-adc` and don't retry.
