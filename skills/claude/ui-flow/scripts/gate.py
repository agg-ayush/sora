#!/usr/bin/env python3
"""ui-flow gate: deterministic phase state + quality gates for the ui-flow skill.

Usage (run from the user's project root):
  gate.py status                                  # current phase, artifacts, next step
  gate.py set-phase <phase> [--force]             # record a phase transition (enforces exit gates unless --force)
  gate.py detect <target>... [--mobile] [--wide]  # run impeccable detector (--mobile 390x844; --wide 1440x900 + 1920x1080, URLs only)
  gate.py brief <brief.md>                        # check shape brief headings + preference ids P1..P12, PASS/FAIL
  gate.py lint <file-or-dir>...                   # mechanical source checks (native select, bare disabled, fixed px sizes)
  gate.py critique <score> <max> <p0>             # record a critique result, PASS/FAIL
  gate.py prefs <failed> <checked>                # check all P1..P12; PASS iff failed == 0 and checked == 12

State lives in .ui-flow/state.json. Exit code 0 = PASS, 1 = FAIL (gate blocked), 2 = usage/tool error.
"""
import glob
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

PHASES = ["setup", "shape", "build", "refine", "review", "ship", "done"]
STATE_DIR = ".ui-flow"
STATE_FILE = os.path.join(STATE_DIR, "state.json")

CRITIQUE_PASS_RATIO = 0.75  # e.g. 30/40
MAX_REFINE_ROUNDS = 3
MAX_COMMANDS_PER_ROUND = 3

# Ordered: first match wins. Keyword is matched against the antipattern id + name.
# Earlier rows are higher priority when picking which commands to run.
RULE_MAP = [
    (("contrast",), "colorize"),
    (("focus", "aria", "alt-text", "label", "a11y", "tap-target", "touch"), "harden"),
    (("viewport", "overflow", "responsive", "mobile", "breakpoint"), "adapt"),
    (("font", "type", "line-height", "line-length", "heading", "letter", "text-size"), "typeset"),
    (("spacing", "padding", "margin", "layout", "grid", "align", "nest", "card", "density", "rhythm"), "layout"),
    (("color", "palette", "gradient", "glow", "saturat", "neon", "purple"), "colorize"),
    (("animation", "motion", "transition", "bounce", "easing"), "animate"),
    (("lorem", "copy", "em-dash", "placeholder", "cta", "label-text", "jargon"), "clarify"),
    (("shadow", "blur", "glass", "border-radius", "decorat", "icon"), "quieter"),
]
FALLBACK_CMD = "polish"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"phase": None, "history": [], "refine_rounds": 0, "last_detect": None, "last_critique": None,
            "last_brief": None, "last_lint": None, "last_prefs": None}


