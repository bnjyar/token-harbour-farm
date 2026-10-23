# Turnstile solving services — HTTP-only API comparison (Oct 2026)

Target context: `tokenharbor.ai` signup, Next.js server action, **managed** Turnstile widget.
Verified from the live bundle: `sitekey = 0x4AAAAAADBuC8Knz1EJZx9-`, rendered as
`turnstile.render(el, {sitekey, action:"signup", callback, error-callback})` — **`action="signup"`, no `cdata`**.
All prices are vendor-published unless marked *(reported)*. No accounts were created, no credits bought.

## 1. Commercial solver APIs

| # | Service | Create / poll endpoints | Auth field | Task type | Inputs | Action? | Advertised success | $/1000 | Min top-up |
|---|---------|------------------------|-----------|-----------|--------|---------|--------------------|--------|-----------|
| 1 | **CapSolver** | `POST https://api.capsolver.com/createTask` / `getTaskResult` | `clientKey` | `AntiTurnstileTaskProxyLess` (proxied: `AntiTurnstileTask` + `proxy`) | `websiteURL`, `websiteKey`; `metadata.action`, `metadata.cdata` optional | ✅ `metadata.action` | no official %; 1–20 s | **1.20** | *(reported)* ~$6 |
| 2 | **2Captcha** | `POST https://api.2captcha.com/createTask`+`getTaskResult` (JSON) **or** legacy `https://2captcha.com/in.php` / `res.php` (form) | `clientKey` / `key` | `TurnstileTaskProxyless` (`TurnstileTask` w/ proxy) / `method=turnstile` | `websiteURL`,`websiteKey`; `action`,`data`,`pagedata` optional | ✅ `action` | no %; ~2 s, 2 883/min free capacity | **1.45** | **$1** |
| 3 | **CapMonster Cloud** | `POST https://api.capmonster.cloud/createTask` / `getTaskResult` | `clientKey` | `TurnstileTask` | `websiteURL`,`websiteKey` | ❌ not documented | **99 %** | **1.30** | $0.10 test balance |
| 4 | **Anti-Captcha** | `POST https://api.anti-captcha.com/createTask` / `getTaskResult` | `clientKey` | `TurnstileTaskProxyless` / `TurnstileTask` | `websiteURL`,`websiteKey`; `action`,`cData`,`chlPageData` | ✅ `action` | no % (human pool) | **2.00** | not published |
| 5 | **SolveCaptcha** | `POST https://api.solvecaptcha.com/in.php` · `GET .../res.php?action=get&id=` | `key` | `method=turnstile` | `sitekey`,`pageurl`; `action`,`data`,`pagedata` optional | ✅ `action` | 99.9 % uptime | **0.80** | not published |
| 6 | **YesCaptcha** | `POST https://api.yescaptcha.com/createTask` / `getTaskResult` (also `cn.yescaptcha.com`) | `clientKey` | `TurnstileTaskProxyless` / `TurnstileTaskProxylessM1` / `TurnstileTask`+proxy | `websiteURL`,`websiteKey` | ❌ no field | no % | ¥25 → **≈3.73** | CNY top-up (1 000 pts = ¥1) |
| 7 | **NopeCHA** | `POST https://api.nopecha.com/token` → `{data:jobId}`; `GET https://api.nopecha.com/token?key=&id=` | `key` (body/query) | `type:"turnstile"` | `sitekey`,`url`; `data:{action,cdata}`; `proxy:{scheme,host,port,username,password}` | ✅ `data.action` | no % | subscription **$4.99/mo** (2 000 solves/day) | $4.99/mo |
| 8 | **DeathByCaptcha** | `POST http://api.dbcapi.me/api/captcha` (`type=12`, `turnstile_params=<json>`), poll `GET /api/captcha/<id>` | `username`+`password` | type 12 | `sitekey`,`pageurl`; `action`; `proxy`+`proxytype` | ✅ `action` | no % | **2.89** | not published |
| 9 | **CaptchaAI** (indie) | 2Captcha-compatible `in.php`/`res.php` | `key` | `method=turnstile` | `sitekey`,`pageurl` | ✅ (2captcha clone) | claims 99.9 %, <10 s | subscription from **$15/mo** | $15/mo |
| 10 | **SadCaptcha** | n/a for Turnstile | — | TikTok / Shein rotate-puzzle only | — | — | — | $0.00025–0.002/solve | — |

