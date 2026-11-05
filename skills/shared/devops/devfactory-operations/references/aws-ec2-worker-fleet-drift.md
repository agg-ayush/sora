# EC2 worker fleet drift audit & deploy verification

Class of task: "does worker fleet X actually run the code/branch/permissions we
think it does" (e.g. Windows COM autologon workers, golden-AMI baseline +
fleet CFN stack pairs), and "does a newly-implemented deploy workflow actually
work when triggered". There are **independent layers that can each say
something different** — the live answer is only the last one:

1. **CFN stack parameter** (e.g. `RepoBranch`) — what the *template* says.
2. **Golden AMI** — code/packages baked at whatever branch the AMI was built
   from; frozen until the next bake.
3. **Live on-disk state on the running instance** — the actual ground truth.
   UserData typically does a best-effort `git reset --hard origin/$RepoBranch`
   on **boot only**, so a long-running box diverges from (1) and (2)
   indefinitely.

Never conclude what a fleet runs from the CFN param or AMI name alone — SSM
into the actual box and check `git rev-parse --abbrev-ref HEAD` /
`git rev-parse HEAD`.

## Procedure

1. Get fresh admin AWS creds (see `aws-saml2aws-refresh.md`) and confirm the
   effective identity — clear stale exported `AWS_*` env vars first (see
   `aws-iam-credential-rotation.md` on this failure mode).
2. **Find the stacks** — CFN stack names don't always match the component
   name; list and grep rather than guessing:
   ```bash
   aws cloudformation list-stacks --profile trilogy --region <region> \
     --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
     --query "StackSummaries[?contains(StackName,'<component>')].[StackName,StackStatus]" --output table
   ```
3. **Read CFN params** (intent) and **AMI lineage** (bake time) for baseline
   and fleet stacks (`describe-stacks` params; `describe-images` for
   ImageId/Name/CreationDate).
4. **Find the actually-running instances** — `MaxFleetSize` > 0 does not
   guarantee running instances exist; a scaler can keep 0 clones up. Enumerate
   via `describe-instances` filtered on the stack-name tag, and note which AMI
   each instance *actually* launched from (can differ from the stack's current
   `GoldenAmiId`).
5. **Query the live box's git state via SSM** (works for Windows with the SSM
   agent — no RDP needed):
   ```bash
   CMD_ID=$(aws ssm send-command --profile trilogy --instance-ids <id> \
     --document-name "AWS-RunPowerShellScript" \
     --parameters '{"commands":["cd C:\\<path>\\<repo>; git rev-parse --abbrev-ref HEAD; git rev-parse HEAD"]}' \
     --query "Command.CommandId" --output text)
   sleep 8
   aws ssm get-command-invocation --profile trilogy --command-id "$CMD_ID" \
     --instance-id <id> --query "[Status,StandardOutputContent,StandardErrorContent]" --output text
   ```
6. **Quantify the drift against the repo**: `git merge-base --is-ancestor
   <box-head> origin/main` (already-merged vs diverged), and `git log --oneline
   <box-head>..origin/main -- <component-paths>` for what main has that the
   box lacks.
7. **Check whether the deploy workflow is real or a stub** before assuming
   push-to-main auto-updates the fleet (`grep -n "TODO\|echo"
   .github/workflows/deploy-<component>.yml`). A hollow/stubbed workflow is
   itself the root cause of drift. Present the one-time repoint (bootstrap
   `--update` against the live box) and the durable fix (implement the
   workflow) as separate, explicitly-labeled options — don't let either stand
   in for the other.

## "Merged + green CI" ≠ "the thing it deploys works"

Treat those as two separate claims — say so explicitly. CI is usually static
checks (YAML validity, shellcheck), not a live run of the workflow's AWS
calls. Before calling a new/first-time infra deploy workflow done, trigger it
for real (`gh workflow run <file> --ref main -f <input>=...` for
`workflow_dispatch`) and watch to completion: `gh run watch <run-id>
--exit-status`. Gap classes that only a live run surfaces:

