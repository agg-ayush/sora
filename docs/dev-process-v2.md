# Tier-2 dev process v2: design-led mini lifecycle

Status: live for new cards on both hosts. Decision: dec-702096732c (supersedes dec-555511b179). Cards without a `process.json` (version 2) run the legacy flow.

## Bottom line

Every card gets one tier at triage (none, light or full) and that tier sets the depth of every later stage. The approach is decided and reviewed only at design. The design is a decision-level guidebook: what to build, the interfaces and states, the tests that prove it and what the implementer may decide alone. Implementation follows it test-first, with the failing run enforced by a hook and a plugin gate rather than by prompt wording. Code review checks two things only: did the code follow the design and is it good code. A real design defect found later goes back to design as a scoped amendment instead of being argued in code. Every finding is labelled as a design escape or not, so the process measures itself.

Owner touchpoints: merge approval (unchanged), a short summary of each full-tier design for information, and an escalation only when a design amendment changes scope.

## Evidence this rests on

| Source | Finding used here |
|---|---|
| Audit of 34 cards, 766 code-review findings (`~/.hermes/cache/scratch/design-audit/REPORT.md`) | 61% design-stage gaps, 27% weak or missing tests, 11% implementation slips, 27% reviewer noise; later rounds mostly caused by earlier fixes; cards that skipped design looped most |
| Design reviewer trial, two cards (`~/.hermes/cache/scratch/adopt-research/REPORT.md`) | State-transition lens plus change-impact bundle lifted design-stage coverage from 0.37 and 0.33 to 0.63 and 0.44; full frameworks did not beat the baseline; runtime and real-browser behaviour is caught by no design reviewer |
| Dev-process research v2 (`~/.hermes/cache/scratch/dev-process-research/REPORT.md`) | Automated reviewers are scoped away from approach; test-first wording alone raised agent regressions (6.08% to 9.94%) while a test-impact map cut them to 1.82%; mutation scores are a weak signal; design-cost recovery is unproven, so tiers and measurement are required |
| Validation of the built system (`~/.hermes/cache/scratch/process-v2/validation-design-review.md`) | One-session design review with subagents: card 1 0.609, card 2 0.413 combined with baseline (bars 0.58 and 0.40); the system guide gave design reviewers no coverage gain at +59% wall time |

## Stage map

| # | Stage | Who | Input | Output | Gate (enforced in code) |
|---|---|---|---|---|---|
| 1 | Triage | Tier 1 (rule plus a brief consumer grep) | Card text | `design: none, light or full` plus modules (UI, risk); tier 2 writes `process.json` | `process.json` v2 turns the gates on |
| 2 | Grounding | `feature-dev:code-explorer` subagent inside the design author session | Card, repo | Existing patterns, consumers and tests with file:line; `evidence/test-impact.txt` | Citations present |
| 3 | Design | Opus author | Card, grounding | Design doc per contract | Pre-check script passes (plugin refuses review otherwise, no round used) |
| 4 | Design review | One Opus session, reviewer agents as parallel subagents | Design doc, card, binding inputs, repo | Verdict plus required tests, other findings and card-rule conflicts | Max 3 rounds (plugin cap); approved before stage 5 |
| 5 | Tests first | Implementer | Design test table, test-impact map | New or changed tests, saved RED run | Red-gate hook blocks source edits until RED exists |
| 6 | Implementation | Sonnet implementer, fresh context | Design, tests | Code, saved GREEN run, status | Status is DONE or DONE_WITH_CONCERNS |
| 7 | Mechanical gates | Scripts | Branch | Lint, types, impact-scoped regression run, real-browser run (UI) | All pass |
| 8 | Code review | One Opus session, conformance, quality and mutation agents as parallel subagents | Diff, design, verification table | Conformance and quality verdicts, labelled findings | Plugin refuses review without RED and GREEN evidence |
| 9 | Fix loop | Implementer round 1, Opus later | Accepted findings | Fix commits, each starting from a reproducing test | Max 3 rounds (plugin cap) |
| 10 | Merge | Owner | PR, e2e on deployed env | Merged PR | Owner approval |

