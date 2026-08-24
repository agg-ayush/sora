---
name: mockup-review-iteration
description: "Live-served HTML mockup review: serve once, revise round by round on numbered feedback, keep diffs surgical."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mockup, review, iteration, html, ui, feedback, revision, prototype]
    related_skills: [sketch, claude-design, spike]
---

# Mockup Review Iteration

Use this skill for the **revision phase** that follows initial mockup/variant generation (from `sketch`, `claude-design`, or a one-off HTML file built ad hoc): the user has seen a first pass and is now giving numbered, round-by-round feedback on a live artifact until it's locked. This is a distinct mode from generating options — it needs conservative editing discipline, not creative range.

Load this whenever a conversation shifts from "show me some directions" to "no here's what's wrong, fix these N things" on an HTML mockup/prototype.

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

For anything spatial (equal widths, row/column wrap count, centering, overflow, gap sizes), don't just apply the CSS and declare it fixed — read back real geometry via `browser_console` with a JS expression against `getBoundingClientRect()`/`scrollHeight`/`clientHeight`, and report the actual numbers. This is strictly better than a screenshot for these claims because it's exact and cheap to re-run every round:

```js
// equal-width check + row count (wrap correctness)
[...document.querySelectorAll('.opt-text')].map(x=>{
  const r=x.getBoundingClientRect();
  return {w:Math.round(r.width), top:Math.round(r.top)};
});
// -> compare widths (Set size === 1 -> allEqual) and distinct `top` values (-> visual row count)

// centering check: does element X's center match container's center?
Math.abs(elCenterX - containerCenterX) <= 3

// overflow check: does content exceed a fixed-height container?
el.scrollHeight > el.clientHeight + 1
```

**For drag-and-drop mockups specifically, verify drop-state layout (e.g. N items landing in one target) by calling the mockup's own state functions directly in `browser_console` instead of simulating real pointer drag events** — real HTML5 drag-and-drop is painful to script reliably via automation. If the mockup's JS exposes helpers like `fixture()`, `move(itemId, targetId)`, `render()` (or equivalent state-mutation + re-render functions), call them directly to force the item-in-target state, then measure geometry per §6 (e.g. count distinct `top` values among tiles in a zone to confirm a 2×2 wrap vs. a single row). This is faster and more reliable than driving native drag events, and works for any state that's just "N items assigned to target X" — not just drag-drop.

When the user asks "what if X were the worst case" (longer question, more options, longest word), build that literal worst-case variant as a new block and measure it the same way — don't just reason about it abstractly. Report the concrete numbers (row count, widths, overflow delta) as evidence, not just "looks fine."

**Combine stressors, don't test them one axis at a time.** If the component has multiple independent things that can each grow (question length, presence of an image, option/character count), a worst-case pass that tests each axis separately (one block for "2-line question + 4 options", a different block for "has an image") will miss the case where they combine — e.g. a 2-line question *and* an image together can overflow a fixed-height section (question+image block colliding with a fixed-grid input/keypad area below it) even though each stressor alone fit fine. Build at least one block that stacks ALL the plausible stressors together (longest realistic question + image present + max option count) and measure that combined case, not just the individual maxima. A layout that passes every single-axis worst case can still break on the union of them.

### 7a. When a feature exists in multiple host modes (e.g. sidebar vs. fullscreen/overlay), don't silently carry a size constraint from the cramped mode into the spacious one

If the component being mocked up already ships in a space-constrained mode (sidebar, compact panel) and the mockup is for a *different*, more spacious mode (fullscreen overlay, modal, letterboxed video frame), treat each mode's sizing as independent. A height/width cap that exists in the sidebar version is very often an artifact of that mode's limited real estate, not an intentional design constant — copying it into the fullscreen mockup wastes the exact space the user asked you to use. When in doubt whether a given dimension is a deliberate design choice vs. a sidebar-mode limitation, ask, or default to letting the spacious mode use its own space and say so explicitly (e.g. "kept tray/target height at the fullscreen values — not shrinking to match sidebar, since that constraint doesn't apply here").