1. **CI service user missing perms the workflow needs.** A CFN-deploying
   workflow run as a CI IAM user needs the CFN actions
   (`CreateChangeSet`/`ExecuteChangeSet`/`UpdateStack`/`DescribeStacks`) on the
   *target* stacks — a sibling fleet's already-working CI user is the fastest
   source of a correctly-scoped policy to clone. If the workflow also deploys
   IAM resources (a deploy-role stack pattern), the CI user separately needs
   IAM role-management perms (`iam:GetRole`, `iam:CreateRole`,
   `iam:PutRolePolicy`, `iam:DeleteRole*`, `iam:PassRole`) — easy to miss
   until the first real run fails on `iam:CreateRole AccessDenied`.
2. **A failed first attempt can leave a stack in `ROLLBACK_FAILED`** (roll
   target already deleted/changed outside CFN). This blocks any further
   update — `delete-stack` + wait `stack-delete-complete` before retrying;
   re-running the workflow does nothing.
3. **A slow-baking Windows AMI can blow past `aws ec2 wait image-available`'s
   default timeout (10 min) while the bake itself succeeds.** Do not "fix" it
   with `--max-attempts`/`--delay` — those are not top-level flags on `wait`
   in this CLI version and fail hard with `Unknown options`, making failure
   100% instead of occasional. Replace the waiter with a manual poll loop on
   `describe-images ... --query 'Images[0].State'` (fails fast on
   `failed`/`error` too).
4. **Verifying an AWS CLI flag/subcommand change must include actually
   invoking the real binary's arg parser** (`aws <service> <verb> help`, or a
   dry-run), not only unit-testing the surrounding shell logic with fake
   states — an unsupported flag passes a logic-only test every time.

### `mergeable` vs `mergeStateStatus` before merging a fleet-fix PR

`gh pr view --json mergeable: MERGEABLE` only means "no textual conflict".
Check `mergeStateStatus` too: `CLEAN` = actually mergeable; `BEHIND` = base
moved — rebase and note that a prior green checks run is stale evidence;
`BLOCKED` immediately after a rebase-push is expected (required checks are
evaluated against the new head SHA) — poll `gh pr checks --watch` until it
flips to `CLEAN`. Only merge on `CLEAN` + zero failing/pending required
checks.

### Cleaning up a merged branch's local worktree + stale tracking ref

After `gh pr merge --delete-branch` from the branch's own worktree:
`git checkout main` first, then `git branch -D`. The remote branch is usually
already gone server-side (`git ls-remote --heads origin <branch>` empty is
ground truth), but `refs/remotes/origin/<branch>` can linger through
`fetch --prune`, `push origin --delete`, and `branch -dr`. When porcelain
commands disagree with each other, drop to plumbing: `git update-ref -d
refs/remotes/origin/<branch>`.

## IAM role policy drift (a second drift axis)

The live worker's **IAM role inline policy** can drift from what the current
CFN template grants (role created by an older template version, never
re-synced). Symptom: after fixing code drift, the worker **crash-loops** with
`AccessDeniedException` reading its own config, even though the current
template clearly grants it. Diagnose by comparing live role policy
(`aws iam get-role-policy`) against what main's template grants — don't
assume the template is what's deployed. Two-tier fix: (a) fast unblock —
`put-role-policy` the missing statements onto the live role; (b) durable fix
— `update-stack` to the current template. Doing (a) alone leaves the stack
still drifted; say so explicitly.

### Durable CFN fix without replacing the instance

For a long-lived, hand-configured worker box, a naive `update-stack` with the
full current template risks CFN replacing the `AWS::EC2::Instance` —
unacceptable for a box you can't cheaply recreate:

1. Diff live template vs main's first; scope exactly what differs.
2. Build a patched template = live template + only the missing IAM
   statements, as a **targeted text edit**. Never round-trip a CFN YAML
   template through a generic YAML library — it destroys `!Ref`/`!Sub`/
   `!GetAtt` intrinsics, and CFN rejects the result or fails mid-rollout.
3. If a YAML template got saved with a `.json` extension, rename to `.yaml`
   before editing — JSON validation of `.json` files will refuse valid CFN
   YAML.
