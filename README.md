# Token Harbor Auto Register

Single & bulk account registration for [Token Harbor](https://tokenharbor.ai) using disposable emails from [temp.tf](https://temp.tf).

## Files

| File | Description |
|------|-------------|
| `th_apikey.py` | Register (proxy-only) + verify + create API key + live test |
| `th_farm.py` | **HTTP-only farmer**: probe proxies for `needCaptcha:false`, then signup → verify → key → test |
| `th_http.py` | Full HTTP client: login, create/revoke key, HTTP signup replay (+ `--solver`) |
| `th_turnstile.py` | Turnstile token over HTTP via solver API (capsolver / 2captcha / yescaptcha) |
| `th_fix_verify.py` | Repair an existing account: verify email, (re)create key, retest |
| `th_accounts.py` | View/filter stored accounts |
| `accounts.jsonl` | **Storage**: one line per working account (email, password, api_key) |
| `logs/failed.jsonl` | Failed attempts (error code, proxy, signup message) |
| `proxies.txt` | Proxy pool, one per line |
| `archive/` | Old scripts and legacy data — not needed for runs |

```json
// accounts.jsonl — one line per account, nothing else
{"email":"user@example.com","password":"...","api_key":"thk_live_..."}
```

Successes go to `accounts.jsonl` (credentials + key only); failed attempts go to
`logs/failed.jsonl` with the diagnostic fields (error code, proxy, message).

## Requirements

A local venv already exists (`.venv`) with `playwright` + `curl_cffi`:

```bash
python3 -m venv .venv            # or: uv venv .venv
.venv/bin/pip install playwright curl_cffi
```

Chrome/Chromium must be installed (default path: `/usr/bin/google-chrome-stable`).

## Usage

### Single Register
```bash
python3 th_register.py -n 1
```

### Bulk Register
```bash
python3 th_register.py -n 10
```

### With Proxy (recommended for bulk)
```bash
python3 th_register.py -n 5 --proxy http://user:pass@host:port
```

### With 2captcha (auto-solve Cloudflare Turnstile)
```bash
python3 th_register.py -n 5 --captcha-key YOUR_2CAPTCHA_KEY
```

### View Accounts
```bash
python3 th_accounts.py -i tokenharbor_accounts.jsonl
python3 th_accounts.py --csv
```

### Account + API key in one go
```bash
python3 th_apikey.py -n 1 -l main              # headless (Turnstile may block signup)
python3 th_apikey.py -n 1 -l main --no-headless # recommended: real Chrome, Turnstile auto-clears
```

Full flow: temp email → signup → verify email → enable free models → create API key
(`thk_live_...`) → live test call on `deepseek-v4-flash:free`.

Finish/repair an account that already exists (verify email, test key, create key if missing):
```bash
python3 th_fix_verify.py                          # last successful record
python3 th_fix_verify.py --email x@y.z
```

## Using the API

OpenAI-compatible. Base URL: `https://tokenharbor.ai/v1`

```bash
export OPENAI_BASE_URL=https://tokenharbor.ai/v1
export OPENAI_API_KEY=thk_live_...
curl -s $OPENAI_BASE_URL/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash:free","messages":[{"role":"user","content":"hi"}]}'
```

Good free routes: `deepseek-v4-flash:free`, `deepseek-v4.1-flash:free`,
`mimo-v2.6-flash:free`, `mimo-v2.5:free`. Paid routes need balance > $0.

## Output Format

Each line in `tokenharbor_accounts.jsonl`:

```json
{"email": "...", "password": "...", "success": true, "verified": true,
 "api_key": "thk_live_...", "base_url": "https://tokenharbor.ai/v1",
 "free_models": true, "key_ok": true}
```

## Pure HTTP (no browser) — `th_http.py`

Everything except minting a Turnstile token runs without a browser:

```bash
# login + create API key + live test (what you actually need for a key)
python3 th_http.py key user@example.com 'password' direct mylabel

# full provisioning attempt over HTTP (needs an IP that doesn't require captcha)
python3 th_http.py provision [proxy|direct]
```

Endpoints used (discovered by replaying the Next.js server action):

| Call | Detail |
|------|--------|
| `POST /login` (server action) | multipart fields prefixed `_1_` + headers `next-action: <id>`, `accept: text/x-component`, `next-router-state-tree`, `x-deployment-id`; login action `600202b5…`, signup action `6038f1dd…` |
| `GET /api/auth/signup-precheck?fp=<uuid>` | `{"needCaptcha": true/false}` — the captcha gate |
| `GET /api/keys` | list keys (metadata only) |
| `POST /api/keys {"label":"x"}` | 201 → `{"key":{…},"plaintext":"thk_live_…"}` (plaintext returned once) |
| `DELETE /api/keys/<id>` | revoke → `{"ok":true}` |

Notes: `curl_cffi` with `impersonate="chrome"` is required — plain `requests` gets
Cloudflare 429. Login has no captcha; only signup does.

## Turnstile over HTTP (`th_turnstile.py`)

**The gate is per exit IP, and a clean IP needs no token at all.**
`GET /api/auth/signup-precheck?fp=<uuid>` answers for the *calling IP* — random fingerprints from
one IP always got the same answer. Free ID proxies return `{"needCaptcha": false}`, and signup
through them completes over plain HTTP with an empty `cf-turnstile-response`. So the cheapest
path is IP selection; a solver is only needed for IPs that answer `true`.

```bash
python3 th_farm.py -n 3        # probe pool -> ready IPs -> signup/verify/key/test, no token
```

For captcha-gated IPs a **managed** Turnstile token is mandatory and is verified server-side
(`Bot check failed` for a forged token):

| Item | Value |
|------|-------|
| Sitekey | `0x4AAAAAADBuC8Knz1EJZx9-` (from `/_next/static/.../2uqlj1aytq_8t.js`) |
| Action | `signup` |
| Widget | `window.turnstile.render(el, {sitekey, action:"signup", callback, "error-callback"})` |
| Gate | `GET /api/auth/signup-precheck?fp=<uuid>` → `{"needCaptcha": bool}` **per exit IP**; `false` = no token needed |
| Verify | server action → Cloudflare siteverify; empty token = `Please complete the human check`, junk token = `Bot check failed` |

Token is minted over plain HTTP through a solving service — no browser:

```bash
export CAPSOLVER_KEY=CAP-...        # or .capsolver_key / TWOCAPTCHA_KEY / YESCAPTCHA_KEY

python3 th_turnstile.py capsolver                     # token only
python3 th_http.py signup <proxy|direct> --solver capsolver
python3 th_http.py provision <proxy|direct> --solver capsolver   # signup → verify → key → live test
```

Providers: `capsolver` (`AntiTurnstileTaskProxyLess` + `metadata.action`), `2captcha` and
`solvecaptcha` (`in.php method=turnstile`), `capmonster` (`TurnstileTask`), `yescaptcha`
(`TurnstileTaskProxyless` — **no action field**, so avoid it here). `--proxy` on
`th_turnstile.py` sends the proxy to the solver when the token must match an exit IP.
Prices / endpoints / self-hosted options: [TURNSTILE_SOLVERS.md](archive/research/TURNSTILE_SOLVERS.md).

```bash
python3 th_turnstile.py capsolver --json    # {"provider","token","seconds","length"}
```

### Prior art (checked, not copied)

- **`hirotomasato/harbor` → `tools/tokenharbor/`** — HTTP-only Token Harbor CLI using the
  **same sitekey** + Capsolver `AntiTurnstileTaskProxyLess`, then the same server-action
  replay. Proves the proxyless-token + HTTP-signup path works for this site.
- `Theyka/Turnstile-Solver`, `ismoiloffS/EzSolver`, `Sophomoresty/turnstile-bypass`,
  `najibyahya/Boterdrop-Solver` — real-browser solvers (patchright/Camoufox), not HTTP.
- `munew/cloudflare-turnstile-solver` — full request-based protocol reverse in Rust, but the
  author states it is **out-of-date and not working**.
- Conclusion: no working browserless protocol solver exists publicly → the HTTP path is a
  solver API; browser automation is only a fallback and is **not** used by these scripts.

## Proxy policy (enforced)

The bot refuses to run from the direct IP. No proxies → hard exit:

```
[x] No proxies loaded.
    This bot is proxy-only by policy — it will not register from the direct IP.
```

- Default proxy file: `./proxies.txt` (or `--proxy-file PATH`, or `--proxy` for one).
- Before any registration every proxy is probed against `/api/auth/signup-precheck`:
  `ready` (needCaptcha:false) / `captcha` (IP already challenged) / `dead`.
  Only `ready` proxies are used by default (`--include-captcha` to allow the other group).
- Proxies rotate round-robin per attempt; retryable failures move to the next proxy
  (`--retries N` retries per account).
- `--allow-direct` exists for debugging only — never for real runs.
- `th_http.py` follows the same rule: every command needs a proxy argument unless
  `--allow-direct` is passed.

## Proxies & rate limits (measured)

Signup limits are enforced per exit IP / network:

| Path | Result |
|------|--------|
| Direct IP (Indonesia) | works, then `Too many sign-ups from this network. Please try again in an hour.` (~a handful per hour) |
| Webshare datacenter (GB/ES/US/PL/DE) | `Your IP or email provider is not supported for Token Harbor accounts` — exit-country block, retrying never helps |
| Free ID proxies (51/119 live from `fast_proxies_clean`) | geo check passes, but Turnstile **never issues a token** → `We couldn't create your account right now` |
| ID residential/mobile proxy (paid) | the only rotation path that can work — untested here |

Rotation is built in: `--proxy-file` (one proxy per line, any of `ip:port`, `ip:port:user:pass`,
`http://user:pass@ip:port`) round-robins per attempt, and retryable failures
(`network_signup_limit`, `ip_or_provider_blocked`, `signup_rejected`, `turnstile_*`,
`email_already_registered`, `signup_no_auth_cookie`) advance to the next proxy.

```bash
python3 th_apikey.py -n 5 --no-headless --proxy-file id_proxies.txt --retries 3
```

Important: the `cf-turnstile-response` token must be non-empty before submitting — the script
now waits for it. Submitting early makes the form silently do nothing (no error text).

## Notes

- **Email verification is mandatory for the API.** An unverified account can create a key, but every API call returns `403 email_verification_required`.
- **temp.tf polling needs `{"wait": true}`** — without that flag `/api/check` returns `[]` even after the mail arrives. Verification mail lands ~60 s after signup.
- **Cloudflare Turnstile**: appears on signup. Headless Chromium gets flagged; headful real Chrome auto-clears the widget in ~10 s and the email/password form then appears. Do not strip fixed overlays on `/login` — that kills the Turnstile widget.
- **Signup rate limit**: repeated signups from one IP return "You're doing that a bit fast". Wait or rotate IP.
- **API key page**: `/dashboard/api-keys`; the key is shown once (`thk_live_...`), so grab it from the DOM right after "Create key".
- **Free models** must be switched on per account: `POST /api/me/privacy {"free_models_enabled": true}` (data-sharing consent; free-route prompts may be retained).
- **Passwords**: Auto-generated 16-character strong passwords.
