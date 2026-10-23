"""Probe: can the Turnstile challenge program be fetched over plain HTTP?

Tries every iframe path shape seen in the wild / in the reversed client, for the
tokenharbor sitekey, and reports which (if any) returns the challenge document.
"""
from curl_cffi import requests as creq

SK = "0x4AAAAAADBuC8Knz1EJZx9-"
HOST = "https://challenges.cloudflare.com"
PATHS = [
    # current build shape (brief): /turnstile/f/av0/rch/<seg>/<sitekey>/<theme>/fbE/<mode>/<size>
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/0/{sk}/light/fbE/new/normal?lang=auto",
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/9n9y4/{sk}/light/fbE/new/normal?lang=auto",
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/{sk}/light/fbE/new/normal?lang=auto",
    # older shape seen in reversed clients
    "/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv0/0/{sk}/light/fbE/new/normal?lang=auto",
    "/cdn-cgi/challenge-platform/h/b/turnstile/if/ov2/av0/rcv/0/{sk}/light/fbE/new/normal?lang=auto",
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/ov2/av0/rcv/0/{sk}/light/fbE/new/normal?lang=auto",
    # build-scoped variants
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/0/{sk}/auto/fbE/new/normal?lang=auto",
    "/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/0/{sk}/light/fbE/managed/normal?lang=auto",
]

s = creq.Session(impersonate="chrome", timeout=30)
for p in PATHS:
    u = HOST + p.format(sk=SK)
    try:
        r = s.get(u, headers={"referer": "https://tokenharbor.ai/",
                              "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        ct = r.headers.get("content-type", "")
        print(f"{r.status_code} {len(r.text):>7} {ct:<30} {p[:80]}")
        if r.status_code == 200 and len(r.text) > 2000:
            open("/home/god/.hermes/cache/scratch/challenge.html", "w").write(r.text)
            print("   -> SAVED challenge.html")
            break
    except Exception as e:
        print(f"ERR {type(e).__name__} {p[:70]}")
