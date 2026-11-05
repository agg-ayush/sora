---
name: mockup-review-iteration
description: "Use when building or revising an HTML concept mockup: delegate the build, serve once, revise surgically on numbered feedback."
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mockup, review, iteration, html, ui, feedback, revision, prototype]
    related_skills: [sketch, claude-design, spike]
---

# Mockup Review Iteration

## When to Use

Use for the **revision phase** that follows initial mockup/variant generation
(from `sketch`, `claude-design`, or an ad-hoc HTML file): the user has seen a
first pass and is giving numbered, round-by-round feedback on a live artifact
until it's locked. A distinct mode from generating options — it needs
conservative editing discipline, not creative range. Load whenever a
conversation shifts from "show me some directions" to "no here's what's
wrong, fix these N things" on an HTML mockup/prototype.

Reviewing a deployed app (not a mockup) and routing nitpicks into build passes: use `product-ui-review`, which also holds the user's standing UI defaults.

## Core discipline

### 1. Serve it live once, not screenshot-per-round

If a mockup is going to get more than one round of feedback, don't keep round-tripping through `browser_vision` screenshots. Start a local HTTP server once and hand the user a URL they can refresh themselves:

```bash
cd /path/to/mockup/dir
python3 -m http.server 8747   # pick any free port; run backgrounded (terminal background=true)
```

Edits to the file on disk are picked up on refresh — no restart needed per edit. This is dramatically faster feedback-loop than re-screenshotting after every patch, and lets the user scroll/inspect/zoom themselves.

**Verify the server is actually still serving current content before handing back the URL** — background processes can die silently between rounds, and a stale "it's live" claim is worse than admitting you need to restart it:

```bash
curl -sf -o /dev/null -w "HTTP %{http_code} · %{size_download} bytes\n" http://127.0.0.1:8747/mockup.html
```

Only fall back to screenshots if the user has no way to open a local URL (remote session, no browser access).

**"Serve this mockup so I can compare" is a two-minute job: do only that.** When the user points at a mockup in a repo commit, extract just that folder at that commit (`git -C <repo> archive <sha> <path/to/mockup> | tar -x -C <scratch>` or `git show <sha>:<file> > <scratch>/<file>` per file), start `python3 -m http.server <port> --bind 127.0.0.1` in the background from that dir, curl-check the HTML and its CSS return 200, and hand back the URL. Do not detour into unrelated board/merge/dispatch work mid-ask; the user will interrupt. **On a remote host, bind to localhost and hand out the SSH tunnel** (`ssh -L <port>:127.0.0.1:<port> <host>`, then `http://localhost:<port>/`); never bind 0.0.0.0 or hand out a public-IP URL, since this user connects over SSH and does not want mockups exposed publicly. Confirm with `ss -tlnp | grep <port>` that the listener shows `127.0.0.1`.

- **Mocking a screen that already exists in the app: copy, don't redesign.** Lift the exact JSX branch (text, role, class names) and the CSS rules those classes use from the source files, note the source path in the page, and serve it. Offer the proposed alternative as a separate side-by-side only if asked.
- **Serve the whole handoff folder, not just the HTML pair.** Mockup handoffs carry README, reference images and problem pages next to the app; serve from the folder root so every sibling resolves, and curl-check each file (HTML, CSS, README, every image) for 200.
- **When the user points at a newer branch or tree URL, re-serve from that branch's latest head** (fetch, extract, restart or repoint the server) and state the head SHA you are serving. A server left on an older commit shows the user a stale target.

### 1b. "Does the current UI follow the mockup?"

Answer from both codebases, not from memory or impressions:
1. Extract the mockup's structure programmatically: screen/view headings, button labels, checklist item labels and hints, modals (e.g. a Python regex pass over `git show <branch>:<path>/index.html`).
2. Extract the same from the shipped components on `origin/main` (labels, hints, step keys, page sections).
3. Lead with a one-line yes/no, then a table per aspect (sign-in, entry screen, checklist items and wording, trouble/escape flow, main work view layout, finish/submission screens, palette) with mockup vs current. Separate "functionally equivalent but structurally different" from "missing entirely", and name which card owns closing the gap.

### 2. Touch only what was asked — this is the #1 failure mode

When the user gives numbered feedback points, **change exactly those points and nothing else**, even if you notice something adjacent that you personally think also needs fixing. Concrete examples of the trap:

