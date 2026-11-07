
import json, subprocess, os, sys, time
HOME = os.path.expanduser("~")
ACCOUNT = "ayushaggarwal018@gmail.com"
MSG_FILE = HOME + "/.hermes/ti-hiring-state/signup-msg-name"
STATE = HOME + "/.hermes/ti-hiring-state/react-served.json"
SEEN = HOME + "/.hermes/ti-hiring-state/react-monitor-seen.json"
GRACE_SEC = 480
LOG = []

def gog(*a):
    r = subprocess.run(["gog", *a, "--account", ACCOUNT], capture_output=True, text=True, timeout=60)
    return r.stdout

def sh(*a, **kw):
    return subprocess.run(*a, capture_output=True, text=True, timeout=kw.get("timeout",120))

# 1. self-heal: if the watcher loop is dead, restart it
loop_alive = bool(sh(["pgrep","-f","react-loop.sh"]).stdout.strip())
if not loop_alive:
    LOG.append("watcher loop was dead -> restarting")
    subprocess.Popen(["bash",HOME + "/.hermes/scripts/react-loop.sh"], stdout=open("/tmp/react-watcher.log","a"), stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(2)
    loop_alive = bool(sh(["pgrep","-f","react-loop.sh"]).stdout.strip())
    LOG.append("restart " + ("ok" if loop_alive else "FAILED"))

# 2. self-heal: serve any reaction unserved past grace (watcher may have missed it)
served = set(json.load(open(STATE))) if os.path.exists(STATE) else set()
seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
now = time.time()
unserved = []
if os.path.exists(MSG_FILE):
    msg = open(MSG_FILE).read().strip()
    for line in gog("chat","messages","reactions","list",msg).splitlines():
        if "👍" in line and "users/" in line:
            pid = [p for p in line.split() if p.startswith("users/")][0].split("/")[-1]
            em = None
            for l in gog("people","get",f"people/{pid}").splitlines():
                if l.startswith("email"):
                    p2 = l.split(None,1)
                    if len(p2)>1: em = p2[1].strip().lower()
            if em and em not in served:
                unserved.append(em); seen.setdefault(em, now)
seen = {e:t for e,t in seen.items() if e in unserved}
json.dump(seen, open(SEEN,"w"))
stale = [e for e in unserved if now - seen.get(e, now) > GRACE_SEC]
if stale:
    LOG.append(f"unserved past grace {stale} -> running watcher directly")
    r = sh(["python3",HOME + "/.hermes/scripts/react-watcher.py"], timeout=300)
    LOG.append("watcher run: " + (r.stdout.strip()[-300:] or r.stderr.strip()[-300:] or "no output"))

# output only when something happened (watchdog: quiet when all healthy)
if LOG:
    print(" | ".join(LOG))
