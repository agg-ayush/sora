# Locating which AWS account hosts a deployed web app

Use when the user asks "which AWS account is hosting X" or before planning a
deployment that might reuse an existing app's infrastructure.

## Procedure (cheapest signal first)

1. **Refresh creds and confirm identity**: `~/.hermes/scripts/aws-creds-refresh.sh`
   then `aws sts get-caller-identity --query Account --output text`. The
   answer can only be "in this account / not in this account" for accounts
   the session can reach.
2. **DNS**: `dig +short CNAME <host>` and `dig +short ANY <host>`. A
   `*.cloudfront.net` target plus `awsdns` NS means AWS-hosted (Amplify or
   CloudFront) but does not name the account.
3. **Amplify across all regions**, not just us-east-1:
   `for r in $(aws ec2 describe-regions --query 'Regions[].RegionName' --output text); do aws amplify list-apps --region $r --query 'apps[].name' --output text; done`.
   App names often differ from the product name, so match by custom domain:
   `aws amplify list-domain-associations --app-id <id> --query 'domainAssociations[].domainName'`
   per app. `get-app ... customDomains` is usually empty; domain associations
   are the reliable field.
4. **Route53**: `aws route53 list-hosted-zones`, look for the host's zone.
   No zone and no Amplify domain association means not hosted in this account.
5. **The repo itself**: grep the product repo for `arn:aws:[a-z0-9-]*:[a-z0-9-]*:[0-9]{12}`
   (experiments, IaC, SDK calls). Account IDs there are strong leads.
6. **Name the leads**: map account IDs to names via the org role mapping at
   `~/.aws/onelogin-roles-mapping.json` (`roles[].account_id / account_name /
   role_type`), and search it by keyword (e.g. `legal`) for sibling accounts
   of the same function.

## Reporting

- State what was verified ("not in account N: no Amplify app, domain or zone")
  separately from what is inferred ("likely account M, from ARNs in the
  repo"). Never present an inferred account as confirmed.
- If the leads are accounts the SAML login cannot assume, say so and name the
  person who deployed it as the one-message confirmation.
- Tie the answer to the decision it serves: hosting in an account we cannot
  access means reuse implies migrating into someone else's stack, which this
  user rejects when that is more hassle than provisioning fresh in an account
  we control.
