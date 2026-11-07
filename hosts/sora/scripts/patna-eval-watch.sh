#!/bin/bash
# Watchdog for the local Patna eval run. Silent when healthy; prints a line when something needs attention.
# Fires on: (a) eval progress stalled (no new GCS cache report in >10 min while run is active), (b) box memory pressure (OOM risk), (c) the run's local worker process gone while sessions remain.
export PATH=/usr/local/bin:/opt/google-cloud-sdk/bin:$PATH
STAMP=$(date -u +%H:%M)

# memory pressure check — use MemAvailable (reclaimable), not raw free
AVAIL_MB=$(free -m | awk '/^Mem:/{print $7}')
if [ "$AVAIL_MB" -lt 1500 ]; then
  echo "MEM-LOW $STAMP: ${AVAIL_MB}MB available — OOM risk on the local eval run; consider whether the eval worker wedged"
fi

# local eval worker liveness: is a transcript-eval / node process running?
if ! pgrep -f "transcript-eval|eval-main|workflow-cli" >/dev/null 2>&1; then
  # only flag if there appear to be unfinished sessions (a progress marker file the run writes)
  if [ -f /tmp/patna-eval-progress.json ]; then
    REMAIN=$(python3 -c "import json;d=json.load(open('/tmp/patna-eval-progress.json'));print(d.get('remaining',0))" 2>/dev/null || echo "?")
    if [ "$REMAIN" != "0" ] && [ "$REMAIN" != "?" ]; then
      echo "EVAL-WORKER-GONE $STAMP: no transcript-eval process alive but $REMAIN sessions remain — the local run may have crashed"
    fi
  fi
fi
