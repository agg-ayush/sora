# MCP server setup in Hermes

Use when asked to add, wire up, configure, authenticate, or troubleshoot an
MCP server in Hermes — from an agent session (non-interactive terminal, no
browser). Split by auth shape: API-key, OAuth, and local stdio servers each
have different mechanics.

## API key / Bearer header

Store the provider key in the host's private `.env` (or configured secret store) without printing it. Configure an environment-variable reference, not the literal key:

```bash
hermes config set mcp_servers.<name>.url "<url>"
hermes config set mcp_servers.<name>.headers.Authorization 'Bearer ${MCP_NAME_API_KEY}'
hermes mcp test <name>
```

Check whether the installed Hermes version expands this reference in MCP headers. If it does not, use its supported key-command/secret mechanism rather than committing or printing a bearer token.

A 403 with a valid-looking key often means the provider scopes MCP access to
a distinct key type (e.g. an `mcp_`-prefixed key minted via a dedicated flow),
not that MCP is broken — check the provider's MCP-specific key docs before
debugging transport/headers.

## OAuth

The authorization step needs a browser on the callback host. Use an interactive browser handoff where required.
Split the work: do the config half yourself, hand off the browser half.

1. **Check whether the server actually accepts arbitrary OAuth clients**
   before assuming Hermes can connect — fetch the discovery documents:
   ```
   curl -s https://<mcp-host>/.well-known/oauth-authorization-server
   curl -s https://<mcp-host>/.well-known/oauth-protected-resource
   ```
   A `registration_endpoint` present with
   `token_endpoint_auth_methods_supported: ["none"]` means dynamic client
   registration (DCR) is open — Hermes's OAuth defaults (PKCE, public client)
   register and work without a pre-registered client. Don't take a provider's
   docs framing ("OAuth-only, allowlisted clients") as a hard technical gate —
   verify against the discovery document, not the prose.
2. **Set config directly, don't drive the interactive wizard blind.**
   ```
   hermes config set mcp_servers.<name>.url "<url>"
   hermes config set mcp_servers.<name>.auth oauth
   ```
   Do NOT run `hermes mcp add <name> --url <url> --auth oauth` from a
   scripted/non-interactive shell — it launches the OAuth flow inline, fails,
   then blocks on prompts a scripted/EOF answer can abort *before* the config
   is saved, silently losing the edit. Two plain `config set` calls are
   unconditionally reliable.
3. **Hand off the login step to the user.** They run `hermes mcp login <name>`
   in their own interactive terminal — it prints an authorize URL, opens their
   browser, and waits on the local callback. Tokens land at
   `~/.hermes/mcp-tokens/<name>.json` (0600) once they approve.
4. **Verify after handoff, not before.** `hermes mcp test <name>` works
   standalone.

For the user-facing remote-OAuth handoff detail, also see
`mcp-server-oauth-setup.md` in this skill's references.

## Local (stdio) servers — the `hermes mcp add` shape

For command-based (stdio) servers, `hermes mcp add` is the right entry point —
it does a live connect + tool-discovery validation that hand-editing
`config.yaml` skips:

```bash
hermes mcp add <name> --command <binary> --args <arg1> <arg2> ...
```

Everything after `--args` is passthrough argv — pass each token as a separate
arg, never one quoted string. Non-interactive: pipe the answers, e.g.
`printf "y\ny\n" | hermes mcp add ...`.

Config shape it produces:

```yaml
mcp_servers:
  <name>:
    command: <binary>
    args: [...]
    enabled: true
```

## Pitfalls (any server type)

- **Tools register at session startup only, never hot-reloaded.** After any
  add/config change, start a new session or `/reload-mcp` — a successful
  `mcp test` still won't surface `mcp__<name>__*` tools in the current
  session.
- **Hermes has ONE global `mcp_servers` map, not per-workspace.** Prefer
  binding a code server to the session cwd over pinning one repo path.
- **A subprocess spawned via `command:` gets a filtered environment** — it
  won't inherit your shell profile. Add needed vars under an `env:` key on the
  server entry (e.g. `DOTNET_ROOT` for some LSPs).
- **If `command:` is a locally-installed binary, use the absolute path** —
  the spawned subprocess may not find it on PATH.
- **Python `mcp` SDK missing on a fresh box → MCP silently disabled.** Install
  it into the venv Hermes actually runs
  (`~/.hermes/hermes-agent/venv/bin/python -m pip install mcp`), not system
  python.
- **First run of a `uvx`-launched server is slow** (builds + downloads deps).
  Bump `connect_timeout: 120` on the server entry if initial discovery times
  out; subsequent runs are cached.

## Management commands

| Command | What |
|---|---|
| `hermes mcp list` | Show configured servers |
| `hermes mcp test <name>` | Live connect + tool-discovery check |
| `hermes mcp configure <name>` | Toggle which discovered tools are enabled |
| `hermes mcp remove <name>` | Remove (also cleans up OAuth tokens) |