## 1. Triage and tiers

| Tier | Rule | Stages that change |
|---|---|---|
| None | Bug fix that comes with a failing test, pure refactor, test-only work, copy or config with no behaviour change | Skip 2 to 4; bug fixes still start from a failing test (the RED run) |
| Light | One obvious approach, but the change touches at least one of: a state or transition, an async, concurrent or retry path, a persisted or shared contract, more than one consumer or surface | Short design (approach paragraph, no alternatives); lens reviewer only |
| Full | More than one sensible approach where the wrong pick is expensive, a new subsystem, a cross-cutting change, or task wording that leaves the approach open | Full design with 2 to 3 alternatives; lens plus change-impact bundle; owner gets a design summary |

Rules:
- "The exact fix is given in the task" is not enough for none: the fix says what to change, not what it touches. Triage greps for consumers of what the card names before deciding.
- Modules are added only when triggered. UI module: the card changes user-facing UI. Risk module: persistent data, migrations, external services, auth, money, legal or anything irreversible.
- Tier 2 may raise the tier, never lower it. The implementer returning NEEDS_CONTEXT or BLOCKED because the task is bigger than designed re-tiers the card.
- Legacy `needs-design: yes/no` maps to full/none.
- The three-file threshold from the research is a hypothesis; the escape labels test it.

## 2. Grounding

The design author first launches `feature-dev:code-explorer` as a subagent: existing patterns to follow, every consumer and call site of anything that changes (found by search, marked changing or unchanged) and the existing tests that cover those paths. The author writes that test list to `evidence/test-impact.txt`; it is the test-impact map for stage 5.

## 3. Design contract (decision level, not line level)

Required sections for light and full:
1. Problem, goals, non-goals; requirements with ids (R1, R2), each testable.
2. Grounding summary with file:line citations and the consumer list.
3. Approach. Full: 2 to 3 real alternatives, the pick, why the others lose and assumptions with how each was verified. Light: one paragraph.
4. Behaviour model, only when there are states, async work or concurrent actors: states, transitions and what happens on failure, retry, cancellation, repeated or concurrent action, identity change and stale data.
5. Interfaces and data shapes.
6. Verification table: one row per requirement and per behaviour transition, with the test, its level, the observable asserted and the wrong implementation it must catch.
7. May decide alone (internal choices) and must escalate (anything contract-visible).
8. Build sequence, failure modes, rollback and open questions.

Optional modules: UI (surface states, per-control interaction contract, sizes that matter) and risk (failure-mode table, time budgets against measured upstream latency, idempotency, rollback with data effects).

Detail limit: name decisions, not code. A design longer than the code it describes has written the code instead.

The pre-check script verifies the design-meta header, section presence, that every requirement id appears in the verification table, path:line citations, placeholders and the 'Changes since review' section on revisions. A failed pre-check goes back to the author without spending a review round.

## 4. Design review

| Tier | Reviewers |
|---|---|
| Light | One Opus session: generalist pass by the session itself plus the `design-lens` subagent |
| Full | One Opus session: generalist pass plus `design-lens` and `change-impact-bundle` (everything-claude-code change-impact plus correctless red-team, testability and assumptions) as parallel subagents |
| Optional | ce-doc-review when the design rewrites many user-visible strings |

Rules:
- Every reviewer gets the full binding inputs (task, standing decisions, files the task names). Missing inputs produced identical false blockers in the trial.
- Findings carry a section, file:line evidence and a required correction; at most 7 blocking per round; unproven claims are tagged unverified.
- The merged verdict loses nothing: after the verdict block come `required_tests` (every missing test any agent named), `other_findings` (one line per agent finding not merged) and `card_rule_conflicts` (process or card-rule conflicts, outside the blocking cap). Full agent findings stay in `review/*.md` and the author reads them.
- The lens never marks a state, transition or consumer as covered without citing the test or file:line that covers it.
- Every non-blocking suggestion gets a written answer in the design (adopted or rejected with a reason). Adopted ones become acceptance criteria in the implementation brief.
- The lens includes a stale-test inventory: every changed literal, label and selector is grepped across unit and e2e tests and each hit is listed.
- Reviewers run read-only with a 20 minute cap and the host kept awake.