def save(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def impeccable_bin():
    patterns = [
        "~/.claude/plugins/cache/impeccable/impeccable/*/skills/impeccable/scripts/impeccable",
        "~/.claude/skills/impeccable/scripts/impeccable",
    ]
    hits = []
    for pat in patterns:
        hits.extend(sorted(glob.glob(os.path.expanduser(pat))))
    if not hits:
        sys.exit("gate: impeccable launcher not found; is the impeccable plugin installed?")
    return hits[-1]


def map_rule(finding):
    key = (finding.get("antipattern", "") + " " + finding.get("name", "")).lower()
    for keywords, cmd in RULE_MAP:
        if any(k in key for k in keywords):
            return cmd
    return FALLBACK_CMD


def check_artifacts():
    return {p: os.path.exists(p) for p in ("PRODUCT.md", "DESIGN.md")}


def cmd_status(_args):
    state = load()
    artifacts = check_artifacts()
    phase = state["phase"]
    lint = state.get("last_lint")
    if phase is None:
        phase = "setup" if not (artifacts["PRODUCT.md"] and artifacts["DESIGN.md"]) else "shape"
        reason = "no state file; inferred from PRODUCT.md and DESIGN.md"
    else:
        reason = "from .ui-flow/state.json"
    print(json.dumps({
        "phase": phase,
        "reason": reason,
        "artifacts": artifacts,
        "refine_rounds": state["refine_rounds"],
        "refine_rounds_left": MAX_REFINE_ROUNDS - state["refine_rounds"],
        "last_detect": state["last_detect"] and {k: state["last_detect"][k] for k in ("verdict", "blocking", "commands")},
        "last_critique": state["last_critique"],
        "last_brief": state.get("last_brief"),
        "last_lint": lint and {"verdict": lint.get("verdict"), "total": lint.get("total")},
        "last_prefs": state.get("last_prefs"),
    }, indent=2))
    return 0


def check_transition_gate(cur, target, state):
    """Return error message if transition cur -> target violates an exit gate, else None."""
    artifacts = check_artifacts()
    last_detect = state.get("last_detect")
    last_critique = state.get("last_critique")
    last_brief = state.get("last_brief")
    last_lint = state.get("last_lint")
    last_prefs = state.get("last_prefs")

    if cur == "setup" and target != "setup":
        missing = [k for k, ok in artifacts.items() if not ok]
        if missing:
            return f"setup exit gate failed: missing {', '.join(missing)}"

    if cur == "shape" and target == "build":
        if not last_brief or last_brief.get("verdict") != "PASS":
            return "shape exit gate failed: run `gate.py brief <brief.md>` and fix what it lists"

    if target == "refine" and cur == "build":
        if not last_detect:
            return "build exit gate failed: run `gate.py detect <target> --mobile` at least once before entering refine"

    if target == "review":
        if not last_detect or last_detect.get("verdict") != "PASS":
            return "refine exit gate failed: `gate.py detect` must PASS before advancing to review (pass --force only if user accepted findings after 3 rounds)"
        if not last_lint or last_lint.get("verdict") != "PASS":
            return "refine exit gate failed: `gate.py lint <src>` must PASS before advancing to review"

    if target == "ship":
        if not last_critique or last_critique.get("verdict") != "PASS":
            score_info = f" (last score {last_critique.get('score')}/{last_critique.get('max')}, p0={last_critique.get('p0')})" if last_critique else ""
            return f"review exit gate failed: `gate.py critique` must PASS{score_info} before advancing to ship"
        if not last_detect or last_detect.get("verdict") != "PASS":
            return "review exit gate failed: `gate.py detect` must PASS before advancing to ship"
        if not last_lint or last_lint.get("verdict") != "PASS":
            return "review exit gate failed: `gate.py lint <src>` must PASS before advancing to ship"
        if not last_prefs or last_prefs.get("verdict") != "PASS":
            return "review exit gate failed: `gate.py prefs <failed> <checked>` must PASS before advancing to ship"

    if target == "done":
        if not last_detect or last_detect.get("verdict") != "PASS":
            return "ship exit gate failed: final `gate.py detect` must PASS before marking done"
        if not last_critique or last_critique.get("verdict") != "PASS":
            return "ship exit gate failed: `gate.py critique` must PASS before marking done"
        if not last_lint or last_lint.get("verdict") != "PASS":
            return "ship exit gate failed: `gate.py lint <src>` must PASS before marking done"
        if not last_prefs or last_prefs.get("verdict") != "PASS":
            return "ship exit gate failed: `gate.py prefs <failed> <checked>` must PASS before marking done"

    return None


def cmd_set_phase(args):
    force = "--force" in args
    pos = [a for a in args if a != "--force"]
    if len(pos) != 1 or pos[0] not in PHASES:
        print(f"gate: phase must be one of {PHASES} [--force]", file=sys.stderr)
        return 2
    target = pos[0]
    state = load()
    cur = state["phase"]

    if not force:
        err = check_transition_gate(cur, target, state)
        if err:
            print(f"gate BLOCKED ({cur} -> {target}): {err}", file=sys.stderr)
            return 1

    if target == "refine" and cur in ("refine", "review"):
        state["refine_rounds"] += 1
    if target == "shape":  # new screen starts a fresh refine budget
        state["refine_rounds"] = 0
        state["last_detect"] = None
        state["last_critique"] = None
        state["last_brief"] = None
        state["last_lint"] = None
        state["last_prefs"] = None
    state["history"].append({"from": cur, "to": target, "forced": force, "at": now()})
    state["phase"] = target
    save(state)
    print(f"phase -> {target} (refine rounds used: {state['refine_rounds']}/{MAX_REFINE_ROUNDS})")
    return 0


def run_detect(targets, viewport=None):
    cmd = [impeccable_bin(), "detect", "--json", "--no-advisory"]
    if viewport:
        cmd += ["--viewport", viewport]
    proc = subprocess.run(cmd + targets, capture_output=True, text=True)
    if proc.returncode not in (0, 2):
        print(proc.stderr.strip() or proc.stdout.strip(), file=sys.stderr)
        sys.exit(2)
    out = proc.stdout.strip()
    return json.loads(out) if out else []


def cmd_detect(args):
    mobile = "--mobile" in args
    wide = "--wide" in args
    targets = [a for a in args if a not in ("--mobile", "--wide")]
    if not targets:
        print("gate: detect needs at least one file, dir, or URL", file=sys.stderr)
        return 2
    findings = run_detect(targets)
    if mobile:
        if not any(t.startswith(("http://", "https://")) for t in targets):
            print("gate: --mobile only applies to URL targets; skipping mobile pass", file=sys.stderr)
        else:
            for f in run_detect(targets, "390x844"):
                f["viewport"] = "mobile"
                findings.append(f)
    if wide:
        if not any(t.startswith(("http://", "https://")) for t in targets):
            print("gate: --wide only applies to URL targets; skipping wide passes", file=sys.stderr)
        else:
            for vp, tag in (("1440x900", "wide-1440"), ("1920x1080", "wide-1920")):
                for f in run_detect(targets, vp):
                    f["viewport"] = tag
                    findings.append(f)

    by_cmd = defaultdict(list)
    for f in findings:
        by_cmd[map_rule(f)].append(f)
    priority = [cmd for _, cmd in RULE_MAP] + [FALLBACK_CMD]
    ranked = sorted(by_cmd, key=lambda c: (priority.index(c), -len(by_cmd[c])))
    blocking = [f for f in findings if f.get("severity") in ("error", "warning")]

    result = {
        "verdict": "PASS" if not blocking else "FAIL",
        "at": now(),
        "targets": targets,
        "total": len(findings),
        "blocking": len(blocking),
        "by_rule": dict(Counter(f.get("antipattern") for f in findings)),
        "commands": ranked[:MAX_COMMANDS_PER_ROUND],
        "deferred_commands": ranked[MAX_COMMANDS_PER_ROUND:],
        "findings_by_command": {
            c: [{"rule": f.get("antipattern"), "file": f.get("file"), "line": f.get("line"),
                 "snippet": (f.get("snippet") or "")[:160], "viewport": f.get("viewport", "desktop")}
                for f in by_cmd[c]]
            for c in ranked
        },
    }
    state = load()
    state["last_detect"] = result
    save(state)
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


def cmd_critique(args):
    try:
        score, max_score, p0 = (int(a) for a in args)
    except ValueError:
        print("gate: critique <score> <max> <p0_count>", file=sys.stderr)
        return 2
    threshold = round(max_score * CRITIQUE_PASS_RATIO)
    verdict = "PASS" if score >= threshold and p0 == 0 else "FAIL"
    state = load()
    state["last_critique"] = {"verdict": verdict, "score": score, "max": max_score,
                              "threshold": threshold, "p0": p0, "at": now()}
    save(state)
    print(json.dumps(state["last_critique"], indent=2))
    return 0 if verdict == "PASS" else 1


BRIEF_HEADINGS = ["Primary actions", "Secondary actions", "Pages", "States", "Preferences"]
BRIEF_IDS = [f"P{i}" for i in range(1, 13)]


def cmd_brief(args):
    if len(args) != 1:
        print("gate: brief <brief.md>", file=sys.stderr)
        return 2
    path = args[0]
    text = ""
    if os.path.isfile(path):
        with open(path, errors="replace") as f:
            text = f.read()
    headings = [m.group(1).lower() for m in re.finditer(r"^[ ]{0,3}#{1,6}[ \t]+(.*?)\s*$", text, re.M)]
    missing_headings = [h for h in BRIEF_HEADINGS if not any(h.lower() in t for t in headings)]
    missing_ids = [i for i in BRIEF_IDS if not re.search(rf"\b{i}\b", text)]
    exists = os.path.isfile(path)
    verdict = "PASS" if exists and not missing_headings and not missing_ids else "FAIL"
    result = {"verdict": verdict, "path": path, "missing_headings": missing_headings,
              "missing_ids": missing_ids, "at": now()}
    if not exists:
        result["error"] = "file not found"
    state = load()
    state["last_brief"] = result
    save(state)
    print(json.dumps(result, indent=2))
    return 0 if verdict == "PASS" else 1


SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "out", "coverage", "__tests__", "__fixtures__"}
SKIP_FILES = ("*.test.*", "*.spec.*", "*.stories.*")
MARKUP_EXT = {".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro"}
STYLE_EXT = {".css", ".scss", ".sass", ".less"}

