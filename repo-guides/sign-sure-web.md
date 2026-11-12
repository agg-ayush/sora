# sign-sure-web system guide

verified-at: 3758fd066456cadb75cf831e4a192a4231f310d5 (origin/staging, read from a git archive of that commit)

Navigation aid, not evidence. Every design claim and review finding cites file:line read in the session. A card whose base commit is newer than the verified-at commit re-checks the entries it relies on. The remote host's main checkout was behind origin/staging when this was verified: start worktrees from `origin/staging`.

## What it is

Next.js 15 (App Router, React 18, TypeScript strict, Tailwind) app, Node >=22. Supabase holds auth, Postgres and storage. The product is the signature-flow board: legal admins see every Legal Intake ticket joined with its Adobe Sign agreement, and can send agreements for signature from a ticket page. Signers get a separate interim page. Deploys come from `.github/workflows/deploy-vercel.yml` on push to `staging` and `prod`. `amplify.yml` and README text still name Amplify. Branches: PRs target `staging` only; `prod` follows at promotion.

## Module map

| Path | Holds |
|---|---|
| `src/middleware.ts` | Session refresh for every route except static assets, `/sw.js`, `/ingest/*` and `/api/board/refresh` (that route checks its own bearer) |
| `src/app/(app)/` | Root layout for sign-in routes only: login, forgot and reset password, auth callback and confirm, error page |
| `src/app/(board)/` | Second root layout with its own `<html>`: `page.tsx` (`/`), `tickets/[ticketNumber]`, `updates`, `documents`, `actions.ts`, and `styles/*.css` (tokens, base, list, detail, controls, actions, updates, send) |
| `src/app/api/board/**/route.ts` | JSON routes: `refresh` (cron), `status`, `preferences`, `documents`, `updates/seen`, `fixture-ledger`, and per ticket `send`, `send-context`, `signers`, `notes`, `remind`, `resolve`, `uploads`, `attach-signed`, `comments-read`, `agreements/[agreementId]/(cancel,discard,manage,history,correct-email,authoring-url)` |
| `src/lib/board/model/` | Pure board model: `build.ts` (snapshot to `Board`), `schema.ts` (zod, strict), `types.ts`, `codes.ts` (holds `BOARD_SCHEMA_VERSION`), `attention.ts`, `time.ts` |
| `src/lib/board/intake/` | Legal Intake read client (GET only), `fixture-client.ts`, `source.ts` (snapshot read with deadline), `attention-keys.ts` |
| `src/lib/board/adobe/` | Adobe Sign read side: `client.ts`, `token.ts`, `status-reader.ts`, `status-cache.ts` |
| `src/lib/board/send/` | The only write path: `orchestrator.ts` (`runSend`), `adobe-sender.ts`, `intake-writer.ts`, `link-store.ts`, `attach-signed.ts`, `reminders.ts`, `pending-updates.ts`, `board-sweeps.ts`, `guard.ts`, `origin.ts`, `fixture.ts` (in-process ledger), `deps.ts` |
| `src/lib/board/*.ts` (top level) | `get-board.ts` and `load-board.ts` (serve and rebuild), `snapshot-store.ts`, `config.ts` (env validation, server-only), `access.ts` and `api-access.ts` (grant checks), `links.ts`, `updates*.ts`, `comment-reads.ts`, `dashboard-query.ts`, `list-model.ts` |
| `src/lib/roles/viewer.ts` | `getViewer`, `requireRole`, `hasRole`; role lookup against `user_roles` |
| `src/lib/supabase/` | `server.ts`, `client.ts`, `middleware.ts` (`updateSession`), `database.types.ts` (generated), `fetch-timeout.ts` |
| `src/components/board/` | Dashboard and ticket UI; `send/` (send form and result), `agreements/`, `documents/`, `updates/`, `time/` |
| `src/components/signer/`, `src/components/ui/` | Signer home; shadcn-style primitives |
| `src/lib/board/__fixtures__/intake/` | Fixture datasets: `team`, `review`, `mine-fallback`, `dashboard-seed` and drift or failure cases (`settings-403`, `truncated`, `paging-gap`) |
| `supabase/migrations/`, `supabase/rollbacks/` | Forward migrations (CLI applies) and manual down scripts (outside `migrations/` on purpose) |
| `scripts/` | `import-agreement-links.ts`, `seed-staging-updates.ts`, `smoke-board-refresh*.mjs`, `generate-icons.mjs` |

## Data flow

