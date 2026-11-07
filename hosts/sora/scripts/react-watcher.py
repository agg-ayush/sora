#!/usr/bin/env python3
"""Reaction watcher: serve each thumbs-up reactor on the signup message who
hasn't been served yet. Serve = create a session ~15min out + email them the
assessment link (with the new Meet) via startgreat Gmail. State in
~/.hermes/ti-hiring-state/react-served.json so restarts don't re-serve."""
import json, os, subprocess, sys, time, base64, urllib.request, urllib.parse
HOME = os.path.expanduser("~")

ACCT = "ayushaggarwal018@gmail.com"           # gog account for chat reads
MSG_FILE = HOME + "/.hermes/ti-hiring-state/signup-msg-name"
SERVED = HOME + "/.hermes/ti-hiring-state/react-served.json"
ADMIN = open(HOME + "/.ti-hiring-admin-token").read().strip()
BASE = "https://<internal-host>"
ASSIGNMENT = "the-spec-nobody-implemented"
DURATION_MIN = 30
KEYRING_PW = open(HOME + "/.config/gogcli/.keyring-pw").read().strip()
ENV = dict(os.environ, GOG_KEYRING_PASSWORD=KEYRING_PW)

def gog(*a):
    return subprocess.run(["gog", *a, "--account", ACCT], capture_output=True, text=True, timeout=60, env=ENV).stdout

def ssm(name):
    return subprocess.run(["aws","ssm","get-parameter","--name",name,"--with-decryption","--region","ap-south-1","--query","Parameter.Value","--output","text"], capture_output=True, text=True).stdout.strip()

def gmail_token():
    cid=ssm("/ti/orchestrator/GOOGLE_OAUTH_CLIENT_ID"); cs=ssm("/ti/orchestrator/GOOGLE_OAUTH_CLIENT_SECRET"); rt=ssm("/ti/orchestrator/GOOGLE_OAUTH_REFRESH_TOKEN")
    body=urllib.parse.urlencode({"client_id":cid,"client_secret":cs,"refresh_token":rt,"grant_type":"refresh_token"}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body, headers={"Content-Type":"application/x-www-form-urlencoded"}, method="POST"), timeout=20).read())["access_token"]

def api(method, path, body=None):
    data=json.dumps(body).encode() if body is not None else None
    h={"Authorization":f"Bearer {ADMIN}"}
    if body is not None: h["Content-Type"]="application/json"
    req=urllib.request.Request(BASE+path, data=data, headers=h, method=method)
    r=urllib.request.urlopen(req, timeout=30); return json.loads(r.read())

def reactors():
    """Yield (email, name) for each thumbs-up reactor."""
    msg = open(MSG_FILE).read().strip()
    for line in gog("chat","messages","reactions","list",msg).splitlines():
        if "👍" not in line or "users/" not in line: continue
        pid = [p for p in line.split() if p.startswith("users/")][0].split("/")[-1]
        pe = gog("people","get",f"people/{pid}")
        em = nm = None
        for l in pe.splitlines():
            ls=l.strip()
            if ls.startswith("email"):
                p=ls.split(None,1); em=p[1].strip().lower() if len(p)>1 else None
            if ls.startswith("name"):
                p=ls.split(None,1); nm=p[1].strip() if len(p)>1 else None
        if em: yield em, (nm or em.split("@")[0])

def send_link_email(at, to, name, meet):
    first = name.split()[0]
    html = f'''<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;color:#111;line-height:1.55;font-size:15px">
<p>Hi {first},</p>
<p>Please read these instructions carefully ahead of your assessment.</p>
<p><b>Technical assessment &mdash; about 30 minutes</b></p>
<p>This is a live coding assessment of about 30 minutes. You will work in a live environment with an AI agent, exactly as you would on a real task.</p>
<p>Link: <a href="https://<internal-host>/"><b>https://<internal-host>/</b></a></p>
<ul>
<li>Sign in with the email address this was sent to.</li>
<li>Join the video call at <a href="{meet}"><b>{meet}</b></a> and keep your camera, microphone and screen share on for the whole session.</li>
<li>Set aside 30 uninterrupted minutes in a quiet place with a stable internet connection.</li>
<li>Your session is scheduled to start about 15 minutes from now. Join any time from then, up to 10 minutes after the start, or the session lapses. The exact start time is on your session page and the calendar invite.</li>
</ul>
<p><b>During the assessment:</b></p>
<ul>
<li>The 30-minute timer starts when you click Continue.</li>
<li>Our agents have internet access, so use them freely for any research. We need to see how you think and work, so anything done outside the assessment window disqualifies the submission.</li>
<li>Stay on the assessment tab: switching away more than once ends the session.</li>
<li>Click Done when you finish. If you do not, the session submits automatically when the timer runs out.</li>
</ul>
<p>If you face any issues at any point, reply to this email with screenshots and we will help you.</p>
<p>Good luck!<br>Regards, TI</p>
</div>'''
    raw = base64.urlsafe_b64encode(f"To: {to}\r\nSubject: Your Trilogy assessment link\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html}".encode()).decode()
    req=urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", data=json.dumps({"raw":raw}).encode(), headers={"Authorization":f"Bearer {at}","Content-Type":"application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=20).read()

def serve(em, nm, at):
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()+15*60))
    s = api("POST","/v1/sessions",{"candidateEmail":em,"candidateName":nm,"scheduledStartAt":start,"assignment":ASSIGNMENT,"durationMinutes":DURATION_MIN,"idempotencyKey":f"react-{em}-{int(time.time())}"})
    sid = s.get("id")
    meet = None
    for _ in range(20):  # wait for provisioning to create the Meet
        d = api("GET", f"/v1/sessions/{sid}/detail")
        meet = d.get("meet_url")
        if meet: break
        time.sleep(6)
    if not meet: raise RuntimeError(f"no meet for {sid}")
    send_link_email(at, em, nm, meet)
    print(f"served {em} ({nm}) session={sid} meet={meet}")

def main():
    if not os.path.exists(MSG_FILE):
        print("no signup-msg-name; nothing to watch"); return
    served = set(json.load(open(SERVED))) if os.path.exists(SERVED) else set()
    todo = [(em,nm) for em,nm in reactors() if em not in served]
    if not todo: return
    at = gmail_token()
    for em,nm in todo:
        try:
            serve(em,nm,at); served.add(em); json.dump(sorted(served), open(SERVED,"w"))
        except Exception as e:
            print(f"serve FAILED {em}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
