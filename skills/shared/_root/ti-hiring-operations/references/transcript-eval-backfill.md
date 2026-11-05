# Transcript Eval Backfill

Source: remote `ti-hiring-transcript-eval-backfill/SKILL.md`; frontmatter/title/scope wrapper removed.


Use for dispatching transcript eval jobs from captured TI hiring assessment sessions, especially batch backfills with pre-existing GCS captures.

- Deduplicate plan rows by `sid`: one execution per distinct session, not per row.
- For `gs://<gcs-bucket>/transcript-eval/captures/<SID>/capture.tar.gz`, calculate SHA-256 over downloaded object bytes. From `/home/ubuntu/ti-hiring/transcript-eval`, use `@google-cloud/storage` `createReadStream()` and Node `crypto.createHash('sha256')` to avoid local large tarballs.
- For a single execution, fire with `gcloud run jobs execute transcript-eval-eval --project ti-hiring --region us-east1 --update-env-vars "CANDIDATE_ID=<SID>,ASSIGNMENT_ID=<SLUG>,SESSION_ID=<SID>,CAPTURE_OBJECT=transcript-eval/captures/<SID>/capture.tar.gz,CAPTURE_DIGEST=<SHA256>"`. `SESSION_ID` must be set. Sequentialize gcloud calls: concurrent job-level `--update-env-vars` changes can mix session identities.
- For bounded parallel backfills when the operator explicitly authorizes an equivalent dispatch path, POST Cloud Run v2 `projects/<PROJECT>/locations/<REGION>/jobs/<JOB>:run` with per-execution `overrides.containerOverrides[0].env`. This isolates each session's env, avoids the shared-job update race, and is much faster than the gcloud CLI. Limit unsettled executions to 10 on the small VPC subnet (or 5 if free-IP errors appear), use short foreground waves, and persist each returned execution ID immediately. Never retry a session with an ID; reconcile ambiguous acknowledgements against Cloud Run execution inventory first.
- Parse the ID from `gcloud run jobs executions describe transcript-eval-eval-XXXXX` in the gcloud output, or the v2 operation metadata name. Read back each execution (`gcloud run jobs executions describe <EXEC> --project ti-hiring --region us-east1 --format=json`) and compare all five environment fields in `spec.template.spec.containers[0].env`. Do not wait for completion if dispatch alone was requested.
- Persist the digest, slug, ID, and exact errors after each step so interruptions do not cause duplicate executions. On gcloud authentication errors, stop rather than requesting an interactive login; continue other sessions after isolated errors. Keep each download and execute invocation under ~90 seconds.

## Read-only completion checks

- Treat the persisted session-to-execution map as authoritative. Describe each execution with `gcloud run jobs executions describe <EXEC> --project ti-hiring --region us-east1 --format=json`: `status.conditions[type=Completed].status=True` with `succeededCount` means success; `False` or `failedCount` means failure; otherwise it is still running. Poll in small parallel batches and never re-execute failures while monitoring.
- Read reports at `gs://<gcs-bucket>/transcript-eval/cache/<SID>/<ASG>/report.json`; the three signal/pattern pairs are in `focused.findings`, with `focused.abstained` and possibly `focused.abstain_reason`. A successful execution should still be checked for a real report object.
- For failed execution logs, filtering `labels."google.cloud.run.job_execution"` can return zero results even when logs exist. Use the execution's `status.logUri` filter, which here is `resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="<EXEC>"`; read stderr `textPayload` and quote the actual failing line rather than the generic container exit message. On exit(2), stderr can be empty except `Container called exit(2).`: fetch `transcript-eval/cache/<SID>/<ASG>/inspection.json` and use `issues[].message` verbatim (e.g. `sessions/ contains no transcript files`). A failed execution can still have a report.json (often an abstained report); keep execution status and report presence as separate facts.

## DTU sheet backfills

- Before every individual U or V write, freshly read `DTU!A1:V1000`, locate the unique session ID in Q (zero-based index 16), and use that current row. Row numbers shift when upstream sheet edits occur; a previously observed row is unsafe. Read back Q plus the target cell after writing.
- Do not assume the evaluation run map and the sheet are aligned: session IDs can be absent from Q even when their GCS reports exist. Never infer a row by candidate email or positional order when Q is absent; report the exact IDs as blocked instead of writing elsewhere.
- Validate report `candidate_id` and `assignment_id` against the sheet, then select the best pattern for each of `problem_ownership`, `question_quality`, `advice_seeking` across non-abstained `focused` and `combined` findings, ranking `mixed > not_exercised > does_not_show`. Only all-three-mixed earns `review`; otherwise `no`.
- If neither the local cache nor the exact GCS path contains a report, leave U/V untouched and report the missing report. A blank U/V pair alone does not prove the session was evaluated. Mirror downloaded reports into `<cache>/<SID>/<ASG>/report.json` and validate the complete inventory before reporting counts.
