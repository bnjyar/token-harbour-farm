#!/usr/bin/env python3
"""Pure-HTTP signup attempt via Next.js server action (no browser).

Usage: python3 http_signup2.py <proxy|direct>
"""
import html as htmlmod
import json
import re
import secrets
import string
import sys
import time

from curl_cffi import requests as creq

BASE = "https://tokenharbor.ai"
proxy = sys.argv[1] if len(sys.argv) > 1 else "direct"
proxies = None if proxy == "direct" else {"http": proxy, "https": proxy}


def temp_email():
    r = creq.get("https://temp.tf/api/account", timeout=20, impersonate="chrome")
    return r.json()["email"]


def hidden_fields(doc):
    out = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', doc):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            out[htmlmod.unescape(n.group(1))] = htmlmod.unescape(v.group(1)) if v else ""
    return out


s = creq.Session(impersonate="chrome", proxies=proxies, timeout=45)
r = s.get(f"{BASE}/login", headers={"accept-language": "en-US,en;q=0.9"})
print("GET:", r.status_code, "| cookies:", list(s.cookies.keys()))
hid = hidden_fields(r.text)
print("hidden:", {k: (v[:50] + "…") if len(v) > 50 else v for k, v in hid.items()})

fp = str(__import__("uuid").uuid4())
pre = s.get(f"{BASE}/api/auth/signup-precheck?fp={fp}")
print("precheck:", pre.status_code, pre.text[:80])

email = temp_email()
pw = "Py" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)) + "!7"
print("email:", email)

fields = {
    "$ACTION_REF_1": hid.get("$ACTION_REF_1", ""),
    "$ACTION_1:0": hid.get("$ACTION_1:0", ""),
    "$ACTION_1:1": hid.get("$ACTION_1:1", ""),
    "$ACTION_KEY": hid.get("$ACTION_KEY", ""),
    "device_fingerprint": fp,
    "timezone": "Asia/Jakarta",
    "next": "",
    "email": email,
    "password": pw,
    "invite_code": "",
    "cf-turnstile-response": "",
}
act_id = ""
try:
    act_id = json.loads(fields["$ACTION_1:0"]).get("id", "")
except Exception:
    pass

headers = {
    "origin": BASE,
    "referer": f"{BASE}/login",
    "accept": "text/x-component",
}
if act_id:
    headers["next-action"] = act_id

resp = s.post(f"{BASE}/login", data=fields, headers=headers, allow_redirects=False)
print("POST:", resp.status_code, "| location:", resp.headers.get("location"))
print("set-cookie:", (resp.headers.get("set-cookie") or "")[:200])
print("cookies:", list(s.cookies.keys()))
body = resp.text
print("body len:", len(body))
print("head:", body[:400].replace("\n", " "))
# look for human-facing errors
for kw in ["already", "Too many", "couldn't", "not supported", "captcha", "verified", "success", "redirect"]:
    i = body.lower().find(kw.lower())
    if i != -1:
        print(f"  [{kw}] ...{body[max(0,i-150):i+200]}...".replace("\n", " ")[:420])
open("/home/god/.hermes/cache/scratch/http_signup2_resp.txt", "w").write(body)
print("EMAIL/PW:", email, pw)
