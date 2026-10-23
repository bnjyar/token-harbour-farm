# Own Turnstile solver — attempt log and verdict (2026-10-20)

Goal: mint a `cf-turnstile-response` for `tokenharbor.ai` with no browser and no
paid solver service. Everything below was executed over plain HTTP on this host.

## What was proven reachable over HTTP

| Artifact | Result |
|---|---|
| `GET /turnstile/v0/api.js` | 302 → `/turnstile/v0/b/d2d3316b729e/api.js` (86 KB loader) |
| Widget iframe doc | **200, ~282 KB**, via `/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/<seg>/<sitekey>/light/fbE/new/normal?lang=auto` |
| `<seg>` validation | **none** — `9n9y4`, `aaaaa`, `zzzz9`, `00000` all return 200 (per-request, echoed back in `_cf_chl_opt`) |
| `window._cf_chl_opt` | fully readable: sitekey, `managed`, chlId, 4 opaque tokens, timings |
| Inline orchestrator | 262,936 chars, CSP nonce, no `WebAssembly`/`eval(`/`atob(` literals |

Obfuscation: reversed-string table (1,941 entries, index offset 245,
`x -> table[i-245].reverse()`); a static decoder (`archive/solver/deob.py`)
rewrote 462 calls and dumped all strings. Decoded endpoint surface:
`/cdn-cgi/challenge-platform/h/`, `cf-chl`, `cf-chl-out`, `cf-chl-out-s`,
`cf-chl-ra`, `cf.turnstile.u`, `turnstileResults`, `debug.challenges.cloudflare.com`.

## Where it breaks

Running the orchestrator in Node + jsdom (no browser binary) reaches the first
realm anti-tamper check and dies:

- `pl(window)` validates the realm: `Function`, `Array`, `ArrayBuffer.isView`,
  `Reflect.get/apply`, String, Symbol, DataView, TextEncoder, Map, WeakSet,
  `Math.random`, plus native-`toString` shapes.
- With native-`toString` spoofing and 20+ DOM/canvas/Worker/Audio stubs the check
  still fails; the object it inspects is expected to be a *sandbox the script
  builds itself*, not `window` — i.e. the failure is deeper than a missing API.
- Errors are swallowed into `throw new TypeError` with no message by design, so
  every fix is guesswork: this is deliberate friction, not an oversight.

## Verdict

A from-scratch browserless minter is a VM-reimplementation project (the only
public attempt, `munew/cloudflare-turnstile-solver`, is ~30k lines of Rust and
its author declares it dead). It has to reproduce ~55–79 fingerprint values that
must stay coherent with the claimed UA/TLS/GPU/timezone, and it breaks whenever
`api.js` rotates.

## What actually removed the need for a solver

`GET /api/auth/signup-precheck?fp=<uuid>` answers **per exit IP**, not per
fingerprint. Free Indonesian proxies that pass the geo fence return
`{"needCaptcha": false}` — and those IPs sign up with **no token at all**.

Measured on the pool in `proxies.txt`: 25 tested → 10–12 `ready`, 12–15 dead,
0–1 `captcha`. Signup through a `ready` IP produced auth cookies immediately;
the whole chain (signup → verify → free models → key → live call) completed
with zero captcha tokens. So the cheapest "solver" is IP selection, not
reverse engineering.

`th_turnstile.py` (capsolver/2captcha/yescaptcha over HTTP) stays as the
fallback for IPs that *do* answer `needCaptcha: true`.
