# Comparing LLM models on published benchmarks

Use when asked "X vs Y benchmarks", "which model is better for coding/agents", "other models near X's cost", or before proposing a model/route change.

## Procedure

1. Pull three source classes in parallel and register each in a citation ledger as it arrives:
   - Vendor launch pages / model cards for each model (their own tables, footnotes, effort labels).
   - An independent evaluator's pages (e.g. Artificial Analysis comparisons, index announcements, launch articles with cost per task).
   - A benchmark owner's leaderboard or third-party runner (e.g. Vals for Terminal-Bench, with $ per task).
2. `web_extract` the comparison pages; search snippets and blog aggregators often mix effort levels or copy vendor numbers without saying so.
3. Build ONE table from a single evaluator, matched by effort level (high vs high, max vs max). Put other harnesses' numbers in prose, labeled as a different harness. Always include the user's current default as the baseline column.
4. Report quality AND cost-per-task AND tokens-per-task together. Identical per-million-token prices can still mean several-times different bills because token usage differs; tokens-per-task is the mechanism, say it.
5. Read vendor footnotes for effort-level reversals (higher effort scoring lower) and evaluation caveats (safety fallback, pre-release build). These matter more for agent routing than the headline score.
6. When asked for alternatives near a cost point, list models from the same cost-per-task table sorted by cost with their score; flag any that are cheaper AND higher-scoring.
7. Add an access row for each candidate: current provider/gateway, a new account, or not yet released. Check the gateway's actual model catalog before asserting access (see Gateway probing below). Keep unavailable models only if the user explicitly asks for future options, clearly separated from today's usable choices. Never substitute a similarly named variant for a requested model, and compare the named effort level consistently.
7a. When the user cites a past bad experience ("too expensive / too slow"), investigate its cause before extrapolating: compare the actual route, effort, token usage, and any premium speed mode against the successor's current standard route and price. Do not infer pricing from a model-name suffix or invent a context-window variant; use the exact catalog identifier.
7b. Measure latency live on the gateway for the shortlist (TTFT and total time on a streamed ~500-token answer). Published tokens/sec is the native API; a gateway route can buffer the whole stream, which makes the model unusable for interactive sessions even when one-shot use is fine.
8. End with a recommendation framed as a matched pilot on the user's real workload; never change model routing on benchmarks alone, and state that no routing change was made.

## Gateway probing (TrueFoundry-style OpenAI-compatible gateway)

- Resolve the **actual configured provider's** inference base URL and query its documented `/models` endpoint, if available. On a TrueFoundry-style OpenAI-compatible route the inference base URL commonly ends in `/api/llm/api/inference/openai/v1`; other `/models` paths can return HTML with HTTP 200. Verify a JSON model list, not status alone.
- Catalog entries may omit price/context data; check the provider's current price and route billing separately before comparing models.
- Use exact IDs from that catalog. A prefixed route and an unprefixed ID can differ in access; an auth error on one route does not prove every route lacks the model.
- For latency, measure timestamp of the **first SSE content event** and completion on a streamed, capped test response, using approved credentials without printing tokens or placing them in shell history. `curl -w time_starttransfer` alone may time response headers, not the first token; do not label a route buffered on that metric alone.
- Use a streaming client that timestamps parsed SSE content events. Keep prompt and max token cap identical across compared routes.

## Pitfalls

- Never mix scores from different harnesses or evaluators in one table row; same benchmark name with a different scaffold gives different numbers.
- Never mix composite-index versions: an evaluator rescales on a new index version (a model's score can drop 10+ points), so label the version and keep one version per column.
- Label composite indexes as composite scores, not pass percentages.
- Report launch/intro discounts with their end date and the post-discount price; a temporary discount can flip the cost ranking.
- Cost per composite-index task and cost per agentic task (long terminal runs) can rank models oppositely because verbose models burn more on long runs; for agent routing weight the agentic cost.
- Tag vendor-reported numbers as vendor-reported; vendors pick favorable effort settings and baselines.
- Model-group/provider routing changes need explicit user instruction; a benchmark win is not that instruction.
- If a gateway `/models` probe fails on auth, report model access as unconfirmed, not as unavailable.
