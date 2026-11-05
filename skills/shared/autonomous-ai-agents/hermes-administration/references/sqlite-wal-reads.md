---
title: Hermes SQLite DBs: live reads and corruption recovery
---

# Reading a live DB while the gateway holds it open

Hermes state/ledger DBs (state.db, gateway store, kanban DB) run in WAL
mode while the owning process (the gateway, typically) has them open. A
Open the live database with the standard read-only URI and a short SQLite
read transaction so the `-wal` and `-shm` sidecars are visible in the same
snapshot:

```python
import sqlite3
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.execute("BEGIN")
# Run the bounded audit queries; close promptly to release the snapshot.
```

**Do not add `immutable=1` for a live WAL database.** It tells SQLite that
the file cannot change, which can bypass the live WAL and return stale or
empty results. Confirm the sidecars are accessible and `PRAGMA journal_mode`
reports `wal`; cross-check recent timestamps/counts against expected live
activity. If opening read-only fails because sidecars are inaccessible,
report the coverage gap instead of silently falling back to an immutable
connection. Avoid holding a read transaction longer than necessary, since
it can delay WAL checkpointing.

# Recovering a corrupt state.db (sessions missing / empty chat list)

Symptom: after a repair or migration, `hermes sessions list` is empty or
short. First check whether a preserved original exists (e.g.
`~/backups/state.db.corrupt-*.db`) and count it read-only: a DB that fails
`PRAGMA integrity_check` ("Rowid out of order") is often still fully
readable row by row.

Procedure (dump/reload from the original, never repair in place):

1. Count the source: `sqlite3 <orig> "select count(*) from sessions; select count(*) from messages"`.
2. Dump straight from the original: `sqlite3 <orig> .dump > dump.sql`.
   Do not route through `.backup` first: `.backup` of a corrupt DB can
   write a 0-byte file without a non-zero exit.
3. Count `INSERT INTO sessions VALUES(` / `INSERT INTO messages VALUES(`
   lines in the dump (`grep -acF`); they must match step 1.
4. Load into a fresh file: `sqlite3 recovered.db < dump.sql 2> load.err`.
   Rows from the corrupt page fail `NOT NULL constraint failed:
   messages.timestamp`; those are garbage and dropping them is expected.
   Any other error type means stop.
5. Verify: `integrity_check` = ok, sessions == source sessions,
   messages + load errors == dump message inserts.
6. Swap: stop the gateway, copy recovered.db over `~/.hermes/state.db`,
   delete `state.db-wal`/`-shm`, `chmod 600`, start the gateway, confirm
   with `hermes sessions list`. Keep the original and dump until the user
   confirms their chats look right, then offer to delete the artifacts.

Pitfall: every verification gate must also assert the counts are
non-empty and non-zero. A script whose source step silently produced an
empty file passes `0 == 0` arithmetic checks and swaps an empty DB in.

Pitfall: run `systemctl --user stop`, the copy, and `start` as separate
short commands; chaining them with a slow CLI check in one SSH call can hit
the tool timeout mid-sequence and leave the gateway stopped. Re-check
`is-active` after any timeout.
