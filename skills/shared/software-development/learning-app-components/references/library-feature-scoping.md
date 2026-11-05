---
name: library-feature-scoping
description: >
  Triage a customer/product feature request against @<org>/learning-app-components
  (or any headless React state-machine component library) before proposing a design or
  ETA. Use when someone asks "can the library do X" / "block/allow Y behavior" and the
  answer requires checking what the state machine and provider actually support today,
  where the library's responsibility ends versus the consuming platform's, and how to
  slot a new capability into the existing config-prop pattern without scope creep.
platforms: [linux, macos, windows]
version: 1.0.0
author: Hermes Agent
license: MIT
category: software-development
metadata:
  hermes:
    tags: [learning-app-components, feature-triage, library-scope, requirements, state-machine, react]
    related_skills: [library-update, library-release, one-three-one-rule]
---

# Library Feature Scoping

Use this when a customer or product request lands as "can the player do X" for
`@<org>/learning-app-components` (headless lesson-player library: XState
machines in `src/machines/`, public surface via `LearningPlayerProvider` +
`useLearningPlayer()`, render-prop components like `MediaControls`). The job is to
turn a vague ask into an honest, precisely-scoped answer — not to draft an
implementation plan on a guess.

## Procedure

### 1. Verify current capability before claiming anything, positive or negative

Never assert "we don't have X" or "there's no flag for Y" from memory or a single
`web_search`. Grep the actual source first:

- Config surface: `grep` the provider props interface (`LearningPlayerProviderProps*`
  in `src/context/LearningPlayerProvider.tsx`) for anything adjacent to the ask
  (`debugMode`, `playbackSpeedPreset`, `autoAdvance`, `showDismissButton`, etc.).
- Behavior: grep the relevant machine (`src/machines/lessonPlayerMachine.ts` etc.)
  for the event/guard that would gate the behavior (e.g. `SEEK_TO`, `NEXT_STEP`).
- Persistence: grep for `localStorage|sessionStorage|persist|storage` — this library
  has none today; don't assume otherwise, and don't assume it always will.

If the user pushes back with "don't we already have a flag for this" — that is a
direct signal to re-search with a more targeted pattern before repeating your prior
claim. Being wrong once is fine; repeating an unverified claim after pushback is not.

### 2. Draw the library-vs-platform boundary explicitly, every time

This library is a headless, single-lesson-instance component: no `userId`, no
storage, no concept of "other lessons." Anything that requires state to survive a
remount, span across lessons, or know who the student is is **structurally the
consuming platform's job**, not a missing feature here. Say this plainly rather than
letting the request's phrasing (e.g. "the video" vs "the lesson sequence") blur the
line. Concretely:
- Within-instance (ours): seek/timeline gating, popup-prompt lock, playback state —
  anything reachable from the current `LearningPlayerProvider` mount.
- Cross-instance (theirs): next-lesson navigation, resume-across-sessions, reviewer
  vs. student identity, anything that needs a backend.

### 3. Find the single choke point before proposing a design

This library funnels equivalent user actions through one function/action rather than
scattering checks — e.g. all seeks (`seekTo` user-facing and `internalSeekTo`
machine-facing) go through one `performSeek(time, internal)` in
`LearningPlayerProvider.tsx`. Locate that choke point for the behavior in question
before sketching an enforcement mechanism; it tells you exactly where a guard belongs
and what it must NOT break (internal/remediation seeks, restart-to-0, etc.).

### 4. Match the existing config-prop pattern for anything new

New capabilities are optional props on `LearningPlayerProviderPropsNew` /
`...PropsOld` with a stated default (see `playbackSpeedPreset`, `autoAdvance`,
`debugMode`, `showDismissButton`). Follow that shape — default value, JSDoc with
`@default`, plumbed through `useLearningPlayer()` — rather than inventing a parallel
config mechanism. If the capability needs data flowing in/out across sessions,
propose a callback (`onXxxCompleted`-style, matching `onPartCompleted` /
`onPopupPromptCompleted`) for the platform to persist, not a new architecture.

### 5. Scope discipline — implement exactly what's confirmed, nothing adjacent

