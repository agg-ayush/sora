---
name: aws-worker-fleet-drift-audit
description: "Verify what code/branch AND what IAM permissions are actually live on a deployed AWS EC2 worker fleet (Windows COM autologon workers, golden-AMI baseline+fleet CFN pairs, etc.) versus what the repo/CI/template believes is deployed — diagnose gaps in the deploy pipeline that let them drift, and once a fix/new deploy workflow is implemented, test it end-to-end via a real trigger (not just green CI). Use whenever asked to check/fix which branch a worker points to, why a fleet seems stale, why a worker crash-loops with AccessDenied after a repoint, whether a deploy workflow actually pushes code to running instances, or to verify a newly-built/first-time deploy workflow actually works when run."
tags: [aws, ec2, ssm, cloudformation, ami, drift, ci-cd, windows, alpha-learn, iam-drift, crash-loop, script-to-lesson, parser-format-mismatch, workflow-testing, ami-bake-timeout]
related_skills: [aws-iam-credential-rotation, content-pipeline-data-layers]
metadata:
  hermes:
    tags: [aws, ec2, ssm, cloudformation, ami, drift, ci-cd, windows, alpha-learn]
    related_skills: [aws-iam-credential-rotation, content-pipeline-data-layers]
---

# AWS Worker Fleet Code-Drift Audit

Class of task: "does worker fleet X actually run the code/branch we think it
does" — e.g. alpha-learn's script-generation / article-generation /
video-render Windows COM worker fleets (baseline + auto-scaled golden-AMI
fleet CFN stack pairs). These fleets have **three independent layers** that
can each say something different, and the live answer is only the third one:

1. **CFN stack parameter** (e.g. `RepoBranch`) — what the *template* says it
   should deploy. Checking this alone is not sufficient evidence.
2. **Golden AMI** — code baked in at whatever branch was checked out the
   moment the AMI was built. Frozen until the next bake; doesn't track `main`
   automatically.
3. **Live on-disk git checkout on the running instance** — the actual ground
   truth. UserData typically does a best-effort `git fetch` + `reset --hard
   origin/$RepoBranch` on **boot only**. If a box has been running since
   before a branch/param change, or an `--update` was never re-run against
   it, its checkout can silently diverge from both (1) and (2) indefinitely.

**Never conclude "workers are on branch X" from the CFN param or the AMI name
alone — SSH/SSM into the actual box and check `git rev-parse --abbrev-ref
HEAD` and `git rev-parse HEAD`.** In one audit, the CFN `RepoBranch` param
already read `main` and the fleet UserData already reset to `origin/main`,
yet the one running instance was still on a stale feature branch weeks old —
because it launched before the switch and no bootstrap/update had touched it
since.

## Procedure

1. **Get admin AWS creds** (see `aws-saml2aws-refresh` skill) and confirm
   effective identity — clear stale exported `AWS_*` env vars first (see
   `aws-iam-credential-rotation` pitfall on this same failure mode):
   ```bash
   unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE
   aws sts get-caller-identity --profile trilogy --query Arn --output text
   ```
2. **Find the stacks** — CFN stack names for these fleets don't always match
   the component name obviously; list and grep rather than guessing:
   ```bash
   aws cloudformation list-stacks --profile trilogy --region <region> \
     --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
     --query "StackSummaries[?contains(StackName,'<component>')].[StackName,StackStatus]" --output table
   ```
3. **Read CFN params** (intent) and **AMI lineage** (bake time) for both the
   baseline and fleet stacks:
   ```bash
   aws cloudformation describe-stacks --profile trilogy --stack-name <stack> \
     --query "Stacks[0].Parameters[].[ParameterKey,ParameterValue]" --output text
   aws ec2 describe-images --profile trilogy --image-ids <ami-id> \
     --query "Images[0].[ImageId,Name,CreationDate]" --output text
   ```
4. **Find the actually-running instance(s)** — don't assume the fleet's
   `MaxFleetSize`/`BaselineReserve` means instances exist; check directly, and
   note which AMI each one *actually* launched from (can differ from the
   stack's current `GoldenAmiId` if it launched before the last AMI update):
   ```bash
   aws ec2 describe-instances --profile trilogy \
     --filters "Name=tag:aws:cloudformation:stack-name,Values=<baseline-stack>,<fleet-stack>" \
                "Name=instance-state-name,Values=running,pending" \
     --query "Reservations[].Instances[].[InstanceId,ImageId,LaunchTime,Tags[?Key=='Name'].Value|[0]]" --output text
   ```
5. **Query the live box's actual git state via SSM** (works for Windows
   instances with the SSM agent — no RDP/interactive session needed):
   ```bash
   CMD_ID=$(aws ssm send-command --profile trilogy \
     --instance-ids <instance-id> \
     --document-name "AWS-RunPowerShellScript" \
     --parameters '{"commands":["cd C:\\<repo-worker-path>\\<repo-name>; Write-Output (\"BRANCH: \" + (git rev-parse --abbrev-ref HEAD)); Write-Output (\"HEAD: \" + (git rev-parse HEAD)); git log -1 --format=\"%ci %h %s\""]}' \
     --query "Command.CommandId" --output text)
   sleep 8
   aws ssm get-command-invocation --profile trilogy --command-id "$CMD_ID" --instance-id <instance-id> \
     --query "[Status,StandardOutputContent,StandardErrorContent]" --output text
   ```
6. **Quantify the drift against the repo**, not just "is it behind":
   ```bash
   git fetch origin main <stale-branch> --quiet
   git merge-base --is-ancestor <box-head-sha> origin/main && echo "already merged" || echo "diverged / commits box has that main lacks"
   git log --oneline <box-head-sha>..origin/main -- <component-paths>   # commits main has that the box is missing
   ```
7. **Check whether the deploy workflow is real or a stub** before assuming a
   push-to-main auto-updates the fleet:
   ```bash
   grep -n "TODO\|echo" .github/workflows/deploy-<component>.yml
   ```
   A hollow/stubbed deploy workflow (just an `echo` placeholder) is itself the
   root cause of drift, distinct from any one-time manual fix — flag both:
   the immediate repoint (bootstrap `--update` against the live box) and the
   structural gap (implement the workflow) as separate, explicitly-labeled
   options for the user to choose from.

