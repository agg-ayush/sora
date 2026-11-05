# College ADD Batch Invites

Source: remote `ti-hiring-operations/ti-hiring-batch-invites/SKILL.md`; frontmatter/title removed.


Run a college's ADD invite batch end to end: gather candidate names from the form-submissions sheet, build a college tab, draft the schedule, get it approved, then create sessions and send the verified invite emails. Candidate emails use the BARE site link, never per-candidate session URLs. This skill is the orchestration; it does not fix pipeline bugs.

## Standing references (same sheets every batch)

- **Form-submissions sheet** (per-college tabs + the Form Responses source): `<internal-doc-id>`
- **Count/snapshot sheet** (registration counts per college): `<internal-doc-id>`
- **Invite email template doc**: `<internal-doc-id>` (one tab per college/flow; edit the relevant tab, never full-replace a tab that has live reviewer comments)

## When to Use

- "Schedule <college> candidates for <date>" / a new campus batch of ADD invites.
- Don't use for: a single ad-hoc session (use the orchestrator create-session directly), the candidate-issue review flow, or pipeline bug fixes.

## Inputs to collect first

- **College name** (the filter target).
- **Date + batch timings**: the ADD window (e.g. 4pm-9pm IST), batch size cap (default 100 concurrent, the TPM-safe cap), session length (default 30 min), and whether VVA is included or ADD-only.
- Confirm the email copy in the template doc matches the current flow (e.g. ADD-only drops the Deep Dive part) before scheduling.

## Procedure

1. **Gather + filter.** Read the form-submissions sheet's Form Responses tab. Filter to the college by the College column, matching EVERY spelling variation (the college name, abbreviations, common misspellings). Exclude colliding colleges (e.g. IIIT Allahabad vs MNNIT Allahabad share "Allahabad"). Dedupe by email identity (keep the latest submission per email; log removed dupes). Verify the count against the snapshot sheet; reconcile any gap before proceeding. Report the final count.
2. **Build the college tab.** Create a tab named for the college in the form-submissions sheet, in the same format as the existing college tabs: candidate form fields in the leading columns, a "Removed duplicates" audit block to the right. Write the deduped list.
3. **Draft the schedule.** Split the candidates into batches of the cap size across the window at the session-length spacing. Assign each candidate a batch number + start time; write those into columns beside the candidate rows (aligned to the correct row). Present the batch table (batch -> start time -> count) to the user.
4. **APPROVAL GATE. Stop here.** Do NOT create sessions or send emails until the user explicitly approves the schedule and the email copy. This is a hard stop.
5. **Send (after approval).** For each candidate: create the session at their batch start, poll until the Meet link is non-null (Meet provisions at ready; retry on transient failure), build the email from the template with the candidate's name + their own Meet link + their batch times, VERIFY (meet present, only their meet link in the body, times match, no em dashes), then send. Never send on a failed verify. Log every send (idempotent — skip already-sent). At the end, re-run once to retry transient failures, then report total sent / failed / any candidate who could not get a Meet link.

## Pitfalls

- **The college filter is the highest-risk step.** College names collide and are misspelled heavily. Always enumerate the distinct College values and confirm the inclusions/exclusions before building the tab. Never trust the snapshot count over the form.
- **Two email columns exist** (a form-autocomplete one and a dedicated contact one) and they sometimes disagree. Prefer the college-domain address when present, else the dedicated contact column. Flag rows where both are valid but differ.
- **Meet links lag.** Meet creation can transiently fail (Google 502) — poll and retry; never send an invite without a real Meet link.
- **Batch/candidate row alignment.** When writing batch labels into the tab, key them to the candidate's email and the actual row order, not an assumed index — verify a few rows read back correctly.
- **Concurrency cap is a rate-limit constraint, not arbitrary.** Do not exceed the proven safe cap without confirming the model-provider TPM limit.
- **Sheet writes past the existing grid can silently no-op.** Verify a probe cell landed before trusting a large batch-update response; read back boundary rows to confirm alignment.

## Verification

- The college tab exists with the deduped count matching the reconciliation.
- Every candidate has a batch + start time in the tab, aligned to the right row.
- After send: the send log shows status=sent for all (minus logged failures), every sent row has a non-null meet_url and a message_id, and the count matches the tab.
