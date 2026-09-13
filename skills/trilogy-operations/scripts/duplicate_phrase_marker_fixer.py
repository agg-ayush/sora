#!/usr/bin/env python3
"""
Fix DI script.md marker-placement failures where the gate is:
  "the phrase after marker X, up to the next marker or <break>, must occur
   exactly once in the whole cleaned narration" (see marker-resolve-check.py
   style checkers, and stages/ingest/src/parser.py's uniqueness contract).

Handles two failure modes:
  - duplicate phrase: two markers resolve to the identical trailing text
  - empty phrase: a marker sits flush against another marker or a <break>

Content-preserving: only marker *positions* move, no wording changes.
Always re-run the real checker/parser after this as the final word --
this script's internal bookkeeping is a heuristic, not the gate itself.

Usage:
    python3 duplicate_phrase_marker_fixer.py <script.md path> [more paths...]

Edits files in place. Prints per-file before/after unresolved counts.
"""
import re
import sys

MARKER_RE = re.compile(r"\[([tvi]\d+(?:\.\d+)?|s\d+\.i\d+\.(?:start|end))\]")
BREAK_RE = re.compile(r"<break[^>]*/>")


def clean_text(narr):
    c = MARKER_RE.sub("", narr)
    c = BREAK_RE.sub(" ", c)
    return c


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


def remove_marker(narr, marker):
    idx = narr.find(f"[{marker}]")
    if idx == -1:
        return narr
    end = idx + len(marker) + 2
    if end < len(narr) and narr[end] == " ":
        end += 1
    new = narr[:idx] + narr[end:]
    return re.sub(r"[ \t]{2,}", " ", new)


def word_positions(narr):
    """Yield (start, end, word) for word tokens, skipping markers/breaks."""
    masked = MARKER_RE.sub(lambda m: " " * (m.end() - m.start()), narr)
    masked = BREAK_RE.sub(lambda m: " " * (m.end() - m.start()), masked)
    for m in re.finditer(r"\S+", masked):
        yield m.start(), m.end(), m.group(0)


def unresolved(narr, elems):
    return [
        e
        for e in elems
        if (lambda ph: not ph or phrase_count(narr, ph) != 1)(phrase_after(narr, e))
    ]


def fix_slide(narr, elems):
    """elems: ordered list of marker ids (e.g. 't1', 'v2.3') declared for the slide."""
    for _ in range(len(elems) * 4 + 10):
        bad = unresolved(narr, elems)
        if not bad:
            break
        target = bad[0]
        base = remove_marker(narr, target)
        best, best_bad = None, len(bad)
        for ws, _, _ in word_positions(base):
            cand = base[:ws] + f"[{target}] " + base[ws:]
            ph = phrase_after(cand, target)
            if not ph:
                continue  # empty-phrase placement never allowed
            badn = len(unresolved(cand, elems))
            if badn < best_bad:
                best, best_bad = cand, badn
                if badn < len(bad):
                    break
        if best is not None and best_bad < len(bad):
            narr = best
        else:
            if f"[{target}]" not in narr:
                narr = f"[{target}] " + base
            break  # cannot improve further; stop to avoid looping
    return narr


def fix_file(path):
    text = open(path).read()
    parts = re.split(r"(^###\s+.+$)", text, flags=re.M)
    out = parts[0]
    for i in range(1, len(parts), 2):
        heading, body = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        m = re.search(r"(\*\*\[SAY\]\*\*\s*)(.+?)(?=\n\s*\*\*\[|\Z)", body, re.S)
        if m:
            elems = [
                f"{mm.group(2)}{mm.group(3)}"
                for mm in re.finditer(
                    r"\*\*\[(TEXT|VISUAL) (t|v)(\d+(?:\.\d+)?)\]\*\*", body
                )
            ]
            before = len(unresolved(m.group(2), elems))
            newnarr = fix_slide(m.group(2), elems)
            after = len(unresolved(newnarr, elems))
            if before or after:
                print(f"  {heading.strip()}: {before} -> {after} unresolved")
            body = body[: m.start(2)] + newnarr + body[m.end(2):]
        out += heading + body
    open(path, "w").write(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        print(f"== {p}")
        fix_file(p)
