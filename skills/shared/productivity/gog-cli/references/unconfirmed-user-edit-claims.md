# Unconfirmed "I already edited this" claims from the user

Companion note to `iterative-review-cycles-live-edits-and-comments.md` —
read that file first for the general live-edit-sync workflow. This file
covers one specific failure mode within it.

## The failure mode

Mid-review-cycle on a shared gdoc, the user says something like "I rewrote
that as X" — phrased as if the edit already happened in the browser. A
fresh `gog docs cat <docId>` pull, however, still shows the old/previous
text, not X.

The wrong response is to treat the user's description as ground truth and
push a full-replace write containing your best guess at what X should look
like, without saying anything about the mismatch. That risks two things at
once:

- Masking a real problem: their edit may not have saved, you may be reading
  a stale doc/mirror, or the doc ID drifted between the working copy and
  the main doc.
- Writing words into the doc the user never actually typed, then having
  that fabricated text propagate to a paired doc (working copy <-> main) on
  the next sync pass — compounding the error and making it harder to trace
  back to its origin.

## The right response

1. Say plainly that the pulled content doesn't match what they described —
   name the old text and the claimed new text — before writing anything.
2. Only write your best-effort match if they confirm the intended wording
   (or don't push back on your literal transcription attempt), and be
   explicit that you are the one writing it now, not that you found it
   already there.
3. Treat this as higher-stakes when a working-copy/main-doc pair is being
   kept in sync — an unconfirmed guess written to one gets copied to the
   other on the next "push to main" pass.
