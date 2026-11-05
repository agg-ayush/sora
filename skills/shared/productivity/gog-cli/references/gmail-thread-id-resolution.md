# Resolving a Gmail web URL to a thread/message

A Gmail webmail URL like
`https://mail.google.com/mail/u/0/#inbox/FMfcgzQhWBjMChCDGVGDNTkxjFKHKfdM`
contains the **web-format** thread id (`FMfcgz...`). This is NOT the hex
thread id the Gmail API (and `gog gmail thread get <id>`) expects. Passing
the `FMfcgz...` string straight to `gog gmail thread get` fails or returns
the wrong thread, and there is no reliable client-side decode worth chasing.

Instead, search for the message using what you know about it and pull the
real hex thread id from the result:

```bash
gog --account <acct> gmail search "<query>" -j
# => {"threads": [{"id": "<hex thread id>", "date": ..., "from": ..., "subject": ...}, ...]}

gog --account <acct> gmail thread get <hex_id> -j
```

## Picking the right thread

- Search by **participant names and problem words**, not just the project
  name. Forwarded threads keep the original, often unrelated, subject line
  (a colleague forwarding an old customer thread about a different topic),
  so a project-name search misses them and lands on Chat-notification or
  meeting-report emails that merely mention the project.
- Run several small queries in one loop (names, topic words, project name)
  and print `id | date | from | subject | messageCount` for each, then pick.
- A Google Chat "messaged you while you were away" email or a Read/Gemini
  report share is almost never the thread the user linked. If the best match
  is a notification/digest, keep searching or list the candidates and
  confirm before summarizing it as "the thread".
- If the user says you read the wrong thread, take their hints (people
  named, rough timeframe) straight into new queries; don't defend the first
  pick.

## Reading the body

`gmail thread get -j` dumps every header (ARC/DKIM noise) plus base64
bodies. Pipe it through a small python walker over `payload.parts[]` that
base64url-decodes `body.data` and prints From/Date/Subject plus only the
text/plain part. Forwarded chains are inside the single message body as
quoted text, oldest at the bottom; read bottom-up to get the original
problem statement before later replies.
