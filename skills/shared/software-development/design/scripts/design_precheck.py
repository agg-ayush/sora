#!/usr/bin/env python3
"""Structural pre-check for a design document. Stdlib only, Python 3.9.

Usage: design_precheck.py <design.md> [--nb NB1,NB2]
Exit 0 prints "ok" (plus warnings). Exit 1 prints the problem list.
Importable: check(path, nb_ids=None) -> (ok, problems, warnings).
"""
import re
import sys

CORE_SECTIONS = [
    ("problem", r"\bproblem\b"),
    ("requirements", r"\brequirements?\b"),
    ("grounding", r"\bgrounding\b"),
    ("approach", r"\bapproach\b"),
    ("behaviour model", r"\b(behaviou?r(al)?|state) model\b"),
    ("interfaces and data shapes", r"\binterfaces?\b|\bdata shapes?\b"),
    ("verification", r"\bverification\b"),
    ("may decide", r"\bmay decide\b"),
    ("must escalate", r"\bmust escalate\b"),
    ("build sequence", r"\bbuild sequence\b"),
    ("failure modes", r"\bfailure[- ]modes?\b"),
    ("rollback", r"\brollback\b"),
    ("open questions", r"\bopen questions?\b"),
]
MODULE_SECTIONS = {"ui": r"\bui\b", "risk": r"\brisk\b"}
TABLE_COLUMNS = [
    ("id", r"^(id|req|requirement|row)"),
    ("test", r"\btest"),
    ("level", r"\blevel\b"),
    ("observable asserted", r"observable|assert"),
    ("wrong implementation caught", r"wrong|mutant|catch"),
]
VAGUE_WORDS = re.compile(
    r"\b(fast|faster|clean|intuitive|robust|user[- ]friendly)\b", re.I)
PLACEHOLDER = re.compile(r"\bTBD\b|\bTODO\b|\.\.\.|\u2026")
CITATION = re.compile(r"[\w./@-]+\.\w+:\d+(?:-\d+)?")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RID = re.compile(r"\bR\d+\b")
TID = re.compile(r"\bT\d+\b")
NBID = re.compile(r"\bNB\d+\b")
LEGACY_MSG = (
    "missing design-meta header: legacy design docs are not accepted. Start the "
    "document with a fenced block containing "
    "`design-meta: tier=<light|full> modules=<ui,risk|none>` (add a "
    "`revision: <n>` line on revisions).")


def _split_fences(lines):
    """Return (prose_lines, code_line_count, first_fence_block)."""
    prose, code, first, in_fence, cur = [], 0, None, False, []
    for ln in lines:
        if ln.lstrip().startswith("```"):
            if in_fence:
                in_fence = False
                if first is None:
                    first = cur
                cur = []
            else:
                in_fence = True
                cur = []
            prose.append("")
            continue
        if in_fence:
            cur.append(ln)
            code += 1
            prose.append("")
        else:
            prose.append(ln)
    return prose, code, first


def _parse_meta(lines):
    """Read design-meta from the first fenced block within the first lines."""
    head = lines[:40]
    start = None
    for i, ln in enumerate(head):
        if ln.lstrip().startswith("```"):
            start = i
            break
        if ln.strip():
            return None
    if start is None:
        return None
    block = []
    for ln in head[start + 1:]:
        if ln.lstrip().startswith("```"):
            break
        block.append(ln)
    meta, found = {}, False
    for ln in block:
        s = ln.strip()
        if s.startswith("design-meta:"):
            found = True
            for k, v in re.findall(r"(\w+)=([^\s]+)", s):
                meta[k.lower()] = v
        m = re.match(r"revision\s*[:=]\s*(\d+)", s)
        if m:
            meta["revision"] = m.group(1)
        for k, v in re.findall(r"\brevision=(\d+)", s):
            meta["revision"] = v
    return meta if found else None


