---
name: product-ui-review
description: "Use when auditing a live app UI or routing UI nitpicks."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ui, review, audit, staging, nitpicks, kanban, preferences]
    related_skills: [impeccable, mockup-review-iteration, tier2-orchestration]
---

# Product UI Review

## When to Use

The user asks to check a deployed UI for small improvements, or gives visual/UX nitpicks about a live app that a coding pass will implement.

For reviewing a real, deployed app (staging/preview) and turning findings or the user's nitpicks into instructions for the coding passes that build it. HTML concept mockups belong to `mockup-review-iteration`; the design craft itself belongs to `impeccable`/the repo's UI pipeline skill.

## Procedure

1. **Find out which screens an in-flight build pass already owns** (read the running and queued cards). Skip auditing those screens; findings there are wasted or conflict with the redesign.
2. **Capture a screenshot matrix in a real browser** for every remaining route: 1440 light, 1440 dark, 390 mobile. Include detail pages for each record state (draft, out for signature, signed, declined, empty). Also hit every header/nav link; a dead link (404) is a bug, not a nitpick.
3. **Review each screenshot with a picky prompt** (alignment, spacing, empty space, truncation, button-style consistency, duplicated info, unclear labels, hidden next action, dark-mode contrast, tap targets). Crop tall mobile captures into regions; a full 390x3500 capture downscales to unreadable.
4. **Cross-check suspicious states against the data source** (DB rows, upstream API status) before filing them as UI bugs. Contradictory status on one page is often inconsistent seed data; file both the seed fix and the product rule (which source wins when they disagree).
5. **Check test-data hygiene.** Verification records named with internal jargon ("Pass N Probe"), duplicated seed notes and leftover test records are user-visible; require realistic fictional names and cleanup in the staging environment only.
6. **Route each finding to the pass that owns that screen.** A running pass gets an addendum comment on its card; everything else goes to the next queued pass. Number items continuously across addenda so the user and builder can reference them. When a queued pass grows past roughly 15-20 items, split it by screen ownership into parallel cards (each with a self-contained body, since the worker snapshots only the body) plus a final app-wide card for cross-cutting sweeps (copy, theme tokens, tap targets) that depends on the others, then archive the old card.
7. **When a new instruction contradicts an earlier one, say so explicitly in the addendum** ("replaces the card body's instruction to ..."). Builders follow the card body otherwise.
8. **A running pass may have already read its instructions.** After its current phase (e.g. design revision) finishes, verify its design includes the addendum; if not, steer it directly.
9. **Report to the user** split by pass, one table or numbered list per pass, plain language, and flag any place you extended their ask beyond what they literally said so they can veto it.

## Ayush's UI defaults (apply without being asked)

- **Users are US-based:** dates typed and shown as MM/DD/YYYY, list dates as "Nov 5, 2026", calendars start Sunday.
- **Popovers anchor directly under their trigger** (date pickers, menus); a gap between field and popover is a bug.
- **Account actions live in a profile menu** (avatar button: email, settings, theme, sign out), not as always-visible header links. Only list destinations that exist.
- **Brand is mark + product name only**, no descriptive sub-label.
- **Tab/segment counts are bare numbers** ("Active 12"); unit words go in aria-label/tooltip, not visible text.
- **Row actions must never push the primary link/content off screen.** If an action does not fit the row, move it to the detail page.
- **Every status notice that implies a next step carries the action button inline** (e.g. "PDF not attached" + "Attach").
- **Consistent button style per action level, actions in one row, status chips next to the title, status colours shared across pages.**
- **Collapse stacked empty states into one line; hide cancelled/inactive records by default or show them muted.**
- **Badges/pills go to the right edge when the right side is empty; the main text stays put.**
- **Tap targets at least 44px on mobile; inline icons stay on their text's line.**
- **Replace leftover favicons/app icons from earlier projects** with a full set generated from the current brand mark.
- **Dark mode: inputs match their card surface; check low-contrast text explicitly.**
- Proportional sizing (%, relative), never fixed px; use the space available at wide widths.
- **List toolbars: all list controls in one group, left-aligned** (Search, Filter, Dates, Sort), same height and spacing. Splitting sort to the far right reads as unrelated at wide widths; the right end is for page-level actions only (Refresh, last-updated).
- **A control names what it does.** A dropdown that shows only its current value ("Needs attention first") reads as a filter or action; prefix it ("Sort: Needs attention first") with a sort icon and caret. Only do this for single-value controls: never list active filters inside a Filter trigger, since that list can grow long. How a filter signals it is active (count badge, chips) is a design call.
- **No footer notes that carry nothing actionable:** visible result counts ("12 tickets in Active") and legends explaining a chip that already has its own tooltip go. Keep live counts for screen readers in a visually hidden `aria-live` element.
- **Copy is for experienced professionals:** short, exact and in the domain's own terms (Adobe Sign's for signing). No tooltips that restate the label or describe what a self-evident control does on click, no reassurance or hand-holding. Simplicity comes from layout, not from explaining. When this comes up, run a copy audit of every user-visible string from source (tooltips, helper text, empty states, errors, template sentences) rather than fixing only the one example.

## Pitfalls

- **Don't audit a screen a running pass is redesigning** — it duplicates or contradicts that pass's work.
- **Don't assume an addendum reached a running builder** — verify at the next phase boundary. Kanban T2 workers build their design from a `task.md` snapshot of the card body in `~/.hermes/tasks/t2-<task-id>/`, written when the run starts; later card comments never reach it. For a running pass, append the addenda to that `task.md` (the next design review re-reads it); for a queued pass, check its `task.md` contains every addendum as soon as it starts.
- **Don't file seed-data inconsistencies as pure UI bugs** — check the data source first.
- **Don't silently broaden the user's ask** (e.g. picker format to all dates) — do it if clearly implied, but name the extension in the report. Extending a fix to sibling controls is where it usually goes wrong (applying a sort-label pattern to Filter); check that the pattern still fits each sibling before prescribing it.
- **Specify the problem, not the pixel, when the solution is a judgement call.** If the user says to let the UI judge handle it, the addendum states the constraint and leaves the design choice to the builder under the ui-flow preferences, recording the choice in its design brief. Over-specified addenda get corrected.
- **When correcting an earlier addendum, write a new addendum that names which one it overrides** — never assume the builder reconciles two conflicting comments.
- **For source-based copy audits, enumerate visible literals and template fragments programmatically, then verify each proposed row's source line and word limit** — multiline JSX and generated labels are easy to miss or misquote.
- **Before removing a duplicate `title`, check ellipsis and `[title]` CSS selectors** — it may reveal truncated text or control styling, so keep it or note the coupled fix.
