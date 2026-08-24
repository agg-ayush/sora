---
name: serena-mcp
description: "Wire Serena (LSP-backed semantic code navigation MCP server) into Hermes via hermes mcp add."
version: 1.0.0
author: Ayush + Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mcp, serena, code-navigation, lsp, semantic-search, refactoring, setup]
    homepage: https://github.com/oraios/serena
    related_skills: [hermes-agent, claude-code, codex]
---

# Serena MCP Server

Serena (github.com/oraios/serena, MIT) is an LSP-backed **semantic code navigation
and editing** MCP server. It gives an agent symbol-level tools — find symbol,
find references, find implementations, rename symbol, replace symbol body,
insert before/after symbol, per-file diagnostics — instead of grepping and reading
whole files. Backed by language servers (LSP) for 40+ languages, so it understands
code structure and relational context, not just text.

Value is highest on **large, existing codebases** (precise retrieval, cross-file
refactors). Low value on new/empty projects or single-file scripts — the semantic
overhead isn't worth it there.

## When to Use

- User wants Hermes to navigate/refactor a large codebase at the symbol level
  (rename across files, find all references, replace a function body precisely)
- You're burning context grepping + reading whole files to understand structure
- Setting up Hermes for serious work on an unfamiliar/large repo

Skip for: greenfield projects, tiny scripts, doc-only work.

## Prerequisites (already satisfied on Ayush's Mac)

- **`uvx`** — bundled with Hermes at `~/.hermes/bin/uvx` (uv 0.11.x). No separate
  install. If not on PATH, prefix with the full path: `~/.hermes/bin/uvx`.
- **`mcp` Python SDK** — already present in Hermes' own venv
  (`~/.hermes/hermes-agent/venv/.../site-packages/mcp/`). Hermes' native MCP client
  uses it. If a fresh machine lacks it, MCP is silently disabled — fix with
  `~/.hermes/hermes-agent/venv/bin/python -m pip install mcp` (install into the
  venv Hermes actually runs, not the system python).
- No git clone, no `serena init` needed — `uvx --from git+...` builds and runs it
  on demand and caches it.

## Setup — the one command

Run from a real terminal (it prompts interactively; pipe answers for non-interactive):

```bash
export PATH="$HOME/.hermes/bin:$PATH"

hermes mcp add serena \
  --command uvx \
  --args --from git+https://github.com/oraios/serena serena start-mcp-server \
         --context ide --project-from-cwd
```

Everything after `--args` is passthrough argv for the child command — do NOT quote
it as one string; pass each token as a separate arg (Hermes stops its own flag
parsing at `--args`).

Hermes then connects live, discovers Serena's tools (24 with `--context ide`),
and asks `Enable all N tools? [Y/n/select]`. Answer `Y`. It writes to
`~/.hermes/config.yaml` and says "Start a new session to use these tools."

**Non-interactive** (answer the overwrite-if-exists + enable-all prompts):

```bash
printf "y\ny\n" | hermes mcp add serena --command uvx \
  --args --from git+https://github.com/oraios/serena serena start-mcp-server \
         --context ide --project-from-cwd
```

### Why `--context ide` and `--project-from-cwd`

- `--context ide` — Serena's tool/prompt profile tuned for terminal-based generic
  MCP clients (reduces tool duplication with the host agent). Hermes is exactly
  this. Do NOT use `desktop-app` (the default) or the client-specific
  `claude-code` / `ide-assistant` contexts. `ide` yields 24 tools including
  `execute_shell_command`; `ide-assistant` drops a couple of the basic file tools
  (23 tools) on the assumption the host provides them — either is fine, `ide` is
  the safe default. List contexts with:
  `~/.hermes/bin/uvx --from git+https://github.com/oraios/serena serena context list`
