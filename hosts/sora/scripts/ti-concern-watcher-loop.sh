#!/usr/bin/env bash
# Persistent watcher loop: runs the concern-watcher tick every 60s, forever.
# Alerts are sent by the tick script into the Telegram group chat; replies to
# that chat land in the live gateway session where they can be answered.
while true; do
  /usr/bin/python3 "$HOME/.hermes/scripts/ti-concern-watcher.py" >> "$HOME/.hermes/logs/ti-concern-watcher.log" 2>&1
  sleep 60
done
