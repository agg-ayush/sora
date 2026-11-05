---
name: ticoons
description: Use when working on TiCoons Trilovations of any kind.
version: 0.1.0
author: Ayush Aggarwal
license: MIT
metadata:
  hermes:
    tags: [TiCoons, Trilovation]
    related_skills: [ticoons-revenue, brainlift-writer, plain-language-validator]
---

# TiCoons

Router skill for any Trilovation work on the TiCoons platform. Load the specialist skill for the task at hand; do not attempt the work from this skill alone.

## When to load which

| Task | Skill to load |
|---|---|
| Drafting or revising narrative fields, revenue plans, proposals, milestones, CEO decision-log entries, red flags, quarter transitions | `ticoons-revenue` |
| Creating or extending a brainlift (DOK-layered document) via interview | `brainlift-writer` |
| Checking any prose before it ships (narrative fields, decision entries, relay messages) for sentences that impress instead of inform | `plain-language-validator` |

## Standing rules that apply across all TiCoons work

- Every field write is user-approved first: exact text shown, approved, then written, then read back to verify.
- Before stating any platform state (milestone list, due dates, completion, which items exist), pull it live with the ticoons MCP (`milestone_list`, etc.). Session summaries and earlier turns drift from the record; answer from the fresh read and say what changed versus what you believed.
- When the user asks to move a milestone date, check the live record first (it may already be changed), then update and read the returned record back.
- Never take unrequested platform actions. Reading context and writing it into the record are separate requests.
- No Oxford commas, no long em dashes (use a comma, colon, or period) in anything written to the platform.
- Internal session context, names, and comms never leak into platform-facing text.
- Before drafting any field or decision-log entry, pull 2-3 accepted examples from other Trilovations and match their length and shape. One example is not a pattern.
- Only claims the source material backs. No invented color (durations, frequencies, history) to make a field read better.
- Every line must be self-contained for a cold reader: no internal shorthand ("the December window") the reviewer never saw.
- A field holds what its name says. Drop framing that argues the field should not exist ("X is not a competitor") and jargon nobody outside the session uses ("honest competitive risk").
- CEO decision-log entries are decisions about how the product works: decision, rule, why. Never an event log ("PR merged", "wiring proven") and never context restated from another field. Keep implementation specifics (API operation lists) out.
- After logging a decision, check every milestone still aligns with it and propose milestone edits in the same pass.
- Mark a milestone complete only when its stated proof exists in its stated environment (a simulator run does not complete a "proven against the real service" milestone). Confirm with the user before marking.
- Approved revenue items are immutable. A tier change that fails against them is a stakeholder conversation, not a retry.
- Source of the specialist skills: github.com/<org>/ticoons-libre-agents/tree/main/skills.
