# Google Chat via gog — send messages and DMs

`gog` sends Google Chat messages via **user auth** (`spaces.messages.create`).
The message posts as the authenticated user with the Chat app name attributed
under it.

## Prerequisites

Sending only works if the OAuth client gog authenticates through has the
Chat API enabled **and** a Chat app configured in its backing GCP project.
Without the Chat-app registration, `messages.create` returns `404` even
though reads (`spaces list`) succeed — the 404 is a missing app config, not
an auth failure. Reads work without any of this.

The Chat-app config step is **Console-only** (not writable over a user API):
Console → APIs & Services → Google Chat API → Configuration → set app name +
avatar + description. For send-only, connection type can be a placeholder
HTTP endpoint URL (never called); to also receive @-mentions/replies, use
**Cloud Pub/Sub** (topic + subscription, local subscriber pulls — no public
endpoint needed), not HTTP/Apps Script.

## Commands

```bash
ACCT=<account>

gog chat spaces list -p                                # find spaces/XXXX ids
gog chat messages send spaces/XXXX --text "hi"         # send to a space
gog chat messages send spaces/XXXX --text "r" --thread spaces/XXXX/threads/YYYY
gog chat dm send user@example.com --text "hi"          # direct message by email
gog chat messages react spaces/... --emoji ...         # react
```

## Pitfalls

- **Address DMs by email, never by a bare space id.** `spaces list -p` shows
  DIRECT_MESSAGE rows with an EMPTY `NAME` — the listing cannot tell you whose
  DM it is, and a message sent to an unidentified `spaces/XXXX` id can land in
  a real person's DM. Use `chat dm send <email>` so the recipient is explicit.
  To identify an existing DM space's counterparty, list the space's members
  first.
- **Test sends need a known target.** Use a fresh space you created or an
  email-addressed DM to yourself — never an unidentified space id.
- **Self-DM via `chat dm send $ACCT` fails** with `400 Don't specify the
  calling user as a membership`. Self-notes go to a space, not a DM.
- **A `404` on send means the Chat app config is gone**, not an auth problem.
  Re-do the Console config step; no re-login is needed.

## Verification

`gog chat messages send <known-space> --text "test" -j` returns a `message`
object with a real `name` (`spaces/.../messages/...`), `createTime`, and
`sender.type: HUMAN`.
