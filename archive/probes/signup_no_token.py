import sys; sys.path.insert(0,"/home/god/Documents/token-harbour-farm")
"""Sign up over HTTP through IPs whose precheck says needCaptcha:false.

Success = auth cookie present (sb-auth-auth-token). No Turnstile token is sent.
"""
import json
import re
import time

import th_http

GOOD = [
    "http://110.76.147.31:8080",
    "http://202.159.35.84:9933",
    "http://156.230.176.245:8080",
    "http://151.158.133.157:8080",
    "http://103.178.23.6:8080",
    "http://103.157.117.226:81",
    "http://151.158.133.153:8080",
    "http://157.20.35.18:8080",
    "http://154.19.38.195:1111",
    "http://103.36.9.9:8181",
]

for px in GOOD:
    try:
        res = th_http.signup(proxy=px)
    except Exception as e:
        print(f"{px} EXC {type(e).__name__}: {str(e)[:80]}")
        continue
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", res["body"]))[:200]
    auth = bool(res["auth"])
    print(f"{px} status={res['status']} need={res['need_captcha']} auth={auth} :: {txt}")
    if auth:
        print("SUCCESS", res["email"], res["password"])
        json.dump({"email": res["email"], "password": res["password"]},
                  open("/home/god/.hermes/cache/scratch/winner.json", "w"))
        break
    time.sleep(2)
