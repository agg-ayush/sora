# Orchestrator ops routing, flags and renames

## Ops vs code
- One internal test booking is an API call, not a task. Use the scheduler intake endpoint (`POST /v1/scheduling/intake`, single internal row, `sendEmail=false`, IST start time) for instant/near-now e2e sessions. Check for an existing endpoint before filing a kanban task or proposing a direct DB insert; only shipping code goes through task + T2.
- The intake route is registered only when the orchestrator task runs with `SCHEDULING_ENABLED=true`. A 404 `not_found` on `POST /v1/scheduling/intake` means the flag is off in that environment, not a bad payload: check the live ECS task-definition env first, and report enabling it as an infra change needing approval. Until then, bookings go through `POST /v1/sessions`, and any "test through the intake path" acceptance criterion cannot be met there.
- Booking 409 = the candidate already holds an active session. A `frozen` row keeps the slot until teardown/retention clears it, so a finished candidate can be unable to rebook. Force-terminate the stale row, then rebook with a new idempotency key. Do it without asking.
- A `frozen` row with `finalizeError: true` and `infraTeardownState: pending` is wedged, not finishing: it also holds the orchestrator deploy drain, so a `Deploy orchestrator` run can sit `in_progress` far past its usual ~10 min. When a deploy stalls, list frozen sessions first. Force-destroy lands it as `terminated` / `override_teardown_incomplete`.
- The override can return 409 while the transition still lands. Always re-GET the session and report its actual status, not the HTTP code.
- `409 teardown_in_progress` on a frozen row means a teardown chain holds its lease and is still retrying with backoff. For many such rows (a batch-end wave), run the override as a background loop: re-GET each target, override only rows still `frozen`, sleep ~60s, exit when none remain, `notify=true`. Each row clears as its lease lapses. Don't hand-fire overrides repeatedly from the main chat.
- If a bulk side-effecting loop (overrides, POSTs) is interrupted, re-GET live state for every target before re-running: some calls landed. Write such loops to act only on rows whose live status still needs the action, so a rerun is safe.
- Batch-end `finalize failed` auto-concerns are our internal errors: teardown calls Recall (bot stop, recording list, recording download into the session folder) and a batch's timers expiring together exhaust the shared Recall pacer. Workspace capture and transcripts are a separate path; force-destroy skips only the Recall recording pull. Before describing what teardown does or what a flag gates, read the teardown code on origin/main and cite it; don't assert an env gate exists, or agree that one does, without finding it in config.
- Bulk booking (a cohort): one `POST /v1/sessions` per row with a deterministic idempotency key per row, run by a subagent off the main chat, single pass, no client retries. The scheduler sweeper owns Meet-pacer backoff; a subagent must not re-implement pacing. An attempt showing `status: failed` with `attempts` and `nextAttemptAt` still advancing is still retrying; only after its deadline passes re-POST genuinely dead keys with a fresh suffixed key (`-r2`, `-r3`). Verify the final set by start instant (parse to Date, not string compare on `.000Z`) and by case-insensitive email; duplicate form rows mean one session per distinct email. Never send mails on bulk booking unless asked.
- Async booking (202): poll `/v1/scheduling-attempts/:key/status`. A `failed` status with `lastError: "meet pacer deferred"` is the Meet rate-limiter and self-retries; re-poll after ~20s before calling it a failure. `committed` gives `sessionId`, then GET the session for `meetUrl`.
- To show someone the never-ran/Oops ended screen: book a session and force_destroy it before joining; the session page then renders that state.
- Drive link for a session: the row's `driveFolderId` is normally null (the folder resolves on demand), so it proves nothing. Read `GET /v1/sessions/:id/detail` and take `detail_json.url` from the `session_summary_uploaded` event; that is the Drive summary file. Only sessions that ran through real teardown have it; force-destroyed test sessions never do. For a candidate's sessions, `GET /v1/sessions?email=<addr>` then check each one's detail.
- Assignment publish (`PUT /v1/admin/assignments/:slug`) only upserts content. Activation is a separate step, so newly published slugs are inactive by design; activate explicitly before booking one.
- Toggle one assignment with the per-slug routes (`POST /v1/admin/assignments/:slug/activate` / `.../deactivate`); see `assignment-publication.md`. The body-less catalog-wide `/activate` and `/deactivate` flip every slug at once and ignore any `{"slug":...}` body, so never use them for a single assignment. Never toggle publication via migrations or direct SQL: activate/deactivate must be an anytime API operation.
- `GET /v1/admin/assignments` (list) reads the legacy manifest file, not the DB catalog, so it under-reports slugs. The truth for published state is the per-slug GET.
- Before any publication call, read the route and store code on `origin/main` to confirm its scope, and snapshot `published` for every slug (`GET /v1/admin/assignments/:slug`). Re-check all of them after the call; a `{"status":"deactivated"}` does not prove the intended slug changed. If the call hit the wrong set, restore the prior state right away with the opposite action and say so plainly.
- List sessions with `GET /v1/sessions?limit=N` (admin auth); there is no `/v1/admin/sessions`. Each row carries `sessionFlow` (`browser` / `ssh`) and `status`; the route list lives in `orchestrator/src/http/routes-admin.ts` on origin/main.

