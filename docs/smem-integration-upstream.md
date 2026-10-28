# synapse-mem integration (upstream)

The synapse-mem agent integrations hub no longer lives in this repo. The single source of truth is the fork:

- Repo: https://github.com/agg-ayush/synapse-mem
- Branch: `feat/agent-integrations-hub` (directory `integrations/`)

It contains the Hermes `MemoryProvider` plugin with its E2E test, Claude Code wiring, a generic MCP config, and the install, store-setup and sync scripts.

Activate in Hermes: `sh integrations/agents/hermes/activate.sh` from a clone of the fork (`--uninstall` reverses it).
