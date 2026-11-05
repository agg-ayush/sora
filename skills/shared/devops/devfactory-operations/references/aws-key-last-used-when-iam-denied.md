# Is an IAM key still in use when introspection is denied?

`iam:GetAccessKeyLastUsed` can return `AccessDenied` even for an assumed
"Admin"-named role — a permissions-boundary/explicit-deny on that specific
introspection action, **not** a login/SAML problem. Confirm with `aws sts
caller-identity` (shows the correct assumed-role ARN) that auth is fine, then
treat the API as unavailable and use an indirect method.

`cloudtrail lookup-events --lookup-attributes AttributeKey=AccessKeyId,...`
is also unreliable for this question: it only surfaces management-plane events
within the trail's retention window, so an **empty result does not mean
unused** — S3/ECR data-plane calls are often not recorded there at all. Don't
report "not used in 90 days" off an empty CloudTrail lookup alone.

## Reliable alternative: cross-reference GitHub secrets + workflow runs

When the credential backs a GitHub Actions deploy workflow:

1. Confirm the GitHub secret is actually this IAM user's key by comparing
   creation/update timestamps — a secret set within ~1 minute of the IAM
   access key's `CreateDate` is almost certainly that same key:
   ```bash
   gh secret list --repo <org>/<repo> | grep -iE 'AWS_ACCESS|AWS_SECRET'
   aws iam list-access-keys --user-name <user> \
     --query "AccessKeyMetadata[].{Id:AccessKeyId,Created:CreateDate}"
   ```
2. Find which workflows reference that secret, and how recently they ran
   successfully:
   ```bash
   grep -rn 'secrets.AWS_ACCESS_KEY_ID' .github/workflows/
   gh run list --repo <org>/<repo> --workflow <workflow>.yml --limit 5 \
     --json conclusion,createdAt,headSha
   ```
   A recent `success` run on a workflow that calls `configure-aws-credentials`
   with that secret is direct, positive proof the key is live — a stronger
   signal than a denied or empty IAM-side query, with no extra IAM permission
   needed.

This generalizes beyond AWS: whenever a credential's own audit log is
inaccessible, look for the consumer's own external record of using it (CI run
history, deploy logs, app logs) rather than concluding "can't tell."
