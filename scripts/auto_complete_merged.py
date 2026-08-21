#!/usr/bin/env python3
"""auto_complete_merged — poll review-state kanban tasks and auto-complete merged PRs.

Runs as a cron job (every 5 min). For each board, finds tasks in 'review' state,
checks the linked PR's merge state on GitHub, and auto-completes the task if merged.

This removes the T1/T2 having to remember to close the task after merge — the
board stays clean without manual intervention.
"""

import json
import os
import re
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
BOARDS_DIR = f"{HOME}/.hermes/kanban/boards"


def sh(*args, timeout=30):
    r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def get_boards():
    """Return list of board slugs from the boards directory."""
    if not os.path.isdir(BOARDS_DIR):
        return []
    return [d for d in os.listdir(BOARDS_DIR) if os.path.isdir(os.path.join(BOARDS_DIR, d))]


def get_review_tasks(board):
    """Return review-state tasks on a board."""
    rc, out, _ = sh("hermes", "kanban", "--board", board, "list", "--status", "review", "--json")
    if rc != 0:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def get_pr_state(repo, pr_number):
    """Return the PR's state and merge status."""
    rc, out, _ = sh("gh", "pr", "view", str(pr_number), "--repo", repo, "--json", "state,mergedAt,mergeCommit")
    if rc != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def extract_pr_number(task):
    """Extract the PR number from a task's result or title."""
    for field in (task.get("result") or "", task.get("title") or ""):
        m = re.search(r"#(\d+)", field)
        if m:
            return int(m.group(1))
    return None


def main():
    boards = get_boards()
    if not boards:
        print("no boards found", file=sys.stderr)
        return

    completed = 0
    for board in boards:
        tasks = get_review_tasks(board)
        for task in tasks:
            task_id = task.get("id")
            if not task_id:
                continue

            # Find the PR number
            pr_num = extract_pr_number(task)
            if not pr_num:
                continue

            # Get the repo from the task's workdir
            workdir = task.get("workdir") or ""
            if not workdir:
                continue
            # Extract org/repo from the workdir path (e.g. ~/Trilogy/app -> Trilogy/app)
            parts = workdir.rstrip("/").split("/")
            if len(parts) >= 2:
                repo = f"{parts[-2]}/{parts[-1]}"
            else:
                continue

            # Check PR state
            pr = get_pr_state(repo, pr_num)
            if not pr:
                continue

            if pr.get("state") == "MERGED":
                # Auto-complete the task
                merge_sha = (pr.get("mergeCommit") or {}).get("oid", "")[:8]
                rc, out, err = sh(
                    "hermes", "kanban", "--board", board, "complete", task_id,
                    "--result", f"merged via PR #{pr_num} ({merge_sha})"
                )
                if rc == 0:
                    print(f"auto-completed {task_id} on {board}: PR #{pr_num} merged ({merge_sha})")
                    completed += 1
                else:
                    print(f"failed to complete {task_id}: {err}", file=sys.stderr)

    if completed:
        print(f"auto-completed {completed} task(s)")


if __name__ == "__main__":
    main()