- User complains about text wrapping in one component → don't also add reserved whitespace/feedback-docks to five *other* unrelated components "while you're in there."
- User asks to widen a grid → don't also restructure spacing on a different section that wasn't mentioned.
- User asks to move one element up → don't also recenter or resize things nearby that weren't flagged.

This reads as **"you're changing random shit I didn't ask for"** and burns trust immediately, even when each individual unrequested change is defensible on its own merits. It also makes the diff harder for the user to verify against their actual ask.

If you genuinely think something else needs fixing, **name it as a separate observation and ask** — don't fold it into the same patch. Default to the smallest patch that satisfies the literal feedback item.

Before applying a batch of numbered fixes, mentally re-read the user's list and check each patch maps 1:1 to a numbered item. If a patch doesn't trace back to an explicit ask, cut it.

### 3. When the user is unsure about ONE sub-element, give them a mini side-by-side, not a unilateral pick

If feedback is "this looks bad, not sure, let me see" about one specific piece (a keypad layout, a button style, a color) — rather than the whole composition — don't silently choose a replacement and ship it. Build 2-3 named variants of *just that sub-element*, stacked in the same page for direct comparison (e.g. "keypad option A — 2 rows" vs "option B — 3 rows" vs "original — for comparison"), and let them pick. This mirrors the variant-comparison philosophy from `sketch`/`claude-design`, just applied at sub-component granularity instead of whole-screen granularity — it's the right move whenever the user's uncertainty is scoped to one element, not the whole design.

### 4. Batch independent numbered fixes, but keep each patch scoped to its own item

When the user gives 3-4 numbered points in one message, it's fine to apply them in one working pass — but keep each as its own targeted `patch` call against its own snippet, so if one needs rework it doesn't tangle with the others in the diff.

### 5. If `browser_vision`/`vision_analyze` errors on the routed model, fall back to DOM assertions — don't skip verification

Some routed models reject image inputs outright (`"model does not support image inputs"`). Don't treat that as "can't verify, moving on" — fall back to `browser_console` with a JS expression that asserts on the DOM directly: element counts, `textContent`, `innerHTML` snippets, `children.length` against what the mockup is supposed to contain:

```js
document.querySelectorAll('.pill').length            // expected item count
document.getElementById('tray').children.length      // expected tray contents
document.querySelector('.q-text')?.textContent       // expected text present
```