- `--project-from-cwd` — auto-activates the project from Hermes' working directory
  (looks for `.serena/project.yml` or `.git`, falls back to cwd). This is the right
  choice because Hermes has ONE global `mcp_servers` config (not per-workspace), so
  the server should bind to whatever repo the session is running in. Alternative:
  pin one repo with `--project /abs/path/to/repo` instead of `--project-from-cwd`.

## Resulting config.yaml shape

```yaml
mcp_servers:
  serena:
    command: uvx
    args:
      - --from
      - git+https://github.com/oraios/serena
      - serena
      - start-mcp-server
      - --context
      - ide
      - --project-from-cwd
    enabled: true
```

You can hand-edit this instead of using the CLI, but the CLI does a live connect +
tool-discovery validation, so prefer `hermes mcp add`.

## After setup

- **Restart / new session required.** MCP tools are discovered at startup and NOT
  hot-reloaded mid-conversation (prompt-cache invariant). Start a new `hermes`
  session or `/reload-mcp` in-session.
- Tools appear prefixed: `mcp_serena_find_symbol`, `mcp_serena_replace_symbol_body`,
  `mcp_serena_find_referencing_symbols`, etc. (Hermes naming: `mcp_{server}_{tool}`).
- Verify: `hermes mcp list`, `hermes mcp test serena`, or in-session ask the agent
  to use a Serena tool.

## Management commands

| Command | What |
|---|---|
| `hermes mcp list` | Show configured servers |
| `hermes mcp test serena` | Live connect + tool-discovery check |
| `hermes mcp configure serena` | Toggle which discovered tools are enabled |
| `hermes mcp remove serena` | Remove (also cleans up any OAuth tokens) |

## Key Serena tools (post-prefix `mcp_serena_*`)

- `find_symbol` — global/local symbol search by name path
- `get_symbols_overview` — top-level symbols in a file (outline, no full read)
- `find_referencing_symbols` — everywhere a symbol is used
- `find_implementations` / `find_declaration`
- `replace_symbol_body` — swap a function/class body precisely
- `insert_before_symbol` / `insert_after_symbol`
- `rename_symbol` — LSP-backed rename across the codebase
- `get_diagnostics_for_file` — LSP diagnostics
- `search_for_pattern`, `replace_content`, `read_file`, `find_file`, `list_dir` — basics
- `write_memory` / `read_memory` / `list_memories` — Serena's per-project memory
- `activate_project` — needed only if NOT using `--project-from-cwd`/`--project`

## Pitfalls

- **First run is slow.** `uvx` builds Serena + downloads ~77 packages on the very
  first invocation (tens of seconds). Bump `connect_timeout` if the initial
  discovery times out: add `connect_timeout: 120` to the server entry, or
  `--connect-timeout 120` on `hermes mcp add`. Subsequent runs are cached and fast
  (<1s to spawn).
- **Don't quote the `--args` payload as one string.** Each token is a separate arg.
- **`serena` command not found (if not using uvx).** If you ever switch to a local
  install, the spawned subprocess may not find `serena` on PATH — use the absolute
  path to the executable in `command`.
- **Global config, not per-repo.** Hermes has one `mcp_servers` map. `--project-from-cwd`
  makes it follow the session's cwd; if you work across many repos in one session,
  Serena re-activates per cwd on connect but won't switch mid-session — restart or
  ask the agent to `activate_project` a different path.
- **Env vars for some language servers.** A few LSPs need extra env (e.g. .NET's
  `DOTNET_ROOT`). Add them under an `env:` key on the server entry — the MCP
  subprocess gets a filtered environment and won't inherit your shell profile.
- **mcp SDK missing on a fresh box** → MCP silently disabled. Install `mcp` into
  Hermes' venv (see Prerequisites), not system python.

## Verified

Setup verified live end-to-end on macOS: `hermes mcp add serena --command uvx
--args ... --context ide --project-from-cwd` connected, discovered 24 tools, saved
the config shape above, and `hermes mcp remove serena` cleaned it up. `uvx` and the
`mcp` SDK confirmed present in the Hermes install.