When the user confirms a specific behavior ("just confirm this, don't introduce extra
stuff like a 5s buffer"), drop any unconfirmed polish you were about to propose —
even numeric-tolerance conveniences framed as "just implementation detail." If it
wasn't asked for, don't fold it into the design; name it separately if it's worth
raising, and only as a separate question, not a default.

### 6. When the user hands you labeled shorthand (a1/a2/b1...), answer in that same structure

If the user breaks their own feedback into labeled sub-points (e.g. `a1`, `a2`, `b1`,
`c1`...), respond point-by-point against those exact labels — don't dissolve them back
into flowing prose paragraphs. They will call this out directly ("can you simplify
this man?") if you restate their own structured input as narrative. Mirroring their
labels also makes it obvious which of their points you've verified vs. still owe an
answer on.

### 7. Settle the top-level behavioral branch before drilling into implementation shape

When a feature has a fork in customer-facing behavior (e.g. "block next-part
skipping" vs. "allow next-part but keep watch status"), resolve *which branch* before
asking about the internal data shape needed to support it. Don't front-load
persistence-payload or storage-schema questions ahead of the behavioral question they
depend on — the user will flag the ordering as backwards ("doesn't the customer
question of X come before Y?").

### 8. Don't design the technical contract when the user only wants to discuss spec

If the user says something like "I just want to discuss spec/behavior with you," stop
proposing payload shapes, emit triggers, or storage schemas — even if they feel like
natural next steps. Hold that design work until they explicitly ask for it. Jumping
ahead reads as "complicating this."

### 9. Verify a cited reference implementation by actually driving it, not just reading markup

When the user points at a live reference URL ("conceptually similar to this: <url>"),
don't stop at static DOM inspection — drive the actual interaction and compare against
alternate methods to find *where* a behavior is enforced:
- For custom range/slider components (Vidstack, Radix, etc.) that ignore plain
  `.click()`, dispatch a real pointer sequence to simulate a user drag:
  `pointerdown` at the start position → `pointermove` to the target fraction →
  `pointerup`, all with matching `clientX/clientY` from `getBoundingClientRect()`.
  A bare click or `.value =` assignment on these components is usually a no-op.
- To find *which layer* enforces a limit, compare two seek methods: set
  `video.currentTime` directly (bypasses the UI) vs. drive the on-screen slider via
  the pointer sequence above. If direct assignment sticks but the UI drag clamps
  (e.g. `aria-valuenow` pins below the dragged-to value), the block is a UI/interaction
  guard, not a tamper-proof media-layer one — call this distinction out, it affects how
  strict the customer should expect enforcement to be.
- Cross-origin iframes: `iframe.contentDocument` throws/returns null if genuinely
  cross-origin; a same-origin embed (common for a vendor's own demo page framing its
  own player) will expose the inner document directly — check before assuming you need
  a screenshot-only approach.

### 10. Don't re-ask questions the conversation already answered

Track what the user has already settled earlier in the thread (e.g. "review mode is
internal-only," "backward seeking is fine"). Re-raising a settled point as an open
question reads as not having listened — the user will call it out as "not a valid
question." Before listing open questions for the customer/team, scan back over what's
already been stated and drop anything already resolved.

### 12. Give a scoped effort estimate, not a full plan, until scope is confirmed

Feature-request triage output is: current-state summary (with grep evidence) →
library/platform boundary → a short list of *genuinely open* scoping questions →
a rough ETA range conditioned on those questions. Don't draft the implementation
plan itself until the open questions are answered — that's a separate step (see
`plan` skill once scope is locked).

When the ETA depends partly on the customer's own follow-through (e.g. they must
wire up storage on their end before cross-session behavior actually works),
split the commitment: state a firm date for the work you fully control (the
library-side change — implementation, config surface, callbacks), and make the
dependent piece's timeline explicit as *conditional on their input*, not folded
into the same deadline. Committing an EOD-style date without that split reads as
a promise you can't keep once the customer answers land late or their side isn't
ready — say "our side ships by X; the cross-session piece goes live once you wire
up Y" rather than one undifferentiated ETA.

### 18. When recommending a numeric storage/precision unit, check robustness against the axis that can change, not just "more precise"

When a customer decision involves what unit to persist (e.g. absolute seconds
watched vs. percentage watched), don't default to the more granular-sounding
option. Ask what happens to *each* candidate if the underlying content changes
later (video re-cut, length edited, slide replaced) — an absolute unit (seconds)
silently breaks if the reference dimension moves, while a relative unit
(percentage) doesn't. Recommend the option that's robust to that edge case, and
say why in one line ("percentage survives a video being re-cut; seconds does
not") rather than picking on raw precision alone.

### 19. Before designing a cross-session/persistence seam, check the platform's OWN integration contract docs — don't assume the library dictates the shape

When a feature involves data that must survive a remount, span devices, or be
handed off to the consuming platform (step 2's "cross-instance, theirs" case),
don't design the callback/prop shape unilaterally from the library's internal
model and present it to the customer as the interface. Check whether the
consuming platform ALREADY has a documented integration contract for exactly
this (e.g. a postMessage protocol, a `contentState` save/restore field, a
composition chain like "applet session" data flowing up through a renderer to
an integrator). If it does, that contract's shape is a real design constraint on
what we can emit — not a detail to reconcile after the fact.

Concretely, this surfaced when a customer casually mentioned "we have a
postMessage doc" and "here's how session data composes upstream" *after* the
scoping doc and even the implementation had already settled on a structured,
per-slide, two-channel payload (`maxWatchedPct` + `lastPlayheadPct` keyed by
`lessonId+stepId+partId`). Reading the docs revealed their protocol expects a
single OPAQUE string per contentId, stored/restored verbatim — a materially
different shape. Had this been checked during scoping (step 1, "verify current
capability" — extended here to "verify the CONSUMER's capability/contract too"),
the open questions to the customer would have been sharper from round one:
opaque-blob-we-own-the-format vs. structured-fields-they-compose, what key
they use to bucket per-embed state, whether they need a rollup summary field
(mirroring their own `contentSummary` pattern), and who owns blob
versioning — instead of surfacing after a design was already built and shipped.

**Action:** the moment a feature's persistence/callback seam crosses the
library→platform boundary (step 2), ask "does the platform have public
integration docs for this?" as a scoping question BEFORE proposing a payload
shape — the same discipline as verifying our own source before claiming a
capability gap, just aimed outward at the consumer's contract instead of
inward at our own code.

### 20. When compiling a list of open questions for the customer, re-run the library/platform boundary check (step 2) against the QUESTIONS LIST itself, not just against the feature's behavior

Step 2 draws the boundary for what we *build*. The same boundary applies to what we
*ask*. After a customer hands you their platform's integration contract (e.g. "we
store an opaque blob, you hand us data"), it's tempting to turn every seam in that
contract into a question — blob-vs-structured serialization, what key format they use
internally, whether they merge two of our channels into one object on their side,
how they version their own stored blob. These all look related to the integration,
but they're asking the customer to co-design their OWN renderer/storage internals
through our doc — not ours to ask. Keep only questions about our own emission
surface (what we send them, in what shape, whether we optionally add a field) and
cut everything that's actually us outsourcing our platform-design homework to them.

Concretely: of five integration questions drafted from a customer's own docs, four
were "how should your platform work internally" and got cut; the one that survived
("should we also emit a lesson-level rollup field") was the only one about what *we*
emit. If the user says something like "I think we're scope creeping, some of these
questions don't seem relevant" — that's the signal this filter wasn't applied. Redo
it: for each question, ask "is this about what we build/emit, or am I asking them to
design something on their side that's none of our business how they implement?" —
the latter gets cut, not softened.

### 21. When a subagent-driven diff cleanup pass finishes, treat it as a candidate to re-audit, not a completed pass

A "reduce diff size / strip churn" or "reduce comment noise" instruction dispatched
to a subagent will reliably converge on the easy subset (pure content-identical
reformatting, obviously-verbose comments) and leave the harder subset untouched
(reformatting mixed with one real symbol change, comments that need judgment).
Two things that repeatedly happened driving this loop:

- A first churn-cleanup pass collapsed only hunks whose collapsed text was
  byte-identical to main. The user found the SAME pattern in other files minutes
  later and had to point it out explicitly a second and third time before the
  audit was reframed as **statement-shape** normalization (rewrite every
  import/destructure/call-arg/object-literal to main's exact line-shape with
  the new/renamed identifier inline, even past print-width) rather than
  **pure-hunk** matching. `git diff -w` does not surface this gap — a
  single-line-to-multi-line reflow makes every added line "real" to a
  line-based diff regardless of whitespace-insensitivity.
- Fixing files the user pointed at, one at a time, reads as "half doing shit"
  even when each individual fix is correct — because it implies the same
  defect exists elsewhere and wasn't looked for. Once the user names a defect
  class (not just a specific file), the very next pass must audit the WHOLE
  diff for that class in one shot, not wait for each additional instance to be
  pointed out.

**Action:** when dispatching a diff-cleanup subagent, state the audit method
explicitly (statement-shape normalization, not pure-hunk matching) and require
it cover every changed file in the diff, not just previously-flagged ones.
When the user flags a second instance of the same defect class after a "done"
pass, don't defend the first pass's scope — immediately widen to a full-diff
audit at the correct level of generality. Full method + concrete example:
`references/diff-hygiene-churn-and-comments.md`.

### 22. Before handing a built feature to the human for manual QA, verify the demo/test-app actually exposes every new config knob

A feature can be fully implemented and gated correctly inside the library while
`test-app/demo.tsx` (or whatever the local manual-test harness is) still only
wires the OLD subset of props — the demo doesn't auto-track new provider props
just because they compile. Before saying "ready for you to test," grep the demo
for each new prop/callback name the design introduced
(`grep -c '<newPropName>' test-app/demo.tsx`). If any are missing, wire them the
same way a real integrating customer would consume them — actual toggles in a
settings panel, persisted values fed back in via seed inputs, callback payloads
rendered in a visible log panel — not just enough for the app to type-check.
Finding this gap only after the human sits down to test wastes a manual-test
round and forces a mid-review pause to build the harness.

### 23. Launch a manual-QA dev/demo server as an independently-tracked process, and know what its logs can and can't show

When a human is going to manually test a feature in the browser, the dev server
(Vite, etc.) must survive independently of whatever agent/session built the
demo — if it's started inside a coding-agent's own terminal/tmux session, it
dies the instant that session exits or is torn down, silently, with no error
surfaced until the human tries to load the page. Launch it as its own tracked
background process (e.g. Hermes `terminal(background=true)`) and verify it's
actually live (HTTP 200 + expected page title) before handing over the URL. If
it dies later (laptop sleep, an unrelated session teardown), just relaunch the
same way — this is routine, not worth an incident-style explanation.

Separately: a plain dev server's stdout is HTTP/module-transform logs only. It
has no visibility into in-browser application state (React state, a progress
log panel, an XState machine's context) — that only exists in the page's JS
runtime. If the human can't visually confirm a fast/off-screen UI event (e.g.
a completion event that fires and passes in under a second), don't try to
"check the server logs" for it — there's nothing there to check. Verify it the
way you'd verify any runtime behavior you can't watch live: trace the code
path, or point at/run the existing test that asserts that exact transition.

### 24. Scope verification effort to the blast radius of the edit, not a fixed checklist

Once a human is manually QA-ing a built feature via a live demo server, small
follow-up tweaks land constantly (move a panel, add a show/hide toggle, tweak a
label) — almost always confined to `test-app/demo.tsx` (or whatever harness file),
never touching shipped library source. Running the full `pnpm run test`/`build`
suite on every one of these is wasted cycles and doesn't match what actually
changed. For an edit fully contained to the test-app/demo harness:
- Verification = lint the touched file (`npx eslint <file>`) + a visual/functional
  check in the browser (HMR picks it up; confirm the specific behavior asked for).
- Do NOT run the library's test/build suite — it wasn't touched and can't regress
  from a harness-only change. State this reasoning explicitly if a generic
  "workspace has unverified changes" nudge fires (it will, repeatedly, since it
  can't tell demo-only edits from library edits) — re-explaining once establishes
  the pattern for the rest of the QA session.
- The moment an edit ALSO touches `src/` (shipped code), the full gate applies
  again — this shortcut is strictly for the harness/demo file, never for library
  source, however small the change looks.

### 25. When manual QA reports a live behavior bug, fix it repro-test-first — don't patch from a read-code hypothesis alone

A human manually clicking through the demo will find bugs that both the design
review and the automated `pr-review-toolkit` pass missed — these are exactly the
timing/state-interaction bugs that only show up under real sequencing (e.g. "I
captured a seed at 0:11, reloaded, and it resumed at 0:05 instead"). Don't jump
straight from a plausible code-read hypothesis to an in-place patch:

1. Form a hypothesis from reading the actual code path (which effect/guard/ref
   could produce exactly this symptom), but don't commit a fix on that alone.
2. Dispatch a fix session with a brief that requires it to FIRST write a test
   reproducing the exact reported repro steps (the same sequence the human just
   ran — watch past a specific event, capture/seed, reload, resume — not a
   generic version of the bug), confirm the test fails on current code, THEN
   diagnose the root cause against that failing test, fix it, and confirm the
   same test now passes.
3. Independently verify yourself before committing: read the diff, confirm the
   root-cause explanation holds up against the actual changed lines (not just
   the subagent's prose summary), and re-run the full suite + lint + tsc.
4. Report the root cause in one plain paragraph the human can sanity-check
   against what they observed, then hand the fix back to them to re-test the
   exact QA step that failed — don't just declare it fixed from the test.

This is the same "never trust a self-report" discipline applied to bug fixes,
not just feature builds — a subagent claiming "fixed" without a test that was
red-then-green on the exact repro is a claim, not evidence.

### 26. When orchestrating a Claude Code session for the design/implementation loop, don't treat its TUI context-percentage as proof of a routing failure

Claude Code's own status-bar percentage (e.g. "83%/200k") reflects the TUI's
*assumed* context window for whatever model name it happens to display —
often a `claude-sonnet`-style label even when the actual `model_provider`
routing (e.g. `fireworks`) is correctly sending every tool call to a
different model with a much larger real window (Kimi K3's 1M). A
high/climbing/stuck percentage by itself is cosmetic display noise, not
evidence the session is thrashing on premature compaction or that routing is
broken. Before switching `model_provider`/executor to "fix" this, confirm
whether the actual tool calls are misrouted (check call metadata / a trivial
probe), not just the label the TUI shows. Escalate a routing change only if
the calls themselves prove misrouted.

## Pitfalls (cont.)

- Assuming a dev/demo server started inside an agent's own session will
  outlive that session — it won't; launch it as an independent tracked
  background process for any human-facing manual QA.
- Trying to verify an in-browser runtime event (state update, log panel entry)
  from the dev server's process logs — the server has no visibility into
  browser-side application state; verify via code trace or an existing test
  instead.
- Running the full test/build suite on a tweak that only touched the
  test-app/demo harness — match verification weight to blast radius (lint +
  visual check suffices there; the full suite is for shipped `src/` changes).
- Patching a manual-QA-reported bug directly from a code-read hypothesis
  without first writing a test that reproduces the exact reported steps —
  write the failing test first, confirm root cause against it, then fix.

## Pitfalls (cont. 2)

- Reading a Claude Code session's TUI context-window percentage as proof of a
  routing failure — it reflects the TUI's assumed model/window, which can be
  wrong even when the real tool calls route correctly. Confirm via actual
  call metadata before treating it as a signal.
 (a spec, a BrainLift, a design doc — code
paths, file references, architecture debate, internal tooling labels), and the user
then says "I'm going to share this with the customer," treat that as a request for a
**different document**, not a lighter edit of the same one. An internal artifact and a
customer-facing decision doc differ in more than length:
- Cut every internal reference: file paths, function/class names, state-machine
  internals, architecture debate, methodology jargon (e.g. DOK layers, gate cards).
- Reframe from "what we investigated" to "what we'll build" + "what we need you to
  decide" — lead with behavior and options, not with the investigation that produced
  them.
- Turn open internal questions into a short list of customer decisions, each with
  concrete options and — where the codebase evidence supports it — an explicit
  recommendation, not a bare menu.
- Match visual weight to the ask: a customer decision doc is a plain, minimal page
  (see `sketch`/`popular-web-designs` restraint) — not the internal methodology's
  visual identity (e.g. a BrainLift's DOK color ramp), which would leak process to an
  external reader and looks over-designed for a "share this" request.
Rebuilding from scratch is faster and safer than trying to redact an internal doc down
to something exportable — the internal doc's structure (methodology-first) fights the
external doc's structure (behavior-first) at almost every section.

Default the customer-facing artifact to **plain markdown**, not a styled HTML page,
unless the user asks for something rendered/visual. A minimal `.md` needs no browser
verification, no repo format-check dance, and matches "keep it simple" by construction.
If the user explicitly says "minimal text doc," that's a signal to drop HTML entirely,
not just to strip styling from it.

### 13. Audit every declarative sentence in a customer decision doc — is it actually a decision?

The most common defect in a first draft of a customer-facing decision doc is smuggling
an unresolved internal choice in as a stated fact. Classic case: "progress is stored
so it survives across devices" reads as a shipped capability, but it's conditional on
*where* it's stored — if the customer wants on-device storage instead, it does NOT
survive across devices. Before finalizing, scan every bullet under "what we'll build"
for words like "survives," "persists," "always," "automatically" — anything asserting
an outcome that actually depends on an open question — and either cut it or convert it
into (or qualify it against) the decision itself. The user will catch this and call it
out as "decisions presented to them as facts," which undermines the whole doc's
credibility as neutral.

### 14. Use the customer's own terminology, not the codebase's internal nouns

If the customer or their reference implementation calls something "slide," write
"slide" throughout the customer doc — not the codebase's internal term ("part",
"video", "step"). Terminology mismatches make a customer doc read as translated-from-
internal rather than written-for-them. Grep the reference/demo's DOM or ask which term
the customer already uses; don't default to whatever noun the source code happens to use.

### 15. A recommendation can deliberately oppose the cited reference — say why

Don't assume "match the reference implementation" is the default recommendation. If
the reference allows a behavior (e.g. free navigation past unfinished content) but the
actual customer goal (e.g. "students shouldn't be able to skip") argues for a stricter
rule, recommend the stricter option and flag explicitly that it goes further than the
cited reference. Silently mirroring the reference when the stated goal argues
otherwise is a missed catch, not a neutral default.

### 16. Mark dependent ("nested") questions as conditional on a specific other answer

When soliciting behavioral decisions from a customer, some questions only make sense
given a particular answer to an earlier one — e.g. "what's a skipped item's limit"
only applies if the customer picks free navigation over gating in the first question.
State the dependency explicitly ("If you pick free movement in Q1...") rather than
listing it as an unconditional fifth question; otherwise it reads as an extra
unrelated ask instead of the corollary it is. When generating a batch of "what other
open questions might there be" for the user to review, actively look for this
nested-dependency shape — it's a distinct category from independent top-level
decisions, and worth calling out as such before presenting the list.

### 17. When asked for more open questions, separate "worth asking" from "worth stating as behavior"

Not every corner case the request surfaces should become a customer question. Push
each candidate through: is this genuinely undecided from the customer's perspective
(ask it), or is there an obvious/default answer that doesn't need customer input
(state it as behavior, don't ask)? and is this a real product decision or an
implementation nicety dressed as one (e.g. does 2x playback speed still count as
"watched" — trivial, drop it; the user will flag this as "over engineering" if
included). Present only the genuinely open, non-trivial ones as numbered questions.

## Pitfalls

## Pitfalls

- Placing a written artifact (HTML doc, markdown, config) inside the repo means it's
  still subject to whatever the repo's own scripts run over "everything" — e.g.
  `pnpm run format` = `prettier --check .` scans all file types, not just source, and
  will fail CI on an unformatted `docs/*.html` you just added. Before calling a
  non-code deliverable done, check whether the repo's format/lint script globs your
  file's extension (`.prettierrc`, `.prettierignore`, the `format`/`lint` script
  targets in `package.json`) and run it — visual/rendering verification is necessary
  but not sufficient once the file lives inside a repo with its own CI gates.

- Asserting a negative ("no flag for this exists") without grepping first — costs a
  round of correction and erodes trust in every other claim in the same message.
- Blurring "within this lesson" and "across lessons/sessions" — the two need
  different owners and different ETAs; conflating them makes the whole estimate look
  hand-wavy.
- Sneaking in a UX nicety (grace buffer, extra tolerance, snap-back animation) that
  wasn't asked for — treat "let's just confirm this" as a hard stop on scope, not an
  invitation to add "helpful" extras.
- Re-litigating something the user already told you in an earlier message — reread
  the thread before listing "questions for the customer."
- Stating a conditional outcome ("survives across sessions/devices") as a fact when
  it actually depends on an unresolved decision (where it's stored) — audit every
  declarative sentence in a customer doc before shipping it.
- Writing a customer doc in the codebase's internal terminology instead of the
  customer's own words for the same concept.
- Defaulting to "match the reference implementation" without checking whether the
  stated customer goal actually argues for a stricter or different behavior.
- Listing a dependent/nested question as if it were an independent top-level one,
  or asking a question with an obvious non-answer (over-engineering) instead of just
  stating the default and moving on.
- Giving one undifferentiated ETA when part of the timeline depends on the
  customer's own follow-through — split "our side ships by X" from "the
  customer-dependent piece goes live once they do Y."
- Recommending a numeric unit for "more precision" without checking whether it's
  robust to the dimension most likely to change later (video re-cut, length edit).
- Designing a cross-session persistence/callback shape from the library's own
  internal model without first checking whether the consuming platform already
  has a documented integration contract (postMessage protocol, opaque-state
  field, a composition chain up to an integrator) that constrains the shape —
  check the platform's public docs during scoping, not after a design ships.
- Turning every seam exposed by the customer's own integration docs into a
  customer question — several will actually be "how should you build your own
  renderer," which isn't ours to ask. Re-run the boundary check from step 2
  against the questions list itself (step 20) before sending it.
- Handing off a built feature for manual QA without checking the demo/test-app
  wires every new prop/callback — grep the demo for each new name before
  saying "ready to test."
