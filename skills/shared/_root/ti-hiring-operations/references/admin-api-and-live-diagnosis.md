# Admin API calls and live-session diagnosis

## Making admin calls
- Route every orchestrator admin call through the local `ti-hiring-admin.sh <method> <path> [json]` helper, including ad-hoc lookups inside execute_code. It self-refreshes on 401/403: it refreshes AWS creds, re-pulls the token from SSM, rewrites `/home/ubuntu/.ti-hiring-admin-token` and retries once. Hand-rolling an SSM fetch plus HTTP per call is the redundancy the helper exists to remove, and Ayush flags it.
- The token value never goes into a doc, chat or card. Docs name the SSM parameter path, the AWS account and the region only.
- External-facing docs leave out local-only tooling (the helper script, the token file) because other readers such as the infra vendor don't have it. Keep the raw AWS CLI command there instead.

## Common lookups
- To find someone's session: `GET /v1/sessions?email=<email>` and take the latest by `scheduledStartAt`. People can have multiple addresses (<org-domain> and devfactory.com), so try both. Report id, status, assignment, start in UTC and IST, and `meetUrl`.
- To create a new session for someone who already has one: force-destroy the old non-terminal row first. It blocks a rebook with a 409.
- Instant sessions (start under 10 min out) are supported. The scheduler dispatches an ad-hoc Recall bot instead of a scheduled one.

## Diagnosing a live symptom
When Ayush reports a live failure (a button returned an error code, "session could not be created", an error screen):
1. Get the session id (ask, or look it up by email).
2. Pull that session's orchestrator CloudWatch log lines and its event history.
3. Map the log reasons onto the route, then the lifecycle function that emitted them.
4. Only then state the cause, quoting the log line.

Don't present a code-read guess ("probably a read-after-write race", "either X or Y") as the diagnosis. Without logs, say the cause is unconfirmed and pull them. A hedged multi-mechanism theory just sends Ayush back to ask "are you sure".

If the failure is in the external infra service, confirm our request matches its contract (endpoint, body shape, auth) and say so explicitly. Don't dig into their side unless asked.
