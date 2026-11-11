# Tier evidence: what was measured

Source: a hands-on trial of 13 research setups on two tasks. Task 1 was a prior-art survey with a recall key (4 tier-1 and 10 tier-2 tools for "review designs and plans before implementation"). Task 2 was a factual docs question scored against 8 claim items. One run per tool and one blind LLM rater, so a one-item difference is noise. The robust findings are the failures and the gaps shared by every run.

## Routing summary

| Depth | Best measured option | Result |
|---|---|---|
| Quick | `web_search` + `web_extract` + `gh api` with the strong prompt (`quick-prompt.md`) | Task 2: 0.875 in 149 s, 0 wrong claims, 21 of 22 quotes verbatim. Task 1: 3 of 4 tier-1 tools, missed the best one |
| Quick alternative | Parallel Responses `high` (about USD 0.25) or `medium` (about USD 0.05) | 0.875 in 107 s, or 0.81 in 37 s. One call, no tool control |
| Standard | One Opus-class Claude Code researcher with the ledger method (`evidence-ledger-method.md`) | Only run to find 4 of 4 tier-1 tools. 49 candidate rows, 0 non-existent repos, stars and licences checked, about 11 minutes, USD 2 to 4 |
| Deep | Sherlock fan-out + Parallel Task `pro` or `ultra` + standard verifier (`deep-tier.md`) | Sherlock had the widest unique recall (47 relevant repos, 29 found by no other run); Parallel `ultra` stars matched GitHub on 33 of 33 rows checked |

Caveat on the standard result: it ran on Opus while the plain and Sherlock runs used Sonnet, so model strength and method are confounded. The plain prompt on Opus was not tested.

## Trial scores

| Setup | T1 tier 1 | T1 tier 2 | Repos listed | Fabricated repos | T1 wall s | T2 score | T2 wrong claims |
|---|---|---|---|---|---|---|---|
| Sherlock (14 beads, spot-check) | 3/4 | 5/10 | 83 | 0 | 582 | 0.81 | 0 |
| Plain web_search + strong prompt | 3/4 | 4/10 | 60 | 0 | 735 | 0.875 | 0 |
| Evidence-ledger method, standard (Opus) | 4/4 | 4/10 | 49 | 0 | 676 | 0.875 | 0 |
| Evidence-ledger method, deep (T1 only) | 4/4 | 4/10 | 61 | 0 | 941 | n/a | n/a |
| Parallel Task core | 2/4 | 2/10 | 26 | 0 | 431 | 0.81 | 1 |
| Parallel Task pro | 3/4 | 4/10 | 20 | 0 | 657 | 0.875 | 0 |
| Parallel Task ultra | 3/4 | 3/10 | 36 | 0 | 1002 | 0.81 | 0 |
| Parallel Responses low | 3/4 | 2/10 | 19 | 0 | 36 | 0.44 | 2 |
| Parallel Responses medium | 2/4 | 1/10 | 28 | 0 | 71 | 0.81 | 0 |
| Parallel Responses high | 1/4 | 1/10 | 26 | 0 | 81 | 0.875 | 0 |
| Perplexity sonar-deep-research (TrueFoundry) | 2/4 | 2/10 | 31 | 0 | 147 | 0.81 | 0 |
| OpenAI gpt-5-search-api (TrueFoundry) | 0/4 | 0/10 | 4 | 0 | 21 | 0.44 | 2 |
| GPT Researcher deep | 1/4 | 3/10 | 18 | 0 | 1004 | 0.44 | 0 |
| Union of all 13 runs | 4/4 | 5/10 | 294 | 0 | n/a | n/a | n/a |

Task 2 detail: every run scoring 0.81 or better agreed on the answer, and every run missed `requiredMinimumVersion` (the item that caps scores at 0.875) because nobody searched past the obvious settings.

Metadata checks: runs that used `gh api` matched GitHub on every row checked. Parallel core and ultra took stars from `api.github.com` pages and stayed within 10 percent. Runs that marked stars or dates UNVERIFIED were honest, not wrong. gpt-5-search gave garbled metadata. No run invented a repo; the wrong-fact risk sat in capability and relevance claims.

## What each tier still misses

- **Quick:** one pass and no discovery depth. It missed the best tier-1 tool on Task 1 and the non-obvious setting on Task 2. Escalate when the answer needs a complete list.
- **Standard:** 6 of 10 tier-2 tools missed. Narrow tools inside large repos need the tree walk and the expected-but-absent probe, which is why both are in the method.
- **Deep:** even the union of all 13 runs missed 5 of 10 tier-2 tools (flow-next, correctless, ECC change-impact, an architecture-critic file in the official plugin marketplace, expect-the-unexpected). They sit inside large repos or as one narrow file, and no run reported them as gaps. Without the tree walk, deep adds volume, not coverage.

## Scored poorly: do not default to

- Parallel Responses `low` and TrueFoundry `gpt-5-search-api`: misread the brief (design review as UI design), near-zero recall, wrong claims.
- GPT Researcher: slow (3887 s with failed reruns), needed patches, truncated reports.
- Perplexity `sonar-deep-research`: low recall, and the vendor lists the model as retired even though the gateway still served it. Do not build on it.
- OpenAI and Gemini deep-research models were not run (no key or no model on the gateway). Exa, Tavily, Linkup and similar were surveyed only.

## Risks to remember

- Single key per task and one rater: confirm a finalist on a second task before hard-coding it.
- The ledger verifier checks internal consistency, not truth.
- Sherlock cost and tokens cannot be metered per run on the Seatbelt route; its protocol is heavy (beads and many dispatches).
- Vendor benchmark claims are vendor-run, not independent.
