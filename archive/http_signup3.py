#!/usr/bin/env python3
"""Try server-action POST variants until one authenticates (no browser)."""
import html as htmlmod, json, re, secrets, string, sys, uuid
from curl_cffi import requests as creq

BASE = "https://tokenharbor.ai"
proxy = sys.argv[1] if len(sys.argv) > 1 else "direct"
proxies = None if proxy == "direct" else {"http": proxy, "https": proxy}

def hidden_fields(doc):
    out = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', doc):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag); v = re.search(r'value="([^"]*)"', tag)
        if n: out[htmlmod.unescape(n.group(1))] = htmlmod.unescape(v.group(1)) if v else ""
    return out

def new_email():
    return creq.get("https://temp.tf/api/account", timeout=20, impersonate="chrome").json()["email"]

s = creq.Session(impersonate="chrome", proxies=proxies, timeout=45)
r = s.get(f"{BASE}/login")
hid = hidden_fields(r.text)
print("hidden full:", json.dumps(hid, indent=1)[:600])
try:
    ref = json.loads(hid.get("$ACTION_1:0", "{}"))
except Exception:
    ref = {}
print("action ref:", json.dumps(ref)[:300])
act_id = ref.get("id", "")

for variant in ("no-header", "with-header", "action-id-field"):
    email = new_email()
    pw = "Py" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)) + "!7"
    fields = {
        "$ACTION_REF_1": hid.get("$ACTION_REF_1", ""),
        "$ACTION_1:0": hid.get("$ACTION_1:0", ""),
        "$ACTION_1:1": hid.get("$ACTION_1:1", ""),
        "$ACTION_KEY": hid.get("$ACTION_KEY", ""),
        "device_fingerprint": str(uuid.uuid4()),
        "timezone": "Asia/Jakarta",
        "next": "",
        "email": email,
        "password": pw,
        "invite_code": "",
        "cf-turnstile-response": "",
    }
    headers = {"origin": BASE, "referer": f"{BASE}/login"}
    if variant == "with-header":
        headers["next-action"] = act_id
        headers["accept"] = "text/x-component"
    elif variant == "action-id-field":
        fields = {f"$ACTION_ID_{act_id}": "", **{k: v for k, v in fields.items()
                  if k not in ("$ACTION_REF_1", "$ACTION_1:0", "$ACTION_1:1", "$ACTION_KEY")}}
    resp = s.post(f"{BASE}/login", data=fields, headers=headers, allow_redirects=False)
    cookies = list(s.cookies.keys())
    body = resp.text
    err = ""
    for kw in ("already", "Too many", "couldn't", "not supported", "captcha", "invalid", "error"):
        i = body.lower().find(kw.lower())
        if i != -1:
            err = body[max(0, i - 100):i + 160].replace("\n", " ")
            break
    print(f"[{variant}] status={resp.status_code} loc={resp.headers.get('location')} cookies={cookies}")
    print(f"   body[{len(body)}]: {body[:200].strip()[:200]}")
    if err:
        print(f"   msg: {err[:300]}")
    if any("auth" in c for c in cookies):
        print("   *** AUTH COOKIE SET ***", email, pw)
        break