SELECT_RE = re.compile(r"<select[\s>]")
DISABLED_TAG_RE = re.compile(r"<(?:button|input|a)(?=[\s>/])([^>]*)", re.I)
DISABLED_ATTR_RE = re.compile(r"\sdisabled(?=[\s=/>]|$)", re.I)
STYLE_OBJECT_RE = re.compile(r"\bstyle\s*=\s*\{\{(.*?)\}\}", re.S)
NUMERIC_PROP_RE = re.compile(r"(?<![\w-])([A-Za-z][\w-]*)\s*:\s*(\d+(?:\.\d+)?)(?![\w.])\s*(?=,|$)")
CSS_TEMPLATE_RE = re.compile(r"\b(?:styled(?:\.[\w]+|\([^)]*\))|css)\s*`([^`]*)`", re.S)
SIZING_PROPS = {
    "width", "height", "min-width", "min-height", "max-width", "max-height", "font-size", "line-height",
    "padding", "margin", "gap", "row-gap", "column-gap", "top", "right", "bottom", "left", "inset",
    "flex-basis", "grid-template-columns", "grid-template-rows", "grid-auto-rows", "grid-auto-columns",
}
SIZING_PREFIXES = ("padding-", "margin-", "inset-")
PROP_RE = re.compile(r"(?<![\w-])([A-Za-z][\w-]*)[\"']?\s*:\s*([^;{}]*)")
PX_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)px\b")
TW_PREFIXES = ("w|h|min-w|min-h|max-w|max-h|size|p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap|gap-x|gap-y|"
               "space-x|space-y|text|leading|top|right|bottom|left|inset|inset-x|inset-y|basis")
