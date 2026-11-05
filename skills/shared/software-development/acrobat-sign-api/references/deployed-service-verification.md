# Verifying a deployed signing service end to end ("does prod need anything?")

Use when the user asks to confirm an environment is fully set up after a credential or config change. The user expects every layer checked with live evidence, not a config read-through. Report as one table (check, result) plus a short list of things not needed now.

## Order

1. **Env vars, compared by identity, never printed.** Decrypt each production env value (Vercel `GET /v9/projects/{prj}/env`, then `GET /v1/projects/{prj}/env/{id}` per entry, filter `target` contains `production`). Compare secrets against the known-good local files (e.g. client id == approved app, refresh token == the admin-consent token file) and print only labels ("approved app", "OTHER <hash prefix>"). Print plain only non-secret values (API access point, token scope mode, `x-api-user`, base URLs, feature flags).
2. **Missing vars: read the code before calling them missing.** `git grep` each unset var on the deployed branch (excluding tests). A var with a fallback (`X || Y`) or used only for optional analytics is not a gap; say so in one line.
3. **The live build has those values.** Env is baked at build time: take `targets.production` from `GET /v9/projects/{prj}`, then confirm its `createdAt` is after the latest env `updatedAt`, `readyState == READY`, and note the commit sha.
4. **The public domain serves that build.** Custom domains fronted by a CDN (CloudFront in front of Vercel) return 404 from the Vercel alias API, so prove it from the page instead: `curl -s https://<domain>/login | grep -o 'dpl_[A-Za-z0-9]*'` must equal the production deployment id.
5. **Live Adobe auth exactly as prod does it.** Refresh the token with prod's own client id/secret/refresh token against prod's access point, then one read as the prod `x-api-user` (`GET /agreements?pageSize=1`). For account-scoped setups add `GET /webhooks` (account-gated) and list which webhooks exist and whose they are, so stray ones are explained rather than discovered later.
6. **Scheduled work actually runs unattended.** Read the latest snapshot/cron output from the prod DB (generated_at age, degraded/warnings, per-source fetched/failed/hidden counts, reauth flags) and confirm it ran after your last manual trigger.
7. **Users who need access have it.** Query the app's users/roles/access tables joined to `auth.users` (role, access flag, last sign-in) for the named operators.
8. **Real browser, logged in as a real admin.** Mint a session without a password: Supabase `POST /auth/v1/admin/generate_link` (magiclink, service role key) then `POST /auth/v1/verify` with the `hashed_token`, set the session as the `sb-<ref>-auth-token` cookie (`base64-` + base64url JSON, chunked `.0/.1` above ~3180 chars) in Playwright, open the dashboard and a few ticket pages, capture page errors and any 5xx responses, and screenshot to the scratch dir.

## Reporting

- Lead with the verdict ("needs nothing" or the exact gap).
- Separate "not needed now but you should know" items (code not yet promoted, roles only needed by a later feature) from gaps, and propose prod writes only with an explicit ask.
