---
name: hosting-sla-fact-check
description: "Use when comparing hosting platforms. Price every option."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [Research, Hosting, SLAs, Cloud]
    related_skills: [grounded-citations]
---

# Hosting SLA fact checks

## When to Use

Use for cloud-hosting vendor comparisons where availability commitments, cold starts, operating cost and backend dependencies affect an architecture decision.

## Procedure for a hosting decision

1. **Diagnose reported slowness before treating it as a platform problem.** When the user says the current deploy is slow, pull real request durations from the runtime logs first (Amplify: `aws logs filter-log-events --log-group-name /aws/amplify/<app-id> ... | grep -oE 'Duration: [0-9.]+ ms' | sort -n | tail`). Multi-second durations or hard-timeout values (e.g. exactly 30000 ms) point at app work blocking the request (a synchronous build on first load), which no platform move fixes; card that as an app fix separately. A TTFB probe from a warm route does not reproduce what the user felt.
2. **Use only the evaluation axes the user cares about.** Do not invent weighting axes (geography/latency, contractual SLA) and let them drive the pick; confirm weights when unsure. A number stated for emphasis is not a hard target.
3. **Price every credible option, not the shortlist already in mind.** When the user asks for numbers, dispatch a researcher with the full candidate list (current platform; AWS container/VM/serverless family; GCP Cloud Run; Vercel; Cloudflare via OpenNext; Netlify; Railway/Render/Fly) plus an instruction to add anything credible missing. Required per option: cost for one env and both envs with formulas, streaming support, response/body/timeout caps, verbatim SLA quote with URL, cold-start evidence, ops burden.
4. **Model environment parity explicitly.** Staging identical to prod doubles per-env compute on container/VM platforms, but team/account-floor platforms (Vercel, Cloudflare, Netlify) often cover both envs under one floor; show both columns so this difference is visible.
5. **Apply the end-state filter.** Drop options with a hard conflict against a known later requirement (no streaming for a chat feature, response caps below document payload sizes) rather than planning a migration.
6. **Verify ownership/governance of the hosting account before recommending it.** For Vercel, list the teams the user can actually see (Vercel MCP `list_teams`); a personal team or a colleague's personal team is the wrong home for an org production system. If no org-owned team is visible, present the fork: get added to an existing org team, create one (cost + who pays), or pick another platform.
7. Present a compressed table (both-env cost, streaming, SLA, the one catch per option), then a lean conditional on the open governance question, and leave the pick to the user.

## Evidence rules

- Read the AWS SLA index **and** the linked service-specific contract; an index listing can overturn assumptions that no SLA exists. Distinguish the percentage from its eligibility (region, AZ spread, healthy targets), measurement window, exclusions, and service-credit remedy. Do not convert separate component SLAs into an end-to-end application guarantee.
- Verify serverless runtime limits on the particular hosting product, not generic underlying compute documentation. Community cold-start numbers are application anecdotes, not service percentiles.
- Separate build-machine RAM, execution-instance lifetime, request timeout, response/body limits, and per-instance concurrency. Explicitly mark missing vendor specifications rather than importing limits from Lambda or containers.
- Model low-traffic container/VM costs with explicit operating hours and baseline load balancer, public IPv4, provisioned memory, storage, and variable LCU/traffic assumptions. Calculate with a tool and label minimum sizing as untested until the app runs.
- Check current product eligibility before analyzing architecture: a product may remain operational for existing accounts while rejecting new customers.
- A status-page feed may show only recent incidents or duplicate IDs after migration. Inspect incident records and coverage date, deduplicate, distinguish regional/customer/product impacts, and never infer a 12-month availability percentage from examples.
- For cited briefs, pair URLs with verbatim fetched-page quotes in an evidence CSV and independently re-fetch decision-driving legal/price claims. Put source links next to each sentence; for coverage validators that split at punctuation followed whitespace, use `claim [source](URL)[n]. Next claim` so adjacent claims are counted separately.
- If a legal URL's Markdown/text extraction returns a navigational summary or empty shell, inspect the browser-rendered HTML before quoting a contractual percentage; verify the exact defined-term wording, punctuation, and eligibility there.
- Cross-check a vendor's canonical pricing page against its detailed billing examples when regional egress basis differs (destination versus origin). Model the expensive plausible interpretation and explicitly request vendor billing confirmation rather than choosing one silently.
- For confidential-document applications, check hosting terms for prohibited data classes (including financial and government identifiers) independently of technical upload capability, and flag a counsel/negotiated-terms gate when the contract forbids relevant data.
- For edge-platform comparisons, separate account/team minimums from per-project and per-seat fees; separate preview/branch deploys from production deploys, and distinguish build-minute meters from runtime CPU/memory. Check whether a Next.js adapter executes SSR in Workers, a regional Function, or truly at the edge rather than inferring this from the product name.
- Read service-specific enterprise SLA text before general enterprise terms: a Workers runtime SLA can override a broader CDN uptime statement. Do not promote an enterprise percentage to a self-serve plan, or a marketing-page percentage to a legal commitment when the order-form SLA is unpublished.
- Reconcile contradictory CDN pricing pages against the account's actual billing mode and workload eligibility, especially when large-file distribution is excluded. For streamed legal documents, distinguish buffered body caps, streamed-response caps, CPU time, wall duration, isolate memory, and static-asset size.
