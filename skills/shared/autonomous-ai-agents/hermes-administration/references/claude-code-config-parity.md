# Claude Code config parity (seatbelt config dir + cross-host)

Use when the seatbelt Claude Code config (`CLAUDE_CONFIG_DIR=~/.hermes/claude-seatbelt-config`) or a second host should see the same plugins, skills and rules as the normal `~/.claude`.

## Seatbelt config dir mirrors ~/.claude
1. Symlink, don't copy: `plugins` -> `~/.claude/plugins` (the whole dir: cache, marketplaces, registries), plus `skills` and `CLAUDE.md`. Per-file symlinks drift; the user wants everything in sync from one source.
2. Keep the seatbelt dir's own `settings.json` (it carries the seatbelt routing). Regenerate its `enabledPlugins` from the registry so every installed plugin is on:
   ```python
   n = json.load(open(HOME + '/.claude/plugins/installed_plugins.json'))
   s['enabledPlugins'] = {k: True for k in n['plugins']}
   ```
   Rerun this after every plugin install; the symlinked registry updates but the enable map does not.
3. Symlinked layers (CLAUDE.md, skills, plugin dirs) hold no plugin secrets; MCP keys live in `~/.claude.json`/settings, which stay per-config.

## Syncing plugin sets between hosts
1. Diff the key sets of `~/.claude/plugins/installed_plugins.json` on both hosts first; aim for an identical set, both directions.
2. Public marketplaces: `claude plugin install <name>@<marketplace>`.
3. Private-repo marketplaces on a host without GitHub auth (install fails): copy `plugins/marketplaces/<mkt>` and `plugins/cache/<mkt>/<plugin>` over ssh with tar, then merge the entries into the target's `installed_plugins.json` and `known_marketplaces.json`, rewriting `installPath`/`installLocation` home prefixes (`/Users/ayush` <-> `/home/ubuntu`).
4. Regenerate `enabledPlugins` in each host's seatbelt `settings.json` (step 2 above).
5. tar from macOS: set `COPYFILE_DISABLE=1` and pass `--no-xattrs`, or GNU tar on Linux prints one `LIBARCHIVE.xattr.com.apple.provenance` warning per file and floods the tool output.

## Verify live, per host
Run a real seatbelt `claude -p` on each host asking whether specific newly synced skills (e.g. `sherlock:sherlock`, `superpowers:test-driven-development`) are available. Registry equality alone does not prove the session loads them.

On the Linux host the seatbelt headers sit in `.bashrc` as `seatbelt_headers=$'x-tfy-api-key: ...\nx-maat-token: ...'`. Extract with a regex on that assignment and replace the literal `\n` with a real newline; extracting by line number breaks when `.bashrc` shifts and yields a 401 "Invalid token" that looks like an auth failure but is a probe bug.
