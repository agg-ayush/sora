#!/usr/bin/env python3
"""watch_ci_main — watch a repo's default-branch CI for failures, notify on new failures.

Polls the GitHub check-runs API for the default branch's latest commit and
emits a notification when a check-run transitions to `completed` with a
`failure` or `action_required` conclusion. Watermark-deduped — each failing
check-run is notified once.

Usage (via cron with --no-agent):

    hermes cron create ci-main-content \
      --schedule "*/5 * * * *" --no-agent \
      --script "$HERMES_HOME/scripts/watch_ci_main.py" \
      --script-args "--name content-ci --repo NousResearch/alpha-learn-content-gen"

Set GITHUB_TOKEN (or GH_TOKEN) in the Hermes .env file
(``${HERMES_HOME:-~/.hermes}/.env``) to avoid the 60 req/hr
anonymous rate limit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _watermark import Watermark, format_items_as_markdown  # type: ignore


def _get(url: str, token: str, timeout: float) -> dict | list:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "Hermes-CI-Watcher/1.0")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Watch a repo's default-branch CI for failures.")
    p.add_argument("--name", default="", help="Watcher name (used for state file)")
    p.add_argument("--repo", default="", help="owner/name of the repo")
    p.add_argument("--branch", default="main", help="The default branch to watch (default: main)")
    p.add_argument("--config", default="", help="A JSON config file with {name, repo, branch} (for cron use)")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout (default: 30)")
    args = p.parse_args()

    # Config file wins over CLI args (for cron use — the cron runs the script bare).
    # The script reads its config from ~/.hermes/scripts/watch_ci_main.json by default
    # (a single {name, repo, branch} JSON object) when no --config is given.
    config_path = args.config or os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch_ci_main.json")
    if os.path.exists(config_path):
        try:
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
            args.name = args.name or cfg.get("name", "")
            args.repo = args.repo or cfg.get("repo", "")
            args.branch = cfg.get("branch", args.branch)
        except Exception as e:
            print(f"watch_ci_main: failed to read config {config_path}: {e}", file=sys.stderr)
            return 2

    if not args.name:
        print("watch_ci_main: --name (or config with name) is required", file=sys.stderr)
        return 2
    if not args.repo:
        print("watch_ci_main: --repo (or config with repo) is required", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", args.repo):
        print(f"watch_ci_main: --repo must be owner/name (got {args.repo!r})", file=sys.stderr)
        return 2

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    # If the env doesn't have the token (the cron runs the script bare), read it
    # from the Hermes .env file directly.
    if not token:
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            for line in open(env_file):
                line = line.strip()
                if line.startswith("GITHUB_TOKEN=") or line.startswith("GH_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    # 1. Get the latest commit on the default branch.
    try:
        branch = _get(
            f"https://api.github.com/repos/{args.repo}/branches/{urllib.parse.quote(args.branch, safe='')}",
            token, args.timeout,
        )
    except Exception as e:
        print(f"watch_ci_main: failed to fetch branch {args.branch}: {e}", file=sys.stderr)
        return 2
    sha = (branch.get("commit") or {}).get("sha")
    if not sha:
        print(f"watch_ci_main: no commit sha on branch {args.branch}", file=sys.stderr)
        return 2

    # 2. Get the check-runs for that commit.
    try:
        checks_raw = _get(
            f"https://api.github.com/repos/{args.repo}/commits/{sha}/check-runs?per_page=100",
            token, args.timeout,
        )
    except Exception as e:
        print(f"watch_ci_main: failed to fetch check-runs for {sha[:8]}: {e}", file=sys.stderr)
        return 2

    checks: dict = checks_raw if isinstance(checks_raw, dict) else {}
    runs = checks.get("check_runs", [])
    # A check-run is a failure if it's completed with a failure/action_required conclusion.
    failing = [
        {
            "id": str(r.get("id", "")),
            "title": f"{r.get('name','?')} — {r.get('conclusion','?')} on {args.branch}@{sha[:8]}",
            "url": r.get("html_url") or r.get("details_url"),
            "body": ((r.get("output") or {}).get("summary") or "")[:500],
            "created_at": r.get("completed_at") or r.get("started_at"),
        }
        for r in runs
        if r.get("status") == "completed" and r.get("conclusion") in ("failure", "action_required", "timed_out")
    ]

    if not failing:
        return 0  # silent — no failures

    wm = Watermark.load(args.name)
    new = wm.filter_new(failing, id_key="id")
    wm.save()

    if new:
        out = format_items_as_markdown(new, body_key="body")
        if out:
            sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