## Two orchestrator services share one DB
- "How many copies of the orchestrator run" means how many ECS services run orchestrator code against the shared DB, not task count per service. `ti-orchestrator` (browser flow) and `ti-orchestrator-ssh` (SSH flow) are both copies. List every service in the cluster before answering.
- Any sweeper whose claim query is not scoped to its own `sessionFlow` lets the other copy claim rows it cannot tear down (the SSH copy cannot lock/capture/stop a browser session's sandbox), which strands them `frozen`. Suspect this when batch-end rows freeze en masse.
- Stop-gap with no code change: take the SSH service out.
  1. Verify zero non-terminal sessions with `sessionFlow=ssh` via `GET /v1/sessions` (an SSH-flow session would be stranded without its copy).
  2. Lower the autoscaling floor first, else autoscaling restarts the task: `aws --profile trilogy --region ap-south-1 application-autoscaling put-scalable-target --service-namespace ecs --resource-id service/ti-orchestrator/ti-orchestrator-ssh --scalable-dimension ecs:service:DesiredCount --min-capacity 0 --max-capacity <current max>`.
  3. `aws ... ecs update-service --cluster ti-orchestrator --service ti-orchestrator-ssh --desired-count 0`, then poll `describe-services` until `runningCount` is 0.
  Reverse with the same two calls. The real fix (flow-scoping the sweep) is a PR; card it blocked if it must not land mid-run.

- Take the simplest input the user can give. External sandbox create needs `{repoUrl, path, ref?}`; if the user hands a repo/folder URL, derive path/ref (verify the folder has `assignment.md` and a baked snapshot at the baked commit, omit `ref` if the snapshot has none) instead of designing a mapping table for them to fill.

## Alerts and DB access
See `observability-alerts.md` (CloudWatch filter patterns, metric-filter + alarm + SNS recipe, concern event shape, why direct DB access waits).

## Candidate email triggers
- Before promising "book it and the mail will land", trace which paths actually call the invite builder (`git grep buildInviteEmail origin/main -- orchestrator/src`). Do not assume create, reschedule and intake behave alike: the send can be wired on some paths and absent or origin-inferred on others.
- Target design, confirmed by Ayush: the invite mail is an explicit opt-in `sendEmail` field in the request JSON on schedule (create) and reschedule, and per-row in the intake JSON. Cancel sends no candidate mail. Default is off everywhere; never infer it from booking origin. If the code on main still differs, card the change rather than working around it.
- To test mail content alone without booking, render the template and send it from startgreat to Ayush (see `invite-mail-batch-send.md`). Use a real booking only when the test is specifically about the trigger path.

## Booking 502 `calendar event ... start does not match requested start`
The booking verifier compares the Calendar event start to the requested start as exact instants after the round-trip. A 502 with this message means that check refused the booking, not that the payload was bad; the event may already exist. It blocks real bookings as well as the post-deploy smoke suite, so treat it as a live booking blocker when you report it and when you prioritise the fix card. Do not retry the same request in a loop.
- The fix is in the verification (compare the same instant regardless of the offset Calendar echoes back), never dropping the Calendar event. The event's guest list is what admits the candidate into the Meet; a Meet created without the invite leaves the candidate unable to enter. Don't propose removing the calendar invite even though the mail no longer carries the Meet link.
- Don't describe it as "POST is broken": other bookings succeed. If asked why some bookings passed and one failed, compare the actual requested vs echoed start values from the failing response/logs instead of guessing.
- After the fix merges, prove it with a real booking for Ayush (arm a background PR watcher, then book through the helper and confirm a 201 with no mismatch). Close the test session afterwards when asked (force_destroy).

## Verify a merged fix only on the deployed image
Merge is not deploy. `Deploy orchestrator` runs on push to main and takes about 10 minutes (it can sit queued first). Before re-testing a fix live, confirm the PRIMARY ECS task's image tag equals the merge sha:
```
aws --profile trilogy --region ap-south-1 ecs describe-services --cluster ti-orchestrator --services ti-orchestrator --query 'services[0].deployments[*].{status:status,taskDef:taskDefinition}' --output text
aws --profile trilogy --region ap-south-1 ecs describe-task-definition --task-definition <family:rev> --query 'taskDefinition.containerDefinitions[0].image' --output text
```
If it doesn't match yet, arm a background watcher on `gh run list --repo <org>/ti-hiring --branch main --workflow 'Deploy orchestrator' --limit 1 --json status,conclusion` until `completed|success`, then re-test. A failure on the old image is not evidence against the fix, so don't report it as one.

## Close the card once the fix is proven live
When the main session has proven a card's fix end to end (merged, deployed, a real call succeeds), close the card and stop its worker yourself: complete it with the live evidence as the summary. Don't leave the worker spinning on its own wrap-up, and don't ask Ayush whether to close it. A heartbeating worker whose PR merged and got verified is stale, not in progress.

## Admin helper output
`ti-hiring-admin.sh` prints the response body followed by a trailing `[http NNN]` line. Strip everything from the last `\n[http` before JSON-parsing, and always read the status. A parse where every field is None usually means an error body such as a 409 or 502, not an empty success. The helper self-refreshes the token on 401/403, so don't hand-fetch it first.

## Flags
- Vendor-neutral names, new path is the default. Name the opt-out for old behaviour (`LEGACY_FLOW=true` routes to the legacy backend; unset/false = new route). Never put a supplier/product name in flags, filenames, code or docs.
- Flipping a route flag alone is rarely the cutover: confirm the live ECS task env and any catalog/statement publication the new route needs, and stage with the old route pinned until publication is GET-verified.

## Supplier-name purge touching persisted identifiers
1. One clarify before dispatch: does "zero references" include already-applied migration files and live DB columns / stored TEXT CHECK values?
2. If yes, the task body requires: additive compatibility stage safe for mixed old/new ECS tasks; cutover; final purge after old tasks retire; fresh-DB replay AND upgrade-from-prod proof; rollback per phase; environments that skip an intermediate commit.
3. Final gate: case-insensitive `git grep -i` plus tracked-filename check returns zero at exact PR head. No blind search/replace; no string-splitting in SQL to dodge grep. Git history and external discussions stay untouched.
4. Pause in-flight WIP that uses old names; keep it uncommitted and single-writer.
- `schema_migrations` records migration NUMBER only: renaming an applied file keeps the ledger valid, but editing historical SQL changes fresh replay, so prove both paths.

## Kanban mechanics
- `hermes kanban specify` rewrites title and body via an LLM and can drop constraints. Re-read `show --json` after it; if you already wrote a complete body with `edit`, skip `specify`.
- After `dispatch`, check `spawned` is non-empty before telling the user a worker is running.
- A card meant to wait must be created already blocked (`initial_status=blocked`). Creating it ready and blocking afterwards races the dispatcher, which spawns a worker within seconds. Read the status back after creation and, if a worker grabbed it, stop that worker before re-blocking.
- Code fixes go through a kanban card plus a T2 tmux supervisor on that card, never a plain `delegate_task` subagent and never a bare tmux session fed a brief file with no card. Plain subagents are for ops and data work only. When replacing a misbehaving T2, stop it and start a fresh one on the card; don't keep steering it.

## Waiting on CI/deploys
- Never block the main chat: run `gh run watch` / `gh pr checks --watch` as `terminal(background=true, notify=true)`.
- A checks pass listing only one check (e.g. Semgrep) is a false green; confirm the full exact-head check set ran. Reopening the PR retriggers CI without code changes.
- Post-deploy smoke failures are not the PR's CI; identify which workflow a linked run belongs to before acting.
- When a PR is red, get the actual error before explaining: `gh pr view <n> --json statusCheckRollup` for which jobs failed, then `gh run view <run-id> --log-failed | grep '##\[error\]'`. Report the file:line and whether it is a type/lint miss or a logic failure. A tsc `possibly 'undefined'` on a regex capture group is a one-line guard, not a design problem.
