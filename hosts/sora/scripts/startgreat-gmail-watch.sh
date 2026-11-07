#!/bin/bash
# Watchdog: probe startgreat gmail quota. Silent (no stdout) while throttled.
# When it clears, do the full pull and print a wake-up signal so the agent runs the bucketing.
export GOG_KEYRING_PASSWORD=$(cat "$HOME/.config/gogcli/.keyring-pw")
probe=$(gog --account <ops-mailbox> --client startgreat gmail search "in:inbox -from:me newer_than:3d" --max 5 --json 2>&1)
if echo "$probe" | grep -q rateLimitExceeded; then
  exit 0   # silent: no output, no wake
fi
# cleared — do the full pull and emit a signal
gog --account <ops-mailbox> --client startgreat gmail search "in:inbox -from:me newer_than:3d" --max 300 --json > /tmp/sg-threads.json 2>/tmp/sg-err.txt
echo "STARTGREAT-QUOTA-CLEARED — full thread list at /tmp/sg-threads.json ($(wc -c < /tmp/sg-threads.json) bytes). Run the VVA/not-VVA bucketing now."