1. A request to `/` calls `getViewer()` once (per-request `cache`). Role `legal_admin` renders `BoardHome`; anything else renders `SignerHome`. No `user_roles` row means signer, but only after a successful lookup: a failed lookup is an error page, never signer. While `user_roles` is missing the lookup falls back to `board_access` and logs (`src/lib/roles/viewer.ts:44-68`).
2. `get-board.ts` builds the dependency set (Legal Intake client or fixture client, Adobe client, Supabase service-role client, snapshot store) and calls `loadBoard` in `load-board.ts`. A page never builds the board in the request: the first viewer after the stored snapshot is older than `BOARD_FRESH_S` (60) starts a rebuild under a database lease (`BOARD_LEASE_S`, default 90, capped by `MAX_LEASE_S`); everyone else gets the last good board.
3. A rebuild reads the Legal Intake snapshot (`LEGAL_INTAKE_TIMEOUT_MS` 20000 per call, `BOARD_INTAKE_DEADLINE_MS` 45000 for the whole read, `src/lib/board/config.ts:83-84`), reads Adobe agreement statuses through `status-cache.ts`, joins them with `board_agreement_links` rows, runs `buildBoard`, validates with `boardSchema` and stores the snapshot. If intake fails, the previous board is served with a banner (`served: "carried"`).
4. `GET /api/board/refresh` is the 5 minute cron (`vercel.json`). It needs `Authorization: Bearer <CRON_SECRET>` and refuses every production and preview call when `CRON_SECRET` is unset. After the build it runs the sweeps (`runBoardSweeps`, `autoAttachSweep`, `pendingUpdatesSweep`, automatic reminders). Production forwards the call to `STAGING_REFRESH_URL` when set.
5. Writes (send, cancel, remind, attach, resolve, notes) go through `src/lib/board/send/`. The send route runs `guard.ts` (board access, same-origin check against `src/lib/allowed-origins.json`, staging-database to staging-intake pairing), then `runSend`: validate, re-read ticket documents, download, upload to Adobe, create the agreement once with no automatic retry, record the link, then best-effort steps (status cache, authoring link, ticket move, note). An Adobe create that is not confirmed returns "Do not send again yet" because a retry could email signers twice. A confirmed write stores a patch of that ticket's row (`refresh-after-write.ts`, ticket patch wait 5 s) and a rebuild in `after()` reconciles it (settle wait 12 s); unconfirmed or failed writes rebuild nothing.
6. Client components poll or refresh (`BoardAutoRefresh`, `PageFreshness`) and call the API routes; server components call `lib` code directly.

## Domain concepts

- Ticket: a Legal Intake ticket, addressed by ticket number in URLs (`/tickets/<n>`). `/signature-flow` and `/signature-flow/<n>` are 307 redirects.
- Agreement: an Adobe Sign agreement, linked to a ticket by a `board_agreement_links` row (`source` is `manual`, `send` or imported). Only agreements with source `send` are auto-attached.
- Attention and staleness are computed by Legal Intake and rendered as given; the board never re-grades them.
- Snapshot: the stored `Board`. `generatedAt` is when a snapshot was assembled and `builtAt` is the start of the full build its unpatched rows came from; `patches` records per-ticket patch times (`src/lib/board/model/types.ts:185-190`, `src/lib/board/model/built-at.ts`). Compare row age with `rowAtOf`, not with `generatedAt`: they are different timestamps.
- Roles: `legal_admin` (row in `user_roles`) or signer. `public.users.role` is not used because users can update their own row. Grants only through the SQL functions `grant_role` and `revoke_role`.
- Fixture mode: `BOARD_INTAKE_SOURCE=fixture` with `BOARD_FIXTURE_DIR` serves fixtures, runs sends against an in-process ledger, and shows a "Demo data" banner. Production also needs `BOARD_ALLOW_FIXTURES=1`.
- Kill switches (runtime env): `BOARD_ENABLED=0` (404 everywhere on the board), `BOARD_ADOBE=0` (no Adobe calls, sending off), `BOARD_AUTO_ATTACH=0`, `BOARD_AUTO_REMINDERS=0`. All variables are in `.env.example` and validated in `src/lib/board/config.ts`; a bad value fails naming the variable, not the value.

## Conventions

