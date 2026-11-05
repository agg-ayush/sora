# Eval review list + capture artifacts

Use when standing up a filtered candidate-review surface over transcript-eval reports, pulling per-session capture files (prompts, transcripts) from S3, running the GCP eval for a single late/added candidate, or answering "didn't we turn X off?" about teardown artifacts.

## Eval viewer
- Two viewer generations exist in the transcript-eval repo. Check the `main`-clean checkout first: it has a sidebar list and boots from hash URLs `#<candidate_id>/<assignment_id>`. The newer working-copy viewer is single-candidate by design and takes `?candidate_id=` query params. A link built for one does nothing on the other (shows the empty "drop report.json" page).
- Layout the user settled on: one port is the filtered list (front door), a second port runs the viewer; each list row links into the viewer and carries extra columns/buttons (prompts page, Recall bot link). Put links as buttons on the list server, not as chat-pasted URLs.
- Recall bot link format: `https://ap-northeast-1.recall.ai/dashboard/explorer/bot/<bot_id>?order=desc&experience=new`.
- Cache reports locally (download once from the GCS bucket via the repo's own client libs) and serve from the cache.

## Filtering on eval signals
- "The batch" means every session in the cohort, not only rows someone hand-labelled in the sheet. Confirm population size against the session list before filtering.
- When a candidate has both a focused and a combined eval, take per-rubric `best(focused, combined)` before applying the threshold unless told otherwise; surface disagreements to the user first.
- Manually added candidates (sheet rows outside the batch export) may lack a cached report; fetch theirs explicitly.

## S3 capture files
- The per-session capture prefix is `ti-ses-<uuid>` (dash). Session ids are `ses_<uuid>`; build the prefix by stripping `ses_`, not by concatenating `ti-` + the id (yields `ti-ses_<uuid>`, which 404s every time and looks like a credential flake).
- When an S3 fetch "intermittently" fails with admin creds, print the exact key requested before blaming creds or retrying.
- Refresh SAML creds with the aws-creds-refresh script on ExpiredToken; no long sleeps or retry loops.

## Adding one candidate to a cohort sheet + running the GCP eval ("infra lead's flow")
1. Fill the sheet row (session id, capture link, etc.) and read it back. When a cell value starts with `-` (e.g. a literal `---` placeholder), gog parses it as a flag; pass values via a JSON/file input or after `--` rather than as a bare positional.
2. Upload the session's capture tarball to the eval bucket under `transcript-eval/captures/<session_id>/` if it isn't there.
3. The GCP flow is the Cloud Run jobs driven by `transcript-eval/deploy/scripts/run.sh` (config in `deploy/config.env`; batch variant `run-batch.sh <candidates.csv>`). Read its usage block first: it has a GCS/repo mode (fetch job then eval job), a Drive-session mode (`SESSION_ID`, eval only), and the eval job (`dist/eval-main.js`) also accepts `CAPTURE_OBJECT` + `CAPTURE_DIGEST`. Pick the mode that matches where this cohort's capture actually lives, and confirm the digest format the acquire step expects in source before firing.
4. Executing an existing job with existing creds is a data operation; deploying/redeploying the job is control-plane and not agent-initiated.
5. gcloud on the box needs interactive re-auth periodically. When it does, ask the user once, in caps, to run `gcloud auth login --update-adc`, with the exact env/command ready to fire after. Settle the mode before messaging; don't think out loud in the ask.

## "Didn't we turn X off?"
Check three sources before answering: current code on origin/main (does a flag exist?), the live ECS task definition env (is it set?), and session_search for the original decision's exact scope. Remembered decisions are often narrower than recalled. Lead with yes/no, then the real scope, then offer a card for the broader change.
- Current facts (re-verify): teardown uploads the Recall video to Drive unconditionally, no on/off flag; what is gated off is storing/printing Recall's presigned download URL. Workspace capture stays in S3, no Drive copy.
