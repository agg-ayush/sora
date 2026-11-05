#!/usr/bin/env python3
"""Run the auth canary locally and send only alerts through the remote host."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _alert_relay import send_alert

CHANNEL = "ssh:devbox:telegram"


def main() -> int:
    canary = Path(__file__).with_name("auth-canary.py")
    result = subprocess.run([sys.executable, str(canary)], capture_output=True, text=True, timeout=120)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.stdout:
        delivered = send_alert(CHANNEL, result.stdout)
        if delivered.returncode:
            print(
                f"auth-canary-relay: ALERT TO {CHANNEL.upper()} FAILED (exit {delivered.returncode}): "
                f"{(delivered.stderr or delivered.stdout).strip()[:200]}",
                file=sys.stderr,
            )
        else:
            print(f"auth-canary-relay: sent via {CHANNEL}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
