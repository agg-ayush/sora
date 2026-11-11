# Adopt, adapt or build

Use when a pipeline stage, skill or workflow needs improving and the question is whether something published already does it, or when one named third-party tool is proposed for our architecture. The owner expects adopt-or-adapt to be checked before anything is built from the ground up, and "checked" means the internet, not only what is installed.

- Part A: wide survey plus hands-on scoring (many candidates, pick a winner).
- Part B: vetting one named tool against our architecture.

Both parts get their candidate lists from the research tiers in `SKILL.md`. Research tiers only produce the list: every shortlisted candidate is still trialled hands-on.

## Part A: survey and trial

1. **Pause any build in flight.** If a home-made version is already dispatched when this question comes up, stop it before it writes and confirm the repo is untouched.
2. **Write the requirements first**: 4 to 6 numbered criteria (what it must cover, generic versus project-specific, runs headless in the pipeline, licence, maturity, cost proportionate to the task). Every survey row and trial is scored against them.
3. **Research pass.** Run the standard tier first to get a candidate list in minutes. Go to the deep tier only if fewer than about 60 candidates came back or any bucket has fewer than 10. Require the report to include the tree-walk results and the expected-but-absent list as inputs to the buckets.
4. **Survey wide, in buckets, in parallel subagents.** Typical buckets: official marketplaces and big collections, frameworks for the whole stage, narrow lenses or critics for one gap. Aim for 60 to 100 candidates. For each: read the actual prompt, skill or command files (a README is not evidence), verify the repo with `gh api`, flag NOASSERTION, no licence and archived repos; mark anything unverified. Each bucket ends with its own top 5.
5. **Trial every shortlisted candidate hands-on**, not a token top 3. If budget forces fewer, the report lists each shortlisted tool not run and why. A paper survey that ends with "copy the patterns and build our own" is not an answer to an adopt question.
6. **Score by retrodiction on real past work:**
   - Pick a historical task whose downstream outcome is known (later review findings, bugs, rework). Build an answer key from those outcomes, classify each item (design-level gap, implementation slip, weak test, noise) and score only the classes the tool is meant to catch.
   - Run each candidate blind: scratch clone at the task's base commit, the original task text only, never the answer key or the artifacts it is compared against. Install project-scoped (`--plugin-dir`, project `.claude/`, isolated `CLAUDE_CONFIG_DIR`), never into the user's global config. Approved model route only. Record wall time, turns and cost per run.
   - Cap metered spend in the brief (spend rules in `SKILL.md`) and end the report with a spend table.
   - Run long trials under `caffeinate -i -t <seconds>` with a per-run timeout (for example 1200 s).
   - Score each item FULL, PARTIAL or MISSED from what the output actually surfaced: weighted = (F + 0.5 P) / N. Score our current process on the same key as the baseline.
   - Evaluate two modes separately: the tool **alone** (could it replace ours?) and **added to the baseline** (marginal gain). A full framework can lose on replacement while a narrow reviewer wins as an add-on.
   - Record real defects outside the key and false positives; a tool that finds a build-breaking bug the key missed matters.
   - Confirm the best 2 or 3 on a second historical task before recommending anything.
7. **Write results to disk as you go**: `answer-key.md`, `baseline-score.md`, one `score.md` per trial, a `stats.tsv` of wall, turns and cost, then `REPORT.md`. Long agents get interrupted (host sleep, provider stalls); per-trial files let the next agent resume. A replacement brief names the files already on disk and the exact remaining steps.
8. **Report BLUF**: adopt, adapt or build verdict per stage; the score table (alone, combined with baseline, best combination, cost); what nothing catches; licence and integration notes; candidates not trialled and why.

Rules for tooling that shapes a pipeline stage:

- Keep adopted or written tooling generic across repos and task types. Recurring failures from one project become labelled anti-pattern examples, never mandatory checklist items.
- Prefer tiered depth (light versus full, optional modules triggered by the task) over sending every task through every step.
- Copy text only from permissive licences; for NOASSERTION repos take ideas, not prompts.

## Part B: vetting one named tool

