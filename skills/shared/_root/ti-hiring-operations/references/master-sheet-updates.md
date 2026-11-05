# Master sheet updates (adding a college cohort)

Spreadsheet: "Innovation Catalyst Internship Application | 2027 & 2028 (Responses)", id `<internal-doc-id>`. Tabs: per-college cohort tabs (e.g. `IIT Patna`, `IIIT Allahabad`, `IIIT Kota`, `MNNIT`, `DTU`; some are hidden, so list every tab via the API rather than reading the first one), `Form Responses 1` (raw form), `Master sheet` (gid 96442833, funnel tracker).

## Procedure
1. Read-only first. Use `gog --account ayushaggarwal018@gmail.com --readonly sheets get <id> "'<Tab>'!A1:S2000" -j` (quote tab names with spaces). Get tab list/grid sizes via `gog ... api call sheets v4 spreadsheets.get` with a `fields` mask. Delegate the bulk audit to a subagent, then spot-verify its key counts yourself with a short script before reporting.
2. Map columns by letter. Master: A Name, B Email, C Phone, D College, E Graduation year, F GitHub, G-J ADD (Sent, Submitted, Result, Feedback Summary), K-N VVA (same four), O Move to CCAT, P CCAT Sent, Q CCAT Submitted, R-S CCAT Attempt-1/2. No scheduling time or link columns. Values in use: `Yes` for Sent/Submitted, `Passed`/`Failed` for Result. No formulas, dropdowns or protections at last check.
3. Cohort tabs: A-G = timestamp, login email (B), full name (C), entered email (D), phone, college, graduation year. Some tabs add ADD batch / ADD start (IST). A separate "Removed duplicates" block sits to the right (J+ or L+); it is not candidate data, exclude it.
4. Reconcile against Master by login email B, then entered email D, then phone. Name-only matches are collisions, not identity matches. Report exact matches whose Master college label conflicts with the cohort tab; do not relabel or duplicate them without a decision.
5. Check capacity: Master grid has a fixed row count; appending a cohort can need the grid expanded first.
6. GitHub (F) comes from `Form Responses 1` column H when it contains a valid GitHub handle/profile; I is the self-described project and J is the project link. The original H/I headers are `GitHub handle` and `What did you build that nobody asked you to build?`; they were restored after a regression. Older response rows may still have `Batch N` and IST start times in H/I, so validate values row by row instead of trusting the header alone. Some values are bare handles or text; some candidates submitted the form more than once, so choose the response deliberately.
7. Present to the user: a column-letter table of what each field means, where it would come from and what decision it needs; the counts; the conflicting records. Then offer a row-by-row dry run. Write nothing until the user settles the open decisions.

## Slotting a cohort for ADD sessions
When asked to slot a cohort tab for scheduling:
1. Confirm the date and window in IST. The intake contract takes IST directly (`scheduledStartIst`, see `routes-scheduling.ts` and `ist.ts` on `origin/main`); don't convert to UTC for the payload.
2. Every slot must END inside the window, not just start in it. Default shape: 30-minute sessions with a 15-minute gap (e.g. window 7-9: 07:00, 07:45, 08:30). Split students evenly across slots in sheet order and show the slot table before writing.
3. Build the intake payload (rowRef `<Tab>!<row>`, `op: upsert`, name, email, start, duration) as a local file, leaving assignment/problem fields empty when assignments aren't finalized.
4. If the user says "just update the sheet, don't schedule yet", write only the tab's existing `ADD batch` and `ADD start (IST)` columns and call no scheduling endpoint.
5. Locate those columns by reading the header row and matching the header text; never assume letters from another tab. Write, then read back header + a few rows per batch to confirm values sit under the right headers before reporting done. An off-by-one write must be cleared from the wrong cells as well as rewritten.

## Filling eval-pipeline columns on a cohort tab
Some cohort tabs (e.g. DTU, in the `TI HIRING COPY` spreadsheet `<internal-doc-id>`) carry per-candidate eval columns after `ADD start (IST)`: Session ID, Candidate ID, Assignment ID, GCS capture copy, Eval viewer, Eval result. Locate them by header text, as above.
1. Fill only the operational columns: session id, candidate id, assignment id, the GCS capture-copy path and the viewer link in the same format the other filled rows use (read a filled row first and match it).
2. Leave `Eval result` empty. It is a human-owned verdict column (values like `review`/`yes`/`no`); never write evaluator signals, an "all yellow" summary or a pass guess there.
3. Do not add the evaluator's per-signal values anywhere else in the sheet either; they live in the report (`transcript-eval/cache/<session>/<assignment>/report.json` in the eval bucket) reached via the viewer link.
4. Literal placeholder values starting with `-` (e.g. `---`) get parsed as CLI flags by gog; pass them via a JSON/values file or after `--`.
5. Re-locate the target row by email from a fresh read immediately before writing; never reuse a row number from an earlier read. Rows get re-sorted or inserted by other editors, so a cached row number silently writes into another candidate's row. If the user names a row, trust it over your cache, and clear any cells you wrote to the wrong row.
6. Read the row back after writing and report the cell values.