4. **Preview with a change set**; inspect `Changes[].ResourceChange
   .[LogicalResourceId,ResourceType,Action,Replacement]`. If anything besides
   the IAM role shows `Replacement=True`, do not execute — diagnose first.
5. **Pessimistic-replacement footgun**: an AMI param typed
   `AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>` pointing at an
   SSM-latest path can't be proven unchanged at plan time, so the change set
   flags the instance `Replacement=True` even when nothing changed. Fix: pin a
   dated SSM parameter to the AMI the box is actually running and pass that
   path as the param value — also stops the stack silently drifting to
   whatever SSM-latest resolves to next time. (Same class of issue for
   `!Ref`-ed SubnetId/KeyName/VpcId.)
6. **A rolled-back stack update reverts manual live patches** — re-apply the
   manual IAM patch immediately after a rollback so the worker isn't
   crash-looping while you debug the template, then retry the CFN fix.
7. After `execute-change-set`, verify no replacement happened: compare
   instance ID + `LaunchTime` before/after.

## Verify the worker is actually consuming

Right commit ≠ working worker. After any repoint/update, poll actual health
via SSM: check the worker process is alive (`Get-CimInstance Win32_Process`
filtered on the worker module) and tail the worker log for `CRASH LOOP` /
repeated AccessDenied / `polling <queue-url>`. Crash loops retry on backoff —
wait one full `nextRetryInSec` interval after an IAM fix before re-checking.

## Golden-AMI package drift: InService fleet, queue not draining

A third drift class: the AMI's baked Python environment predates a package
the worker now needs. Symptom sequence: fleet scaled out, instances
`InService`, but the SQS queue stays flat across repeated polls (sample 2-3×,
30-60s apart, before concluding "stuck"); scheduled task `State: Running` but
no live python process (dying/restarting faster than one poll catches);
worker log shows `ModuleNotFoundError` + `CRASH LOOP`. Prove the package is
missing directly (`find_spec` returns None / `pip show` errors) rather than
inferring from the log. Root cause: **fresh fleet boxes boot from the golden
AMI and never run the bootstrap's first-time install path**, so a package
added after the last bake is missing on every new box while the baseline
(which got the update directly) works. Fix: rebake the AMI from the live
baseline (`gh workflow run <deploy-workflow> -f bake_ami=true`), then confirm
actual drain — poll the queue until it moves and spot-check a fresh box's log
for a successful poll line. "Rebake triggered" and "queue confirmed
draining" are two separate claims.

**Self-heal at boot, don't gate-and-fail at bake time**: for a recurring
missing-dependency class of bug, the primary fix is the box fixing itself at
boot (reinstall + verify the import resolves before starting the worker loop).
A bake-time gate that fails loudly produces an alert nobody watches; a gate is
acceptable only as a secondary signal.

## Fleet-wide deploy switch: `S3_BUCKET`/`CLOUDFRONT_*` in the worker's SSM namespace

If the deployed worker's bootstrap hydrates its deploy-step env from its SSM
secrets path, `S3_BUCKET`/`CLOUDFRONT_DOMAIN`/`CLOUDFRONT_DISTRIBUTION_ID`
under that path are the **single fleet-wide switch for which environment
every future generation job deploys to** — no per-job override. Before
running any batch/bulk generation on a test/validation pipeline branch, check
this SSM value first and confirm it matches where the user wants content to
land:

```bash
aws ssm get-parameters --region <region> \
  --names /<ns>/S3_BUCKET /<ns>/CLOUDFRONT_DOMAIN /<ns>/CLOUDFRONT_DISTRIBUTION_ID \
  --with-decryption --query "Parameters[*].[Name,Value]" --output text
```

To retarget the fleet, pull the dev identifiers from a source that already
splits them correctly and `put-parameter --overwrite` each. If content
already landed on the wrong bucket, that's a full-tree move (manifest + every
asset key under the prefix), a separate step from flipping the switch.

### Moving published content between environments — four steps, not two

