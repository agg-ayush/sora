---
name: hookify
description: "Turn a plain-English rule into a working Hermes shell-hook (config entry + script)."
version: 1.0.0
author: Ayush + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hooks, shell-hooks, automation, guardrails, config, hermes]
    related_skills: [hermes-agent, requesting-code-review]
---

# Hookify — plain-English rule → working Hermes shell hook

Turn a request like "warn me before rm -rf" or "auto-format Python after every
write" into a real, wired-up Hermes **shell hook**: a `hooks:` entry in
`~/.hermes/config.yaml` plus a small script under `~/.hermes/agent-hooks/`.

Native Hermes equivalent of Claude Code's `hookify` plugin, but targeting
Hermes' actual shell-hook system (NOT Claude Code's `PreToolUse`/`settings.json`
format). Shell hooks run as subprocesses in both CLI and gateway sessions — no
Python plugin authoring needed.

## When to Use

- User states a behavioral rule in plain English: "don't let it push to main",
  "block dangerous shell commands", "format TS files after editing", "log every
  subagent completion", "inject git status into every turn".
- User says "make a hook for X" / "hookify X" / "add a guardrail".

Skip when: the rule is a one-off (just do it), or it needs in-process access to
Hermes internals (write a Python plugin instead).

## Decision: which hook mechanism?

| Need | Use |
|---|---|
| Drop-in script, block/observe/transform, CLI+gateway | **Shell hook** (this skill) |
| In-process, Python, complex state | Plugin hook (`~/.hermes/plugins/`) |
| Keep a *coding* agent going until a check passes | `pre_verify` — see `requesting-code-review` |
| Standing coding posture, no gating | `agent.coding_instructions` config (cheaper) |

Prefer the cheapest thing that works. A shell hook costs a subprocess per event.

## The valid events (VALID_HOOKS)

Event name MUST be one of these (typo → "Did you mean X?" warning, skipped):

- `pre_tool_call` — before any tool runs. **Can block.** Matcher applies.
- `post_tool_call` — after a tool returns. Observe / react (e.g. format). Matcher applies.
- `pre_llm_call` — once per turn before the tool loop. **Can inject context.**
- `post_llm_call` — once per turn after the tool loop. Observe.
- `pre_verify` — code-edit turns, before finish. Can keep the agent going.
- `on_session_start` / `on_session_end` / `on_session_finalize` / `on_session_reset`
- `subagent_start` / `subagent_stop` — delegation lifecycle.
- `transform_terminal_output` / `transform_tool_result` / `transform_llm_output`
- `pre_api_request` / `post_api_request` / `api_request_error`
- `pre_gateway_dispatch` (gateway only) / `pre_approval_request` / `post_approval_response`

Matcher (regex on `tool_name`) is only meaningful for `pre_tool_call` / `post_tool_call`.

## Config schema

```yaml
# ~/.hermes/config.yaml
hooks:
  <event_name>:
    - matcher: "<regex>"          # optional; pre/post_tool_call only
      command: "<shell command>"  # required; runs via shlex.split, shell=False
      timeout: <seconds>          # optional; default 60, capped at 300

hooks_auto_accept: false          # see Consent below
```

Add via `hermes config edit` (the agent-write guard blocks direct config.yaml
writes for the agent, so the *user* edits it or uses `hermes config`).

## JSON wire protocol (script contract)

Each fire: Hermes pipes JSON to the script's **stdin**, reads JSON from **stdout**.

**stdin:**
```json
{
  "hook_event_name": "pre_tool_call",
  "tool_name": "terminal",
  "tool_input": {"command": "rm -rf /"},
  "session_id": "sess_abc",
  "cwd": "/path",
  "extra": {"task_id": "...", "tool_call_id": "..."}
}
```
`tool_name`/`tool_input` are `null` for non-tool events. `extra` carries
event-specific kwargs (`user_message`, `changed_paths`, `attempt`, `coding`,
`child_role`, `duration_ms`, …).

**stdout (all optional):**
```jsonc
{"decision": "block", "reason": "..."}    // block a pre_tool_call (Claude-Code shape)
{"action": "block", "message": "..."}     // block (Hermes-canonical shape)
{"context": "..."}                         // inject into pre_llm_call
{"action": "continue", "message": "..."}   // keep agent going at pre_verify
// empty / no output / {} == silent no-op
```
Malformed JSON, non-zero exit, and timeouts log a warning but never abort the
agent. Fail-open by design.

## Build procedure

1. **Map intent → event + matcher.** "before X runs / block X" → `pre_tool_call`.
   "after X" → `post_tool_call`. "every turn add context" → `pre_llm_call`.
   Pick the matcher regex on `tool_name` (`terminal`, `write_file|patch`, etc.).
2. **Write the script** to `~/.hermes/agent-hooks/<name>.sh`, `chmod +x`. Read
   stdin JSON with `jq`, decide, print the response JSON. ALWAYS print at least
   `{}` so stdout is valid.
3. **Add the config entry** under `hooks:` (user does this via `hermes config edit`).
4. **Approve consent** — first run prompts per `(event, command)` pair, persisted
   to `~/.hermes/shell-hooks-allowlist.json`. Non-TTY (gateway/cron): set
   `hooks_auto_accept: true` OR `HERMES_ACCEPT_HOOKS=1` OR `--accept-hooks`.
