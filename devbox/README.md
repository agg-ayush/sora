# Devbox (DevPod on AWS)

Persistent remote dev environment: c6a.2xlarge EC2 in us-east-1a, runs the
devcontainer in this directory. Built for running hermes + claude code agents
with node/python/docker available.

## Files

- `devcontainer.json` — image + features (node 22, python 3.12, docker-in-docker, git, gh, aws-cli)
- `post-create.sh` — bakes claude code, hermes agent, ripgrep into the image (idempotent)
- `setup-hermes.sh` — one-time wiring: clones this repo, symlinks plugin/skills/scripts, copies config templates. Run after `gh auth login` on the box.

## Use

```bash
# first time (from the machine with devpod + AWS creds)
mkdir -p ~/devbox/.devcontainer
cp devcontainer.json post-create.sh setup-hermes.sh ~/devbox/.devcontainer/
devpod provider add aws
devpod provider set-options aws \
  -o AWS_INSTANCE_TYPE=c6a.2xlarge -o AWS_DISK_SIZE=80 \
  -o AWS_REGION=us-east-1 -o AWS_AVAILABILITY_ZONE=us-east-1a \
  -o AWS_VPC_ID=<your-vpc> -o INACTIVITY_TIMEOUT=0
devpod up ~/devbox --provider aws --ide none

# then on the box
devpod ssh devbox
gh auth login
~/setup-hermes.sh
# fill ~/.hermes/.env with API keys; run `claude` once for OAuth
```

## Gotchas

- Repo clone is NOT in post-create on purpose: devpod 0.6 panics on
  git-credential lookups during lifecycle hooks (loft-sh/devpod#1719), and the
  repo is private anyway. `setup-hermes.sh` runs post-`gh auth login` instead.
- AWS SAML creds expire hourly; if `devpod up` fails with auth errors, refresh
  creds and retry.
- Workspace auto-stops when no session is attached, regardless of
  INACTIVITY_TIMEOUT. `devpod up` resumes in ~30s.
