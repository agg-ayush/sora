# Legal Intake API (companion to Sign dashboards)

Public API at `https://<internal-host>/api/v1/` (docs at `/api/v1/docs`, agent guide alongside). Bearer key auth. Read the OpenAPI doc itself before answering filter/permission questions, not a summary of it.

## Keys and scope

- **No service-account concept: a key acts as the person who created it** and inherits their help-desk role. Requesters see only their own tickets; legal-team members see the team queue. A dashboard that must show every ticket needs a key minted by (or for) a legal-admin account. Ask for the role, not just "a key".
- A role upgrade on the creating account takes effect on the existing key; re-probe instead of asking for a new key.
- Verify scope with `GET /v1/tickets/attention?view=team`: the response must carry `view: team` and the expected `audience`. A board should fail loudly when it does not, rather than render a personal view as the team view.
- `GET /v1/me` reports the role; use it in error messages.

## Data endpoints

- `/v1/tickets/states` lists states with `waiting_on`; signature-flow states are those with `waiting_on == "signature"` (`ready_for_signature`, `sent_for_signature`; `signed` follows).
- `/v1/tickets?status=open|closed&state=...&per_page&page` paginates with `data` + `total_count`.
- `/v1/tickets/attention` returns the intake system's own urgency grading plus a `settings` block (business-day thresholds). **Live rows can lack keys that captured fixtures had** (`attention_level`, `waiting_on`), and the embedded settings block can carry extra keys (`escalation`, `thresholds`) absent from `/v1/tickets/attention/settings`. Re-capture fixtures from the live endpoint before trusting a parser built on old captures.

## Environments

- Staging lives at `https://<internal-host>/api/v1/` with its own key and webhook secret; prod and staging expose the same OpenAPI surface (diff the two `/docs` specs once to confirm before relying on it).
- Base URL is env config, never a constant: dev, tests and demo renders default to staging; prod is an explicit opt-in. Keep one secrets env file per environment and source the one you mean.
- When the user asks to switch a running render to staging, re-run the render with the staging env sourced into a separate output dir, restart the local server on the same port from that dir, curl it for 200, and report the new counts. Keep the prod render dir on disk so switching back is one server restart.

## Prod data rule

The data owner's condition: nothing touches prod data while developing. Dashboards make GET-only calls even in prod (enforce in the adapter, grep the diff for non-GET methods before claiming it); anything that writes or tests write paths runs against the staging environment. Before the user tells a stakeholder "read-only", verify it against the actual code of every build in flight.

## Verifying a live render

- **Print the artifact's top-level keys before reporting any count.** `d.get('tickets', [])` on a payload whose rows live under `rows` returns a real-looking zero and nearly produces a false "board is empty" diagnosis.
- Report from the payload's own `counts`, `warnings` and `degraded` fields; warnings about missing attention keys or settings drift are adapter findings to hand to the builder, not render failures.
- Live boards contain real counterparty names and deal titles; flag that before the user screen-shares.
