#!/usr/bin/env python3
"""Host-profile helpers for devbox/host-profile.sh (cron jobs + config overrides).

Install-if-absent only: existing jobs and existing configs are never touched.

  host_profile.py cron <hosts/<profile>/cron-jobs.json> [--mac]
  host_profile.py overrides <config.yaml> <config-overrides.yaml> [--mac]
  host_profile.py watchdog <hosts/<profile>/watchdog.json> <dest> <repo dir>
  host_profile.py watchdog-check <installed watchdog.json>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERMES = os.environ.get("HERMES_BIN") or str(Path.home() / ".local" / "bin" / "hermes")


def log(msg: str) -> None:
    print(f"[host-profile] {msg}", flush=True)


def hermes_bin() -> str:
    from shutil import which

    return HERMES if os.path.exists(HERMES) else (which("hermes") or "hermes")


def existing_job_names(run=subprocess.run) -> set[str]:
    out = run([hermes_bin(), "cron", "list", "--all"], capture_output=True, text=True, timeout=120)
    return set(re.findall(r"^\s*Name:\s+(.+?)\s*$", out.stdout or "", re.M))


def _expand(text: str) -> str:
    return text.replace("$HOME", str(Path.home()))


def build_create_args(job: dict) -> list[str]:
    """Argument list for `hermes cron create` (everything after the binary)."""
    args = ["cron", "create", job["schedule"]]
    if job.get("prompt"):
        args.append(job["prompt"])
    args += ["--name", job["name"], "--deliver", job.get("deliver", "local")]
    if job.get("script"):
        args += ["--script", job["script"]]
    if job.get("no_agent"):
        args.append("--no-agent")
    for skill in job.get("skills") or []:
        args += ["--skill", skill]
    if job.get("workdir"):
        args += ["--workdir", _expand(job["workdir"])]
    if job.get("model"):
        args += ["--model", job["model"]]
    if job.get("provider"):
        args += ["--provider", job["provider"]]
    if job.get("enabled") is False:
        args += ["--paused", "--paused-reason", "recorded as paused in hosts profile"]
    return args


def install_cron_jobs(jobs_file: Path, is_mac: bool, run=subprocess.run) -> int:
    data = json.loads(jobs_file.read_text())
    existing = existing_job_names(run)
    created = present = skipped = failed = 0
    for job in data["jobs"]:
        name = job["name"]
        if name in existing:
            present += 1
            continue
        if is_mac and "telegram" in str(job.get("deliver", "")):
            log(f"SKIP cron {name}: Mac must not deliver to Telegram (standing rule)")
            skipped += 1
            continue
        script = job.get("script")
        if script and not (Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "scripts" / script).is_file():
            log(f"WARNING: cron {name}: script {script} missing from scripts/; creating anyway")
        if job.get("enabled_toolsets"):
            log(f"note: cron {name} recorded with enabled_toolsets={job['enabled_toolsets']}; "
                "`hermes cron create` has no flag for it, set it via the agent cronjob tool if needed")
        r = run([hermes_bin(), *build_create_args(job)], capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            log(f"created cron {name} ({'active' if job.get('enabled', True) else 'paused'})")
            created += 1
        else:
            log(f"WARNING: cron {name} creation failed: {(r.stderr or r.stdout or '').strip()[-200:]}")
            failed += 1
    log(f"cron jobs: {created} created, {present} already present, {skipped} skipped, {failed} failed")
    return 0


def deep_merge(base, over):
    """Dicts merge recursively; lists and scalars from `over` replace."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = dict(base)
        for k, v in over.items():
            out[k] = deep_merge(base[k], v) if k in base else v
        return out
    return over


def apply_overrides(config_path: Path, overrides_path: Path, is_mac: bool) -> int:
    import yaml

    over = yaml.safe_load(overrides_path.read_text()) or {}
    if is_mac and "telegram" in (over.get("platforms") or {}):
        log("REFUSING config override: Mac must not configure the Telegram platform (standing rule)")
        return 1
    cfg = yaml.safe_load(config_path.read_text()) or {}
    merged = deep_merge(cfg, over)
    header = (f"# config.yaml created from config/config.yaml.template + {overrides_path.parent.name}/config-overrides.yaml\n"
              "# (setup-hermes.sh; comments of the template are not preserved).\n")
    config_path.write_text(header + yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
    log(f"applied {overrides_path.parent.name}/config-overrides.yaml keys: {', '.join(over)}")
    return 0


def install_watchdog(src: Path, dest: Path, repo_dir: str) -> int:
    """Copy watchdog.json with __REPO_DIR__ replaced by repo_dir, JSON-escaped; other bytes unchanged."""
    escaped = json.dumps(repo_dir)[1:-1].encode()
    dest.write_bytes(src.read_bytes().replace(b"__REPO_DIR__", escaped))
    return 0


def watchdog_alert_channel(cfg: dict) -> str | None:
    """The channel scripts/watchdog.py alerts on: `channel`, else the legacy `telegram` boolean (default on)."""
    channel = cfg.get("channel")
    if channel is None:
        channel = "telegram" if cfg.get("telegram", True) else None
    return channel or None


def check_watchdog(path: Path) -> int:
    """Warn when a watchdog.json would alert over Telegram from a host that should stay local."""
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"WARNING: could not read {path}: {e}")
        return 0
    channel = watchdog_alert_channel(cfg) if isinstance(cfg, dict) else None
    if channel and "telegram" in channel:
        log(f"WARNING: {path} alerts via Telegram (channel {channel}); this host's profile keeps alerts local.")
        log(f'  To stop it, set "telegram": false and remove "channel" in {path},')
        log("  or delete the file and re-run devbox/setup-hermes.sh to install the profile default.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    is_mac = "--mac" in argv
    pos = [a for a in argv[1:] if not a.startswith("--")]
    if pos[0] == "cron":
        return install_cron_jobs(Path(pos[1]), is_mac)
    if pos[0] == "overrides":
        return apply_overrides(Path(pos[1]), Path(pos[2]), is_mac)
    if pos[0] == "watchdog":
        return install_watchdog(Path(pos[1]), Path(pos[2]), pos[3])
    if pos[0] == "watchdog-check":
        return check_watchdog(Path(pos[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
