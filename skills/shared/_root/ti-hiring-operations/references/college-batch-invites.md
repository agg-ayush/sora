# College batch invites (ADD), end to end

Scope: "schedule <college> candidates for <date>" — a new campus batch of ADD invites, gathered from the form-submissions sheet through verified invite email. Not for a single ad-hoc session (create it directly), the candidate-issue review flow, or pipeline bug fixes. This is orchestration only; it does not fix pipeline bugs.

## Standing resources (same every batch)

- **Form-submissions sheet** (per-college tabs + Form Responses source): `<internal-doc-id>`
- **Count/snapshot sheet** (registration counts per college): `<internal-doc-id>`
- **Invite email template doc** (one tab per college/flow): `<internal-doc-id>` — edit the relevant tab, never full-replace a tab with live reviewer comments.

## Inputs to collect first

- College name (the filter target).
- Date + batch timings: ADD window (e.g. 4pm–9pm IST), batch size cap (default 100 concurrent — the TPM-safe cap; confirm against the model provider before exceeding), session length (default 30 min), VVA included or ADD-only.
- Confirm the email copy in the template doc matches the current flow (ADD-only drops the Deep Dive part) before scheduling.

## Procedure

1. **Gather + filter.** Read the Form Responses tab. Filter to the college by the College column, matching EVERY spelling variation (name, abbreviations, common misspellings). Exclude colliding colleges (e.g. IIIT Allahabad vs MNNIT Allahabad share "Allahabad"). Dedupe by email identity (keep the latest submission per email; log removed dupes). Verify the count against the snapshot sheet and reconcile any gap. Report the final count.
2. **Build the college tab.** Same format as existing college tabs: candidate form fields in the leading columns, a "Removed duplicates" audit block to the right.
3. **Draft the schedule.** Split candidates into batches of the cap across the window at session-length spacing. Assign each candidate a batch number + start time, written beside their rows (aligned to the correct row). Present the batch table (batch → start → count).
4. **APPROVAL GATE — hard stop.** Do NOT create sessions or send emails until the user explicitly approves both the schedule and the email copy.
5. **Send (after approval).** Per candidate: create the session at their batch start, poll until the Meet link is non-null (Meet provisions at ready; retry transient 502s — never send without a real link), build the email from the template (candidate name + their own Meet link + batch times), verify (meet present, only their meet link in the body, times match, no em dashes), then send. Never send on a failed verify. Log every send idempotently (skip already-sent). At the end, re-run once to retry transient failures, then report total sent / failed / any candidate without a Meet link.

## Pitfalls

- **The college filter is the highest-risk step.** College names collide and are misspelled heavily — enumerate distinct College values and confirm inclusions/exclusions before building the tab. Never trust the snapshot count over the form.
- **Two email columns exist** (form-autocomplete vs dedicated contact) and can disagree. Prefer the college-domain address when present, else the dedicated contact column; flag rows where both are valid but differ.
- **Meet links lag.** Poll and retry on transient failures; never send an invite without a real Meet link.
- **Row alignment.** Key batch labels to the candidate's email and actual row order, never an assumed index; read a few rows back to verify.
- **The concurrency cap is a rate-limit constraint, not arbitrary.** Do not exceed the proven safe cap without confirming the model-provider TPM limit.
- **Sheet writes past the existing grid can silently no-op.** Verify a probe cell landed before trusting a large batch-update response; read back boundary rows to confirm alignment.
