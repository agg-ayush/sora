# Bulk booking and bulk BCC mail

## Bulk session booking via POST /v1/sessions

- Use direct `POST /v1/sessions` (one per row, idempotency key per row) when the scheduling intake route is not enabled. Run the POST loop in a subagent, not the main chat.
- Fire each row ONCE. The scheduler sweeper owns retries for Meet/Recall pacer deferrals: an attempt with `status: failed` but an advancing `nextAttemptAt` and climbing `attempts` is still retrying. Re-POST with a fresh key suffix (`-r2`, `-r3`) only after the attempt deadline passes and the row is genuinely terminal; reusing a spent key is a no-op.
- Confirm AM vs PM for every slot before booking. Unlabeled times are IST; echo IST and UTC together.
- Dedupe by email first: the one-active-session guard 409s a second row for the same person. Ask which submission to keep, then terminate and rebook if switching.
- Verify start times by parsing both sides to instants, not string compare (DB returns `.000Z`). Match emails case-insensitively when cross-checking bookings.

## Bulk announcement mail from startgreat (BCC, no names)

1. Show the exact delta from the user's prose (spelling/punctuation only). Send one plain test to the user, then the HTML card version, before any batch.
2. Send with `--to <ops-mailbox>` and recipients in `--bcc`, chunked at 10 addresses per message; the Bcc header gets rejected well below 20.
3. Probe any send limit ONLY with the user's own or test addresses. A probe that carries real candidate addresses cannot be unsent.
4. On `Invalid Bcc header` for a chunk, bisect to the single bad address instead of retrying the chunk: one malformed address fails the whole message. Sheet email columns can be truncated (e.g. `...@dtu.a`); take the full value from the other email column.
5. Verify by reading the Bcc lines of every sent thread (search with an explicit high `--limit`; the default page drops threads) and diff against the target set. Resume only the missing addresses so nobody is mailed twice.
