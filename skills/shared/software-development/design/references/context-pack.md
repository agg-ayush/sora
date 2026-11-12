# Context pack

Every session starts from a context pack instead of rediscovering the repo, with rules that keep the pack from biasing judgement.

## What each role gets

| Role | Gets | Does not get |
|---|---|---|
| Design author | Card, grounding output, system guide, graph and symbol tools | n/a |
| Design reviewers (generalist and subagents) | Card, design doc, binding inputs, system guide, graph and symbol tools | Previous review verdicts. The author's reasoning outside the doc |
| Implementer | Approved design, test-impact map, system guide, graph and symbol tools | Review transcripts |
| Code reviewers | Diff, design, verification table, system guide, graph and symbol tools | The implementer's own notes on why it is right |

Binding inputs (the task, standing decisions and files the task names) go to every role in full.

## Pieces

**System guide.** One file per repo (AGENTS.md or CLAUDE.md, or a harness-kept guide for a product repo) with architecture, module map, conventions, test and build commands and non-obvious gotchas. It records the commit it was last verified at. When a finding traces back to a wrong or missing guide entry, the escape analysis updates the guide.

**Knowledge graph (graphify)** for navigation: where things live and what connects to what. Binary: `graphify` when it is on PATH, otherwise `~/.local/bin/graphify`. Commands (all read `graphify-out/graph.json` in the current directory unless `--graph <path>` is given):
- `graphify extract <repo> --code-only`: build the graph once per repo (local AST, no API key).
- `graphify update <path>`: incremental re-extract in a card worktree (no LLM needed). Run it before querying when the worktree is ahead of the graph.
- `graphify query "<question>" [--dfs] [--budget N]`: traversal for a question, for example "what calls the archive helper".
- `graphify explain "<node>"`: plain-language summary of a node and its neighbours.
- `graphify path "<A>" "<B>"`: shortest path between two nodes.
- `graphify affected "<node>" [--depth N]`: reverse traversal for what a change to the node impacts.
- `graphify god-nodes [--top N]`: the most connected nodes (hubs to treat with care).

The CLI may print a version-mismatch warning on stderr; ignore it. If `graphify-out/graph.json` is absent, skip the graph and use search.

**Symbol tools (Serena)**, when available in the session: `find_symbol` for definitions, `find_referencing_symbols` for exact references, `get_symbols_overview` for a file's structure. Use them to confirm what the graph suggests.

## Bias rules

1. The pack is for navigation, not evidence. Every finding and every design claim about existing code cites `path:line` read in this session.
2. Consumer and call-site lists are confirmed by grep. Graphs miss string references such as selectors, copy, test files and dynamic imports, which is where missed consumers hide.
3. Reviewers write their own list of likely failure modes from the card and the code before reading the design's rationale, so the design does not set their frame.
4. A guide or graph older than the card's base commit (`process.json` `base_commit`) is flagged stale. Stale entries are re-verified, not trusted.
5. The pack stays only if coverage holds: before wide rollout the trial card is rerun with and without the pack and compared on coverage, minutes and tokens.