A published lesson-plan JSON bakes in the **absolute CDN host** it was
published against (`base_url`/`video_base_url`), and the player resolves
media from those JSON fields, not from where the files sit. An environment
move is: (1) copy the full keyspace, (2) **rewrite `base_url`/`video_base_url`
in every moved JSON** to the target host, (3) delete from the source, (4)
**invalidate the destination CDN** for the rewritten keys. Skipping (2) leaves
the migration looking complete while every lesson 403s against the old host.

- Step (4) is easy to skip because the symptom looks like step (2) not
  running. CloudFront ignores query strings by default and serves its cached
  pre-rewrite copy — diagnose from headers, not body: `x-cache: Hit from
  cloudfront` + large `age` = stale cached hit. Fire `create-invalidation` on
  the **destination** distribution; invalidate the whole relevant prefix (a
  broad wildcard beats N precise paths, especially around literal `+` in
  lesson ids, which can silently fail to match). Verify by re-fetching the
  exact URL the player hits and checking both the rewritten body field AND a
  fresh `x-cache`/`age`.
- `aws s3 sync`/`cp` on a single-key path containing `+` can silently no-op
  while the script logs "OK" — **verify each moved key with a `head-object`
  against the destination before deleting the source**, for anything with
  special characters in the key. With versioning enabled, a lost object is
  recoverable from a prior version even after a delete-marker.

## Ad-hoc scripts invoking pipeline code: replicate the worker's env hydration

The worker's invocation path hydrates secrets from SSM Parameter Store into
the process environment before calling the pipeline; your ad-hoc script does
not, and the failure surfaces as an opaque `KeyError: 'TFY_BASE_URL'` deep in
an unrelated-looking import chain while every job "succeeds" at the
SSM-command level. Check the per-item outcome your script logs, not the
overall SSM status. Before invoking pipeline code from an ad-hoc script,
hydrate the same SSM namespace the worker's bootstrap reads (grep the
bootstrap for the exact path prefix):

```python
import boto3, os
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
for page in ssm.get_paginator("get_parameters_by_path").paginate(Path="/<ns>/", Recursive=True, WithDecryption=True):
    for p in page["Parameters"]:
        os.environ.setdefault(p["Name"].split("/")[-1], p["Value"])
```