1. **Research the real architecture, not the pitch.** Is it a replacement runtime or a layer over the same CLIs (Claude Code, Codex) we already use? Does it manage its own state and workers, or attach to arbitrary external state? This decides whether "adopt wholesale" is coherent before any feature comparison.
2. **Judge against our constraints, not a feature checklist.** For each advertised capability: do we already have an equivalent, and if not, is the gap real enough to pay the switch cost? Give an honest yes or no when asked directly.
3. **Prefer borrowing the one pattern** when only one feature is valuable and the rest would duplicate or conflict with our orchestration (state ownership, lifecycle). Port just that mechanism.
4. **Verify any claimed integration by running it against the real system** before writing "supports Y" in a doc. A README describing behaviour in its own terms does not show it interoperates with our state: install it, point it at real sessions or data, check. The same applies to our own claimed capability ("we already have dependency graphs"): exercise the mechanic on a scratch board, repo or branch, not from `--help` text. A primitive can exist while the convention for using it does not, and that is a closable gap.
5. **Separate bookkeeping from judgment.** A task-graph row per check proves a check was recorded, not that the model judged it well. For multi-check judge prompts validate returned check keys against the expected set, retry only the missing ones; fingerprint `(check_id, item_id, evidence_hash)` to measure verdict flips.
6. **Do not launder existing code into precedent.** Code already in the target repo is not evidence it works. If you have not read it closely enough to vouch for it, write "similar pattern at path:line, unverified".
7. **Ambiguous or empty `clarify` on a side-effecting decision** (install, clone, start a server): retry once, then take the reversible option (document or plan only) and say what you defaulted to and why.
8. **Clean up negative evaluations at once.** Kill any process the candidate started and remove the clone. If the verdict removes a tool reference from docs, remove it and bump that doc's own "last updated" line in the same pass.
9. **Fork or derivative of our own system.** Find the fork point first (`git log --reverse --oneline | head -1` on their clone, then `git log --after=<date>` on ours) so our later progress is not misread as their innovation or their bug. Categorise each hunk: identical or cosmetic, their edit of our content (improvement, lateral or regression), content they added that we lack, our content they lack (predates their fork versus deliberately dropped). Report at that granularity.
10. **Check referenced artifacts exist on both sides** before crediting a text addition. A forked prompt can describe a script that does not exist. Exists on both: a real doc improvement. Only in their fork: a real idea but porting the artifact is infra work. Neither: aspirational, do not rank it as proven.
11. **Verify claimed bug fixes by tracing control flow**, building the concrete failing scenario yourself. A claimed fix may not reproduce in our setup (irrelevant for us) or may expose a real bug in our base code. Verify claimed CLI behaviour with `<command> --help` or by running it.
12. **A positive verdict deploys to parity, nothing more.** Replace what the old system did on each host; do not add capabilities the old setup never had (sync crons, extra repos) just because the tool supports them. Propose extras separately.
13. **Swapping a model into an existing route:** list what the gateway actually serves (`/v1/models`), compare only models we can call at the same reasoning level, and check the wire protocol (routes driving the Claude Code CLI need an Anthropic-compatible endpoint; OpenAI-protocol-only models need a Hermes-native or Codex-style runner). Verify with a real completion through Hermes (`-m <alias>`), not just curl.
14. **Publish the outcome.** After verification, publish the intended PR or handoff artifact and report its real state. Merge or commit to main only where the user or repo policy authorises it.
15. **Strict-JSON output contracts:** build the report as a dict in code and serialise it with `json.dumps` instead of hand-typing escaped quotes.

## Prior verdicts (historical: re-verify against current releases before reuse)

- **beads** (task-graph tracker): not adopted twice. Our kanban backend already gives durable tasks, dependencies and claim locks; and a tracker guarantees a row per check, not good judgment of that check.
- **amux** (tmux session manager with dashboard and watchdog): not a replacement for the tier system. Its self-healing watchdog pattern was ported into our orphan reaper. Its dashboard only shows workers it spawned itself and cannot discover existing tmux sessions, so it is not a monitor for tier sessions; Telegram notifications are the mobile channel.

## Pitfalls

- Writing "tool X gives us Y" from the tool's own docs: that is a hypothesis until run.
- Recommending replacement of a working, deeply integrated system for a slicker feature list without checking the narrower "borrow one pattern" option first.
- Treating "layer over the same CLIs" as "compatible with our state model".
- Leaving evaluation installs, clones or processes behind after a negative verdict.
