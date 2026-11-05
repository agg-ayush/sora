# Assignment publication and catalog toggles

Read before activating, deactivating or verifying assignments in the orchestrator DB.

## How publication works
- `PUT /v1/admin/assignments/:slug` (also what the ti-hiring-assignments sync Action uses) upserts content only. It does NOT publish. Activation is a separate, deliberate step.
- Per-slug toggles are the standard path: `POST /v1/admin/assignments/:slug/activate` and `POST /v1/admin/assignments/:slug/deactivate` flip one row's `published` flag. Activation is guarded (a slug with no synced content is rejected); unknown slugs 404.
- There is no legacy/new slug split anymore: every publishable slug is controlled the same way.
- `GET /v1/admin/assignments` (list) may read a file manifest rather than the DB catalog, so it can show fewer rows than are published. Use per-slug GETs for the truth until the list is rerouted to the DB.

## Rules
1. Toggle assignments through the per-slug endpoints. Never ship a migration or data-only PR to flip an assignment: Ayush wants activate/deactivate operable at any time through endpoints, not code changes.
2. After ANY toggle, read back `published` for every slug, not just the target. An API `{"status":"deactivated"}` response does not prove the target changed.
3. Before relying on a newly merged endpoint, confirm the deploy is live (a 404 on the route means the running task predates the merge).
4. Never edit an already-run migration's hardcoded slugs; migrations are immutable history.
5. Verification for any catalog change: GET each slug's published flag, attempt a booking against the turned-off slug (must reject), and book one still-active slug (must succeed).

## Verifying DB content matches the repo
Compare DB content against `origin/main` (`git fetch` then `git show origin/main:<slug>/assignment.md`), never against a local working copy: a stale local checkout makes a correct sync look stale.
- Per-slug GET returns the statement under `statementMd` (not `content`). Normalize line endings and trailing whitespace before comparing.
- `repo_ref` is null on every row by design (sync does not pin a ref); this is not drift.
- Repo checkout lives at /home/ubuntu/ti-hiring-assignments; slug dirs are the top-level entries excluding .github, README.md and scripts.
