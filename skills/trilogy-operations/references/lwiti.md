---
name: lwiti
description: "Use when Ayush sends weekly Athena Applets stats to publish the Athena Applets entry in the lwiti (Last Week in TI) Hugo release-notes repo. Covers the feature-YAML schema, stat-to-bullet math, the contested shared-file git/push flow, and the hard never-do rules."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [lwiti, athena-applets, release-notes, trilogy, weekly, hugo]
    related_skills: [google-workspace]
---

# Athena Applets — Weekly lwiti Release Notes

## Overview

`lwiti` ("Last Week in TI") is a Hugo static site (`github.com/<org>/lwiti`) publishing weekly Trilogy Innovations release notes. Each Wednesday every internal team adds **one feature entry** to that week's shared Markdown file. **Ayush owns the Athena Applets entry only** — never touch another team's entry (Marauders Map, EduPaid, Mosaic, BrainTrust, Alpha Coach, Finance Factory/Collections, Legal Intake, RebaseAI, EduLLM-* variants, etc.).

Athena Applets = an AI pipeline that generates, reviews, and fixes K-7 math lessons (CCSS + TEKS standards) for the Athena learning platform (`<internal-host>`).

Local clone: `/Users/ayush/Trilogy/lwiti`.

> The committed `CLAUDE.md` in this repo is a **different team's** (EduLLM-ELA) instructions. Ignore it entirely — this skill is the source of truth for the Athena Applets entry.

## When to Use

- Ayush sends the week's stats (a "lesson stats" dashboard dump, an "agent stats" per-session table, a screenshot, sometimes a Google Doc link) to publish the Athena Applets release-notes entry.
- Don't use for: any other team's entry, or any non-release-notes edit to the repo.

## Repo conventions

- **Release file:** `content/english/releases/MMDDYYYY.md` — the **Wednesday** date of that week, IST (e.g. `07222026.md` for 22 Jul 2026). Get it with `TZ=Asia/Kolkata date +%m%d%Y`.
- **Image:** `assets/images/MMDDYYYY/AthenaApplets.png`, referenced in YAML as `/images/MMDDYYYY/AthenaApplets.png`.
- **The file is shared** — every team appends to the same file the same week, so **push conflicts are the norm, not the exception** (see Git flow). Never resolve a conflict by picking one side — keep every team's entry.

### Frontmatter template (only when creating a brand-new week's file — usually another team beats you to it)

```yaml
---
title: "<D> <Month>, <YYYY> - Last week in TI"
meta_title: "<DD>/<MM>/<YYYY> - Last week in TI"   # format drifts MM/DD vs DD/MM across weeks — match the most recent other entries that week, don't fight it
description: "A review of all the exciting things that happened last week at Trilogy Innovations"
date: <YYYY>-<MM>-<DD>T00:00:00Z
image: "/images/Trilogy Innovations Banner.png"
categories: ["Releases"]
author: "stakeholder"
tags: ["AI", "Releases"]
draft: false

features:

---
```

### Athena Applets feature entry template

```yaml
  - title: "Athena Applets: <punchy one-liner reflecting this week's real headline>"
    image: "/images/<MMDDYYYY>/AthenaApplets.png"
    content: "<1-2 sentence summary. Must NOT repeat sentences that appear in the bullets below.>"
    bulletpoints:
      - "**Production output** – <lessons approved this week, split by grade AND by CCSS/TEKS>. <new lessons generated this week, by grade if available>."
      - "**Reviewer engagement** – <total iterations>: <feedback rounds> (<%>), <approvals> (<%>). <total comments>, <comments/lesson>."
      - "**Agent performance** – <fix rate>% fix rate: <fixed> of <total> issues resolved across <N> lessons with completed edit work this week. <unresolved count> unresolved<, concentrated in detail if useful>."
      - "**Review time** – Average of <X> minutes per iteration across <Y> total minutes."
      - "**Review queue** – <total> total: <only grades with a non-zero count, largest first>."
      # Optional, only if the catalog doc is being kept in sync that week:
      - "**Complete lesson catalog** – See the full list of all uploaded lessons across grades in this [lesson catalog](<google-doc-link>) with direct links to each lesson."
    app:
      enable: true
      label: "Try it out"
      link: "https://<internal-host>/"
```

