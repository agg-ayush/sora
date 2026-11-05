# CSS/layout pitfalls for HTML mockup verification

Depth file for `mockup-review-iteration`: the measured-geometry technique and
the CSS-specific failure modes seen in real mockup rounds. The SKILL.md keeps
the workflow rules; this file keeps the layout mechanics.

## Measure layout claims with computed geometry, not eyeballing

For anything spatial (equal widths, row/column wrap count, centering,
overflow, gap sizes), read back real geometry via `browser_console` against
`getBoundingClientRect()`/`scrollHeight`/`clientHeight` and report the actual
numbers — exact and cheap to re-run every round.
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

**For drag-and-drop mockups, verify drop-state layout by calling the
mockup's own state functions directly in `browser_console` instead of
simulating real pointer drag events** — real HTML5 drag-and-drop is painful
to script reliably. If the mockup exposes helpers like `fixture()`,
`move(itemId, targetId)`, `render()`, call them to force the state, then
measure geometry (e.g. count distinct `top` values among tiles in a zone to
confirm a 2×2 wrap vs a single row).

When the user asks "what if X were the worst case" (longer question, more
options, longest word), build that literal worst-case variant as a new block
and measure it — don't reason abstractly. **Combine stressors, don't test
one axis at a time**: a worst-case pass that tests each axis separately
misses the case where they combine (a 2-line question AND an image together
can overflow a fixed-height section even though each alone fit). Build at
least one block stacking ALL plausible stressors and measure that.

## Mode-independent sizing

When a feature exists in multiple host modes (sidebar vs fullscreen/overlay),
don't silently carry a size constraint from the cramped mode into the
spacious one — a height cap that exists in the sidebar version is very often
an artifact of that mode's limited real estate, not a design constant. When
in doubt, ask, or default to letting the spacious mode use its own space and
say so explicitly. Same for target counts: don't assume 2 vs 4 targets need
different heights unless asked — "uniform proportional sizing" is often
wanted; confirm before diverging.

## Proportional sizing for runtime-resized host containers

If the real host container varies at runtime (ResizeObserver-driven video
overlay, responsive panel), don't harden a mockup dimension to a fixed px
value. Compute it as a fraction of the frame's measured dimensions in JS
(`targetHeight = frameHeight * FRACTION`), store it in a CSS variable, and
re-derive on every render/resize/fixture-switch. When unclear whether a
number should be fixed or proportional, ask rather than guess.

## Pinning a container that collapses when emptied

A flex/grid container sized only by content shrinks when items are removed
("the tray shrinks when empty"). Fix with measure-after-render, not a
guessed min-height constant:

```js
requestAnimationFrame(() => {
  const h = trayEl.offsetHeight;
  if (h > 0) trayEl.style.setProperty('--tray-min-height', h + 'px');
});
```
```css
.tray-strip { min-height: var(--tray-min-height, 110px); }
```

Verify per the geometry technique: measure with items, clear, re-measure,
assert the numbers match.

## Shared selectors: parameterize, never hardcode per-variant literals

A shared CSS rule used by multiple layout variants (e.g. 2-target vs
4-target) will silently regress every OTHER variant when you hardcode a
literal fix for one of them. The edit target is correct and singular, but
the shared class/selector fans it out to siblings invisibly.

Fix: never hardcode a spacing/sizing literal on a selector shared across
variants. Compute it in JS per-variant (keyed off `fixture().targets.length`
or equivalent) into a CSS custom property, derived from measured geometry so
it can't clip:

```js
const maxColGap = Math.max(4, targetWidth - PADDING - tileSize * 2 - MARGIN);
const colGap = targetCount <= 2 ? Math.min(45, maxColGap) : Math.min(8, maxColGap);
document.documentElement.style.setProperty('--in-zone-col-gap', colGap + 'px');
```
```css
.drop-inner.images { column-gap: var(--in-zone-col-gap, 8px); }
```

After the fix, verify EVERY variant that shares the selector, not just the
one in the ask.

## Centering empty-state text: both axes

`.placeholder { text-align: center }` handles horizontal centering of
wrapped text, but a flex container also needs `justify-content: center` on
its main axis (and `align-items: center` on cross) to actually center the
block within an empty tray/target. Check both properties, not just one.

## Grid items: percentage heights need explicit row tracks