### 7. When the mockup previews a feature that will render inside a specific host container, replicate that container exactly — not an approximation

If the real feature renders inside a fixed host (a video overlay letterboxed to 16:9, a modal, an iframe, a fixed-aspect canvas), don't build the mockup at "whatever fits the browser viewport." Go find the actual host component's sizing/positioning logic (e.g. how it computes `videoBounds` and absolutely positions the overlay `inset:0` over it) and reproduce that exact box — same aspect ratio, same positioning strategy — so review happens in a truthful frame, not an approximation that could hide overflow/clipping bugs that only show up at the real dimensions.

- **Inventing placeholder content (fake image URLs, made-up copy) when real fixture data already exists in the repo.** Pull real question text, item lists, and image URLs from the actual test/fixture files — it's not extra work, and it surfaces real content-length edge cases synthetic content won't.
- **Defaulting to `flex: 1 1 auto` for a "fill remaining space" child.** It only works when the child already has a definite content height; for a grid/list whose height should come *from* the parent, use `flex: 1 1 0` (or switch the parent to CSS grid with a `1fr` row) instead.
- **Iterating on the child's CSS (`1fr` rows, `flex-grow`) when a "won't fill height" bug is actually the parent's `flex-basis`.** If the same fix keeps "not working" after 2 attempts on the child, check one level up in the flex/grid chain before trying a 3rd variant of the same child-side fix.
- **Re-delegating a hung Claude Code session on a small throwaway mockup fix instead of just hand-editing it.** A wedged over-thinking loop on a bounded, hand-editable artifact wastes a second delegation round-trip for no benefit — kill it and patch the file directly.

### 11. When a mocked component's real host container resizes at runtime (ResizeObserver-driven video overlay, responsive panel), size proportionally to the measured frame, not to a fixed px value — and if it's ambiguous, ask which the user wants

If the real feature's host container varies in size at runtime, don't harden any mockup dimension to a fixed pixel value just because it looked right at one window size. Compute it as a fraction of the frame's measured dimensions in JS (e.g. `targetHeight = frameHeight * FRACTION`), store the result in a CSS variable, and re-derive it on every render/resize/fixture-switch — the same pattern the tray tile sizing already used (`--tile-size`). When it's unclear whether a given number should be a fixed constant or should scale with the frame, ask directly rather than guessing (this came up explicitly: "everything should be proportional/relative, not fixed" — the real component runs inside a ResizeObserver-driven video bounds box that varies with viewport). Also don't assume different target counts (2 vs 4) should get different heights unless asked — "uniform proportional sizing" (same height regardless of count) is often what's wanted; confirm before diverging counts to different fractions.

### 12. To stop a container collapsing when its content is emptied (a tray, a list), measure its rendered height once and pin it via a CSS variable — don't guess a min-height constant

A flex/grid container sized only by its content will shrink when items are removed ("the tray shrinks when empty"). Fix with a measure-after-render pattern instead of guessing a constant:

```js
// after appending content and letting the browser paint:
requestAnimationFrame(() => {
  const h = trayEl.offsetHeight;
  if (h > 0) trayEl.style.setProperty('--tray-min-height', h + 'px');
});
```
```css
.tray-strip { min-height: var(--tray-min-height, 110px); }
```

This captures the real rendered height (accounting for wrapping, tile sizes) rather than a hardcoded guess, and keeps working if tile sizes/item counts change later. Verify per §6: measure height with items, clear the content, re-measure, assert the two numbers match — don't eyeball it.

### 14. A shared CSS rule/selector used by multiple layout variants (e.g. 2-target vs 4-target) will silently regress every OTHER variant when you hardcode a literal fix for just one of them — parameterize via a JS-computed CSS variable instead

