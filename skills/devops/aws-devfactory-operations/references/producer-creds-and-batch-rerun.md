# Producer creds for on-box batch submit, and re-running a batch subset

## The worker's own IAM role is consumer-only — running the producer CLI (batch submit) on the box needs separate creds

The worker fleet's instance role (e.g. `alpha-learn-script-generation-worker-role`)
is scoped to **consume** the job queue (`sqs:ReceiveMessage`/`DeleteMessage`,
S3 read/write under the status prefix) — it deliberately does NOT get
`sqs:SendMessage`. If you drive the batch/producer CLI (e.g.
`script_generation_worker.dispatch batch <folder>`) directly on a fleet box
via SSM — a reasonable move when the box already has the scripts staged
locally and the code/dependencies installed — the enqueue step fails with:

```
... is not authorized to perform: sqs:SendMessage on resource: ...
FAILED to enqueue <lesson_id>
```

This is not a bug to fix in the role (the box's role is correctly scoped —
it shouldn't be able to produce jobs, only consume them) — it's a distinct
credential need for that one invocation. Fix: inject **producer** creds (an
IAM user that already has `sqs:SendMessage`/`GetQueueUrl` on the queue — e.g.
the app's own prod content-manager user, the same one wired into the
Amplify env for the direct-S3+SQS path) into the process env for just that
batch-submit command, the same "second, separate credential layer" pattern
used for the deploy/CDN step (see main SKILL.md) — not the box's instance
role, and not the SSM-hydrated worker secrets:

```powershell
$env:AWS_ACCESS_KEY_ID = "<producer-user-access-key>"
$env:AWS_SECRET_ACCESS_KEY = "<producer-user-secret-key>"
# then run the batch/submit CLI — enqueue now succeeds; consumption (the fleet
# picking the jobs back up) still runs under the box's own instance role,
# unaffected by this env override.
```

This recurs every time someone re-runs a filtered subset of a batch from the
box itself — expect to hit it again and reach straight for producer creds
rather than re-diagnosing the role's policy from scratch.

## Re-running only a specific subset of a batch — stage a filtered folder, don't touch the queue directly

The batch CLI's discover step walks every `<id>_script/script.md` under
whatever root folder you point it at — there is no per-lesson-id filter flag.
To re-run only a known subset (e.g. the N lessons that failed and have since
been content-fixed, out of a larger folder that also has already-succeeded
ones), don't re-run the whole folder (wastes fleet capacity regenerating
already-good lessons) and don't try to hand-edit the queue. Instead, on the
box, copy just the target lesson subfolders into a fresh scratch folder and
point the batch CLI at that:

```powershell
$failed = Get-Content <failed-ids-file>   # one lesson id per line
$dst = "<scratch-root>\rerun"
New-Item -ItemType Directory -Path $dst | Out-Null
foreach ($lid in $failed) {
  Copy-Item (Join-Path $src $lid) (Join-Path $dst $lid) -Recurse -Force
}
# then: python -m <producer_module>.dispatch batch $dst
```

This is the general pattern for "re-run only a subset via a discover-by-folder
batch CLI" — applies to any producer CLI in this fleet family, not just one
incident.
