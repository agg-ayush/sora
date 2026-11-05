---
name: ti-hiring-operations
description: Operate TI hiring assessments, invites, and eval backfills.
version: 1.1.0
author: Ayush, Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [ti-hiring, recruiting, scheduling, gmail, transcript-eval]
---

# TI Hiring Operations

## When to Use

Use for TI hiring assessment scheduling and admin calls, candidate email, college ADD invitation batches, batch outcome/incident review, and transcript-eval capture backfills. Do not use the college-batch procedure for a single ad-hoc session or a pipeline code fix.

## Core Procedure

1. Read the relevant reference below. For infrastructure work, also read `references/architecture-and-ops.md` and the other preserved operational references in this skill.
2. **Admin / candidate:** Resolve the candidate and session from the live orchestrator. Use the ops-box `ti-hiring-admin.sh` helper (not a printed bearer token). Classify status and end reason before booking, terminating, rescheduling, or communicating. Treat unzoned times as IST and confirm UTC conversion. For multi-part schedules, restate ADD and VVA unless the approved flow is explicitly ADD-only. Verify every sent message in startgreat's Sent mail.
3. **College ADD batch:** Reconcile form rows with the snapshot, enumerate college spelling variants and email disagreements, dedupe by email, build/read back the college tab, and draft the cap-safe schedule. **Stop for explicit approval of schedule and email copy.** Only then create each session and verify its Meet link and individualized mail before sending; persist per-candidate idempotent outcomes. See `references/batch-invites.md`.
4. **Transcript eval:** Dedupe by session ID; calculate capture digests from GCS; dispatch with all five environment fields, isolated per execution for authorized parallel runs; persist IDs immediately and read back the execution environment. Monitor completion and sheet writes separately. See `references/transcript-eval-backfill.md`.

## Hard Gates and Conflicts

- Never print credentials; use local token/keyring stores. Do not initiate GCP project control-plane changes without the owner's specific approval. A candidate disposition email requires approval for **that email**, and any transcript-based email requires a fresh session-to-recipient lookup just before send. Never send an invite without a real Meet link.
- Source conflict: the older admin helper lists `PATCH /v1/sessions/:id` with `scheduledStartAt`, but the operations procedure says there is **no reschedule API** and directs force-destroy + rebook. Verify the live route/semantics before any reschedule; never assume PATCH moves the slot. See the verbatim source facts in `references/admin.md`.
- Treat an accepted API call, booked session, sent mail, merged PR, deployed image, completed eval, and present report as separate facts; verify the exact target after each action.

## References

- `references/admin.md` — general operations, admin API, scheduling, candidate communications, infra/incident/evaluation gotchas, and legacy reference pointers.
- `references/batch-invites.md` — college sheet IDs, reconciliation, schedule, approval, send, verification.
- `references/transcript-eval-backfill.md` — GCS digests, Cloud Run dispatch, execution/report checks, DTU writes.
