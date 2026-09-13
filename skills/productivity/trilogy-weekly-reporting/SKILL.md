---
name: trilogy-weekly-reporting
description: Weekly Trilogy reports (lwiti and Athena insights).
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [reporting, trilogy, weekly, lwiti, customer]
---

# Trilogy Weekly Reporting

Umbrella for the two weekly reporting workflows Ayush drives: the **lwiti** (Last Week in TI) Hugo release-notes entry for Athena Applets, and the customer-facing **Athena Report** Google Doc on reviewer QC activity.

## When to Use

- Ayush sends the week's Athena Applets stats (lesson-stats dashboard dump, agent-stats per-session table, screenshot, sometimes a Google Doc link) to publish the lwiti release-notes entry.
- Ayush asks to "build this week's insights doc" / "customer insights" and supplies (or references) the raw weekly reviewer-activity analysis file.
- **Do NOT use** for any other team's lwiti entry, or for non-release-notes edits to the lwiti repo.

## Procedure

### lwiti — Athena Applets release-notes entry (references/lwiti.md)

Repo: `/Users/ayush/Trilogy/lwiti` (`github.com/<org>/lwiti`, Hugo static site). Each Wednesday every internal team appends ONE feature entry to that week's shared Markdown file. **Ayush owns the Athena Applets entry only** — never touch another team's entry. **The committed `CLAUDE.md` in that repo is a different team's (EduLLM-ELA) — ignore it entirely**; this skill is the source of truth.

Key conventions:
- **Release file:** `content/english/releases/MMDDYYYY.md` — Wednesday date of that week, IST (`TZ=Asia/Kolkata date +%m%d%Y`).
- **Image:** `assets/images/MMDDYYYY/AthenaApplets.png`, referenced as `/images/MMDDYYYY/AthenaApplets.png`.
- **The file is shared** — push conflicts are the norm. Never resolve by picking one side; keep every team's entry.
- **Entry shape:** frontmatter `features:` list; Athena Applets entry has `title`, `image`, `content` (1-2 sentence summary that does NOT repeat the bullets), `bulletpoints` (Production output / Reviewer engagement / Agent performance / Review time / Review queue, optional lesson-catalog link), and an `app:` block (`enable: true`, `label: "Try it out"`, `link: "https://<internal-host>/"`). No `button:` block for this entry.
- Bullet math: derive each bullet from the dashboard/agent-stats dump per the reference's stat-to-bullet mapping — don't invent numbers.

Workflow: prep the file/image/entry skeleton in parallel with waiting on remaining data; don't sit idle for all inputs.

### Customer Weekly Insights — Athena Report (references/customer-weekly-insights.md)

Weekly customer-facing summary of external-reviewer QC activity on AI-generated math lessons, for Trilogy (the customer, not internal engineering).

Inputs each week:
1. **Raw weekly analysis file** — search Drive yourself first: `gog -a ayushaggarwal018@gmail.com drive search "External Reviewer Activity Analysis"` (and variants). Only ask the user if nothing matching the current window turns up.
2. **Supabase metrics** — pull yourself. Project ref `mifrsmqobehferwsrlwt` ("learning-app"), already linked via the `supabase` CLI. Tables: `lesson_status_changes`, `lessons`, `comments`, `iterations`, `grades`. Use the exact metric definitions in `references/process-conventions.md` §2/§4 — don't invent SQL.
3. **Optional extras** — article-deviation audit, pre-classified "Top failure categories" file — only if the user supplies them.

Output: Google Doc via `gog docs`/`gog drive`, account `ayushaggarwal018@gmail.com`, in My Drive folder `Customer Weekly Reports` (create if truly absent). Title: `Athena Report - [Week of <start>-<end>, 2026]`. Do NOT auto-share — hand back the link.

Process: get the analysis file → query Supabase for the core metrics → check/create the folder → build the doc per the stable structure in `references/process-conventions.md` → run the §11 checklist (internal jargon, un-hyperlinked lesson IDs, missing blank lines between bold-label fields, `it#` shorthand, redundant metrics) → create the doc and return the webViewLink.

## Pitfalls

- Touching another team's lwiti entry — Ayush owns Athena Applets only.
- Resolving a shared-file push conflict by picking one side — always keep every team's entry.
- Following the lwiti repo's committed `CLAUDE.md` — it's a different team's instructions, not this entry's.
- Guessing lwiti bullet numbers — derive from the actual stats dump per the reference's math.
- Asking the user for the weekly analysis file without searching Drive first.
- Inventing Supabase SQL instead of using the reference's business definitions.
- Auto-sharing the Athena Report — create and hand back the link; Ayush distributes.
- Skipping the §11 finalization checklist before creating the doc.

## Verification

- lwiti: the week's `MMDDYYYY.md` contains the new Athena Applets entry alongside all other teams' entries; image committed at the right path; entry YAML parses.
- Athena Report: doc exists in the `Customer Weekly Reports` folder with the right title convention; every metric traces to a Supabase query result or the analysis file; §11 checklist items all pass; link handed back, no auto-share.

## References

- `references/lwiti.md` — full frontmatter + entry templates, weekly workflow, git/push flow, hard never-do rules.
- `references/customer-weekly-insights.md` — full input list, process, edge cases (inactive reviewers, no-activity weeks).
- `references/process-conventions.md` (inside customer-weekly-insights) — metric definitions, doc structure, formatting rules, finalization checklist.
