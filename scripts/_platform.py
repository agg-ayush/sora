"""Host differences the watcher scripts would otherwise each have to know about.

The same scripts run on the laptop and on the server, and three things differ:
how an alert reaches a human, whether the machine can have been asleep, and
which service manager runs the auto-update job. Everything else is portable.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime

IS_MAC = sys.platform == "darwin"

# Whether a human is ever looking at this machine's screen. Drives whether a
# desktop banner is a real second channel or a no-op worth skipping.
HAS_DESKTOP = IS_MAC

AUTOUPDATE_UNIT = "hermes-autoupdate"
AUTOUPDATE_LAUNCHD_LABEL = "ai.hermes.autoupdate"


def _run(cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def last_wake() -> datetime | None:
    """When the machine last woke, or None if that can't be established.

    None means "do not suppress anything". On a server that is the permanent
    answer: it never sleeps, so a scheduler gap is always a real fault and
    explaining one away would silence the very failure this check exists to
    catch.

    On macOS, `kern.waketime` reports full wakes only — not the DarkWakes used
    for maintenance, which is the distinction that matters: the Hermes
    scheduler fires during neither, so a night of DarkWakes still leaves a real
    gap.
    """
    if not IS_MAC:
        return None
    try:
        r = _run(["sysctl", "-n", "kern.waketime"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    m = re.search(r"sec\s*=\s*(\d+)", r.stdout)
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1))).astimezone()
    except (ValueError, OSError):
        return None


def notify(title: str, body: str, sound: str | None = None) -> bool:
    """Push a short alert at whoever owns this machine. Never raises.

    On the laptop that is a desktop banner. On the server there is no screen,
    so it goes to Telegram instead — which means a caller that ALSO sends to
    Telegram should check HAS_DESKTOP first rather than posting twice.

    Returns False on failure, having written the reason to stderr: callers
    treat stdout as the channel of record and must not depend on this landing.
    """
    if IS_MAC:
        esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
        clause = f' sound name "{esc(sound)}"' if sound else ""
        script = f'display notification "{esc(body)[:220]}" with title "{esc(title)}"{clause}'
        cmd = ["osascript", "-e", script]
    else:
        cmd = ["hermes", "send", "-t", "telegram", f"**{title}**\n\n{body}"]

    try:
        r = _run(cmd, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"notify: failed to run {cmd[0]}: {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        detail = (r.stderr or r.stdout or "").strip()[:200]
        print(f"notify: {cmd[0]} failed ({r.returncode}): {detail}", file=sys.stderr)
        return False
    return True


def autoupdate_problem() -> str | None:
    """Describe what's wrong with the auto-update job, or None if it's healthy.

    Checks that the job is still registered with the service manager and that
    its last run exited cleanly. A silently unregistered updater is the failure
    that matters: Hermes keeps working while falling further behind.
    """
    if IS_MAC:
        r = _run(["launchctl", "list", AUTOUPDATE_LAUNCHD_LABEL])
        if r.returncode != 0:
            return (
                f"launchd job `{AUTOUPDATE_LAUNCHD_LABEL}` is not loaded "
                "— Hermes will not auto-update"
            )
        m = re.search(r'"LastExitStatus"\s*=\s*(-?\d+)', r.stdout)
        if m and int(m.group(1)) != 0:
            return f"auto-update last exited {m.group(1)} — check ~/.hermes/logs/auto-update.log"
        return None

    timer = f"{AUTOUPDATE_UNIT}.timer"
    r = _run(["systemctl", "--user", "is-active", timer])
    if r.stdout.strip() != "active":
        return (
            f"systemd timer `{timer}` is {r.stdout.strip() or 'missing'} "
            "— Hermes will not auto-update"
        )
    r = _run(["systemctl", "--user", "show", f"{AUTOUPDATE_UNIT}.service",
              "-p", "ExecMainStatus", "--value"])
    code = (r.stdout or "").strip()
    if code.isdigit() and int(code) != 0:
        return f"auto-update last exited {code} — check ~/.hermes/logs/auto-update.log"
    return None
