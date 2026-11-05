# Prod ECS services and incident accounting

## Services in cluster `ti-orchestrator` (ap-south-1)
Before you scale any service down, check which live flows go through it. Confirm on live session data, not from the service name.

| Service | Role | Safe to stop? |
|---|---|---|
| `ti-orchestrator` | Browser-flow API plus the sweeper | Never |
| `ti-orchestrator-ssh` | Same image running the SSH flow. Its sweeper shares the DB and can claim browser-flow lifecycle work, which shows up as stuck `frozen` rows and finalize errors. | Only when active sessions show zero `flow=ssh`. Lower the autoscaling floor to 0 first, then set the desired count to 0. If you skip the floor change, ECS restarts the task. |
| `ti-orchestrator-ws-bridge` | Stateless terminal WebSocket proxy (`<internal-host>`). Every browser candidate's terminal tabs connect through it. It has no DB handle and cannot race the sweeper. | Never while sessions are live, because every candidate's terminals die |

## Counting lost work after an incident
Split the batch's rows by `endReason` and by whether an S3 capture exists. Do not count by status alone.
- Rows with `finalizeError` usually still have their capture. The work is safe and only the finalize or summary step is missing.
- Forfeit rows and `ready_expired_media_gate` rows had no workspace, so they had nothing to lose.
- Admin `force_destroy` rows are deliberate rebooks or cleanup.
- Candidate loss means a row that was joined and ready, ended with `ready_expired_teardown_incomplete` and has no capture. Do not report it as lost until you check the Vercel sandbox (below).
- Transcript `pending` is the normal async state, so it is not a loss signal.

## Checking a no-capture row's sandbox before you call it lost
A missing `infraCapture` in the DB does not always mean the workspace is gone. Each session's Vercel sandbox is a named sandbox; whether its state survived depends on whether a final-state snapshot exists (step 3).
1. Get the team and project ids from the stack: `aws --profile trilogy --region ap-south-1 cloudformation describe-stacks --stack-name ti-orchestrator` and read the `VercelTeamId` and `VercelProjectId` parameters.
2. Look up the exact sandbox with `mcp__vercel__list_named_sandboxes` (`project`=project id, `teamId`, `sortBy=name`, `namePrefix=ti-ses-<session uuid>`). Use the full session-id prefix: broad prefixes return 50-row pages that can skip the target. The raw REST list needs a `project` param, so use the MCP tool.
3. Read `status`, `persistent`, `currentSnapshotId` and the `ti-snapshot` tag. Check whether `currentSnapshotId` is a final-state snapshot or just the base assignment snapshot the sandbox booted from: fetch it with `GET /v1/sandboxes/snapshots/<id>` and compare its `createdAt` to the sandbox `createdAt` (a base snapshot predates the sandbox and has no `parentId` from this session). A stopped `persistent:false` sandbox discards runtime state on stop and has no resume path; its snapshot is only the starter image, so the work is gone. Only a snapshot created at or after stop holds candidate work.
4. Check `totalIngressBytes` and `totalEgressBytes`. Values of a few KB mean bake-time traffic only, so the candidate probably never worked in it. Say that before anyone spends time on recovery.
5. Recover read-only: restore from a final-state snapshot into a fresh sandbox, read or capture the files to S3, then write the capture pointer back. Non-persistent snapshots expire after about a week, so do this soon.
6. Inspect the restored sandbox through the REST command endpoint (token from SSM `/ti/orchestrator/VERCEL_TOKEN`):
   ```
   curl -s -X POST -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' \
     "https://api.vercel.com/v2/sandboxes/sessions/<sbx_id>/cmd?teamId=<team>" \
     -d '{"command":"sh","args":["-c","<script>"],"wait":true,"logs":true}'
   ```
   Pass `"logs":true` or the response carries only the exit code. The body is NDJSON; stdout arrives in `{"data":...,"stream":"stdout"}` lines.
7. The candidate workspace is `/workspace` (not `/vercel/sandbox`, which is empty) and home is `/home/vercel-sandbox`. Work happened only if files under `/workspace` are newer than its `README.md` or starter files changed, or `~/.claude/projects` is non-empty (Claude Code creates it on first run). Untouched starter plus no `~/.claude/projects` means the candidate never started (or, in a clone from a base snapshot, that the work was never snapshotted): report accordingly.
8. Recovery clones created via `mcp__vercel__create_sandboxes_v3` come up `persistent:true`, so stopping them auto-creates a snapshot. That is harmless (it expires) but say so when reporting.

## Wedged teardown on a still-running sandbox: act before the timeout
When `infra_teardown_incomplete_alerted` fires (capture read-back failing) the sandbox may still be running and fully recoverable, but only until its Vercel timeout, which counts from sandbox creation (default 1h), not from the alert.
1. First compute the deadline: sandbox `createdAt + timeout`. If under ~15 min remain, extend the timeout before anything else (`mcp__vercel__extend_session_timeout`), because a `persistent:false` sandbox loses everything on stop and the cmd API returns HTTP 410 the moment it expires.
2. Then pull the capture: if the orchestrator left `/tmp/capture-<session>.tar.gz`, verify it (`gzip -t`, `md5sum`, size) and stream it out in base64 chunks through the cmd endpoint (`dd bs=3M skip=N count=1 | base64 -w0`), appending locally and checking the final md5. Upload to S3 and write the capture pointer back.
3. Do not spend the window on diagnosis first. Recovery outranks RCA while the clock runs.