5. **Verify** with `hermes hooks test <event> [--for-tool X]` (fires against a
   synthetic payload) and `hermes hooks doctor` (checks exec bit, allowlist,
   mtime drift, JSON validity, timing).

## Worked recipes

### Block direct commits/pushes to main (fits Ayush's standing rule)

```yaml
hooks:
  pre_tool_call:
    - matcher: "terminal"
      command: "~/.hermes/agent-hooks/block-main-write.sh"
      timeout: 5
```
```bash
#!/usr/bin/env bash
# ~/.hermes/agent-hooks/block-main-write.sh
payload="$(cat -)"
cmd=$(echo "$payload" | jq -r '.tool_input.command // empty')
# block git commit/push when current branch is main/master
if echo "$cmd" | grep -qE 'git (commit|push)'; then
  branch=$(git -C "$(echo "$payload" | jq -r '.cwd // "."')" symbolic-ref --short HEAD 2>/dev/null)
  if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    printf '{"decision":"block","reason":"Blocked: no direct %s on %s. Use a branch."}\n' \
      "$(echo "$cmd" | grep -oE 'commit|push' | head -1)" "$branch"
    exit 0
  fi
fi
printf '{}\n'
```

### Block `rm -rf /` style commands

```yaml
hooks:
  pre_tool_call:
    - matcher: "terminal"
      command: "~/.hermes/agent-hooks/block-rm-rf.sh"
      timeout: 5
```
```bash
#!/usr/bin/env bash
payload="$(cat -)"
cmd=$(echo "$payload" | jq -r '.tool_input.command // empty')
if echo "$cmd" | grep -qE 'rm[[:space:]]+-rf?[[:space:]]+/'; then
  printf '{"decision":"block","reason":"blocked: rm -rf / not permitted"}\n'
else
  printf '{}\n'
fi
```

### Auto-format Python/TS after every write

```yaml
hooks:
  post_tool_call:
    - matcher: "write_file|patch"
      command: "~/.hermes/agent-hooks/auto-format.sh"
```
```bash
#!/usr/bin/env bash
payload="$(cat -)"
path=$(echo "$payload" | jq -r '.tool_input.path // empty')
case "$path" in
  *.py)  command -v black >/dev/null && black "$path" 2>/dev/null ;;
  *.ts|*.tsx) command -v prettier >/dev/null && prettier --write "$path" 2>/dev/null ;;
esac
printf '{}\n'
```
Note: the agent's in-context view of the file is NOT re-read automatically — the
reformat only lands on disk; a later `read_file` picks it up.

### Inject git status into every turn (Claude-Code UserPromptSubmit equivalent)

```yaml
hooks:
  pre_llm_call:
    - command: "~/.hermes/agent-hooks/inject-git-status.sh"
```
```bash
#!/usr/bin/env bash
cat - >/dev/null   # discard stdin
if status=$(git status --porcelain 2>/dev/null) && [[ -n "$status" ]]; then
  jq --null-input --arg s "$status" '{context: ("Uncommitted changes:\n" + $s)}'
else
  printf '{}\n'
fi
```
(Claude Code's `UserPromptSubmit` maps to `pre_llm_call` here — no separate event.)

### Log every subagent completion

```yaml
hooks:
  subagent_stop:
    - command: "~/.hermes/agent-hooks/log-subagents.sh"
```
```bash
#!/usr/bin/env bash
jq -c '{ts: now, parent: .session_id, extra: .extra}' < /dev/stdin \
  >> ~/.hermes/logs/orchestration.log
printf '{}\n'
```

## `hermes hooks` CLI

| Command | What |
|---|---|
| `hermes hooks list` | Configured hooks: matcher, timeout, consent status |
| `hermes hooks test <event> [--for-tool X] [--payload-file F]` | Fire against a synthetic payload, show parsed response |
| `hermes hooks revoke <command>` | Remove allowlist entries for a command |
| `hermes hooks doctor` | Exec bit, allowlist, mtime drift, JSON validity, timing |

## Pitfalls

- **Always print valid JSON to stdout** (at minimum `{}`). Garbage stdout → warning, hook ignored.
- **`command` runs via `shlex.split`, shell=False** — no pipes/redirects/globs in the
  config `command` string itself. Put shell logic inside the script.
- **Two block shapes both work**: `{"decision":"block","reason":...}` and
  `{"action":"block","message":...}`. Message/reason must be non-empty to block.
- **Consent is keyed on the exact command string, not the script hash.** Editing the
  script does NOT re-prompt. `hermes hooks doctor` flags mtime drift so you can
  spot silent edits.
- **Non-TTY sessions** (gateway, cron, CI) silently skip un-approved hooks — set one
  of the three consent bypasses first.
- **Matcher only matters for pre/post_tool_call.** On other events it's ignored.
- **`pre_llm_call` fires once per turn**, not per message — use it for per-turn context.
- **Agent can't write config.yaml directly** (security guard). The user runs
  `hermes config edit` to add the `hooks:` block; the agent writes the *script* file.
- **Fail-open**: a broken hook never blocks the agent. If a block isn't firing, run
  `hermes hooks test` — the script probably printed bad JSON or exited nonzero.

## Verified

Event list pulled from `hermes_cli/plugins.py::VALID_HOOKS`; schema, wire protocol,
consent model, and CLI from Hermes' shell-hooks docs. Recipes follow the documented
stdin/stdout contract.
