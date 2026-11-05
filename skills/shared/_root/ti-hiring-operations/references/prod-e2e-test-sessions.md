# Production e2e test sessions and rollout scope

## Admin token and the helper command
The admin token lives in a local store, `/home/ubuntu/.ti-hiring-admin-token` (chmod 600). Make admin calls with `/home/ubuntu/.local/bin/ti-hiring-admin.sh <METHOD> <PATH> [JSON]` (source: this skill's `scripts/ti-hiring-admin.sh`) instead of fetching from SSM on every call. Only on 401/403 refresh the file from SSM (`aws --profile trilogy --region ap-south-1 ssm get-parameter --name /ti/orchestrator/ADMIN_TOKEN --with-decryption --query Parameter.Value --output text > ~/.ti-hiring-admin-token`, then chmod 600). To check the store is current, compare it to SSM in shell (`[ "$F" = "$S" ]`) and print only MATCH/DIFFER, never the value. Smoke-test the helper with `GET /healthz`. If the store seems missing, check for existing `~/.ti-hiring-*` files before creating one.

## Booking an internal test session on prod
It's an API call on existing endpoints. Don't open a Kanban task or build a new feature for it.
1. Read back the live assignment list with the admin GET (`/v1/admin/assignments`, admin token from SSM via `aws --profile trilogy --region ap-south-1`). Name the exact slug you'll use. Any currently published assignment works for a pilot, so never hold the test for catalog expansion.
2. Confirm the deployed ECS image and sandbox routing match what the test is meant to exercise. Booking before the new route is live only tests the old flow and wastes a paid Meet/Recall session.
3. Use the existing scheduler intake endpoint (`POST /v1/scheduling/intake`, `sendEmail=false`) or direct booking (`POST /v1/sessions`). Direct booking enforces a lead-time floor (`DIRECT_BOOKING_MIN_LEAD_MS` in `routes-admin.ts`, 400 `lead_time_too_short`); check its current value on `origin/main` before picking a start time, since the user may have it removed for testing. The same 10-minute limit is re-enforced downstream by the scheduler's Recall dispatch lead (`SCHEDULED_BOT_MIN_LEAD_MS`, consumed in `advance-scheduler.ts` and `provider-pacer.ts`): removing only the route floor turns a clean 400 into a 502 `scheduling_attempt_failed` after the Meet space and Calendar event were already created (leaked resources, no bot). Near-immediate booking needs an ad-hoc Recall bot fallback (no `join_at`) for starts inside the lead window, which is the user's chosen design; the Recall provider already omits `join_at` inside that window. Direct booking never emails the candidate; the sheet/intake path emails only when a row sets `sendEmail: true` (gated in `scheduling/processor.ts`, sent via `meet.sendSessionEmail`). Give the time in IST and echo the UTC conversion. Only report a session once Meet, Calendar and Recall are confirmed. A pending attempt is not a session.
4. On 409 `candidate_has_active_session`, GET the blocking session id from the error body. A just-finished session sits in `frozen` with `finalizeError` until teardown settles; `force_destroy` override then returns 409 `teardown_incomplete`, so don't loop on overrides. Re-read its status; once it is `terminated`, retry the booking with a fresh idempotency key (reusing the old key replays the old result).
5. "Close it and make a new one": POST `/v1/sessions/<id>/override` with `{"action":"force_destroy","reason":...}` works directly on `scheduled`/`ready` sessions (200 `{ok:true}`). GET the row to confirm `terminated`/`admin_force_destroy`, then book with a fresh idempotency key in the same script. If the SSM fetch exits 254, the SAML creds expired: run `/home/ubuntu/.hermes/scripts/aws-creds-refresh.sh` and rerun. Don't ask for confirmation first; the user's request is the approval.
6. The user owns the real browser e2e. Hand over the booking details and stop.

## Session expiry questions
When asked whether sessions can "not expire" or have a long window, first pin down which phase is meant: the pre-join window (booking to candidate sign-in) or the post-join run. Answer only that phase, grounded in `origin/main`. Phase map:
- Pre-join: the row sits `scheduled`. The sandbox is created by candidate-start on join, not at booking, so a long join window holds no VM. The constraint is the join window / never-started sweep on `scheduled` rows.
- Post-join: `READY_TTL_MINUTES` (config, default 15) runs from `readyAt` until Continue; then `durationMinutes` is the working window; the provider's `infra_expires_at` is a hard VM kill the orchestrator can't lift.
The user's usual intent is a long join window with the normal 30-minute run after Continue, which touches only the pre-join gate.

## Writing a "how to create a session" doc
For an operator-facing how-to on booking sessions via the API:
1. Derive the request contract from `orchestrator/src/http/routes-admin.ts` on `origin/main` (`git show origin/main:<path>`), not memory: body fields, the validation branches that 400, auth scopes (admin and operator both accepted), and the 409/503 failure shapes.
2. Cover both paths (direct `POST /v1/sessions` and `POST /v1/scheduling/intake`), plus cancel, reschedule and status routes.
3. Auth section: the local token store read (`TOKEN=$(cat ~/.ti-hiring-admin-token)`), the helper command with booking examples, the SSM parameter name and the exact `aws --profile trilogy --region ap-south-1 ssm get-parameter --name /ti/orchestrator/ADMIN_TOKEN --with-decryption --query Parameter.Value --output text` refresh command. When asked to add "the command to get the token", this section is what goes in. Never put the token value in the doc or chat, even when asked directly; decline once in plain words, keep the fetch command, and offer a scoped token or a booking UI for non-AWS users.
4. Write the markdown to a scratch file, `docs create` + `docs insert --markdown --file`, verify with `docs structure` (headings present). For later sections, insert a scratch markdown file rather than passing multi-line text with quotes/code fences as a shell argument to `find-replace`; embedded quotes and flags in the text break arg parsing.
5. When the user says "don't block the main chat", put CI watchers in a background process with notify and do the doc work in the foreground; never wait on the watcher.

## Writing the tester happy-path checklist doc
When asked for a doc of what to check in the booked session:
1. Derive the screen order from the deployed page code on `origin/main`, not memory: `wrapper/src/app/session/[id]/page.tsx` (pre-live page) and `wrapper/src/app/session/[id]/assessment/page.tsx` (live page). Grep for which component renders where (`SessionStatement`, `ProvisioningContinue`, `MeetLink`).
2. The candidate order is: sign in, then the briefing screen (rules, Meet link, media-gate checklist; Continue held until every gate signal is green), then join Meet on laptop and phone (checklist ticks live), then Continue flips the session live and redirects to the assessment page, where the assignment statement and the sandbox appear. The statement is never on the pre-Continue screen.
3. Fix an existing checklist doc with targeted `gog docs find-replace`, then read back with `gog docs cat` to confirm. Don't leave "this replaces earlier text" notes in the doc; rewrite the sentence cleanly.

## Triaging the tester's findings after the walk
The user records findings as comments on the checklist doc.
1. Read them with `gog docs comments list <docId> -j` (text in `content`, anchor in `quotedFileContent.value`); treat every comment as a finding, including ones anchored to unrelated passages.
2. Split each comment into its separate asks (one comment often holds a UI directive plus an unrelated bug). Classify each: product bug, UX gap, or design directive (e.g. "match the handoff mockup, with our palette").
3. For every bug, read the deployed code on `origin/main` for a root-cause candidate before filing, and put the file/function and mechanism in the card body along with a RED-test requirement. Example class: a media-gate signal that is keyed to a participant identity derived from a different signal (camera matched only to whoever screen-shared) cannot tick until that other signal fires, which shows up as "X only went green when I did Y".
4. File new cards through the kanban tools, prioritized above everything else (bugs that block candidate join first, then UX gaps, then design parity). Never repurpose archived cards by rewriting their body in the DB: it corrupts their history.
5. Reply with each finding, its card and the root cause found, then ask how the rest of the walk went.

## Diagnosing a live-session failure the tester reports
When the user reports a wrong screen or stuck state after a walk and says "card it, don't block":
1. Pull evidence in two quick reads, no more: the session row via admin `GET /v1/sessions/<id>` (status, endReason, finalizeError, capture/teardown/video fields) and CloudWatch `aws --profile trilogy --region ap-south-1 logs filter-log-events --log-group-name /ecs/ti-orchestrator --filter-pattern '<session-id-prefix>'` over the last ~90 min, filtered in python for error/fail/capture/teardown/video lines.
2. Name which leg failed (capture, sandbox stop, video, transcript) and which row field the client likely reads to pick the error screen (e.g. `finalizeError: true`).
3. File one card with the timestamped log lines, the row state, the investigations (why the leg failed; why that failure blocks an orthogonal user path such as submitting concerns; whether the user's input was still recorded) and a RED test. Mention adjacent signals (e.g. Recall pacer exhaustion) as leads, not causes.
4. Reply with the card id and the evidence summary, then stop; the worker owns the fix.
5. For failures in the capture/teardown/Drive legs, check `session-artifacts.md` first: it holds the settled artifact design (what goes to Drive, which legs may set `finalize_error`) that the card must respect.
6. "Session could not be created" on the candidate screen means candidate-start failed at join. The log signature is `session joined scheduled -> provisioning`, then `candidate-start create failed (non-retryable)` with a `code`/`status`, then `candidate-start gave up` + `ALERT`. A follow-on `inline give-up teardown failed ... no such sandbox and no archive exists` only confirms no sandbox was ever made; it is not a second fault. Report the create `code`/`status` as the failure point and the provider side as the owner of the root cause.
7. The infra service is a loopback sidecar in the same ECS task (`INFRA_BASE_URL` must be loopback, `INFRA_PORT` in the task-definition env), so its lines land in `/ecs/ti-orchestrator` too. Don't hunt SSM for an infra URL or look for a separate `/ecs/ti-*infra*` log group; widen the same log-group filter to the create timestamp window (all lines, not just the session id) to see what the sidecar logged.
8. To answer "is our call into infra correct?", check the contract in two reads on `origin/main`: `orchestrator/src/providers/infra-client.ts` (`createSandbox`: `POST /v1/infra/sandboxes`, bearer service token, `Idempotency-Key` = session id, body `{repoUrl, path, ref?, maxLifetimeMinutes?}` with optionals omitted when unset) and the call site in `orchestrator/src/lifecycle/candidate-start.ts` (fields come from the assignment spec + row). A 5xx on create means the provider answered and failed; a malformed request would come back 4xx. If the same create 5xx hits several sessions in a row, report it as a provider-side outage, not a per-session fault.
9. When the user asks for a "light" check, stop after the session log lines, the contract read and a one-paragraph verdict with ranked likely causes. Don't chase provider internals you can't see; name them as the owner's piece.
10. CloudWatch filter patterns don't support regex alternation (`a\|b`): the call errors, stdout is empty and the python parser dies with `JSONDecodeError`. Use `?term1 ?term2` for OR, or one plain term and filter the rest in python.

## Activating a route right after its PR merges
Do these in order before offering to book:
1. Watch the deploy workflow run for the merge SHA to finish, then confirm ECS: PRIMARY deployment `rolloutState=COMPLETED`, running count at desired, task-definition image tag equals the merge SHA, and the routing env flag (e.g. `LEGACY_FLOW`) is in the intended state. Use a plain `describe-services` + a python parse; nested JMESPath `--query` projections break easily.
2. Publish the assignment statements the test needs via the admin publication route, then GET each slug back and compare `statementMd` byte-exact plus `repo_url`/`repo_path`/`repo_ref` and `published`.
3. Report the exact start time in IST with UTC, and ask for the go-ahead with the default assignment named.
Later merges that deploy while you wait don't invalidate the booking path unless they touch it; say so in one line instead of re-verifying everything.

## Functional cutover plus a cleanup ask
- Ship the working route first. Put the full rename/cleanup (code, file names, env flags, DB identifiers) on its own card that runs in parallel. Don't link it as a child of the functional card or queue it behind the pilot: the user wants it done ASAP too, it just must not gate the release.
- Keep the legacy flow if it still works. Don't break it or remove it just to simplify naming.
- If a design comes back as a multi-PR migration program for what the user sees as "wire it and let it work", ask one clarify question (functionality first vs. cleanup in this release) before approving it. On "functionality first", do all of these:
  - Rewrite the active card's title and body so the latest decision is at the top.
  - Steer the design author to revise the doc in place.
  - Comment on the card that the previous design is obsolete and must not go to review or implementation.
  - Keep the dirty WIP in place, with no reset and no second writer.
- Env flag naming the user prefers: the new behavior is the default, and a neutral opt-out flag such as `LEGACY_FLOW=true` selects the old path. Never put a vendor name in the flag.
- The sandbox backend needs repo URL + folder path (+ optional ref). One repo URL plus the assignment slug as its folder path is enough; the DB assignment row is the only mapping (see `assignment-sandbox-mapping.md`). Don't build a second lookup from files.