## 5. Tests first

- The implementer writes or changes the tests in the verification table first, runs them on the unchanged code and saves the failing output with `capture-evidence.sh red`. Only then does it edit source.
- Enforcement is mechanical at two points: the red-gate hook (a deterministic PreToolUse hook, no model call, fails open) blocks source edits until a failing RED file exists, and the plugin refuses code review without RED and GREEN evidence. tdd-guard was evaluated and not adopted: it makes a model call per edit, fails closed on errors and runs unpinned code from npm.
- Bash-based edits are not intercepted by the hook; the plugin gate is the backstop.
- Tests are immutable to the implementer once RED is recorded. Changing an existing assertion needs a written reason that the code reviewer checks.

## 6. Implementation and deviation route

- Fresh context per task. It ends with one status: DONE, DONE_WITH_CONCERNS (with the concerns), NEEDS_CONTEXT (what is missing) or BLOCKED (why).
- If the design is wrong or incomplete on anything contract-visible, the implementer stops and returns the section, the claim and what it observed. Tier 2 sends it to the design author for a scoped amendment with a change log; the amendment gets one review round; work resumes against the amended design. Internal choices on the may-decide list stay in code.
- An amendment that changes scope is escalated to the owner.

## 7. Mechanical gates

Lint, types and an impact-scoped regression run (the test-impact map plus anything new) run together; for UI-module cards a real-browser run of the changed flows follows once they pass. Heavy runs go one at a time per card. A green full suite is run once and rerun only after code changes.

## 8. Code review

- One Opus session, `/hermes-dev-process:card-review`, two verdicts:
  - Conformance (`conformance-reviewer`): anything in the design missing, extra or misunderstood; boundaries respected; every requirement has a test with a real assertion; verification promises kept; changed assertions justified.
  - Quality: pr-review-toolkit `code-reviewer` always, plus `silent-failure-hunter` (error handling changed), `state-transition-reviewer` (stateful behaviour), `type-design-analyzer` (new or changed types), `pr-test-analyzer` (test files changed at full tier) and `comment-analyzer` (substantial new comments), plus `mutation-probe` (at most 5 targeted mutants in a throwaway worktree, impacted tests only) to flag tests that cannot fail. Each runs only when its trigger applies.
- Approach preferences are out of scope and dropped. A defect with evidence that the design caused it is labelled design-defect and routed to the amendment route, not fixed ad hoc.
- Every finding needs file:line and the concrete failure it causes. Findings are severity-gated and deduplicated; only blocking ones start a fix round.

## 9. Fix loop

- Each fix starts with a test that reproduces the finding (RED), then the fix. Earlier evidence files move to `evidence/r<N>/`.
- Re-review covers the fix diff only.
- Round 1 uses the original implementer; later rounds move to Opus.
- Hard cap of 3 rounds per card (plugin-enforced); unresolved findings are parked in writing on the PR.

## 10. Merge

Unchanged: PR with problem and behaviour summary, e2e against the deployed environment, owner approval per PR.

## 11. Measurement

- Every code-review finding is labelled: design escape, implementation slip, weak test or noise.
- The plugin writes `start`, `end` and `refused` events to each card's `metrics.jsonl`; tier 2 adds amendment and gate events with `card_state.py`.
- `scripts/process_metrics.py` summarises v2 cards against the audit baseline (3.1 review rounds with design, 4.6 without) and gives keep or drop hints after 10 cards.

## Parallelism

