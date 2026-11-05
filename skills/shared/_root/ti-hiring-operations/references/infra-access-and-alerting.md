# TI-hiring infra access and concern alerting

## DB access (ap-south-1, acct <aws-account>)
- RDS is private in the VPC with no direct access by design; all reads/changes go through the orchestrator admin API.
- The devbox EC2 security group has no route to RDS:5432, so SSM port-forwarding from the devbox times out. Do not retry it.
- ECS exec is disabled on the orchestrator service and tasks; no shell path into the VPC without an infra change.
- Direct read-only access for someone (e.g. a stakeholder) needs either an SG rule change or making RDS publicly accessible (reboot). Neither is acceptable right before a live batch; offer the admin API instead.

## Assignment publication
- Per-slug endpoints: POST /v1/admin/assignments/:slug/activate and /deactivate. LEGACY_SLUGS is empty; all slugs use the same flow.
- Data changes like publish flags go through endpoints, never migration files.
- GET /v1/admin/assignments reads sandbox/assignments.manifest (legacy manifest path), not the DB catalog. Per-slug GETs are the DB truth.
- To verify synced content, compare DB against origin/main, never the local working copy (it can be stale).

## Concern / trouble-exit alerting (zero code)
- Concern and trouble-exit submissions are session events in the DB and log lines in CloudWatch group /ecs/ti-orchestrator.
- Metric filter `ti-concern-events`: pattern `{ $.endpoint = "concern" || $.msg = "trouble_exit" }` -> metric TIHiring/TIConcernEvents.
- Alarm `ti-hiring-concern-submitted` (Sum > 0 over 60s) -> SNS topic arn:aws:sns:ap-south-1:<aws-account>:ti-hiring-concerns, email subscribers Ayush, infra lead, colleague (each must click the AWS confirmation email).
- CloudWatch filter gotcha: a raw substring with embedded quotes like `endpoint":"concern` is an Invalid filter pattern. Use `{ $.endpoint = "concern" }`, `"concern"` or plain `concern`. In the console the button is "Search log group".
- Session event payloads nest kind/note inside `detail_json` (JSON string); the timestamp field is `ts`, not `at`.

## Booking at scale
- POST /v1/sessions is the individual scheduling path; /v1/scheduling/intake needs SCHEDULING_ENABLED (not set on prod).
- Meet-pacer deferrals are retried by the scheduler sweeper on its own; POST each row once and let the sweeper grind. Attempt status `failed` with advancing nextAttemptAt is still retrying.
- Booking is silent; mail only goes out when explicitly requested.
