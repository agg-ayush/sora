---
name: customer-weekly-insights
description: "Build the weekly customer-facing 'Athena Report' Google Doc for Trilogy curriculum QC (reviewer feedback summary) from a raw analysis file + Supabase metrics."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [reporting, customer-facing, supabase, google-docs, trilogy]
    related_skills: [google-workspace]
---

# Weekly Customer Insights Report (Athena Report)

Produces the weekly customer-facing summary of external-reviewer QC activity on
AI-generated math lessons, for Trilogy (the customer — not internal engineering).

## Trigger

User says something like "build this week's insights doc" / "customer insights" and
supplies (or references) the raw weekly reviewer-activity analysis file.

## Inputs each week (mixed-provider model)

1. **Raw weekly analysis file** — first try to find this yourself: search Drive
   with `gog -a ayushaggarwal018@gmail.com drive search "External Reviewer Activity
   Analysis"` (and variants like `"<Reviewer> - Key"` / current week's date range)
   before asking the user. These docs land in the same My Drive root as prior
   Athena Reports/analysis docs. Only ask the user to provide the file if nothing
   matching the current window turns up.
2. **Supabase metrics** — pull these yourself. Project ref `mifrsmqobehferwsrlwt`
   ("learning-app"), already linked via `supabase` CLI (`supabase projects list`
   shows it LINKED). Tables: `lesson_status_changes`, `lessons`, `comments`,
   `iterations`, `grades`. Use the exact metric definitions in
   `references/process-conventions.md` §2 and §4 — don't invent SQL, state the
   business definition and query directly.

   Reference prompt the user historically sent to another agent for this (use as
   clarification of exact definitions, not a literal template to relay anywhere —
   you query Supabase directly yourself):
   > "get me the following for the past week (<start date> to today)
   > 1. total and unique count of lessons that changed statuses to "Ready for
   >    Customer Review"
   > 2. average number of customer iterations (status changes from "Ready for
   >    Customer Review" to "Customer feedback provided") for lessons that got
   >    approved (status changed to "approved with comments" or "approved by lwai"
   >    or "uploaded to athena") for
   >    a. past 1 week
   >    b. past 2 months"
3. **Optional extras** (ad hoc, not every week): article-deviation audit, a
   pre-classified "Top failure categories" file. Only fold these in if the user
   supplies them — don't assume they exist.

## Output

- **Google Doc**, created via `gog docs`/`gog drive`, account
  `ayushaggarwal018@gmail.com`.
- **Location:** folder `Customer Weekly Reports` in My Drive (create if it doesn't
  exist yet — check with `gog drive search` / `gog drive ls` first, only create if
  truly absent).
- **Title convention:** `Athena Report - [Week of <start>-<end>, 2026]` (e.g.
  `Athena Report - [Week of Jul 13-20, 2026]`).
- Do not auto-share with anyone — just create the doc and hand back the link;
  Ayush handles distribution.

## Process

1. Get the raw analysis file from the user (ask if not yet provided).
2. Query Supabase yourself for the core metrics (submission counts, approval
   counts, avg customer-iteration counts — both within-window and full-lifecycle
   where possible). Exact prompt templates: `references/process-conventions.md` §4.
3. Check/create the `Customer Weekly Reports` folder in My Drive.
4. Build the doc following the stable structure and conventions in
   `references/process-conventions.md` (§5 structure, §6 formatting rules, §7-§9
   for edge cases like inactive reviewers or no-reviewer-activity weeks).
5. Before finalizing, run the checklist in §11 of the reference doc (internal
   jargon, un-hyperlinked lesson IDs, missing blank lines between bold-label
   fields, `it#` shorthand, redundant metrics).
6. Create the Google Doc with `gog docs`/`gog drive` and return the webViewLink.

## Critical conventions (do not violate)

- **Customer-facing language only** — never internal filenames, "QC gap",
  "enforcement failure", "Uploaded to Athena" as a customer concept, bucket
  numbers, repo paths.
- **Never reword reviewer quotes** — verbatim only, they're evidence.
- **Objective vs Subjective test:** Objective = generalizable pattern (applies to
  any lesson). Subjective = tied to that specific lesson's content. (NOT
  "verifiable vs preference" — that was tried and rejected.)
- **Omit inactive reviewers entirely** — no "Reviewer: 0" rows.
- **No trailing "why we're showing you this" framing** — state data, let it speak.
- **QC gate promotions ("QC Audit — colleague AI Agent" entries) MUST be included.**
  These are `old_status = 'Ready for Internal Review'` → `new_status = 'Ready for
  Customer Review'` changes — the QC gate that promotes a lesson into the customer
  review queue. This IS the mechanism lessons use to reach the customer, not a
  revert/exclusion case. Include them in "lessons submitted for review" counts at
  full weight. (Corrected from an earlier, wrong assumption that these were
  auto-restore reverts to be excluded — verify via old_status/new_status if ever
  unsure.)
- **Blank line between every `**Label:**` field** in per-item blocks (Google Docs
  markdown-paste quirk — without it, consecutive bold lines collapse together).
- Lesson IDs hyperlinked as `https://<internal-host>/lesson?lesson=<ID>` with
  `+` → `%2B`; link once per section, not every mention.
- Iteration refs written as `iteration 7`, never `it7`.

Full detail (document structure evolution, rejected approaches, article-alignment
section rules, no-reviewer-activity substitute content pattern) is in
`references/process-conventions.md` — read it in full before building a doc,
especially the first few times.
