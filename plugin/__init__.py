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
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

WORKTREES_DIRNAME = ".orchestrate-worktrees"
SUBPROCESS_TIMEOUT = 15
STALL_SECONDS = 300

def _tasks_root() -> Path:
    return get_hermes_home() / "tasks"


def _run(cmd: list[str], timeout: int = SUBPROCESS_TIMEOUT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", f"{type(exc).__name__}: {exc}")


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


def _start(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    prompt = args.get("prompt")
    workdir = str(args.get("workdir") or "").strip()
    worktree = str(args.get("worktree") or "").strip() or None
    dangerous = _coerce_bool(args.get("dangerous"), True)
    executor = str(args.get("executor") or "claude").strip().lower()
    model = str(args.get("model") or "").strip() or None
    effort = str(args.get("effort") or "").strip().lower() or None
    model_provider = str(args.get("model_provider") or "truefoundry").strip().lower()

    if not task_id or not prompt or not workdir:
        return {"ok": False, "error": "task_id, prompt, and workdir are required"}
    if executor not in {"claude", "codex"}:
        return {"ok": False, "error": f"invalid executor: {executor!r} (must be 'claude' or 'codex')"}
    if model_provider not in {"truefoundry", "fireworks"}:
        return {"ok": False, "error": f"invalid model_provider: {model_provider!r} (must be 'truefoundry' or 'fireworks')"}
    if effort and effort not in {"low", "medium", "high", "xhigh", "max"}:
        return {"ok": False, "error": f"invalid effort: {effort!r}"}
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
    full_prompt = f"{prompt}{status_instruction}"

    if executor == "codex":
        exec_cmd = "codex"
        if dangerous:
            exec_cmd += " --dangerously-bypass-approvals-and-sandbox"
        if model:
            exec_cmd += f" -m {shlex.quote(model)}"
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
        if model and model_provider != "fireworks":
            # In the fireworks path the model is set via ANTHROPIC_MODEL env vars;
            # passing --model truncates the accounts/... path in interactive mode (403).
            exec_cmd += f" --model {shlex.quote(model)}"
        if effort:
            exec_cmd += f" --effort {shlex.quote(effort)}"
        # Deny-guard hook: structurally block git push / gh pr create/merge /
        # secret reads / destructive commands in the T3 session. The merge gate
        # is the broker — the agent edits+commits, never pushes/merges. Write a
        # per-session settings.json with the hook and pass it via --settings.
        deny_settings = artifact_dir / "deny-settings.json"
        deny_settings.write_text(json.dumps({
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": str(_deny_guard_path())}]}]}
        }), encoding="utf-8")
        exec_cmd += f" --settings {shlex.quote(str(deny_settings))}"
        # Secret-scrub: pop credentials from the child env so a Bash-equipped
        # agent can't exfiltrate them (the broker holds the secrets and pushes
        # on the agent's behalf). NOTE: do NOT scrub FIREWORKS_API_KEY — the
        # fireworks path needs it (exported as ANTHROPIC_AUTH_TOKEN).
        env_scrub = " ".join(
            f"unset {k}" for k in ("GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "TFY_API_KEY", "TRUEFOUNDRY_API_KEY")
        )
        if model_provider == "fireworks":
            # Route this session to Kimi K3 on Fireworks' Anthropic-compatible
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
            k3_model = "accounts/fireworks/models/kimi-k3"
            k3_exports = (
                f"export CLAUDE_CONFIG_DIR={shlex.quote(k3_config.as_posix())} && "
                f"export ANTHROPIC_BASE_URL=https://api.fireworks.ai/inference && "
                f"export ANTHROPIC_AUTH_TOKEN={shlex.quote(fireworks_key)} && "
                f"export ANTHROPIC_API_KEY= && "
                f"export ANTHROPIC_MODEL={k3_model} && "
                f"export ANTHROPIC_DEFAULT_OPUS_MODEL={k3_model} && "
                f"export ANTHROPIC_DEFAULT_SONNET_MODEL={k3_model} && "
                f"export ANTHROPIC_DEFAULT_HAIKU_MODEL={k3_model} && "
                f"export ANTHROPIC_DEFAULT_FABLE_MODEL={k3_model} && "
                f"export CLAUDE_CODE_SUBAGENT_MODEL={k3_model} && "
                f"export CLAUDE_CODE_AUTO_COMPACT_WINDOW=1048576 && "
            )
            shell_cmd = (
                f"cd {shlex.quote(Path(rundir).as_posix())} && "
                f"{env_scrub} && "
                f"{k3_exports}"
                f"{exec_cmd} {shlex.quote(full_prompt)}"
            )
        else:
            shell_cmd = (
                f"cd {shlex.quote(Path(rundir).as_posix())} && "
                f"{env_scrub} && "
                # ambient ANTHROPIC_API_KEY breaks the TrueFoundry gateway claude uses
                "unset ANTHROPIC_API_KEY ANTHROPIC_API_KEY_BACKUP BACKUP_ANTHROPIC_API_KEY && "
                f"{exec_cmd} {shlex.quote(full_prompt)}"
            )
    # Ensure TFY_API_KEY is available inside the tmux session (the tmux server
    # may have been started before Hermes loaded .env, so it won't inherit the
    # key from the current shell). Export it explicitly in the shell command.
    tfy_key = os.environ.get("TFY_API_KEY") or ""
    tfy_export = f"export TFY_API_KEY={shlex.quote(tfy_key)} && " if tfy_key else ""
    shell_cmd = f"{tfy_export}{shell_cmd}"
    launch = _run(["tmux", "new-session", "-d", "-s", task_id, "-x", "160", "-y", "50", shell_cmd])
    if launch.returncode != 0:
        return {"ok": False, "error": (launch.stderr or launch.stdout or "tmux new-session failed").strip()}

    # For codex: the prompt is sent via send-keys after a short startup delay
    # (codex 0.144.x has a bug with positional prompt args — see comment above).
    # For claude: the prompt is passed as a CLI arg (safe for claude).
    if executor == "codex":
        _run(["sh", "-c", f"sleep 5 && tmux send-keys -t {shlex.quote(task_id)} -l {shlex.quote(full_prompt)} && sleep 1 && tmux send-keys -t {shlex.quote(task_id)} Enter"])

    # Full pane logging via pipe-pane crashes the git-bash/MSYS tmux server
    # (takes down ALL sessions). Only safe on real Linux/macOS tmux; on Windows
    # rely on capture-pane polling in `status` instead.
    if sys.platform != "win32":
        tmux_log = artifact_dir / "tmux.log"
        _run(["tmux", "pipe-pane", "-o", "-t", task_id, f"exec >> {shlex.quote(tmux_log.as_posix())}"])

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
    }
    _write_text(artifact_dir / "meta.json", json.dumps(meta, indent=2))

    return {
        "ok": True,
        "task_id": task_id,
        "session": task_id,
        "rundir": meta["rundir"],
        "artifact_dir": artifact_dir.as_posix(),
    }


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
        _write_text(activity_path, json.dumps({"fingerprint": fingerprint, "last_change_ts": last_change_ts}))

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
    if parsed["outcome"] is not None:
        return parsed
    return stray_parsed


def _deny_guard_path() -> Path:
    """Path to the deny-guard hook script (blocks git push / gh pr / secrets in T3 sessions)."""
    return get_hermes_home() / "scripts" / "deny-guard.sh"


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
        }

    capture = _run(["tmux", "capture-pane", "-t", task_id, "-p", "-S", f"-{tail}"])
    pane = capture.stdout if capture.returncode == 0 else ""
    lines = [line for line in pane.splitlines() if line.strip()]
    waiting_for_input = bool(lines) and "❯" in lines[-1]
    done = (status_file or "").strip().lower() == "complete"

    # Claude Code / Codex show a live activity indicator in the pane while a turn
    # is running (a spinner word + "esc to interrupt", elapsed timer, or a token
    # counter). If that's present, the session is WORKING — a high-effort turn can
    # legitimately think for minutes without writing status.md, so file-change
    # staleness alone must NOT flag it stalled (that would Esc a thinking session).
    tail_text = "\n".join(lines[-6:]) if lines else ""
    actively_working = bool(
        re.search(r"esc to interrupt|Thinking…|Working…|↑ \d|tokens|\(\d+m?s? ", tail_text)
    )

    now = time.time()
    last_change_ts = _record_activity(task_id, status_file, now)
    seconds_since_change = now - last_change_ts
    stalled = (
        not done
        and not waiting_for_input
        and not actively_working
        and seconds_since_change >= stall_seconds
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
        timeout = int(args.get("timeout") or 600)
    except (TypeError, ValueError):
        timeout = 600
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
    while True:
        state = _session_state(task_id, tail, stall_seconds)
        if state["state"] in {"needs_input", "stalled", "done", "exited"}:
            return {"ok": True, "timed_out": False, **state}
        if time.monotonic() >= deadline:
            return {"ok": True, "timed_out": True, **state}
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
        task_ids = [p.name for p in _tasks_root().iterdir() if p.is_dir()]
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
    if not real_paths:
        return {"result": "fail", "evidence": "status=complete but git shows zero real changes in rundir (orchestration files excluded)"}

    return {"result": "pass", "evidence": f"status=complete; {_short_diffstat(diffstat, cached_diffstat, porcelain)}"}


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


def _gate(args: dict) -> dict:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"ok": False, "error": "task_id is required"}

    impl = _check_impl_complete(task_id)
    review = _coerce_verdict(args.get("review"), "not implemented (Tier-2)")
    tests = _coerce_verdict(args.get("tests"), "not implemented (Tier-2)")
    passed = all(c["result"] == "pass" for c in (impl, review, tests) if c["result"] != "skipped")

    return {
        "ok": True,
        "task_id": task_id,
        "impl": impl,
        "review": review,
        "tests": tests,
        "passed": passed,
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
    "clean": _clean,
    "check_diff": _check_diff,
}


def _handle(args: dict, **kw) -> str:
    try:
        action = str(args.get("action") or "").strip().lower()
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
        "change for stall_seconds), block until it needs input, stalls, or exits (wait), steer it with follow-up "
        "input, fetch its result, or stop it. "
        "gate runs the exit-gate verdict (impl-complete check plus caller-supplied review/tests verdicts, "
        "defaulting to skipped stubs if omitted). "
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
                    "recover", "gate", "clean", "check_diff", "interrupt", "diagnose",
                ],
            },
            "task_id": {"type": "string", "description": "tmux session name / artifact dir name"},
            "prompt": {"type": "string", "description": "Initial task for Claude (start)"},
            "workdir": {"type": "string", "description": "Absolute dir Claude runs in (start)"},
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
                "enum": ["truefoundry", "fireworks"],
                "description": (
                    "Backend routing for the claude executor (start). "
                    "truefoundry (default) = Claude models via the TF gateway; "
                    "fireworks = Kimi K3 via Fireworks' Anthropic-compatible endpoint "
                    "(isolated CLAUDE_CONFIG_DIR, ignores --model). Codex executor ignores this."
                ),
            },
            "effort": {
                "type": "string",
                "enum": ["low", "medium", "high", "max", "auto"],
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
