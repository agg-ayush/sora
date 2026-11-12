"""claude-orchestrate — drive interactive Claude Code sessions inside tmux."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

WORKTREES_DIRNAME = ".orchestrate-worktrees"
SUBPROCESS_TIMEOUT = 15
STALL_SECONDS = 300

# ---------------------------------------------------------------------------
# Doom-loop circuit breaker (borrowed from sentinel/conductor/self_heal.py)
# ---------------------------------------------------------------------------
# Per-task ring of the last N tool-call fingerprints. When the last
# DOOM_THRESHOLD fingerprints are identical, the session is in a doom loop.
# A tripped fingerprint is also stored globally so the same (tool, args)
# pattern blocks across sessions for BREAKER_COOLDOWN_S.

DOOM_THRESHOLD = 3
DOOM_RING_SIZE = 6
BREAKER_COOLDOWN_S = 300

# In-memory state — resets on plugin reload, which is fine given the short
# cooldown.  The breaker state is intentionally NOT persisted to disk.
_doom_rings: dict[str, list[str]] = {}
_breakers: dict[str, float] = {}  # key -> trip timestamp (epoch seconds)


def _now_ts() -> float:
    return time.time()


def doom_fingerprint(tool: str, args: Any) -> str:
    """sha1 of tool name + normalized args (whitespace collapsed, lower-cased)."""
    norm = re.sub(r"\s+", " ", str(args)).strip().lower()[:200]
    return hashlib.sha1(f"{tool}|{norm}".encode()).hexdigest()[:12]


def _breaker_open(key: str) -> bool:
    ts = _breakers.get(key)
    if ts is None:
        return False
    return (_now_ts() - ts) < BREAKER_COOLDOWN_S


def _trip_breaker(key: str) -> None:
    _breakers[key] = _now_ts()
    # Keep the dict bounded.
    if len(_breakers) > 100:
        for k in sorted(_breakers, key=lambda k: _breakers[k])[: len(_breakers) - 100]:
            _breakers.pop(k, None)


def observe_action(task_id: str, tool: str, args: Any) -> bool:
    """Record a tool call; return True if this is a doom loop (trip the breaker)."""
    fp = doom_fingerprint(tool, args)
    seq = _doom_rings.get(task_id, [])
    seq.append(fp)
    seq = seq[-DOOM_RING_SIZE:]
    _doom_rings[task_id] = seq
    if len(seq) >= DOOM_THRESHOLD and seq[-DOOM_THRESHOLD:].count(fp) >= DOOM_THRESHOLD:
        _trip_breaker(f"doom:{fp}")
        _trip_breaker(f"task:{task_id}")
        return True
    return False


def clear_doom_task(task_id: str) -> None:
    _doom_rings.pop(task_id, None)


def doom_loop_active(task_id: str) -> bool:
    """True if the task's own breaker is open (doom loop detected recently)."""
    return _breaker_open(f"task:{task_id}")


def breaker_open_for(tool: str, args: Any) -> bool:
    """True if the exact (tool, args) fingerprint is globally blocked."""
    return _breaker_open(f"doom:{doom_fingerprint(tool, args)}")

def _tasks_root() -> Path:
    return get_hermes_home() / "tasks"


