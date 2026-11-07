#!/usr/bin/env python3
"""TI concern watcher: polls GET /v1/admin/concerns (the alert-stream endpoint,
shipped as t_4b8e2d7f) for new concerns/trouble and delivers each to Telegram
(TI_CONCERN_TELEGRAM_CHAT, else the Telegram home channel). Cursor persisted between runs. Managed cron job, every minute."""
import json, os, subprocess, time
from pathlib import Path

HOME = os.path.expanduser("~")


def hermes_bin():
    # Resolve at call time: the install hash changes on every hermes update,
    # which silently breaks a hardcoded path (first noticed 2026-11-01).
    import glob, os, shutil
    candidates = ([shutil.which("hermes")]
                  + [HOME + "/.local/bin/hermes"]
                  + sorted(glob.glob(HOME + "/.hermes/installs/*/environments/*/venv/bin/hermes")))
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return "hermes"

ORCH = "https://<internal-host>"
ADMIN = HOME + "/.local/bin/ti-hiring-admin.sh"
CURSOR_FILE = Path(HOME + "/.hermes/state/ti-concern-cursor.json")
# Group chat id comes from the environment (never hardcode it in the repo); falls back to the
# platform home channel ("telegram") when TI_CONCERN_TELEGRAM_CHAT is unset. The systemd unit loads ~/.hermes/.env.
TELEGRAM_CHAT = os.environ.get("TI_CONCERN_TELEGRAM_CHAT", "").strip()
TELEGRAM_TARGET = f"telegram:{TELEGRAM_CHAT}" if TELEGRAM_CHAT else "telegram"


def log(msg):
    print(msg, flush=True)


def send_telegram(text):
    p = subprocess.run([hermes_bin(), "send", "-t", TELEGRAM_TARGET, text],
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        log(f"telegram send failed: {(p.stdout or '')[-150:]} {(p.stderr or '')[-150:]}")
    return p.returncode == 0


def fetch_page(cursor):
    path = f"/v1/admin/concerns?limit=100" + (f"&after={cursor}" if cursor else "")
    p = subprocess.run([ADMIN, "GET", path], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise RuntimeError(f"concerns GET failed: {(p.stdout or '')[-150:]} {(p.stderr or '')[-150:]}")
    raw = "\n".join(l for l in p.stdout.splitlines() if not l.startswith("[http"))
    return json.loads(raw)



def check_gate_expirations():
    """New ready_expired* sessions since last tick -> telegram. Reads the session list
    (cheap: scheduled-for-today filter client-side) and compares end timestamps."""
    import time as _t
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    marker = Path(HOME + "/.hermes/state/ti-gate-expiry-seen.json")
    p = subprocess.run([ADMIN, "GET", "/v1/sessions?limit=500"], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return 0
    raw = "\n".join(l for l in p.stdout.splitlines() if not l.startswith("[http"))
    rows = json.loads(raw)
    now = datetime.now(timezone.utc)
    seen = {}
    if marker.exists():
        try: seen = json.load(open(marker)).get("ids", {})
        except Exception: seen = {}
    fresh = []
    for x in rows:
        er = x.get("endReason") or ""
        if not er.startswith("ready_expired"): continue
        sid = x["id"]
        end = x.get("endsAt") or ""
        if sid in seen: continue
        fresh.append(x)
    # first boot: seed without paging
    if not marker.exists():
        ids = {x["id"]: True for x in fresh}
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"ids": ids}))
        return 0
    delivered = 0
    for x in fresh:
        er = x.get("endReason")
        text = f"TI media-gate expiry [{er}] | session {x['id'][:20]} | {(x.get('candidateEmail') or '')[:40]} - candidate expired at the gate"
        if send_telegram(text):
            delivered += 1
        seen[x["id"]] = True
    marker.write_text(json.dumps({"ids": seen}))
    return delivered

def main():
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    cursor = None
    if CURSOR_FILE.exists():
        try:
            cursor = json.load(open(CURSOR_FILE)).get("cursor")
        except Exception:
            cursor = None

    if cursor is None:
        # first boot: grab a page to get the current nextCursor, deliver nothing
        page = fetch_page(None)
        cursor = page.get("nextCursor")
        CURSOR_FILE.write_text(json.dumps({"cursor": cursor}))
        log(f"watcher initialized at cursor {cursor}")
        return

    delivered = 0
    seen = 0
    newest = cursor
    while True:
        page = fetch_page(cursor)
        items = page.get("items") or []
        for a in items:
            seen += 1
            kind = a.get("concernKind") or a.get("kind") or "concern"
            session = (a.get("sessionId") or "?")[:20]
            note = (a.get("note") or "")[:250].replace("\n", " ")
            sess = a.get("session") or {}
            status = sess.get("status") or "?"
            if a.get("kind") == "trouble_exit":
                tx = a.get("troubleExit") or {}
                late = "late" if tx.get("late") else "on time"
                frm = tx.get("from") or "?"
                text = f"TI trouble exit | session {session} | from {frm} ({late}) | status {status}\n{note}"
            else:
                text = f"TI concern [{kind}] | session {session} | status {status}\n{note}"
            if send_telegram(text):
                delivered += 1
        newest = page.get("nextCursor") or newest
        if not page.get("hasMore"):
            break
        cursor = newest
    gate = check_gate_expirations()
    if seen or newest != cursor or gate:
        CURSOR_FILE.write_text(json.dumps({"cursor": newest}))
    if delivered or gate:
        log(f"delivered {delivered} concerns (seen {seen}) + {gate} gate expiries")


if __name__ == "__main__":
    main()
