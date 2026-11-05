# Adding an MCP server on the user's behalf

General API-key/stdio and management guidance: `references/mcp-server-setup.md`. This note covers browser handoff for remote OAuth.

When wiring up a new remote MCP server from an agent session (non-interactive
terminal, no browser), the two auth shapes need different handling.

## API key / Bearer header

Set directly, no handoff needed:

```
hermes config set mcp_servers.<name>.url "<url>"
hermes config set mcp_servers.<name>.headers.Authorization "Bearer <key>"
hermes mcp test <name>
```

If the provider returns 403 with an otherwise-valid-looking key, don't
conclude MCP is broken — many providers scope MCP access to a distinct key
type from the regular API key (e.g. Recall.ai requires a key minted via an
explicit "New MCP API Key" flow, identifiable by an `mcp_` prefix; a normal
account API key is rejected at the MCP endpoint even though it works
everywhere else). Check the provider's MCP-specific docs for a separate
key-creation step before debugging transport/header code.

## OAuth

The authorization step needs a real browser — the agent cannot complete it.
Split the work: do the config half yourself, hand off the browser half.

1. **Check whether the server actually accepts arbitrary OAuth clients**
   before assuming Hermes can connect. Fetch the two discovery documents:

   ```
   curl -s https://<mcp-host>/.well-known/oauth-authorization-server
   curl -s https://<mcp-host>/.well-known/oauth-protected-resource
   ```

   A `registration_endpoint` present with
   `token_endpoint_auth_methods_supported: ["none"]` means dynamic client
   registration (DCR) is open — Hermes's OAuth defaults (PKCE, public client,
   `client_name: "Hermes Agent"`) will register and work without a
   pre-registered `client_id`/`client_secret`. Don't take a provider's docs
   framing ("OAuth-only, allowlisted clients", "only Claude Desktop/Code
   supported") as a hard technical gate — that language usually describes
   which clients the provider *tested*, not which ones DCR actually rejects.
   Verify against the discovery document, not the prose.

2. **Set config directly, don't drive the interactive wizard blind.**

   ```
   hermes config set mcp_servers.<name>.url "<url>"
   hermes config set mcp_servers.<name>.auth oauth
   ```

   Do NOT run `hermes mcp add <name> --url <url> --auth oauth` from a
   scripted/non-interactive shell — it launches the OAuth flow inline,
   fails with "non-interactive environment and no cached tokens found", then
   blocks on `Continue without authentication? [Y/n]` and `Save config
   anyway? [y/N]` prompts. A scripted/EOF answer to those can abort *before*
   the config is saved, silently losing the edit. Setting `url` and `auth`
   as two plain `config set` calls is unconditionally reliable; the wizard
   is not, outside a real TTY.

3. **Hand off the login step to the user.** Tell them to run
   `hermes mcp login <name>` in their own interactive terminal — it prints
   an authorize URL, opens their browser, and waits on the local callback.
   The agent's terminal tool has no display/browser to do this itself, and
   should not try. Tokens land at `~/.hermes/mcp-tokens/<name>.json` (0600)
   once they approve.

4. **Verify after handoff, not before.** `hermes mcp test <name>` works
   standalone and doesn't require the tools to be registered in a running
   session. New MCP tools only register at process/session startup, so even
   a successful login won't surface `mcp__<name>__*` tools in the *current*
   session — check with `hermes mcp test` or a fresh session, not by
   searching the live session's toolset.
