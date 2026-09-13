---
name: local-state-monitoring
description: Poll and monitor local tasks, processes, and SQLite DBs.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [monitoring, polling, tmux, watchdog, canary, devops]
    category: devops
---

# Local State Monitoring

Umbrella skill for monitoring, polling, and building watchdogs around local state (e.g. background tasks, tmux sessions, SQLite DBs, log files). 

## When to Use
- When asked to poll a local task, tmux session, or log file until completion.
- When asked to build a watchdog or canary script against a local database.

## Playbooks
- `references/background-task-polling.md` (Polling a tmux/task dir on interval)
- `references/watchdog-script-verification.md` (Building silent-unless-new watchdogs)
