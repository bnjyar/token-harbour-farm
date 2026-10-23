#!/usr/bin/env python3
"""Pure-HTTP signup: rotate proxies until one authenticates (no browser at all)."""
import html as htmlmod, json, re, secrets, string, sys, uuid
from curl_cffi import requests as creq

BASE = "https://tokenharbor.ai"

def hidden_fields(doc):
    out = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', doc):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag); v = re.search(r'value="([^"]*)"', tag)
        if n: out[htmlmod.unescape(n.group(1))] = htmlmod.unescape(v.group(1)) if v else ""
    return out

def new_email():
    return creq.get("https://temp.tf/api/account", timeout=20, impersonate="chrome").json()["email"]

proxies = [l.strip() for l in open("/home/god/.hermes/cache/scratch/id_proxies_live.txt") if l.strip()]

for proxy in proxies:
    px = None if proxy == "direct" else {"http": proxy, "https": proxy}
    s = creq.Session(impersonate="chrome", proxies=px, timeout=25)
    try:
        r = s.get(f"{BASE}/login")
        if r.status_code != 200 or "Create account" not in r.text:
            print(f"{proxy}: get {r.status_code}"); continue
    except Exception as e:
        print(f"{proxy}: dead ({type(e).__name__})"); continue
    hid = hidden_fields(r.text)
    try:
        act_id = json.loads(hid.get("$ACTION_1:0", "{}")).get("id", "")
    except Exception:
        act_id = ""
    fp = str(uuid.uuid4())
    try:
        pre = s.get(f"{BASE}/api/auth/signup-precheck?fp={fp}")
        need = pre.json().get("needCaptcha")
    except Exception as e:
        print(f"{proxy}: precheck fail {e}"); continue
    print(f"{proxy}: precheck needCaptcha={need}")
    if need is not False:
        continue
    for variant in ("no-header", "with-header"):
        email = new_email()
        pw = "Py" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)) + "!7"
        fields = {
            "$ACTION_REF_1": hid.get("$ACTION_REF_1", ""),
            "$ACTION_1:0": hid.get("$ACTION_1:0", ""),
            "$ACTION_1:1": hid.get("$ACTION_1:1", ""),
            "$ACTION_KEY": hid.get("$ACTION_KEY", ""),
            "device_fingerprint": fp, "timezone": "Asia/Jakarta", "next": "",
            "email": email, "password": pw, "invite_code": "",
            "cf-turnstile-response": "",
        }
        headers = {"origin": BASE, "referer": f"{BASE}/login"}
        if variant == "with-header":
            headers["next-action"] = act_id
            headers["accept"] = "text/x-component"
        try:
            resp = s.post(f"{BASE}/login", data=fields, headers=headers, allow_redirects=False)
        except Exception as e:
            print(f"   {variant}: post fail {type(e).__name__}"); continue
        ck = list(s.cookies.keys())
        auth = [c for c in ck if "auth-token" in c and "verifier" not in c]
        print(f"   {variant}: {resp.status_code} cookies={ck}")
        snippet = re.sub(r"<[^>]+>", " ", resp.text)
        snippet = re.sub(r"\s+", " ", snippet)
        for kw in ("already", "Too many", "couldn't", "not supported", "captcha", "invalid", "Account created", "check your email"):
            i = snippet.lower().find(kw.lower())
            if i != -1:
                print("     msg:", snippet[max(0, i - 80):i + 160][:240]); break
        if auth:
            print("*** SUCCESS ***", email, pw, "cookies:", auth)
            open("/home/god/.hermes/cache/scratch/http_signup_hit.json", "w").write(
                json.dumps({"email": email, "password": pw, "proxy": proxy, "cookies": ck}))
            sys.exit(0)
print("no proxy produced an account")
