#!/usr/bin/env bash
# Keep-hot: hourly AWS creds refresh. Both devflows and eswlegal mint via
# saml2aws/KeyCloak (self-healing, password-only) since 2026-10-27 - the
# KeyCloak assertion carries both roles, so no OneLogin id_token window
# exists anymore. Alert Telegram only when the refresh actually fails.
set -u
LOG="/tmp/aws-creds-refresh.log"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

if out=$(bash ~/.hermes/scripts/aws-creds-refresh-linux.sh 2>/dev/null); then
  log "keep-hot: refreshed (devflows + eswlegal via saml2aws)"
  exit 0
fi
MSG="sora: AWS creds refresh FAILED (devflows/eswlegal saml2aws login broken). Check /tmp/aws-creds-refresh.log on the box"
curl -s -X POST "https://api.telegram.org/bot$(grep ^TELEGRAM_BOT_TOKEN ~/.hermes/.env | cut -d= -f2)/sendMessage" \
  -d chat_id=<chat-id> --data-urlencode "text=$MSG" >/dev/null 2>&1 || true
log "keep-hot: refresh FAILED - alert sent"
exit 1
