# Assignment to sandbox mapping (external-IDE route)

Owner-settled contract for how a booked session gets its assignment and sandbox.

## Contract
- The DATABASE is the single assignment mapping. One row per assignment, keyed by the
  scheduling slug (e.g. `say-it-in-json`), holding: the exact repo `assignment.md` body
  (candidate-facing statement), `repoUrl`, `path` (repo folder) and optional `ref`.
- All repo assignment folders get rows (not only the currently active few). Seed from a
  pinned repo commit and read every row back after publishing.
- The scheduling API caller passes the assignment slug explicitly. No random selection.
- Persist the selected tuple on the booking so join-time sandbox create and its retries
  use the same `{repoUrl, path, ref?}` even if the catalog row changes later.
- Do NOT add a second runtime lookup from bundled JSON/snapshot files in the orchestrator
  to build create args. The infra sidecar validates that the tuple has a baked snapshot.
- Sandbox create body shape: `{repoUrl, path, ref?, maxLifetimeMinutes?}`.
- `maxLifetimeMinutes`: omit the property when scheduling omits it (infra server default
  applies). When scheduling supplies it, it must actually control the sandbox lifetime,
  within the server's validated bounds.

- Publication PUT `/v1/admin/assignments/:slug` takes ONLY `{title, statementMd}`; the server derives `repoUrl`/`path=slug`/`ref=null` and rejects any extra key with 400 `invalid_body`. Read the handler at the deployed SHA before calling an admin write route, since a strict schema rejects fields you assume it wants.
- Baked snapshots are keyed with `ref: null`; send `ref` only when the snapshot was baked
  with one. Do not derive `ref=main` from a GitHub `/tree/main/<folder>` URL (infra 422s).

## Syncing assignment repo changes to the DB
- There is no auto-sync; the DB changes only through the publication API. The chosen design is a GitHub Action in the assignments repo (not the orchestrator repo): on push to main (plus `workflow_dispatch`), diff changed assignment folders to slugs, PUT each via `/v1/admin/assignments/:slug` with `{title, statementMd}`, deactivate deleted slugs, fail the run on any failed PUT.
- Prefer the push-driven Action over a poller/cron watcher: no watermark state, fires exactly on change, zero orchestrator change.
- Auth: a dedicated scoped sync token (own SSM parameter) stored as a repo Actions secret, not the shared admin token, so scope and rotation stay independent. Never put it in the workflow file or logs.
- The card's workspace must clone the assignments repo and open the PR there.

## Real infra route semantics (teardown / cleanup / auth)
- Teardown errors carry `retryable` + `retryAfterSeconds` (body or `Retry-After` header).
  Transient 502/503 (rolling deploy)/504/409 `teardown_in_progress` and a 200
  `destroyed:false` must be replayed with the same Idempotency-Key and intent, within a
  bounded budget, before persisting failure; flattening them into one failure loses the
  capture and leaves the sandbox alive to its provider lifetime. Infra archives before
  destroy, so a replay does not duplicate the archive.
- After a `capture:false` stop, GET reports `expired` and a further POST returns 410
  `sandbox_gone` (non-retryable). Treat expired/destroyed/404/410 as cleanup complete and
  escalate other non-retryable errors immediately instead of burning the retry ladder.
- Healthz is unauthenticated: a wrong service token boots healthy and 401s per candidate.
  A one-time read-only authenticated probe at boot is the fix.
- Transcript summary entries fail independently: one `no_timestamps` file must not null
  every other file's stats.
- Hand-rolled fake infra clients that return success for any teardown or 200 for unknown
  sandboxes hide all of the above; tests must use real-route-shaped fakes.

## Handling an infra owner's compliance report
1. Verify each finding against the DEPLOYED image SHA (ECS task definition image tag vs
   merged PR SHA), reading the exact code paths at that SHA, before routing anything.
2. One card per independent finding, own worktree, priority by candidate impact
   (capture loss/cleanup loops above boot checks above summary quality). Fix all of them,
   including low ones, but do not gate the first e2e on the small ones.
3. Comment the finding on already-running cards that own overlapping pieces (e.g. the DB
   mapping card gets the no-ref rule) instead of spawning a duplicate writer.
4. If the report contradicts a standing user instruction (e.g. drop a field the user said
   to forward), do not silently reverse either side: record the discrepancy on the card and
   surface it to the user with the practical consequence.

## Pitfalls
- Before promising a pass-through field works, trace it to the code that USES it on the
  far side. A schema can accept a field and silently drop it, and a client may always send
  a config default; forwarding alone changes nothing.
- The existing statements table stores slug/title/statement only; repo mapping needs an
  additive schema change owned by ONE card so parallel cards do not collide on migrations.
- The booking backend is stamped at booking time: a test session booked before the new
  route is the production default lands on the old flow. Do not book a test session until
  the route that will serve it is live.
- Do not conflate "statement text is in the DB" with "repo path lookup"; explain both from
  fresh code reads, not recall.

## Scope discipline on reliability work around this route
- Prefer the provider's native mechanism (e.g. Recall bot PATCH `join_at` on reschedule)
  over speculative edge-case machinery.
- A duplicate recording is acceptable versus no recording; do not add human alerts for it.
- Keep the functional path the user is waiting to test moving first; bound hardening reviews.

## Propagating contract changes to parallel cards
- Prepend a "LATEST USER CONTRACT (SUPERSEDES CONFLICTING TEXT BELOW)" header to every
  affected card body, re-read to confirm, comment, and steer each running worker off the
  obsolete approach in the same turn. Name which card owns shared pieces (DB migrations).
- When the change hinges on an open question, ask once, then replace the pending text in
  place instead of appending.
