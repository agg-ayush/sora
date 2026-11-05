---
name: spike
description: "Test feasibility with disposable, runnable experiments."
version: 1.0.1
author: Hermes Agent (adapted from gsd-build/get-shit-done)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spike, prototype, experiment, feasibility, proof-of-concept]
    related_skills: [sketch, subagent-driven-development]
---

# Spike

Validate a specific unknown with a throwaway experiment before committing to a production build. This is not a production implementation, a research-only answer, or a full coding-agent campaign.

## When to Use

- The user asks to try, prototype, compare, or validate a risky idea before building it.
- Available docs or code cannot answer the feasibility question without an experiment.

If the user already uses `gsd-spike` and wants its persistent MANIFEST/commit workflow, use that instead. If the answer is in docs, research it; if feasibility is already established, implement rather than spike.

## Procedure

1. **Define the question and stopping rule.** For a broad idea, split into 2–5 independent Given/When/Then questions; test the highest-risk/idea-killing one first. For an already precise request, use one spike. Identify the observable result and at least one failure/edge case. For multiple spikes, show the ordered questions and align scope with the user before coding. Done when the success criterion is checkable.
2. **Research just enough to choose a probe.** Use `web_search`/`web_extract` for current external APIs, `read_file` for project code and docs, and `terminal` against the project's actual environment for dependency versions. Compare credible alternatives only where the choice affects feasibility. Done when the selected approach and its assumptions are explicit.
3. **Build the smallest observable experiment.** Put runnable code and `README.md` together in a disposable scratch directory by default (`$TMPDIR` or the session scratch path); use a repo-local `spikes/NNN-name/` only if the user wants the artifact in that repo. Prefer a CLI with recognizable input/output, then a tiny page or endpoint, then a focused executable test. Do not use a full coding-agent session, branch, or commit for a one-off validation; a short-lived `delegate_task` is acceptable for independent substantial variants. Avoid production scaffolding, but never hardcode credentials. Done when the real probe runs.
4. **Test the criterion and failure modes.** Run the probe with `terminal` and capture actual output, including an edge case or counterexample. Fix or investigate surprising behavior; no “works” verdict from a stub or single happy path. For alternatives, use the same fixture and compare measured evidence, not invented scores. Done when the claim follows from observed output.
5. **Record the verdict.** In the spike `README.md`, state the question, environment, exact run command, observations, constraints, and `VALIDATED`, `PARTIAL`, or `INVALIDATED`. Include what failed and a recommendation for the real build. An invalidated hypothesis is a successful spike. Done when someone else can reproduce or challenge the result.

## Existing Spikes / Frontier

When asked what to test next, inspect previous results for untested integration, assumed data handoffs, missing capabilities, and alternative paths to partial/invalidated outcomes. Offer 2–4 checkable candidates and let the user select.

## Pitfalls

- A spike that accumulates production features or commits has become a build; stop and re-scope it.
- A comparison needs the same question and comparable fixtures for both variants.
- Keep secrets in existing approved credential mechanisms, not test scripts or README files.

## Verification

- [ ] The actual runnable artifact answers the Given/When/Then question with observed output.
- [ ] At least one failure mode or limitation was exercised and recorded.
- [ ] The verdict and recommendation cite the experiment; any repo write was explicitly scoped.

Adapted from the GSD `/gsd-spike` workflow (MIT © 2025 Lex Christopherson, https://github.com/gsd-build/get-shit-done).