A percentage `height` on a CSS Grid *item* resolves against nothing unless
the grid has explicit row tracks. Setting `height: 42%` on a grid item
inside `display:grid; grid-auto-rows: auto` collapses the tile to its
intrinsic content height.

Fix: give the grid explicit tracks consuming the full container height —
`grid-template-rows: 1fr 1fr` — then set the item's `height: 100%` (of its
now-definite row track). The percentage that matters is the ratio between
tracks, not a height percentage on the child. Same root cause as the
flex-basis pitfall below (percentage/flex-grow resolving against an
undefined parent dimension), different layout mode.

## Aspect-ratio-locked images: size the tile on ONE axis

When a tile/card contains an `aspect-ratio`-locked image, size the tile with
ONE dimension (width) as the percentage/CSS var and let the other be `auto`
— splitting width and height into two independent percentages (or capping
via `max-height` on the image) fights the aspect-ratio and silently squishes
the image (e.g. a 152×152 tile rendering a 152×79 image).

```css
.tile.in-zone {
  width: var(--in-zone-tile-w, 42%);
  height: auto;            /* let content (image aspect-ratio) drive it */
  overflow: visible;
}
.tile.in-zone .tile-img {
  width: 100%;
  height: auto;            /* NOT max-height — let aspect-ratio own the height */
  aspect-ratio: 1/1;
}
```

To still guarantee N rows fit the target's actual height, compute the width
cap in JS from BOTH target dimensions before writing the CSS var:

```js
const capWpct = (((targetHeightPx - gapFrac * targetWidthPx) / rows - labelSpacePx) / targetWidthPx) * 100;
const tileWpct = Math.min(desiredWpct, Math.max(minWpct, Math.round(capWpct)));
```

Verify by asserting `imgWidth === imgHeight` (within ~2px) via
`getBoundingClientRect()` on the rendered image — a non-square image can
pass a "did it clip" check while being visibly squished.

## box-sizing on JS-var-driven fixed track sizes

A row track sized by a JS-computed CSS var (e.g. `grid-template-rows:
var(--tray-height) 1fr`) is meant to be the element's TOTAL box height, but
`box-sizing: content-box` is the default: `height: 144px` + `padding: 18px`
+ border renders 164px, bleeding into the next row/sibling (reads as "two
sections aren't stacking cleanly"). Easy to miss because siblings often
already have `border-box` explicitly while one element was overlooked.

Fix: any element whose height is driven by a JS-computed CSS variable used as
a fixed grid/flex track size must have `box-sizing: border-box` set
explicitly. Verify with real geometry: `sectionA.bottom <= sectionB.top`, and
`getComputedStyle(sectionA).boxSizing === 'border-box'` on the var-driven
element.

## Competing auto margins

Two flex children each carrying their own `margin: auto` in the same axis
fight each other — the two auto margins split the remaining space unevenly
rather than centering the block (symptom: visibly off-center content despite
a rule that "looks" right). For a single element centered in the leftover
space, exactly ONE `margin: auto 0` should exist in that flex column; audit
siblings for leftover competing auto margins and remove them. Verify by
measuring above/below gaps via `getBoundingClientRect()` and confirming they
match.

## Wasted space in a fixed host box (checklist)

When the user flags wasted space in a mockup that should fill a fixed host
box:

1. Find every `max-width`/fixed-width cap on elements that should stretch
   and remove it — a leftover cap from an earlier draft is the most common
   single cause of a cramped mockup.
2. For a child that must fill remaining vertical space in a flex column, use
   `flex: 1 1 0` (basis zero), not `flex: 1 1 auto`. `auto` sizes from
   content first; if the content has no definite height, `1 1 auto` won't
   stretch it no matter the flex-grow. If a `1fr`/flex-grow fix "isn't
   working" after 2+ attempts on the child, the real bug is almost always one
   level up in the parent's flex-basis.
3. Alternative that sidesteps flex-basis ambiguity: `display: grid;
   grid-template-rows: auto 1fr` — a grid parent guarantees the `1fr` row
   gets exactly the remaining space.
4. Audit fixed/reserved padding and always-rendered-but-often-empty elements
   (bottom padding for an absolutely-positioned button, a feedback dock that
   reserves height when empty) — collapse them with `.el:empty { display:
   none }` instead of always reserving max height.
5. Verify with real geometry after each fix — the remaining gap below the
   growing element should be exactly accounted for by the other fixed-height
   siblings; unaccounted gap means a cap or wrong flex-basis remains.
