# GCP/gcloud auth: session policy, headless login, tool scope

## Org session policy: both CLI and ADC tokens die with the session

- Org enforces a short-lived OAuth session (~24h observed) on
  Google Workspace-linked accounts. When it expires, the stored refresh token
  itself dies (`invalid_grant` / `invalid_rapt`) — it cannot be silently
  refreshed; it requires a real browser re-login (`gcloud auth login`).
- `gcloud auth application-default login` does NOT solve this. ADC
  (`application_default_credentials.json`) is just a second copy of the same
  user OAuth refresh token in a different file, so Python/`google-cloud-*`
  libraries and MCP servers that don't shell out to gcloud can find
  credentials. It rides the same org session policy and dies the same way.
  Run both logins (CLI + ADC) once so both surfaces work, but expect both to
  need the same periodic browser re-login — there is no user-side way to mint
  a refresh token without the browser under this org policy.
- A detect-only reauth-failure hook adds little when the agent already reads
  the error from tool output and a browser step is mandatory either way —
  only worth building if it can also remediate headlessly. (Contrast the AWS
  saml2aws hook, which actually fixes creds with zero human involvement.)

## Interactive login on a headless/remote box (direct copy-paste OAuth)

When the user explicitly wants to log in ON the box itself (not via
impersonation, not via a second-device bootstrap relay), use the direct
copy-paste OAuth flow — do not reach for `--no-browser` remote-bootstrap
first; it expects the *other* device to complete a token handoff
automatically and often hangs with no error:

1. Install gcloud locally if missing (e.g. under `/tmp/google-cloud-sdk`),
   add its `bin/` to `PATH` for the session.
2. Run `gcloud auth login --no-launch-browser` as a **background pty
   process** — it prints an `accounts.google.com/o/oauth2/auth?...` URL and
   then blocks on "enter the verification code".
3. Give the user that exact URL to open in their own browser. After they
   sign in, Google shows a code starting `4/0A...`.
4. Feed the code back via the background-process submit mechanism (process
   `submit` action) — do not type it as a normal terminal command; the
   process is mid-prompt on a pty.
5. Confirm with `gcloud auth list` (shows `*` next to the active account)
   before doing anything else.

If the user says "don't take indirect routes, log in here directly" — that is
a rejection of any flow that bounces through a second device/relay in favor
of this direct copy-paste flow on the box being operated. Default to the
direct flow first.

## gog vs gcloud — completely disjoint, do not conflate

- `gog` CLI (see the `gog-cli` skill) is Google **Workspace** only: gmail,
  drive, docs, sheets, calendar, chat, keep, meet, photos, forms, sites,
  slides, admin, groups, classroom, tasks, searchconsole, etc. Zero GCP infra
  surface — no compute, storage (GCS), bigquery, iam, or run. gog's own
  "storage"/"admin" nouns are Drive/Workspace-admin, not GCP.
- gog uses its own separate OAuth client, independent of the gcloud CLI's
  credential store. `gog auth status -j` shows `service_account_configured`
  separately from Workspace user auth.
- Conclusion: gog cannot substitute for gcloud for any GCP infrastructure
  task (Cloud Run, GCS, IAM, Vertex, etc). Don't re-check this each session —
  it's a permanent tool-scope fact.
