# Teammate access handoff (onboarding a dev onto ti-hiring infra)

## Procedure
1. Answer the "what can we give vs. what needs someone else" split FIRST, in one table, from what you already know. Do not spend many tool calls probing live permissions before replying; the user wants the split fast, and details can be verified afterwards.
2. Split by who can grant it:
   - **Us (Ayush):** Vercel API token + team/project IDs, Postgres connection string, Drive folder share, application secrets (LLM gateway, Recall), Recall workspace invite.
   - **infra lead (admin):** AWS account/role, GitHub org/repo access, GCP project IAM. Ayush is GCP *Editor*, which lacks `resourcemanager.projects.setIamPolicy`; adding members needs Project IAM Admin or Owner.
3. Put secrets in ONE Google Doc owned by Ayush, shared reader-only with the teammate (gog). The company shares secrets via gdoc; do not push back with guardrail lectures or alternative secret stores. Pull values from SSM with `aws --profile trilogy ssm get-parameter --region ap-south-1 --with-decryption`, append with `gog docs insert <docId> --file -`, then read back and confirm every exact value landed and the permission list is still only owner + teammate. Never echo secret values into chat output.
4. GCP IAM does NOT grant Google Drive access: share the artifact root folder (`DRIVE_ROOT_FOLDER_ID`, folder `add-assessment-artifacts`) separately. Give the user the folder link if they want to share it themselves.
5. List what is still missing explicitly so nothing is dropped: network path to DB, Drive share, app secrets.

## Secret sources (SSM, ap-south-1, prefix /ti/orchestrator/)
LLM_SANDBOX_CREDENTIAL, ANTHROPIC_BASE_URL, RECALL_API_KEY, RECALL_WEBHOOK_SECRET, RECALL_WEBHOOK_TOKEN, plus the Vercel token and DB URL used by the orchestrator. The Vercel token is a Vercel API/CLI access token (not an MCP OAuth login); it also works as a bearer token for tools that accept one.

## Postgres reachability
- RDS is private; its SG allows 5432 only from the orchestrator ECS task SG. A connection string alone is useless from a laptop, and AWS account access alone does not open a path either. Say this plainly instead of conflating "AWS CLI fetched the secret" with "how he connects".
- Working route: SSM Session Manager port-forward through the existing devbox (same VPC, SSM agent online), `AWS-StartPortForwardingSessionToRemoteHost` to the RDS host on 5432 -> localhost:15432. Needs one RDS SG ingress rule from the devbox's private IP as `/32`, not the devbox's SG (that SG is shared with other instances), and the teammate needs `ssm:StartSession`. Reuse the devbox; do not provision a bastion.
- Never open RDS to 0.0.0.0/0. The SG change touches prod: get explicit approval for that exact rule before applying, then test the tunnel.
