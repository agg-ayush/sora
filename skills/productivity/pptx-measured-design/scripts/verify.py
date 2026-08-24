"""Verify the rendered PDF: no text outside its card, dots aligned to their text.

Usage: python verify.py [render/<deck>.pdf]
Defaults to the only .pdf in render/.
"""
import glob
import sys
import fitz

if len(sys.argv) > 1:
    path = sys.argv[1]
else:
    found = sorted(glob.glob('render/*.pdf'))
    if not found:
        sys.exit("no PDF in render/ — run the soffice conversion first")
    path = found[0]

d = fitz.open(path)
bad = []

for pi, p in enumerate(d):
    pn = pi + 1
    p.get_pixmap(dpi=110).save(f'render/s{pn}.png')
    spans = [s for b in p.get_text('dict')['blocks']
             for l in b.get('lines', []) for s in l['spans']]

    # dot alignment
    for dr in p.get_drawings():
        r = dr['rect']
        if not (2 < r.width < 6 and 2 < r.height < 6):
            continue
        cand = sorted([s for s in spans
                       if s['bbox'][0] > r.x1 - 1
                       and abs((s['bbox'][1] + s['bbox'][3]) / 2
                               - (r.y0 + r.y1) / 2) < 9],
                      key=lambda s: s['bbox'][0])
        if not cand:
            continue
        s = cand[0]
        dy = (r.y0 + r.y1) / 2 - (s['bbox'][1] + s['bbox'][3]) / 2
        if abs(dy) > 1.6:
            bad.append(f"p{pn} dot off {dy:+.2f} near '{s['text'][:26]}'")

    # text inside page margins
    W, H = p.rect.width, p.rect.height
    for s in spans:
        x0, y0, x1, y1 = s['bbox']
        if x0 < 6 or x1 > W - 6 or y0 < 2 or y1 > H - 6:
            bad.append(f"p{pn} text at edge '{s['text'][:26]}' box={x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}")

    # text must not cross a card's bottom/right border
    cards = [dr['rect'] for dr in p.get_drawings()
             if dr['rect'].width > 60 and dr['rect'].height > 30]
    for s in spans:
        sb = fitz.Rect(s['bbox'])
        for c in cards:
            # span starts inside the card horizontally and vertically overlaps it
            if sb.x0 > c.x0 + 1 and sb.x0 < c.x1 - 1 and sb.y0 > c.y0 - 1 and sb.y0 < c.y1 - 1:
                if sb.y1 > c.y1 + 1.5 or sb.x1 > c.x1 + 1.5:
                    bad.append(f"p{pn} span escapes card '{s['text'][:24]}'")
                break

seen, out = set(), []
for b in bad:
    if b not in seen:
        seen.add(b)
        out.append(b)

print(f"pages: {d.page_count}")
if out:
    print("ISSUES:")
    for b in out[:40]:
        print(" ", b)
    sys.exit(1)
print("render check: clean")
