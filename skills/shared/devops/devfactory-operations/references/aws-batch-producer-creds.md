# Producer creds for on-box batch submit, and re-running a batch subset

## The worker's IAM role is consumer-only — batch submit on the box needs separate creds

The fleet's instance role is scoped to **consume** the job queue
(`sqs:ReceiveMessage`/`DeleteMessage`, S3 read/write under the status prefix)
— it deliberately does NOT get `sqs:SendMessage`. Driving the batch/producer
CLI directly on a fleet box via SSM (reasonable when scripts are staged and
deps installed there) fails the enqueue step with `not authorized to perform:
sqs:SendMessage`.

This is not a bug to fix in the role — it's a distinct credential need for
that one invocation. Inject **producer** creds (an IAM user that already has
`sqs:SendMessage`/`GetQueueUrl` on the queue) into the process env for just
that batch-submit command — the same "second, separate credential layer"
pattern as the deploy/CDN step, not the box's instance role and not the
SSM-hydrated worker secrets. Consumption still runs under the box's own
instance role, unaffected. Expect to hit this on every filtered re-run from
the box — reach straight for producer creds rather than re-diagnosing the
role's policy.

## Re-running only a subset of a batch — stage a filtered folder

The batch CLI's discover step walks every job folder under the root you point
it at; there is no per-lesson-id filter flag. To re-run only the failed/fixed
subset out of a larger folder, don't re-run the whole folder (wastes fleet
capacity regenerating good lessons) and don't hand-edit the queue. On the
box, copy just the target subfolders into a fresh scratch folder and point
the batch CLI at that:

```powershell
$failed = Get-Content <failed-ids-file>   # one id per line
$dst = "<scratch-root>\rerun"
New-Item -ItemType Directory -Path $dst | Out-Null
foreach ($lid in $failed) {
  Copy-Item (Join-Path $src $lid) (Join-Path $dst $lid) -Recurse -Force
}
# then: python -m <producer_module>.dispatch batch $dst
```

Generalizes to any discover-by-folder batch CLI in this fleet family.
