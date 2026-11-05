# RCA docs

Short, crisp, plain English. Use the team's existing RCA as the shape reference (read it with `gog docs cat <id>` before drafting):

1. Title line: `RCA: <what broke, in user terms>, <date>`, then a metadata block (Date / Author / Status / Severity) as separate lines.
2. **What happened**: the user-visible symptom, 2-3 sentences.
3. **Cause**: the proven mechanism with file/function names; say explicitly whether it was deterministic or a race.
4. **Timeline (UTC)**: only for incidents/regressions with a time window and blast radius (outage, deploy ordering). Leave it out for a plain logic bug with a clean root cause.
5. **How it got to production**: the section stakeholders actually read. Answer concretely: which tests existed for this path and why they passed anyway (e.g. unit tests mocked the branch that broke, no test drove the real sequence end to end), what review/QA it went through, and which gate would have caught it. One thin line here gets bounced back with "this doesn't tell me how it got into prod".
6. **Fixes**: Done / Next, one line each. The Next list should close the gap named in section 5.

No "Lesson" section: a tacked-on generic rule reads as random; the fixes carry the lesson.

## Classify regression vs never-worked before writing it

A regression means a previously working behavior broke. If the broken path was introduced by the same change that shipped it (it never worked), call it a bug in a new feature, not a regression, and drop the timeline. Check git history for when the path first existed before using the word.

## Chat TLDR of an RCA

When asked for a TLDR in chat: two lines, no function names, file paths or branch logic. Say what the user experienced, why in plain words, and that it's fixed.

## Workflow

Draft markdown under the scratch dir, `gog docs create <title> -j` for the id, `gog docs write <id> --replace --markdown --file <md>`. Edits to a doc with no reviewer comments: rewrite the markdown and full-replace, then re-cat to confirm the change landed. Source the cause from the card's completion summary and comments (proven root cause), not from memory. No em dashes, no Oxford commas. Run the humanizer skill over it when asked.
