"""Recon of the Turnstile challenge document fetched over plain HTTP.

Answers: is the per-render segment validated? where is the config, the challenge id,
the opaque tokens, the inline program, and the network endpoints?
"""
import re
import sys

from curl_cffi import requests as creq

SK = "0x4AAAAAADBuC8Knz1EJZx9-"
HOST = "https://challenges.cloudflare.com"
PATH = "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/{seg}/%s/light/fbE/new/normal?lang=auto" % SK


def fetch(seg):
    s = creq.Session(impersonate="chrome", timeout=30)
    r = s.get(HOST + PATH.format(seg=seg), headers={"referer": "https://tokenharbor.ai/"})
    return r


# 1) is the 5-char segment validated, or any base36 segment accepted?
print("== segment probe ==")
for seg in ["9n9y4", "aaaaa", "zzzz9", "9n9y5", "1a2b3", "00000"]:
    try:
        r = fetch(seg)
        print(f"  {seg}: {r.status_code} {len(r.text)}")
    except Exception as e:
        print(f"  {seg}: ERR {type(e).__name__}")

doc = open("/home/god/.hermes/cache/scratch/challenge.html").read()
print("\n== document ==")
print("len", len(doc))
print("scripts:", len(re.findall(r"<script", doc)), "| inline len:",
      [len(m) for m in re.findall(r"<script[^>]*>(.*?)</script>", doc, re.S)][:5])
print("csp nonce:", (re.search(r"nonce-([^'\"]+)", doc) or [None, None])[1] if "nonce-" in doc else None)
for pat in ["_cf_chl_opt", "turnstile.dx", "chlId", "chl_api", "orchestrate", "cf-chl", "WebAssembly",
            "eval(", "atob(", "postMessage", "sitekey", "0x4AAAAAADBuC8Knz1EJZx9-"]:
    print(f"  {pat!r}: {len(re.findall(re.escape(pat), doc))}")

print("\n== head of document ==")
print(doc[:1200])
