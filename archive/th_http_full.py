#!/usr/bin/env python3
"""Full pure-HTTP Token Harbor flow: signup -> verify -> create key -> test key."""
import json, re, sys, time
from curl_cffi import requests as creq
import th_http

BASE = "https://tokenharbor.ai"


def inbox(email, wait=120):
    end = time.time() + wait
    while time.time() < end:
        r = creq.post("https://temp.tf/api/check", json={"email": email, "wait": True},
                      timeout=90, impersonate="chrome")
        data = r.json().get("data") or []
        if data:
            return data
        time.sleep(5)
    return []


def verify(s, email):
    msgs = inbox(email)
    link = None
    for m in msgs:
        hit = re.findall(r"https://[a-z.]*tokenharbor\.ai/[^\"'\s<>]*verif[^\"'\s<>]*", m.get("body", ""))
        if hit:
            link = hit[0]
            break
    if not link:
        return False, "no_verify_mail"
    r = s.get(link, allow_redirects=True)
    cookies = {c.name for c in s.cookies.jar}
    return ("auth" in " ".join(cookies)), (r.status_code, r.url, sorted(cookies))


def list_keys(s):
    r = s.get(f"{BASE}/api/keys")
    return r.status_code, r.text[:300]


def create_key(s, label="hermes"):
    for payload in ({"label": label}, {"name": label}, {"label": label, "name": label}):
        r = s.post(f"{BASE}/api/keys", json=payload, headers={"origin": BASE, "referer": f"{BASE}/dashboard/api-keys"})
        if r.status_code < 400:
            return r.status_code, r.text[:400], payload
    return r.status_code, r.text[:300], None


if __name__ == "__main__":
    proxy = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "direct" else None
    res = th_http.signup(proxy)
    s = res["session"]
    print("signup:", res["status"], "need_captcha:", res["need_captcha"], "email:", res["email"], res["password"])
    print("cookies after signup:", res["cookies"])
    ok, info = verify(s, res["email"])
    print("verify:", ok, info)
    print("list keys:", list_keys(s))
    st, body, payload = create_key(s, "http-test")
    print("create:", st, payload, body)
    m = re.search(r"thk_live_[A-Za-z0-9_]+", body or "")
    if m:
        key = m.group(0)
        print("KEY:", key)
        tr, td = th_http.creq.post(f"{BASE}/v1/chat/completions",
                                   headers={"Authorization": f"Bearer {key}"},
                                   json={"model": "deepseek-v4-flash:free",
                                         "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
                                         "max_tokens": 16}, timeout=90)
        print("key test:", tr.status_code, td.text[:200])
