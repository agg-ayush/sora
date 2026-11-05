# Refire first gate: mtime-vs-status check

Applies before ANY other action on a quota-cleared refire (before reading bucket files, before any Gmail API call):

- Compare `/tmp/student-buckets.json` mtime against `/tmp/student-buckets-status.json` `run_at_utc`. Buckets-file mtime NEWER than the last recorded status = an unrecorded write happened between runs — observed twice within one hour on 10 Oct: a 14:35Z partial 9-entry overwrite written right after status settled, then a 15:14Z from-scratch keyword rebuild (vva=41/not_vva=115) over the settled vva=11/not_vva=50 state. The status sidecar stayed stale in both, which is the tell.
- Do not trust or extend the newer file. Preserve it as `/tmp/student-buckets.corrupt-<HHMM>Z.json`, locate the newest backup whose meta says `settled-verified`, verify that backup's hygiene (duplicate senders, one sender in two buckets only when they are distinct threads complaining about distinct rounds, counts vs status), and restore from it via direct Python write + fsync + re-read count/sha verification.
- A refire backup far smaller than its predecessors (2.5KB vs 45KB, 9 entries vs 61) is itself a corruption artifact, not a restore carrier — restore from the last FULL settled backup instead.
- A sender appearing in BOTH vva and not_vva is not automatically a defect: check thread ids. Two distinct threads complaining about different rounds (e.g. an AI-interview drop in the VVA thread and a server-end failure in the ADD thread) is correct per-round bucketing and both entries stay.
