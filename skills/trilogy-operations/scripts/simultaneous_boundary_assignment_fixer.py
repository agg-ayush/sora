#!/usr/bin/env python3
"""
Two-phase fixer for DI script.md marker-placement failures caused by extreme
marker density (a <break>-delimited segment has more element markers than
word tokens to anchor them on — e.g. 19 [tN] markers over a 6-word segment).

Phase 1 (this file's core contribution): strip every element marker from the
narration and reassign ALL of them SIMULTANEOUSLY per segment — evenly spaced
across that segment's word boundaries, with overflow routed to whichever
other segment still has spare capacity. This avoids the classic bug where
inserting markers one at a time shifts the text under markers inserted
earlier, corrupting their phrases.

Phase 2: run the standard uniqueness-repair loop (see
duplicate_phrase_marker_fixer.py in this same skill) on top of the phase-1
assignment to mop up any remaining phrase collisions.

Content-preserving: only marker *positions* move; words/breaks/s-i markers
are untouched. Always re-run the real checker/parser afterward, and diff
spoken-word text (markers+breaks stripped) old vs new to confirm no wording
changed.

Usage:
    python3 simultaneous_boundary_assignment_fixer.py <script.md path> [more...]

Edits files in place.
"""
import re
import sys

MARKER_RE = re.compile(r"\[([tvi]\d+(?:\.\d+)?|s\d+\.i\d+\.(?:start|end))\]")
ELEM_RE = re.compile(r"\[([tv]\d+(?:\.\d+)?)\]")
BREAK_RE = re.compile(r"<break[^>]*/>")


def elements_of(body):
    return [f"{m.group(2)}{m.group(3)}" for m in
            re.finditer(r"\*\*\[(TEXT|VISUAL) (t|v)(\d+(?:\.\d+)?)\]\*\*", body)]


def clean_text(narr):
    return BREAK_RE.sub(" ", MARKER_RE.sub("", narr))


def phrase_after(narr, marker):
    idx = narr.find(f"[{marker}]")
    if idx == -1:
        return None
    rest = narr[idx + len(marker) + 2:]
    rest = re.split(r"\[|<break", rest)[0].strip()
    return rest


def phrase_count(narr, phrase):
    if not phrase:
        return 0
    return clean_text(narr).count(phrase)


def segments(narr):
    segs, start = [], 0
    for m in BREAK_RE.finditer(narr):
        segs.append((start, m.start()))
        start = m.end()
    if start < len(narr):
        segs.append((start, len(narr)))
    return segs


def word_tokens(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)
            if not MARKER_RE.fullmatch(m.group(0))]


def build(bare, seg_markers_bounds, segs):
    out, cursor = [], 0
    for si, (ts, te) in enumerate(segs):
        out.append(bare[cursor:ts])
        seg = bare[ts:te]
        toks = word_tokens(seg)
        bounds = sorted(seg_markers_bounds.get(si, []), key=lambda x: x[1])
        by_b = {}
        for mk, b in bounds:
            by_b.setdefault(b, []).append(mk)
        newseg = seg
        for b in sorted(by_b, reverse=True):
            pos = toks[min(b, len(toks) - 1)][0] if toks else 0
            while pos < len(newseg) and newseg[pos] == " ":
                pos += 1
            mktext = " ".join(f"[{mk}]" for mk in by_b[b])
            newseg = newseg[:pos] + mktext + " " + newseg[pos:]
        newseg = re.sub(r"[ \t]+", " ", newseg)
        out.append(newseg)
        cursor = te
    out.append(bare[cursor:])
    return "".join(out)


def fix_narration(narr, elems):
    segs = segments(narr)
    seg_of, order_in_seg = {}, {}
    for si, (ts, te) in enumerate(segs):
        for m in MARKER_RE.finditer(narr[ts:te]):
            if m.group(1) in elems:
                order_in_seg.setdefault(si, []).append(m.group(1))
                seg_of[m.group(1)] = si
    for eid in elems:
        if eid not in seg_of:
            order_in_seg.setdefault(0, []).append(eid)
            seg_of[eid] = 0

    bare = re.sub(r"[ \t]+", " ", ELEM_RE.sub("", narr))
    segs = segments(bare)
    W = {si: len(word_tokens(bare[ts:te])) for si, (ts, te) in enumerate(segs)}

    assign = {si: [] for si in range(len(segs))}
    for si, markers in order_in_seg.items():
        cap = W.get(si, 0)
        keep, overflow = (markers, []) if cap and len(markers) <= cap else \
            (markers[:cap], markers[cap:]) if cap else ([], markers)
        M = len(keep)
        for k, mk in enumerate(keep):
            assign[si].append((mk, (k * cap) // M if M else 0))
        for mk in overflow:
            placed = False
            for sj in range(len(segs)):
                if len(assign[sj]) < W.get(sj, 0):
                    assign[sj].append((mk, min(len(assign[sj]), W[sj] - 1)))
                    placed = True
                    break
            if not placed and segs:
                sj = len(segs) - 1
                assign[sj].append((mk, max(0, W.get(sj, 1) - 1)))

    def normalize(a):
        out = {}
        for si, lst in a.items():
            cap = W.get(si, 0)
            lst = sorted(lst, key=lambda x: x[1])
            prev, newl = -1, []
            for mk, b in lst:
                b = max(b, prev + 1)
                if cap:
                    b = min(b, cap - 1)
                    if b <= prev:
                        b = prev + 1 if prev + 1 < cap else prev
                newl.append((mk, b))
                prev = b
            out[si] = newl
        return out

    assign = normalize(assign)
    cur = build(bare, assign, segs)

    # phase 2: uniqueness repair via re-placement search
    for _ in range(300):
        bad = next((e for e in elems if not phrase_after(cur, e) or
                    phrase_count(cur, phrase_after(cur, e)) != 1), None)
        if not bad:
            return cur
        loc = None
        for si, lst in assign.items():
            for k, (mk, b) in enumerate(lst):
                if mk == bad:
                    loc = (si, k)
                    break
            if loc:
                break
        if not loc:
            return cur
        si, k = loc
        moved = False
        for sj in [si] + [x for x in range(len(segs)) if x != si]:
            cap = W.get(sj, 0)
            if not cap:
                continue
            used = {bb for mm, bb in assign[sj] if mm != bad}
            for newb in range(cap):
                if newb in used:
                    continue
                old = assign[si].pop(k)
                assign[sj].append((bad, newb))
                assign = normalize(assign)
                cand = build(bare, assign, segs)
                ph = phrase_after(cand, bad)
                if ph and phrase_count(cand, ph) == 1:
                    cur, moved = cand, True
                    break
                assign[sj] = [(m2, b2) for m2, b2 in assign[sj] if m2 != bad]
                assign[si].insert(k, old)
                assign = normalize(assign)
            if moved:
                break
        if not moved:
            return cur
    return cur


def fix_file(path):
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"(^###\s+.+$)", text, flags=re.M)
    out = parts[0]
    for i in range(1, len(parts), 2):
        heading, body = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        m = re.search(r"(\*\*\[SAY\]\*\*\s*)(.+?)(?=\n\s*\*\*\[|\Z)", body, re.S)
        if m:
            elems = elements_of(body)
            newnarr = fix_narration(m.group(2), elems)
            body = body[:m.start(2)] + newnarr + body[m.end(2):]
        out += heading + body
    if out != text:
        open(path, "w", encoding="utf-8").write(out)
        return True
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        print(("FIXED " if fix_file(p) else "UNCHANGED ") + p)