## Testing a newly-implemented deploy workflow end-to-end (not just CI-green)

Once a hollow deploy workflow has been implemented for real (see previous
section), **merging it with green CI is not evidence it works** — CI here is
usually static checks (YAML validity, shellcheck, unit tests on unrelated
components), not a live run of the workflow's actual AWS calls. Before
calling a new/first-time infra deploy workflow done, trigger it for real
(the merge's own push, or `gh workflow run <file> --ref main -f <input>=...`
for `workflow_dispatch`) and watch it to completion —
`gh run watch <run-id> --exit-status`. Two gap classes surfaced this way that
static review won't catch:

1. **CI service user missing perms the workflow needs.** A CFN-deploying
   workflow run as a CI IAM user (e.g. `<component>-ci`, driven by
   `secrets.AWS_ACCESS_KEY_ID`) needs the CFN actions
   (`CreateChangeSet`/`ExecuteChangeSet`/`UpdateStack`/`DescribeStacks`) on
   the *target* stacks — a sibling fleet's already-working CI user (e.g.
   article-generation's) is the fastest source of a correctly-scoped managed
   policy to clone and re-scope to the new stack ARNs. But if the workflow
   also deploys IAM resources (a "deploy role" stack pattern, so the actual
   `update-stack` runs `--role-arn <deploy-role>` instead of the CI user's
   own broad perms), the CI user separately needs **IAM role-management
   perms** (`iam:GetRole`, `iam:CreateRole`, `iam:PutRolePolicy`,
   `iam:DeleteRole*`, `iam:PassRole`) to create/tear down that role stack —
   easy to miss because it looks like "just a CFN deploy" until the first
   real run fails on `iam:CreateRole AccessDenied`.
2. **A failed first attempt can leave a stack in `ROLLBACK_FAILED`,
   especially if a resource it tried to roll back to was already
   manually deleted/changed outside CFN.** `ROLLBACK_FAILED` blocks any
   further update — you must `aws cloudformation delete-stack` and
   `aws cloudformation wait stack-delete-complete` before retrying, not
   just re-run the workflow.
3. **A slow-baking Windows golden AMI can blow past the default
   `aws ec2 wait image-available` timeout even though the bake itself
   succeeds.** The default waiter is 40 attempts × 15s = 10 min; a Windows
   AMI bake can take ~13 min, so the script/job exits non-zero right as the
   AMI transitions to `available` in the background — a false failure, not
   a real one. Symptom: the workflow step fails, but `aws ec2
   describe-images --image-ids <ami>` a few minutes later shows `available`.
   **`aws ec2 wait image-available` does not accept `--max-attempts`/
   `--delay` as top-level CLI flags on this aws CLI version** — passing them
   fails hard with `Unknown options: --max-attempts, --delay`, which is
   worse than the original 10-min timeout (100% failure instead of an
   occasional false one). Do not "fix" the timeout by adding waiter flags to
   the `wait` subcommand. Instead replace the waiter with a manual poll
   loop against `describe-images`:
   ```bash
   AMI_STATE=""
   for _ in $(seq 1 90); do   # 90 x 20s = 30 min budget
     AMI_STATE=$(aws ec2 describe-images --region "$REGION" --image-ids "$NEW_AMI" \
       --query 'Images[0].State' --output text 2>/dev/null || echo "pending")
     if [[ "$AMI_STATE" == "available" ]]; then break
     elif [[ "$AMI_STATE" == "failed" || "$AMI_STATE" == "error" ]]; then
       echo "AMI $NEW_AMI entered state '$AMI_STATE'; aborting." >&2; exit 1
     fi
     sleep 20
   done
   [[ "$AMI_STATE" == "available" ]] || { echo "AMI $NEW_AMI not available after 30 min (state: $AMI_STATE)" >&2; exit 1; }
   ```
   This also fails fast on a genuinely `failed`/`error` AMI instead of
   burning the full timeout. If a run fails on the *old* waiter-flag bug
   after the AMI already finished baking, you can finish the interrupted
   deploy manually (repoint the fleet's `GoldenAmiId` param to the
   now-available AMI via `update-stack`, then deregister the old AMI +
   delete its snapshot) rather than re-running the whole workflow.
4. **Merged + green CI on a PR that touches this wait logic is not
   sufficient evidence it works** — static CI (shellcheck, YAML validity)
   doesn't execute the actual `aws ec2 wait`/poll call against a real AMI.
   The waiter-flags bug above only surfaced on the first *live* push-triggered
   rebake after merge. Treat a bake-wait/poll change as unverified until a
   real bake has gone through it end-to-end at least once.

Treat "PR is CLEAN/mergeable with green CI" and "the thing it deploys
actually works when triggered" as two separate claims — say so explicitly
rather than letting the former stand in for the latter.

### `mergeable` vs `mergeStateStatus` before merging a fleet-fix PR

`gh pr view <N> --json mergeable` returning `MERGEABLE` only means "no
textual conflict" — it does not mean the PR is ready to merge right now.
Check `mergeStateStatus` too: `CLEAN` = actually mergeable (checks current
against the latest base); `BEHIND` = base has moved since the PR's head was
last rebased, so a prior green `gh pr checks` run may be stale evidence —
rebase (`git fetch origin main && git rebase origin/main && git push
--force-with-lease`) if fresh CI against current `main` matters; `BLOCKED`
immediately after that rebase-push is expected (GitHub is waiting on
required checks against the new head SHA — the old green run no longer
counts), not a regression — poll `gh pr checks --watch` until it flips to
`CLEAN`. Only merge on `CLEAN` + 0 failing/pending required checks.

### Cleaning up a merged branch's local worktree + stale remote-tracking ref

After `gh pr merge --delete-branch` when the branch was checked out in the
current worktree, `git branch -D <branch>` fails ("used by worktree") —
`git checkout main` first, then delete. The remote branch is usually already
gone server-side by then (`git ls-remote --heads origin <branch>` returning
empty is the ground truth), but the local `refs/remotes/origin/<branch>`
tracking ref can linger and keep showing up in `git branch -r --list` even
after `git fetch --prune`, `git push origin --delete <branch>` (fails
"remote ref does not exist" — already gone), and `git branch -dr <branch>`
(fails "not found" despite `branch -r --list` still showing it — a
porcelain/loose-ref inconsistency). When the porcelain commands disagree with
each other, drop to plumbing: `git update-ref -d
refs/remotes/origin/<branch>` removes it directly and is the reliable fix.