def _run(cmd: list[str], timeout: int = SUBPROCESS_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        env = os.environ.copy()
        local_bin = str(Path.home() / ".local" / "bin")
        path = env.get("PATH", "")
        if local_bin not in path.split(os.pathsep):
            env["PATH"] = f"{local_bin}{os.pathsep}{path}" if path else local_bin
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", f"{type(exc).__name__}: {exc}")


def _detached_tmux_launch(cmd: list[str]) -> list[str]:
    """Start a fresh tmux server in its own systemd scope.

    A server forked from inside the gateway's service unit lives in that unit's
    cgroup, so restarting the gateway kills every session on it. A server that is
    already running keeps its cgroup; only the first launch needs the scope.
    """
    if not sys.platform.startswith("linux") or shutil.which("systemd-run") is None:
        return cmd
    if _run(["tmux", "list-sessions"]).returncode == 0:
        return cmd
    return ["systemd-run", "--user", "--scope", "--quiet", "--collect", *cmd]


def _artifact_dir(task_id: str) -> Path:
    return _tasks_root() / task_id


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_meta(task_id: str) -> dict:
    raw = _read_text(_artifact_dir(task_id) / "meta.json")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def _session_exists(task_id: str) -> bool:
    return _run(["tmux", "has-session", "-t", task_id]).returncode == 0


def _coerce_bool(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off", ""}
    return bool(raw)


def _check_available() -> bool:
    return bool(shutil.which("tmux") and shutil.which("claude"))


SEATBELT_BASE_URL = "https://<model-gateway>"
CLAUDE_ROUTE_REFUSAL = (
    "Claude Code must not run on the TrueFoundry gateway (pay-per-token anthropic-primary billing). "
    "Allowed routes for executor=claude: model_provider=seatbelt (primary) or model_provider=fireworks (fallback)."
)
SEATBELT_MODELS = {
    "opus": "claude-teams-group/claude-opus-5-5",
    "sonnet": "claude-teams-group/claude-sonnet-5-5",
}
SEATBELT_HAIKU_MODEL = "claude-teams-group/claude-haiku-4-5-20251001"
SEATBELT_FABLE_MODEL = "claude-teams-group/claude-fable-5-1"
_SEATBELT_HEADER_RE = re.compile(r"^(x-tfy-api-key|x-maat-token): (.*)$", re.MULTILINE)
_SEATBELT_ASSIGN_RE = re.compile(r"seatbelt_headers=\$'(.*?)'", re.DOTALL)


def _seatbelt_home() -> Path:
    return Path.home()


def _seatbelt_headers() -> str:
    """Build ANTHROPIC_CUSTOM_HEADERS from the user's rc file; raises ValueError if unusable."""
    home = _seatbelt_home()
    names = [".zshrc", ".bashrc"] if sys.platform == "darwin" else [".bashrc", ".zshrc"]
    texts = []
    for name in names:
        text = _read_text(home / name)
        if text is not None:
            texts.append((name, text))
    if not texts:
        raise ValueError(f"seatbelt headers rc file not found (looked for {', '.join(names)} in {home})")
    name, text = next(((n, t) for n, t in texts if "seatbelt_headers" in t), texts[0])
    # rc stores the two headers inside a $'...' assignment with a literal \n
    # escape between them; unescape before matching header lines.
    assign = _SEATBELT_ASSIGN_RE.search(text)
    haystack = assign.group(1).replace("\\n", "\n") if assign else text
    found = {m.group(1): m.group(2).rstrip().rstrip("'").rstrip() for m in _SEATBELT_HEADER_RE.finditer(haystack)}
    if "x-tfy-api-key" not in found or "x-maat-token" not in found:
        raise ValueError(f"x-tfy-api-key / x-maat-token header lines missing in ~/{name}")
    tfy_key = os.environ.get("TFY_API_KEY") or ""
    if len(tfy_key) < 8:
        raise ValueError("model_provider=seatbelt requires TFY_API_KEY in env")
    if not found["x-tfy-api-key"].endswith(tfy_key[-8:]):
        raise ValueError(f"stale seatbelt token: x-tfy-api-key in ~/{name} does not match the configured TFY_API_KEY (mismatch)")
    return f"x-tfy-api-key: {found['x-tfy-api-key']}\nx-maat-token: {found['x-maat-token']}"


# ---------------------------------------------------------------------------
# Review-round cap
# ---------------------------------------------------------------------------
# Review->fix loops are bounded in code, not only in the skill text: each
# kanban card gets at most REVIEW_CAP_DEFAULT review sessions per kind
# (code review / design review). The 4th `start` is refused. The model cannot
# lift the cap through an argument; a human edits the ledger or drops an
# override file (see _review_cap_reserve).

REVIEW_CAP_DEFAULT = 3
REVIEW_FREE_RESTARTS = 2  # crash-restarts of one review task_id that are not recounted

# Session names: "review" (not "preview"), plus the short forms used in practice:
# crev/drev/rev, optionally numbered (t2-x-crev2, t2-x-drev3, t-x-rev).
_REVIEW_NAME_RE = re.compile(r"(?<!p)review|(?<![a-z])[cd]?rev\d*(?![a-z])", re.I)
_DESIGN_NAME_RE = re.compile(r"design|(?<![a-z])d(?:ev)?rev|dreview", re.I)
# Sessions that change code/docs, even when the name mentions a review
# (review-fix, reviewfix1, design-revise2, drevision3, review-rework, ...).
_FIXISH_NAME_RE = re.compile(r"fix|revis|rework|remediat|author|coder|address", re.I)
_IMPL_NAME_RE = re.compile(r"(?<![a-z])impl", re.I)
_REVIEW_PROMPT_STRONG_RE = re.compile(r"pr-review-toolkit|review-pr\b", re.I)
_REVIEW_PROMPT_VERDICT_RE = re.compile(r"\b(?:write|writes|produce|emit)\b[^.\n]{0,80}\bverdict\b", re.I)


def _review_cap() -> int:
    try:
        cap = int(os.environ.get("CLAUDE_ORCHESTRATE_REVIEW_CAP", "").strip())
    except ValueError:
        return REVIEW_CAP_DEFAULT
    return cap if cap >= 1 else REVIEW_CAP_DEFAULT


def _review_kind(task_id: str, prompt: Any) -> str | None:
    """Return 'code' or 'design' when this start is a review session, else None."""
    text = str(prompt or "")
    if _FIXISH_NAME_RE.search(task_id):
        is_review = False
    elif _REVIEW_NAME_RE.search(task_id):
        is_review = True
    elif _IMPL_NAME_RE.search(task_id):
        is_review = False  # impl sessions may mention the toolkit in their instructions
    else:
        is_review = bool(_REVIEW_PROMPT_STRONG_RE.search(text) or _REVIEW_PROMPT_VERDICT_RE.search(text))
    if not is_review:
        return None
    if _DESIGN_NAME_RE.search(task_id):
        return "design"
    if not _REVIEW_PROMPT_STRONG_RE.search(text) and re.search(r"design doc", text, re.I):
        return "design"
    return "code"


def _review_ledger_dir() -> Path:
    return _tasks_root() / ".review-rounds"


def _review_ledger_path(kanban_task: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", kanban_task)[:120] or "unknown"
    return _review_ledger_dir() / f"{safe}.json"


def _read_review_ledger(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("rounds"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"rounds": []}


def _write_review_ledger(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class _review_ledger_lock:
    """Advisory exclusive lock so two concurrent starts cannot both take the last round."""

    def __init__(self, path: Path):
        self._lock_path = path.with_suffix(".lock")
        self._fh = None

    def __enter__(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._lock_path, "a")
        try:
            import fcntl
            fcntl.flock(self._fh, fcntl.LOCK_EX)
        except ImportError:  # no fcntl (Windows): best effort
            pass
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.close()  # releases the flock
        return False


def _review_extra_rounds(path: Path) -> int:
    """Human grant: an integer in <ledger>.extra adds that many rounds per kind."""
    try:
        return max(0, int(path.with_suffix(".extra").read_text("utf-8").strip()))
    except (OSError, ValueError):
        return 0


def _previous_run_unfinished(task_id: str) -> bool:
    """True when an earlier run of this task_id never wrote a terminal outcome (crashed)."""
    raw = _read_text(_artifact_dir(task_id) / "outcome.md") or ""
    return _parse_outcome(raw)["outcome"] is None


def _review_cap_reserve(task_id: str, prompt: Any, kanban_task: str) -> tuple[dict | None, tuple | None]:
    """Count this start against the card's review cap.

    Returns (refusal, reservation). refusal is an ok:false result when the cap is
    reached; reservation identifies the ledger entry so a failed launch can undo it.
    Both None means the start is not a capped review session.
    """
    if not kanban_task:
        return None, None
    kind = _review_kind(task_id, prompt)
    if kind is None:
        return None, None
    path = _review_ledger_path(kanban_task)
    cap = _review_cap()
    with _review_ledger_lock(path):
        data = _read_review_ledger(path)
        rounds = data["rounds"]
        prior = [r for r in rounds if isinstance(r, dict) and r.get("task_id") == task_id]
        if prior and _previous_run_unfinished(task_id):
            restarts = sum(int(r.get("restarts", 0)) for r in prior)
            if restarts < REVIEW_FREE_RESTARTS:
                # Crash-restart of the same round: not a new round.
                prior[0]["restarts"] = int(prior[0].get("restarts", 0)) + 1
                data["kanban_task_id"] = kanban_task
                _write_review_ledger(path, data)
                return None, None
        used = sum(1 for r in rounds if isinstance(r, dict) and r.get("kind") == kind)
        allowed = cap + _review_extra_rounds(path)
        if used >= allowed:
            label = "design-review" if kind == "design" else "code-review"
            names = ", ".join(str(r.get("task_id")) for r in rounds if isinstance(r, dict) and r.get("kind") == kind)
            return {
                "ok": False,
                "error": (
                    f"review-round cap reached: kanban task {kanban_task} already used {used} of {allowed} "
                    f"{label} rounds ({names}). Do NOT start another review session. STOP and escalate to a human "
                    f"with the outstanding findings from the latest verdict (kanban_block kind=needs_input). "
                    f"A human can grant more rounds by writing an integer to {path.with_suffix('.extra')} "
                    f"or by deleting/editing {path}; this cannot be changed from a tool argument."
                ),
                "review_rounds_used": used,
                "review_cap": allowed,
                "review_kind": kind,
                "escalate": True,
            }, None
        rounds.append({"task_id": task_id, "kind": kind, "started_at": time.time(), "restarts": 0})
        data["kanban_task_id"] = kanban_task
        _write_review_ledger(path, data)
    return None, (path, task_id, kind)


def _review_cap_release(reservation: tuple) -> None:
    """Undo a reservation when the launch failed, so a failed start does not burn a round."""
    path, task_id, kind = reservation
    try:
        with _review_ledger_lock(path):
            data = _read_review_ledger(path)
            for i in range(len(data["rounds"]) - 1, -1, -1):
                r = data["rounds"][i]
                if isinstance(r, dict) and r.get("task_id") == task_id and r.get("kind") == kind:
                    del data["rounds"][i]
                    break
            _write_review_ledger(path, data)
    except OSError:
        pass


def _kanban_task_for(args: dict, task_id: str) -> str:
    kanban_task = str(args.get("kanban_task_id") or "").strip()
    if not kanban_task:
        m_kb = re.match(r"^(?:t2-)?(t_[0-9a-f]{8})\b", task_id)
        if m_kb:
            kanban_task = m_kb.group(1)
    return kanban_task


# ---------------------------------------------------------------------------
# Process v2 gates and metrics
# ---------------------------------------------------------------------------
# Active only when ~/.hermes/tasks/t2-<kanban_task_id>/process.json exists with
# "version": 2; without it a card is legacy and nothing here runs. A gate that
# hits an unexpected error logs and allows the start: a bug here must never
# wedge the pipeline. A refusal never reserves or counts a review round.

_V2_PRECHECK_REL = Path("skills/shared/software-development/design/scripts/design_precheck.py")
_V2_FAIL_UPPER_RE = re.compile(r"\bFAIL(?:ED)?\b|[✗✕×]")
_V2_FAIL_COUNT_RE = re.compile(r"\b[1-9]\d*\s+(?:failed|failing|errors?)\b", re.I)
_V2_PASS_RE = re.compile(r"\b[1-9]\d*\s+passed\b|\bPASS\b|^ok\s|\bpassing\b|[✓✔]", re.I | re.M)
_V2_EXIT_RE = re.compile(r"^\s*(?:exit(?:[ _-]?(?:code|status))?|rc)\s*[:=]\s*(-?\d+)\s*$", re.I | re.M)
_V2_FINDING_RE = re.compile(r"^\s*[-*]?\s*F\d+\b.*$", re.M)
_V2_ESCAPE_RE = re.compile(r"\[escape:\s*(design|impl|test|noise)\s*\]", re.I)
_V2_VERDICT_PATH_RES = (
    re.compile(r"((?:/|~/)[^\s`'\"<>)]*verdict[^\s`'\"<>)]*)", re.I),
    re.compile(r"verdict[^\n]{0,120}?((?:/|~/)[^\s`'\"<>)]+)", re.I),
)


def _v2_log(msg: str) -> None:
    print(f"[claude-orchestrate] process-v2: {msg}", file=sys.stderr)


def _v2_card(kanban_task: str) -> tuple[Path, dict] | None:
    """(card_dir, process.json) when the card opted into process v2, else None."""
    if not kanban_task:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", kanban_task)[:120]
    card = _tasks_root() / f"t2-{safe}"
    try:
        proc = json.loads((card / "process.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(proc, dict) or proc.get("version") != 2:
        return None
    return card, proc


def _v2_metrics_append(card: Path, stage: str, event: str, round_: int | None, detail: Any) -> None:
    row = {"ts": round(time.time(), 3), "stage": stage, "event": event, "round": round_, "detail": detail}
    try:
        card.mkdir(parents=True, exist_ok=True)
        with open(card / "metrics.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")  # one write: O_APPEND keeps lines whole
    except OSError as exc:
        _v2_log(f"metrics write failed: {exc}")


def _v2_precheck_path() -> Path | None:
    here = Path(__file__).resolve().parent.parent
    home = get_hermes_home()
    candidates = [here / _V2_PRECHECK_REL, home / "skills" / "design" / "scripts" / "design_precheck.py"]
    candidates += sorted(home.glob("skills/*/design/scripts/design_precheck.py"))
    candidates += sorted(home.glob("skills/*/*/design/scripts/design_precheck.py"))
    return next((c for c in candidates if c.is_file()), None)


def _v2_load_precheck():
    script = _v2_precheck_path()
    if script is None:
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("hermes_design_precheck", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "check", None)


def _v2_design_gate(card: Path, proc: dict) -> dict | None:
    """Run the design pre-check by import. Returns a refusal or None."""
    check = _v2_load_precheck()
    if check is None:
        _v2_log("design_precheck.py not found; design pre-check skipped")
        return {"warning": "design pre-check script not found; gate skipped"}
    design = str(proc.get("design_path") or "").strip() or str(card / "design.md")
    ok, problems, warnings = check(design)
    if ok:
        return {"warnings": list(warnings or [])} if warnings else None
    problems = [str(p) for p in (problems or [])] or ["pre-check failed without details"]
    listing = "\n".join(f"- {p}" for p in problems)
    return {
        "ok": False,
        "error": (
            f"design pre-check failed for {design} ({len(problems)} problem(s)):\n{listing}\n"
            "Do NOT start the design review yet. Send the design back to the design author to fix these, "
            "then start the review again. No review round was used."
        ),
        "escalate": False,
        "precheck_failed": True,
        "missing": problems,
        "review_kind": "design",
    }


def _v2_run_text(path: Path) -> tuple[str, str]:
    """(first line = command, rest = runner output) of an evidence file."""
    raw = path.read_text("utf-8", errors="replace")
    head, _, rest = raw.partition("\n")
    return head, rest


def _v2_exit_code(text: str) -> int | None:
    found = _V2_EXIT_RE.findall(text)
    return int(found[-1]) if found else None


def _v2_red_ok(rest: str) -> bool:
    code = _v2_exit_code(rest)
    if code == 0:
        return False
    return bool(_V2_FAIL_UPPER_RE.search(rest) or _V2_FAIL_COUNT_RE.search(rest) or (code or 0) != 0)


def _v2_green_ok(rest: str) -> bool:
    if _V2_FAIL_UPPER_RE.search(rest) or _V2_FAIL_COUNT_RE.search(rest):
        return False
    code = _v2_exit_code(rest)
    if code is not None:
        return code == 0
    return bool(_V2_PASS_RE.search(rest))


def _v2_evidence_problems(card: Path) -> list[str]:
    ev = card / "evidence"
    reds, greens, problems = [], [], []
    for kind, bucket in (("red", reds), ("green", greens)):
        for f in sorted(ev.glob(f"{kind}-*.txt")):
            try:
                _, rest = _v2_run_text(f)
            except OSError:
                continue
            if rest.strip():
                bucket.append((f, rest))
    if not reds:
        problems.append("no non-empty evidence/red-*.txt (save the failing test run before implementing: "
                        "first line the exact test command, then the raw runner output)")
    elif not any(_v2_red_ok(rest) for _, rest in reds):
        names = ", ".join(f.name for f, _ in reds)
        problems.append(f"{names} does not show a failing test (expected FAIL, FAILED, failed, a cross mark "
                        "or a nonzero exit line); RED must fail before the fix")
    if not greens:
        problems.append("no non-empty evidence/green-*.txt (save the passing run after implementing)")
    else:
        for f, rest in greens:
            if not _v2_green_ok(rest):
                problems.append(f"{f.name} does not show a clean passing run (failures present, nonzero exit "
                                "or no pass marker); GREEN must pass without failures")
    return problems


def _v2_code_gate(card: Path, proc: dict) -> dict | None:
    if proc.get("tier") not in ("light", "full") and proc.get("kind") != "bugfix":
        return None
    problems = _v2_evidence_problems(card)
    if not problems:
        return None
    listing = "\n".join(f"- {p}" for p in problems)
    return {
        "ok": False,
        "error": (
            f"code review refused: RED/GREEN evidence missing or invalid in {card / 'evidence'}:\n{listing}\n"
            "Do NOT start the code review yet. Send the card back to the implementer to save the missing "
            "evidence, then start the review again. No review round was used."
        ),
        "escalate": False,
        "evidence_missing": problems,
        "review_kind": "code",
    }


def _v2_stage(task_id: str, review_kind: str | None) -> str:
    if review_kind:
        return f"{review_kind}_review"
    name = task_id.lower()
    if re.search(r"ground|explor", name):
        return "grounding"
    if re.search(r"design|author", name) and not re.search(r"fix", name):
        return "design"
    if re.search(r"fix|address|remediat|rework", name):
        return "fix"
    if re.search(r"impl|coder|test", name):
        return "implementation"
    return "other"


def _v2_gate_start(task_id: str, prompt: Any, kanban_task: str) -> tuple[dict | None, dict | None]:
    """(context, refusal) for a start. Both None for legacy cards. Fails open."""
    try:
        found = _v2_card(kanban_task)
        if found is None:
            return None, None
        card, proc = found
        kind = _review_kind(task_id, prompt)
        ctx = {"card": card, "kind": kind, "stage": _v2_stage(task_id, kind), "prompt": str(prompt or "")}
        gate = _v2_design_gate(card, proc) if kind == "design" else _v2_code_gate(card, proc) if kind == "code" else None
        if gate and gate.get("ok") is False:
            _v2_metrics_append(card, ctx["stage"], "refused", None, {
                "task_id": task_id, "reason": "precheck" if kind == "design" else "evidence",
                "missing": gate.get("missing") or gate.get("evidence_missing"),
            })
            return ctx, gate
        if gate:
            ctx["warnings"] = gate.get("warnings") or [gate.get("warning")]
        return ctx, None
    except Exception as exc:  # noqa: BLE001 - fail open
        _v2_log(f"gate error, allowing start: {exc!r}")
        return None, None


def _v2_review_round(kanban_task: str, task_id: str, kind: str) -> int | None:
    rows = [r for r in _read_review_ledger(_review_ledger_path(kanban_task))["rounds"]
            if isinstance(r, dict) and r.get("kind") == kind]
    idx = [i for i, r in enumerate(rows) if r.get("task_id") == task_id]
    return (idx[-1] + 1) if idx else None


def _v2_verdict_path(prompt: str, card: Path, round_: int | None) -> Path | None:
    for rx in _V2_VERDICT_PATH_RES:
        m = rx.search(prompt)
        if m:
            return Path(m.group(1).rstrip(".,;:")).expanduser()
    if round_:
        return card / "review" / f"verdict-r{round_}.md"
    return None


def _v2_note_started(ctx: dict, task_id: str, kanban_task: str) -> None:
    try:
        kind, card = ctx["kind"], ctx["card"]
        round_ = _v2_review_round(kanban_task, task_id, kind) if kind else None
        side = {"started_at": time.time(), "stage": ctx["stage"], "round": round_, "kind": kind,
                "card": card.as_posix(), "ended": False}
        if kind == "code":
            vp = _v2_verdict_path(ctx["prompt"], card, round_)
            side["verdict_path"] = vp.as_posix() if vp else None
        _write_text(_artifact_dir(task_id) / ".metrics.json", json.dumps(side))
        detail = {"task_id": task_id}
        if ctx.get("warnings"):
            detail["warnings"] = ctx["warnings"]
        _v2_metrics_append(card, ctx["stage"], "start", round_, detail)
    except Exception as exc:  # noqa: BLE001
        _v2_log(f"start metrics failed: {exc!r}")


def _v2_finding_counts(path: Path) -> dict | None:
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    counts = {"design": 0, "impl": 0, "test": 0, "noise": 0, "unlabelled": 0, "total": 0, "blocking": 0}
    for line in _V2_FINDING_RE.findall(text):
        m = _V2_ESCAPE_RE.search(line)
        counts[m.group(1).lower() if m else "unlabelled"] += 1
        counts["total"] += 1
        if re.search(r"\[BLOCKING\]", line, re.I):
            counts["blocking"] += 1
    return counts


def _v2_record_end(task_id: str, outcome: str) -> None:
    """Append one `end` event when a v2 session's outcome is first collected."""
    try:
        side_path = _artifact_dir(task_id) / ".metrics.json"
        raw = _read_text(side_path)
        if not raw:
            return
        side = json.loads(raw)
        if side.get("ended"):
            return
        card = Path(side["card"])
        detail: dict = {"task_id": task_id, "outcome": outcome,
                        "minutes": round((time.time() - float(side["started_at"])) / 60, 2)}
        if side.get("kind") == "code":
            candidates = [Path(side["verdict_path"])] if side.get("verdict_path") else []
            if side.get("round"):
                candidates.append(card / "review" / f"verdict-r{side['round']}.md")
            for vp in candidates:
                counts = _v2_finding_counts(vp)
                if counts is not None:
                    detail["findings"] = counts
                    break
        side["ended"] = True
        _write_text(side_path, json.dumps(side))
        _v2_metrics_append(card, side["stage"], "end", side.get("round"), detail)
    except Exception as exc:  # noqa: BLE001
        _v2_log(f"end metrics failed: {exc!r}")


def _start(args: dict) -> dict:
    """Start a session, enforcing process v2 gates (v2 cards only), then the per-card review-round cap."""
    task_id = str(args.get("task_id") or "").strip()
    reservation = None
    ctx = None
    kanban_task = ""
    if task_id and args.get("prompt") and not _session_exists(task_id):
        kanban_task = _kanban_task_for(args, task_id)
        ctx, gate_refusal = _v2_gate_start(task_id, args.get("prompt"), kanban_task)
        if gate_refusal is not None:
            return gate_refusal
        refusal, reservation = _review_cap_reserve(task_id, args.get("prompt"), kanban_task)
        if refusal is not None:
            if ctx:
                _v2_metrics_append(ctx["card"], ctx["stage"], "refused", None,
                                   {"task_id": task_id, "reason": "review-round cap"})
            return refusal
    try:
        result = _start_session(args)
    except BaseException:
        if reservation:
            _review_cap_release(reservation)
        raise
    if reservation and not result.get("ok"):
        _review_cap_release(reservation)
    if ctx and result.get("ok"):
        _v2_note_started(ctx, task_id, kanban_task)
    return result


def _seed_graphify(main_repo: Path, worktree: Path) -> None:
    """Give a new worktree its own copy of the main repo's graph so --update never writes to main.

    Copies only when main has a non-empty .graphify and the worktree has none; a legacy
    symlink is dropped first. Never creates .graphify in the main repo. Fail-open.
    """
    try:
        src, dst = main_repo / ".graphify", worktree / ".graphify"
        if dst.is_symlink():
            dst.unlink()
        if dst.exists() or not src.is_dir() or not any(src.iterdir()):
            return
        shutil.copytree(src, dst, symlinks=False)
        for name in ("branch.json", "worktree.json", "needs_update"):
            (dst / name).unlink(missing_ok=True)
    except OSError:
        pass


def _start_session(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    prompt = args.get("prompt")
    workdir = str(args.get("workdir") or "").strip()
    worktree = str(args.get("worktree") or "").strip() or None
    dangerous = _coerce_bool(args.get("dangerous"), True)
    executor = str(args.get("executor") or "claude").strip().lower()
    model = str(args.get("model") or "").strip() or None
    effort = str(args.get("effort") or "").strip().lower() or None
    model_provider = str(args.get("model_provider") or "seatbelt").strip().lower()

    if not task_id or not prompt or not workdir:
        return {"ok": False, "error": "task_id, prompt, and workdir are required"}
    if executor not in {"claude", "codex"}:
        return {"ok": False, "error": f"invalid executor: {executor!r} (must be 'claude' or 'codex')"}
    if model_provider not in {"truefoundry", "fireworks", "seatbelt"}:
        return {"ok": False, "error": f"invalid model_provider: {model_provider!r} (must be 'truefoundry', 'fireworks' or 'seatbelt')"}
    if model_provider == "truefoundry" and executor == "claude":
        # Claude Code through TF speaks the anthropic protocol, where the
        # gateway strips group prefixes and bills every Claude model as
        # anthropic-primary at list rates. Claude work goes through seatbelt
        # (primary) or fireworks/Kimi K3.1 Pro (fallback). truefoundry remains valid
        # only for the codex executor (codex_responses transport).
        return {"ok": False, "error": CLAUDE_ROUTE_REFUSAL}
    if effort and effort not in {"low", "medium", "high", "xhigh", "max"}:
        return {"ok": False, "error": f"invalid effort: {effort!r}"}
    seatbelt_model = None
    seatbelt_headers = ""
    if model_provider == "seatbelt":
        if executor != "claude":
            return {"ok": False, "error": "model_provider=seatbelt is only supported with executor=claude"}
        seatbelt_model = SEATBELT_MODELS.get(model or "")
        if seatbelt_model is None:
            return {"ok": False, "error": f"invalid model for seatbelt: {model!r} (must be 'opus' or 'sonnet')"}
        try:
            seatbelt_headers = _seatbelt_headers()
        except ValueError as exc:
            return {"ok": False, "error": f"{exc}; failing closed"}
    if _session_exists(task_id):
        return {"ok": False, "error": f"tmux session '{task_id}' already exists"}

    artifact_dir = _artifact_dir(task_id)
    status_path = artifact_dir / "status.md"
    result_path = artifact_dir / "result.md"
    outcome_path = artifact_dir / "outcome.md"
    _write_text(artifact_dir / "prompt.md", str(prompt))
    _write_text(status_path, "starting")
    # Pre-create so the agent updates this file rather than creating a fresh one in its cwd.
    # PENDING is not a valid outcome token, so _read_outcome still reports outcome:None until overwritten.
    _write_text(outcome_path, "PENDING")

    rundir = workdir
    worktree_path: Path | None = None
    if worktree:
        worktrees_parent = Path(workdir).parent / WORKTREES_DIRNAME
        worktrees_parent.mkdir(parents=True, exist_ok=True)
        worktree_path = worktrees_parent / worktree
        add = _run(["git", "-C", workdir, "worktree", "add", worktree_path.as_posix(), "-b", worktree])
        if add.returncode != 0:
            # Branch likely already exists — retry without creating it.
            fallback = _run(["git", "-C", workdir, "worktree", "add", worktree_path.as_posix(), worktree])
            if fallback.returncode != 0:
                return {
                    "ok": False,
                    "error": (fallback.stderr or fallback.stdout or "git worktree add failed").strip(),
                }
        _seed_graphify(Path(workdir).resolve(), worktree_path)
        rundir = str(worktree_path)

    status_instruction = (
        f"\n\nAt each phase boundary, write a single word to {shlex.quote(status_path.as_posix())}: "
        "investigating, implementing, testing, blocked, or complete. "
        f"When finished, write your final summary to {shlex.quote(result_path.as_posix())} "
        "and set status.md to complete. "
        f"When you finish or give up, also update the existing file at the absolute path "
        f"{shlex.quote(outcome_path.as_posix())} — replace its contents with exactly one terminal token "
        "as the first line: DONE (task complete, confident), DONE_WITH_CONCERNS (complete but with "
        "caveats — list them after the token), NEEDS_CONTEXT (cannot proceed without more information — "
        "state what's needed after the token), or BLOCKED (blocked by an external/unsolvable problem — "
        "state why after the token)."
    )
    learned_rules = _error_journal_inject(executor)
    if learned_rules and "## Learned Rules" not in str(prompt):
        full_prompt = f"{learned_rules}\n\n{prompt}{status_instruction}"
    else:
        full_prompt = f"{prompt}{status_instruction}"

    if executor == "codex":
        exec_cmd = "codex"
        if dangerous:
            exec_cmd += " --dangerously-bypass-approvals-and-sandbox"
        if model:
            exec_cmd += f" -m {shlex.quote(model)}"
        if model == "gpt-6-sol" and worktree_path is not None:
            # Plugin-created worktrees are untrusted dirs and stall on codex's
            # trust prompt before the brief submits. Trust exactly this path
            # for this launch only — -c is process-scoped, no config write.
            trust = f'projects={{{json.dumps(str(worktree_path.resolve()))}={{trust_level="trusted"}}}}'
            exec_cmd += f" -c {shlex.quote(trust)}"
        # Codex 0.144.x has a bug where a positional prompt arg triggers a
        # spurious "Missing environment variable: TFY_API_KEY" error. Launch
        # bare and send the prompt via send-keys after a short startup delay.
        shell_cmd = (
            f"cd {shlex.quote(Path(rundir).as_posix())} && "
            f"{exec_cmd}"
        )
    else:
        exec_cmd = "claude"
        if dangerous:
            exec_cmd += " --dangerously-skip-permissions"
        if model and model_provider not in {"fireworks", "seatbelt"}:
            # In the fireworks/seatbelt paths the model is set via env vars;
            # passing --model truncates the accounts/... path in interactive mode (403).
            exec_cmd += f" --model {shlex.quote(model)}"
        if effort:
            exec_cmd += f" --effort {shlex.quote(effort)}"
        # Deny-guard hook: structurally block git push / gh pr create/merge /
        # secret reads / destructive commands in the T3 session. The merge gate
        # is the broker — the agent edits+commits, never pushes/merges. Write a
        # per-session settings.json with the hook and pass it via --settings.
        deny_settings = artifact_dir / "deny-settings.json"
        stop_gate_cmd = f"python3 {shlex.quote(str(_stop_gate_path()))} {shlex.quote(str(artifact_dir.resolve()))}"
        session_settings: dict = {
            "hooks": {
                "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": str(_deny_guard_path())}]}],
                "Stop": [{"matcher": "", "hooks": [{"type": "command", "command": stop_gate_cmd, "timeout": 15}]}],
            }
        }
        deny_settings.write_text(json.dumps(session_settings), "utf-8")
        exec_cmd += f" --settings {shlex.quote(str(deny_settings))}"
        # Secret-scrub: pop credentials from the child env so a Bash-equipped
        # agent can't exfiltrate them (the broker holds the secrets and pushes
        # on the agent's behalf). NOTE: do NOT scrub FIREWORKS_API_KEY — the
        # fireworks path needs it (exported as ANTHROPIC_AUTH_TOKEN).
        env_scrub = " ".join(
            f"unset {k}" for k in ("GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "TFY_API_KEY", "TRUEFOUNDRY_API_KEY")
        )
        if model_provider == "fireworks":
            # Route this session to Kimi K3.1 Pro on Fireworks' Anthropic-compatible
            # endpoint. CLAUDE_CONFIG_DIR isolates the session from the personal
            # OAuth login + TF-gateway settings.json (which otherwise override
            # env-var routing). ANTHROPIC_API_KEY must be explicitly empty so the
            # Bearer-token path (ANTHROPIC_AUTH_TOKEN) wins.
            fireworks_key = os.environ.get("FIREWORKS_API_KEY") or ""
            if not fireworks_key:
                return {"ok": False, "error": "model_provider=fireworks requires FIREWORKS_API_KEY in env"}
            k3_config = get_hermes_home() / "claude-k3-config"
            k3_config.mkdir(parents=True, exist_ok=True)
            # Pre-seed onboarding + trust so the isolated session doesn't stall on
            # first-run dialogs (workspace trust / bypass-permissions are handled by
            # --dangerously-skip-permissions; onboarding gate is config-state only).
            k3_state = k3_config / ".claude.json"
            try:
                existing = json.loads(k3_state.read_text(encoding="utf-8")) if k3_state.exists() else {}
            except ValueError:
                existing = {}
            changed = False
            if not existing.get("hasCompletedOnboarding"):
                existing["hasCompletedOnboarding"] = True
                changed = True
            approved = existing.setdefault("customApiKeyResponses", {}).setdefault("approved", [])
            if fireworks_key not in approved:
                approved.append(fireworks_key)
                changed = True
            if changed:
                k3_state.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            fw_model = "accounts/fireworks/models/kimi-k3p1-pro"
            k3_exports = (
                f"export CLAUDE_CONFIG_DIR={shlex.quote(k3_config.as_posix())} && "
                f"export ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference && "
                f"export ANTHROPIC_AUTH_TOKEN={shlex.quote(fireworks_key)} && "
                f"export ANTHROPIC_API_KEY= && "
                f"export ANTHROPIC_MODEL={fw_model} && "
                f"export ANTHROPIC_DEFAULT_OPUS_MODEL={fw_model} && "
                f"export ANTHROPIC_DEFAULT_SONNET_MODEL={fw_model} && "
                f"export ANTHROPIC_DEFAULT_HAIKU_MODEL={fw_model} && "
                f"export ANTHROPIC_DEFAULT_FABLE_MODEL={fw_model} && "
                f"export CLAUDE_CODE_SUBAGENT_MODEL={fw_model} && "
                f"export CLAUDE_CODE_AUTO_COMPACT_WINDOW=1048576 && "
            )
            shell_cmd = (
                f"cd {shlex.quote(Path(rundir).as_posix())} && "
                f"{env_scrub} && "
                f"{k3_exports}"
                f"{exec_cmd} {shlex.quote(full_prompt)}"
            )
        elif model_provider == "seatbelt":
            # Isolate from the personal OAuth login/settings.json (same reason as
            # the fireworks route) and pre-seed onboarding so the first launch
            # doesn't stall on the welcome/theme screens.
            sb_config = get_hermes_home() / "claude-seatbelt-config"
            sb_config.mkdir(parents=True, exist_ok=True)
            sb_state = sb_config / ".claude.json"
            try:
                existing = json.loads(sb_state.read_text(encoding="utf-8")) if sb_state.exists() else {}
            except ValueError:
                existing = {}
            if not existing.get("hasCompletedOnboarding"):
                existing["hasCompletedOnboarding"] = True
                sb_state.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            # Trust the launch dir + accept bypass-permissions: both dialogs
            # default to "No, exit" in an isolated config and silently kill an
            # unattended T2 spawn. hasTrustDialogAccepted covers the trust
            # dialog; bypassPermissionsModeAccepted covers the warning.
            trust_projects = existing.setdefault("projects", {})
            proj = trust_projects.setdefault(str(Path(rundir).resolve()), {})
            changed = False
            if not proj.get("hasTrustDialogAccepted"):
                proj["hasTrustDialogAccepted"] = True
                changed = True
            if not existing.get("bypassPermissionsModeAccepted"):
                existing["bypassPermissionsModeAccepted"] = True
                changed = True
            if changed:
                sb_state.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            seatbelt_exports = (
                f"export CLAUDE_CONFIG_DIR={shlex.quote(sb_config.as_posix())} && "
                f"export ANTHROPIC_BASE_URL={SEATBELT_BASE_URL} && "
                "export ANTHROPIC_AUTH_TOKEN=seatbelt && "
                f"export ANTHROPIC_CUSTOM_HEADERS={shlex.quote(seatbelt_headers)} && "
                f"export ANTHROPIC_DEFAULT_OPUS_MODEL={shlex.quote(seatbelt_model)} && "
                f"export ANTHROPIC_DEFAULT_SONNET_MODEL={shlex.quote(seatbelt_model)} && "
                f"export ANTHROPIC_DEFAULT_HAIKU_MODEL={shlex.quote(SEATBELT_HAIKU_MODEL)} && "
                f"export ANTHROPIC_DEFAULT_FABLE_MODEL={shlex.quote(SEATBELT_FABLE_MODEL)} && "
                "export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1 && "
                "export CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 && "
            )
            # Headers are exported before env_scrub unsets TFY_API_KEY.
            shell_cmd = (
                f"cd {shlex.quote(Path(rundir).as_posix())} && "
                "unset ANTHROPIC_API_KEY ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY && "
                f"{seatbelt_exports}"
                f"{env_scrub} && "
                f"{exec_cmd} {shlex.quote(full_prompt)}"
            )
        else:
            # Only seatbelt and fireworks are routable for Claude Code. Never
            # fall through to an ambient/default endpoint.
            return {"ok": False, "error": CLAUDE_ROUTE_REFUSAL}
    # Ensure TFY_API_KEY is available inside the tmux session (the tmux server
    # may have been started before Hermes loaded .env, so it won't inherit the
    # key from the current shell). Export it explicitly in the shell command.
    tfy_key = os.environ.get("TFY_API_KEY") or ""
    tfy_export = f"export TFY_API_KEY={shlex.quote(tfy_key)} && " if tfy_key else ""
    shell_cmd = f"{tfy_export}{shell_cmd}"
    # Final guard (defense in depth): no Claude Code launch may name the
    # TrueFoundry gateway, whatever branch composed the command.
    # The brief is excluded: a task about TrueFoundry may legitimately name it.
    launch_shell = shell_cmd.replace(shlex.quote(full_prompt), "")
    if executor == "claude" and "truefoundry.cloud" in launch_shell.lower():
        return {"ok": False, "error": CLAUDE_ROUTE_REFUSAL}
    launch_args = ["tmux", "new-session", "-d", "-s", task_id, "-x", "160", "-y", "50", shell_cmd]
    launch = _run(_detached_tmux_launch(launch_args))
    if launch.returncode != 0 and launch.args[:1] == ["systemd-run"]:
        launch = _run(launch_args)
    if launch.returncode != 0:
        return {"ok": False, "error": (launch.stderr or launch.stdout or "tmux new-session failed").strip()}

    # For codex: the prompt is sent via send-keys after a short startup delay
    # (codex 0.144.x has a bug with positional prompt args — see comment above).
    # For claude: the prompt is passed as a CLI arg (safe for claude).
    if executor == "codex":
        _run(["sh", "-c", f"sleep 5 && tmux send-keys -t {shlex.quote(task_id)} -l {shlex.quote(full_prompt)} && sleep 1 && tmux send-keys -t {shlex.quote(task_id)} Enter"])
        # Verify the brief actually submitted — a failed submit leaves the session
        # idle at the prompt forever. Capture the pane after ~8s; if the prompt
        # line is still visible (not consumed), re-send Enter.
        time.sleep(8)
        state = _session_state(task_id)
        if state.get("state") == "working":
            pass  # brief landed, session is working
        else:
            # Re-send Enter — the first submit didn't take
            _run(["tmux", "send-keys", "-t", task_id, "Enter"])
            time.sleep(3)
            state = _session_state(task_id)
            if state.get("state") != "working":
                return {"ok": False, "error": f"brief submit failed: session is {state.get('state')}, not working. Check the tmux pane manually.", "task_id": task_id}

    # codex 0.154.x shows a startup confirmation ("1. Yes, continue / Press enter
    # to continue") when launched with --dangerously-bypass-approvals-and-sandbox.
    # The brief cannot land until it is dismissed; answer Yes. Sends before the
    # codex brief (which is typed literally), so an in-progress brief line is
    # never clobbered. The menu only appears at codex startup; an already-accepted
    # codex session never shows it again, so this is harmless when absent.
    if executor == "codex" and dangerous:
        _run(["tmux", "send-keys", "-t", task_id, "Enter"])
        time.sleep(2)
        _run(["tmux", "send-keys", "-t", task_id, "Enter"])

    # Full pane logging via pipe-pane crashes the git-bash/MSYS tmux server
    # (takes down ALL sessions). Only safe on real Linux/macOS tmux; on Windows
    # rely on capture-pane polling in `status` instead.
    if sys.platform != "win32":
        tmux_log = artifact_dir / "tmux.log"
        _run(["tmux", "pipe-pane", "-o", "-t", task_id, f"cat >> {shlex.quote(tmux_log.as_posix())}"])

    meta = {
        "task_id": task_id,
        "workdir": Path(workdir).as_posix(),
        "rundir": Path(rundir).as_posix(),
        "worktree": worktree,
        "worktree_path": worktree_path.as_posix() if worktree_path else None,
        "executor": executor,
        "model": model,
        "effort": effort,
        "model_provider": model_provider if executor == "claude" else None,
        "created_at": time.time(),
        "phase": "1",  # T2 lifecycle: 1 (setup) → 1b (design, optional) → 2 (implement) → 3 (gate) → 4 (PR) → 5 (cleanup)
    }
    # Optional kanban linkage: when the T2 supervisor passes the kanban task this
    # session serves, long blocking plugin calls (wait/gate) auto-heartbeat the
    # kanban claim so a >TTL blocking call can't starve the claim into a stale
    # reclaim. tmux-spawned sessions never get a worker_pid from the dispatcher,
    # so the reclaimer's pid-alive extension doesn't protect them.
    kanban_task = _kanban_task_for(args, task_id)
    kanban_board = str(args.get("kanban_board") or "").strip()
    if kanban_task:
        meta["kanban_task_id"] = kanban_task
        if kanban_board:
            meta["kanban_board"] = kanban_board
    _write_text(artifact_dir / "meta.json", json.dumps(meta, indent=2))

    # Auto-arm a background watcher for kanban-linked sessions: the T1 doesn't
    # have to remember. The watcher is a delegate_task child that polls the
    # kanban board for review_requested/blocked on this task. Bounded (~25 min)
    # so it doesn't outlive the delegation timeout.
    watcher_armed = False
    if kanban_task and kanban_board:
        try:
            import json as _json
            _ = _json  # ensure json is available in this scope
            # The watcher is armed by the T1 (delegate_task is a Hermes tool,
            # not callable from the plugin). Instead, write a flag file the T1's
            # next turn reads to know it should arm the watcher. This is the
            # closest we can get to deterministic without the plugin having
            # access to delegate_task.
            _write_text(artifact_dir / ".watcher-needed", kanban_task)
            watcher_armed = True
        except Exception:
            pass

    result = {
        "ok": True,
        "task_id": task_id,
        "session": task_id,
        "rundir": meta["rundir"],
        "artifact_dir": artifact_dir.as_posix(),
        "watcher_needed": watcher_armed,
    }
    return result


def _git_porcelain_for_fingerprint(rundir: str | None) -> str:
    if not rundir or not (Path(rundir) / ".git").exists():
        return ""
    result = _run(["git", "-C", rundir, "status", "--porcelain"])
    if result.returncode != 0:
        return ""
    return str(len([line for line in result.stdout.splitlines() if line.strip()]))


def _record_activity(task_id: str, status_file: str | None, now: float) -> float:
    """Update the on-disk activity fingerprint; return last_change_ts (bootstraps on first poll).

    Fingerprint uses status.md + outcome.md + worktree change count — not pane text,
    since some executors (codex) render an animated logo that changes every frame,
    which would look like permanent progress and defeat stall detection.
    """
    activity_path = _artifact_dir(task_id) / "activity.json"
    outcome_file = _read_text(_artifact_dir(task_id) / "outcome.md")
    meta = _read_meta(task_id)
    git_porcelain = _git_porcelain_for_fingerprint(meta.get("rundir"))
    fingerprint = hashlib.sha256(
        f"{status_file or ''}\x00{outcome_file or ''}\x00{git_porcelain}".encode("utf-8", "surrogatepass")
    ).hexdigest()

    stored = {}
    raw = _read_text(activity_path)
    if raw:
        try:
            stored = json.loads(raw)
        except ValueError:
            stored = {}

    last_change_ts = stored.get("last_change_ts")
    if not isinstance(last_change_ts, (int, float)) or stored.get("fingerprint") != fingerprint:
        last_change_ts = now
        stored.update({"fingerprint": fingerprint, "last_change_ts": last_change_ts})
        activity_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{activity_path.name}.", suffix=".tmp", dir=activity_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                json.dump(stored, temp_file)
            os.replace(temp_name, activity_path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    return last_change_ts


_VALID_OUTCOMES = {"DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"}

# Orchestration artifacts, not code — never count as "real work" or a diff violation.
_ORCHESTRATION_BASENAMES = {"outcome.md", ".task-brief.md", "status.md", "result.md", "activity.json", "meta.json"}


def _parse_outcome(raw: str) -> dict:
    """Parse a terminal token (first non-empty line) + trailing detail out of outcome.md text."""
    lines = raw.splitlines()
    first_idx = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_idx is None:
        return {"outcome": None, "detail": ""}

    token = lines[first_idx].strip().strip(".:,;").upper()
    detail = "\n".join(lines[first_idx + 1:]).strip()
    if token in _VALID_OUTCOMES:
        return {"outcome": token, "detail": detail}
    return {"outcome": None, "detail": raw.strip()}


def _read_outcome(task_id: str) -> dict:
    """Artifact-dir outcome.md is authoritative. If it's missing/PENDING/invalid, fall back to a stray
    <rundir>/outcome.md (agents sometimes write there instead of the artifact path) — but always delete
    that stray copy so it never persists in the codebase/worktree diff. Never raises.
    """
    artifact_raw = _read_text(_artifact_dir(task_id) / "outcome.md") or ""
    parsed = _parse_outcome(artifact_raw)

    stray_parsed = {"outcome": None, "detail": ""}
    try:
        meta = _read_meta(task_id)
        rundir = meta.get("rundir")
        if rundir:
            stray_path = Path(rundir) / "outcome.md"
            stray_raw = _read_text(stray_path)
            if stray_raw is not None:
                stray_parsed = _parse_outcome(stray_raw)
                stray_path.unlink(missing_ok=True)
    except Exception:
        pass

    # Artifact dir wins on a valid token; the worktree copy is cleaned up either way.
    final = parsed if parsed["outcome"] is not None else stray_parsed
    if final["outcome"] is not None:
        _v2_record_end(task_id, final["outcome"])
    return final


def _deny_guard_path() -> Path:
    """Path to the deny-guard hook script (blocks git push / gh pr / secrets in T3 sessions)."""
    return get_hermes_home() / "scripts" / "deny-guard.sh"


def _stop_gate_path() -> Path:
    """Path to the Stop hook script (records stop receipt, runs Rust syntax lint, blocks uncommitted complete)."""
    return get_hermes_home() / "scripts" / "t3-stop-gate.py"


def _error_journal_path() -> Path:
    return get_hermes_home() / "scripts" / "error-journal.py"


def _error_journal_inject(executor: str) -> str:
    """Return auto-promoted learned rules for *executor* from error-journal.py, or empty string."""
    ej = _error_journal_path()
    if not ej.is_file():
        return ""
    res = _run(["python3", str(ej), "inject", executor])
    return res.stdout.strip() if res.returncode == 0 and res.stdout else ""


def _error_journal_record(task_id: str, executor: str, error_type: str, trace: str, fix: str) -> None:
    """Best-effort record + auto-promote into error-journal.py when a gate check fails."""
    ej = _error_journal_path()
    if not ej.is_file() or not trace:
        return
    try:
        _run(["python3", str(ej), "record", task_id, executor, error_type, trace[:500], fix[:300]])
    except Exception:
        pass


def _native_claude_status(task_id: str) -> str | None:
    """Read Claude Code 2.1+'s native session JSON (`status`: 'idle' | 'working') if matched by tmux session name."""
    for base in (get_hermes_home() / "claude-seatbelt-config" / "sessions",
                 get_hermes_home() / "claude-k3-config" / "sessions",
                 Path.home() / ".claude" / "sessions"):
        if not base.is_dir():
            continue
        try:
            for entry in base.glob("*.json"):
                data = json.loads(entry.read_text("utf-8"))
                tmux_ref = str(data.get("tmux") or "")
                if tmux_ref.startswith(f"{task_id}:"):
                    st = str(data.get("status") or "").strip().lower()
                    if st in {"idle", "working"}:
                        return st
        except Exception:
            continue
    return None


_KANBAN_HB_MIN_INTERVAL = 60  # seconds between auto-heartbeats per session
_kanban_hb_last: dict[str, float] = {}  # task_id -> last heartbeat (monotonic)


def _maybe_kanban_heartbeat(task_id: str, *, force: bool = False) -> None:
    """Best-effort kanban claim heartbeat for a kanban-linked session.

    Reads the session's meta.json for kanban_task_id/kanban_board (set at start).
    Shells out to `hermes kanban heartbeat` so the CLI's own rules (board routing,
    claim verification) apply. Throttled to once per _KANBAN_HB_MIN_INTERVAL per
    session. Never raises — a heartbeat failure must not break the plugin action.

    This is the structural fix for long blocking calls starving the claim TTL:
    the supervisor's event loop is blocked inside `wait`, so the heartbeat has to
    come from inside the loop. tmux-spawned sessions never get a worker_pid from
    the dispatcher, so the reclaimer's pid-alive extension doesn't protect them.
    """
    try:
        if not task_id:
            return
        meta_raw = _read_text(_artifact_dir(task_id) / "meta.json")
        meta = json.loads(meta_raw) if meta_raw else {}
        ktask = meta.get("kanban_task_id")
        if not ktask:
            m_kb = re.match(r"^(?:t2-)?(t_[0-9a-f]{8})\b", task_id)
            if m_kb:
                ktask = m_kb.group(1)
        if not ktask:
            return
        now = time.monotonic()
        last = _kanban_hb_last.get(task_id, 0.0)
        if not force and (now - last) < _KANBAN_HB_MIN_INTERVAL:
            return
        cmd = ["hermes", "kanban"]
        kboard = meta.get("kanban_board")
        if kboard:
            cmd += ["--board", str(kboard)]
        cmd += ["heartbeat", str(ktask), "--note", "auto-heartbeat: supervised session active"]
        result = _run(cmd)
        if result.returncode == 0:
            _kanban_hb_last[task_id] = now
    except Exception:
        pass


def _session_state(task_id: str, tail: int = 60, stall_seconds: int = STALL_SECONDS) -> dict:
    """Classify a session as working / needs_input / stalled / done / exited from pane + status.md."""
    artifact_dir = _artifact_dir(task_id)
    status_file = _read_text(artifact_dir / "status.md")

    if not _session_exists(task_id):
        return {
            "task_id": task_id,
            "state": "exited",
            "alive": False,
            "done": True,
            "reason": "session_exited",
            "status_file": status_file,
            "result": _read_text(artifact_dir / "result.md"),
            "outcome": _read_outcome(task_id)["outcome"],
            "doom_loop": doom_loop_active(task_id),
        }

    capture = _run(["tmux", "capture-pane", "-t", task_id, "-p", "-S", f"-{tail}"])
    pane = capture.stdout if capture.returncode == 0 else ""
    lines = [line for line in pane.splitlines() if line.strip()]
    native_status = _native_claude_status(task_id)
    waiting_for_input = (bool(lines) and "❯" in lines[-1]) or (native_status == "idle")
    done = (status_file or "").strip().lower() == "complete"

    # Claude Code / Codex show a live activity indicator in the pane while a turn
    # is running (a spinner word + "esc to interrupt", elapsed timer, or a token
    # counter). If that's present, the session is WORKING — a high-effort turn can
    # legitimately think for minutes without writing status.md, so file-change
    # staleness alone must NOT flag it stalled (that would Esc a thinking session).
    tail_text = "\n".join(lines[-6:]) if lines else ""
    actively_working = (native_status == "working") or bool(
        re.search(r"esc to interrupt|Thinking…|Working…|↑ \d|tokens|\(\d+m?s? ", tail_text)
    )
    if native_status == "working":
        waiting_for_input = False

    now = time.time()
    last_change_ts = _record_activity(task_id, status_file, now)
    seconds_since_change = now - last_change_ts
    doom_loop = doom_loop_active(task_id)
    stalled = (
        not done
        and not waiting_for_input
        and not actively_working
        and (seconds_since_change >= stall_seconds or doom_loop)
    )

    if done:
        state = "done"
    elif waiting_for_input:
        state = "needs_input"
    elif stalled:
        state = "stalled"
    else:
        state = "working"

    return {
        "task_id": task_id,
        "state": state,
        "alive": True,
        "status_file": status_file,
        "pane": pane,
        "waiting_for_input": waiting_for_input,
        "done": done,
        "seconds_since_change": seconds_since_change,
        "doom_loop": doom_loop,
        "outcome": _read_outcome(task_id)["outcome"],
    }


def _status(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}
    try:
        tail = int(args.get("tail") or 60)
    except (TypeError, ValueError):
        tail = 60
    try:
        stall_seconds = int(args.get("stall_seconds") or STALL_SECONDS)
    except (TypeError, ValueError):
        stall_seconds = STALL_SECONDS
    return {"ok": True, **_session_state(task_id, tail, stall_seconds)}


def _wait(args: dict) -> dict:
    """Block until the session needs input, stalls, exits, or reports complete — or times out.

    Deterministic replacement for a hand-rolled poll loop: returns as soon as the
    session leaves the 'working' state so the caller is not left blind on a stall.
    """
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}
    try:
        timeout = int(args.get("timeout") or 900)
    except (TypeError, ValueError):
        timeout = 900
    try:
        interval = max(3, int(args.get("interval") or 15))
    except (TypeError, ValueError):
        interval = 15
    try:
        tail = int(args.get("tail") or 60)
    except (TypeError, ValueError):
        tail = 60
    try:
        stall_seconds = int(args.get("stall_seconds") or STALL_SECONDS)
    except (TypeError, ValueError):
        stall_seconds = STALL_SECONDS

    deadline = time.monotonic() + timeout
    artifact_dir = _artifact_dir(task_id)
    while True:
        # Auto-heartbeat the kanban claim this session serves (if any) — the
        # supervisor's event loop is blocked here, so a >TTL blocking wait would
        # otherwise let the claim expire into a stale reclaim.
        _maybe_kanban_heartbeat(task_id)
        state = _session_state(task_id, tail, stall_seconds)
        if state["state"] in {"needs_input", "stalled", "done", "exited"}:
            result = {"ok": True, "timed_out": False, **state}
            # Surface a watcher-needed hint when the session is kanban-linked
            # and no watcher flag has been consumed yet.
            if state.get("outcome") and (artifact_dir / ".watcher-needed").exists():
                result["watcher_needed"] = True
            if (artifact_dir / ".watcher-expired").exists():
                result["watcher_expired"] = True
            return result
        if time.monotonic() >= deadline:
            result = {"ok": True, "timed_out": True, **state}
            if (artifact_dir / ".watcher-needed").exists():
                result["watcher_needed"] = True
            if (artifact_dir / ".watcher-expired").exists():
                result["watcher_expired"] = True
            return result
        time.sleep(interval)


def _steer(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    message = args.get("message")
    if not task_id or message is None:
        return {"ok": False, "error": "task_id and message are required"}
    if not _session_exists(task_id):
        return {"ok": False, "error": f"tmux session '{task_id}' not found"}

    send = _run(["tmux", "send-keys", "-t", task_id, "-l", str(message)])
    if send.returncode != 0:
        return {"ok": False, "error": (send.stderr or send.stdout or "send-keys failed").strip()}
    # Claude Code / Codex TUIs (Ink-based) need a beat to commit the pasted text
    # into their input buffer before Enter registers. Firing Enter instantly after
    # the text is a no-op — the message lands in the box but never submits, leaving
    # the session idle-at-prompt (looks like a stall). Pause, then submit, then
    # re-submit once if the input line still shows the text uncommitted.
    time.sleep(0.5)
    enter = _run(["tmux", "send-keys", "-t", task_id, "Enter"])
    if enter.returncode != 0:
        return {"ok": False, "error": (enter.stderr or enter.stdout or "send-keys Enter failed").strip()}
    # Verify submission: if the tail still shows our text sitting on the input
    # line (prompt marker + our message, not consumed), the Enter didn't take —
    # send it once more.
    time.sleep(0.7)
    pane = _run(["tmux", "capture-pane", "-t", task_id, "-p"])
    tail = (pane.stdout or "")[-600:]
    snippet = str(message).strip()[:40]
    if snippet and snippet in tail and ("❯" in tail or "> " in tail):
        _run(["tmux", "send-keys", "-t", task_id, "Enter"])

    return {"ok": True, "task_id": task_id, "sent": str(message)}


def _interrupt(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}
    if not _session_exists(task_id):
        return {"ok": False, "error": "no such session"}

    sent = _run(["tmux", "send-keys", "-t", task_id, "Escape"])
    if sent.returncode != 0:
        return {"ok": False, "error": (sent.stderr or sent.stdout or "send-keys Escape failed").strip()}
    return {"ok": True, "task_id": task_id, "sent": "Escape"}


def _diagnose(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}

    state = _session_state(task_id)
    if state["alive"]:
        capture = _run(["tmux", "capture-pane", "-t", task_id, "-p", "-S", "-120"])
        pane_tail = capture.stdout if capture.returncode == 0 else (capture.stderr or "capture-pane failed").strip()
    else:
        pane_tail = "session gone"

    tmux_log = _read_text(_artifact_dir(task_id) / "tmux.log")
    tmux_log_tail = "\n".join(tmux_log.splitlines()[-120:]) if tmux_log is not None else None
    return {
        "ok": True,
        "task_id": task_id,
        "pane_tail": pane_tail,
        "tmux_log_tail": tmux_log_tail,
        "meta": _read_meta(task_id),
        "state": state,
        "seconds_since_change": state.get("seconds_since_change"),
    }


def _result(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}

    artifact_dir = _artifact_dir(task_id)
    meta = _read_meta(task_id)
    rundir = meta.get("rundir")

    git_status = None
    git_diffstat = None
    if rundir and (Path(rundir) / ".git").exists():
        status_run = _run(["git", "-C", rundir, "status", "--porcelain"])
        if status_run.returncode == 0:
            git_status = status_run.stdout
        diff_run = _run(["git", "-C", rundir, "diff", "--stat"])
        if diff_run.returncode == 0:
            git_diffstat = diff_run.stdout

    outcome = _read_outcome(task_id)
    return {
        "ok": True,
        "task_id": task_id,
        "status_file": _read_text(artifact_dir / "status.md"),
        "result": _read_text(artifact_dir / "result.md"),
        "git_status": git_status,
        "git_diffstat": git_diffstat,
        "outcome": outcome["outcome"],
        "outcome_detail": outcome["detail"],
    }


def _stop(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}
    keep_worktree = _coerce_bool(args.get("keep_worktree"), True)

    if _session_exists(task_id):
        _run(["tmux", "send-keys", "-t", task_id, "-l", "/exit"])
        _run(["tmux", "send-keys", "-t", task_id, "Enter"])
        time.sleep(1.5)

    killed = _run(["tmux", "kill-session", "-t", task_id]).returncode == 0

    meta = _read_meta(task_id)
    if not keep_worktree:
        worktree_path = meta.get("worktree_path")
        workdir = meta.get("workdir")
        if worktree_path and workdir:
            _run(["git", "-C", workdir, "worktree", "remove", "--force", worktree_path])

    return {"ok": True, "task_id": task_id, "killed": killed}


def _recover(args: dict) -> dict:
    """Report task artifacts whose tmux sessions are gone."""
    task_id = str(args.get("task_id") or "").strip() or None
    if task_id:
        task_ids = [task_id]
    elif _tasks_root().exists():
        task_ids = [p.name for p in _tasks_root().iterdir() if p.is_dir() and not p.name.startswith(".")]
    else:
        task_ids = []

    orphaned = []
    for tid in task_ids:
        try:
            if _session_exists(tid):
                continue
            orphaned.append({"task_id": tid, "orphaned": True})
        except Exception as exc:
            orphaned.append({"task_id": tid, "error": f"{type(exc).__name__}: {exc}"})

    return {"ok": True, "orphaned": orphaned}


def _clean(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}
    force = _coerce_bool(args.get("force"), False)
    if _session_exists(task_id) and not force:
        return {"ok": False, "error": "session still alive"}

    meta = _read_meta(task_id)
    remove_worktree = _coerce_bool(args.get("remove_worktree"), False)
    removed_worktree = False
    if remove_worktree:
        worktree_path = meta.get("worktree_path")
        workdir = meta.get("workdir")
        if worktree_path and workdir:
            removed_worktree = _run(["git", "-C", workdir, "worktree", "remove", "--force", worktree_path]).returncode == 0

    artifact_dir = _artifact_dir(task_id)
    removed_dir = artifact_dir.exists()
    if removed_dir:
        shutil.rmtree(artifact_dir)

    return {
        "ok": True,
        "task_id": task_id,
        "removed_dir": removed_dir,
        "removed_worktree": removed_worktree,
    }


def _parse_allowlist(raw: Any) -> list[str]:
    """Accept a real list or a JSON-encoded string; leniently coerce to list[str]."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(p) for p in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return [raw]
        if isinstance(parsed, list):
            return [str(p) for p in parsed]
        return [raw]
    return []


def _matches_allowlist(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.endswith("/**"):
            # fnmatch has no recursive-glob; treat dir/** as a path prefix match.
            prefix = pattern[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif "**" in pattern and fnmatch.fnmatch(path, pattern.replace("**", "*")):
            return True
    return False


def _check_diff(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    base_sha = str(args.get("base_sha") or "").strip()
    if not task_id or not base_sha:
        return {"ok": False, "error": "task_id and base_sha are required"}

    meta = _read_meta(task_id)
    rundir = meta.get("rundir")
    if not rundir or not (Path(rundir) / ".git").exists():
        return {"ok": False, "error": "rundir missing or not a git repo"}

    allowlist = _parse_allowlist(args.get("allowlist"))
    reset_on_violation = _coerce_bool(args.get("reset_on_violation"), False)

    committed = _run(["git", "-C", rundir, "diff", "--name-only", base_sha, "HEAD"])
    working = _run(["git", "-C", rundir, "diff", "--name-only", base_sha])
    if committed.returncode != 0 or working.returncode != 0:
        err = (committed.stderr or working.stderr or "git diff failed").strip()
        return {"ok": False, "error": err}

    # --untracked-files=all expands new directories to individual file paths (default
    # collapses "dir/" to one entry, which would hide files inside from the allowlist check).
    porcelain = _run(["git", "-C", rundir, "status", "--porcelain", "--untracked-files=all"])
    untracked = [line[3:].strip() for line in porcelain.stdout.splitlines() if line.startswith("??")]

    changed = set()
    changed.update(p.strip() for p in committed.stdout.splitlines() if p.strip())
    changed.update(p.strip() for p in working.stdout.splitlines() if p.strip())
    changed.update(untracked)
    changed = {p for p in changed if Path(p).name not in _ORCHESTRATION_BASENAMES}

    violating = sorted(p for p in changed if not _matches_allowlist(p, allowlist))
    clean = not violating

    reset = False
    if reset_on_violation and not clean:
        _run(["git", "-C", rundir, "reset", "--hard", base_sha])
        _run(["git", "-C", rundir, "clean", "-fd"])
        reset = True

    return {
        "ok": True,
        "task_id": task_id,
        "clean": clean,
        "changed_paths": sorted(changed),
        "violating_paths": violating,
        "reset": reset,
    }


def _short_diffstat(diffstat: str, cached_diffstat: str, porcelain: str) -> str:
    for text in (diffstat, cached_diffstat):
        lines = [line for line in text.strip().splitlines() if line.strip()]
        if lines:
            return lines[-1].strip()
    lines = [line for line in porcelain.strip().splitlines() if line.strip()]
    if lines:
        return f"{len(lines)} file(s) changed (untracked/porcelain only)"
    return "no changes"


def _check_impl_complete(task_id: str) -> dict:
    meta = _read_meta(task_id)
    rundir = meta.get("rundir")
    status_text = _read_text(_artifact_dir(task_id) / "status.md")
    status_ok = (status_text or "").strip().lower() == "complete"
    if not status_ok:
        got = (status_text or "").strip() or "<missing>"
        return {"result": "fail", "evidence": f"status.md={got!r}, expected 'complete'"}

    if not rundir or not (Path(rundir) / ".git").exists():
        return {"result": "pass", "evidence": "status=complete; git verification unavailable (rundir is not a git repo)"}

    # --untracked-files=all expands new directories so filenames can be checked against
    # _ORCHESTRATION_BASENAMES (default porcelain would collapse "dir/" to one entry).
    porcelain_run = _run(["git", "-C", rundir, "status", "--porcelain", "--untracked-files=all"])
    diff_run = _run(["git", "-C", rundir, "diff", "--stat"])
    cached_run = _run(["git", "-C", rundir, "diff", "--cached", "--stat"])
    porcelain = porcelain_run.stdout if porcelain_run.returncode == 0 else ""
    diffstat = diff_run.stdout if diff_run.returncode == 0 else ""
    cached_diffstat = cached_run.stdout if cached_run.returncode == 0 else ""

    changed_paths = {line[3:].strip() for line in porcelain.splitlines() if line.strip()}
    real_paths = {p for p in changed_paths if Path(p).name not in _ORCHESTRATION_BASENAMES}
    if real_paths:
        return {"result": "pass", "evidence": f"status=complete; {_short_diffstat(diffstat, cached_diffstat, porcelain)}"}

    # Nothing uncommitted. A finished agent that committed its work has a clean
    # worktree — reading only the worktree calls that "zero changes" and fails
    # the gate on the tidiest possible outcome. Fall back to committed changes.
    head_run = _run(["git", "-C", rundir, "log", "--oneline", "-5"])
    head_log = head_run.stdout.strip() if head_run.returncode == 0 else ""
    if head_log:
        return {"result": "pass", "evidence": f"status=complete; worktree clean, committed work present:\n{head_log}"}

    return {"result": "fail", "evidence": "status=complete but git shows zero changes (no uncommitted files, no commits)"}


_VALID_VERDICT_RESULTS = {"pass", "fail", "skipped"}


def _coerce_verdict(raw: Any, default_evidence: str) -> dict:
    """Parse a caller-supplied {"result", "evidence"} verdict (dict or JSON string). Falls back to skipped on absence/malformance."""
    stub = {"result": "skipped", "evidence": default_evidence}
    if raw is None:
        return stub
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return stub
    if not isinstance(raw, dict):
        return stub
    result = raw.get("result")
    if result not in _VALID_VERDICT_RESULTS:
        return stub
    return {"result": result, "evidence": str(raw.get("evidence") or "")}


_PHASE_ORDER = ["1", "1b", "2", "3", "4", "5"]

def _set_phase(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    phase = str(args.get("phase") or "").strip()
    if not task_id or not phase:
        return {"ok": False, "error": "task_id and phase are required"}
    if phase not in _PHASE_ORDER:
        return {"ok": False, "error": f"invalid phase {phase!r} (must be one of {_PHASE_ORDER})"}
    meta = _read_meta(task_id)
    if not meta:
        return {"ok": False, "error": f"no task {task_id!r}"}
    current = meta.get("phase", "1")
    current_idx = _PHASE_ORDER.index(current) if current in _PHASE_ORDER else 0
    target_idx = _PHASE_ORDER.index(phase)
    if target_idx < current_idx:
        return {"ok": False, "error": f"cannot go backwards: current phase is {current}, requested {phase}"}
    meta["phase"] = phase
    meta[f"phase_{phase}_entered_at"] = time.time()
    _write_text(_artifact_dir(task_id) / "meta.json", json.dumps(meta, indent=2))
    return {"ok": True, "task_id": task_id, "phase": phase, "previous": current}

def _gate(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}

    # Phase gate: refuse to run the exit gate if the session hasn't been advanced to Phase 3.
    meta = _read_meta(task_id)
    current_phase = meta.get("phase", "1")
    if current_phase not in ("3", "4", "5"):
        return {"ok": False, "error": f"gate called in phase {current_phase} — advance to phase 3 first via `claude_orchestrate action=set_phase task_id={task_id} phase=3`", "phase": current_phase}

    # The gate runs at the end of a long supervised turn — heartbeat the kanban
    # claim (if linked) so the claim is fresh when the supervisor next comments
    # gate evidence. Forced (bypasses the throttle): this runs once per phase,
    # not in a poll loop.
    _maybe_kanban_heartbeat(task_id, force=True)

    impl = _check_impl_complete(task_id)
    review = _coerce_verdict(args.get("review"), "not implemented (Tier-2)")
    tests = _coerce_verdict(args.get("tests"), "not implemented (Tier-2)")

    # Design-doc gate: when the session is kanban-linked, verify a design doc
    # is attached before allowing the implementation phase to pass. The T2
    # skill's pitfall is "forgetting to attach the accepted design doc before
    # Phase 2" — this makes it structural.
    design_doc_ok = True
    design_doc_note = ""
    meta = _read_meta(task_id)
    ktask = meta.get("kanban_task_id")
    kboard = meta.get("kanban_board", "")
    if ktask:
        try:
            cmd = ["hermes", "kanban", "attachments", ktask]
            if kboard:
                cmd += ["--board", kboard]
            att = _run(cmd)
            if att.returncode == 0:
                attachments = att.stdout or ""
                if "design" not in attachments.lower() and ".md" not in attachments:
                    design_doc_ok = False
                    design_doc_note = "no design doc attached — run `hermes kanban attach` before Phase 2"
        except Exception:
            pass  # attachment check is best-effort; don't block on a CLI failure

    passed = all(c["result"] == "pass" for c in (impl, review, tests) if c["result"] != "skipped") and design_doc_ok

    executor = str(meta.get("executor") or "claude")
    if impl["result"] == "fail":
        _error_journal_record(task_id, executor, "impl_incomplete", impl.get("evidence", ""), "Ensure status.md is 'complete' and all changes are committed in the worktree before finishing.")
    if review["result"] == "fail":
        _error_journal_record(task_id, executor, "review_needs_fixes", review.get("evidence", ""), "Address all P0/P1 code review findings before advancing.")
    if tests["result"] == "fail":
        _error_journal_record(task_id, executor, "test_failure", tests.get("evidence", ""), "Run and pass the test suite on the branch before marking complete.")

    return {
        "ok": True,
        "task_id": task_id,
        "impl": impl,
        "review": review,
        "tests": tests,
        "passed": passed,
        "doom_loop": doom_loop_active(task_id),
        "design_doc_attached": design_doc_ok,
        "design_doc_note": design_doc_note or None,
    }


def _list(args: dict) -> dict:
    listing = _run(["tmux", "list-sessions", "-F", "#{session_name}"])
    names = [line.strip() for line in listing.stdout.splitlines() if line.strip()] if listing.returncode == 0 else []
    sessions = [{"task_id": name, "status": _read_text(_artifact_dir(name) / "status.md")} for name in names]
    return {"ok": True, "sessions": sessions}


_ACTIONS = {
    "start": _start,
    "status": _status,
    "wait": _wait,
    "steer": _steer,
    "interrupt": _interrupt,
    "diagnose": _diagnose,
    "result": _result,
    "stop": _stop,
    "list": _list,
    "recover": _recover,
    "gate": _gate,
    "set_phase": _set_phase,
    "clean": _clean,
    "check_diff": _check_diff,
}


def _handle(args: dict, **kw) -> str:
    try:
        action = str(args.get("action") or "").strip().lower()
        task_id = str(args.get("task_id") or "").strip()
        if task_id and action in {"start", "status", "wait", "steer", "interrupt", "diagnose", "result", "gate", "set_phase"}:
            _maybe_kanban_heartbeat(task_id)
        fn = _ACTIONS.get(action)
        if fn is None:
            return json.dumps({"ok": False, "error": f"unknown action: {action}"})
        return json.dumps(fn(args))
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


CLAUDE_ORCHESTRATE_SCHEMA = {
    "name": "claude_orchestrate",
    "description": (
    "Drive interactive Claude Code sessions inside tmux: start a session, poll its status/pane output "
    "(status/wait report state as working/needs_input/stalled/done/exited; stalled means no pane or status.md "
    "change for stall_seconds, or a doom-loop breaker tripped), block until it needs input, stalls, or exits "
    "(wait), steer it with follow-up "
    "input, fetch its result, or stop it. "
    "gate runs the exit-gate verdict (impl-complete check plus caller-supplied review/tests verdicts, "
    "defaulting to skipped stubs if omitted) and also reports doom_loop. "
    "clean deletes a dead task's artifact dir (and optionally its worktree). "
    "check_diff computes changed paths since base_sha (committed + working tree + untracked) and "
    "checks them against a glob allowlist, optionally hard-resetting the worktree on violation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "Action to perform. interrupt sends Esc to interrupt a wedged/over-thinking Claude session "
                    "without killing it; diagnose dumps pane, log, meta, and state for hang root-causing."
                ),
                "enum": [
                    "start", "status", "wait", "steer", "result", "stop", "list",
                    "recover", "gate", "set_phase", "clean", "check_diff", "interrupt", "diagnose",
                ],
            },
            "task_id": {"type": "string", "description": "tmux session name / artifact dir name"},
            "prompt": {"type": "string", "description": "Initial task for Claude (start)"},
            "workdir": {"type": "string", "description": "Absolute dir Claude runs in (start)"},
            "kanban_task_id": {
                "type": "string",
                "description": (
                    "Kanban task this session serves (start). When set, long blocking calls "
                    "(wait/gate) auto-heartbeat the kanban claim so a >TTL blocking call can't "
                    "starve the claim into a stale reclaim. Persisted to meta.json."
                ),
            },
            "kanban_board": {
                "type": "string",
                "description": (
                    "Kanban board slug for kanban_task_id (start). Passed as --board on the "
                    "auto-heartbeat CLI call so board routing never relies on the sticky "
                    "active board."
                ),
            },
            "worktree": {
                "type": "string",
                "description": "If set, create a git worktree+branch of this name off workdir before running Claude there (start)",
            },
            "dangerous": {
                "type": "boolean",
                "description": "Pass --dangerously-skip-permissions (start, default true)",
            },
            "executor": {
                "type": "string",
                "enum": ["claude", "codex"],
                "description": "Coding CLI to launch (start). Default claude; codex is the fallback executor.",
            },
            "model": {
                "type": "string",
                "description": "Model id to pin for this session (claude --model / codex -m). Omit for the executor default.",
            },
            "model_provider": {
                "type": "string",
                "enum": ["truefoundry", "fireworks", "seatbelt"],
                "description": (
                    "Backend routing for the claude executor (start). "
                    "truefoundry = codex executor only (refused for claude: anthropic-primary billing); "
                    "fireworks = Kimi K3.1 Pro via Fireworks' Anthropic-compatible endpoint "
                    "(isolated CLAUDE_CONFIG_DIR, ignores --model); "
                    "seatbelt = Claude via the seatbelt gateway (claude executor only; model must be 'opus' or 'sonnet')."
                ),
            },
            "effort": {
                "type": "string",
                "enum": ["low", "medium", "high", "xhigh", "max"],
                "description": "Reasoning effort for the claude executor (start; --effort). Omit for the CLI default.",
            },
            "tail": {"type": "integer", "description": "Lines of pane output to return (status/wait, default 60)"},
            "timeout": {"type": "integer", "description": "Max seconds to block before returning timed_out (wait, default 600)"},
            "interval": {"type": "integer", "description": "Seconds between polls (wait, default 15, min 3)"},
            "stall_seconds": {
                "type": "integer",
                "description": (
                    "Seconds of no pane/status change before state becomes 'stalled' (status/wait, default 300)"
                ),
            },
            "message": {"type": "string", "description": "Text to send into the session (steer)"},
            "phase": {
                "type": "string",
                "enum": ["1", "1b", "2", "3", "4", "5"],
                "description": "Advance the task lifecycle phase (set_phase). Phases: 1=setup, 1b=design, 2=implement, 3=gate, 4=PR, 5=cleanup.",
            },
            "keep_worktree": {
                "type": "boolean",
                "description": "Keep the worktree on disk after stop (default true)",
            },
            "review": {
                "type": "object",
                "description": (
                    "External review verdict to feed into the gate composite (gate). "
                    "JSON object {result: pass|fail|skipped, evidence: str}. Defaults to a skipped stub if omitted."
                ),
            },
            "tests": {
                "type": "object",
                "description": (
                    "External test verdict to feed into the gate composite (gate). "
                    "JSON object {result: pass|fail|skipped, evidence: str}. Defaults to a skipped stub if omitted."
                ),
            },
            "remove_worktree": {
                "type": "boolean",
                "description": "Also `git worktree remove --force` the task's worktree (clean, default false)",
            },
            "force": {
                "type": "boolean",
                "description": "Allow clean to remove an artifact directory while its session is live (clean, default false)",
            },
            "base_sha": {
                "type": "string",
                "description": "Commit before the fixer ran, to diff against (check_diff, required)",
            },
            "allowlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Glob patterns (fnmatch-style, repo-relative POSIX paths) changed files must match "
                    "(check_diff, required). Accepts a JSON string or a real list."
                ),
            },
            "reset_on_violation": {
                "type": "boolean",
                "description": (
                    "If true and there are violating paths, hard-reset the worktree to base_sha and drop "
                    "untracked files (check_diff, default false)"
                ),
            },
        },
        "required": ["action"],
    },
}


def register(ctx) -> None:
    ctx.register_tool(
        name="claude_orchestrate",
        toolset="claude_orchestrate",
        schema=CLAUDE_ORCHESTRATE_SCHEMA,
        handler=_handle,
        check_fn=_check_available,
        emoji="🤖",
    )
