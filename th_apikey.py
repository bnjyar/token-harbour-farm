#!/usr/bin/env python3
"""
Token Harbor: register account + email verify + create API key + verify key works.

Output JSONL fields:
  email, password, success, verified, api_key, base_url, free_models, key_ok, created_at

Usage:
    python3 th_apikey.py                 # 1 account, key label "hermes"
    python3 th_apikey.py -n 3 -l main
    python3 th_apikey.py --enable-free   # also turn on free models (data-sharing consent)
"""

import argparse
import json
import re
import secrets
import string
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[!] Playwright not installed. Run: pip install playwright")
    sys.exit(1)

BASE = "https://tokenharbor.ai"
API_BASE = f"{BASE}/v1"
FREE_MODEL = "deepseek-v4-flash:free"
KEY_RE = re.compile(r"thk_live_[A-Za-z0-9_]+")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


# ---------------------------------------------------------------- helpers
def gen_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_temp_email():
    req = urllib.request.Request("https://temp.tf/api/account")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())["email"]


def check_inbox(email, max_wait=120):
    """Poll temp.tf inbox. NOTE: `wait: true` is required — without it the API
    returns [] even when mail has already arrived."""
    start = time.time()
    while time.time() - start < max_wait:
        req = urllib.request.Request(
            "https://temp.tf/api/check",
            data=json.dumps({"email": email, "wait": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
                if data.get("data"):
                    return data["data"]
        except Exception:
            pass
        time.sleep(5)
    return []


def extract_verify_link(messages):
    for msg in messages:
        body = msg.get("body", "") or ""
        links = re.findall(r"https://tokenharbor\.ai/verify-email\?token=[A-Za-z0-9_-]+", body)
        if links:
            return links[0]
        # generic fallback: any tokenharbor link containing verify
        links = re.findall(r"https://[a-z.]*tokenharbor\.ai/[^\"'\s<>]*verif[^\"'\s<>]*", body)
        if links:
            return links[0]
    return None


def kill_overlays(page, nuke=False):
    """Dismiss cookie/free-model modals. nuke=True also strips fixed overlays
    (only safe on dashboard pages — on /login it can wipe the Turnstile widget)."""
    page.evaluate(
        """(nuke) => {
            const btn = [...document.querySelectorAll('button')]
                .find(b => ['Not now','Dismiss','Close'].includes(b.innerText.trim()));
            if (btn) btn.click();
            if (!nuke) return;
            document.querySelectorAll('div.fixed.inset-0').forEach(el => {
                const c = el.className || '';
                if (c.includes('bg-black') || c.includes('z-[70]') || c.includes('backdrop')) el.remove();
            });
        }""",
        nuke,
    )
    time.sleep(1)


def enable_free_models(page):
    """POST /api/me/privacy {free_models_enabled:true} from page context."""
    res = page.evaluate(
        """async () => {
            try {
                const r = await fetch('/api/me/privacy', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({free_models_enabled: true}),
                    credentials: 'include',
                });
                return {status: r.status, body: await r.text()};
            } catch (e) { return {error: String(e)}; }
        }"""
    )
    ok = False
    try:
        ok = json.loads(res.get("body", "{}")).get("free_models_enabled") is True
    except Exception:
        pass
    if not ok:  # fallback: click the button
        clicked = page.evaluate(
            """() => {
                const btn = [...document.querySelectorAll('button')]
                    .find(b => b.innerText.trim() === 'Enable free models');
                if (!btn) return false;
                btn.click(); return true;
            }"""
        )
        time.sleep(4)
        ok = bool(clicked)
    return ok


def create_api_key(page, label):
    """Open /dashboard/api-keys, submit the new-key form, return the revealed key."""
    page.goto(f"{BASE}/dashboard/api-keys", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    kill_overlays(page, nuke=True)

    # open the form if it is not already open
    page.evaluate(
        """() => {
            if (document.querySelector('input[placeholder^="e.g."]')) return;
            const btn = [...document.querySelectorAll('button')]
                .find(b => b.innerText.trim() === '+ New key');
            if (btn) btn.click();
        }"""
    )
    page.wait_for_selector('input[placeholder^="e.g."]', timeout=15000)
    page.evaluate(
        """(label) => {
            const inp = document.querySelector('input[placeholder^="e.g."]');
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(inp, label);
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        label,
    )
    time.sleep(0.6)
    clicked = page.evaluate(
        """() => {
            const btn = [...document.querySelectorAll('button')]
                .find(b => b.innerText.trim() === 'Create key');
            if (!btn) return false;
            btn.scrollIntoView();
            btn.click();
            return true;
        }"""
    )
    if not clicked:
        return None, "create_button_missing"

    # the key is displayed once; poll the DOM for it
    for _ in range(20):
        time.sleep(1)
        text = page.inner_text("body")
        m = KEY_RE.search(text)
        if m:
            return m.group(0), None
    return None, "key_not_revealed"


def verify_key(api_key, model=FREE_MODEL, timeout=90):
    """Call the OpenAI-compatible endpoint with the new key."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
        "max_tokens": 16,
    }
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, {"status": resp.status, "reply": msg[:120], "model": model}
    except urllib.error.HTTPError as e:
        return False, {"status": e.code, "error": e.read().decode()[:300], "model": model}
    except Exception as e:
        return False, {"error": str(e), "model": model}


# ---------------------------------------------------------------- main flow
def register_with_key(chrome_path="/usr/bin/google-chrome-stable", headless=True,
                      proxy=None, label="hermes", enable_free=True):
    email = get_temp_email()
    password = gen_password()
    out = {
        "email": email,
        "password": password,
        "success": False,
        "verified": False,
        "api_key": None,
        "base_url": API_BASE,
        "free_models": False,
        "key_ok": False,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    with sync_playwright() as p:
        opts = {"executable_path": chrome_path, "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled"]}
        if proxy:
            m = re.match(r"https?://(?:([^:@/]+):([^@/]+)@)?([^/]+)", proxy)
            if not m:
                raise ValueError(f"bad proxy url: {proxy}")
            user, pw, hostport = m.groups()
            opts["proxy"] = {"server": f"http://{hostport}"}
            if user:
                opts["proxy"]["username"] = user
                opts["proxy"]["password"] = pw
        browser = p.chromium.launch(**opts)
        ctx = browser.new_context(viewport={"width": 1400, "height": 1200})
        page = ctx.new_page()
        try:
            # --- signup -------------------------------------------------
            page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            kill_overlays(page)
            try:
                page.click('button:has-text("Sign up")', timeout=10000)
                time.sleep(2)
            except Exception:
                pass

            if not page.query_selector('input[name="email"]'):
                # Cloudflare Turnstile gate: in a headful/real Chrome it clears itself
                # within ~10s, so wait instead of failing immediately.
                try:
                    page.wait_for_selector('input[name="email"]', timeout=45000)
                except Exception:
                    out["error"] = "turnstile_blocking_signup"
                    return out

            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', password)
            # Cloudflare Turnstile must have issued a token, otherwise the
            # submit is silently ignored (form stays, no error text).
            try:
                page.wait_for_function(
                    """() => {
                        const e = document.querySelector('input[name="cf-turnstile-response"]');
                        return !e || (e.value || '').length > 0;
                    }""",
                    timeout=45000,
                )
            except Exception:
                out["error"] = "turnstile_token_missing"
                return out
            page.click('button:has-text("Create account")')
            time.sleep(7)

            body = page.inner_text("body")
            for phrase, code in (
                ("This email is already on board", "email_already_registered"),
                ("already registered", "email_already_registered"),
                ("a bit fast", "signup_rate_limited"),
                ("don't match", "password_rejected"),
                ("too weak", "password_rejected"),
                ("not supported for Token Harbor accounts", "ip_or_provider_blocked"),
                ("couldn't create your account", "signup_rejected"),
                ("Too many sign-ups from this network", "network_signup_limit"),
            ):
                if phrase.lower() in body.lower():
                    out["error"] = code
                    out["signup_message"] = body[:500]
                    return out

            auth = [c for c in ctx.cookies() if "auth-token" in c["name"] and "code-verifier" not in c["name"]]
            if not auth:
                out["error"] = "signup_no_auth_cookie"
                out["signup_message"] = body[:500]
                return out
            out["success"] = True

            # --- email verification ------------------------------------
            messages = check_inbox(email, max_wait=45)
            link = extract_verify_link(messages)
            if link:
                page.goto(link, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)
                out["verified"] = "verify=success" in page.url or "verified" in page.inner_text("body").lower()
                out["verify_url"] = page.url

            # --- free models + API key ---------------------------------
            page.goto(f"{BASE}/dashboard", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            kill_overlays(page, nuke=True)
            if enable_free:
                out["free_models"] = enable_free_models(page)

            key, err = create_api_key(page, label)
            if not key:
                out["error"] = err
                return out
            out["api_key"] = key

            # --- prove the key works -----------------------------------
            ok, detail = verify_key(key)
            out["key_ok"] = ok
            out["key_test"] = detail
            return out
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
            return out
        finally:
            browser.close()


def validate_proxies(proxies, workers=12, timeout=15):
    """Probe each proxy against the signup precheck. Returns (ready, captcha, dead).

    ready   -> reachable AND needCaptcha:false (usable for signup right now)
    captcha -> reachable but the server wants a Turnstile token from that IP
    dead    -> timeout / non-200 / not the precheck JSON
    """
    import concurrent.futures as cf
    import urllib.request

    def probe(p):
        url = f"{BASE}/api/auth/signup-precheck?fp={uuid.uuid4()}"
        handler = urllib.request.ProxyHandler({"http": p, "https": p})
        opener = urllib.request.build_opener(handler)
        opener.addheaders = [("user-agent", UA)]
        try:
            with opener.open(url, timeout=timeout) as r:
                data = json.loads(r.read())
            return p, ("captcha" if data.get("needCaptcha") else "ready")
        except Exception:
            return p, "dead"

    ready, captcha, dead = [], [], []
    with cf.ThreadPoolExecutor(workers) as ex:
        for p, state in ex.map(probe, proxies):
            {"ready": ready, "captcha": captcha, "dead": dead}[state].append(p)
    return ready, captcha, dead


def parse_proxy(line):
    """Accept host:port, host:port:user:pass, user:pass@host:port or a full URL."""
    s = (line or "").strip().strip("\r\n")
    if not s or s.startswith("#"):
        return None
    if "://" in s:
        return s
    parts = s.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:  # Webshare style: ip:port:user:pass
        ip, port, user, pw = parts
        return f"http://{user}:{pw}@{ip}:{port}"
    if "@" in s:  # user:pass@ip:port
        return f"http://{s}"
    return None


def load_proxies(proxy=None, proxy_file=None):
    out = []
    if proxy:
        p = parse_proxy(proxy)
        if p:
            out.append(p)
    if proxy_file:
        path = Path(proxy_file).expanduser()
        if not path.exists():
            if proxy_file == "proxies.txt":  # default path may simply be absent
                return out
            raise SystemExit(f"proxy file not found: {path}")
        for line in path.read_text().splitlines():
            p = parse_proxy(line)
            if p:
                out.append(p)
    return out


def mask_proxy(p):
    if not p:
        return "direct"
    m = re.match(r"https?://(?:[^@/]+@)?(.+)", p)
    return m.group(1) if m else p


RETRYABLE = {
    "signup_rate_limited",
    "network_signup_limit",
    "turnstile_token_missing",
    "turnstile_blocking_signup",
    "signup_no_auth_cookie",
    "email_already_registered",
    "ip_or_provider_blocked",
    "signup_rejected",
}


def main():
    ap = argparse.ArgumentParser(description="Token Harbor: account + API key")
    ap.add_argument("-n", "--count", type=int, default=1)
    ap.add_argument("-o", "--output", default="accounts.jsonl", help="successful accounts (JSONL)")
    ap.add_argument("--failed-output", default="logs/failed.jsonl", help="failed attempts (JSONL)")
    ap.add_argument("-l", "--label", default="hermes")
    ap.add_argument("--chrome", default="/usr/bin/google-chrome-stable")
    ap.add_argument("--proxy", default=None, help="single proxy")
    ap.add_argument("--proxy-file", default="proxies.txt",
                    help="proxy list, one per line (rotated per attempt / on rate limit)")
    ap.add_argument("--retries", type=int, default=0,
                    help="extra attempts per account with the next proxy (default: 0)")
    ap.add_argument("--allow-direct", action="store_true",
                    help="DEBUG ONLY: allow running without a proxy (bot policy: always use a proxy)")
    ap.add_argument("--no-validate", action="store_true",
                    help="skip the precheck probe of each proxy")
    ap.add_argument("--include-captcha", action="store_true",
                    help="also use proxies whose IP already requires a Turnstile token")
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--no-free", action="store_true", help="skip enabling free models")
    ap.add_argument("--delay", type=int, default=5)
    args = ap.parse_args()

    proxies = load_proxies(args.proxy, args.proxy_file)

    if not proxies and not args.allow_direct:
        raise SystemExit(
            "[x] No proxies loaded.\n"
            "    This bot is proxy-only by policy — it will not register from the direct IP.\n"
            "    Put proxies in ./proxies.txt (ip:port / ip:port:user:pass / http://user:pass@ip:port)\n"
            "    or pass --proxy-file PATH. Use --proxy for a single one.\n"
            "    Debug escape hatch: --allow-direct (not for real runs)."
        )

    if proxies and not args.no_validate:
        print(f"[*] validating {len(proxies)} proxies (signup precheck)...", flush=True)
        ready, captcha, dead = validate_proxies(proxies)
        print(f"[*] ready={len(ready)} captcha-required={len(captcha)} dead={len(dead)}")
        usable = ready + (captcha if args.include_captcha else [])
        if not usable and not args.allow_direct:
            raise SystemExit("[x] No usable proxies (all dead or captcha-gated). Refresh the proxy list.")
        proxies = usable or (proxies if args.allow_direct else [])

    if not proxies:
        print("[!] running DIRECT — debug mode only, expect the hourly network limit")

    outp = Path(args.output)
    failp = Path(args.failed_output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    failp.parent.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    cursor = 0

    def next_proxy():
        nonlocal cursor
        if not proxies:
            return None
        p = proxies[cursor % len(proxies)]
        cursor += 1
        return p

    print(f"[*] proxies: {len(proxies)}" + ("" if proxies else " (direct)"))
    with open(outp, "a") as f, open(failp, "a") as ff:
        for i in range(1, args.count + 1):
            attempts = args.retries + 1
            for att in range(1, attempts + 1):
                proxy = next_proxy()
                tag = f" via {mask_proxy(proxy)}" if proxy else " direct"
                print(f"[{i}/{args.count}] attempt {att}/{attempts}{tag}...", end=" ", flush=True)
                r = register_with_key(
                    chrome_path=args.chrome,
                    headless=not args.no_headless,
                    proxy=proxy,
                    label=args.label,
                    enable_free=not args.no_free,
                )
                r["proxy"] = mask_proxy(proxy) if proxy else None
                if r.get("success") and r.get("api_key"):
                    ok += 1
                    # accounts.jsonl keeps credentials + key only
                    f.write(json.dumps({"email": r["email"], "password": r["password"],
                                        "api_key": r["api_key"]}) + "\n")
                    f.flush()
                    print(f"OK verified={r['verified']} free={r['free_models']} key_ok={r['key_ok']} -> {r['email']}")
                    print(f"      key: {r['api_key']}")
                    break
                fail += 1
                ff.write(json.dumps(r) + "\n")
                ff.flush()
                print(f"FAIL -> {r.get('error')}")
                if r.get("error") not in RETRYABLE or att == attempts or len(proxies) < 2:
                    break
                time.sleep(2)
            if i < args.count:
                time.sleep(args.delay)

    print(f"\n[*] done: ok={ok} fail={fail}")
    print(f"[*] accounts: {outp.resolve()}")
    print(f"[*] failures: {failp.resolve()}")


if __name__ == "__main__":
    main()