**"Turnstile" vs "Cloudflare Challenge"** — separate products, do not mix up:
CapSolver `AntiTurnstileTaskProxyLess` vs `CloudflareTask`; CapMonster `TurnstileTask` vs "Cloudflare Bot Challenge" (both $1.30);
2Captcha/SolveCaptcha/Anti-Captcha use one task type for the widget and need `data`+`pagedata`+`action` when the widget sits on a
`/cdn-cgi/challenge-platform` interstitial; YesCaptcha has a distinct "Cloudflare challenge page" doc page. A signup form on the site's
own page is the **widget** case → only sitekey + URL (+ action) needed.

### Exact payloads (copy-paste)

```http
POST https://api.capsolver.com/createTask            {"clientKey":"K","task":{"type":"AntiTurnstileTaskProxyLess",
  "websiteURL":"https://tokenharbor.ai/login?mode=signup","websiteKey":"0x4AAAAAADBuC8Knz1EJZx9-",
  "metadata":{"action":"signup"}}}
POST https://api.capsolver.com/getTaskResult         {"clientKey":"K","taskId":"..."}   → solution.token
```
```http
POST https://api.2captcha.com/createTask             {"clientKey":"K","task":{"type":"TurnstileTaskProxyless",
  "websiteURL":"...","websiteKey":"0x4...","action":"signup"}}
POST https://api.2captcha.com/getTaskResult          {"clientKey":"K","taskId":12345678} → solution.token
# legacy: POST https://2captcha.com/in.php  key,method=turnstile,sitekey,pageurl,action,json=1 → {"status":1,"request":"id"}
#         GET  https://2captcha.com/res.php?key=&action=get&id=&json=1 → {"status":1,"request":"<token>"}
```
```http
POST https://api.capmonster.cloud/createTask         {"clientKey":"K","task":{"type":"TurnstileTask",
  "websiteURL":"...","websiteKey":"0x4..."}}
POST https://api.capmonster.cloud/getTaskResult      {"clientKey":"K","taskId":407533072} → solution.token
```
```http
POST https://api.anti-captcha.com/createTask         {"clientKey":"K","task":{"type":"TurnstileTaskProxyless",
  "websiteURL":"...","websiteKey":"0x4...","action":"signup"}}
POST https://api.anti-captcha.com/getTaskResult      {"clientKey":"K","taskId":123} → solution.token
```
```http
POST https://api.yescaptcha.com/createTask           {"clientKey":"K","task":{"type":"TurnstileTaskProxyless",
  "websiteURL":"...","websiteKey":"0x4..."}}          # no action/cdata field exists
POST https://api.yescaptcha.com/getTaskResult        {"clientKey":"K","taskId":"..."} → solution.token
```
```http
POST https://api.nopecha.com/token                   {"key":"K","type":"turnstile","sitekey":"0x4...",
  "url":"...","data":{"action":"signup"}}            → {"data":"<jobid>"}
GET  https://api.nopecha.com/token?key=K&id=<jobid>  → {"data":"<token>"}
```
```http
POST https://api.solvecaptcha.com/in.php             key,method=turnstile,sitekey,pageurl,action,json=1
GET  https://api.solvecaptcha.com/res.php?key=&action=get&id=&json=1 → {"status":1,"request":"<token>","useragent":"..."}
```

## 2. Pricing (per 1 000 Turnstile tokens) — sources

- 2Captcha `$1.45` — https://2captcha.com/pricing (min $1: https://2captcha.com/for-customer)
- CapSolver `$1.20` — https://docs.capsolver.com/en/pricing/ (min ≈$6 reported, not on official page)
- CapMonster `$1.30`, 99 % — https://capmonster.cloud/en/prices/ and /en/cloudflare-turnstile/ ($0.10 test balance)
- Anti-Captcha `$2.00` — https://anti-captcha.com/price
- SolveCaptcha `$0.80` — https://solvecaptcha.com/pricing
- YesCaptcha 25 pts = ¥0.025 → ¥25/1 000 ≈ $3.73 @ ¥6.69/$ — https://docs.yescaptcha.com/en/tasks/turnstile/ + /en/account/recharge/
- NopeCHA $4.99/mo (2 000/day), 19.99/49.99 tiers — https://nopecha.com/pricing
- DeathByCaptcha `$2.89` — https://deathbycaptcha.com/api/turnstile
- CaptchaAI from $15/mo — https://captchaai.com/pricing
- SadCaptcha per-solve, TikTok/Shein only — https://www.sadcaptcha.com/

Indie "Turnstile-only" services advertising $0.075–$0.40/1 000 (nslsolver.com, peak.fo, solvegate.io, capsolver-alternative
SEO sites) were **not** verified: new domains, affiliate content, no independent track record, no public status page. Treat as
unproven; the advertised rate is below the human-labour floor, which usually means reused/stale tokens.

