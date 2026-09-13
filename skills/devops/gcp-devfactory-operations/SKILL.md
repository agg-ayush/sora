---
name: gcp-devfactory-operations
description: "GCP/gcloud auth, SA setup, org-infra recon for DevFactory."
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [gcp, gcloud, service-account, oauth, adc]
---

# GCP DevFactory Operations

Umbrella for Google Cloud (gcloud CLI, service accounts, ADC) work in this org — the GCP counterpart to `aws-devfactory-operations`.

## Auth mechanics (verified facts, not guesses)

- Org enforces a short-lived OAuth session (observed ~24h) on Google Workspace-linked accounts. When it expires, the stored refresh token itself dies (`invalid_grant` / `invalid_rapt`) — this is not a token that can be silently refreshed, it requires a real browser re-login (`gcloud auth login`).
- `gcloud auth application-default login` does NOT solve this. ADC (`application_default_credentials.json`) is just a second copy of the same user OAuth refresh token in a different file, so Python/`google-cloud-*` libraries and MCP servers that don't shell out to gcloud can find credentials. It rides the same org session policy and dies the same way. Run both logins (CLI + ADC) once so both surfaces work, but expect both to need the same periodic browser re-login — there is no user-side way to mint a refresh token without the browser under this org policy.
- A hook that only detects-and-reports the reauth failure adds little when the agent already reads the error from tool output in the same/next turn and a browser step is mandatory either way — only worth building if it can also remediate headlessly (compare to the AWS saml2aws hook, which actually fixes creds with zero human involvement).

## gog vs gcloud — completely disjoint, do not conflate

- `gog` CLI (see `gog-cli` skill) is Google **Workspace** only: gmail, drive, docs, sheets, calendar, chat, keep, meet, photos, forms, sites, slides, admin, groups, classroom, tasks, searchconsole, etc. Zero GCP infra surface — no compute, storage (GCS), bigquery, iam, or run. gog's own "storage"/"admin" nouns are Drive/Workspace-admin, not GCP.
- gog uses its own separate OAuth client, independent of the gcloud CLI's credential store. `gog auth status -j` shows `service_account_configured` separately from Workspace user auth.
- Conclusion: gog cannot substitute for gcloud for any GCP infrastructure task (Cloud Run, GCS, IAM, Vertex, etc). Don't re-check this each session — it's a permanent tool-scope fact.

## Before assuming an SA/project setup is blocked, check existing infra patterns first

Don't guess at org policy or ask the user to unblock something the org's own repos already do. Recon steps, in order:

1. `grep -h "Command:" ~/.config/gcloud/logs/<recent-dates>/*.log | sed 's/.*Command: //' | sort | uniq -c | sort -rn` — shows what gcloud subcommands have actually been run from this machine (IAM binding, SA create, workload-identity-pool create, etc).
2. `grep -rho "projects/[a-z0-9-]*" ~/.config/gcloud/logs/.../*.log | sort -u` — surfaces real project IDs already in use.
3. Grep sibling repos' deploy/bootstrap scripts for `PROJECT_ID=`, `*_SA=`, `iam service-accounts create`, `add-iam-policy-binding` — an established bootstrap script (e.g. one that creates `FETCH_SA`, `EVAL_SA`, `COORDINATOR_SA` inside `$PROJECT_ID` and binds bucket roles) proves SA creation and project ownership are already working patterns here, not something to treat as a shared-infra unknown.
4. Only the SA **key-creation** step needs a live check (`gcloud iam service-accounts keys create` — may be blocked by an `iam.disableServiceAccountKeyCreation` org policy). If keys are disabled, impersonation (`--impersonate-service-account`) still rides the human's own OAuth session for local/interactive use, so it does not bypass the reauth floor — it only helps for workloads running natively inside GCP (e.g. attached to a Cloud Run job).

This recon-before-assuming step generalizes: check what the org's own scripts already do before treating a capability as blocked or requiring a new unilateral decision.
