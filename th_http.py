#!/usr/bin/env python3
"""
Token Harbor — full HTTP client (no browser).

Covered without a browser:
  * login (Next server-action replay)      -> session cookies
  * list / create API keys                 -> /api/keys (JSON REST)
  * email verification                     -> temp.tf + verify link
  * key smoke test                         -> /v1/chat/completions

Signup is also replayable over HTTP (see signup()), but Token Harbor rejects
account creation from proxy/VPN networks server-side ("We couldn't verify your
network. Turn off any VPN or proxy..."), so signup needs a clean residential IP
or a captcha-solving service.

Usage:
  python3 th_http.py login <email> <password> [proxy|direct]
  python3 th_http.py key   <email> <password> [proxy|direct] [label]
  python3 th_http.py signup [proxy|direct]
"""

import json
import re
import secrets
import string
import sys
import time
import uuid

from curl_cffi import CurlMime, requests as creq

BASE = "https://tokenharbor.ai"
ACTION_KEY_RE = re.compile(r'name="\$ACTION_KEY"[^>]*value="([^"]+)"')
DEPLOY_RE = re.compile(r'data-dpl-id="([^"]+)"')
ROUTER_TREE = ('%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A'
               '%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C4096%5D%7D'
               '%2Cnull%2Cnull%2C4116%5D')
ACTION_REF = '{"id":"600202b5df997de7ccfb99eee71a88c9289db6442d","bound":"$@1"}'
LOGIN_ACTION = "600202b5df997de7ccfb99eee71a88c9289db6442d"
SIGNUP_ACTION = "6038f1ddf2bd8123b130aff0b4342056400ffca2a6"


def _px(proxy):
    return None if not proxy else {"http": proxy, "https": proxy}


def _session(proxy=None):
    return creq.Session(impersonate="chrome", proxies=_px(proxy), timeout=45)


def _auth_cookies(req):
    jar = {c.name: c.value for c in req.cookies.jar}
    return {k: v for k, v in jar.items() if "auth-token" in k and "verifier" not in k}


def _boot(s, action_id, fields, html):
    """POST a Next server-action form the way the browser does."""
    mp = CurlMime()
    dep = DEPLOY_RE.search(html)
    return s.post(
        f"{BASE}/login",
        multipart=mp,
        data=fields,
        headers={
            "next-action": action_id,
            "accept": "text/x-component",
            "next-router-state-tree": ROUTER_TREE,
            "x-deployment-id": dep.group(1) if dep else "",
            "origin": BASE,
            "referer": f"{BASE}/login",
        },
        allow_redirects=False,
    )


# ---------------------------------------------------------------- login
def login(email, password, proxy=None):
    s = _session(proxy)
    page = s.get(f"{BASE}/login")
    html = page.text
    key = ACTION_KEY_RE.search(html)
    fields = {
        "_1_$ACTION_REF_1": "",
        "_1_$ACTION_1:0": ACTION_REF,
        "_1_$ACTION_1:1": '["$undefined"]',
        "_1_$ACTION_KEY": key.group(1) if key else "",
        "_1_device_fingerprint": str(uuid.uuid4()),
        "_1_timezone": "Asia/Jakarta",
        "_1_next": "",
        "_1_email": email,
        "_1_password": password,
        "0": '["$undefined","$K1"]',
    }
    r = _boot(s, LOGIN_ACTION, fields, html)
    auth = _auth_cookies(s)
    return {"session": s, "status": r.status_code, "body": r.text, "auth": auth, "ok": bool(auth)}


# ---------------------------------------------------------------- keys
def list_keys(s):
    r = s.get(f"{BASE}/api/keys")
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:300]


def create_key(s, label="hermes"):
    r = s.post(f"{BASE}/api/keys", json={"label": label},
               headers={"origin": BASE, "referer": f"{BASE}/dashboard/api-keys"})
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:400]}
    return r.status_code, body


def enable_free_models(s):
    """Turn on the free routes (required before any :free model call works)."""
    r = s.post(f"{BASE}/api/me/privacy", json={"free_models_enabled": True},
               headers={"origin": BASE, "referer": f"{BASE}/dashboard"})
    return r.status_code, r.text[:200]


def revoke_key(s, key_id):
    r = s.delete(f"{BASE}/api/keys/{key_id}",
                 headers={"origin": BASE, "referer": f"{BASE}/dashboard/api-keys"})
    return r.status_code, r.text[:200]


