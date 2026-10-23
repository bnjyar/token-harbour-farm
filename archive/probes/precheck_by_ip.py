"""Check whether the captcha gate is per-IP: ask signup-precheck through every proxy.

needCaptcha:false => that exit IP can sign up with no Turnstile token at all.
"""
import concurrent.futures as cf
import uuid

from curl_cffi import requests as creq

BASE = "https://tokenharbor.ai"
proxies = [l.strip() for l in open("proxies.txt") if l.strip()]


def probe(px):
    url = f"{BASE}/api/auth/signup-precheck?fp={uuid.uuid4()}"
    p = px if "://" in px else "http://" + px
    try:
        r = creq.get(url, impersonate="chrome", timeout=12,
                     proxies={"http": p, "https": p})
        body = r.text[:80]
        return px, r.status_code, body
    except Exception as e:
        return px, "ERR", type(e).__name__


with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for px, st, body in ex.map(probe, proxies):
        print(f"{st!s:<4} {px:<28} {body}")
