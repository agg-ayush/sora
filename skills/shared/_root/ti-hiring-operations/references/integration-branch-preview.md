# Previewing wrapper UI before merge (Vercel preview, local dev server, static mockup)

Use when the user wants to visually check UI from an integration branch or an open PR before production, or compare it against a static design mockup. When the user asks to test a UI PR locally before merge, stand up the local dev server and wait for their OK before merging.

## Which path
- "let me test locally before you merge" -> local dev server on the PR branch worktree. Fastest, no Vercel auth.
- Shareable preview of an integration branch -> Vercel preview.
- A designer's HTML mockup rendered -> static server. Do exactly that, nothing more.

## Static mockup server (designer handoff HTML)
1. Pull the requested path at the exact ref (`git archive` / `git show <ref>:<path>`) into a scratch dir. If the user links a folder, serve the whole folder so relative assets and sibling pages resolve.
2. `python3 -m http.server <port> --bind 0.0.0.0` as a background process; verify every file returns 200 with curl.
3. Give the public URL (`http://<ec2-public-ip>:<port>/...`). When the user points at a newer branch/commit, re-pull into the same dir and keep the same URL.
- Do not investigate, diff or build anything else in the same turn. The user interrupts when a "serve this" request turns into archaeology.
- Before describing the mockup's layout (one vs two column, which screen shows what), open the specific file/view you are describing; handoff folders often hold several mockups with different layouts and they are easy to conflate.

## Local dev server on a PR branch
1. Use the PR's worktree (or check out the head sha). Run `next dev` from `wrapper/` as a background process on a free port bound to 0.0.0.0, with dev-only env: `SESSION_REGISTRY_FILE=<json>` (file-backed registry instead of the orchestrator), `ORCHESTRATOR_URL` unset, and the env-gated test login enabled.
2. Log in through the test-login route (`/auth/test-login?token=<dev token>&sid=<id>`), which sets `wr_session` for the test candidate. Hand the user that URL with the public IP.
3. Verify with curl + a cookie jar that `/session/<id>` returns 200 and expected screen strings render before handing it over.

File-registry fixture gotchas (validation failures are silent):
- Any validation failure in the registry JSON surfaces as a 500 `registry_unavailable`, not a field error. Read `validRecord` / `validMediaGate` / `parseRegistry` in `wrapper/src/lib/session/registry.ts` and satisfy every required field rather than guessing one at a time.
- Both the document AND each session record need `"version": 1`; the record's `id` must equal its key.
- `mediaGate` needs boolean `enabled`, `failOpen` and `signals.{joined,camera,screenshare,mic,recording}`.
- A 404 after login means `candidateEmail` does not exactly equal `TEST_CANDIDATE_EMAIL` in `wrapper/src/lib/auth/test-login.ts`; copy it from source, do not retype it.
- Pre-satisfied gate signals show the ready state; set them false (or `enabled:false`) to walk the gate steps.
- Set `readyAt` to roughly now. The ready-TTL countdown computes `readyAt + readyTtlMinutes` and calls `window.location.reload()` at zero, so a stale `readyAt` puts the setup page into an endless reload loop.
- The file registry is read-only: `/entered`, `/done` and trouble POSTs return 200 but never change the record, so Continue cannot advance the page. To show the next screen, edit the fixture to the post-action shape (for Continue: `status: "live"`, `joinedAt` now, `endsAt` now + duration); the session page then redirects to `/assessment`. Tell the user this is a fixture step, not a UI bug.
- The login page shows "Google sign-in unavailable" whenever the OAuth env vars are unset, which is normal locally. Hand over the test-login URL directly rather than the sign-in page.
- Before handing over, walk every screen the user will click through (setup -> assessment -> finish) against the fixture with curl, so fixture gaps surface before the user hits them one per message.

## Vercel preview of an integration branch
Facts:
- The `Deploy wrapper` workflow only runs on push to `main` and deploys `--prod`. Never dispatch or retarget it for a preview.
- Use the existing wrapper Vercel project; do not create a new project or change the production alias.
- `create_deployment` with a `gitSource` of the private repo fails (`incorrect_git_source_info`) when the Vercel GitHub integration cannot see the repo. Deploy from a local checkout instead.

Procedure:
1. Verify the branch tip sha and which PRs are merged into it vs still draft.
2. Check for an existing preview deployment of that branch first.
3. Check out the exact tip in a clean worktree under `wrapper/`.
4. `VERCEL_TOKEN` is only a GitHub Actions secret. Start `npx --yes vercel@latest login` as a background PTY process, read the device URL from the log, and ask the user IN ALL CAPS to open and approve it. Never ask for or paste the code/token in chat.
5. Link to the existing project/team, then `vercel pull --yes --environment=preview`, `vercel build`, `vercel deploy --prebuilt` (no `--prod`).
6. Verify the URL serves the expected commit and sits behind Vercel deployment protection.

## Framing
- A preview or local dev server is visual-only. If backend PRs the UI depends on are unmerged or undeployed, say the flow is not functionally testable from it and it is not e2e evidence.
- Record preview scope (branch, sha, not-prod, not-e2e) on the tracking card.