TW_RE = re.compile(rf"(?<!\w)(?:{TW_PREFIXES})-\[(\d+(?:\.\d+)?)px\]")
AT_QUERY_RE = re.compile(r"@(?:media|container)\b")

FIX_SELECT = "Use a styled custom dropdown with full keyboard support (preference P4)."
FIX_DISABLED = "Use aria-disabled and show the reason on hover, focus and tap (preference P5)."
FIX_PX = "Use rem/em/%/fr/ch/viewport units or clamp(); px only for 1-2px hairlines (preference P11)."


def cut_value(value):
    """Truncate at the first comma outside parentheses."""
    depth = 0
    for i, ch in enumerate(value):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth <= 0:
            return value[:i]
    return value


def sizing_prop(prop):
    prop = re.sub(r"[A-Z]", lambda c: "-" + c.group().lower(), prop)
    return prop in SIZING_PROPS or prop.startswith(SIZING_PREFIXES)


def has_fixed_px_decl(text):
    for m in PROP_RE.finditer(text):
        if sizing_prop(m.group(1)):
            if any(float(n) > 2 for n in PX_RE.findall(cut_value(m.group(2)))):
                return True
    return False


def numeric_style_offsets(text):
    for style in STYLE_OBJECT_RE.finditer(text):
        for prop in NUMERIC_PROP_RE.finditer(style.group(1)):
            if prop.group(1) != "lineHeight" and prop.group(1) != "line-height" and sizing_prop(prop.group(1)) and float(prop.group(2)) > 2:
                yield style.start(1) + prop.start()


