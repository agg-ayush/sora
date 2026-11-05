"""Send local alerts directly or through a remote Hermes host."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path


def hermes_executable() -> str:
    launcher = Path.home() / ".local" / "bin" / "hermes"
    if launcher.is_file():
        return str(launcher)
    return shutil.which("hermes") or "hermes"


def relay_destination(channel: str) -> tuple[str, str] | None:
    if not channel.startswith("ssh:"):
        return None
    parts = channel.split(":", 2)
    if len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]*", parts[1]) or not parts[2]:
        raise ValueError(f"invalid SSH alert channel: {channel}")
    return parts[1], parts[2]


def send_alert(channel: str, body: str) -> subprocess.CompletedProcess:
    destination = relay_destination(channel)
    if destination is None:
        cmd = [hermes_executable(), "send", "-t", channel, body]
    else:
        host, target = destination
        remote = '"$HOME/.local/bin/hermes" send -t {} {}'.format(
            shlex.quote(target), shlex.quote(body)
        )
        cmd = ["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", host, remote]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
