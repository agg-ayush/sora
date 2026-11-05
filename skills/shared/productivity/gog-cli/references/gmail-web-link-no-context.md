# Resolving a bare Gmail web link with no search keyword

See `references/gmail-thread-id-resolution.md` for the base fix (the
`FMfcgz...` web-format id in a Gmail URL fragment isn't the hex id the API
needs — search by sender/subject/date and pull the real id from results).

That base fix assumes you have *something* to search on. Sometimes the user
just pastes the bare link with zero other context (no keyword, no "the one
about X mentioned earlier"). Don't stall trying to decode the URL itself —
there's no reliable client-side mapping from web-format id to hex id.

Instead:

1. List recent inbox mail: `gog --account <acct> gmail search
   "newer_than:1d"` (or `gmail list --max 10`).
2. Narrow candidates by sender, subject and date hints. A plausible email is not proof it corresponds to the web-format link.
3. If no unique match is verifiable, show candidate metadata and ask for a discriminating clue before summarizing or acting on any one message.
