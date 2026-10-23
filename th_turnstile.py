#!/usr/bin/env python3
"""Token Harbor — Turnstile token minting over plain HTTP (no browser).

Mints a `cf-turnstile-response` through a solving service's REST API; the
signup itself (Next server-action replay) lives in th_http.py.

Providers / credential lookup (env first, then dotfile in cwd or $HOME):
  capsolver    CAPSOLVER_KEY    .capsolver_key    AntiTurnstileTask[ProxyLess] + metadata.action
  2captcha     TWOCAPTCHA_KEY   .2captcha_key     in.php method=turnstile
  solvecaptcha SOLVECAPTCHA_KEY .solvecaptcha_key in.php method=turnstile (cheapest, $0.80/1k)
  capmonster   CAPMONSTER_KEY   .capmonster_key   TurnstileTask
  yescaptcha   YESCAPTCHA_KEY   .yescaptcha_key   TurnstileTaskProxyless (no action field!)

Usage:
  python3 th_turnstile.py                     # provider picked from available keys
  python3 th_turnstile.py capsolver
  python3 th_turnstile.py 2captcha --proxy http://user:pass@ip:port
  python3 th_turnstile.py capsolver --json    # machine-readable output
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from curl_cffi import requests as creq

SITEKEY = "0x4AAAAAADBuC8Knz1EJZx9-"
PAGE_URL = "https://tokenharbor.ai/login?mode=signup"
ACTION = "signup"

KEY_ENV = {"capsolver": "CAPSOLVER_KEY", "2captcha": "TWOCAPTCHA_KEY", "yescaptcha": "YESCAPTCHA_KEY",
           "capmonster": "CAPMONSTER_KEY", "solvecaptcha": "SOLVECAPTCHA_KEY"}
KEY_FILE = {"capsolver": ".capsolver_key", "2captcha": ".2captcha_key", "yescaptcha": ".yescaptcha_key",
            "capmonster": ".capmonster_key", "solvecaptcha": ".solvecaptcha_key"}


def load_key(provider):
    v = os.environ.get(KEY_ENV[provider], "").strip()
    if v:
        return v
    for d in (Path.cwd(), Path.home()):
        p = d / KEY_FILE[provider]
        if p.is_file():
            v = p.read_text().strip()
            if v:
                return v
    raise SystemExit(
        f"[x] no {provider} key — set {KEY_ENV[provider]} or create {KEY_FILE[provider]} "
        f"(capsolver needs a ~$6 top-up; 2captcha/solvecaptcha start at $1)"
    )


def _px(proxy):
    if not proxy:
        return None
    p = proxy.strip()
    if "://" not in p:
        p = "http://" + p
    return p


def _net(url, **kw):
    r = creq.post(url, impersonate="chrome", timeout=30, **kw)
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f"{url} -> {r.status_code}: {r.text[:200]}")


# ------------------------------------------------------------------ providers
def _capsolver(key, sitekey, url, action, cdata, proxy, timeout, interval):
    # Per docs: extra Turnstile data goes in `metadata`, not top-level pageAction/data.
    task = {"type": "AntiTurnstileTaskProxyLess", "websiteURL": url, "websiteKey": sitekey}
    meta = {}
    if action:
        meta["action"] = action
    if cdata:
        meta["cdata"] = cdata
    if meta:
        task["metadata"] = meta
    if proxy:
        task["type"] = "AntiTurnstileTask"
        task["proxy"] = _px(proxy)
    d = _net("https://api.capsolver.com/createTask", json={"clientKey": key, "task": task})
    if d.get("errorId"):
        raise RuntimeError(f"capsolver createTask: {d.get('errorCode')} {d.get('errorDescription')}")
    tid = d["taskId"]
    return _poll("capsolver", lambda: _net("https://api.capsolver.com/getTaskResult",
                                           json={"clientKey": key, "taskId": tid}),
                 timeout, interval)


def _capmonster(key, sitekey, url, action, cdata, proxy, timeout, interval):
    task = {"type": "TurnstileTask", "websiteURL": url, "websiteKey": sitekey}
    d = _net("https://api.capmonster.cloud/createTask", json={"clientKey": key, "task": task})
    if d.get("errorId"):
        raise RuntimeError(f"capmonster createTask: {d.get('errorCode')} {d.get('errorDescription')}")
    tid = d["taskId"]
    return _poll("capmonster", lambda: _net("https://api.capmonster.cloud/getTaskResult",
                                            json={"clientKey": key, "taskId": tid}),
                 timeout, interval)


def _yescaptcha(key, sitekey, url, action, cdata, proxy, timeout, interval):
    # NOTE: YesCaptcha's Turnstile task has no action/cdata field — action is silently dropped.
    task = {"type": "TurnstileTaskProxyless", "websiteURL": url, "websiteKey": sitekey}
    if proxy:
        p = _px(proxy)
        creds, _, hostport = p.split("://", 1)[1].rpartition("@")
        host, _, port = hostport.partition(":")
        task = {"type": "TurnstileTask", "websiteURL": url, "websiteKey": sitekey,
                "proxyType": "http", "proxyAddress": host, "proxyPort": int(port or 80)}
        if creds:
            user, _, pw = creds.partition(":")
            task["proxyLogin"], task["proxyPassword"] = user, pw
    d = _net("https://api.yescaptcha.com/createTask", json={"clientKey": key, "task": task})
    if d.get("errorId"):
        raise RuntimeError(f"yescaptcha createTask: {d.get('errorCode')} {d.get('errorDescription')}")
    tid = d["taskId"]
    return _poll("yescaptcha", lambda: _net("https://api.yescaptcha.com/getTaskResult",
                                            json={"clientKey": key, "taskId": tid}),
                 timeout, interval)


def _in_php(name, base, key, sitekey, url, action, cdata, proxy, timeout, interval):
    """2captcha-style form API (2captcha, solvecaptcha, captchaai…)."""
    form = {"key": key, "method": "turnstile", "sitekey": sitekey, "pageurl": url, "json": 1}
    if action:
        form["action"] = action
    if cdata:
        form["data"] = cdata
    if proxy:
        p = _px(proxy).split("://", 1)[1]
        form.update({"proxy": p, "proxytype": "HTTP"})
    d = _net(f"{base}/in.php", data=form)
    if d.get("status") != 1:
        raise RuntimeError(f"{name} in.php: {d.get('error_text') or d}")
    tid = d["request"]

    def poll():
        r = creq.get(f"{base}/res.php", timeout=30, impersonate="chrome",
                     params={"key": key, "action": "get", "id": tid, "json": 1})
        return r.json()

    return _poll(name, poll, timeout, interval)


def _2captcha(key, sitekey, url, action, cdata, proxy, timeout, interval):
    return _in_php("2captcha", "https://2captcha.com", key, sitekey, url, action, cdata,
                   proxy, timeout, interval)


def _solvecaptcha(key, sitekey, url, action, cdata, proxy, timeout, interval):
    return _in_php("solvecaptcha", "https://api.solvecaptcha.com", key, sitekey, url, action,
                   cdata, proxy, timeout, interval)


def _poll(name, fn, timeout, interval):
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(interval)
        d = fn()
        if d.get("errorId"):
            raise RuntimeError(f"{name}: {d.get('errorCode')} {d.get('errorDescription') or d.get('error_text')}")
        if d.get("status") == "ready":
            sol = d.get("solution") or {}
            tok = sol.get("token") or sol.get("gRecaptchaResponse")
            if tok:
                return tok
            raise RuntimeError(f"{name}: ready but no token in {json.dumps(d)[:200]}")
        if d.get("status") == 1 and d.get("request"):  # 2captcha async shape
            return d["request"]
    raise RuntimeError(f"{name}: timeout after {timeout}s")


PROVIDERS = {"capsolver": _capsolver, "2captcha": _2captcha, "solvecaptcha": _solvecaptcha,
             "capmonster": _capmonster, "yescaptcha": _yescaptcha}


def solve(provider=None, sitekey=SITEKEY, url=PAGE_URL, action=ACTION, cdata=None,
          proxy=None, timeout=150, interval=3):
    """Return a fresh cf-turnstile-response token, or raise RuntimeError."""
    if provider is None:
        for cand in ("capsolver", "2captcha", "solvecaptcha", "capmonster", "yescaptcha"):
            if os.environ.get(KEY_ENV[cand]) or (Path.cwd() / KEY_FILE[cand]).is_file():
                provider = cand
                break
        else:
            provider = "capsolver"
    if provider not in PROVIDERS:
        raise SystemExit(f"[x] unknown provider {provider!r}; pick from {', '.join(PROVIDERS)}")
    key = load_key(provider)
    return PROVIDERS[provider](key, sitekey, url, action, cdata, proxy, timeout, interval)


def main():
    ap = argparse.ArgumentParser(description="mint a Turnstile token over HTTP")
    ap.add_argument("provider", nargs="?", default=None, choices=[None, *PROVIDERS])
    ap.add_argument("--sitekey", default=SITEKEY)
    ap.add_argument("--url", default=PAGE_URL)
    ap.add_argument("--action", default=ACTION)
    ap.add_argument("--cdata", default=None)
    ap.add_argument("--proxy", default=None, help="solver-side proxy (only if the token must match an exit IP)")
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    try:
        tok = solve(a.provider, a.sitekey, a.url, a.action, a.cdata, a.proxy, a.timeout)
    except (RuntimeError, SystemExit) as e:
        print(f"[x] {e}")
        return 1
    if a.json:
        print(json.dumps({"provider": a.provider, "token": tok, "seconds": round(time.time() - t0, 1),
                          "length": len(tok)}))
    else:
        print(f"[+] token ({len(tok)} chars, {time.time() - t0:.1f}s): {tok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