def _sections(prose):
    """List of (level, title, body_lines) with nested bodies included."""
    heads = []
    for i, ln in enumerate(prose):
        m = HEADING.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    out = []
    for idx, (i, lvl, title) in enumerate(heads):
        end = len(prose)
        for j, l2, _ in heads[idx + 1:]:
            if l2 <= lvl:
                end = j
                break
        body = [b for b in prose[i + 1:end] if not HEADING.match(b)]
        out.append((lvl, title, body))
    return out


def _has_content(body):
    return any(b.strip() for b in body)


def _find(sections, pattern):
    rx = re.compile(pattern, re.I)
    return [s for s in sections if rx.search(s[1])]


def _table_rows(body):
    """Return list of tables; each is (header_cells, [row_cells])."""
    tables, i = [], 0
    while i < len(body):
        if body[i].strip().startswith("|") and i + 1 < len(body) and re.match(
                r"^\s*\|?[\s:|-]+\|[\s:|-]*$", body[i + 1]):
            header = [c.strip() for c in body[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(body) and body[j].strip().startswith("|"):
                rows.append([c.strip() for c in body[j].strip().strip("|").split("|")])
                j += 1
            tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


def _map_columns(header):
    mapping = {}
    for name, pat in TABLE_COLUMNS:
        for idx, cell in enumerate(header):
            if re.search(pat, cell.strip().lower()) and idx not in mapping.values():
                mapping[name] = idx
                break
    return mapping


def check(path, nb_ids=None):
    """Return (ok, problems, warnings) for the design at path."""
    problems, warnings = [], []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return False, ["cannot read %s: %s" % (path, exc)], []
    lines = text.splitlines()
    meta = _parse_meta(lines)
    if meta is None:
        return False, [LEGACY_MSG], []

    tier = meta.get("tier", "")
    if tier not in ("light", "full"):
        problems.append("design-meta tier must be light or full (got %r)" % tier)
    mods_raw = meta.get("modules", "none")
    modules = [] if mods_raw == "none" else [m for m in mods_raw.split(",") if m]
    for m in modules:
        if m not in MODULE_SECTIONS:
            problems.append("design-meta lists unknown module %r (allowed: ui, risk)" % m)
    try:
        revision = int(meta.get("revision", "1"))
    except ValueError:
        revision = 1
        problems.append("design-meta revision is not a number")

    prose, code_lines, _ = _split_fences(lines)
    sections = _sections(prose)

    found = {}
    for name, pat in CORE_SECTIONS:
        hits = _find(sections, pat)
        if name == "requirements" and not hits:
            hits = [h for h in _find(sections, CORE_SECTIONS[0][1])
                    if RID.search("\n".join(h[2]))]
        if not hits:
            problems.append("missing section: %s" % name)
        elif not any(_has_content(h[2]) for h in hits):
            problems.append("empty section: %s" % name)
        else:
            found[name] = [h for h in hits if _has_content(h[2])][0]
    for m in modules:
        if m in MODULE_SECTIONS:
            hits = _find(sections, MODULE_SECTIONS[m])
            if not hits:
                problems.append("missing module section: %s" % m)
            elif not any(_has_content(h[2]) for h in hits):
                problems.append("empty module section: %s" % m)

    prob = found.get("problem")
    if prob and not re.search(r"non[- ]?goals?", prob[1] + " ".join(prob[2]), re.I):
        problems.append("problem section does not state non-goals")

    approach = found.get("approach")
    if approach and tier == "full" and "alternative" not in " ".join(approach[2]).lower():
        problems.append("full tier approach lists no alternatives")

    # requirements and verification table
    req = found.get("requirements")
    req_ids = []
    if req:
        req_ids = sorted(set(RID.findall("\n".join(req[2]))), key=lambda s: int(s[1:]))
        if not req_ids:
            problems.append("requirements section has no ids (R1, R2, ...)")
        for ln in req[2]:
            m = VAGUE_WORDS.search(ln)
            if m and not re.search(r"\d", RID.sub("", ln)):
                warnings.append(
                    "unquantified adjective %r in requirement: %s" % (m.group(1), ln.strip()[:80]))

    ver = found.get("verification")
    table_text = ""
    if ver:
        tables = _table_rows(ver[2])
        best = None
        for header, rows in tables:
            cols = _map_columns(header)
            if best is None or len(cols) > len(best[1]):
                best = (header, cols, rows)
        if best is None:
            problems.append("verification section has no table")
        else:
            header, cols, rows = best
            missing = [n for n, _ in TABLE_COLUMNS if n not in cols]
            if missing:
                problems.append(
                    "verification table missing columns: " + ", ".join(missing))
            else:
                for row in rows:
                    for col in ("observable asserted", "wrong implementation caught"):
                        idx = cols[col]
                        if idx >= len(row) or not row[idx].strip() or PLACEHOLDER.search(row[idx]):
                            problems.append(
                                "verification row '%s' has an empty %s cell"
                                % (row[0][:30] if row else "?", col))
            table_text = "\n".join(" ".join(r) for r in rows)
        for rid in req_ids:
            if not re.search(r"\b%s\b" % rid, table_text):
                problems.append("requirement %s has no row in the verification table" % rid)
        bm = found.get("behaviour model")
        if bm:
            for tid in sorted(set(TID.findall("\n".join(bm[2]))), key=lambda s: int(s[1:])):
                if not re.search(r"\b%s\b" % tid, table_text):
                    problems.append(
                        "behaviour transition %s has no row in the verification table" % tid)

    ground = found.get("grounding")
    if ground:
        cites = CITATION.findall("\n".join(ground[2]))
        need = 3 if tier == "full" else 1
        if len(cites) < need:
            problems.append(
                "grounding has %d path:line citations (need at least %d)" % (len(cites), need))

    scan = "\n".join(re.sub(r"`[^`]*`", "", ln) for ln in prose)
    seen = set()
    for n, ln in enumerate(scan.splitlines(), 1):
        for m in PLACEHOLDER.finditer(ln):
            key = (n, m.group(0))
            if key not in seen:
                seen.add(key)
                problems.append("placeholder %r at line %d" % (m.group(0), n))

    if revision >= 2:
        cs = _find(sections, r"changes since review")
        if not cs or not any(_has_content(s[2]) for s in cs):
            problems.append(
                "revision %d needs a non-empty 'Changes since review' section" % revision)
        else:
            body = [b for s in cs for b in s[2]]
            for ln in body:
                if NBID.search(ln) and not re.search(r"adopted|rejected", ln, re.I):
                    problems.append(
                        "Changes since review line has an NB id without adopted or rejected: %s"
                        % ln.strip()[:80])
            joined = "\n".join(body)
            for nb in nb_ids or []:
                if not re.search(r"\b%s\b" % re.escape(nb), joined):
                    problems.append("Changes since review does not answer %s" % nb)

    limit = 200 if tier == "light" else 500
    if len(lines) > limit:
        warnings.append(
            "design is %d lines (soft limit %d for %s): check the detail limit"
            % (len(lines), limit, tier or "?"))
    if code_lines > 40:
        warnings.append(
            "%d lines of fenced code: name decisions, not code" % code_lines)

    return (not problems), problems, warnings


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    nb = None
    if "--nb" in argv:
        i = argv.index("--nb")
        if i + 1 < len(argv):
            nb = [x for x in argv[i + 1].split(",") if x]
            args = [a for a in args if a != argv[i + 1]]
    if len(args) != 1:
        print("usage: design_precheck.py <design.md> [--nb NB1,NB2]", file=sys.stderr)
        return 2
    ok, problems, warnings = check(args[0], nb)
    if ok:
        print("ok")
        for w in warnings:
            print("warning: " + w)
        return 0
    print("design pre-check failed (%d problems):" % len(problems))
    for p in problems:
        print("- " + p)
    for w in warnings:
        print("warning: " + w)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