If several fixture/variant states render through the same selector (`.drop-inner.images` used by both the 2-target and 4-target layouts), a literal value change made to satisfy feedback about *one* variant (e.g. "add gap between tiles in the 2-target bucket") applies to *all* variants sharing that selector — including ones the user didn't mention and said were already fine ("the changes also changed 4 grid, it was fine as is before this"). This is a distinct failure mode from §2 (touching unrequested elements): here the edit target is correct and singular, but the CSS mechanism (one shared class/selector) fans it out to siblings invisibly.

Fix: never hardcode a spacing/sizing literal on a selector shared across variants. Compute it in JS per-variant (keyed off `fixture().targets.length` or equivalent) into a CSS custom property, with the value derived from measured geometry so it can't clip:

```js
const maxColGap = Math.max(4, targetWidth - PADDING - tileSize * 2 - MARGIN);
const colGap = targetCount <= 2 ? Math.min(45, maxColGap) : Math.min(8, maxColGap);
document.documentElement.style.setProperty('--in-zone-col-gap', colGap + 'px');
```
```css
.drop-inner.images { column-gap: var(--in-zone-col-gap, 8px); }
```

This both (a) fixes the requested variant, (b) leaves untouched variants untouched, and (c) caps the gap so it can never exceed the space available in the narrowest variant — the same geometry-capping instinct as §6/§11, applied to spacing values instead of sizes. After the fix, verify **every** variant that shares the selector, not just the one in the ask — pull the CSS var value and measure clipping (per §6) for each fixture, since "it looks right in the variant I changed" is not evidence the sibling variants are still fine.

### 13. Placeholder/empty-state text and in-target tile labels should be centered on both axes by default in a soft-styled mockup — check justify-content on the flex main axis, not just text-align

A common half-fix: `.placeholder { text-align: center }` handles horizontal centering of wrapped text but a flex container also needs `justify-content: center` on its main axis (and `align-items: center` on cross) to actually center the block within an empty tray/target — text-align alone won't center a short single-line placeholder inside a wider flex row. When the user says text looks off-center in an empty state, check both properties, not just one.

### 15. A percentage `height` on a CSS Grid *item* resolves against nothing unless the grid has explicit row tracks — give the grid `grid-template-rows` (e.g. `1fr 1fr`), then use `height: 100%` on the child, not a `%` height on the child itself

When converting a fixed-px in-zone tile layout to percentage-based sizing (per §11/§14), setting `height: var(--tile-h-pct)` (e.g. `42%`) directly on a grid item inside `display:grid; grid-auto-rows: auto` does **not** produce 42% of the container — grid rows auto-size to content by default, so there's no definite row height for the percentage to resolve against, and the tile collapses to its intrinsic content height instead (label text height, effectively).

Fix: give the grid explicit row tracks that consume the full container height — `grid-template-rows: 1fr 1fr` for a 2-row layout — and then set the item's `height: 100%` (100% of its now-definite row track), not a smaller percentage on the item. The percentage that actually matters is the ratio between the tracks (equal `1fr 1fr` = 50/50), not a height percentage on the child.

This is the grid-layout sibling of the flex-basis pitfall already documented in §6/Attribution#2 (`flex: 1 1 auto` not stretching a child with no intrinsic height) — same root cause (percentage/flex-grow resolving against an *undefined* parent dimension), different layout mode. When a "should be N% of container" sizing fix isn't taking effect on a grid item, check whether the grid has explicit row/column tracks before adding more percentage tweaks to the child.

### 16. When a tile/card contains an `aspect-ratio`-locked image, size the tile with ONE dimension (width) as the percentage/CSS-var and let the other be `auto` — splitting width and height into two independent percentage vars (or capping via `max-height` on the image) fights the aspect-ratio and squishes the image into a non-square/distorted rectangle

A tempting way to make an in-zone image tile "percentage-based and never-clipping" is to set both `--tile-w` and `--tile-h` (or a `max-height` on `.tile-img`) as independent percentages of the target box. This breaks the moment the target's aspect ratio differs from the image's: the image has `aspect-ratio: 1/1` but the two percentages resolve against different container dimensions (width vs. height), so satisfying both constraints simultaneously requires the browser to violate one — it silently squishes the image (e.g. a 152×152 tile rendering a 152×79 image instead of a square one).