Stages stay in order where one consumes the other's output. Inside a stage, parallel work runs as subagents of one session, not as separate sessions:

| Where | One session that fans out | Why |
|---|---|---|
| Design review | Opus session launches the lens and bundle agents in parallel, does the generalist pass itself, then merges | Each subagent reads the doc in a fresh context; one session is one review round for the plugin cap; far lighter on the host than separate processes |
| Code review | Opus session launches the conformance, quality and mutation agents in parallel, then writes the two verdicts | Same pattern as pr-review-toolkit |
| Mechanical gates | Lint, types and regression together; browser runs after | These are processes; heavy runs are capped per card |
| Measurement | Metrics events and the owner's design summary | Never blocks the card |

Subagent rules: each reviewer is an agent file with its own model setting and read-only tools (Write only for its findings file); each writes full findings to `<task-dir>/review/<agent>-r<round>.md` and returns a short summary; one failed agent is rerun once.

Host limit: kanban `max_in_progress` is host-wide and set to 4.

## Context pack and tools

| Role | Gets | Does not get |
|---|---|---|
| Design author | Card, grounding output, system guide, graph and symbol tools | n/a |
| Design reviewers | Card, design doc, binding inputs, graph and symbol tools | System guide (measured: no coverage gain, +59% wall time); previous verdicts; the author's reasoning outside the doc |
| Implementer | Approved design, test-impact map, system guide, graph and symbol tools | Review transcripts |
| Code reviewers | Diff, design, verification table, system guide, graph and symbol tools | Implementer's own notes on why it is right |

Pieces:
- System guide: `repo-guides/<repo>.md` in this repo (kept in the harness, not the product repo), with a `verified-at` commit.
- Knowledge graph (graphify, `~/.local/bin/graphify`) for navigation, copied into each card worktree (never linked) and updated incrementally.
- Symbol tools (Serena) for exact references and definitions.

Bias rules:
1. The pack is for navigation, not evidence. Every claim about existing code cites file:line read in this session.
2. Consumer and call-site lists are confirmed by grep. Graphs miss string references such as selectors, copy, test files and dynamic imports.
3. Reviewers write their own list of likely failure modes before reading the design's rationale.
4. A guide or graph older than the card's base commit is flagged stale and re-verified.

## 12. What this process still will not catch at design

Runtime state across identity or prop change, native browser behaviour and layout in bounded containers. Stage 7's real-browser run, the mutation probe and the stale-test inventory are the nets; the escape labels show how much gets through.

## Where it lives

| Piece | Path |
|---|---|
| Design skill (tiers, contract, review procedure, context pack, anti-patterns, pre-check) | `skills/shared/software-development/design/` |
| Tier-2 orchestration (stages 5 to 10, card state, legacy note) | `skills/tier2-orchestration/` |
| Triage | `skills/tier1-suborchestration/SKILL.md` |
| Reviewer agents and commands (`hermes-dev-process@hermes-setup`) | `plugins/hermes-dev-process/` |
| Gates, metrics events, graphify copy | `plugin/__init__.py` |
| Red-gate hook, evidence capture, metrics summary | `scripts/red-gate-hook.py`, `scripts/capture-evidence.sh`, `scripts/process_metrics.py` |
| Sign-sure system guide | `repo-guides/sign-sure-web.md` |

## Sources adopted

| Piece | Source | Licence |
|---|---|---|
| State-transition design lens | Our own `state-transition-reviewer` | Ours |
| Change-impact bundle | everything-claude-code (d2ef268), correctless (74f9ef3) | MIT, with attribution |
| Grounding explorer, quality agents | claude-plugins-official feature-dev, pr-review-toolkit | Apache-2.0 |
| Implementer statuses, plan detail rule | obra/superpowers | MIT |
| Red-gate hook | Ours (tdd-guard evaluated, not adopted) | Ours |
| Stale-test inventory idea | BMAD verification-gap lens | Ideas only (licence unclear) |
