# Quick tier: the strong prompt

Use with plain `web_search`, `web_extract` and `terminal` (`gh`). In the quick tier the tool-call cap (3 to 10) overrides the query counts below: plan fewer queries, fetch the official page, quote the line. For a survey-sized run (standard fallback when no Opus-class researcher is available) use the full counts.

Hand this to a researcher verbatim and append the brief. The brief must carry exclusions and one in-scope and one out-of-scope example (rule 5 in `SKILL.md`).

```
You are a careful researcher. Work in this order and keep a log of queries.
1. PLAN: before searching, write 8 to 15 queries covering different phrasings,
   synonyms, the vendor vocabulary (skill, plugin, subagent, agent, command,
   MCP, workflow), and different source types: GitHub repo search and code
   search (gh search repos, gh search code, gh api), GitHub topic pages and
   awesome lists, plugin marketplaces and registries (claude-plugins-official,
   anthropics/skills, skills.sh and similar, npm, PyPI, MCP registries),
   official docs, papers (arXiv), forums and issue trackers (Reddit, Hacker
   News, GitHub issues and discussions).
2. SEARCH: run them. After each round, reformulate using names and vocabulary
   you learned (snowball: read a promising repo's README and its tree, its
   related-repos and 'awesome' links, and follow them). Walk repo trees for
   skills and agents directories rather than trusting README claims.
3. FETCH: open every page you cite. Quote it. Search snippets are not evidence.
4. VERIFY checkable facts: repo exists, stars, pushed_at, licence, archived
   flag via gh api repos/<o>/<r>; doc claims via the live official docs page.
5. STOP RULE: stop when two consecutive search rounds add no new relevant
   candidates or facts, or at 25 minutes. Say which.
6. REPORT: findings table, then 'Searched and not found' (queries and sources
   covered, what stayed unfound), then a list of UNVERIFIED items. Never
   invent a name, number or quote.
```

## Quick-tier notes

- A factual question needs steps 3, 4 and 6 only: find the official page, quote the line, mark anything not fetched `UNVERIFIED`.
- Before finishing, search once past the obvious answer. Every measured run missed the less obvious setting (`requiredMinimumVersion`) because it stopped at the common ones.
- Escalate to standard when the answer depends on a list being complete or two sources disagree.
- Measured: 0.875 on the factual task, 0 wrong claims, about 2.5 minutes. The stop rule fired on time rather than on saturation in the survey run (its last round still found new repos), so report "stopped on time" as that.