Fix: pick ONE sizing axis (normally width, since the tray tiles already scale off frame *width*) and let the other be `auto`, so `aspect-ratio` on the image is the sole thing determining the cross dimension:

```css
.tile.in-zone {
  width: var(--in-zone-tile-w, 42%);
  height: auto;            /* NOT a percentage — let content (image aspect-ratio) drive it */
  overflow: visible;        /* not hidden — nothing should need cropping if sized right */
}
.tile.in-zone .tile-img {
  width: 100%;
  height: auto;             /* NOT max-height — let aspect-ratio own the height */
  aspect-ratio: 1/1;
}
```

To still guarantee N rows fit inside the target's *actual* height (so the image-driven height doesn't cause clipping/overflow), compute the width **cap** in JS from BOTH target dimensions — not just target width — before writing it to the CSS var:

```js
// cap tile width so `rows` of square (aspect-ratio 1/1) tiles fit the target's real height,
// after subtracting per-tile label space and the gap between rows
const capWpct = (((targetHeightPx - gapFrac * targetWidthPx) / rows - labelSpacePx) / targetWidthPx) * 100;
const tileWpct = Math.min(desiredWpct, Math.max(minWpct, Math.round(capWpct)));
```

This is the aspect-ratio-image-specific sibling of §14/§15 (which cover non-image grid-cell sizing) — same instinct (compute geometry in JS, write it into a single CSS var, verify per §6) but the specific trap here is splitting one visual unit's size into two independently-constrained CSS percentages. Verify by asserting `imgWidth === imgHeight` (within ~2px) via `getBoundingClientRect()` on the actual rendered image, not just checking the tile box didn't clip — a non-square image can pass a "did it clip" check while still being visibly squished.

### 17. When a JS-computed height (a CSS var driving a fixed grid/flex row track, e.g. `grid-template-rows: var(--tray-height) 1fr`) is applied to an element that ALSO has padding and/or a border, add `box-sizing: border-box` to that element explicitly — don't assume it inherited it

A row track sized `var(--tray-height)` (or any JS-computed fixed dimension) is meant to be the element's *total* box height. But `box-sizing: content-box` is the CSS default, so `height: 144px` + `padding: 18px` + `border: 1px×2` renders a 164px box — 20px taller than its 144px grid row — and the excess bleeds into the *next* row/sibling (looks like "the next section overlaps/overflows into this one" even though nothing about the next section's own CSS changed). This is easy to miss because sibling elements in the same component often already have `box-sizing: border-box` set explicitly (e.g. the target/card elements did, in a real case) while one element (the tray/header strip) was overlooked and left on the content-box default — the bug reads as "two sections aren't stacking cleanly" when the real cause is one specific element's box-sizing.

Fix: any element whose height is driven by a JS-computed CSS variable used as a fixed grid/flex track size (not `auto`/`1fr`) must have `box-sizing: border-box` set explicitly, so the declared height IS the rendered total height regardless of padding/border. Don't rely on a global `* { box-sizing: border-box }` reset existing — audit the specific component's elements for it, especially ones with both padding/border AND a JS-set height var.

Verify per §6 with a direct measurement, not just "looks stacked": get each section's `getBoundingClientRect()`, confirm `sectionA.bottom <= sectionB.top` (zero or positive gap), and separately confirm `getComputedStyle(sectionA).boxSizing === 'border-box'` on the element whose height is CSS-var-driven — reading the box-sizing value directly is what actually proves the fix (a screenshot or "gap looks fine" can miss a 1-2px overlap that a strict `<=` check catches).

### 18. Two flex children each carrying their own `margin: auto` in the same axis fight each other — only ONE margin/auto owner should exist per gap you're trying to balance