- Imports from `src` use the `@/` alias, never relative dots (`.cursor/rules/internal-imports.mdc`). Prettier with `@trivago/prettier-plugin-sort-imports` orders imports (`.prettierrc`): react, third party, then `@/`.
- Component files and component names are PascalCase. Add `"use client"` only for client-only features.
- In pages and route handlers `params` and `searchParams` are Promises: always `await` them.
- Server-only modules start with `import "server-only"`. Vitest aliases it to an empty module.
- Code and UI copy: no em dashes. `src/lib/board/__tests__/copy-sweep.test.ts` fails on `—`, "Stuck" as a label, "working days or hours", British "Cancelled" and "Cancelling", "Unrecognised", Title Case tab labels and "Ticket Dashboard" in `components/board`, `lib/board` and `app` source.
- Migrations: file name `<UTC timestamp>_<snake_name>.sql` where the timestamp comes from `date -u +"%Y%m%d%H%M%S"`; never hand-edit `database.types.ts` (regenerate it); the user applies migrations. Rollback scripts go in `supabase/rollbacks/`.
- Any change to the persisted board shape, including an added optional field, bumps `BOARD_SCHEMA_VERSION` (`src/lib/board/model/codes.ts:1`). A stored snapshot of another version is ignored and rebuilt.
- Status cache writes go through the `board_put_agreement_status` SQL function, which is `service_role` only.
- Access and write rules: the board reads Legal Intake with GET only; every write lives under `src/lib/board/send/`. No counterparty token routes exist. If one is added it follows the contract in README ("Signer token links").
- Test recipients: use `sign-sure+<label>@<org-domain>` or `@example.com`, never a personal address. Prod test tickets carry `[TEST - DO NOT SIGN]`.

## Run unit, lint, type and format checks

Install: `npm ci --legacy-peer-deps` (CI form). `cp .env.example .env` first for tests and lint.

| Check | Command (as CI runs it) |
|---|---|
| Lint | `npm run lint` (`next lint`, config `eslint.config.mjs`: next/core-web-vitals and next/typescript) |
| Types | `npm run type-check:next` (`tsc --noEmit`, strict, `@/*` maps to `src/*`) |
| Format | `npm run format:check`; fix with `npm run format` |
| All unit tests | `npm run test` (`vitest run`) |
| Board unit tests (CI job) | `NODE_ENV=test npx vitest run src/lib/board src/components/board src/app/api/board src/lib/roles src/components/signer src/lib/__tests__/safe-next-path.test.ts src/lib/__tests__/next-config-redirects.test.ts src/lib/supabase` |
| One file | `NODE_ENV=test npx vitest run <path>` |
| Production build | `npm run build` (CI also checks that no server-only variable name appears in `.next/static`) |

CI jobs on PRs to `staging` and `prod` (`.github/workflows/code-quality.yml`): lint, format, typecheck, unit tests, board unit tests, board e2e in 7 shards. Run vitest with `NODE_ENV=test` or unset: a production `NODE_ENV` makes `src/tests/setup.ts` throw because a production React build has no `act()`.

## Test layout

- Unit tests sit in `__tests__/` next to the code, named `*.test.ts` or `*.test.tsx`: `src/lib/board/__tests__`, `src/lib/board/send/__tests__`, `src/components/board/__tests__`, `src/app/api/board/__tests__`, `src/app/__tests__`, `src/lib/roles/__tests__`. Shared helpers: `src/lib/board/__tests__/model-test-utils.ts`, `adobe-test-utils.ts`.
- `vitest.config.ts`: happy-dom, globals on, setup `src/tests/setup.ts` (clears a Map-backed `localStorage` after each test), global setup `src/tests/board-global-setup.ts`. It excludes any path containing `/tests/`, `*.config.*` and `node_modules`, so Playwright specs under `tests/e2e/` never run in vitest, and a unit test must not live in a directory named `tests`.
- `board-global-setup.ts` builds the team fixture board once and provides `teamBoard`, `boardCss` and `boardSources` to tests through vitest `inject`. Several component tests assert on CSS and on source text through these (for example `send-polish-css.test.ts`, `dashboard.test.tsx`): renaming a class, selector or file can fail them without any behaviour change.
- `src/components/board/__tests__/__snapshots__/ticket-page-unchanged.test.tsx.snap` is the only snapshot file.
- `src/tests/setup.ts` wraps `fetch` with `offlineFetch` so unmocked same-origin requests reject like a refused connection; unit tests make no live network calls.
- e2e: Playwright specs in `tests/e2e/*.spec.ts` (30 specs), helpers in `tests/e2e/support/`, committed baselines in `tests/e2e/__baselines__/` (`docrow-actions-visible.json`, `pill-cross-page.json`). Config `playwright.board.config.ts`. Fixture intake and a stub Supabase (`tests/e2e/support/supabase-stub.mjs`) mean no database or network. The specs run on three fixture servers (team 3100, mine-fallback 3101, review 3102) plus a save server (3103), with run-scoped ports and output dirs.

