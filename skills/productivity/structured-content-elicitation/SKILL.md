---
name: structured-content-elicitation
description: Gather content section-by-section for narrative content.
---

# Structured Content Elicitation

## When to use

Any deliverable with a fixed structure (slide deck, report, doc) where the *content itself* is personal opinion, reflection, first-person narrative, or subjective judgment — not generic/factual filler. Examples: "how I work" retrospective decks, personal workflow write-ups, opinion pieces, status narratives, anything where two people given the same template would fill it in differently.

Trigger phrases: "let's discuss each [slide/section]," "don't rush," "the things I want to say are different for each [X]," or any pushback after you draft full content in one shot for something inherently personal.

## The mistake this prevents

Given a reference/template (an example deck, a prior doc, a known structure), it's tempting to identify the structure AND draft full content for every section in one pass, then present it all for feedback. This fails for personal/narrative content because:
- The user's actual points differ per section — batch-drafting means guessing most of it wrong
- Feedback on a full draft is diffuse ("this is off but I don't know how to fix it in one comment") vs. sharp (yes/no on one section at a time)
- The user has to unwind your invented content before inserting their real content, which is more work than starting from a blank per-section prompt

## Procedure

1. **Separate structure/format from content.** Identify (or confirm with the user) the section structure and visual format once — this can come from a reference deck, template, or explicit ask. Format choices (colors, layout, template) are cheap to change later and can be confirmed in one pass. If the reference is a batch of `.pptx` files, see "Reading batches of reference decks" below for extraction — `scripts/dump_pptx.py` handles it when markitdown can't.
2. **Go section-by-section for content.** For each section: ask what the user wants to say (open-ended, not multiple-choice unless the question is genuinely narrow), let them answer in their own words, confirm/refine, THEN move to the next section.
3. **Only draft prose once the user has given actual substance for that section.** Don't pre-fill a section with your best guess and ask them to correct it — ask first, draft second.
4. **If you must ask multiple questions across several sections, and the user asks for all questions at once** (e.g. "give me all the questions in a bullet, I'll answer all in one go"), collapse to a single consolidated list grouped by section — but still process/confirm their answers section by section afterward if they choose to answer one at a time instead. Respect however they choose to pace it.
5. Batch-draft the whole deliverable only after every section has real content from the user, not before.

## Pitfall

Having a well-matched template/reference (e.g. five example decks that all follow an identical structure) makes it *feel* safe to draft all the content by inference from the template's typical phrasing. It isn't — the template tells you the shape of each section, not what THIS user actually did or believes. Structure inference from examples is fine; content inference is not, for this class of deliverable.

## Reading batches of reference decks (.pptx)

When the user points at a folder of competitor/peer reference decks ("check the download folder, all ppt was there"):

- `read_file` cannot open `.pptx` (binary). `python -m markitdown file.pptx` sometimes silently extracts nothing — the `markitdown[pptx]` extra doesn't always install (pip warns `does not provide the extra 'pptx'`). Fall back to `scripts/dump_pptx.py` in this skill (needs `python-pptx`, not markitdown) — it prints shape text, tables, and speaker notes per slide, which is enough to reconstruct structure across N decks in one pass.
- Diff the decks against each other, not just each one individually — the useful signal is the *shared skeleton* (same slide count, same section banners, same rhetorical arc, same speaker-note time budget), because that's the actual template being used even if no one explicitly named it as one.
- Structure inference from a peer's deck is fine (slide count, banner labels, pacing). Copying a peer's *specific framing or claims* is not — if the user has a materially different or better setup than a peer in the reference set (a more sophisticated pipeline, a different tool split), the analogous slide should be built from the user's own architecture, not adapted from the peer's language. Point out the contrast rather than reusing it. Watch for an explicit signal like "fuck \<peer>, we have better architecture" — that means don't anchor the slide's content on that peer's example at all, even structurally-adjacent phrasing.
- If a draft slide leans on a claim that's a specific factual/behavioral assertion about how the user's systems work (not just structure or framing), flag it back to the user for confirmation before finalizing rather than asserting it as fact — this class of deck is presented live and an unconfirmed claim on stage is the user's problem, not yours.