When centering a content block vertically inside a column (header above, footer/note below), a common half-fix is `.contentBlock{margin:auto 0}` to center it — but if a sibling like `.note{margin-top:auto}` is *also* present (left over from an earlier "push footer down" attempt), the two auto margins split the remaining space unevenly between themselves rather than producing a symmetric above/below gap around the centered block. The visible symptom: content sits noticeably higher than center (e.g. 114px gap above vs. 229px below) even though the intended rule looks like it should center everything.

Fix: for a single element you want vertically centered in the leftover space, exactly one `margin: auto 0` (or `margin-top/bottom: auto` pair) should exist in that flex column — audit every other child in the same flex container for a leftover competing auto margin and remove it.

Verify with the same measured-gap technique as §6 — read `above = centeredEl.top - prevSibling.bottom` and `below = nextSibling.top - centeredEl.bottom` via `getBoundingClientRect()`, and confirm they're equal (or the expected ratio) before calling it balanced. Don't infer "centered" from `align-items:center`/`margin:auto` being present in the CSS — competing auto margins on siblings make the rule not do what it looks like it should.

## Attribution

When the user flags wasted space in a mockup that should fill a fixed host box (e.g. "you're wasting the screen space"):

1. **Find every `max-width`/fixed-width cap** on elements that should stretch (grids, trays, rows) and remove it — a leftover cap from an earlier draft is the most common single cause of a mockup looking cramped inside a much bigger frame.
2. **For a child that must fill remaining vertical space in a flex column, use `flex: 1 1 0` (basis zero), not `flex: 1 1 auto`.** `auto` sizes from content first and only grows from there — if the content (e.g. a CSS grid with `grid-auto-rows: 1fr`) has no definite height of its own, `1 1 auto` will NOT stretch it no matter how much `flex-grow` you add. If a `1fr`/`flex-grow` fix "isn't working" after 2+ attempts tweaking the grid/child itself, the real bug is almost always one level up, in the *parent's* flex-basis — stop iterating on the child and check the parent.
3. **Alternative that sidesteps flex-basis ambiguity entirely:** make the container `display: grid; grid-template-rows: auto 1fr` instead of nested flex — a grid parent guarantees the `1fr` row gets exactly the remaining space, no flex-content-first surprises.
4. **Audit fixed/reserved padding and always-rendered-but-often-empty elements** (bottom padding sized for an absolutely-positioned button that doesn't need that much clearance, a feedback/status dock that reserves height even when empty) — these silently eat the vertical budget the growing element needed. Collapse empty-but-fixed-height elements with `.el:empty { display: none }` instead of always reserving max height.
5. **Verify with real geometry after each fix** (per §6) — confirm the remaining gap below the growing element is *exactly* accounted for by the other fixed-height siblings. Unaccounted gap means there's still a cap or a wrong flex-basis somewhere in the chain.

### 9. After an external edit (Claude Code, another process) lands on a live-served mockup, a blank/broken-looking reload is more likely stale cache than a broken edit — verify before diagnosing

When you `browser_navigate` back to a mockup URL right after a coding CLI finishes editing it and the page comes back empty (`document.body.children.length === 0`, no expected elements in the snapshot, or a `browser_console` eval throws `Cannot read properties of null`), don't jump straight to "the edit broke the file." Check in this order:

1. **Selector-independent sanity probe first**: `document.body.children.length` — a null-property error usually means you evaluated against a selector (`#overlay`) that doesn't match the current markup (`.overlay`), not that the DOM is actually empty.
2. **Hard-reload with a cache-busting query param** (`?v=2`) — a `python3 -m http.server` + open browser tab combo can serve/hold a stale (sometimes empty) response across a file save that landed mid-request.
3. **Independently confirm the file is syntactically valid** and the background server is still alive (`process(action='list')`) before concluding the edit itself broke something:
   ```bash
   node -e "const fs=require('fs'); const html=fs.readFileSync('path/to/mockup.html','utf8'); const m=html.match(/<script>([\s\S]*)<\/script>/); try{new Function(m[1]); console.log('JS syntax OK');}catch(e){console.log('SYNTAX ERROR:', e.message);}"
   ```
4. Only after a fresh cache-busted load against a confirmed-live server with a syntax-valid file still comes back empty do you have real evidence the edit broke rendering.

### 10. When delegating a throwaway mockup/HTML fix to a coding CLI (Claude Code) and it wedges in an over-thinking hang, don't re-delegate — just make the fix directly

Claude Code can get stuck in a silent thinking loop on layout tasks that look bounded but aren't crisply specified ("redesign this to use the space better"): long wall-clock, no new tool output, no `status.md` change. If `claude_orchestrate(action='wait'/'status')` shows `working` unchanged for 5+ minutes, interrupt it once (`action='interrupt'`, non-destructive); if still wedged, kill the session rather than re-steering. For a small self-contained artifact a human could hand-edit in a few `patch` calls (a mockup file, a config tweak) — don't burn a second CLI delegation attempt recovering from the hang. Make the fix directly with `read_file`/`patch` and move on. Reserve a second delegation attempt (different CLI/model) for changes too large to hand-edit practically.

**A second failure shape looks different from a hang and needs the same cutoff instinct: the session reports `done` on every `wait`/`status` poll, but the requested change never lands in the file.** This shows up after several `steer` rounds on a session whose context has grown large — it acknowledges the new instruction, reports `done` almost immediately, and the diff has no corresponding edit. One false-done is worth a single retry-steer; if it repeats across 2+ steer cycles on the same outstanding ask, treat it like a hang — stop re-steering, kill the session, and hand-edit. Don't keep re-asking; the false-done pattern doesn't self-resolve.

**Before hand-editing after a kill (either failure shape), audit what the session actually landed vs. never touched — don't assume every requested item is still outstanding.** A wedged/false-done session commonly got some items of a multi-point ask done before it stalled. Re-navigate the live mockup and read back computed state via `browser_console` (CSS custom properties, class names, `getBoundingClientRect()` per §6) for *every* item in the original request, not just the one you suspect is missing, then diff that against the ask before touching the file — cheaper than re-reading the whole diff/source and avoids reapplying a fix that already landed.

- **Scope creep disguised as thoroughness.** The instinct to "fix it properly while I'm here" is wrong in this mode. Proper here means minimal and literal.
- **Re-screenshotting every round** when a live server was already available — wastes turns and the user already has the URL.
- **Claiming the server is live without checking.** Background HTTP servers die silently; verify with a real request before saying "refresh now."
- **Picking a winner for the user on an element they explicitly said they were unsure about.** That's their call once you've given them a real side-by-side, not yours to make unilaterally.
- **Declaring a layout fix "confirmed" without measuring it.** A screenshot or visual impression is not proof of equal widths, correct wrap count, or no-overflow — pull real `getBoundingClientRect()`/`scrollHeight` numbers before claiming a spatial fix worked.
- **Silently giving up on verification when `browser_vision` errors** (e.g. non-vision routed model). Fall back to `browser_console` DOM assertions instead of shipping the mockup unverified.
- **Trusting a `browser_click` success report on a toggle/tab control without checking the DOM changed.** Nested-clickable markup can make a ref resolve to the wrong node; verify state actually flipped, and if not, drive it via `document.getElementById(...).click()` in `browser_console` instead.
- **Building N×M separate files for a combinatorial variant space** instead of one page with toggle controls that re-render the relevant subtree — multiplies files without multiplying insight, and makes side-by-side comparison harder, not easier.
- **Building the mockup at generic viewport dimensions when the real feature renders inside a fixed/constrained host container** (video overlay, modal, letterboxed frame). Find the host's real sizing logic (e.g. `videoBounds` computation + `inset:0` absolute positioning) and reproduce the exact box — a mockup that "looks right" in a browser tab can still miss overflow/clipping that only appears at the true render dimensions.
- **Inventing placeholder content (fake image URLs, made-up copy) when real fixture data already exists in the repo.** Pull real question text, item lists, and image URLs from the actual test/fixture files — it's not extra work, and it surfaces real content-length edge cases synthetic content won't.
