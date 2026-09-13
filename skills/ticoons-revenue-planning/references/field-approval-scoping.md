# Field-level approval scoping on narrative writes

Extends the "never write until approved" rule in SKILL.md with a scoping corollary.

**Never bundle an unapproved field into the same write call as an approved one.**

Caught live: description text was explicitly approved by the user (pasted final wording). The same `mcp__ticoons__trilovation_update` call was about to also carry a buyer-field tweak ("fresh grad" → "applicant") that the agent had decided on its own, without presenting it or getting a yes. User response: "who approved the buyer>" — a direct catch of scope creep into a write call.

Rule: when several fields are mid-cleanup in one pass (e.g. reconciling old-system context across description / buyer / value-delta / competitors), treat each field as its own approve-then-write cycle:

1. Show old text vs. proposed text for ONE field.
2. Wait for explicit approval (or edits) on that field.
3. Write ONLY that field via `trilovation_update` — never batch in a second field's text "since we're already in there."
4. Move to the next field only after the previous one is confirmed live.

Batching writes for already-approved fields together is fine; the failure mode is smuggling an unapproved change into a call that also carries something real.