No `button:` block for this entry (other teams use it; Athena Applets doesn't link out).

## Weekly workflow

1. **Ayush sends the week's data** across 2+ messages plus a screenshot (pasted image → local temp file path) and sometimes a Google Doc link. Don't wait idle for all of it.
2. **Prep immediately, in parallel with waiting on remaining data:**
   - `git fetch` + merge `origin/main` (another team has usually already created/added to this week's file).
   - Copy the screenshot into `assets/images/MMDDYYYY/AthenaApplets.png`.
   - Cross-check the "approved by grade" lesson IDs against the local grade catalogs (see below); add any missing rows (blank name cell if the name isn't known yet).
3. **Compute the bullets** from the raw stats (see math rules below).
4. **Draft the full YAML entry and show it to Ayush before writing/committing anything he hasn't seen.** He is very specific about phrasing, what to include/exclude, and duplication between the `content` line and the bullets. Iterate on his edits.
   - Completion criterion: he has seen and approved the exact YAML.
5. **Never push without his explicit "good to go"/"push".** Drafting and even committing locally is fine; pushing is not, until he says so explicitly. Hard rule.
6. **Push, resolving conflicts and squashing to one commit** (see Git flow).

## Grade catalog files — `grade_3.md`, `grade_4.md`, `grade_5.md`, `grade_6.md`

Live at the **repo root** (not under `content/`) and are **Ayush's personal working files — NEVER commit them, ever.** They are a running catalog of every live lesson per grade: `| # | Standard ID | Lesson Name | Lesson Link |`.

- Lesson link pattern: `https://<internal-host>/lesson?lesson=<URL-encoded-standard-id>`. `+` in IDs like `TEKS.MATH.CONTENT.4.5.D+1` encodes to `%2B`; parens in `TEKS.MATH.CONTENT.6.12(B)+1` encode to `%28`/`%29`.
- Each week cross-check that week's "approved by grade" IDs against these; add missing rows (increment the row number, update the "List of N live Grade X lessons" header count). **Unknown display name → blank name cell** (an accepted pending pattern). Don't block the push on getting names.
- A Google Doc mirrors these four catalogs as tabs, used only as the embed link for the "Complete lesson catalog" bullet — **not a source of truth**. Ayush edits it manually or asks it be skipped some weeks. When in doubt, ask whether to include the catalog bullet at all.

Other files that must stay **permanently uncommitted** (repo-root scratch): `delete_this_before_push.md`, `batch_check_interactions.js`, `check_lesson_interactions.js`, `update_grade3_interactions.js`, `interaction_results.json`. These are not gitignored, so before every `git add` run `git status --short` and eyeball that none get staged.

## Computing the bullets from raw data

Ayush sends numbers in whatever shape the current dashboard/reviewer tooling outputs — **the schema has changed multiple times**, so don't assume a fixed shape; ask if a field you need is missing.

- **Production output:** split approved counts by grade, and within each grade by CCSS vs TEKS. Sum must match the total given.
  - **Gotcha:** the `CCSS.MATH.CONTENT...` prefix does **not** reliably mean CCSS — some such lessons are TEKS per Ayush's classification. **Ask him to confirm the CCSS/TEKS split** rather than inferring from the ID string, especially if a grade suddenly shows CCSS where it was TEKS-only.
- **Reviewer engagement:** `<total iterations>: <feedback> (<%>), <approvals> (<%>)`, plus `<comments>, <comments/lesson>`. Report the numbers given; don't compute derived rates unless asked.
- **First-time pass rate:** was included → redefined → dropped. **Default to omitting** unless he asks for it back.
- **Agent performance** (the fiddly one):
  - Ayush sends a per-session table: lesson ID, session ID, type, issues, fixed, fails (sometimes with prose explaining each failure).
  - **Critical, repeated rule:** any lesson whose session work was **unconfirmed, undeployed, or otherwise unfinished** is **excluded entirely from both numerator and denominator** — not counted as "fixed," not counted as "failed" either. Read the prose carefully; several genuine-looking "fails" get reclassified as false positives/downgrades, changing the sum.
  - **Sanity check:** sum `(issues − fixed)` across every *remaining* row. If it's not zero you missed an exclusion. A clean remainder reconciling to a round number is a *good* sign, not a coincidence to distrust.
  - Sometimes he sends the batch pre-scoped (deferred/unpublished already removed) — then use the numbers as given, no further filtering. Ask if unsure whether a batch is pre-scoped.
  - "N lessons" — use Ayush's own bottom-line lesson count even if your manual row count differs by one; the discrepancy is in his source data, trust his stated total.
- **Review time:** `Average of <X> minutes per iteration across <Y> total minutes.` — direct passthrough.
- **Review queue:** `<total> total: <grade>: <count>, ...` — **only grades with a non-zero count**, largest first. Sum matches the stated total.

## Git flow (contested shared file — expect a conflict every week)

This repo is an **explicit exception** to "never commit directly to main." Ayush has repeatedly directed direct commits to `main` (no branch/PR) once he's approved the draft. Follow that here.

1. `git add` **only** the release `.md` file and the `AthenaApplets.png` — never `git add -A`/`git add .`, so scratch/catalog files can't sneak in.
2. `git commit -m "Athena Applets Release Notes"` (this exact message every week).
3. `git push origin main` — if rejected ("fetch first"/non-fast-forward), that's expected:
   - `git fetch origin`, then `git merge origin/main --no-edit`.
   - Clean auto-merge: verify no conflict markers (`grep -c "^<<<<<<<\|^=======\|^>>>>>>>" <file>` prints `0`), the YAML frontmatter still parses (`yaml.safe_load`), and every team's `title:` you expect is still present.
   - Genuine conflict (two teams' entries collided in `features:`, or a `meta_title` format drift): **keep every entry from both sides** — never delete/overwrite another team's block. For `meta_title` format conflicts, match whatever the *more recent* entries that week use.
4. **Squash the merge into a single commit before considering the push done** (Ayush corrected this once; apply proactively without being asked):
   ```
   git log --oneline -5                # find the commit right before your own first commit this session
   git reset --soft <that-commit-sha>  # un-commits after it, keeps combined diff staged
   git status --short                  # sanity: only your release .md + image staged
   git commit -m "Athena Applets Release Notes"
   git push --force-with-lease origin main
   ```
5. Report the final commit SHA and what got merged alongside your entry.

**Auth note (Mac/this clone):** git uses **SSH** and a single `gh` account (`agg-ayush`). The Windows multi-account "Repository not found" gotcha does not apply here. If push/pull ever fails with "repository not found" on a repo that worked minutes earlier, run `gh auth status` to rule out an account flip before assuming anything else.

## Things that drift — re-confirm, don't assume

- The bullet structure/priorities have shifted before (an AFK stretch produced an entry emphasizing approval counts + week-over-week over raw iteration counts). Periodically re-confirm the current structure rather than assuming last week's shape is permanent.
- `meta_title` date format drifts MM/DD ↔ DD/MM. Match the majority/most-recent convention each week.
- First-time pass rate: included → redefined → excluded. Confirm current preference.

## Hard rules (never violate)

- **Never edit any other team's feature entry.** Athena Applets only.
- **Never push without Ayush's explicit approval of the exact draft.** Always show the full YAML first.
- **Never commit the grade catalog files or the repo-root scratch files.** Always `git add` explicit filenames, never wildcard.
- **Never fabricate a metric, lesson name, or link.** Unknown lesson name → blank cell, not a guess.
- **Always fetch/merge before pushing** — the file is contested every week.

## Verification checklist

- [ ] Editing only the Athena Applets entry; every other team's `title:`/block untouched
- [ ] `git status --short` shows only the release `.md` + `AthenaApplets.png` staged (no `grade_*.md`, no scratch files)
- [ ] Full YAML draft shown to Ayush and explicitly approved before any push
- [ ] Production-output CCSS/TEKS split confirmed with Ayush where ambiguous; grade sums match totals
- [ ] Agent-performance denominator excludes all unfinished lessons; `(issues − fixed)` over remaining rows = 0
- [ ] No conflict markers remain; frontmatter parses; all expected teams' entries present
- [ ] Merge squashed to a single commit before push
- [ ] Final commit SHA + co-merged entries reported back
