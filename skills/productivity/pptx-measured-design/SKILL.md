---
name: pptx-measured-design
description: Build designed .pptx decks whose text provably fits — measure every text box against the real font file before placing it, then verify the rendered PDF. Use when asked for a PowerPoint/pptx/deck/slides that must look designed (not a template bullet dump), when porting an approved HTML mockup to pptx, or when a generated deck has overflowing/clipped/misaligned text.
---

# Measured pptx design

Generating a deck blind produces overflow. The fix is to **measure before you place** and
**verify what actually rendered**, never the source you wrote.

Two invariants:

1. **No box is created before its content is measured.** Height comes from wrapping the real
   text with the real font file (PIL), so a box is exactly as tall as it needs to be.
2. **Nothing is judged by eye.** A build-time budget assert catches overflow; a render-time
   PDF check catches escapes and misalignment. Vision is a last sanity pass only.

## When to use

- "Make it a ppt / pptx / PowerPoint", designed slides, a conference or bootcamp deck.
- Porting a signed-off HTML mockup into pptx.
- Fixing a deck where text clips, overlaps, or spills out of cards.

## Setup

```bash
mkdir -p <deck-dir> && cd <deck-dir>
python3 -m venv .venv
.venv/bin/pip install python-pptx Pillow pymupdf
brew install --cask libreoffice     # only if `soffice` is missing
```

`soffice` lands on PATH at `/opt/homebrew/bin/soffice` (Apple Silicon). The cask install takes
**10–15 minutes** — start it in the background with `notify_on_complete=true` and do other
setup while it runs. Verify with `soffice --version`.

Copy the two assets from this skill into the deck dir:

- `scripts/lib_deck.py` — measured layout primitives (measure, textbox, para, rect, rrect,
  circle, hrule, chip, arrow) + palette. Never edit per-deck; import it.
- `scripts/verify.py` — render-time PDF checker.

## Build loop

Write `build.py` importing `lib_deck`, then run this until both lines are clean:

```bash
cd <deck-dir>
.venv/bin/python build.py && \
soffice --headless --convert-to pdf --outdir render <deck>.pptx && \
.venv/bin/python verify.py
```

Success is exactly two lines: `layout: no overflow` and `render check: clean`.

## Rules that make it work

**Canvas.** 16:9 is `13.333 × 7.5` in. Set `prs.slide_width/height` explicitly; the default is
4:3. Use one page margin constant (`M = 0.62`) and hang everything off it. Work in inches as
floats; let `Inches()` convert at the boundary.

**Every text box is measured.** Call `measure(runs, font, size, width, line_spacing)` →
`(height_in, n_lines)`, then create the box at that exact height. `measure()` mirrors
PowerPoint's greedy word wrap and accounts for the 0.05in insets that `textbox()` zeroes out.

**Assert your budgets.** Keep a `check(name, need, have)` that appends to a `problems` list and
print them at the end. A silent build that "looks fine" is the failure mode this prevents.

```python
problems = []
def check(name, need, have):
    if need > have + 1e-6:
        problems.append(f"OVERFLOW {name}: needs {need:.3f}in, has {have:.3f}in")
    return need
# ...at the end:
print("\n".join(problems) or "layout: no overflow")
```

**Never cut approved content to fit — scale the type.** For dense regions, binary/linear search
the largest font size that fits the measured budget:

```python
def fit_size(fn, budget, hi, lo=5.6, step=0.05):
    """Largest size in [lo, hi] whose measured height fits budget."""
    best = lo
    for i in range(int((hi - lo) / step) + 1):
        sz = round(hi - i * step, 3)
        if fn(sz) <= budget:
            return sz
        best = sz
    return best
```

If the search bottoms out at `lo`, the *container* is too small — grow the card or reduce the
region, don't lower `lo`. **Scale headers with the body** in a fit search: fixed-size headings
inside an auto-fitting card make the search hit its floor while space sits unused above.

**Bullet dots must be offset by the line box, not a guess.** A dot centred on the first line
sits at `y + size * spacing / 72 * DOT_F - dot/2` with `DOT_F = 0.90`. Any factor derived by
eye is wrong proportionally to font size — small text looks fine, large text visibly floats.

**Font consistency.** `para()` writes `a:latin`, `a:cs`, and `a:ea` typefaces on every run;
without that PowerPoint substitutes a different face for some runs. Use system faces
(Georgia + Helvetica Neue) so the deck renders identically elsewhere.

**Kill inherited shadows.** `sh.shadow.inherit = False` on every autoshape, or the theme adds a
drop shadow you didn't ask for.

**Images.** Convert webp → png first (`sips -s format png in.webp --out out.png`); python-pptx
won't take webp. Pass only `height=` to `add_picture` and derive width from the real aspect
ratio so nothing stretches.

## Porting an approved HTML mockup

The mockup is the source of truth for **proportions**, and nesting is easy to get wrong by
reading CSS. Measure the live DOM instead of inferring:

```javascript
[...document.querySelectorAll('#slide2 .col, #slide2 .strip, #slide2 .board')]
  .map(e => ({ cls: e.className, ...e.getBoundingClientRect().toJSON() }))
```

Compare parent/child rects to learn what is actually *inside* what. A real failure here: the
strip and board were nested inside column B, but the pptx port laid them full-width, which
starved column A of height. Reproduce the nesting, not the visual guess.

Diagrams must be native shapes and connectors — never a flattened screenshot pasted in.

## Verification order

1. `build.py` budget asserts → catches content that cannot fit.
2. `verify.py` on the rendered PDF → catches spans escaping a card, crossing a page margin, or
   dots misaligned from their text. This inspects **PyMuPDF glyph boxes**, which is why it
   finds sub-point errors.
3. Vision pass on the PNGs, last, for taste only.

Trust the geometry over vision. Vision reported a "clipped top bar" on a bar that
`get_drawings()` proved spanned `0 → 959.92pt` — full width. It also described a dot problem
only vaguely that the PDF check pinned to `-2.04pt`.

## Pitfalls

- Default presentation size is 4:3 — set 16:9 explicitly.
- `MSO_AUTO_SIZE.NONE` + `word_wrap = True` + zeroed margins, or measured heights won't match.
- Set `line_spacing` as a float multiple and `space_before/after = Pt(0)`; PowerPoint's default
  paragraph spacing silently adds height your measurement doesn't know about.
- Don't reuse a slide layout with placeholders — use `prs.slide_layouts[6]` (blank).
- LibreOffice caches: if the PDF looks stale, delete `render/` and re-convert.
- Re-run the *whole* loop after any edit. A change to one card's font size shifts everything
  below it.
