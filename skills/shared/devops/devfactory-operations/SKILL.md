---
name: devfactory-operations
description: "DevFactory AWS/GCP ops: creds, IAM, EC2 fleets, gcloud."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [aws, gcp, devfactory, saml2aws, iam, gcloud, ec2, devpod]
---

# DevFactory Cloud Operations

Umbrella for DevFactory org cloud work across AWS and GCP. Always-on rules live
here; per-topic depth lives in `references/` and `templates/`.

## Always-on rules (both clouds)

- **Verify live state, never intent.** A CFN stack parameter, a remembered
  project ID, or what main's template says is a claim about intent — read the
  running box / `gcloud projects describe` / live IAM policy before acting or
  quoting anything back to the user. This is the most common false-negative in
  every audit below.
- **Clear stale ambient credentials before trusting an AccessDenied.** Exported
  `AWS_*` env vars silently override profile creds; `unset` them, run
  `aws sts get-caller-identity` / `gcloud auth list`, and confirm the effective
  identity before diagnosing anything.
- **Classify blast radius before cloud-identity/IAM-adjacent changes**, even
  under a blanket "you have autonomy" grant: state whether the change is
  project-scoped or touches org/account-level resources, and confirm before
  crossing from project scope to org scope. A general grant covers picking the
  approach, not silently widening scope.
- **Recon the org's own existing patterns before assuming a capability is
  blocked.** Grep sibling repos' bootstrap/deploy scripts and cloud-CLI logs
  for what already works (SA creation, IAM bindings, AMI bakes) before asking
  the user to unblock something the org already does.
- **Design long-running scripts to survive short-lived credentials**: refresh
  creds inside the loop per iteration (it self-throttles), make each iteration
  idempotent, and prefer sequential-with-refresh over parallel fan-out when
  total wall time can exceed the token lifetime (AWS session: 1h, not raisable;
  GCP org session: ~24h, browser re-login required).

## AWS

- **Credential refresh (current: OneLogin OIDC `trilogy-aws-key.py`)** —
  locate script, headless paste-back login, profile naming, id_token cache:
  `references/aws-onelogin-refresh.md`. Use this by default on macOS; the
  saml2aws/Keycloak path (`references/aws-saml2aws-refresh.md`) is the
  operative one on headless Linux (sora) — see next bullet.
- **Headless Linux (sora): both AWS profiles ride saml2aws/KeyCloak** —
  verified 2026-10-27 that the KeyCloak SAML assertion carries BOTH
  `RAM-AWS-Prod-DevFactory-devflows-Admin` (<aws-account>) and
  `RAM-AWS-Int-CentralFunctions-ESWLegal-Admin` (<aws-account>), so
  `bash ~/.hermes/scripts/aws-creds-refresh-linux.sh` mints `[devflows]` and
  `[eswlegal]` via two unattended `saml2aws login --role <arn> -p <profile>`
  calls (password from `~/.config/saml2aws/.trilogy-password`, log at
  `/tmp/aws-creds-refresh.log`) — password-only, self-healing, no OneLogin
  id_token window. On ExpiredToken on this box, run it FIRST, before ever
  launching a OneLogin paste-back or asking the user for a browser login. If a
  OneLogin prompt from an earlier turn is pending, check whether its process is
  still alive (`ps`, port 12345) before asking the user to paste anything.
  Profiles here are `[devflows]`/`[eswlegal]` only, no `[default]`/`[trilogy]`:
  always pass `--profile`. A bare `aws sts get-caller-identity` on the EC2 box
  falls through to the instance role (`AmazonSSMRoleForInstancesQuickSetup`)
  and looks like success, so verify with
  `aws sts get-caller-identity --profile devflows` (and `eswlegal`). Do NOT regress
  eswlegal to the OneLogin path (id_token dies every ~2h, needs a WebAuthn
  paste-back); a prior refresh-script header claiming ESWLegal is absent
  from the KeyCloak assertion was never verified and was false. Verify the
  assertion live (login form → POST creds → base64-decode SAMLResponse →
  grep `RAM-AWS-`) before trusting any such claim, and re-verify if a login
  starts failing after AD-group changes.
