---
name: ticoons-revenue-planning
description: Draft Ticoons trilovation narratives and revenue plans.
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [ticoons-revenue-planning]
---

# Ticoons narrative + revenue-plan authoring

Two coupled artifacts live on every Trilovation: the **narrative** (description / buyer / value delta / competitors — the story) and the **revenue plan** (the measurable proof the story is true). Both go through the `mcp__ticoons__*` tools. This skill is about the *drafting discipline*, not the tool mechanics (see `mcp__ticoons__get_platform_guide` for domain concepts/behavior rules — read it once per new Trilovation before touching fields).

## Before touching anything

1. `mcp__ticoons__trilovation_get` — read the current narrative in full. Never overwrite a field you haven't read.
2. If updating rather than authoring fresh, identify exactly what scope/content the existing text carries — a rewrite must fold the old scope in, not silently drop it (caught once: a narrative rewrite dropped the original census/audit scope when the tedious-process angle was added).

## Narrative fields (description / buyer / value delta / competitors)

- Each field answers **"what can't they do without us,"** not "who they are" or a role bio. A buyer line that just restates the buyer's job title/relationship failed review; it must name the specific capability gap or pain (e.g. "can review but it's tedious and costs N hours" / "has no visibility without asking").
- Don't invent competitors, numbers, or facts not actually true of the project's current state — verify against what's real (e.g. a placeholder "competitors" list carried over from a stale earlier draft was wrong and had to be cleared).
- **Never write a field into the tool as final until the user has explicitly picked/approved that exact text.** Present 2-3 phrasing options first. Corrected once: "did i finalize the description before you put it in?" — writing a not-yet-approved draft into the live record is treated as jumping ahead, even if the option looked obviously right.

## Revenue-plan proposals

1. **Calibrate against already-approved plans before drafting anything new.** Pull `revenue_plan_item_list` for a few other trilovations (`trilovation_list` first to find ACTIVE/BOOTSTRAPPING ones) and read what actually got accepted. This is the single highest-leverage step — it reveals the real acceptance bar, which is narrower than it looks from first principles.
   - See `references/accepted-revenue-plan-patterns.md` for two worked examples and the pattern extracted from them.
2. **The observed pattern:** a named person **confirms** ((a) a specific behavior/outcome happened, and (b) no negative escalation occurred), plus sometimes a technical-soundness confirmation from a second named person. Not a process description, not an internal metric nobody outside the team would check.
3. **Present candidate outcomes as a flat numbered list**, one line each, so the user can accept/reject/edit per item in one pass without you re-explaining context per item. This is how the user wants to triage a list of options generally — don't bundle several candidate metrics into one paragraph.
4. **Hard filter — cut anything not in our control.** If an outcome depends on another party's future behavior or an unmeasurable internal state ("stakeholder saves N hours" — we don't know his baseline or control his time; "teams fix what we flag" — depends on the team, not us), it gets rejected. Reserve outcomes to things we can directly measure and are accountable for delivering (e.g. our own response latency, our own audit-flag coverage, an audit trail we generate).
   - Corollary: **don't put "what we don't control" into the revenue plan proposal itself**, not even as a caveat section. If it's worth flagging, it's an internal risk note, not part of the customer/investor-facing plan.
5. **"Revenue item" and "specific outcomes" are different fields with different content** — revenue item is the one-line WHAT (the goal), specific outcomes are the measurable confirmations that PROVE it happened. If they read as the same sentence restated, split them: state the goal once, then list the outcome(s) that would confirm it.
6. **Quality bar is its own line, phrased as a negative condition**, not folded into the metric ("no manual doc reading required," "no meeting requests generated" — not just "under 2 minutes").
7. Don't assume unstated relationships/facts when writing someone else's story (e.g. assumed colleague only meets stakeholder about a given topic — wrong, corrected). If a claim about who talks to whom, who decides what, or who is blocked is not something the user explicitly said, ask rather than assert it.
8. Nothing is "Settled" in the proposal until the actual counterparty (customer/investor/stakeholder) confirms it — an internal "yeah that sounds good" from the user approves drafting it, not finalizing it as settled fact in a shared doc.
