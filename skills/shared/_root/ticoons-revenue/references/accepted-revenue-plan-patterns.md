# Accepted revenue-plan item patterns (worked examples)

Pulled from live Ticoons data (Aug 2026) as a calibration baseline before drafting new proposals. Re-pull fresh examples periodically — these are illustrative of the *pattern*, not a fixed reference set.

## Alpha Community V2

> By Sept 15, all of the following hold: (a) customer contact confirms that since launch, Alpha Community has replaced ParentSquare and staff-to-parent email as the school's channel for parent communication — the school no longer sends parent-facing announcements or day-to-day communication through ParentSquare or staff email; (b) customer contact confirms no formal escalation about the reliability or usability of Alpha Community (either the parent-facing features or the staff portal) was raised to school leadership by staff or parents since launch; and (c) Guy confirms the delivered Groups-based data model and staff portal architecture can be extended for future features without requiring a rewrite or major rework.

> By Sept 15, all of the following hold: (a) customer contact (or a designated staff supervisor) confirms that school staff manage their own roster of assigned families/students directly within the Alpha Community staff portal, without needing IT or admin intervention; (b) customer contact confirms no formal escalation... ; and (c) Guy confirms the delivered architecture can be extended without requiring a rewrite.

## Athena Applets V3

> Hands-off delivery at customer quality: 95% of generated videos reach the customer with no changes made by a developer, and meet the customer's quality bar.

> Full grade produced in ~2 days: a complete grade's lesson set is generated, checked and delivered in roughly two days, making grade-level delivery a unit we can commit to on a schedule rather than estimate.

## Newer accepted style (Oct 2026 plans)

Recent ACTIVE plans dropped the (a)/(b)/(c) bundle for one sentence per item, often with a short outcome headline before the colon, and item values summing to the tier cap.

> By Oct 23, 2026, colleague books candidate assessments herself, both individual and campus, in 3-4 clicks with no developer involved, and receives an accurate automated shortlist, with enough data presented for each shortlisted candidate that she can review or verify any of them in under 5 minutes. (25k, the whole tier)

> Coaches stop repeating the mistakes Alpha flags: from 1 Oct to 31 Dec 2026, coaches flagged for a mistake on customer contact's list make it less often in their next three calls than in their three calls before, judged by Diane without knowing which calls came first. Confirmed by customer contact.

> An EduLLM course team (math or reading) runs the evaluator as an automatic check on its generated content for one live course, and confirms in writing that its findings were useful enough to keep it in their pipeline.

> The Grade 7 science subject-matter expert named by Alpha School's Academics Team approves all 67 videos of the Grade 7 science course for release to students, with no further changes requested, by 31 December 2026.

Devices worth reusing: "Confirmed by <name>" as a closing line; "At least one such case must come up" so a zero-occurrence window can't pass vacuously; a concrete date rather than "end of quarter".

Finding calibration plans fast: many Trilovations (including some ACTIVE ones) have empty plans. Parse saved `trilovation_list` output for ACTIVE names, then call `revenue_plan_item_list` on each, one `tool_call` per call.

## Pattern extracted

- **Named person confirms**, not an internal metric we self-report.
- **Behavior actually changed** (replaced the old system / manages own roster), not "the tool works" in the abstract.
- **Escalation-free** is checked explicitly as a quality gate — a feature that technically shipped but generated complaints doesn't count.
- **Time-boxed** ("By Sept 15") or **rate-boxed** ("95%", "~2 days") — never open-ended.
- **Second confirmer for technical soundness** where relevant (Guy confirming the architecture won't need a rewrite) — separates "it works today" from "it doesn't become debt."
- Nothing about competitor dynamics, market position, or things outside the building team's control.
