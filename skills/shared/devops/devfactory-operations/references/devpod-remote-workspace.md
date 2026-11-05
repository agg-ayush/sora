# DevPod remote workspaces (AWS)

Governs setting up and operating DevPod-backed remote development environments
on AWS. Covers provider setup, devcontainer authoring, workspace lifecycle,
and Ayush's usage model, which differs from DevPod's own pitch.

## Usage model: persistent server, not ephemeral build container

Ayush treats a DevPod AWS box as a **persistent remote workstation he lives
in** — not DevPod's default disposable-ephemeral-container pitch. Practical
implications:

- Default to `INACTIVITY_TIMEOUT=0` and no auto-stop.
- Anything not baked into `devcontainer.json` (CLIs, dotfiles, agent tools) is
  lost on container rebuild. If a tool should survive rebuilds, add it as a
  devcontainer feature or `postCreateCommand` — don't just install it ad hoc
  inside a live SSH session unless he explicitly says "just this once."
- The underlying EC2 instance is a normal instance in his account regardless
  of DevPod's involvement — SSH, IAM roles, stop/terminate via plain `aws` CLI
  all work independently. If asked "why not just plain EC2": DevPod's value
  here is the reproducible devcontainer.json spec + IDE remote-connect wiring,
  not disposability (thin value for a pet server). Surface that tradeoff,
  don't oversell DevPod.

## Setup steps

1. **Fresh AWS creds first.** `devpod provider add/set-options aws` calls
   `DescribeInstances` and fails with a cryptic `RequestExpired` on a stale
   saml2aws session. Run the aws-creds-refresh script (see
   `aws-saml2aws-refresh.md`) before touching the provider, and again if any
   devpod command throws `RequestExpired`.
2. `brew install devpod` (cask — installs `devpod-cli` + DevPod.app).
3. `devpod provider add aws`
4. `devpod provider set-options aws -o AWS_INSTANCE_TYPE=... -o
   AWS_DISK_SIZE=... -o AWS_REGION=... -o AWS_AVAILABILITY_ZONE=... -o
   AWS_VPC_ID=... -o INACTIVITY_TIMEOUT=0`
   - `AWS_VPC_ID` must be set explicitly — the provider does not auto-pick a
     subnet. Find one with free IPs first: `aws ec2 describe-subnets --query
     'Subnets[].[SubnetId,VpcId,AvailableIpAddressCount]'`.
5. Author `devcontainer.json` in a plain folder (that folder *is* the
   workspace source) — use the devcontainer template in the skill's
   `templates/` dir as the base.
6. `devpod up <folder> --provider aws --ide none` (or `--ide vscode`/`cursor`
   to open the IDE immediately).
7. **Verify before declaring done**: `devpod ssh <workspace> --command '...'
   and actually check uname/nproc/free/tool versions. Don't trust a clean
   `devpod up` exit alone.

## Pitfalls

- **Never size a billable instance without explicit sign-off on the exact
  type/cost.** Directional input like "16 gigs" or "use the bigger one" is NOT
  approval for a specific instance type — present 2-3 named options with $/hr
  and let him pick. This survives a "stop asking me questions" instruction:
  it's a new billable shared-infra resource, not a config choice.
- **`devpod up` can exceed a short foreground timeout while the workspace
  finishes building successfully in the background.** A CLI timeout on `up` is
  not a failure signal — check `devpod list` and `aws ec2 describe-instances`
  (running/pending + recent LaunchTime) before concluding failure or
  re-running.
- **`INACTIVITY_TIMEOUT=0` does not reliably stop a brand-new workspace from
  auto-stopping** — a box can stop itself right after `up` finishes, before
  any session attaches. If a fresh workspace shows `stopped`, just `devpod up`
  again (idempotent) rather than treating it as a provisioning failure.
- **Workspace name = source folder's basename**, not the devcontainer.json
  "name" field. Name the folder before running `devpod up`.
- **The AWS provider's security group is shared across every DevPod instance
  in the account.** Deleting one workspace does not remove it — verify other
  instances still reference it before treating it as orphaned cleanup.
- **The devpod agent inside the container can die while the EC2 instance and
  even `docker ps` still show something running** — `devpod ssh`/`up` hang on
  "Waiting for devpod agent to come up". `devpod stop` + `up` can make it
  worse. **Under time pressure, don't sink more than ~2-3 min into devpod
  commands before switching tracks**: hand devpod recovery to a background
  subagent and proceed on the actual task via a fallback that doesn't need
  the agent — run locally, or if the container is alive, drive it directly via
  `aws ssm send-command` / `docker exec`.
- **A container reached via `docker exec`/SSM instead of `devpod ssh` is
  usually running as root**, unlike the devpod-managed container. Tools that
  refuse to run as root will fail in a way that looks unrelated to the
  recovery path — create/switch to a non-root user first.

## Decoupling a devbox from DevPod (direct EC2 management)

When stopping DevPod lifecycle management and driving the box as plain EC2:
`INACTIVITY_TIMEOUT=0` and killing the in-container agent are NOT enough —
auto-stop is enforced by a **systemd service on the EC2 host itself**:

```bash
ssh ubuntu@<host-ip> "systemctl list-units --type=service | grep -i devpod"
ssh ubuntu@<host-ip> "sudo systemctl stop devpod.service && sudo systemctl disable devpod.service"
```

This is the one action that reliably stops auto-stop/agent interference.
After this, devpod CLI commands for this workspace are unreliable (they talk
to the dead agent) — switch entirely to plain `aws ec2 ...` + direct `ssh`.

### Resizing the instance once decoupled

Standard EC2 resize: stop instance → wait stopped →
`modify-instance-attribute` with new type → start → wait running. **The
public IP changes on every stop/start** unless an Elastic IP is attached —
always re-fetch it after a resize and don't reuse the old IP in scripts/SSH
configs.