A pipeline's **deploy/publish step can need a second, separate credential
layer** beyond the worker's SSM secrets — e.g. explicit
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` env (checked via `os.getenv`, not
the instance role) plus `S3_BUCKET`/`CLOUDFRONT_*`. Grep the component's
settings module for `os.getenv("AWS_` before assuming the instance role is
enough.

**Credential-ordering bug**: never set explicit deploy credentials on the
whole process env before other AWS SDK calls (SSM hydration etc.) run in the
same process — every subsequent SDK call then authenticates as the deploy
user and fails with an opaque `AccessDenied ... ssm:GetParametersByPath` that
looks like a permissions gap but is a credential-scoping bug. Hydrate
role-scoped things FIRST, then pass a **narrow env dict override only for the
deploy subprocess** (`env=dict(os.environ, AWS_ACCESS_KEY_ID=...)`), never
assign deploy creds onto the parent's `os.environ`.

See `aws-batch-producer-creds.md` for the producer-side variant of the same
pattern.

## Content-job failure diagnosis: content bug vs infra bug

Once the worker is on the right code and IAM-healthy, a submitted job can
still fail because the *input* didn't parse — distinguish before touching
infra:

1. **Inspect the job's output directory on the box via SSM** — list files +
   sizes first; a suspiciously tiny output file is the tell for "parsed to
   nothing".
2. **Don't trust a "PASSED" validation report at face value.** Deterministic
   validators that check *properties of* a list report PASS vacuously when the
   list is empty — cross-check the actual element count, not just the
   validator's verdict.
3. **Reproduce the parser locally against the real input file** — throwaway
   venv with the component's `src/` on `PYTHONPATH` plus its runtime deps,
   call the parser on both the failing file and a known-good fixture;
   zero-vs-healthy section/event counts is conclusive proof of a format
   mismatch.
4. **A spec doc can describe a grammar the parser doesn't implement.** The
   parser's own regexes and its `tests/fixtures/` are the only ground truth
   for what's supported — check the fixtures, not the spec, when validating a
   new source document's format.
5. **Don't re-run a submit-and-watch command to "check on" a job** — if the
   CLI re-enqueues on every invocation, you're sending a genuine duplicate
   (FIFO dedupes by content, not by job). If a duplicate slips in, write a
   cancel/revoke marker the worker checks at pickup rather than deleting an
   in-flight queue message.

**Validate against the ACTUAL downstream gate, not a proxy.** A multi-stage
pipeline can have validators that check different things (structural parse vs.
semantic resolvability); a repair pass validated with the wrong one reports
"all fixed", re-queues, and fails again identically. Confirm which stage
produced the failure log line, read THAT module's check, write a standalone
offline checker against that exact semantic, and sanity it against a
known-failing example before trusting it to clear a batch.

## Operating on Windows worker boxes via SSM

- **Multi-line scripts: base64 payload, not inline escaping.** Local shell →
  SSM JSON → remote PowerShell quoting breaks on anything beyond a one-liner.
  Write the script locally, base64-encode it, decode-and-write on the box in
  one `send-command`, execute it in a second.
- **GUI/COM-dependent scripts silently no-op under raw SSM** (Session 0, no
  interactive desktop): fast clean exit-0 with zero observable effect is the
  tell. Trigger the script's **scheduled task** via `Start-ScheduledTask`
  (runs in the real interactive autologon session) instead of invoking the
  `.ps1` directly; confirm real completion via the script's event-log source,
  not the SSM exit code alone. Note: triggering the task guarantees it *ran*,
  not that the external service granted what it asked.
- **Grace-expired Office licensing does not necessarily block headless COM**:
  reduced-functionality mode blocks the interactive UI, but a win32com script
  that creates/saves a presentation can still succeed — run a minimal COM
  smoke test before treating license-refresh as a prerequisite.
- **Bootstrap `--update` task-state behavior varies per fleet**: some fleets
  preserve a paused (disabled) worker across `--update`, others unconditionally
  re-register + start it. Check the actual bootstrap script's update path
  before running `--update` on a paused box — force-enabling it is a scope
  decision, worth a quick clarify.

## Batch counting & fan-out conventions

- **Count batch outcomes strictly by the batch's own naming convention**, not
  an ad hoc grep pattern — a shared S3 job prefix accumulates manual, e2e, and
  batch jobs distinguished only by the naming convention the batch CLI's
  discover step uses (read its code or logged output before writing the
  query). Grep-pattern drift makes the same batch total change every turn.
- **Fan-out content repair via parallel subagents: pin the output convention
  up front** — state the exact shared path each shard writes to, or (better,
  when a source of truth exists) require each shard to write its result
  directly back to the source of truth as its LAST step. Afterwards verify
  the source reflects every shard's fix by spot-checking one file per range —
  shards reporting success is not the same thing.

## Comment hygiene in infra PRs

Operational-safety comments state the concern in one clause and stop — one
concise line per comment, not a reasoning trail. Sweep every comment you
added across the whole PR's files when trimming, not just the file that
triggered the feedback.

## CFN template-only edit verification

For a template-only change with no runtime behavior, the canonical check is
`aws cloudformation validate-template` (+ `bash -n` for touched shell
scripts). State explicitly that this is template-validate + syntax-check,
not a test suite — don't oversell it as "verified".

## Scope & communication

- Distinguish the one-time repoint from the durable pipeline fix and present
  both; ask which scope the user wants before shared-infra changes.
- A standing "don't ask again" authorization covers the rest of that bounded
  task (the batch, the backlog, the remediation chain it was given for) — keep
  executing to the stated end-state; reserve clarify for genuinely new classes
  of decision outside what was authorized.
- If a clarify about a scope decision got no answer because the conversation
  moved on, don't re-ask later; proceed with the unambiguous part and state
  plainly what's done vs. still pending that call.
