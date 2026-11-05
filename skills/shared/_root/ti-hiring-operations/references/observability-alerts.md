# Observability and alerts (concerns, trouble exits)

## Where the signal lives
- Every candidate concern and "I'm having trouble" exit is a session event in the DB (`concern_submitted`, `trouble_exit`); kind/note sit inside the event's `detail_json` string and the timestamp field is `ts`. Read via `GET /v1/sessions/:id/detail` (events array). A poller keyed on top-level `kind`/`at` silently misses everything: parse `detail_json`.
- The orchestrator also logs each concern request to CloudWatch group `/ecs/ti-orchestrator` (ap-south-1) as JSON: `"msg":"session endpoint","endpoint":"concern"`.

## CloudWatch filter patterns (verified)
- Works: `{ $.endpoint = "concern" }` (exact field match), `concern`, `"concern"`.
- Fails with "Invalid filter pattern": raw JSON fragments with inner quotes such as `endpoint":"concern`. Give stakeholders the `{ $.field = "value" }` form.
- Console label is "Search log group" inside the log group page. Test any pattern with `aws logs filter-log-events --filter-pattern ...` before handing it over.

## Push alerts with zero code (preferred over a custom watcher)
All additive, safe mid-run, no deploy:
1. `aws logs put-metric-filter --log-group-name /ecs/ti-orchestrator --filter-name ti-concern-events --filter-pattern '{ $.endpoint = "concern" || $.msg = "trouble_exit" }' --metric-transformations metricName=TIConcernEvents,metricNamespace=TIHiring,metricValue=1,defaultValue=0`
2. `aws sns create-topic --name ti-hiring-concerns`, then `sns subscribe --protocol email` per recipient. Each recipient must click the AWS confirmation mail; until then the alarm notifies nobody, so say so in caps.
3. `aws cloudwatch put-metric-alarm --metric-name TIConcernEvents --namespace TIHiring --statistic Sum --period 60 --evaluation-periods 1 --threshold 0 --comparison-operator GreaterThanThreshold --treat-missing-data notBreaching --alarm-actions <topic-arn>`
4. Read back with `describe-alarms` and `describe-metric-filters`.
5. SNS email is fragile: corporate mail link-scanners can hit the one-click unsubscribe link, so subscriptions flip to `Deleted` and recipients only ever see the "subscription deactivated" mail. Check `sns list-subscriptions-by-topic` after any "I got a deactivate mail" report, and keep a Telegram watcher as the primary channel during live batches.

## Telegram watcher (CloudWatch-polling)
- Poll `aws logs filter-log-events --log-group-name /ecs/ti-orchestrator --filter-pattern '{ $.endpoint = "concern" || $.msg = "trouble_exit" }' --start-time <cursor+1>` every ~20s; persist the cursor (last event `timestamp`, ms) to a file so restarts never re-ping.
- Wrap every `aws` call in a subprocess timeout and refresh SAML creds on failure: an expired-credential call hangs and wedges the loop silently while the process still looks alive.
- Judge liveness by the cursor advancing, not by the PID existing; `pgrep -f` also matches its own shell, so confirm with `ps -p`.
- Compute probe `--start-time` from real now in ms; a miscomputed future start-time returns empty and looks like "no events".
- Send to a group via `hermes send -t telegram:<negative chat id>`. Get the group id by adding `@getidsbot` to the group (forwarding a message only reveals the forwarder's user id). Prove delivery by asking the user to reply in the group and seeing the inbound in `~/.hermes/logs/gateway.log`, not by the CLI printing `sent`.
- After any watcher restart, events in the gap may be cursor-advanced without a successful send: list them to the user once.

## Reporting concerns to the user
When asked for the concerns, pull them from CloudWatch, then each session's `/detail` for `detail_json.note`. Output a plain list of `Name — "note"` only: no times, Meet links, tables or commentary unless asked.

## DB access requests
The RDS is private-VPC with no direct access by design (all changes go through the orchestrator API, preventing accidental writes). ECS exec is disabled and the devbox has no route to it. Direct read-only access needs either a security-group rule or making the instance public (reboot), both infra changes: never do them right before a live batch; offer admin-API reads (stakeholders can mint their own token) instead.
