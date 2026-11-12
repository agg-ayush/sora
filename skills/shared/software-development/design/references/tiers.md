# Tiers and triage

Every card gets one tier at triage. The tier sets the depth of every later stage.

## The three tiers

| Tier | Rule | What changes |
|---|---|---|
| none | Bug fix that comes with a failing test, pure refactor, test-only work, copy or config with no behaviour change | Skip grounding, design and design review. A bug fix still starts from its failing test (that run is the RED evidence) |
| light | One obvious approach, but the change touches at least one of: a state or transition, an async, concurrent or retry path, a persisted or shared contract, more than one consumer or surface | Short design: one approach paragraph, no alternatives. Review by the generalist plus the design-lens agent |
| full | More than one sensible approach where the wrong pick is expensive, a new subsystem, a cross-cutting change or task wording that leaves the approach open | Full design with 2 to 3 alternatives. Review by the generalist, design-lens and change-impact-bundle. The owner gets a design summary |

## Rules

1. "The exact fix is given in the task" is not enough for none. The fix says what to change, not what it touches. Triage greps for consumers of what the card names before deciding. More than one consumer means at least light.
2. Modules are added only when triggered.
   - `ui`: the card changes user-facing UI (new or changed control, layout, copy, state shown to a user).
   - `risk`: persistent data, migrations, external services, auth, money, legal or anything irreversible.
3. Raise, never lower. Tier 2 may raise the tier after reading the repo. Nobody lowers it.
4. Re-tier on NEEDS_CONTEXT or BLOCKED. If the implementer reports the task is bigger than designed, raise the tier, write the design stages that are now owed and update `process.json`.
5. When unsure, pick the higher tier. A visual mockup is an input to design, not a substitute: a card carrying one is at least light unless the change is a tiny obvious tweak.
6. The three-file threshold seen in outside research is a hypothesis only. The escape labels on code review findings test the tier rules; revise this file when they say a tier is wrong.

## Triage procedure

1. Read the card. List every named component, helper, field, status value, label and copy string.
2. Search the repo for each name (`search_files`, read hit lines only). Record the consumer count and whether tests mention the names.
3. Pick the tier from the table. Check the light triggers one by one: state, async or retry, shared contract, more than one consumer or surface.
4. Pick modules from the triggers above.
5. Record `triage: design=<tier> modules=<ui,risk|none> - <reason, consumers found>` on the card.

Done when the card carries the tier, the modules and the one-line reason with the consumer count.

## Writing process.json

Tier 2 writes `<card dir>/process.json` at triage, before any stage runs. Its presence with `"version": 2` turns the process gates on; absence means a legacy card with no gates.

```json
{"version": 2, "tier": "none|light|full", "modules": ["ui", "risk"], "kind": "feature|bugfix|refactor|test|copy|config", "design_path": "<absolute path or null>", "base_commit": "<sha>"}
```

- `tier` is the triage tier. `modules` is a list, empty when none.
- `kind` is the card type. A `bugfix` still needs RED and GREEN evidence even at tier none.
- `design_path` is the absolute path of `design.md` for light and full, `null` for none.
- `base_commit` is `git rev-parse HEAD` of the card base branch when the card starts. Guides and graphs older than it are stale.
- Write with `json.dump` to a temp file in the same directory, then rename, so the gate never reads a half-written file.
- On re-tier, rewrite the file with the raised tier and append a `metrics.jsonl` event: `{"stage": "triage", "event": "end", "round": 0, "detail": "retier <old> -> <new>: <reason>"}`.
- The first line of `design.md` is the fenced `design-meta` block. Its tier and modules must equal the ones in `process.json`.

## Legacy cards

A card that says `needs-design: yes` means full and `no` means none. It has no `process.json`. Run it on the old path with no gates.