# ---------------------------------------------------------------- signup (HTTP replay)
def signup(proxy=None, email=None, password=None, token=None, solver=None):
    """Replay the signup server action. `solver` mints the Turnstile token over HTTP."""
    s = _session(proxy)
    page = s.get(f"{BASE}/login")
    html = page.text
    pre = s.get(f"{BASE}/api/auth/signup-precheck?fp={uuid.uuid4()}")
    try:
        need = pre.json().get("needCaptcha")
    except Exception:
        need = None
    email = email or creq.get("https://temp.tf/api/account", impersonate="chrome", timeout=20).json()["email"]
    password = password or ("Py" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10)) + "!7")
    if not token and solver:
        import th_turnstile
        token = th_turnstile.solve(solver)
    key = ACTION_KEY_RE.search(html)
    fields = {
        "_1_$ACTION_REF_1": "",
        "_1_$ACTION_1:0": ACTION_REF,
        "_1_$ACTION_1:1": '["$undefined"]',
        "_1_$ACTION_KEY": key.group(1) if key else "",
        "_1_device_fingerprint": str(uuid.uuid4()),
        "_1_timezone": "Asia/Jakarta",
        "_1_next": "",
        "_1_cf-turnstile-response": token or "",
        "_1_email": email,
        "_1_password": password,
        "_1_invite_code": "",
        "0": '["$undefined","$K1"]',
    }
    r = _boot(s, SIGNUP_ACTION, fields, html)
    return {"session": s, "status": r.status_code, "need_captcha": need,
            "email": email, "password": password, "token": bool(token),
            "auth": _auth_cookies(s), "body": r.text}


def verify_email(s, email, wait=120):
    end = time.time() + wait
    link = None
    while time.time() < end and not link:
        r = creq.post("https://temp.tf/api/check", json={"email": email, "wait": True},
                      impersonate="chrome", timeout=90)
        for m in r.json().get("data") or []:
            hit = re.findall(r"https://[a-z.]*tokenharbor\.ai/[^\"'\s<>]*verif[^\"'\s<>]*", m.get("body", ""))
            if hit:
                link = hit[0]
                break
        if not link:
            time.sleep(5)
    if not link:
        return False, "no_mail"
    s.get(link)
    return bool(_auth_cookies(s)), link


def test_key(key, model="deepseek-v4-flash:free"):
    r = creq.post(f"{BASE}/v1/chat/completions",
                  headers={"Authorization": f"Bearer {key}"},
                  json={"model": model,
                        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                        "max_tokens": 16}, impersonate="chrome", timeout=90)
    try:
        content = r.json()["choices"][0]["message"]["content"][:60]
    except Exception:
        content = r.text[:200]
    return r.status_code, content


def main():
    argv = list(sys.argv[1:])
    allow_direct = "--allow-direct" in argv
    argv = [a for a in argv if a != "--allow-direct"]

    def flag(name):
        if name in argv:
            i = argv.index(name)
            v = argv[i + 1] if len(argv) > i + 1 else ""
            del argv[i:i + 2]
            return v
        for a in list(argv):
            if a.startswith(name + "="):
                argv.remove(a)
                return a.split("=", 1)[1]
        return None

    solver = flag("--solver")
    token = flag("--token")
    if len(argv) < 2:
        print(__doc__)
        return
    cmd = argv[0]

    def pick_proxy(idx):
        if len(argv) > idx and argv[idx] not in ("direct", None):
            return argv[idx]
        if allow_direct:
            return None
        raise SystemExit(
            "[x] proxy required — this tool is proxy-only by policy.\n"
            "    usage: python3 th_http.py %s <args> <proxy>   (or --allow-direct for debug)" % cmd
        )

    if cmd == "signup":
        px = pick_proxy(1)
        res = signup(px, token=token, solver=solver)
        print(json.dumps({k: res[k] for k in ("status", "need_captcha", "email", "password", "token")}, indent=1))
        print("auth:", bool(res["auth"]))
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", res["body"]))
        print("summary:", txt[:300])
    elif cmd == "provision":
        # signup -> verify -> key, entirely over HTTP (solver mints the Turnstile token)
        px = pick_proxy(1)
        res = signup(px, token=token, solver=solver)
        print("signup:", res["status"], "needCaptcha:", res["need_captcha"], "token:", res["token"], res["email"])
        if not res["auth"]:
            txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", res["body"]))
            print("blocked:", txt[:200])
            return
        ok, info = verify_email(res["session"], res["email"])
        print("verify:", ok)
        if not ok:
            return
        st, body = create_key(res["session"], "hermes")
        key = body.get("plaintext", "")
        print("key:", st, key)
        if key:
            print("test:", test_key(key))
            print(json.dumps({"email": res["email"], "password": res["password"],
                              "api_key": key, "base_url": f"{BASE}/v1"}, indent=1))
    elif cmd in ("login", "key"):
        email, pw = argv[1], argv[2]
        px = pick_proxy(3)
        res = login(email, pw, px)
        print("login:", res["status"], "auth:", bool(res["auth"]))
        if not res["auth"]:
            return
        if cmd == "key":
            label = argv[4] if len(argv) > 4 else "hermes"
            st, body = create_key(res["session"], label)
            print("create:", st, json.dumps(body)[:300])
            key = body.get("plaintext") or ""
            if key:
                print("KEY:", key)
                print("test:", test_key(key))
        else:
            print("keys:", json.dumps(list_keys(res["session"]))[:400])


if __name__ == "__main__":
    main()
