# AWS Article-Generation + Render Fleet — Reference

Infra design notes for the alpha-learn article-generation and video-render fleets.
Moved out of always-loaded agent memory (2026-07-24) to keep the per-turn context
lean; this is the on-disk source of truth.

## Article-generation fleet (us-east-1)

- **Topology:** baseline always-on enabled worker (`AtLogOn` trigger + autologon)
  + a burst ASG. The scaler Lambda ticks every 1 min; `BaselineReserve` subtracts
  from the backlog before computing the scaling target.
- **Golden AMI:** baked from the baseline with `--no-reboot` (preserves Office
  cached-token activation; activation domains are blocked via the hosts file).
- **Fleet clones self-start** the worker via autologon + `AtLogOn`. PR #1248 fixed a
  bug where the AMI was baked with `WORKER_START=paused` → the scheduled task was
  Disabled → clones came up idle. Now clones self-start correctly.
- **Worker runtime:** uses PowerPoint COM in **Session 1** (interactive desktop),
  NOT a Windows service — COM automation needs the interactive session.

## Render fleet (eu-north-1)

- Consumes `video-render-jobs.fifo` in **eu-north-1**.
- The `alpha-learn-qc` bucket is in **eu-north-1** (NOT us-east-1) — watch the region
  when reading/writing QC artifacts.

## Queues

- `generation-jobs.fifo` is owned by the `alpha-article-generation-queue` stack.
  It was transferred from the deleted `alpha-generation` (Linux) stack via a
  RETAIN → DELETE → IMPORT sequence (so the queue survived the stack deletion).

## Credentials

- **WorkerPassword** (the `articlegen` Windows account) must MATCH the autologon
  `DefaultPassword`, or clones sit idle at the login screen. The value is stored in
  the AWS stack / Secrets — retrieve it from there (do NOT hardcode it in scripts or
  memory). If you rotate it, update BOTH the account password and the autologon
  `DefaultPassword` registry value in the AMI, then re-bake.
