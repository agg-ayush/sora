# Doc authoring and style rules (this user's Google Docs)

Authoring discipline for docs written for this user. Mechanical CLI pitfalls
live in SKILL.md and the other references; this file is the content/style
class rules.

## Citing code (proposals, scoping docs, RFCs)

- Read the actual file/line range before quoting. Never paraphrase what a
  prompt or function "effectively says" and present it as a quote — a caught
  fabricated quote is a hard correction, not a stylistic nit.
- Attach a GitHub permalink to every code citation, not a bare `path:line`:
  `git rev-parse HEAD`, build
  `https://github.com/<org>/<repo>/blob/<sha>/<path>#L<start>-L<end>`, fold it
  into the citation text so every claim is one click from its source.
- Inline external links (a mentioned tool/repo) directly next to the name —
  `beads (https://github.com/...)` — not as a bare parenthetical.

## Bug/issue handoff reports (for another dev to investigate)

Bare confirmed facts only:

- State the issue + exact evidence: affected file/lesson/id, the missing/wrong
  artifact, a verbatim timestamped log extract. Link the source (job log path,
  CloudWatch stream, PR) so the recipient can pull the rest.
- Cut: root-cause theorizing beyond what's confirmed (reads as guessing),
  domain facts the team already knows, aggregate counts from broad heuristic
  scans unless verified against the actual data model (a raw file-count
  comparison can look like a trend but just reflects which interaction types
  legitimately don't emit that artifact), and framing/explainer/caveat
  sections.
- If an earlier draft over-explained, recreate clean via `docs create --file`
  and delete the old one — don't patch with `docs update`.

## Access/credential handoff docs

Each section: heading plus a few short bullets — what the item is and how it
is used with what exists today.

- No build proposals (tunnels, security-group rules, setup steps) unless
  asked; that reads as unapproved scope.
- Cut negative clarifications and status padding; that nuance goes in chat.
- Use native Docs styling (heading + bullets), not dense paragraphs.
- Never write a live secret value into a Doc even on direct request — a Doc is
  a shareable surface and a leaked link is a breach. Write the secret-store
  location and exact fetch command, with a one-line why.
- Operator/runbook docs reference only shared-access resources (AWS account,
  repo, API) — never local helper scripts, cached token files, `~/...` paths,
  or "on the ops box" wording teammates can't run.
- "Make it external facing" = edit the SAME doc in place to remove local-only
  and internal tooling. A second audience-rewritten doc doubles the surface
  and throws away content the user wanted kept.
- API inventories: one pipe table per section, same columns everywhere
  (`Endpoint | Auth | What it does`), one row per endpoint; never fold a pair
  (activate/deactivate) into prose while other sections are tables. Close with
  a short Notes section. State plainly which route groups were left out and
  why; never imply coverage not enumerated from source.
- Add a section by editing the local markdown source + tab-scoped `docs write --replace --markdown --check-orphans` only when comments permit it, verified with `docs structure` — a
  positional insert into a formatted doc orphans text from its heading and
  collapses code-block line continuations.

## Decision-doc style

- Decision bullets state the reason as a compressed fragment riding the main
  clause ("no shared component to take down every candidate at once"), not a
  full "because X" sentence. Clip every stray "because"/"since"/"so that it"
  tail before pushing the doc.
- Every "today the system does X" / before-vs-after claim is an independent
  code-behavior assertion: grep/read the actual code before writing it. Don't
  infer current behavior from the feature's name, from narrative sense, or
  from an earlier design conversation. When the user flags one claim and says
  audit "all of it", that is a full-sweep instruction — verify every "today X"
  line and report which held and which didn't.
- Re-derive technical bullets from the actual settled decision trail, not
  memory (e.g. a per-OS tool split collapsed to one tool's name loses half the
  decision). Drop speculative pre-verification hedges once the thing has been
  verified, and keep a fact in one bullet — cut the repeat from the other.

## Long-running decision/tracking docs

- Group decisions under thematic `###` subheadings, never one flat numbered
  list — a flat list is unscannable past ~10 items and loses the area signal.
- Keep "Options considered" separate from "Decisions"; preserve
  rejected-option detail in internal working docs (distinct from a
  customer/share-ready doc, which gets filtered down).
- Re-group on each substantial addition — insert new decisions under their
  theme rather than appending to the bottom.
- Write decisions to the doc as they settle, not in a batch at the end; the
  tracking doc is the source of truth built in real time.
- State decisions as consensus facts, not attributed quotes — attribution
  reads as meeting-minutes noise once a point is a settled team decision.
- Leave a decision explicitly "Open" (candidates + tradeoffs in a table) when
  the user wants to trial options; don't force-close it.
- Once "Next" items ship, rewrite the section from scratch as the real
  forward decisions — stale build-todo bullets tell the reader nothing.
- When enriching with rationale, keep the concrete anchors (file:line, exact
  field/event names, config values, vendor call names) — don't trade specifics
  for narrative. Don't impose a formal external label (ITD, RFC, spec) on an
  internal working doc unless the user uses one.

## Matching an existing tab/doc's format

Pull the reference tab's rendered text first (`gog docs cat --tab "<name>"
<docId>`) and copy its real structural pattern before writing anything — don't
guess from the doc's title or reuse your own template. The pattern is usually
a short label (one or two words) alone on its own line, then terse plain
statements underneath — not a question-phrased heading or a mini-essay title.
Re-render with `docs cat` and compare side by side before handing back the
link.
