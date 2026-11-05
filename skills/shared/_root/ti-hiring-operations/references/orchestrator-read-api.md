# Orchestrator read-side API map

Use when answering "which endpoint gives X" or writing an API guide for a stakeholder (e.g. someone with only the admin token, no DB access).

## Map a sheet row to a session
- `GET /v1/sessions/lookup?email=` returns the LATEST session only.
- For a batch, or a student with re-bookings, pull `GET /v1/sessions?limit=500` once and filter by `candidateEmail`.
- Sheet email can differ from the booking email (students submit forms with two inboxes); match on phone/name when lookup misses.

## Per-session
- `GET /v1/sessions/:id`: status, endReason, timestamps, assignment, meetUrl, `infraCapture` (S3 uri), `infraVideo` (Drive link), latest concern.
- `GET /v1/sessions/:id/submission-summary`: the full bundle the Drive summary JSON carries (identity, capture, video, event timeline).
- `GET /v1/sessions/:id/detail`: event log; the only place with the FULL concern/trouble-note history (list rows show the latest note only, later concerns overwrite the row column).
- `/transcript` and `/prompts` serve only legacy-era sessions; infra-era sessions stay `transcript: pending` because their artifacts are the S3 capture + Drive video. Do not list these as current routes.

## Admin
- `GET /v1/admin/assignments`, `/v1/admin/statements`, `/v1/admin/allowlist`; `POST /v1/sessions`; `GET /v1/scheduling-attempts/:key/status`.

## Before documenting a route for someone else
- Enumerate real registrations in `orchestrator/src/http/routes-*.ts` (grep `app.(get|post|put|patch|delete)(`), then check a live row's fields: a route existing in code does not mean it returns data for current sessions.

## Stakeholder API guide format
- One short pageless gdoc (`gog docs write --replace --markdown --pageless`). Sections: map row to session / per-session drilldown / admin / caveats. One line per endpoint, honest gaps as caveats. No prose, no auth internals.
