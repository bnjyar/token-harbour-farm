#!/usr/bin/env python3
"""Token Harbor farmer — pure HTTP, no browser, no captcha token.

The Turnstile gate is per exit IP: `/api/auth/signup-precheck` answers
`{"needCaptcha": false}` for clean IPs, and those IPs can sign up with no token
at all. So the pipeline is: probe the proxy pool -> sign up through the "ready"
IPs -> verify the temp inbox -> enable free models -> create + test an API key.

Usage:
  python3 th_farm.py -n 3
  python3 th_farm.py -n 5 --proxy-file proxies.txt --retries 2
  python3 th_farm.py -n 1 --allow-captcha --solver capsolver   # IPs that need a token
"""

import argparse
import concurrent.futures as cf
import json
import re
import time
import uuid
from pathlib import Path

from curl_cffi import requests as creq

import th_http

STORE = Path("accounts.jsonl")
FAILS = Path("logs/failed.jsonl")
READY, CAPTCHA, DEAD = "ready", "captcha", "dead"

ERROR_PATTERNS = [
    (r"Too many sign-ups", "network_signup_limit"),
    (r"doing that a bit fast", "signup_rate_limited"),
    (r"not supported for Token Harbor", "ip_or_provider_blocked"),
    (r"complete the human check", "turnstile_required"),
    (r"Bot check failed", "turnstile_rejected"),
    (r"This email is already on board|already registered", "email_taken"),
    (r"password", "weak_password"),
]


def _px(proxy):
    return {"http": proxy, "https": proxy} if proxy else None


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def classify(body):
    txt = _text(body)
    for pat, code in ERROR_PATTERNS:
        m = re.search(pat, txt, re.I)
        if m:
            s = max(0, m.start() - 60)
            return code, txt[s:m.end() + 160]
    return "signup_rejected", txt[:300]


def probe(proxy, timeout=12):
    """Bucket one proxy by what the captcha gate says about its exit IP."""
    fp = uuid.uuid4()
    try:
        r = creq.get(f"{th_http.BASE}/api/auth/signup-precheck?fp={fp}",
                     impersonate="chrome", timeout=timeout, proxies=_px(proxy))
        if r.status_code != 200:
            return proxy, DEAD, f"http_{r.status_code}"
        return proxy, (CAPTCHA if r.json().get("needCaptcha") else READY), r.text[:60]
    except Exception as e:
        return proxy, DEAD, type(e).__name__


def load_proxies(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line if "://" in line else "http://" + line)
    return out


def append_jsonl(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def store_account(email, password, key):
    rows = []
    if STORE.exists():
        for line in STORE.read_text().splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    if any(r.get("email") == email for r in rows):
        return False
    rows.append({"email": email, "password": password, "api_key": key})
    STORE.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return True


def provision(proxy, solver=None, allow_captcha=False, verify_wait=150, label="farm"):
    """signup -> verify email -> free models -> key -> live test. Returns a dict."""
    out = {"proxy": proxy, "email": None, "stage": "signup"}
    need = None
    if not allow_captcha:
        _, bucket, info = probe(proxy)
        if bucket != READY:
            return {**out, "ok": False, "error": f"ip_{bucket}", "message": info}

    res = th_http.signup(proxy=proxy, solver=solver)
    need = res["need_captcha"]
    out.update(email=res["email"], password=res["password"], need_captcha=need)
    if not res["auth"]:
        code, msg = classify(res["body"])
        return {**out, "ok": False, "error": code, "message": msg}

    out["stage"] = "verify"
    ok, info = th_http.verify_email(res["session"], res["email"], wait=verify_wait)
    if not ok:
        return {**out, "ok": False, "error": "verify_" + str(info)[:40]}

    out["stage"] = "key"
    st, body = th_http.create_key(res["session"], label)
    key = body.get("plaintext", "") if isinstance(body, dict) else ""
    if not key:
        return {**out, "ok": False, "error": f"key_http_{st}", "message": str(body)[:200]}

    out["stage"] = "test"
    th_http.enable_free_models(res["session"])
    st, content = th_http.test_key(key)
    out.update(api_key=key, key_status=st)
    if st != 200:
        return {**out, "ok": False, "error": f"key_test_{st}", "message": str(content)[:200]}

    store_account(out["email"], out["password"], key)
    return {**out, "ok": True}


def main():
    ap = argparse.ArgumentParser(description="HTTP-only Token Harbor farmer")
    ap.add_argument("-n", "--count", type=int, default=1)
    ap.add_argument("--proxy-file", default="proxies.txt")
    ap.add_argument("--retries", type=int, default=2, help="proxies to try per account")
    ap.add_argument("--probe-workers", type=int, default=12)
    ap.add_argument("--verify-wait", type=int, default=150)
    ap.add_argument("--allow-captcha", action="store_true", help="also use IPs that need a token")
    ap.add_argument("--solver", default=None, help="capsolver|2captcha|yescaptcha (needs a key)")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    proxies = load_proxies(args.proxy_file)
    if not proxies:
        raise SystemExit(f"[x] no proxies in {args.proxy_file} — nothing to farm from")

    print(f"[*] probing {len(proxies)} proxies for the captcha gate")
    buckets = {READY: [], CAPTCHA: [], DEAD: []}
    with cf.ThreadPoolExecutor(max_workers=args.probe_workers) as ex:
        for px, bucket, info in ex.map(probe, proxies):
            buckets[bucket].append(px)
    print(f"[*] ready={len(buckets[READY])} captcha={len(buckets[CAPTCHA])} dead={len(buckets[DEAD])}")

    pool = list(buckets[READY])
    if args.allow_captcha:
        pool += buckets[CAPTCHA]
    if not pool:
        raise SystemExit("[x] no usable proxies (all dead or captcha-gated without a solver)")

    made = 0
    for attempt in range(args.count):
        done = False
        for _ in range(min(args.retries, len(pool))):
            px = pool.pop(0)
            try:
                r = provision(px, solver=args.solver, allow_captcha=args.allow_captcha,
                              verify_wait=args.verify_wait)
            except Exception as e:
                r = {"ok": False, "proxy": px, "error": f"{type(e).__name__}", "message": str(e)[:200]}
            if r.get("ok"):
                made += 1
                print(f"[+] {r['email']}  key={r['api_key'][:22]}…  proxy={px}")
                done = True
                break
            print(f"[-] {px:<28} {r.get('error')}  {str(r.get('message', ''))[:90]}")
            append_jsonl(FAILS, {**r, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        if not done:
            print(f"[!] account {attempt + 1}/{args.count} failed on every proxy tried")
        time.sleep(args.delay)

    print(f"[*] created {made}/{args.count}; store={STORE.resolve()}")


if __name__ == "__main__":
    main()
