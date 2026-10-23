#!/usr/bin/env python3
"""
Repair / finish a Token Harbor account in accounts.jsonl — pure HTTP, no browser.

Fills in whatever is missing:
  * login                (always)
  * verify email         (with --verify, or when the record has no key yet)
  * create an API key    (when the record has none)
  * live test of the key

The record stays compact: {"email","password","api_key"}.

Usage:
    python3 th_fix_verify.py                  # last record
    python3 th_fix_verify.py --email x@y.z
    python3 th_fix_verify.py --verify         # force re-verification attempt
"""

import argparse
import json
from pathlib import Path

import th_http


def load(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def save(path, rows):
    lines = []
    for r in rows:
        lines.append(json.dumps({"email": r["email"], "password": r["password"],
                                 "api_key": r.get("api_key", "")}))
    path.write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="repair an account: login, verify, key, test")
    ap.add_argument("-i", "--input", default="accounts.jsonl")
    ap.add_argument("--email", default=None)
    ap.add_argument("--verify", action="store_true", help="force an email-verification attempt")
    ap.add_argument("--proxy", default=None, help="optional proxy for the HTTP session")
    ap.add_argument("-l", "--label", default="hermes")
    args = ap.parse_args()

    path = Path(args.input)
    rows = load(path)
    if not rows:
        raise SystemExit("accounts.jsonl is empty")
    if args.email:
        idx = next((i for i, r in enumerate(rows) if r["email"] == args.email), None)
    else:
        idx = len(rows) - 1
    if idx is None:
        raise SystemExit("record not found")
    rec = rows[idx]
    print(f"[*] {rec['email']}")

    res = th_http.login(rec["email"], rec["password"], args.proxy)
    print("[*] login:", res["status"], "auth:", bool(res["auth"]))
    if not res["auth"]:
        raise SystemExit("[x] login failed — wrong password or account gone")

    if args.verify or not rec.get("api_key"):
        ok, info = th_http.verify_email(res["session"], rec["email"], wait=90)
        print("[*] verify:", ok, info)

    if not rec.get("api_key"):
        st, body = th_http.create_key(res["session"], args.label)
        rec["api_key"] = body.get("plaintext", "")
        print("[*] create key:", st, rec["api_key"] or body)

    print("[*] enable free models:", th_http.enable_free_models(res["session"]))

    if rec.get("api_key"):
        print("[*] key test:", th_http.test_key(rec["api_key"]))

    rows[idx] = rec
    save(path, rows)
    print(json.dumps({"email": rec["email"], "password": rec["password"],
                      "api_key": rec.get("api_key", "")}, indent=1))
    print("[*] saved:", path.resolve())


if __name__ == "__main__":
    main()
