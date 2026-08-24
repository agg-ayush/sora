"""Measured layout primitives over python-pptx.

Text is measured with the real font files via PIL before any box is created,
so nothing overflows: every textbox is sized to its content, and callers
assert against the space they have.
"""
from PIL import ImageFont
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from copy import deepcopy

# ── palette ───────────────────────────────────────────────────────────
INK      = "111827"   # near-black
TXT      = "111827"
BODY     = "5B6472"   # body grey
MUTE     = "9CA3AF"
LINE     = "D8DCE2"
LINE_SOFT= "E8EBEF"
TINT     = "F7F8FA"
WHITE    = "FFFFFF"
AMBER    = "9A6212"   # accent on light
AMBER_L  = "E0A44A"   # accent on dark
ICE      = "C6D0E4"
ICE_DIM  = "94A2BE"

SERIF = "Georgia"
SANS  = "Helvetica Neue"

_FILES = {
    ("Georgia", False): "/System/Library/Fonts/Supplemental/Georgia.ttf",
    ("Georgia", True):  "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    ("Helvetica Neue", False): ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("Helvetica Neue", True):  ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
}
_CACHE = {}
PX = 400.0   # measure at 400 units/inch for sub-point accuracy


def _font(name, bold, size_pt):
    key = (name, bold, round(size_pt, 2))
    if key not in _CACHE:
        spec = _FILES[(name, bold)]
        px = int(round(size_pt / 72.0 * PX))
        if isinstance(spec, tuple):
            f = ImageFont.truetype(spec[0], px, index=spec[1])
        else:
            f = ImageFont.truetype(spec, px)
        _CACHE[key] = f
    return _CACHE[key]


def text_w(s, name, bold, size_pt):
    """Width of s in points."""
    if not s:
        return 0.0
    f = _font(name, bold, size_pt)
    return f.getlength(s) / PX * 72.0


def measure(runs, name, size_pt, width_in, line_spacing):
    """Wrap runs into width_in inches; return (height_in, n_lines).

    runs: list of (text, bold) or (text, bold, color).
    Mirrors PowerPoint's greedy word wrap. Includes the internal 0.05in
    left+right textbox insets, which we zero out in textbox(), so we measure
    against the true usable width.
    """
    limit = width_in * 72.0
    # tokenise into (word, bold) keeping spaces attached to the preceding word
    toks = []
    for r in runs:
        t, b = r[0], r[1]
        parts = t.split(" ")
        for i, p in enumerate(parts):
            if i < len(parts) - 1:
                p = p + " "
            if p:
                toks.append((p, b))
    lines, cur, cw = 0, [], 0.0
    for w, b in toks:
        ww = text_w(w, name, b, size_pt)
        wws = text_w(w.rstrip(" "), name, b, size_pt)
        if cur and cw + wws > limit + 0.01:
            lines += 1
            cur, cw = [(w, b)], ww
        else:
            cur.append((w, b))
            cw += ww
    if cur:
        lines += 1
    lines = max(lines, 1)
    h = lines * size_pt * line_spacing / 72.0
    return h, lines


def rgb(hexstr):
    return RGBColor.from_string(hexstr)


# ── shapes ────────────────────────────────────────────────────────────
def _noline(sh):
    sh.line.fill.background()


def rect(s, x, y, w, h, *, fill=None, line=None, lw=0.75):
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                            Inches(w), Inches(h))
    sh.shadow.inherit = False
    if fill:
        sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = rgb(line); sh.line.width = Pt(lw)
    else:
        _noline(sh)
    sh.text_frame.word_wrap = False
    return sh


def rrect(s, x, y, w, h, *, fill=None, line=None, lw=0.75, radius=0.04):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y),
                            Inches(w), Inches(h))
    sh.shadow.inherit = False
    # adjustment is a fraction of the shorter side
    short = min(w, h)
    sh.adjustments[0] = min(radius / short, 0.5) if short else 0.05
    if fill:
        sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = rgb(line); sh.line.width = Pt(lw)
    else:
        _noline(sh)
    return sh


def circle(s, x, y, d, *, fill=INK):
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y),
                            Inches(d), Inches(d))
    sh.shadow.inherit = False
    sh.fill.solid(); sh.fill.fore_color.rgb = rgb(fill)
    _noline(sh)
    return sh


def hrule(s, x, y, w, *, color=LINE, weight=0.75):
    if w <= 0:
        return None
    ln = s.shapes.add_connector(1, Inches(x), Inches(y), Inches(x + w), Inches(y))
    ln.line.color.rgb = rgb(color)
    ln.line.width = Pt(weight)
    return ln


def textbox(s, x, y, w, h, *, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf


def para(tf, runs, *, font, size, color=TXT, spacing=1.3, align=PP_ALIGN.LEFT,
         letter_spacing=None, first=False):
    """Add a paragraph of (text, bold[, color]) runs with exact line spacing."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align
    p.line_spacing = spacing
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    for r in runs:
        t, b = r[0], r[1]
        c = r[2] if len(r) > 2 else color
        run = p.add_run()
        run.text = t
        f = run.font
        f.name = font
        f.size = Pt(size)
        f.bold = b
        f.color.rgb = rgb(c)
        if letter_spacing:
            f._rPr.set("spc", str(int(letter_spacing * 100)))
        # force the same font for latin/complex-script runs
        rPr = f._rPr
        for tag in ("a:latin", "a:cs", "a:ea"):
            el = rPr.find(qn(tag))
            if el is None:
                el = rPr.makeelement(qn(tag), {})
                rPr.append(el)
            el.set("typeface", font)
    return p


def chip(s, x, y, txt, *, size=7.0, h=0.17, color=TXT, line=LINE, fill=WHITE):
    w = text_w(txt, SANS, False, size) / 72.0 + 0.11
    rrect(s, x, y, w, h, fill=fill, line=line, lw=0.6, radius=0.02)
    tf = textbox(s, x, y, w, h, anchor=MSO_ANCHOR.MIDDLE)
    para(tf, [(txt, False)], font=SANS, size=size, color=color,
         align=PP_ALIGN.CENTER, spacing=1.0, first=True)
    return w


def arrow(s, cx, cy, *, color=MUTE, size=14, label=None, label_color=MUTE):
    """A small right-pointing chevron centred at (cx, cy), plus optional caption."""
    w = size / 72.0 * 0.85
    h = size / 72.0 * 0.85
    sh = s.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE,
                            Inches(cx - w / 2), Inches(cy - h / 2),
                            Inches(w), Inches(h))
    sh.rotation = 90
    sh.shadow.inherit = False
    sh.fill.solid(); sh.fill.fore_color.rgb = rgb(color)
    _noline(sh)
    if label:
        lw = 1.0
        tf = textbox(s, cx - lw / 2, cy + h / 2 + 0.05, lw, 0.14)
        para(tf, [(label, False)], font=SANS, size=6.2, color=label_color,
             align=PP_ALIGN.CENTER, letter_spacing=0.8, spacing=1.0, first=True)
    return sh
