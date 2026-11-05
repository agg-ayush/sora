# Invite mail: render and batch send

Use when sending the candidate invite mail (single test or a whole college batch) from startgreat.

## Modes

- **Mail-only (decoupled):** default when assignments are not confirmed yet. Send the invite now, book sessions later through the intake path. The body carries no Meet link and no per-candidate session URL (the Meet arrives with the calendar invite at booking). Call no booking/intake API in this mode.
- **Book + send:** book through the intake path (rowRef/upsert, the same path the batch uses), then send.

## Procedure

1. **Render from the canonical template doc's HTML block, not a local scratch copy.** Pull the current HTML block from the template doc tab before each batch. A scratch copy drifts from edits reviewers accepted in the doc, and the test mail silently regresses.
2. **Settled formatting:** the whole schedule line is one bold unit including the zone, `<strong>{date}, {start} - {end} IST.</strong>`. Per-piece bolding leaves "IST" plain and gets flagged. The "cannot be paused / join by {join_deadline} IST" line is bold. No em dashes, no internal notes, no college-specific intro lines left in the copy.
3. **Pre-fill one HTML file per recipient** from a manifest in sheet order: name, date like `Thursday, 1 October 2026`, start/end as `H:MM`, join deadline = slot start. Assert zero `{placeholder}` tokens remain across all files before any send.
4. **Test mail to Ayush first** (`ayushaggarwal018@gmail.com`). Inspect the filled schedule line yourself (grep the rendered `<strong>` span) before saying it matches. Send the batch only after he confirms.
5. **Delegate the batch to a subagent** so hundreds of sends stay out of the main chat. Give it only the pre-filled files + manifest. Never put `{...}` template markers in the delegate goal: delegate_task rejects unexpanded markers, and the subagent should do zero templating. For 1-3 late recipients, send inline.
6. Send command: `gog --account <ops-mailbox> --client startgreat gmail send --to <email> --subject '<subject>' --body-html-file <file>` with `GOG_KEYRING_PASSWORD` exported from `/home/ubuntu/.hermes/.env` (never echo it). Throttle about 1 send/sec, log failures and continue.
7. Re-verify the subagent's sent/failed counts against its log before relaying them. Right after a big batch the Gmail query quota is exhausted; the send log's message IDs are the evidence until the quota resets.

## When the doc is edited

Any copy change goes to the doc first (both the copy section and the HTML block), then re-render from the doc. Updating only the send-side file or only the doc desyncs them. When a reviewer's doc comment asks for a change, check the doc body itself, not just the comment thread, before claiming the text is or is not there.

## Late additions to an already-sent batch

1. **Add them to the college tab, not the Master sheet.** The batch rows live in the college tab. Check where the rest of the cohort actually lives before writing.
2. **Write to an explicit row range** (`<Tab>!A{n}:K{n}` for the next empty rows), never a bare append. Append anchors to the end of the used range, which on tabs with batch/audit columns to the right lands rows offset into the wrong columns.
3. **Match existing rows exactly:** same column order, the college value spelled like the other rows, batch label + start time in the batch columns. Extend the tab's alternating-color banding range to cover the new rows (banding does not auto-grow past its end row).
4. **Format only the new rows.** Never reapply a column-wide format (wrap, clip, width) to fix new rows; it changes how every existing row renders. Copy an existing row's format onto the new rows instead (`copyPaste` with `pasteType: PASTE_FORMAT` via the Sheets batchUpdate).
5. Put them in the batch the user names and send per the procedure above.
