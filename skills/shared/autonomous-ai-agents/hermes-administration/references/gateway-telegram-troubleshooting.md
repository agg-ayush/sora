---
title: Diagnosing Telegram/gateway "fatal" and disconnect errors
---

# Gateway platform disconnects (Telegram polling conflict, fatal adapter errors)

## Symptom
TUI notification or watchdog shows a platform (e.g. Telegram) disconnected,
or the gateway log has a "Fatal telegram adapter error" /
`telegram_polling_conflict` entry.

## Step 1 — read the actual error, don't guess
```bash
tail -100 ~/.hermes/logs/gateway.log | grep -i "telegram\|fatal" | tail -10
```
Common root causes seen in this log:
- `Conflict: terminated by other getUpdates request; make sure that only
  one bot instance is running` — another process is long-polling with the
  same bot token. This is the most common cause and is NOT fixed by a
  plain `hermes gateway restart` alone if the old process is still alive.
- Missing bot token: check `TELEGRAM_BOT_TOKEN` is set
  (`hermes config set-env TELEGRAM_BOT_TOKEN "<token>"`) then restart.

## Step 2 — find the real duplicate
First check whether two HOSTS hold the same bot token (e.g. a Mac and a
remote box whose `.env` was copied): grep `TELEGRAM_BOT_TOKEN` in
`~/.hermes/.env` on each. If both have it, the duplicate poller is on the
host that should NOT own the bot, and it can be any Hermes process there,
including `tui_gateway.entry` children of interactive TUI sessions. Count
which processes actually carry the token:
```bash
for p in $(pgrep -f tui_gateway.entry); do
  ps eww -p $p | tr ' ' '\n' | grep -q '^TELEGRAM_BOT_TOKEN=' && echo "$p polls"
done
```
Fix order for a cross-host collision:
1. Back up and remove `TELEGRAM_BOT_TOKEN` from the non-owner host's
   `.env` (chmod 600 the backup). This is the root fix: every future
   launch there inherits the token from `.env`, so killing processes alone
   is whack-a-mole.
2. Kill the token-carrying processes that predate the scrub. Kill the
   parent node TUI wrapper, not just the python `tui_gateway.entry` child:
   the wrapper holds the token in its own env and respawns the child with
   it within seconds.
3. Before killing a wrapper, map it to its session: read
   `HERMES_TUI_ACTIVE_SESSION_FILE` from `ps eww -p <pid>`, cat that JSON
   for `session_id`, look up title and last activity in `state.db`. Never
   kill the wrapper hosting the current conversation; leave it and tell
   the user that one poller remains until they close that session.
   Idle sessions are safe to kill (state is durable, they resume).
4. Verify the owner host's gateway is still active and still has the
   token.

Within a single host, `ps aux | grep -i hermes` returns dozens of
processes:
- `tui_gateway.entry` — one spawns per open TUI session (chat window).
  Many of these is normal; they only matter if they carry a token that
  another gateway is also polling with (see above).
- `hermes_cli.main gateway run --replace` — this is the ONE messaging
  gateway process that should be running. If you see more than one, or
  one with a suspiciously old start time (`ps aux` STARTED column shows
  days ago, e.g. "Sat12AM" while today is Monday), that's the stale
  instance still holding the Telegram long-poll session open on
  Telegram's servers.

```bash
ps aux | grep "gateway run" | grep -v grep
```

## Step 3 — kill the stale one, let launchd respawn
`hermes gateway restart` may report a timeout trying to drain it
gracefully ("Gateway PID still running after 0.0s — restart may fail").
When that happens, kill it directly:
```bash
kill -9 <stale_pid>
```
launchd auto-respawns a fresh gateway process within a few seconds (no
manual restart needed after the kill). Verify a new PID appeared:
```bash
ps aux | grep "gateway run" | grep -v grep
```

## Send-only alerts from a host that must not poll
A host that only needs to SEND alerts (watchdog, auth canary, no-agent
cron reports) cannot use Hermes's own Telegram platform without also
polling: `hermes send` / `send_message_tool` resolve the target through
`platforms.telegram.enabled` + token, and an enabled platform makes that
host's gateway start `getUpdates`, which re-creates the cross-host
conflict above. No send-only/outbound-only switch exists in the adapter
or config loader. Options, simplest first:
1. Relay through the owner host: `ssh <owner-alias> 'hermes send -t
   telegram:<chat_id> "<body>"'` (use the non-interactive SSH alias, not
   a tmux-wrapper alias). No token on the non-owner host at all. Weak
   spot: alerts about the owner host being down cannot leave; keep a local
   fallback (macOS banner) for that case.
2. Cron jobs on the non-owner host: `--deliver local` (report saved,
   visible via `hermes cron list`) unless relayed as above.
In this setup the watchdog/auth-canary relay is a channel string
`ssh:<host-alias>:<target>` (e.g. `ssh:devbox:telegram`) in the alert
config. The remote runs `"$HOME/.local/bin/hermes" send -t <target>`, so
the owner's home channel supplies the chat id; don't hardcode it in
memory or scripts. Send exactly one real test message after a change and
ask the user to confirm it arrived. Exit 0 on the remote doesn't prove
delivery.
Scripts run by launchd get a minimal PATH, so a bare `hermes` there can
resolve to nothing or the wrong binary (watchdog "`hermes status` failed,
exit 2" false alarms). Resolve `~/.local/bin/hermes` absolutely and
reproduce with `env -i HOME=$HOME PATH=/usr/bin:/bin:/usr/sbin:/sbin
/usr/bin/python3 <script>`. Test under `/usr/bin/python3` (3.9) too,
since launchd uses system python.
After scrubbing the token, `gateway_state.json` keeps the last
`telegram: fatal` entry indefinitely (nothing rewrites a platform that no
longer starts). Make the watchdog ignore that platform on the non-owner
host instead of chasing it as a live failure.

## Step 4 — verify reconnection against ground truth, not the notification
```bash
cat ~/.hermes/gateway_state.json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); [print(f'{k}: {v.get(\"state\",\"?\")}') for k,v in d.get('platforms',{}).items()]"
```
Confirm the platform shows `connected` before telling the user it's fixed.

# Granting a messaging user access (allowlist / pairing)

When asked to "add X to the allowlist" with a Telegram user ID (often a
pasted userinfo-bot card with `id:`):

1. Check how access is managed now. Don't grep all of `~/.hermes` for
   "allowed"; that hits dozens of plugin.yaml descriptions. Look directly at:
   - `hermes pairing list` (pending + approved users)
   - `~/.hermes/platforms/pairing/<platform>-approved.json`
   - `TELEGRAM_ALLOWED_USERS` / `GATEWAY_ALLOWED_USERS` in `~/.hermes/.env`
2. If the box uses DM pairing (approved.json holds the owner, no env
   allowlist), add the user without needing a pairing code by appending an
   entry to `<platform>-approved.json`, keyed by the numeric ID as a string:
   `"<numeric-id>": {"user_name": "<username>", "approved_at": <epoch>}`.
   Keep existing entries untouched. `hermes pairing approve <platform> <CODE>`
   only works if the person has already DMed the bot and got a code.
   Use the env allowlist route only if the box already uses it, since that
   needs a gateway restart and a restart ends the current gateway chat.
3. Verify with `hermes pairing list`: the new ID must appear under Approved
   Users. No gateway restart needed for the approved.json route.
4. Tell the user the new person is a regular user (chat + `/help`,
   `/whoami`), not admin, and offer to elevate. Revoke with
   `hermes pairing revoke <platform> <id>`.