## Beyond code: IAM role policy drift

Code-checkout drift (steps 1-7 above) isn't the only kind. The live worker's
**IAM role inline policy** can also drift from what the current CFN template
grants — the role was created by an older template version and never
re-synced via `update-stack`, so it's missing statements the template has
had for a while. Symptom: after fixing code drift and (re)starting the
worker, it **crash-loops** on startup with `AccessDeniedException` reading
its own config (e.g. `ssm:GetParametersByPath` on `/alpha-gen/*`), even
though the SSM parameters exist and the current template clearly grants that
access.

Diagnose the same way as code drift — compare live vs. template, don't
assume the template is what's deployed:
```bash
aws iam get-role-policy --profile trilogy --role-name <worker-role> \
  --policy-name <policy-name> --query "PolicyDocument.Statement[].Sid" --output json
# compare against what main's template actually grants:
git show origin/main:infra/<component>/<baseline-template>.yaml | grep -A8 "Sid: ReadSecrets"
```
Two-tier fix, same pattern as code drift: (a) fast unblock — `put-role-policy`
the missing statements onto the live role directly; (b) durable fix — the
baseline/fleet CFN stack needs an `update-stack` to the current template so
the role isn't perpetually out of sync. Doing (a) alone leaves the stack
still drifted; say so explicitly rather than letting a live patch pass as
"fixed."

### Making the IAM fix durable via CFN without replacing the instance

Naively running `update-stack` with the full current template against a
long-lived, hand-configured worker box (Office-activated, autologon, etc.)
risks CFN replacing the `AWS::EC2::Instance` — unacceptable for a box you
can't cheaply recreate. Full procedure:

1. **Diff live template vs. `main`'s template first** (`get-template` on the
   stack vs. `git show origin/main:infra/.../*.yaml`, both parsed as YAML) to
   scope exactly what differs — don't blindly deploy `main`'s template.
2. **Build a patched template = live template + only the missing IAM
   statements**, editing the live template text in place. **Never
   parse-and-re-serialize a CFN YAML template through a generic YAML
   library** to make this edit — round-tripping destroys `!Ref`/`!Sub`/
   `!GetAtt`/`!Base64` intrinsics (they get flattened to plain strings or
   dropped), and CFN will reject the result with type-mismatch errors like
   `Invalid value for property 'InstanceType'`, or worse, `update-stack` will
   proceed and then fail mid-rollout. Insert the new statements as a targeted
   text edit into the untouched original file instead.
3. **If the live template happens to be saved with a `.json` extension**
   (e.g. fetched via `get-template --query TemplateBody` and it came back as
   YAML text piped into a `.json`-named temp file), copy it to a `.yaml`
   filename before editing with `patch` — the patch tool JSON-validates
   `.json` files and will refuse to write valid CFN YAML into one.
4. **Preview with a change set before executing** and inspect
   `Changes[].ResourceChange.[LogicalResourceId,ResourceType,Action,Replacement]`.
   If anything besides the IAM role shows `Replacement=True`, do not execute
   — diagnose first (see next point).
5. **Pessimistic-replacement footgun:** if the stack's AMI parameter is typed
   `AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>` pointing at an
   *SSM-latest* path (e.g. `/aws/service/ami-windows-latest/...`), CFN's
   change-set static analysis can't prove the resolved `ImageId` is unchanged
   at plan time (same for `SubnetId`/`KeyName`/`VpcId` when they're `!Ref`
   params) — it flags them `RequiresRecreation: Always` and shows
   `WorkerInstance: Modify, Replacement=True` even when nothing about the
   instance actually changed. Fix: create a **dated SSM parameter** pinned to
   the AMI ID the box is *actually running* (`aws ssm put-parameter --type
   String --value <running-ami-id>` under a private path, e.g.
   `/alpha-learn/<component>/windows-base-ami`), pass that path as the
   stack's AMI parameter value (`UsePreviousValue` for every other param), and
   re-preview — the change set should now show only the IAM role as
   `Modify, Replacement=False`. This also has a lasting benefit: the stack
   stops silently drifting toward whatever AMI the SSM-latest path resolves
   to on the *next* unrelated update.
6. **A rolled-back stack update reverts manual live patches.** If a
   change-set execution fails and rolls back, CFN restores the *previous*
   resource state — including reverting any `put-role-policy` you'd applied
   directly to the live role outside CFN as the tier-(a) unblock. Re-apply
   the manual IAM patch immediately after a rollback (before doing anything
   else) so the worker doesn't sit crash-looping while you debug the
   template — then retry the CFN fix.
7. **After `execute-change-set`, verify no replacement happened**: compare
   the instance ID and `LaunchTime` before/after
   (`aws ec2 describe-instances --query "...[InstanceId,State.Name,LaunchTime]"`).
   Identical ID + identical `LaunchTime` = confirmed in-place update.

## Verify the worker is actually consuming, not just on the right commit

