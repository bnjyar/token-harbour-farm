#!/usr/bin/env python3
"""
View / filter Token Harbor accounts created by th_register.py
"""

import argparse
import json
import sys
from pathlib import Path


def load_accounts(path):
    accounts = []
    p = Path(path)
    if not p.exists():
        print(f"[!] File not found: {p}")
        sys.exit(1)
    with open(p, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                accounts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return accounts


def main():
    parser = argparse.ArgumentParser(description="View Token Harbor accounts")
    parser.add_argument("-i", "--input", type=str, default="accounts.jsonl", help="Accounts file")
    parser.add_argument("--success-only", action="store_true", help="Only successful accounts")
    parser.add_argument("--verified-only", action="store_true", help="Only verified accounts")
    parser.add_argument("--csv", action="store_true", help="Output as CSV")
    args = parser.parse_args()

    accounts = load_accounts(args.input)

    if args.success_only:
        accounts = [a for a in accounts if a.get("success", True)]
    if args.verified_only:
        accounts = [a for a in accounts if a.get("verified")]

    print(f"[*] Total accounts: {len(accounts)}\n")

    if args.csv:
        print("email,password,api_key")
        for a in accounts:
            print(f"{a.get('email','')},{a.get('password','')},{a.get('api_key','')}")
    else:
        for idx, a in enumerate(accounts, 1):
            print(f"[{idx}] {a.get('email','N/A')} | {a.get('password','')} | {a.get('api_key') or '-'}")
            if a.get("error"):
                print(f"      Error: {a['error']}")


if __name__ == "__main__":
    main()
