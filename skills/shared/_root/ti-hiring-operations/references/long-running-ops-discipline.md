# Long-running ops discipline (backfills, eval babysitting, bulk sheet writes)

## Main chat stays free
- Never block the main chat on long work: no foreground `sleep N`, no `timeout`-wrapped polls, no retry loops longer than a few seconds. The user keeps discussing other topics and treats a stalled chat as a failure.
- Bulk work (S3 -> GCS capture copies, firing/babysitting Cloud Run evals, multi-row sheet writes) goes to a subagent or a `terminal(background=true, notify=true)` job. The main chat only does short reads and verification.

## Subagent generations
- Background processes a subagent launches get SIGTERM'd when that subagent ends, so a fire-and-forget python helper dies mid-run. Have one subagent drive short bounded bursts against a resumable state file (per-item done/digest), so a kill loses nothing.
- Before dispatching a replacement subagent for the same batch, stop the previous generation (`delegate_task action=list`, then `action=stop`). Two live dispatchers on one state file race and double-fire.
- Re-verify a subagent's completion claims yourself (GCS listing with the full prefix, sheet read-back) before relaying them.

## Sheet writes
- The shared sheet's rows shift while others edit it. Locate each row by session id from a fresh read immediately before every write, never by a cached row number, and read back by session id after.
- Count rows from a structured JSON grid read, not a TSV line scan: form cells contain embedded newlines that break line counting.
- Sheets quota hiccups drop single writes in a loop; read back and retry only the failed cells.