## Run e2e

- Full suite or one shard: `npm run test:e2e:board` or `npm run test:e2e:board -- --shard N/7`. Heavy: it builds the app first. The build is reused while source, build config and inlined public values are unchanged; `--skip-build` needs that too.
- Focused run: `node tests/e2e/support/run-board-e2e.mjs --project=<project> tests/e2e/<spec>.spec.ts --no-deps --workers=2`. A positional spec filter alone does not stop upstream project dependencies: targeting `shared-foundation` without `--no-deps` expands to hundreds of tests. Confirm the reported test count and that every result belongs to the target project.
- A bare `npx playwright test` skips the wrapper's ports and auth environment and can fail before the app runs (for example fixture-ledger 401). Use the wrapper.
- One checkout runs one board e2e at a time: `.next` and the build record are shared. Runs in separate worktrees can overlap because ports and output dirs are run-scoped.
- Stateful projects share the fixture ledger and run serially, with `--workers=1` for repeats. Project order in `playwright.board.config.ts` must match `STATEFUL_PROJECTS` in `tests/e2e/support/board-e2e-run.mjs`. A new spec must be added to `testMatch` in the config, to a project (with its `dependencies`) and to `INDEPENDENT_PROJECTS` or `STATEFUL_PROJECTS`, or CI never runs it.
- Chromium: the config uses `PW_CHROMIUM_PATH` or the newest `chromium-*` under `~/.cache/ms-playwright`, with `--no-sandbox`. Viewport defaults to 1280x800. `tests/e2e/support/test.ts` turns the scrollbar gutter off unless a spec sets `realScrollbars`.
- Report dir `test-results/` and `playwright-report/` hold traces and screenshots; set `PW_TEST_HTML_REPORT_OPEN=never` to avoid the report server.
- Live staging checks (real Supabase and Adobe) are separate and staging only: see the host skill `sign-sure-board-verification`. Never run them against prod.

## Gotchas

- Same fixture, different dates: each e2e server anchors fixture dates to its fixture's `generated_at` (`BOARD_FIXTURE_DATE_ANCHOR`). Re-capturing a fixture changes what the board shows.
- `waitForLoadState("networkidle")` returns immediately after a send while refresh reads are still rendering. Wait for the specific note or agreement content instead.
- Playwright `click()` scrolls sticky controls into view and fakes an 8 to 16 px page jump. Use `page.mouse.click` at the element centre to measure jumps.
- Layout assertions against `scrollHeight` include lazy content; scope them to the affected element.
- A test that builds its own DOM (for example a hand-made `span.pill--tone`) proves CSS, not the component mapping. Drive states through the real component.
- Past review findings cluster on: sequence guards in `src/components/board/send/LinkExisting.tsx` (`searchSeq`, lines 160-180) that tests did not exercise out of order, and the Adobe event code set in `src/lib/board/send/agreement-events.ts:11` (only codes in the Adobe v6 enum belong there).
- Legal Intake keys: a requester-scoped key silently returns only the requester's tickets, which the board detects and refuses. The prod legal-admin key returns 401 on staging.
- `LEGAL_INTAKE_BASE` must include `/api`. Staging is the default. Writes are refused with `SEND_ENV_MISMATCH` when the staging database pairs with a non-staging intake host.
- The live team attention read takes about 15 to 20 s against prod. Time budgets in new code are checked against that, not against a 25 s guess.
- `BOARD_ENABLED=0` deliberately answers 404 like having no grant. Check it first when an admin suddenly sees 404.
- Roles are granted only through the SQL functions. Never insert into `user_roles` or `board_access` by hand.
- A card writes migration files but does not apply them or hand-edit `database.types.ts` (`.cursor/rules/create-migration.mdc`).
- Review and test hygiene the audit measured as the biggest finding sources: concurrency, stale data and lifecycle (two tabs, undo, polling, unmount mid flight), failure and partial states (404, 502, lost response, error with data), and vacuous or conditional assertions. Every state transition needs a test that fails when the guard is removed.
- Consumers hide in strings: selectors, copy, test files and CSS class names. Grep for them; the graph does not see them.
- Untracked scratch dirs such as `shots/` and `undefined/` can appear in a working checkout. Stage files by path, never `git add -A`.