## 3. Recommendation for a few signups/day

Volume math: 5/day ≈ 150 tokens/month ≈ **$0.12–$0.22/month** of solving. Price is noise; **pass rate and min top-up dominate.**

1. **CapSolver** — best default. 3 s typical, accepts `metadata.action` (required here), proxyless or proxy-on, wide Turnstile
   variant coverage (managed/non-interactive/invisible). ~$6 entry is the only downside.
2. **2Captcha** — best *reliability* fallback (human workers, since 2014, huge capacity), $1 entry, `action`/`data` supported,
   both JSON and legacy endpoints. Slowest of the top three but the most forgiving on odd widgets.
3. **SolveCaptcha** — cheapest mainstream ($0.80) and 2Captcha-API-compatible; good if you want to keep one client and swap base URL.
4. **CapMonster Cloud** — $0.10 test balance makes it the cheapest way to *try*; 99 % claim; `action` undocumented (risk for a
   widget that renders with `action:"signup"`).
5. **Anti-Captcha** — $2 but very strong on stubborn/managed widgets; use as escalation when #1/#2 fail repeatedly.
6. **NopeCHA** — flat $4.99/mo only makes sense if you also need reCAPTCHA/other types; the Token API is slower by design.
7. **YesCaptcha** — skip: no action/cdata field, CNY-only billing, and at ¥25/1 000 it is now the most expensive AI service.
8. **DeathByCaptcha** — legacy, $2.89, username/password auth; only if you already have balance.

- **Cheapest viable:** SolveCaptcha ($0.80/1 000) — ~$0.12/mo at 5/day.
- **Best success rate:** CapSolver for speed/consistency, 2Captcha/Anti-Captcha when the widget is picky. Real answer: run 20
  solves on each (≈$0.03) against this exact sitekey and keep whichever returns tokens that the server action accepts.

## 4. Operational caveats specific to this target

- **Always send `action:"signup"`** if the provider supports it. Cloudflare's siteverify can compare the action; a token minted with
  the default/wrong action is rejected even though it looks valid.
- Token TTL ≈ 300 s, single use, bound to sitekey + hostname. Mint → submit in the same run; never cache.
- Proxyless tokens are minted from the solver's IPs. siteverify does not check IP, but the *signup POST* IP is scored by Cloudflare
  bot management — free/datacenter proxies already observed to yield no-token/`signup_rejected` on this site (README).
- Managed mode may render lazily (`sessionStorage.th_turnstile_rendered`), so the widget only exists after the client bundle runs.

## 5. Self-hosted solvers (local HTTP APIs)

| Repo | API | Schema | Notes |
|------|-----|--------|-------|
| `Theyka/Turnstile-Solver` (954★) | `GET /turnstile` then `GET /result` | `?url=&sitekey=&action=&cdata=` → `{"task_id":...}`; `?id=` → `{"elapsed_time":7.6,"value":"0.KBtT-r"}` | patchright browser (chromium/chrome/msedge/camoufox), port 5000, `--proxy` from proxies.txt, docker `theyka/turnstile_solver` |
| `BotsForge/CloudFlare` (54★) | **CapSolver-compatible**: `POST /createTask`, `POST /getTaskResult` | `{"clientKey":"x","task":{"type":"AntiTurnstileTaskProxyLess","websiteURL":"...","websiteKey":"0x4..."}}` → `{"taskId","status"}` → `{"solution":{"token"}}` | drop-in base-URL swap for CapSolver clients, port 5033 |
| `odell0111/turnstile_solver` (54★) | `GET /solve` (header `secret:`) | `{"site_url":"...","site_key":"0x4..."}` → `{"token":...}` | per-context proxies (`--proxies file`), docker, port 8088, ~2 s |
| `ZFC-Digital/cf-clearance-scraper` (740★) | `POST /cf-clearance-scraper` | `{"url":"...","siteKey":"0x4...","mode":"turnstile-min"\|"turnstile-max","proxy":{host,port,username,password},"authToken":...}` | also `waf-session`/`source` modes; docker `zfcsoftware/cf-clearance-scraper`, port 3000; **repo archived, no more updates** |
| `munew/cloudflare-turnstile-solver` | — | — | pure request-based Rust reverse, author states **out of date / not working** |

Self-hosting keeps everything as "HTTP from Python", but each of these runs a real browser (**patchright/Chrome**) inside the
solver container — forbidden on this machine per current constraint, so they'd need a separate box. For a few accounts/day a
hosted API is cheaper than a VPS and avoids the browser entirely.