- Long-run credential survival patterns (per-iteration refresh, idempotent
  steps) still live in `references/aws-saml2aws-refresh.md`.
- **IAM credential audit & rotation** — audit consumers before rotating, scope
  purpose-built identities, verify with real probes, safe teardown order:
  `references/aws-iam-credential-rotation.md`
- **Is a key still in use when IAM introspection is denied** — cross-reference
  GitHub secrets + workflow run history instead:
  `references/aws-key-last-used-when-iam-denied.md`
- **EC2 worker fleet drift** (code checkout, IAM role policy, golden-AMI
  package), deploy-workflow end-to-end verification, prod/dev publish switch,
  content migration between environments, SSM technique:
  `references/aws-ec2-worker-fleet-drift.md`
- **Producer creds for on-box batch submit + re-running a batch subset**:
  `references/aws-batch-producer-creds.md`
- **DevPod remote workspaces** (persistent-workstation model, provider setup,
  lifecycle pitfalls, decoupling to plain EC2) — plus the devcontainer starter
  at `templates/devcontainer-node-python-docker.json`:
  `references/devpod-remote-workspace.md`
- **Requesting access to an org AWS account:** access is AD-group driven (SAML maps AD groups to account roles), so the IT catalog item is "Add user to Active Directory group", not an AWS-specific form. Name the exact group `RAM-AWS-<account-name>-Admin` (or `-PowerUser`) plus the account ID, the reason, and the stakeholder who designated the account as approver. For deploying an app (Amplify, build IAM roles, Route53) ask for Admin: PowerUser hits IAM walls mid-deploy. Read the group names from the org role mapping rather than guessing.
- **Which AWS account hosts a deployed app** (DNS, all-region Amplify domain
  associations, Route53, repo ARNs, org role mapping; verified vs inferred):
  `references/aws-locate-hosting-account.md`
- **Amplify staging/prod promotion** (staging branch from prod head, branch-level env overrides for `NEXT_PUBLIC_*` URLs + rebuild, forwarding server-side env vars into the Next.js SSR runtime via `amplify.yml`, Supabase redirect allow-list per env, subdomain, prod-branch rename ordering, protection, staging login/error-page diagnosis):
  `references/aws-amplify-branch-promotion.md`
- **Unreadable Semgrep check failures — restructure, don't guess nosemgrep**:
  `references/semgrep-unreadable-findings.md`

## GCP

- **Auth mechanics & session policy** (org-killed refresh tokens, ADC rides the
  same policy, headless copy-paste OAuth login, gog-vs-gcloud scope fact):
  `references/gcloud-auth-and-session-policy.md`

### API quotas belong to the credential's owning project

Quotas are charged to the OAuth client's owning project, not the project the
identity is pointed at. Before quoting a quota as "our limit": find the
credential production actually uses (read deployed config for the client ID,
metadata only), map the client to its owning project, then read that project's
quota (`gcloud quotas info list --service=<api>.googleapis.com
--project=<owning-project> --format=json`). Until verified, plan against
published defaults and label headroom UNKNOWN. Label per-user and per-project
limits separately; `quotaIncreaseEligibility: NOT_SUPPORTED` means you cannot
plan on a raise.

### Never state a project ID/number from memory

Resolve project IDs fresh with `gcloud projects list` / `describe` every time —
they go stale and were often never verified. `describe` returns the same
generic permission error for "no IAM access" and "doesn't exist" — say both
possibilities and ask, don't conclude. IDs are globally unique; a taken ID may
be invisible in your org's list. When the user names a project by expected
name-pattern rather than exact ID, surface mismatches instead of silently
substituting an adjacent-looking project.

### Scope check before SA/IAM provisioning

Workload Identity Pools, OIDC providers, and service accounts are
project-scoped by construction. The only account-level exposure is whether the
calling identity has enough role on the target project — and `roles/editor`
can create resources but CANNOT set IAM policy bindings on them (needs
`roles/owner` or `roles/resourcemanager.projectIamAdmin`). Check the calling
identity's actual role before green-lighting a task that ends in
`add-iam-policy-binding`, or an Editor-only identity gets partway through and
hits a permission wall on the binding, not the resource creation.