def lint_line(line, ext):
    rules = []
    if ext in MARKUP_EXT:
        if SELECT_RE.search(line):
            rules.append(("native-select", FIX_SELECT))
    if ext in STYLE_EXT:
        px = not AT_QUERY_RE.search(line) and has_fixed_px_decl(line)
    else:
        sm = re.search(r"\bstyle\s*=", line)
        px = bool(sm) and not AT_QUERY_RE.search(line) and has_fixed_px_decl(line[sm.end():])
        px = px or any(float(n) > 2 for n in TW_RE.findall(line))
    if px and (ext in STYLE_EXT or ext in MARKUP_EXT):
        rules.append(("fixed-px-size", FIX_PX))
    return rules


def iter_lint_files(targets):
    for t in targets:
        if os.path.isdir(t):
            for root, dirs, files in os.walk(t):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for name in sorted(files):
                    yield os.path.join(root, name)
        else:
            yield t


def cmd_lint(args):
    if not args:
        print("gate: lint needs at least one file or dir", file=sys.stderr)
        return 2
    missing = [t for t in args if not os.path.exists(t)]
    if missing:
        print(f"gate: lint target not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    findings = []
    for path in iter_lint_files(args):
        name = os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        if ext not in MARKUP_EXT | STYLE_EXT or any(fnmatch.fnmatch(name, g) for g in SKIP_FILES):
            continue
        with open(path, errors="replace") as f:
            text = f.read()
        lines = text.splitlines(keepends=True)
        seen = set()

        def record(rule, fix, n):
            if n < 1 or n > len(lines) or "ui-flow-ignore" in lines[n - 1] or (rule, n) in seen:
                return
            seen.add((rule, n))
            findings.append({"rule": rule, "severity": "warning", "file": path, "line": n,
                             "snippet": lines[n - 1].strip()[:160], "fix": fix})

        for n, line in enumerate(lines, 1):
            if "ui-flow-ignore" in line:
                continue
            for rule, fix in lint_line(line, ext):
                record(rule, fix, n)
        if ext in MARKUP_EXT:
            for tag in DISABLED_TAG_RE.finditer(text):
                for attr in DISABLED_ATTR_RE.finditer(tag.group(1)):
                    if re.match(r"\s*=\s*\{\s*false\s*\}", tag.group(1)[attr.end():]):
                        continue
                    record("disabled-without-reason", FIX_DISABLED, text.count("\n", 0, tag.start()) + 1)
            for offset in numeric_style_offsets(text):
                record("fixed-px-size", FIX_PX, text.count("\n", 0, offset) + 1)
            if ext in {".ts", ".tsx", ".js", ".jsx"}:
                for template in CSS_TEMPLATE_RE.finditer(text):
                    for css_line in re.finditer(r"[^\n]+", template.group(1)):
                        if not AT_QUERY_RE.search(css_line.group()) and has_fixed_px_decl(css_line.group()):
                            record("fixed-px-size", FIX_PX,
                                   text.count("\n", 0, template.start(1) + css_line.start()) + 1)
    result = {
        "verdict": "FAIL" if findings else "PASS",
        "at": now(),
        "targets": args,
        "total": len(findings),
        "by_rule": dict(Counter(f["rule"] for f in findings)),
        "findings": findings,
    }
    state = load()
    state["last_lint"] = result
    save(state)
    print(json.dumps(result, indent=2))
    return 1 if findings else 0


def cmd_prefs(args):
    try:
        failed, checked = (int(a) for a in args)
    except ValueError:
        failed = checked = -1
    if len(args) != 2 or failed < 0 or checked != len(BRIEF_IDS) or failed > checked:
        print(f"gate: prefs <failed> <checked>  (failed >= 0 and <= checked; checked must equal {len(BRIEF_IDS)})", file=sys.stderr)
        return 2
    verdict = "PASS" if failed == 0 else "FAIL"
    state = load()
    state["last_prefs"] = {"verdict": verdict, "failed": failed, "checked": checked, "at": now()}
    save(state)
    print(json.dumps(state["last_prefs"], indent=2))
    return 0 if verdict == "PASS" else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    handlers = {"status": cmd_status, "set-phase": cmd_set_phase, "detect": cmd_detect, "critique": cmd_critique,
                "brief": cmd_brief, "lint": cmd_lint, "prefs": cmd_prefs}
    handler = handlers.get(sys.argv[1])
    if not handler:
        print(__doc__, file=sys.stderr)
        return 2
    return handler(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