### Counting and labeling the eval columns
- Count column values from the JSON grid (`sheets get ... -j`), never a TSV/line scan: form cells contain embedded newlines that split rows and undercount.
- Before reporting "N failed/empty", reconcile against the user's own count; if they differ, re-read and recount rather than defending the first number.
- The `Eval result` column is human-owned, but write explicit labels when the user directs them. Vocabulary in use: `review`, `yes`, `no`, `forfeited`, `empty_transcript`, plus `empty_transcripts` / `eval_error` in the status column.
- Triage for rows with a session but no report, by orchestrator session status and capture contents: `terminated` (forfeited / ready_expired_media_gate) -> `forfeited`, no eval; `ended` with zero candidate prompts in the capture -> `empty_transcript`, no eval; `ended` with real transcript content -> fire the eval, label `review`. An evaluator report that abstained with "zero transcript files" is an empty transcript, not a pipeline failure; relabel it rather than re-running.
- A filled Session ID column does not mean an eval exists. Before classifying rows as "evaluated but unfilled", check each session id against the eval bucket's report listing; rows with a session id but no report are a never-evaluated cohort and go through the triage above.
- Locate rows for batch writes by session id (or email) from a fresh read; if a target session id is absent from the Session ID column, report it and write nothing rather than guessing a row.
- Present the breakdown (counts per bucket, with the evals in flight separated from the already-linked reports) before writing labels, then write and re-read the column distribution to verify.

### Pulling captures and running evals
- S3 capture prefixes are `ti-ses-<uuid>` (dash). Building `ti-` + the `ses_<uuid>` id yields `ti-ses_<uuid>` and every get 404s, which looks like a credential flake. On repeated 404s check the key shape against a real `aws s3 ls` listing before suspecting auth.
- When overriding env on the Cloud Run eval job, set `SESSION_ID` explicitly; an empty override fails the execution immediately.
- Run eval babysitting, bulk uploads and multi-row sheet writes in a subagent or background process, never as long foreground commands in the main chat: the user keeps working in the foreground and long foreground commands get interrupted.

## Mapping an email-correction form onto a batch sheet
When students submit a "my email was wrong" correction form and the user asks to map them to their batch slots:
1. Map only; write nothing unless told. Report a slot table: survey #, name, batch, row, the email the sheet holds, the corrected email from the form.
2. Pull the whole sheet as a JSON grid with a generous range (e.g. `A1:F1000`, then confirm the returned row count). A narrow fixed range silently drops rows added since, and TSV line scans split rows on embedded newlines. Either one makes present students look missing.
3. Match by name first. The email is the field being corrected, so email-only matching misses most of them. Then classify each match:
   - verified: the sheet's email equals the form's wrong or corrected email
   - name-only: same name but the sheet holds a different email. Flag these for a human to check. Show both emails side by side.
4. Never label a row "unchanged" or "same" based on the form's own before and after columns. That label reads as "the sheet already has this email". Always show the sheet's actual cell value next to the form's corrected value.
5. Before calling anyone absent, search their roll number (e.g. `<roll-no>`) as a substring across every cell of the full grid, and run fuzzy name tokens too. Don't count shared first names (two different Ashishes or Mayanks) as matches. Check the roll number or email before accepting one. If one digit of the roll number is off, or the name order is flipped, call it ambiguous and show both candidate rows rather than picking one.
6. Lead the summary with the corrections that affect invites: rows whose sheet email is broken or differs from the correction, and corrected students with no row. List the slot time when the sheet has one.

## Rules
- Batch/start-time assignments are not evidence an invite was sent or work submitted. Sent needs mail/invite records; Submitted needs completion records; Result/Feedback need human-approved verdicts, never draft evaluator output or evaluator labels like "weak hire" mapped silently to Passed.
- ADD evidence never fills VVA columns and vice versa; CCAT fields come from their own decision/test records.
- Where login and entered email differ (common), ask which is canonical; malformed entered emails exist.