`git rev-parse HEAD` matching `main` is necessary but not sufficient — the
process can still be crash-looping (bad IAM, missing config, bad code path).
After any repoint/update, poll actual worker health via SSM before declaring
done:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match '<worker-module>' }
Get-Content C:\<work-root>\logs\worker.out.log -Tail 12   # look for "CRASH LOOP" / repeated AccessDenied / "polling <queue-url>"
```
A crash-loop retries on an increasing backoff (seconds, not instant) — if you
just applied an IAM fix, wait one full retry interval (state it in the log:
`nextRetryInSec=N`) before re-checking, IAM propagation isn't always instant.

## Bootstrap `--update` task-state behavior varies per fleet

Don't assume all fleets' bootstrap scripts preserve a paused
(Disabled-scheduled-task) worker across an `--update` run. Some fleets
(e.g. article-generation) explicitly preserve enabled/disabled state; others
(e.g. script-generation) unconditionally `Register-ScheduledTask` +
`Start-ScheduledTask`, silently turning a paused/non-consuming box back into
a live consumer. Check the actual bootstrap script's update-path logic
before running `--update` against a box you know is currently paused — if it
will force-enable, that's a scope decision (does the user want it consuming
again right now?) worth a quick clarify, not an assumption.

## GUI/COM-dependent scripts silently no-op under raw SSM — trigger via the scheduled task

Raw `aws ssm send-command` on a Windows box executes in **Session 0**
(non-interactive service context). Any script step that needs a real desktop
— relaunching Office apps for COM re-validation (e.g. an Office/O365
activation-refresh script that reopens PowerPoint to re-check licensing),
or anything else that spawns a GUI process to interact with it — will
either fail outright or **exit 0 having silently skipped the GUI-dependent
part**, because there's no interactive session for the spawned process to
render into.

Symptom pattern: the command reports `Status: Success`, `exit_code: 0`, in a
few seconds, but the script's own log file shows no new entries (or the
underlying scheduled task's `LastTaskResult` doesn't move) — a fast, clean
exit with zero observable effect is the tell, not a thrown error.

Fix: find the scheduled task that normally runs this script (`Get-ScheduledTask
-TaskName <name>` — check `Principal.UserId` / `LogonType: Interactive`,
confirming it runs as the autologon user, e.g. `scriptgen`) and trigger it
via `Start-ScheduledTask -TaskName <name>` (still sent through SSM — that
part is fine) instead of invoking the target `.ps1` directly. The task then
executes inside the real interactive session (verify with
`query session` / `quser` showing an `Active` session with `explorer`
running) where PowerPoint/Office COM can actually render and re-validate.
Confirm real completion via the eventlog source the script logs to (its own
file logger may be broken/misconfigured — cross-check
`Get-EventLog -LogName Application -Source <worker-name>` for
start/done markers with timestamps) rather than trusting the SSM command's
own exit code alone.

Note the limits of this fix: triggering the task correctly guarantees the
script *ran*, not that the underlying licensing/activation call *succeeded*
— a dead cached subscription token, for instance, still returns "no
renewal" even on a perfect run. Don't conflate "script executed properly in
the right session" with "the external service granted what it asked for."

**A grace-expired/reduced-functionality Office license does not necessarily
block headless COM automation.** Reduced-functionality mode (`LicenseStatus:
5`, "Notification" channel) blocks the *interactive editing UI*, but a
win32com-driven script that creates a `Presentation`, adds content, and
saves can still succeed — verified by running a minimal COM smoke test
(`New Presentation → add slide → SaveAs → quit`) as the autologon user via
the scheduled-task pattern above. Don't assume grace-expiry is a hard
blocker for a PPTX-generation pipeline; test COM directly before treating
license-refresh as a prerequisite to unblocking generation jobs.

## Fleet InService but queue not draining — AMI package/dependency drift crash-loop

A distinct drift class from code-checkout drift and IAM drift above: the
**golden AMI's baked Python environment** can predate a package the worker
now needs (added to the bootstrap's install list, or to the always-on
baseline, after the AMI was last baked). Symptom sequence:

1. You scale the fleet out (e.g. raise `DesiredCapacity`/submit a large
   batch) and `describe-auto-scaling-groups`/`describe-instances` shows N
   boxes `InService` — looks healthy.
2. But the SQS queue's `ApproximateNumberOfMessages` (+`NotVisible`) stays
   flat across repeated polls (30-60s apart) instead of draining — sample it
   at least 2-3 times before concluding it's stuck; a single read can't
   distinguish "stuck" from "just started."
3. `Get-ScheduledTask` on a fleet box shows the worker task `State: Running`
   but **no live python process** — the task is registered but the process
   keeps dying and restarting faster than a single poll catches it.
4. The worker's own log on that box shows the real cause:
   ```
   ModuleNotFoundError: No module named '<worker_package>'
   CRASH LOOP: <ts> worker exited (code=1 ranFor=0s consecutiveFastExits=N nextRetryInSec=M)
   ```
   Confirm directly rather than inferring from the log alone — run a tiny
   probe on the box's python (`importlib.util.find_spec("<pkg>")` returns
   `None`, `pip show <pkg>` errors) to prove the package genuinely isn't
   installed on that box, not just failing to import for some other reason.

Root cause: **fresh fleet instances boot straight from the golden AMI** and
do NOT run the bootstrap's full "first-time install" path the way the
baseline box did when it was set up/updated — if a package was added to the
install list *after* the AMI was last baked, every new fleet box inherits
the stale AMI and crash-loops immediately, even though the always-on
baseline box (which got the update applied directly) works fine. This is
easy to miss because `InService`/`Running` state only reflects the ASG/OS
task registration, not whether the process inside is actually surviving.

**Fix:** trigger a golden-AMI rebake from the current (working) baseline —
this is the same `bake_ami`/`rebake` job referenced earlier in this skill,
not a new mechanism:
```bash
gh workflow run <deploy-workflow>.yml --ref <branch> -f bake_ami=true
```
Then wait for the rebake job to complete (it re-bakes from the live
baseline, so whatever the baseline currently has installed becomes the new
AMI), and confirm actual drain — don't just check `InService` count again:
poll the queue's `ApproximateNumberOfMessages`/`NotVisible` until it moves,
and spot-check a freshly-launched box's worker log for a successful
`polling <queue-url>` / job-completion line instead of the crash-loop
pattern. Treat "rebake triggered" and "queue confirmed draining post-rebake"
as two separate claims — don't report the fix as done until the second is
verified.

## Diagnosing a failed content-generation job on the worker (content bug vs. infra bug)

Once the worker is confirmed on the right code and IAM-healthy (sections
above), a submitted job can still fail for reasons that have nothing to do
with fleet drift — the pipeline ran fine but the *input script* didn't parse.
Distinguish the two before touching any infra:

1. **Inspect the lesson's output directory on the box via SSM** — list
   files + sizes first, this alone often reveals the failure shape
   (suspiciously tiny `slides.yaml` / `agent1_content_plan.json` /
   `athena_article.md` is the tell for "parsed to nothing"):
   ```powershell
   $d = 'C:\<work-root>\gen-output\Grade <g>\<lesson-id>'
   Get-ChildItem $d | Select-Object Name, Length | Format-Table -AutoSize
   Get-Content "$d\slides.yaml" -TotalCount 30
   Get-Content "$d\agent3_validation_report.txt"
   ```
2. **Don't trust a "PASSED" validation report at face value.** Deterministic
   validators that check *properties of* the slide list (schema, no dup
   triggers, etc.) report PASS vacuously when the list is empty — "slides
   array is empty (matches plan) — no elements to check" reads like success
   but means the planner produced nothing. Cross-check the actual slide/event
   count, not just the validator's verdict.
3. **Reproduce the parser locally against the real input file** — this is
   the decisive step that turns "probably a format issue" into a proven root
   cause. Spin up a throwaway venv with the component's `src/` on
   `PYTHONPATH` plus its runtime deps (check `pyproject.toml` /
   the package's internal imports for what's needed, e.g. `num2words`,
   `pydantic`, `pillow`, `numpy`), then call the parser directly on both the
   failing file and a known-good fixture from `tests/fixtures/*.md`:
   ```bash
   python -m venv /tmp/parse-test-venv
   /tmp/parse-test-venv/bin/pip install -q num2words pydantic pillow numpy
   PYTHONPATH=components/<component>/src /tmp/parse-test-venv/bin/python -c "
   from <pkg>.parser import parse_script
   for label, p in [('FAILING', '<path-to-input>'), ('FIXTURE', 'components/<component>/tests/fixtures/<known_good>.md')]:
       s = parse_script(p)
       print(label, 'sections=', len(s.sections), 'events=', sum(len(sec.events) for sec in s.sections))
   "
   ```
   `sections=0 total_events=0` on the failing file vs. a healthy count on the
   fixture is conclusive proof of a format mismatch, independent of anything
   in the job logs.
4. **A spec/brainlift doc can describe a grammar the parser doesn't actually
   implement yet.** A markdown spec documenting a "v2" input format (e.g. a
   slide-header grammar with no timestamps) is not evidence the shipped
   parser accepts it — the parser's own regexes (and the `tests/fixtures/`
   files it's tested against) are the only ground truth for what's actually
   supported. If a human-authored source script matches the spec doc but not
   the fixtures' shape, the parser will silently return zero sections rather
   than erroring — check the fixtures, not the spec, when validating a new
   source document's format before submission.
5. **Don't resubmit a job with the same submit-and-watch command to "check on
   it"** — if the underlying CLI/dispatch call re-enqueues on every
   invocation (rather than just attaching to an existing job), re-running it
   sends a genuine duplicate message. FIFO queues with
   `MessageGroupId=<lesson_id>` preserve order but do **not** dedupe by
   content — a duplicate will sit queued behind the original and get
   processed later unless explicitly cancelled. If a duplicate slips in,
   write a cancel/revoke marker the worker checks before/at pickup (rather
   than trying to delete an in-flight SQS message) and confirm in the worker
   log that it was skipped (`"was revoked before pickup; skipping"`).

## Keep operational-safety comments tight

When adding a comment that explains *why* an infra script does something
non-obvious (why `WORKER_START` is `$null` in update mode, why an AMI param is
pinned to a dated SSM path instead of the latest, why a wait loop uses a
manual poll instead of `aws ec2 wait`), state the concern in one clause and
stop — don't narrate the full reasoning trail (what would happen without the
fix, what the previous behavior was, every branch you considered). Ayush
flagged a batch of these as "too many comments" mid-session; the fix was one
concise line per comment, not a paragraph. Sweep every comment you personally
added across the whole PR's files when trimming — not just the file that
triggered the feedback.

## Verifying a CFN template-only edit (no test suite exists)

For a change that's *only* a CFN YAML/JSON template edit (comment trim, added
a parameter description, added a policy statement) with no runtime behavior
to exercise, the canonical verification is `aws cloudformation
validate-template`, not a fabricated ad-hoc script:

```bash
aws cloudformation validate-template --profile trilogy --region <region> \
  --template-body "file://<path>.yaml" --query "length(Parameters)" --output text
```

A non-error result with the expected param count is sufficient evidence for
this class of edit. Pair with `bash -n <script>.sh` for any touched shell
scripts in the same commit. State explicitly that this is template-validate +
syntax-check, not a full test suite — don't oversell it as "verified" without
qualifying what kind of check it was.

## Self-heal at boot, don't gate-and-fail at bake time

When fixing a recurring "golden AMI missing a dependency" class of bug (see
the crash-loop section above), the temptation is to add a bake-time check
that fails the rebake job loudly if the install didn't verify — but a gate
that fails just produces an alert nobody is reliably watching; the fleet
stays broken until someone happens to notice the red CI run. Ayush's explicit
call on this: **make the box self-heal at boot** (reinstall the missing
component + verify the import actually resolves before starting the worker
loop) instead of only gating-and-failing at image-bake time. A gate is
acceptable as a secondary signal, but the primary fix must be the box fixing
itself — don't let a fail-loud check stand in for actually closing the gap.

## Ad-hoc scripts that invoke pipeline code directly must replicate the worker's env hydration

When you drive the pipeline (`lesson_gen.py`, `article_to_ppt.py`, etc.) via
your own throwaway script over SSM — e.g. to republish/backfill lessons that
were generated before a fix landed, bypassing the normal SQS-consumer worker
loop — the worker's normal invocation path silently does something your
ad-hoc script does NOT: it hydrates secrets from SSM Parameter Store
(`/alpha-gen/*` — `TFY_BASE_URL`, API keys, etc.) into the process environment
*before* calling the pipeline. A bare `subprocess.run([...lesson_gen.py...])`
or direct in-process import from a script you wrote yourself starts with
whatever env SSM's `send-command` gives it (not the worker's), and the failure
surfaces deep in an unrelated-looking import chain, not as an obvious "missing
credentials" error:

```
File ".../ppt-generator/core/llm.py", line 43, in <module>
    TFY_BASE_URL = os.environ["TFY_BASE_URL"]
KeyError: 'TFY_BASE_URL'
```

Every job in a batch can "succeed" at the SSM-command level (`rc=0` from your
wrapper) while the actual publish/generate step inside failed 100% of the
time — check the per-item outcome your own script logs, not just the overall
SSM command status.

**Fix:** before invoking the pipeline from an ad-hoc script, hydrate the same
namespace the worker's bootstrap reads, e.g.:
```python
import boto3, os
ssm = boto3.client("ssm", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
for page in ssm.get_paginator("get_parameters_by_path").paginate(Path="/alpha-gen/", Recursive=True, WithDecryption=True):
    for p in page["Parameters"]:
        os.environ.setdefault(p["Name"][len("/alpha-gen/"):], p["Value"])
```
Grep the worker's own bootstrap/startup script for the exact SSM path prefix
it reads before assuming `/alpha-gen/` — confirm it matches this fleet.

**A pipeline's *deploy/publish* step can need a SECOND, separate credential
layer beyond the worker's SSM secrets** — e.g. an `upload_to_s3`/CDN-deploy
component that explicitly requires `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`
env vars (checked via `os.getenv`, not the box's IAM instance-role chain) plus
`S3_BUCKET`/`CLOUDFRONT_DOMAIN`/`CLOUDFRONT_DISTRIBUTION_ID`. The box's own
IAM role won't satisfy this — you must inject an actual access-key pair (e.g.
an app's existing content-manager IAM user creds) for that step specifically.
Grep the target component's config/settings module for `os.getenv(\"AWS_`
before assuming the instance role is enough; a `Missing required environment
variables: AWS_ACCESS_KEY_ID, ...` error from deep in the deploy step is this,
not an IAM-role gap.

See also `references/producer-creds-and-batch-rerun.md` — the worker's own
IAM role is consumer-only (no `sqs:SendMessage`), so running the batch
producer CLI directly on a fleet box needs separate producer creds injected
into the env for that one call; and re-running only a subset of a batch means
staging a filtered folder on the box, since the discover step has no
per-lesson-id filter flag.

### `S3_BUCKET`/`CLOUDFRONT_*` in the worker's SSM namespace IS the fleet-wide prod-vs-dev deploy switch

Don't treat `S3_BUCKET`/`CLOUDFRONT_DOMAIN`/`CLOUDFRONT_DISTRIBUTION_ID` under
the worker's SSM secrets path (e.g. `/alpha-gen/S3_BUCKET`) as just "the
creds one ad-hoc script needs" (previous section) — if the deployed worker's
bootstrap hydrates its deploy-step env from that same SSM path, **that
parameter is the single fleet-wide switch for which environment every future
generation job deploys to.** Whichever bucket it holds (e.g.
`alpha-learn-content-hosted-prod` vs `...-dev`) is where *every* job on the
fleet publishes, with no per-job override — a brand-new/experimental pipeline
branch generating test content will silently ship to whatever this SSM value
already says, which is easy to default to prod if nobody's checked it.

Before running any batch/bulk generation on a pipeline branch that's still in
test/validation (new format, new entry point, freshly retargeted CI/CD,
etc.), check this SSM value FIRST and confirm it matches where the user
actually wants that content to land:
```bash
aws ssm get-parameters --region <region> \
  --names /alpha-gen/S3_BUCKET /alpha-gen/CLOUDFRONT_DOMAIN /alpha-gen/CLOUDFRONT_DISTRIBUTION_ID \
  --with-decryption --query "Parameters[*].[Name,Value]" --output text
```
To retarget the whole fleet (e.g. move test-pipeline output off prod onto
dev), pull the dev bucket/CDN identifiers from a source that already has them
correctly split (e.g. the app's own `DEV_S3_BUCKET`/`DEV_CLOUDFRONT_*` env
vars) and `put-parameter --overwrite` each of the three — the worker's next
job picks it up via its normal SSM hydration, no code/deploy change needed.
If content already landed on the wrong bucket before you caught this, that's a
full-tree move (JSON manifest + every asset key under the lesson's prefix, not
just the JSON), not a parameter fix alone — treat "flip the switch" and
"migrate what already shipped to the wrong side" as two separate, both
necessary, steps.

### Moving already-published content between environments: the lesson JSON bakes in an absolute CDN host — moving files is NOT enough

A lesson-plan JSON produced by the publish/deploy step carries `base_url` and
`video_base_url` fields set to the **absolute CDN host it was published
against** (e.g. `https://<internal-host>/`), and the player reads
the media-resolution host from those JSON fields, not from the app's CDN
picker or from wherever the files physically sit
(`lessonPlan.base_url`/`lessonPlan.video_base_url` in the player library).
Confirm this by grepping the JSON itself (walk every string value looking
for the CDN hostname) before assuming otherwise.

So after moving a lesson's whole keyspace prod→dev (JSON + `visuals/<id>/`
tree), the JSON you just copied still points `base_url`/`video_base_url` at
the OLD host — the player will still resolve every video/audio URL against
the environment you just moved it OUT of, 403'ing once that environment's
copy is deleted. Symptom: `GET https://<old-host>/visuals/<id>/.../s1.mp4
403` even though the lesson JSON itself now loads fine (200) from the new
host.

**Fix: rewrite `base_url`/`video_base_url` in every moved JSON to the target
host as a mandatory third step**, after copy and after delete — read, patch
those two fields, write back:
```python
d = json.loads(fetch(key))
for f in ("base_url", "video_base_url"):
    if d.get(f): d[f] = NEW_CDN_BASE
put(key, json.dumps(d), content_type="application/json")
```
Treat an environment move as **four** necessary steps, not two: (1) copy the
full keyspace, (2) rewrite the baked CDN host in each moved JSON, (3) delete
from the source, (4) invalidate the destination CDN's cache for the rewritten
keys. Skipping (2) leaves the migration looking complete (files present on
both sides, source cleaned) while every lesson is still broken for playback.

**Step (4) is easy to skip because the symptom looks identical to step (2)
not having run.** After rewriting the JSON in the bucket and confirming the
new bytes are correct via a direct bucket read, the CDN can still serve the
OLD (pre-rewrite) JSON — `curl` the CDN URL and it comes back with the stale
`base_url` even with a cache-busting query string appended, because
CloudFront ignores query strings by default and serves whatever it already
cached before your rewrite landed. Diagnose by checking response headers,
not just the body: `x-cache: Hit from cloudfront` + a large `age` value
confirms a stale cached hit, distinct from a genuine data problem. Fix: fire
a CloudFront invalidation for the rewritten keys on the **destination**
distribution and wait for it to reach `Completed` before re-testing:
```bash
aws cloudfront create-invalidation --distribution-id <dest-dist-id> \
  --paths "/lesson-plans/*" --region <region>
# poll: aws cloudfront get-invalidation --distribution-id <id> --id <inv-id> --query Invalidation.Status
```
**A narrow invalidation path pattern built around a literal special character
in the key (e.g. trying to match one lesson id containing `+`) can silently
fail to match the actual cached entry.** Don't spend cycles crafting an
exact-match invalidation path per lesson id — invalidate the whole relevant
prefix (`/lesson-plans/*`, plus `/visuals/*` if media also moved) in one
call; a broad wildcard is cheaper and more reliable than N precise ones.
Verify success by re-fetching the exact URL the player hits and confirming
both the JSON body's rewritten field AND the `age`/`x-cache` response
headers show a fresh miss/short age — a 200 response alone isn't proof the
CDN stopped serving the stale cached copy.

### `aws s3 sync`/`cp` on a single-key path containing `+` can silently no-op — verify per-key, don't trust the script's own "OK" line

When moving objects **per-lesson** via `aws s3 sync <prod-prefix> <dev-prefix>`
scoped to a single JSON key (as opposed to a whole prefix tree), a lesson id
containing a literal `+` (a real, common id shape here, e.g.
`TEKS.MATH.CONTENT.3.2.B+1_script`) can cause the sync/cp to silently fail to
actually land the object while the wrapping script still logs "OK" and moves
on to delete the source. The failure is invisible at the orchestration layer
— it looks like every lesson succeeded until a much later live-load reveals a
specific lesson's JSON is missing on the destination.

**Verify each moved key with a `head-object` (or equivalent existence + size
check) against the destination immediately after the copy, before deleting
the source key** — do not rely on the copy command's exit code or your own
script's "OK" print alone for anything with special characters in the key.
If S3 versioning is enabled on the source bucket, a lost object during a
migration is recoverable from the prior (non-latest) object version even
after a delete-marker was written — check `list-object-versions` before
assuming data is gone.

**Ordering bug: never set those explicit deploy credentials on the whole
process env before other AWS SDK calls (e.g. the SSM secret hydration above)
run in the same script.** `os.environ[...] = key` (or passing `env=` into a
`Popen`/`subprocess.run` that also covers earlier boto3 calls in the same
process) makes EVERY subsequent AWS SDK call in that process — including an
unrelated `ssm.get_parameters_by_path` — authenticate as the deploy IAM user
instead of the box's instance role, and fails with an opaque
`AccessDeniedException ... is not authorized to perform: ssm:GetParametersByPath`
that looks like a permissions gap but is actually a credential-scoping bug.\n
Fix: do the SSM/other role-scoped hydration FIRST (while the process still
inherits the box's role), then build a **narrow env dict override only for the
deploy subprocess** (`dict(os.environ, AWS_ACCESS_KEY_ID=..., AWS_SECRET_ACCESS_KEY=...)`
passed via `subprocess.run(..., env=narrow_env)`), never assign the deploy
creds onto the parent process's own `os.environ`.

## Counting batch job outcomes — scope strictly to the batch's own naming convention

An S3 job-folder prefix (e.g. `script-generation-jobs/`) accumulates folders
from EVERY run ever made against that queue — ad-hoc manual test jobs, earlier
e2e-verification jobs, and multiple distinct batch-CLI runs — all mixed
together with no separation besides the lesson-id/job-id naming pattern
itself. When a user asks "how many did the batch generate/publish", do NOT
grep the prefix with an ad hoc pattern you invent on the spot (e.g. filtering
to `TEKS.*` only, or by grade number alone) — that undercounts or overcounts
depending on what else happens to match. Ground the count in the **exact
naming convention the batch CLI's own discover step uses** (e.g. every folder
it creates carries a fixed suffix like `_script` marking "came from this
Drive-folder batch run", distinct from a bare lesson id used by manual/e2e
jobs). Confirm that convention by reading the batch tool's discover/submit
code (or its logged "discovered N" / "enqueued" output) before writing the S3
query, not by pattern-matching on what "looks like" the right jobs. Getting
this wrong produces different totals on successive turns (e.g. 56 → 171 → 206
for the same batch) purely from grep-pattern drift, not from anything actually
changing — a correction the user will have to make for you if you don't get
it right the first time. When the user says a folder/prefix should hold ONLY
one kind of job, take that as the filter, not a suggestion to combine with
your own guess.

## A script "parses" ≠ a script "resolves" — validate against the ACTUAL downstream gate, not a proxy

A content pipeline can have **more than one validator in the chain**, and
they check different things — e.g. a format parser (`script_to_json.parse()`)
that only checks structural syntax (markers present, blocks well-formed) vs.
an `ingest` stage's `anchor()` step that additionally requires each narration
marker to land on a phrase that is **unique** within its slide's narration
(so the timing engine can resolve "which occurrence of this phrase does the
marker mean"). A script can pass the first and still fail the second with
`missing trigger_phrase, trigger_word, or appear_at` at the real pipeline
stage — because "parses" only proved the marker exists somewhere in the
narration, not that it resolves unambiguously.

**Symptom of validating against the wrong gate:** a repair pass reports
"all N scripts fixed and pass validation" (validated with the *format*
parser), the batch is re-queued, and it fails again with the exact same
downstream error — because the repair never touched the actual failure
condition (duplicate phrases), only reinforced the wrong success signal.

**Fix:** before repairing/validating any content against a multi-stage
pipeline, confirm which stage/module produced the failure log line, read
THAT module's specific check (not the nearest parser you can find), and
write a standalone offline checker against that exact semantic (e.g. "for
each element id, extract the phrase immediately following its marker in the
slide's cleaned narration; flag if empty or count-in-narration != 1"). Sanity
the checker against a KNOWN-failing real example first — confirm it actually
flags the known bug — before trusting it to validate a repair or clear a
batch of files. Re-running the same wrong-gate check after a fix and getting
a green result is not evidence; only a check that reproduces the real
failure mode first, then reports clean after the fix, is.

## Fanning out parallel subagents to repair content files: pin the output convention up front

When repairing many content files against a validator (sharded across
several `delegate_task` subagents for speed), each shard will independently
invent its own working/output directory if you don't specify one — observed:
5 parallel shards produced fixed files in five different unrelated local
paths (`~/di-repair/fixed/`, `/tmp/di-fix/scripts/`, `~/di-repair/scripts/
shard4/`, etc.), and only one shard thought to upload its results back to
the actual source of truth (Drive) — the other four left fixed files sitting
locally, silently blocking the "re-run generation" step until reconciled by
hand (locating each shard's output dir, then bulk-uploading all of them).

**Fix:** in the fan-out brief, state explicitly either (a) the exact shared
local path convention every shard must write to (e.g. `/tmp/fixed/<lesson_id>.md`),
or — preferably, when the files' source of truth is external (Drive, a repo,
a bucket) — (b) that each shard must write its result directly back to the
source of truth itself (upload to the same Drive file id / commit to the
branch) as its LAST step, not just leave a repaired copy in its own
scratch space. Verify after the fan-out completes that the source of truth
actually reflects every shard's fix (spot-check a file from each shard's
range at the real source), not just that each shard *reported* success.

## Blanket "don't ask again" authorization covers the rest of that bounded task

When the user gives a standing instruction covering a whole remaining
scope — e.g. "I want all non-script-issue lessons generated, published, and
registered; if something fails due to the script that's fine, keep going; no
need to ask again" — that authorization is a one-time grant for the REST of
that bounded operation (finishing the batch, republishing the backlog,
completing the multi-step remediation chain it was given for). Do not
resurface incremental sub-decisions inside that same scope for renewed
approval (e.g. re-asking before force-publishing more, before republishing
another leftover subset, before re-driving a retry). Keep executing until the
stated end-state is reached (all clean items generated + published +
registered) or a genuinely new class of decision arises outside what was
authorized (a different repo, a destructive/irreversible action not implied
by the original ask, a new scope entirely). Reserve `clarify` for that new-class
case, not for "should I continue doing the thing I was just told to keep
doing."

## Pulling a Drive folder tree via a service account needs the shared-drive flags

A Drive service account calling `files.list`/`files.get_media` against a
folder that lives in a **Shared Drive** (not the SA's own My Drive) returns
an empty/partial result — `0 subfolders found` — unless you pass
`supportsAllDrives=True` **and** `includeItemsFromAllDrives=True` on every
`list()` call (and `supportsAllDrives=True` on `get_media()`/downloads too).
Omitting either flag looks like a permissions problem (and IS worth
double-checking IAM/sharing on the SA first) but if the SA genuinely has
access, this is almost always the real cause — confirmed by re-running the
identical query with both flags added and getting the full child count.

## SSM PowerShell script quoting — stop fighting inline escaping, use a file

Multi-layer quoting (local shell → `aws ssm send-command --parameters` JSON →
remote PowerShell) reliably breaks on anything beyond a one-liner — nested
quotes, `$`, backticks, and here-strings all get mangled across the layers,
and you'll burn several turns re-escaping before noticing the real fix is
structural, not syntactic. Once a probe/fix script exceeds ~2 lines:

1. `write_file` the script locally (`.ps1` or `.py`) — plain, no shell escaping.
2. Get it onto the box via a payload the SSM JSON parameter can carry safely:
   base64-encode the file's bytes, pass the base64 string as a single command
   parameter, and have the remote-side one-liner
   (`[IO.File]::WriteAllBytes($path, [Convert]::FromBase64String($b64))` or
   the `python -c "..."` equivalent) decode-and-write it, then execute the
   written file in a second `send-command` call.
3. Never try to inline a multi-line script body as a `send-command`
   `commands` array element with embedded quotes — that's the failure mode
   that costs the most retries for the least payoff.

This applies to any SSM-driven Windows-box diagnostic/fix in this class of
audit, not just one specific probe.

## Pitfalls

- CFN param defaults and UserData logic being "already correct" on `main`
  does **not** mean the deployed fleet reflects it — always verify the live
  box directly (step 5). This is the single most common false-negative in
  this class of audit.
- **Ad-hoc verification of an AWS CLI flag/subcommand change must include
  actually invoking the real `aws` binary's arg parser, not just simulating
  the intended logic.** A stubbed-command test that only checks "does my
  poll loop's branching logic work" (feeding it fake states) can pass clean
  while the underlying `aws ec2 wait ... --max-attempts N --delay N` call is
  still rejected outright by the real CLI — the bug was never in the logic,
  it was in an unsupported flag. When verifying a fix to an `aws <service>
  <verb>` invocation, run `aws <service> <verb> help` (or the real command
  against a harmless/dry-run target) to confirm the flags exist, don't only
  unit-test the surrounding shell logic.
- The fleet's `GoldenAmiId` stack param can be newer than what any *actually
  running* instance launched from — cross-check the instance's real `ImageId`
  (step 4), don't assume it matches the stack's current param.
- A `MaxFleetSize` > 0 does not guarantee running fleet instances exist — a
  scaler can legitimately keep 0 clones up if the baseline alone is covering
  load. Always enumerate real instances before reasoning about "the fleet".
- Distinguish two different fixes and present both: (a) a one-time repoint
  of the currently-stale box (fast, e.g. re-run the bootstrap script's
  `--update` path via SSM) vs. (b) fixing a genuinely hollow/incomplete CI/CD
  deploy workflow so future merges don't drift again (the durable fix).
  Don't let (a) stand in for (b), or vice versa — ask which scope the user
  wants before doing shared-infra changes to either.
- If a `clarify` about a scope decision (e.g. "should the repointed worker
  come back up enabled or stay paused?") gets no selection because the user
  moved the conversation to a different part of the same request, don't
  re-ask the same question later. Proceed with whatever part of the original
  ask is unambiguous and within your own scope to finish, and say plainly
  what's done vs. still pending that undecided call — don't silently drop it
  either.
