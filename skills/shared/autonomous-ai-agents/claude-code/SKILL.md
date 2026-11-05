---
name: claude-code
description: "Delegate coding to Claude Code CLI (features, PRs)."
version: 2.4.0
author: Teknium (teknium1), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Coding-Agent, Claude, Anthropic, Code-Review, Refactoring, PTY, Automation]
    related_skills: [codex, hermes-agent, opencode]
---

# Claude Code — Hermes orchestration

Use Claude Code for bounded coding, implementation, and interactive code review; independently inspect its diff and run relevant tests before claiming completion. [Official CLI reference](https://code.claude.com/docs/en/cli-reference). Read [CLI and troubleshooting reference](references/cli-and-troubleshooting.md) only for a needed flag, hook, route, or failure mode.

## When to use

- **Default for Ayush:** interactive `claude` in persistent tmux for implementation, iterative work, and every substantive Claude-based review. Start the task immediately, watch live output, answer reviewer-selection questions, and verify artifacts. Use `--dangerously-skip-permissions` only in a trusted workspace with the intended isolation; this grants broad execution rights.
- **Print mode (`-p`):** short, bounded tasks that cannot need clarification or steering, e.g. read-only analysis or structured extraction. It skips interactive dialogs **and denies unapproved tool permissions** instead of prompting. For writes, pass a narrow `--allowedTools` set or intentionally use `--dangerously-skip-permissions`; otherwise a run may claim it needs edit approval and change nothing.
- Do **not** inject `--max-turns` by default; add a turn cap only when Ayush explicitly asks. A foreground timeout is not a substitute for monitoring a long interactive run.
- **Alternatives:** [agent view](https://code.claude.com/docs/en/agent-view) (`claude --bg`, `claude agents --json --all`, `logs`/`attach`/`stop`) gives structured background state but is a separate mode from `-p` and may still require attachment for permission dialogs. [Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview) or [headless stream-json](https://code.claude.com/docs/en/headless) supports programmatic events and steering. Agent teams cannot spawn from `-p`/SDK sessions ([limitations](https://code.claude.com/docs/en/agent-teams)). Choose the alternative deliberately; it does not silently replace Ayush's tmux preference.

## Prerequisites and route

1. Install/check through `terminal(command="claude --version && claude auth status --text")`; install via `npm install -g @anthropic-ai/claude-code` if missing. Use a supported CLI for the requested model without replacing a global binary used by live tasks.
2. Determine the intended auth/billing route **before** starting a coder. OAuth Teams and a TrueFoundry gateway must not be mixed. On a TF session, explicitly unset `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_BACKUP`, and `BACKUP_ANTHROPIC_API_KEY` just before Claude: ambient API keys override `ANTHROPIC_AUTH_TOKEN` and can cause 401/hangs. This unset is **not** a blanket rule for direct Anthropic API-key billing.
3. For a Teams subscription subprocess, prevent inherited TF routing (`ANTHROPIC_BASE_URL`, `ANTHROPIC_CUSTOM_HEADERS`, gateway token): pass a controlled environment to the child; never paste or log token values. Check effective route/model from response metadata, not only successful exit or a model string. Seatbelt model IDs use plain `claude-teams-group/...`, **without `[1m]`**.
4. On **devbox** (EC2 host `sora`), do not use retired `saml2aws`. A TF gateway, when explicitly intended, uses base URL `https://<llm-gateway>.truefoundry.cloud/api/llm` (not `/api/llm/api/inference/anthropic`) and a securely sourced `ANTHROPIC_AUTH_TOKEN`; `claude --model` takes a bare upstream model ID such as `claude-sonnet-5`, not `claude-group/claude-sonnet-5`. Do not assume TF is the default route merely because older Ubuntu notes said so. Probe route with a harmless one-shot request and verify actual model/billing before implementation. Never print credential values or `/proc/<pid>/environ` wholesale.

## Observable procedure

1. **Isolate writers:** one non-main branch/worktree per concurrent code-changing task; read-only sessions may share a checkout only if they cannot modify it. Set the working directory explicitly. Allocate `~/.hermes/tasks/<task-id>/` for `prompt.md`, `status.md`, `result.md` and (Linux/macOS) `tmux.log`, outside PR diffs.
2. **Prefer `claude_orchestrate` when available** (deferred tool). `start(task_id, prompt, workdir, worktree?)` launches tmux with the prompt as a CLI argument; worktree is opt-in. `wait(task_id, timeout<=360, interval>=3)` returns `working`, `needs_input`, `done`, or `exited`; on `needs_input`, inspect `status` and `steer`. `result` reads artifacts and git diffstat; `stop` exits/cleans the session. The Hermes deferred-tool call is capped around 420s; keep each wait <=360s and repeat only when still working. A `done` or `exited` signal is not proof of correct code. The plugin can be absent in an already-running session; fall back to manual tmux below.
3. **Manual launch:** start tmux in the correct worktree and route; give the initial prompt on launch rather than opening an idle REPL. For multiline prompts, write `prompt.md` and submit a **single-line** instruction pointing Claude to it; `tmux send-keys` interprets embedded newlines as separate submissions. Example (replace paths/session; set auth before starting):
   ```bash
   tmux new-session -d -s claude-task -x 140 -y 40 \
     "cd /path/to/worktree && unset ANTHROPIC_API_KEY ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY && claude --dangerously-skip-permissions 'Read ~/.hermes/tasks/task-id/prompt.md in full and execute it.'"
   tmux capture-pane -t claude-task -p -S -80
   ```
   The `unset` in this example is for **TF token routing only**; for Teams/OAuth or direct API-key billing, construct the corresponding controlled environment instead. Do not blindly send Enter/Down to a dialog on a timer: inspect the actual pane first. First-time workspace trust defaults to Yes (Enter); bypass-permissions confirmation defaults to No (Down then Enter). Print mode has neither dialog. Root/uid 0 rejects bypass outright; use an existing non-root account, not a fake dialog workaround.
4. **Monitor promptly:** `tmux has-session -t <session>` then `tmux capture-pane -t <session> -p -S -80`; check immediately after startup and steering, then adapt interval to live progress. Look for input prompts (`❯`), explicit errors, shell prompt, vanished session, or stall. Use `tmux pipe-pane` for complete logs on Linux/macOS; **never on Windows git-bash/MSYS**, where it can crash the server. Ask Claude to update `status.md` at phase boundaries, but validate against pane/process state and git/test evidence. A missing session on the default socket does not prove death: check matching Claude PIDs and whether tmux used `-L <socket>` before starting another writer.
5. **Review separately:** run a distinct interactive review (including `/review` or project review toolkit); answer reviewer-agent selection questions; feed actionable findings back to the implementation session. Re-run tests/build independently outside Claude and inspect the final diff. Record result, exit/kill owned tmux session. Do not stop another live writer or equate an agent's final prose with a verified artifact.

## Pitfalls and verification

- Before a Linux Opus/TF review using credential scrubbing, retain `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`; test an actual Bash `pwd` within that session, ensure its Bash process has **no provider credentials** (presence only), and verify served/modelUsage model. On Claude Code v2.1.284, scrubbing can force bwrap even with `sandbox.enabled=false`; stale macOS PATH entries on Linux can break its preflight. Ubuntu 24.04 AppArmor may block bwrap unprivileged user namespaces. Use a process-scoped trusted Linux PATH; do not disable scrubbing or host-wide AppArmor. See [route and sandbox pitfalls](references/cli-and-troubleshooting.md).
- Do not trust a blank pane, a `starting` status, or a successful Claude exit as completion. Check actual `claude` binary resolved in tmux, route, git diff, and tests. A fresh worktree with an incomplete `node_modules` can make `npx` download a mismatched floating test runner; use the repository's locked install command before evaluating failures.
- Before claiming done: verify expected files and diff, run the relevant test/build outside Claude, compare observed served model and billing route if relevant, and distinguish `needs_input`/`exited`/failed tests from completion. See [reference](references/cli-and-troubleshooting.md) for hooks, flags, logging and rare platform failures.
