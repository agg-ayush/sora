#!/usr/bin/env python3
"""Claude Code Stop hook for T3 orchestrated sessions (~/.hermes/scripts/t3-stop-gate.py).

Runs once at the end of each Claude turn:
1. Writes a deterministic turn-stop receipt (`last_stop_at`) into `<artifact_dir>/activity.json`.
2. When inside a git repo, checks modified/untracked files:
   - Runs fast Rust linters on changed files only (`ruff check --select=E9,F63,F7,F82` for .py;
     `oxlint --deny-warnings=false` for .js/.jsx/.ts/.tsx) to catch syntax/undefined-name errors
     without per-edit latency.
   - If `<artifact_dir>/status.md` is marked `complete` and the session was launched in an
     implementation worktree (`meta.json` has `worktree` set), blocks completion (exit 2) if
     tracked files or untracked code files remain uncommitted in `git status --porcelain`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".sh", ".sql", ".css", ".html"}


def find_bin(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    local = Path.home() / ".local" / "bin" / name
    return str(local) if local.is_file() and os.access(local, os.X_OK) else None


def record_stop_receipt(artifact_dir: Path, payload: dict) -> None:
    if not artifact_dir.is_dir():
        return
    act_file = artifact_dir / "activity.json"
    try:
        data = json.loads(act_file.read_text("utf-8")) if act_file.exists() else {}
    except Exception:
        data = {}
    now = time.time()
    data["last_stop_at"] = now
    data["last_change_ts"] = now
    if payload.get("session_id"):
        data["claude_session_id"] = payload["session_id"]
    try:
        act_file.write_text(json.dumps(data), "utf-8")
    except Exception:
        pass


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # Avoid infinite Stop-hook loops if Claude is already responding to a prior Stop hook block.
    if payload.get("stop_hook_active"):
        return 0

    artifact_env = os.environ.get("HERMES_T3_ARTIFACT_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "")
    artifact_dir = Path(artifact_env) if artifact_env else None
    if artifact_dir:
        record_stop_receipt(artifact_dir, payload)

    cwd = payload.get("cwd") or os.getcwd()
    # Check if cwd is inside a git worktree
    git_check = subprocess.run(["git", "-C", cwd, "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True)
    if git_check.returncode != 0:
        return 0

    # Collect modified / untracked files in working tree and last commit if working tree is clean
    status_proc = subprocess.run(["git", "-C", cwd, "status", "--porcelain"],
                                 capture_output=True, text=True)
    porcelain_lines = [l for l in status_proc.stdout.splitlines() if l.strip()]

    dirty_files = []
    for line in porcelain_lines:
        path_part = line[3:].strip().split(" -> ")[-1].strip('"')
        full = Path(cwd) / path_part
        if full.is_file():
            dirty_files.append(str(full))

    # Also check files in HEAD commit if working tree was just committed
    lint_targets = list(dirty_files)
    if not lint_targets:
        diff_proc = subprocess.run(["git", "-C", cwd, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                                   capture_output=True, text=True)
        for rel in diff_proc.stdout.splitlines():
            full = Path(cwd) / rel.strip()
            if full.is_file():
                lint_targets.append(str(full))

    py_files = [f for f in lint_targets if f.endswith(".py")]
    js_files = [f for f in lint_targets if Path(f).suffix in {".js", ".jsx", ".ts", ".tsx"}]

    errors = []

    # 1. Fast Rust syntax/fatal-error lint on changed Python files (ruff E9/F63/F7/F82 = syntax & undefined names)
    if py_files:
        ruff = find_bin("ruff")
        if ruff:
            r = subprocess.run([ruff, "check", "--select=E9,F63,F7,F82", "--quiet", *py_files],
                               capture_output=True, text=True, timeout=10)
            if r.returncode != 0 and (r.stdout.strip() or r.stderr.strip()):
                errors.append("Python syntax/undefined-name errors (ruff):\n" + (r.stdout or r.stderr).strip()[:1200])

    # 2. Fast Rust syntax/correctness lint on changed JS/TS files (oxlint -D correctness, ~30ms)
    if js_files:
        oxlint = find_bin("oxlint")
        if oxlint:
            r = subprocess.run([oxlint, "--quiet", *js_files],
                               capture_output=True, text=True, timeout=10)
            if r.returncode != 0 and (r.stdout.strip() or r.stderr.strip()):
                errors.append("JS/TS correctness/syntax errors (oxlint):\n" + (r.stdout or r.stderr).strip()[:1200])

    # 3. Uncommitted-changes gate when status.md == complete in a worktree session
    if artifact_dir and (artifact_dir / "status.md").exists():
        status_txt = (artifact_dir / "status.md").read_text("utf-8").strip().lower()
        meta = {}
        if (artifact_dir / "meta.json").exists():
            try:
                meta = json.loads((artifact_dir / "meta.json").read_text("utf-8"))
            except Exception:
                pass
        if status_txt == "complete" and meta.get("worktree"):
            uncommitted_code = []
            for line in porcelain_lines:
                rel = line[3:].strip().split(" -> ")[-1].strip('"')
                # Ignore internal scratch/plan/serena/ui-flow/graphify artifacts
                if any(rel.startswith(p) for p in (".serena", ".ui-flow", ".graphify", "graphify-out", ".claude", "docs/superpowers")):
                    continue
                if not line.startswith("??") or Path(rel).suffix in CODE_EXTS:
                    uncommitted_code.append(line)
            if uncommitted_code:
                errors.append(
                    "status.md is set to 'complete', but the worktree still has uncommitted changes:\n  "
                    + "\n  ".join(uncommitted_code[:15])
                    + "\nCommit your changes on the worktree branch (or clean temporary files) before finishing."
                )

    if errors:
        sys.stderr.write("\n\n".join(errors) + "\n")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
