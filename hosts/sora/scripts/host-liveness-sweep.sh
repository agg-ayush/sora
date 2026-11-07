#!/usr/bin/env bash
# Host-level liveness sweep - independent of kanban/tier watchdog.
# Checks: gateway up, dashboard up, disk headroom, mem+swap pressure,
# zombie processes (cwd deleted / orphaned claude+node), per 30min cron tick.
set -u
PROBLEMS=""
GW=$(systemctl --user is-active hermes-gateway.service 2>/dev/null)
[ "$GW" = "active" ] || PROBLEMS="$PROBLEMS gateway:$GW"
DB=$(systemctl --user is-active hermes-dashboard.service 2>/dev/null)
[ "$DB" = "active" ] || PROBLEMS="$PROBLEMS dashboard:$DB"
DISK=$(df --output=pcent / | tail -1 | tr -dc "0-9")
[ "$DISK" -lt 90 ] || PROBLEMS="$PROBLEMS disk:${DISK}%"
MEMA=$(free -m | awk "/^Mem:/{print \$NF}")
[ "$MEMA" -gt 500 ] || PROBABLY=""; [ "$MEMA" -gt 500 ] || PROBLEMS="$PROBLEMS mem_avail:${MEMA}m"
ZOMBIES=$(for p in $(pgrep -f "claude |node --expose|tui_gateway" 2>/dev/null); do [ -e "/proc/$p/cwd" ] && [ ! -e "$(readlink /proc/$p/cwd 2>/dev/null)" ] && echo $p; done | wc -l)
[ "$ZOMBIES" -eq 0 ] || PROBLEMS="$PROBLEMS zombies:$ZOMBIES"
if [ -n "$PROBLEMS" ]; then
  # Chat id = the Telegram home channel from ~/.hermes/.env (never hardcoded in the repo).
  curl -s -X POST "https://api.telegram.org/bot$(grep ^TELEGRAM_BOT_TOKEN= ~/.hermes/.env | cut -d= -f2)/sendMessage" \
    -d chat_id="$(grep ^TELEGRAM_HOME_CHANNEL= ~/.hermes/.env | cut -d= -f2)" --data-urlencode "text=⚠️ sora liveness: $PROBLEMS" >/dev/null 2>&1 || true
  echo "$(date -u +%FT%TZ) PROBLEMS:$PROBLEMS" >> ~/.hermes/logs/liveness-sweep.log
else
  echo "$(date -u +%FT%TZ) ok" >> ~/.hermes/logs/liveness-sweep.log
fi
