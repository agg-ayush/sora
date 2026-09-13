---
name: devpod-remote-workspace
description: "Set up/operate a persistent AWS DevPod remote dev box."
version: 0.1.0
author: Ayush Aggarwal (agg-ayush), Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [devpod, aws, remote-dev, devcontainer, ec2]
---

# DevPod Remote Workspace (AWS)

Governs setting up and operating DevPod-backed remote development environments on AWS. Covers
provider setup, devcontainer authoring, workspace lifecycle, and — critically — Ayush's usage
model for it, which differs from DevPod's own marketing pitch.

## When to use

- "set up devpod", "spin up a devbox", "give me a remote dev environment on AWS"
- Managing an existing DevPod AWS workspace: start/stop/rebuild/delete/resize

## Ayush's usage model: persistent server, not ephemeral build container

He treats a DevPod AWS box as a **persistent remote workstation he lives in** ("I'll use it like
an external server I connect to and work") — not DevPod's default disposable-ephemeral-container
pitch. Practical implications:

- Default to `INACTIVITY_TIMEOUT=0` and no auto-stop.
- Anything not baked into `devcontainer.json` (CLIs, dotfiles, agent tools like hermes/claude
  code/codex) is lost on container rebuild. If he wants a tool to survive rebuilds, add it as a
  devcontainer feature or `postCreateCommand` — don't just install it ad hoc inside a live SSH
  session unless he explicitly says "just this once."
- The underlying EC2 instance is a normal instance in his account regardless of DevPod's
  involvement — SSH, IAM roles, stopping/terminating via plain `aws` CLI all work independently of
  the devpod CLI. If he ever asks "why not just plain EC2", the honest answer: DevPod's value for
  his use case is the reproducible devcontainer.json spec + IDE remote-connect wiring, not the
  disposability story (which is thin value for a pet server). Surface that tradeoff, don't oversell
  DevPod.

## Setup steps

1. **Fresh AWS creds first.** `devpod provider add/set-options aws` calls `DescribeInstances`
   under the hood and fails with a cryptic `RequestExpired` (not an obvious "credentials expired"
   message) on a stale saml2aws session. Run `/Users/ayush/.hermes/scripts/aws-creds-refresh.sh`
   (see `aws-devfactory-operations` skill) before touching the provider, and again if any devpod
   command throws `RequestExpired`.
2. `brew install devpod` (cask — installs `devpod-cli` + DevPod.app to `/Applications`).
3. `devpod provider add aws`
4. `devpod provider set-options aws -o AWS_INSTANCE_TYPE=... -o AWS_DISK_SIZE=... -o AWS_REGION=... -o AWS_AVAILABILITY_ZONE=... -o AWS_VPC_ID=... -o INACTIVITY_TIMEOUT=0`
   - `AWS_VPC_ID` must be set explicitly — the provider does not auto-pick a subnet. Find one with
     free IPs first: `aws ec2 describe-subnets --query 'Subnets[].[SubnetId,VpcId,AvailableIpAddressCount]'`.
5. Author `devcontainer.json` in a plain folder (that folder *is* the workspace source — see
   `templates/devcontainer-node-python-docker.json` for a working node+python+docker-in-docker+git+gh+aws-cli base).
6. `devpod up <folder> --provider aws --ide none` (or `--ide vscode`/`cursor` to open the IDE
   immediately).
7. **Verify before declaring done**: `devpod ssh <workspace> --command '...'` and actually check
   uname/nproc/free/tool versions. Don't trust a clean `devpod up` exit alone — see pitfall below.

## Pitfalls

- **Never size a billable instance without explicit sign-off on the exact type/cost.** Directional
  input like "16 gigs" or "use the bigger one" is NOT approval for a specific instance type —
  present 2-3 named options with $/hr and let him pick. This is one of the few question classes
  that survives a "stop asking me questions" instruction, because it's a new billable
  shared-infra resource, not a design/config choice.
- **`devpod up` can exceed a short foreground timeout while the workspace finishes building
  successfully in the background.** A CLI timeout on `up` is not a failure signal — check
  `devpod list` and `aws ec2 describe-instances` (filter on running/pending + recent LaunchTime)
  before concluding it failed or re-running it.
- **`INACTIVITY_TIMEOUT=0` does not reliably stop a brand-new workspace from auto-stopping** —
  a box has been observed stopping itself right after `up` finishes provisioning, before any
  SSH/IDE session attaches. If a fresh workspace shows `stopped`, just `devpod up` again
  (idempotent) rather than treating it as a provisioning failure.
- **Workspace name = source folder's basename**, not the `devcontainer.json` "name" field and not
  whatever name you told the agent to use. To get a specific workspace name, name the folder that
  before running `devpod up`.
- **The AWS provider's security group is shared across every DevPod instance in the account.**
  Deleting one workspace does not remove it — verify via
  `aws ec2 describe-instances --filters Name=instance.group-id,Values=<sg-id>` that other
  instances still reference it before treating it as orphaned cleanup.
- **The devpod agent INSIDE the container can die while the EC2 instance and even `docker ps`
  still show something running** — `devpod ssh`/`up`/`up --recreate` all hang forever on
  "Waiting for devpod agent to come up" and never time out on their own. This is a different
  failure mode than the auto-stop above: the box is reachable at the VM level but the agent
  handshake never completes. `devpod stop` followed by `devpod up` sounds like the obvious fix
  but can make it worse — `stop` kills the container outright (`docker ps` goes empty), and the
  subsequent `up` then has to recreate the container from scratch, which is itself slow (10+ min
  observed) and NOT guaranteed to bring the agent back — it can hang at the exact same step again.
  **Under real time pressure, do not sink more than ~2-3 min into iterating on `devpod
  up`/`stop`/`--recreate` before switching tracks**: hand the devpod recovery off to a background
  subagent (it may eventually succeed) and immediately proceed on the *actual* task via a fallback
  that doesn't depend on the devpod agent at all — either run the work locally, or, if the
  container is still alive (`docker ps` shows it), skip the devpod CLI entirely and drive the
  container directly via `aws ssm send-command` / `docker exec` into it. The SSM/docker-exec path
  works even when the devpod agent handshake never resolves, because it talks to the container
  runtime directly and doesn't need the agent at all.
- **A container reached via `docker exec`/SSM instead of `devpod ssh` is usually running as
  root**, unlike the devpod-managed container which runs as the devcontainer's configured non-root
  user (e.g. `vscode`). Tools that refuse to run as root (Claude Code's
  `--dangerously-skip-permissions` is a known one — see `claude-code` skill pitfall 17) will fail
  in a way that looks unrelated to the recovery path. Create/switch to a non-root user in the
  fallback container before running anything that has this restriction.

## Related

- `aws-devfactory-operations` skill — AWS credential refresh (saml2aws), required before any
  devpod AWS provider operation.
- `templates/devcontainer-node-python-docker.json` — working devcontainer base (node 22, python
  3.12, docker-in-docker, git, gh, aws-cli).
- `agent-orchestration-patterns` skill, `references/parallel-batch-execution.md` — running many
  independent jobs (e.g. candidate evaluations) split across local + remote workers under time
  pressure, including what to do when the remote worker (this devpod) is flaky.
