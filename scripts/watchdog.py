#!/usr/bin/env python3
"""watchdog — make a dead watcher look different from a quiet one.

Every watcher here is silent when there's nothing to report, so one that has
stopped running looks identical to one with good news. This closes that gap.

Must run from the system scheduler — launchd or systemd — and NOT `hermes cron`:
crons only fire while the gateway is up, so a cron-based watchdog would die
alongside what it is watching.

Checks:
  1. Gateway is running (if it isn't, every cron below is silently dead).
  2. Every expected cron job still exists and is recurring, not one-shot.
  3. Each job ran recently — `Last run` within 3x its own interval — so a
     scheduler that quietly stopped firing is caught.
  4. Each job's last run status is `ok`, not an error.
  5. Every messaging adapter the gateway reports is connected, so a live
     gateway with a dead Telegram cannot pass as healthy.
  6. The auto-update job is registered and last exited 0.

The scheduler does not fire while the machine is asleep, so on a laptop check 3
measures the gap against time spent AWAKE: a Mac that slept four hours is not a
stopped scheduler, and alerting on it teaches you to ignore the channel. A
server never sleeps, so nothing is ever explained away there — see
_platform.last_wake.

Alerts go to Telegram, plus a desktop banner on machines that have a screen so
neither channel is load-bearing.

Config: $HERMES_HOME/scripts/watchdog.json
    {"expect": ["orphan-reaper", "hermes-hygiene", "ci-main-content", "tier-events",
                "upstream-drift", "cost-guard", "dead-supervisors"],
     "channel": "telegram", "notify": true}

`channel` is any target `hermes send -t` accepts. It exists because the machine
whose Telegram is switched off still has to be able to shout.

Schedule (launchd, every 30 min) — see config/ai.hermes.watchdog.plist.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _platform  # type: ignore

HERMES_HOME = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
CONFIG = HERMES_HOME / "scripts" / "watchdog.json"
PLATFORM_STATE = HERMES_HOME / "gateway_state.json"

# How many missed intervals before a job counts as stale.
STALE_FACTOR = 3
# Floor so a fast job (every 2m) isn't flagged by a few seconds of scheduler jitter.
STALE_FLOOR = timedelta(minutes=15)

BLOCK_RE = re.compile(r"^\s{2}(\w{8,})\s+\[(\w+)\]\s*$")
FIELD_RE = re.compile(r"^\s{4}([\w ]+):\s+(.*?)\s*$")


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def parse_cron_list(text: str) -> list[dict]:
    """Parse `hermes cron list` blocks. No --json on this version."""
    jobs: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = BLOCK_RE.match(line)
        if m:
            if cur:
                jobs.append(cur)
            cur = {"id": m.group(1), "state": m.group(2)}
            continue
        if cur is None:
            continue
        f = FIELD_RE.match(line)
        if f:
            cur[f.group(1).strip().lower().replace(" ", "_")] = f.group(2)
    if cur:
        jobs.append(cur)
    return jobs


def interval_minutes(schedule: str) -> int | None:
    m = re.search(r"every\s+(\d+)m", schedule or "")
    return int(m.group(1)) if m else None


def parse_dt(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.strip())
    except Exception:
        return None


def check_jobs(problems: list[str], expect: list[str], woke: datetime | None,
               suppressed: list[str]) -> None:
    r = run(["hermes", "cron", "list"])
    if r.returncode != 0:
        problems.append(f"`hermes cron list` failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[:200]}")
        return

    jobs = parse_cron_list(r.stdout)
    by_name = {j.get("name"): j for j in jobs if j.get("name")}

    for name in expect:
        if name not in by_name:
            problems.append(f"cron `{name}` is MISSING — it was expected but is not scheduled")
            continue

        j = by_name[name]
        if j.get("state") != "active":
            problems.append(f"cron `{name}` is not active (state={j.get('state')})")

        if j.get("repeat") not in ("∞", "inf", None):
            problems.append(
                f"cron `{name}` is one-shot (Repeat: {j.get('repeat')}) — it will not fire again"
            )

        now = datetime.now().astimezone()
        last_raw = j.get("last_run", "")
        # "Last run:  <iso>  ok"  → split off the trailing status word.
        parts = last_raw.rsplit("  ", 1) if last_raw else []
        last_dt = parse_dt(parts[0]) if parts else None
        status = parts[1].strip() if len(parts) > 1 else ""

        if not last_raw:
            nxt = parse_dt(j.get("next_run", ""))
            if nxt and nxt < now:
                problems.append(f"cron `{name}` has NEVER run and its next run ({nxt}) is in the past")
            continue

        if status and status != "ok":
            problems.append(f"cron `{name}` last run status is `{status}` (at {parts[0]})")

        mins = interval_minutes(j.get("schedule", ""))
        if last_dt and mins:
            limit = max(timedelta(minutes=mins * STALE_FACTOR), STALE_FLOOR)
            age = now - last_dt
            if age > limit:
                # Sleep stops the scheduler, so the gap only indicts it once the
                # machine has been awake longer than the job's own window and the
                # job still hasn't fired. Waking 3 minutes ago after a four-hour
                # sleep explains the whole gap; being awake all day does not.
                awake = now - woke if woke else None
                mins_ago = int(age.total_seconds() // 60)
                if awake is not None and awake <= limit:
                    suppressed.append(
                        f"{name} last ran {mins_ago}m ago, but the machine woke "
                        f"{int(awake.total_seconds() // 60)}m ago — sleep, not a stopped scheduler"
                    )
                else:
                    problems.append(
                        f"cron `{name}` is STALE — last ran {mins_ago}m ago "
                        f"but runs every {mins}m (scheduler may have stopped)"
                    )


def check_gateway(problems: list[str]) -> None:
    r = run(["hermes", "status"])
    if r.returncode != 0:
        problems.append(f"`hermes status` failed (exit {r.returncode}) — gateway may be down")
        return
    # Scope to the Gateway Service block: "running" elsewhere in the report
    # would mask a dead gateway.
    lines = r.stdout.splitlines()
    status_line = None
    for i, line in enumerate(lines):
        if "Gateway Service" in line:
            for follow in lines[i + 1: i + 6]:
                if "Status:" in follow:
                    status_line = follow
                    break
            break

    if status_line is None:
        problems.append("could not find the Gateway Service status block in `hermes status` output")
    elif "running" not in status_line.lower():
        problems.append(f"Hermes gateway is NOT running ({status_line.strip()}) — every cron watcher is silently dead")


# What the gateway writes into gateway_state.json for each messaging adapter.
# `connecting` and `retrying` are the adapter working through a blip; the rest
# mean it has given up or is down.
HEALTHY_PLATFORM_STATES = {"connected"}
TRANSIENT_PLATFORM_STATES = {"connecting", "retrying"}
# How long an adapter may sit in a transient state before that IS the problem.
# Telegram's own conflict handling gives up after ~200s, so anything still
# retrying well past that is stuck rather than recovering.
TRANSIENT_GRACE = timedelta(minutes=15)


def check_platforms(problems: list[str], ignore: list[str] | None = None) -> None:
    """Catch a running gateway whose messaging adapter is dead.

    This exists because that combination is invisible from outside: on
    2026-08-24 the Telegram adapter went `fatal` after a token conflict and
    stayed disconnected for four and a half hours while the gateway process ran
    normally, `needs_attention` was false, and every other check here passed.
    The channel you would be told on was the channel that was down.
    """
    if not PLATFORM_STATE.exists():
        problems.append(
            f"no {PLATFORM_STATE.name} — the gateway has not reported platform health"
        )
        return
    try:
        state = json.loads(PLATFORM_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        problems.append(f"could not read {PLATFORM_STATE.name}: {e}")
        return

    platforms = state.get("platforms") or {}
    if not platforms:
        # A gateway with no adapters is a legitimate configuration (nothing
        # enabled), so this is not a fault on its own.
        return

    skip = set(ignore or [])
    now = datetime.now().astimezone()
    for name, info in sorted(platforms.items()):
        if name in skip:
            continue
        if not isinstance(info, dict):
            continue
        st = (info.get("state") or "unknown").lower()
        if st in HEALTHY_PLATFORM_STATES:
            continue

        detail = (info.get("error_message") or info.get("error_code") or "").strip()
        # Long enough to keep the diagnosis. Telegram's conflict error puts the
        # cause — another process holding the same bot token — at the very end,
        # and a cut that drops it leaves an alert you cannot act on.
        detail = f" — {detail[:240]}" if detail else ""

        if st in TRANSIENT_PLATFORM_STATES:
            since = parse_dt(info.get("updated_at") or "")
            if since is None or now - since <= TRANSIENT_GRACE:
                continue
            mins = int((now - since).total_seconds() // 60)
            problems.append(
                f"platform `{name}` has been {st} for {mins}m — it is stuck, not recovering{detail}"
            )
        else:
            problems.append(f"platform `{name}` is {st.upper()}{detail}")


def check_autoupdate(problems: list[str]) -> None:
    problem = _platform.autoupdate_problem()
    if problem:
        problems.append(problem)


def check_script_drift(problems: list[str], repo: str | None, exclude: list[str] | None = None) -> None:
    """Report installed scripts that no longer match the repo they came from.

    Only flags scripts that ARE installed but stale — a repo script that isn't
    installed at all is not drift, it might be a helper/hook/non-cron script.
    """
    if not repo:
        return
    source = Path(repo).expanduser() / "scripts"
    if not source.is_dir():
        problems.append(f"script drift unchecked: no scripts dir at {source}")
        return

    skip = set(exclude or [])
    installed_dir = HERMES_HOME / "scripts"
    stale = []
    for src in sorted(source.glob("*.py")) + sorted(source.glob("*.sh")):
        if src.name in skip:
            continue
        installed = installed_dir / src.name
        if installed.exists() and installed.read_bytes() != src.read_bytes():
            stale.append(src.name)

    if stale:
        problems.append(
            f"{len(stale)} installed script(s) differ from {source}: {', '.join(stale)}"
            " — resync with: cp <repo>/scripts/<file> ~/.hermes/scripts/"
        )


def alert(problems: list[str], channel: str | None, use_notify: bool) -> None:
    body = "**Hermes watchdog: {} problem(s)**\n\n".format(len(problems)) + "\n".join(
        f"- {p}" for p in problems
    )
    sys.stdout.write(body + "\n")

    if channel:
        r = run(["hermes", "send", "-t", channel, body])
        if r.returncode != 0:
            print(
                f"watchdog: ALERT TO {channel.upper()} FAILED (exit {r.returncode}): "
                f"{(r.stdout or r.stderr).strip()[:200]}",
                file=sys.stderr,
            )
    # The banner is a genuine second channel only where there is a screen. On a
    # server `notify` falls back to Telegram, which is where the block above
    # already posted, so honouring `notify` there would just double every alert.
    if use_notify and _platform.HAS_DESKTOP:
        summary = problems[0][:180] + ("" if len(problems) == 1 else f" (+{len(problems)-1} more)")
        _platform.notify("Hermes watchdog", summary, sound="Basso")


def main() -> int:
    cfg: dict = {}
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"watchdog: bad config {CONFIG}: {e}", file=sys.stderr)
            return 2

    expect = cfg.get("expect") or []
    problems: list[str] = []
    suppressed: list[str] = []
    stamp = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")

    check_gateway(problems)
    check_platforms(problems, ignore=cfg.get("ignore_platforms"))
    if cfg.get("check_autoupdate", False):
        check_autoupdate(problems)
    check_script_drift(problems, cfg.get("repo", str(Path.home() / "hermes-tier-setup")), exclude=cfg.get("drift_exclude"))
    if expect:
        check_jobs(problems, expect, _platform.last_wake(), suppressed)
    else:
        problems.append("watchdog has no `expect` list configured — it is checking nothing")

    # Printed rather than dropped: a suppressed alert is still a fact about the
    # run, and a log that only ever says "ok" hides how often this fires.
    for s in suppressed:
        print(f"{stamp} watchdog: stale-but-explained — {s}")

    if problems:
        # `channel` names the platform to alert on; the older boolean `telegram`
        # key still works so an un-migrated config keeps alerting rather than
        # falling silent. Explicit `telegram: false` with no channel means the
        # operator wants stdout only.
        channel = cfg.get("channel")
        if channel is None:
            channel = "telegram" if cfg.get("telegram", True) else None
        alert(problems, channel, bool(cfg.get("notify", True)))
        return 1

    print(f"{stamp} watchdog: ok — gateway up, {len(expect)} cron job(s) healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
