# Gmail issue-thread searches under tight quota

Patterns for reading candidate/issue threads from Gmail via `gog` when API
quota is tight. All rules are imperative; the failure each prevents is noted
inline.

## Query construction

- Filter on `internalDateIso` for date cutoffs; Gmail's day-level `after:` is
  coarser than needed.
- `gog gmail search` returns 0 threads for label/date-scoped Gmail operators
  (`in:inbox`, `-from:me`, `newer_than:`, `after:<epoch>` combined with them)
  even when matching mail exists. Run plain keyword searches (subject words
  like `TI Assessment`, `interview`, `unable`, `issue`, `link`) and filter by
  `internalDateIso`/`from`/`labels` locally instead. Keep searches spaced a
  few seconds apart; bursts trip the per-minute query-cost quota.
- Drop threads whose only labels are SENT (no INBOX) — a thread whose earlier
  incoming message matched displays its last SENT message and pollutes results.
- Drop mailer-daemon/Google/Calendar/Drive/noreply/no-reply senders before
  reading anything.
- A quoted multi-word subject exclusion (`-subject:'Tentatively Accepted'`)
  silently returns 0 results; use one word per `-subject:` flag, one flag per
  word.
- Subject exclusions can hide a genuine issue reply living in the same thread
  as a sent template — use them only when the task explicitly narrows reads to
  issue-looking metadata.
- Expect cold job/internship applications to surface in candidate-domain
  searches; bucket them separately (e.g. read_not_issue_applications) instead
  of forcing them into the issue taxonomy. Institutional placement-cell bulk
  mail (e.g. `placements.pg@iiita.ac.in` "SDE Internship Hiring") is not a
  student issue report — skip reading it.
- On a sending mailbox, a subject-template keyword search (e.g. `TI Assessment`)
  returns page after page of SENT-only 1-message invite threads — 120 results,
  zero discovery. Don't page through it; one page proves it is pure noise and
  further pages only burn quota. Prefer issue-flavored keywords (`unable`,
  `issue`, `link`, `interview`) that inbound replies actually contain.
- Paginate with `--page <nextPageToken>`. A response whose `threads` array is
  empty and whose `nextPageToken` equals the token you passed means the keyword
  is exhausted (token loop) — stop, don't re-fetch. A page token that 403'd
  belongs in the bucket file's state so the next run resumes it.
- A domain-targeted search is NOT complete coverage: student replies come from
  other domains too. On a quota-recovery run, diff its thread IDs against
  the watchdog's full thread list and read any SENT-labeled thread with
  messageCount > 1 — a reply or bounce may live in it.
- A thread ID from a watchdog/saved list can 404 on `gmail thread get`
  (stale or account-scoped). The startgreat hiring mailbox is a *separate gog
  account* (`<ops-mailbox>`, gmail-only); its thread IDs 404 under
  `ayushaggarwal018@gmail.com`. Check `gog auth list -j` and retry with the
  mailbox-owning account before concluding an ID is stale. If it still cannot
  be resolved, record it as pending in the bucket file for the next run.
- A thread's messageCount can grow after it was already read and bucketed
  (student sends a follow-up). On each run, diff not just thread IDs but
  message counts against the bucket file's snapshot; re-read any thread whose
  count rose and update its existing entry (merge by thread ID, never replace
  the whole file — earlier passes are often larger than the latest watchdog
  list). Store messageCount in each bucket entry when first read so later runs
  can diff counts without re-reading every thread.
- After any merge, sanity-check the bucket file itself: same-thread duplicate
  entries WITHIN a bucket and the same thread ID in TWO buckets both occur on
  real runs (one entry per message instead of one per thread). Dedupe within
  buckets (keep the first entry) and resolve cross-bucket conflicts by the
  thread's dominant issue — a student sending one interview-flavored and one
  terminal-flavored message about the same failed session is still one issue,
  bucketed once, on the message describing the interview session failing.
- `text/plain` can sit under a multipart/related > multipart/alternative
  nesting with inline image siblings; a parts walk that only checks the top
  level returns an empty body. Decode recursively through ALL parts (any
  level with body.data), preferring text/plain, falling back to stripped
  text/html.

## Reading and classifying threads

- Read candidate threads serially via
  `gog --account <account> --client <client> gmail thread get <id> --json`,
  pausing when quota is tight. On 403 `rateLimitExceeded`, stop immediately and
  retain partial progress rather than retrying in a burst.
- Classify by keyword only against the student's own message text: reply chains
  quote the entire sent template, so a regex over the full body false-matches
  every time. Split the message list by From header first and bucket on the
  incoming message alone.
- Decode `payload.body.data` recursively through `parts`, preferring
  `text/plain` and falling back to stripped `text/html`.
- On `gmail thread get --json`, messages live under `.thread.messages[]` (not
  top-level `.messages`), and headers may omit `value`: use
  `header.get("value")`, not `header["value"]`, or one atypical message aborts
  a whole batch.
- A 2-message thread whose metadata shows the SENT template can have a
  mailer-daemon bounce as its incoming message — metadata-level sender
  filtering cannot catch it, only the thread read reveals it. Count it as a
  bounce and record the bounced address (parsed from the bounce body) so bad
  candidate emails are tracked.
- On quota-recovery runs, inspect the existing bucket file first (it may hold a
  larger earlier pass than the watchdog's latest search) and merge by thread ID
  rather than replacing with only newly read threads.
- An INBOX `Fwd:` from a colleague (e.g. colleague forwarding the assessment
  invite) is the sent template again, not a student issue report — skip it.
- Some `text/plain` parts render with a space between every character
  (letter-spacing artifacts from the HTML rendering pipeline): collapse with a
  regex removing inter-character spaces before keyword matching.

## Environment

- gog lives at `/home/ubuntu/.local/bin/gog` on the Linux box
  (`/opt/homebrew/bin/gog` is macOS-only) and needs `GOG_KEYRING_PASSWORD`
  exported plus a minimal `PATH`/`HOME` when invoked from Python `subprocess`
  (a bare env without PATH raises FileNotFoundError).
- Check the write tool's success flag inside loops; overwriting an unread
  existing file can be refused without raising.
