# Iterative doc-editing cycles: live user edits + unanchored comments

Applies to any workflow where a gdoc is being reworked over many small turns
while a reviewer (or the user) is also editing/commenting directly in the
browser between your calls — e.g. an ITD or proposal going back and forth
with a stakeholder.

## Always re-pull the live doc before a full-body overwrite

If the user says anything like "I made some small edits, use that language,
don't override" — or even without being told — assume the doc may have
changed in the browser since your last write. Before doing a local-file-edit
+ `docs write --replace` round trip:

1. `gog docs cat <docId>` first to fetch current live content.
2. Diff it against what you last wrote/cached locally. Any deltas are the
   user's manual edits — preserve their exact wording verbatim, don't
   "improve" or paraphrase over it while making your own change.
3. Apply only the new change on top of the live content, not on top of your
   stale local draft. Overwriting with a stale draft silently discards
   in-browser edits with no warning — the write succeeds, so nothing signals
   the loss until the user notices their wording is gone.

## Reading comments when anchor text isn't available

`gog drive comments list <docId> --json` returns comment `content`,
`author`, `createdTime`, and `resolved` reliably even when `quotedFileContent`
/anchor data is empty (e.g. after an earlier full-body `docs write --replace`
orphaned the anchors — see `table-editing-and-shared-doc-pitfalls.md`). Don't
treat missing anchors as "can't read the comments" — the comments themselves
are still fully readable via this call:

1. List all comments, filter `resolved == false`.
2. Sort by `createdTime` ascending.
3. Track the timestamp of the last batch you already reported to the user
   (or the time of your last write) and filter to only what's newer — don't
   re-report comments already handled in a prior turn.
4. Since you can't algorithmically map a comment to the exact text it's
   anchored to, print each comment with its timestamp and let the user tell
   you which line/section it's about (they often will, unprompted, e.g. "the
   not exactly necessary was about the code editor") — don't guess silently
   and risk fixing the wrong passage.

## Pulling comments with anchors and replies in one pass

`gog --readonly drive comments list <docId> --all --include-quoted -j` returns
`quotedFileContent.value` (the anchored text) plus `replies`. Print each as
id, time, author, resolved, body, quote and replies. Treat `resolved: null` as
open, not resolved: the field is often omitted on open comments.
Multi-tab docs: also run `docs list-tabs` and `docs cat --tab <title>` for each
tab, because the comment anchor may live in a non-default tab.

## Reconciling reviewer comments into a working doc

- Record a reviewer's suggestion as **proposed** in the working doc or tracker
  until the user explicitly adopts it. Then rewrite it as settled and list only
  the sub-questions that are still open (for example exact fields or edge-case
  behavior).
- Leave frozen or originally shared docs unchanged. Put decisions in the
  working doc and tracker. If a companion artifact (such as a diagram doc) is
  now stale, add a visible top-of-tab "draft under revision, do not circulate"
  notice rather than silently leaving it stale.
- For targeted edits, use this safe loop: `docs cat --tab` preflight and check
  that the old string occurs exactly once, then `docs find-replace --tab <t>
  <docId> <old> <new> -j` and assert `replacements == 1`, then re-cat and
  confirm the new text is present and the old text is gone. This keeps comments
  and anchors intact, unlike `write --replace`.

## When the user gives you the anchor context directly

If the user tells you which option/line a comment refers to (rather than
you deriving it from the API), apply the fix immediately in the next write —
don't re-run comment-anchor archaeology once they've told you.