This is strictly weaker than a real visual check (it won't catch a font that failed to load or colors that clash) but it does catch the failure mode that matters most for interactive mockups: a JS error left the DOM in a stale/empty state that *looks* fine in the accessibility snapshot but is actually broken. Worth running even when vision succeeds, for any mockup with non-trivial interactivity (drag targets, dynamic lists, multi-step state) — vision catches visual bugs, DOM assertions catch structural ones.

**`browser_click` on a ref can silently no-op when the label wraps the control** (e.g. `<label>Items: <button id="btn-text">Text</button><button id="btn-image">Image</button></label>` or similar nested-clickable markup) — the click reports `{"success": true}` but the toggle never actually flips because the ref resolved to an ambiguous/wrong node. Don't trust the reported success on toggle controls; **assert the resulting state changed** with a `browser_console` DOM check right after every click (class list, `textContent`, item count). If it didn't change, don't retry the same ref — call `.click()` directly on the concrete element instead: `browser_console(expression="document.getElementById('btn-image').click()")`. This sidesteps ref-ambiguity entirely and is the more reliable way to drive toggle/tab controls in general.

**For a combinatorial variant space (e.g. item-type × target-count), build one interactive page with toggle controls, not N×M separate files.** When asked to extend a chosen variant across multiple independent axes (text vs. image items, 2/3/4 targets, etc.), materializing every combination as its own HTML file multiplies maintenance cost for no benefit — a single page with buttons that re-render the relevant DOM subtree covers the whole matrix and is easier to compare side by side. Verify by driving every axis combination through `browser_console` and asserting the expected counts/labels (target count, item count, question text) for each cell — don't eyeball one combination and assume the rest generalize.

### 5b. `browser_vision`/`vision_analyze` can return a confident but generic/hallucinated answer instead of erroring — on a dense multi-slide artifact, don't trust prose verification at all; scan the whole DOM programmatically in one pass

Two distinct unreliable-vision failure modes showed up reviewing a 5-slide deck rendered as one long page: (a) `browser_vision` returned `"Vision analysis returned no content."` with no error surfaced, and (b) a follow-up `vision_analyze` on the same screenshot returned a fluent paragraph describing generic "design language" (white cards, hairline rules, sans type) without actually answering the clipping/overlap question asked — it looked like a real answer but wasn't grounded in the specific frames. Neither is a hard error you can catch and branch on; both look superficially like a completed analysis.

For a composition with many elements (a multi-slide deck, a dense dashboard), don't rely on per-element `getBoundingClientRect()` spot checks either — that only proves the specific elements you thought to check are fine. Instead run one whole-page overflow scanner in `browser_console` that walks every element and flags any whose content exceeds its box:

```js
(() => {
  const bad = [];
  document.querySelectorAll('.frame *').forEach(e => {
    if (e.scrollWidth > e.clientWidth + 2 && e.clientWidth > 0) bad.push([e.className || e.tagName, 'w', e.clientWidth, e.scrollWidth]);
    if (e.scrollHeight > e.clientHeight + 2 && e.clientHeight > 0 && getComputedStyle(e).overflow !== 'visible') bad.push([e.className || e.tagName, 'h', e.clientHeight, e.scrollHeight]);
  });
  return JSON.stringify(bad);
})()
```

An empty result (`[]`) is real, checkable evidence of "nothing clipped anywhere" — treat this as the primary verification for "is anything cut off in this deck/mockup" claims, with vision as a secondary/illustrative pass at most, never the deciding evidence on a dense multi-element artifact.

### 6. Verify layout claims with computed geometry, not eyeballing

For anything spatial (equal widths, wrap counts, centering, overflow, gaps),
don't apply the CSS and declare it fixed — read back real geometry via
`browser_console` (`getBoundingClientRect()`/`scrollHeight`/`clientHeight`)
and report the actual numbers. Full technique, the CSS-specific failure modes
(grid tracks, aspect-ratio images, box-sizing, flex-basis, shared-selector
fan-out), and the wasted-space checklist live in
`references/css-layout-pitfalls.md` — load it when the round involves layout
sizing/centering/overflow work.

When the user asks "what if X were the worst case" (longer question, more
options, longest word), build that literal worst-case variant as a new block
and measure it the same way — don't just reason about it abstractly. Report
the concrete numbers as evidence, not just "looks fine."

**Combine stressors, don't test them one axis at a time.** A layout that
passes every single-axis worst case can still break on the union of them —
build at least one block that stacks ALL the plausible stressors together
(longest realistic question + image present + max option count) and measure
that combined case.

### 7. When the mockup previews a feature that will render inside a specific host container, replicate that container exactly — not an approximation

If the real feature renders inside a fixed host (a video overlay letterboxed
to 16:9, a modal, an iframe, a fixed-aspect canvas), don't build the mockup
at "whatever fits the browser viewport." Find the actual host component's
sizing/positioning logic (e.g. how it computes `videoBounds` and absolutely
positions the overlay `inset:0` over it) and reproduce that exact box — same
aspect ratio, same positioning strategy — so review happens in a truthful
frame that can't hide overflow/clipping bugs that only appear at real
dimensions.

Other discipline in this mode:

- **Invent no placeholder content when real fixture data exists in the
  repo** — pull real question text, item lists, and image URLs from the
  actual test/fixture files; it surfaces real content-length edge cases
  synthetic content won't.
- **`flex: 1 1 0`, not `flex: 1 1 auto`, for a "fill remaining space"
  child** — `auto` sizes from content first; if a `1fr`/flex-grow fix
  "isn't working" after 2 attempts on the child, the bug is one level up in
  the parent's flex-basis.
- **Don't re-delegate a hung Claude Code session on a small throwaway
  mockup fix** — a wedged over-thinking loop on a bounded, hand-editable
  artifact wastes a round-trip; kill it and patch the file directly. Same
  cutoff for the false-done shape: session reports `done` on every poll but
  the change never lands — one false-done gets a single retry-steer; a
  repeat means stop, kill, hand-edit. Before hand-editing after a kill,
  re-read live state for EVERY item of the original ask (some may have
  already landed) rather than assuming all are outstanding.

### 11. When a mocked component's real host container resizes at runtime, size proportionally to the measured frame, not to a fixed px value — and if it's ambiguous, ask which the user wants

If the real host container varies at runtime (ResizeObserver-driven video
overlay, responsive panel), don't harden a mockup dimension to a fixed px
value just because it looked right at one window size. Compute it as a
fraction of the frame's measured dimensions in JS, store it in a CSS
variable, and re-derive on every render/resize/fixture-switch. Also don't
assume different target counts (2 vs 4) should get different heights unless
asked — "uniform proportional sizing" is often what's wanted; confirm before
diverging counts to different fractions. Same discipline for mode-independent
sizing: a height cap from a cramped sidebar mode is usually an artifact of
that mode, not a design constant — don't carry it into a spacious fullscreen
mockup (see `references/css-layout-pitfalls.md`, "Mode-independent sizing").

### 9. After an external edit lands on a live-served mockup, a blank/broken-looking reload is more likely stale cache than a broken edit — verify before diagnosing

Check in this order:

1. **Selector-independent sanity probe first**: `document.body.children.length`
   — a null-property error usually means you evaluated against a selector that
   doesn't match the current markup, not that the DOM is actually empty.
2. **Hard-reload with a cache-busting query param** (`?v=2`) — a static file
   server + open browser tab can serve/hold a stale (sometimes empty) response
   across a file save that landed mid-request.
3. **Independently confirm the file is syntactically valid** and the
   background server is still alive before concluding the edit broke
   something.
4. Only after a fresh cache-busted load against a confirmed-live server with
   a syntax-valid file still comes back empty is there real evidence the edit
   broke rendering.

### 10. When delegating a throwaway mockup fix to a coding CLI and it wedges, don't re-delegate — hand-edit

Covered under §7's discipline list: interrupt once after 5+ min of no
progress, kill on repeat, and hand-edit the bounded artifact yourself.

### 12. Stakeholder review mockups: static, desktop-scoped, true to the real content structure

When the ask is "mockups to send to a reviewer" (screens embedded in a doc), the deliverable is static screenshots, not product code: never touch the app repo or open a PR for it. Scope rules for this user:

- **Desktop/laptop only unless mobile is explicitly asked for** — do not spend a round on responsive or mobile variants for an internal/assessment tool.
- **Mirror the real information structure.** If the real feature has several documents/briefs/tabs (check the implementing branch/PR), the mockup must show all of them and at least one non-default one selected; flattening to a single item gets rejected.
- **Put secondary navigation in an existing side rail rather than adding a tab strip over the main pane** — horizontal tabs above the reading area eat vertical space; reuse the rail that already holds the timer/progress, and don't add a new column that narrows the reading pane.
- **Professional palette by default**: restrained (navy/slate, one muted accent, off-white), consistent spacing and type hierarchy; generic default-Claude styling reads as unprofessional. Route visual design to a design-focused subagent loaded with `frontend-design`/`impeccable`, not plain Claude Code.
- Update the SAME review doc in place (`gog docs replace-image` per screen, see `gog-cli`) and fix any caption text that describes the old layout.
- **Each screenshot must fit one laptop viewport height** (about 1440x900 CSS px). A full-page capture taller than that misrepresents what the candidate sees; drop or recrop it rather than shrinking it.
- **Upload the full-resolution PNGs to Drive and put a clickable link directly below each embedded image** — doc embeds are downscaled and reviewers need to zoom.

### 13. Handing mockups to another owner: publish a reference branch, not a PR

When someone else takes over the UI, or the user asks to push the mockup into a branch on a repo, give them one GitHub branch they can build on:

0. **Check write access before cloning or committing:** `gh repo view <owner>/<repo> --json viewerPermission -q .viewerPermission`. `READ` means a push will 403 no matter how credentials are routed; tell the user up front and ask who should grant access, instead of building the commit first. Clone into a durable path (not the scratch dir, which prunes idle entries after 24h) so a commit waiting on access survives, and run `gh auth setup-git` so pushes use the gh token.
   - **Fallback when the user says "put it in a new repo under my account":** create a private repo (`gh repo create <user>/<name> --private`) holding ONLY the mockup files at the root plus a short README, one commit, built in a fresh `git init -b main` dir. Never push the cloned product repo's history into it; a full fork gets rejected as "not the barebones mockup". Verify via API: one commit, root listing equals the mockup files, visibility private.
   - **Run `git remote -v` right before every push.** A `set-url` chained with `&&` after a failed command never runs, and the push silently goes back to the original remote.
   - When the user later asks where a feature lives in the pushed mockup, answer with the exact page URL and each entry point (element + line/anchor), grepped fresh from the files, not from memory of the build report.

1. Create an isolated worktree off the branch that holds the existing UI implementation (usually an open PR head), never the shared checkout and never `main`.
2. Add only a `ui-handoff/` folder: the HTML sources and screenshots under `images/` for exactly the screens currently embedded in the review doc (list the doc's images first, e.g. `gog docs images list`, and map each to its file), plus a README that lists the exact existing UI file paths, links the implementation PR and states known gaps and scope (for example, desktop only).
   - **Current mockups only**: omit superseded prototypes and alternates that were dropped from the doc; do not ship them "marked as superseded". The new owner should see one unambiguous target.
   - **Scope the README to what the new owner owns**: if they take only the UI, leave out backend/API/spec PRs and other people's workstreams entirely.
   - **Self-contained on GitHub**: link files by relative path in the branch, not to the Google Doc; the user and new owner may not be able to open embedded doc images from the working host.
3. README wording must be accurate: call unmerged code "existing implementation in open PR", not "production"; call the design "latest mockup", not "final", unless the user said it is final.
4. Before pushing, verify: copied files are byte-identical to the sources the user reviewed (hash compare), `git diff --check HEAD^ HEAD` is clean (static HTML often carries trailing whitespace), only `ui-handoff/` changed, no secrets or per-candidate URLs, and the remote branch does not already exist. Amend the unpublished commit for cleanup instead of stacking fixups.
5. Push the branch, confirm the remote SHA matches, confirm the base PR head is unchanged, and open no PR. Hand the user the branch URL plus the README link as one message, and comment the handoff on any tracking card while leaving it blocked for the new owner.

### 14. Building a concept-demo mockup (first pass, before review rounds)

1. **Settle the concept before any visual talk.** Walk each persona's flow as what the system does for them, mapped to their known pains, one screen/persona at a time. Keep appearance out of this phase entirely (layout, colors, card styles); the user settles look later with the design skills, and UI-look talk during concept discussion gets cut off.
2. **Naming design skills is the explicit ask for polish.** When the user points at `impeccable`, `ui-styling`, `frontend-design`, `ui-ux-pro-max` or similar, the default "minimal styling, plain white, borders, grey text" rule no longer applies. Tell the builder to load and follow those skills (Claude Code reads them from its own skills dir); never hardcode a plain-wireframe style constraint into the build prompt that contradicts them.
3. **Delegate through `claude_orchestrate`, not T1/T2.** A throwaway mockup needs no worktree, branch, PR or gate: `start` with `model: "claude-opus-5"` (when Opus is asked), a scratch or dedicated output dir as `workdir`, no `worktree`, and a one-line prompt pointing at a `prompt.md` that carries the full settled concept (per-screen sections, mock data names, project boundaries, out-of-scope items) plus the output paths.
   - **Split into several pages, one per screen/flow step**, navigated the way the real product would (board → case → signer link, breadcrumbs). A single page cramming every element reads as barebones; this user treats the mock as an early UI to refine later, so no wiring, but real page structure.
   - **Concept-demo mocks are realistic product screens, never a presentation.** The user presents the concept live in his own voice, so the UI must not explain or sell itself. Ban in the prompt and grep for afterwards: index/launcher pages, demo view-switchers, legends explaining badges, "how it works"/"why" panels, benefit lines, old-vs-new comparisons. Distinctions (e.g. needs-approval vs auto-advanced) appear only as natural UI states. Show alternate states (e.g. a red-flag case) as a separate real record reachable through normal navigation, not a demo toggle.
   - **Back every screen with one fully fleshed mock record** (ticket number, parties, amounts, terms, named people, timestamped activity trail), plus a few shallower records for list/board views; require the data to be consistent across pages (same names, dates in a plausible order).
   - **Put an explicit acceptance checklist in `prompt.md`** (every required element per page, cross-cutting rules: self-contained, proportional sizing, accessibility, the design skills to load) and require the builder's report to map each item to the file that satisfies it. A rebuild without a checklist drifts.
   - **When the user names his own Claude Code skill (e.g. a custom UI pipeline skill), the prompt must say "invoke the `<skill>` skill with the Skill tool and follow its phases and gates"**, and the checklist still goes in `prompt.md`. Before `start`, copy the user-level skills into the workdir: `mkdir -p <workdir>/.claude/skills && cp -r ~/.claude/skills/* <workdir>/.claude/skills/`; a routed session may not load `~/.claude/skills`, and it fails with `Unknown skill: <name>` then improvises without the pipeline. Also tell the builder to report any skill the pipeline chains to that is missing and name its substitute.
   - **Smoke-check the pane ~20s after `start`** (`tmux capture-pane -t <task_id> -p | tail`). A "Not logged in" footer or an `Unknown skill` error means the build is not running as intended; `stop`, fix (route through the configured `model_provider`, or install skills project-level as above), and restart under a new `task_id` instead of waiting on a dead session.
   - **Pre-trust every new `workdir` before `start`** (each new dir, not once per session). An interactive Claude session in a never-trusted directory dies at the folder-trust dialog (the default selection is "No, exit" and a steered newline doesn't answer it). Symptom: `status` shows `state: exited`, `status_file: starting`, outcome `PENDING` and no output files; restart under a new `task_id` after trusting. Fix: `tmux new -d -s trust -c <dir> claude`, wait for the dialog, `tmux send-keys -t trust Down` then `Enter`, confirm the ready prompt, `/exit`, kill the session, then `start`. Trust is cached per directory afterwards.
   - **Lock the UI before a build agent implements the feature.** When a T2/coding card will build a UI, finish the mockup and get the user's approval first, then hand the approved mockup to the build as a design input; hold the build after its design phase rather than letting it invent the UI.
4. **"Don't block main chat" means start and return.** After `start`, report the task id and end the turn or keep discussing; do not sit in a synchronous `wait` for the whole build (polished multi-page builds take 20+ minutes). Check `status` when the user comes back or the session signals. If you must wait, keep each `wait` timeout under the tool's ~420s hard cap and use `status` between calls; a timed-out `wait` is the cap, not a failed build, so never repeat it unchanged. A pane showing "Waiting for API response · will retry in Ns" is Claude Code's own backoff; wait again rather than killing or re-steering.
   - **Revision rounds on a built concept demo:** restate each requested change as a numbered understanding (what gets added, where it sits, what existing element is kept or demoted) and get a go-ahead before starting the builder; then put that list in the revision `prompt.md` as the checklist. Keep existing ids/anchors when demoting an element so links from other pages still land.
5. **Verify the artifact yourself before reporting.** `status.md` can read `complete` before `result.md`/`outcome.md` are written; re-read them after a short pause instead of reporting from a `PENDING` outcome. Parse each HTML file (tag balance, duplicate ids), check cross-links and referenced assets exist, grep every page for self-explaining copy (`how it works`, `legend`, `demo`, `benefit`, `instead of`, `old way`), then render it with the browser tools for a visual pass. Report the absolute file paths and the builder's own caveats (e.g. mock-date inconsistencies), then `stop` the session.

## Pitfalls

- **Scope creep disguised as thoroughness** — "fix it properly while I'm
  here" is wrong in this mode; proper means minimal and literal.
- **Re-screenshotting every round** when a live server was already
  available; **claiming the server is live without checking** it.
- **Picking a winner for the user on an element they said they were unsure
  about** — give a real side-by-side; the pick is theirs.
- **Declaring a layout fix "confirmed" without measuring it** — pull real
  geometry numbers, not visual impressions.
- **Giving up on verification when `browser_vision` errors** — fall back to
  `browser_console` DOM assertions.
- **Trusting a `browser_click` success report on a toggle/tab control**
  without asserting the DOM state changed; drive
  `document.getElementById(...).click()` directly when refs are ambiguous.
- **Building N×M separate files for a combinatorial variant space** instead
  of one page with toggle controls that re-render the relevant subtree.
- **Building at generic viewport dimensions when the real feature renders
  inside a fixed/constrained host container** — reproduce the exact box.
- **Inventing placeholder content when real fixture data exists in the
  repo.**
- **Describing unmerged PR code as production in a handoff README** — the new
  owner will assume it is deployed.
- **Serving only part of a handoff folder, or an older commit of it** — the user compares against a partial or stale target.
- **Padding a handoff with older prototypes or adjacent workstreams** — extra
  files and links force the new owner to guess which is current and what they
  own; ship only the current doc screens and their scope.
- **Building a concept demo that narrates itself** (launcher, legends, demo
  toggles, explainer panels) — the user presents; the screens must read as a
  real tool backed by a real-looking record.
- **Exposing a mock server on a public IP** — bind 127.0.0.1 and give the SSH
  tunnel command.
