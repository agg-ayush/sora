---
name: aws-iam-credential-rotation
description: "Audit which IAM identity a service/workflow actually uses, replace an over-privileged or personal-named IAM user with a purpose-scoped one, verify by real probe calls, and safely delete the old identity. Use whenever asked to check/rotate/remove IAM users or credentials backing a running service, container, or CI workflow."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [AWS, IAM, credentials, security, S3, CI, infra]
    related_skills: [github-auth]
---

# AWS IAM Credential Audit & Rotation

Class of task: a service, container, or CI workflow is using an IAM identity that
needs to be checked, replaced, or removed (over-privileged personal-named user,
shared/leaked key, decommissioned employee's user, consolidating scope). This
covers the full audit → replace → verify → cleanup lifecycle safely.

## 1. Audit before touching anything

Never assume the identity you were told about is the only consumer. Enumerate
ALL places a credential could be sourced from before rotating it:

- Container/process env (`docker inspect`, `docker exec env`, systemd unit, `.env` files on the host)
- CI secrets (`gh secret list`) — and check each workflow's `env:` block for which secret names it actually references; don't assume every workflow shares the same secret pair
- Other hosts / scripts that might reference the same key
- `grep` the whole repo for the old username/ARN pattern before declaring cleanup done

**Do not rotate a credential that isn't actually broken.** In one session, a
service's container was on an over-privileged personal-named user (fixed), but
the CI workflows were already on a separate, correctly-scoped, purpose-built CI
user — rotating those too would have been unnecessary blast radius. Confirm
each consumer's actual identity before acting on it.

Before creating a *new* purpose-scoped IAM user for a gap, search existing users
and customer-managed policies by naming convention first — a fit-for-purpose
identity may already exist:

```bash
aws iam list-users --query "Users[?contains(UserName,'<project-prefix>')].UserName"
aws iam list-policies --scope Local --query "Policies[?contains(PolicyName,'<Concern>')].PolicyName"
```

## 2. Scope the replacement identity

- Prefer **per-concern purpose-scoped users** over folding new perms into one
  broad identity, even if consolidating looks convenient. Separate identities
  = separate CloudTrail attribution = real traceability. Don't recreate the
  over-broad-permissions problem you're fixing.
- Derive exact required actions from what the code/scripts actually call, not
  from guessing:
  ```bash
  grep -rhoE "aws (ec2|ssm|sqs|s3|ecr|cloudformation|autoscaling) [a-z-]+" <script_dir>/ | sort -u
  ```
- S3 object-level actions (`PutObject`/`GetObject`/`DeleteObject`) need the
  bucket ARN **with `/*`** appended as a separate `Resource` entry — a
  bucket-only ARN in the policy only covers bucket-level ops (`ListBucket`,
  config), not object writes. This is a common "policy looks right but PUT
  still fails" cause.

## 3. Verify with real calls, not policy reading

IAM policy JSON and even `iam simulate-principal-policy` can both look correct
while the real call still fails (SCP, bucket policy, propagation lag). Always
verify the new key end-to-end before cutting anything over:

```bash
# Real round-trip probe per bucket/resource, not just a simulator check
echo "probe" > /tmp/probe.txt
AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... aws s3 cp /tmp/probe.txt s3://<bucket>/probe.txt
AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... aws s3 rm s3://<bucket>/probe.txt
```

If a freshly-attached inline/managed policy fails a probe immediately after
attaching, retry after ~10-30s before concluding the policy is wrong — IAM
propagation lag is a real and common false negative here.

**Stale exported `AWS_*` env vars silently override profile creds.** If any
earlier command in the same shell exported `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` / `AWS_SECURITY_TOKEN` /
`AWS_PROFILE`, those take precedence over `~/.aws/credentials` for every
subsequent `aws` call — even right after a fresh saml2aws login. Symptom:
`aws sts get-caller-identity` flips between identities across calls in the
same investigation (e.g. back to a personal-named IAM user instead of the
assumed admin role), producing spurious `AccessDenied` on actions the correct
role actually has. Before trusting or diagnosing an `AccessDenied`:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN AWS_PROFILE
aws sts get-caller-identity --profile devflows --query Arn --output text
```

and pass `--profile devflows` explicitly on the calls that matter rather than
relying on ambient shell state.

Never hand-type a truncated/masked access-key ID from console output — pull it
programmatically (`aws iam list-access-keys --query ...`) to avoid probing
with a mistyped key and misdiagnosing a permissions failure that's actually a
typo.

## 4. Cut over the consumer

**Docker gotcha:** `docker restart` reuses the env baked into the container at
`docker run` time — it does **not** re-read an updated `--env-file` from disk.
Updating `.env` on the host and then `docker restart`-ing silently leaves the
old credential live. You must recreate the container:

```bash
docker rm -f <container>
docker run --env-file /path/.env <same flags as original deploy> <image>
# then verify the NEW key is actually live inside the container:
docker exec <container> env | grep AWS_ACCESS_KEY_ID
```

Back up the file you're editing (`.env`, workflow YAML, etc.) before overwriting it.

## 5. Delete the old identity safely

`iam delete-user` fails with `DeleteConflict` unless every attachment is
removed first. Full teardown order:

```bash
delete_user () {
  local U=$1
  for K in $(aws iam list-access-keys --user-name "$U" --query "AccessKeyMetadata[].AccessKeyId" --output text); do
    aws iam delete-access-key --user-name "$U" --access-key-id "$K"
  done
  for P in $(aws iam list-attached-user-policies --user-name "$U" --query "AttachedPolicies[].PolicyArn" --output text); do
    aws iam detach-user-policy --user-name "$U" --policy-arn "$P"
  done
  for N in $(aws iam list-user-policies --user-name "$U" --query "PolicyNames[]" --output text); do
    aws iam delete-user-policy --user-name "$U" --policy-name "$N"
  done
  for G in $(aws iam list-groups-for-user --user-name "$U" --query "Groups[].GroupName" --output text); do
    aws iam remove-user-from-group --user-name "$U" --group-name "$G"
  done
  aws iam delete-login-profile --user-name "$U" 2>/dev/null || true
  aws iam delete-user --user-name "$U"
}
```

## Pitfalls

- **Self-lockout mid-rotation**: if you delete/replace the admin key you're
  currently using to perform the rotation before finishing, the session dies
  mid-cleanup. Check for an alternate local identity (e.g. an assumed IAM role
  on the operator's machine) before treating this as a hard blocker — it's
  often recoverable without asking the user for fresh creds.
- Confirm zero repo references to the old identity name/ARN before declaring
  cleanup complete (`search_files`/`grep` across the whole repo, not just the
  directory you were pointed at).
- Leftover `.bak` files containing the old dead credential (e.g. a pre-edit
  `.env` backup) are low-risk once the key is deleted server-side, but flag
  them to the user rather than silently leaving stale secrets on disk.
- This is IAM-shared-infra work: confirm scope with the user before deleting
  or rotating anything, and before creating new users/policies when multiple
  reasonable scoping strategies exist (e.g. "fold into existing user" vs.
  "create N new purpose-scoped users") — this is exactly the kind of
  hard-to-reverse call that warrants a clarify, not a default guess.
