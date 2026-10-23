#!/usr/bin/env python3
"""
Token Harbor Auto Register (Single + Bulk) + Email Verification
Uses temp.tf for disposable emails and Playwright for browser automation.

Requirements:
    pip install playwright
    # Chrome/Chromium must be installed

Usage:
    # Single account
    python3 th_register.py -n 1

    # Bulk (10 accounts)
    python3 th_register.py -n 10

    # With proxy (to avoid Cloudflare Turnstile)
    python3 th_register.py -n 5 --proxy http://user:pass@host:port

    # With 2captcha API key (to auto-solve Turnstile)
    python3 th_register.py -n 5 --captcha-key YOUR_2CAPTCHA_KEY
"""

import argparse
import json
import urllib.request
import urllib.parse
import time
import secrets
import string
import sys
import re
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("[!] Playwright not installed. Run: pip install playwright")
    sys.exit(1)


def gen_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def get_temp_email():
    req = urllib.request.Request("https://temp.tf/api/account")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["email"]


def check_inbox(email, max_wait=30):
    """Poll temp.tf inbox for emails."""
    start = time.time()
    while time.time() - start < max_wait:
        req = urllib.request.Request(
            "https://temp.tf/api/check",
            data=json.dumps({"email": email}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                if data.get("data"):
                    return data["data"]
        except Exception:
            pass
        time.sleep(3)
    return []


def extract_verify_link(messages):
    for msg in messages:
        body = msg.get("body", "")
        links = re.findall(
            r"https://tokenharbor\.ai/verify-email\?token=[A-Za-z0-9_-]+", body
        )
        if links:
            return links[0]
    return None


def solve_turnstile_2captcha(page, api_key):
    """Attempt to solve Cloudflare Turnstile using 2captcha."""
    try:
        # Try to extract sitekey from the page
        sitekey = page.evaluate(
            """() => {
            const el = document.querySelector('[data-sitekey]');
            return el ? el.getAttribute('data-sitekey') : null;
        }"""
        )
        if not sitekey:
            # Try from iframe or scripts
            html = page.content()
            keys = re.findall(r'data-sitekey=["\']([0-9a-zA-Z_-]+)["\']', html)
            if keys:
                sitekey = keys[0]

        if not sitekey:
            print("[!] Could not find Turnstile sitekey")
            return False

        print(f"[*] Found Turnstile sitekey: {sitekey}")
        print(f"[*] Submitting to 2captcha...")

        # Submit to 2captcha
        req = urllib.request.Request(
            "http://2captcha.com/in.php",
            data=urllib.parse.urlencode(
                {
                    "key": api_key,
                    "method": "turnstile",
                    "sitekey": sitekey,
                    "pageurl": "https://tokenharbor.ai/login",
                    "json": "1",
                }
            ).encode(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("status") != 1:
                print(f"[!] 2captcha error: {result}")
                return False
            captcha_id = result["request"]

        # Poll for result
        for _ in range(30):
            time.sleep(5)
            req2 = urllib.request.Request(
                f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
            )
            with urllib.request.urlopen(req2, timeout=30) as resp:
                result2 = json.loads(resp.read())
                if result2.get("status") == 1:
                    token = result2["request"]
                    print(f"[*] Got Turnstile token")
                    # Inject token into page
                    page.evaluate(
                        f"""() => {{
                        const el = document.querySelector('input[name="cf-turnstile-response"]');
                        if (el) el.value = "{token}";
                    }}"""
                    )
                    return True
                if result2.get("request") == "CAPCHA_NOT_READY":
                    continue
                print(f"[!] 2captcha result: {result2}")
                return False
    except Exception as e:
        print(f"[!] 2captcha error: {e}")
    return False


def register_account(
    chrome_path="/usr/bin/google-chrome-stable",
    headless=True,
    proxy=None,
    captcha_key=None,
):
    email = get_temp_email()
    password = gen_password()

    with sync_playwright() as p:
        launch_opts = {
            "executable_path": chrome_path,
            "headless": headless,
        }
        if proxy:
            launch_opts["proxy"] = {"server": proxy}

        browser = p.chromium.launch(**launch_opts)
        page = browser.new_page()

        try:
            # Step 1: Load login page
            page.goto("https://tokenharbor.ai/login")
            time.sleep(3)

            # Click Sign up tab
            page.click('button:has-text("Sign up")')
            time.sleep(2)

            # Check if Turnstile appeared (no email input)
            has_form = page.evaluate(
                """() => !!document.querySelector('input[name="email"]')"""
            )

            if not has_form:
                print("[!] Cloudflare Turnstile detected")
                if captcha_key:
                    if not solve_turnstile_2captcha(page, captcha_key):
                        return {
                            "email": email,
                            "password": password,
                            "success": False,
                            "error": "turnstile_captcha_failed",
                        }
                    # Re-check form
                    time.sleep(2)
                    has_form = page.evaluate(
                        """() => !!document.querySelector('input[name="email"]')"""
                    )
                    if not has_form:
                        return {
                            "email": email,
                            "password": password,
                            "success": False,
                            "error": "turnstile_persisted",
                        }
                else:
                    return {
                        "email": email,
                        "password": password,
                        "success": False,
                        "error": "turnstile_no_captcha_key",
                    }

            # Step 2: Fill form
            page.fill('input[name="email"]', email)
            page.fill('input[name="password"]', password)

            # Step 3: Submit
            page.click('button:has-text("Create account")')
            time.sleep(4)

            # Step 4: Verify success
            cookies = page.context.cookies()
            auth_cookies = [c for c in cookies if "auth-token" in c["name"]]
            signup_ok = len(auth_cookies) > 0

            if not signup_ok:
                return {
                    "email": email,
                    "password": password,
                    "success": False,
                    "error": "signup_no_auth_cookie",
                }

            # Step 5: Wait for verification email and verify
            messages = check_inbox(email, max_wait=30)
            verify_link = extract_verify_link(messages)

            verified = False
            if verify_link:
                page.goto(verify_link)
                time.sleep(3)
                if "verify=success" in page.url:
                    verified = True

            return {
                "email": email,
                "password": password,
                "success": True,
                "verified": verified,
                "verify_link": verify_link,
                "url": page.url,
            }
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="Token Harbor bulk register + verify"
    )
    parser.add_argument("-n", "--count", type=int, default=1, help="Number of accounts")
    parser.add_argument(
        "-o", "--output", type=str, default="tokenharbor_accounts.jsonl", help="Output file"
    )
    parser.add_argument("--headless", action="store_true", default=True, help="Run headless")
    parser.add_argument("--no-headless", action="store_true", help="Show browser")
    parser.add_argument(
        "--chrome", type=str, default="/usr/bin/google-chrome-stable", help="Chrome path"
    )
    parser.add_argument("--proxy", type=str, default=None, help="Proxy URL (http://host:port)")
    parser.add_argument(
        "--captcha-key", type=str, default=None, help="2captcha API key for Turnstile"
    )
    parser.add_argument("--delay", type=int, default=4, help="Base delay after submit")
    args = parser.parse_args()

    headless = not args.no_headless if args.no_headless else args.headless
    output_path = Path(args.output)

    print(f"[*] Bulk register: {args.count} account(s)")
    print(f"[*] Chrome: {args.chrome} | Headless: {headless}")
    if args.proxy:
        print(f"[*] Proxy: {args.proxy}")
    if args.captcha_key:
        print(f"[*] 2captcha: enabled")
    print(f"[*] Output: {output_path}\n")

    success = 0
    failed = 0

    with open(output_path, "a") as f:
        for i in range(1, args.count + 1):
            print(f"[{i}/{args.count}] Creating account...", end=" ", flush=True)
            try:
                result = register_account(
                    chrome_path=args.chrome,
                    headless=headless,
                    proxy=args.proxy,
                    captcha_key=args.captcha_key,
                )
                f.write(json.dumps(result) + "\n")
                f.flush()

                if result["success"]:
                    status = "VERIFIED" if result["verified"] else "UNVERIFIED"
                    print(f"OK ({status}) -> {result['email']}")
                    success += 1
                else:
                    print(f"FAIL -> {result.get('error', 'unknown')}")
                    failed += 1
            except Exception as e:
                print(f"ERROR: {e}")
                failed += 1

            if i < args.count:
                time.sleep(args.delay)

    print(f"\n[*] Done. Success: {success}, Failed: {failed}")
    print(f"[*] Saved to: {output_path.absolute()}")


if __name__ == "__main__":
    main()
