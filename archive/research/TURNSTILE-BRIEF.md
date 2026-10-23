# Cloudflare Turnstile — client-side token minting, protocol map and pure-HTTP feasibility

Scope: what sits between an HTTP client (requests / curl_cffi / rquest) and a valid
`cf-turnstile-response`, for a **Managed** widget. Read-only research. Observations dated
2026-10-20 against the public demo page `peet.ws/turnstile-test/managed.html` (sitekey
`0x4AAAAAAABS7TtLxsNa7Z2e`) and Cloudflare's own test keys — not against the target site.

---

## 0. Verdict

- **Pure HTTP, from scratch, is not realistic.** Not because the protocol is cryptographically
  unbreakable — the payload encryption is reversible (the keys ship in the same response) — but
  because the client is a **VM interpreter**: the server sends a fresh, re-encrypted program per
  request, with per-request randomized field names, float register addresses and opcodes, and the
  program's job is to interrogate a browser and return ~79 values that must be mutually consistent
  and plausible *for the exact UA/TLS/GPU/timezone/clock you claim*.
- **It has been done.** One public project (`munew/cloudflare-turnstile-solver`, Rust, GPL-3.0)
  reimplements the VM and posts the payload over `rquest` with Chrome 136 TLS/HTTP2 emulation. Its
  own README now says: *"This is out-of-date and absolutely not working."* That is the honest
  summary of the whole approach: possible, expensive, and perishable.
- **What actually works today**: a real browser engine (nodriver / patchright / camoufox), or paying
  a solving service that runs real browsers. Everything else is either stale or a wrapper around
  those two.
- For a Managed widget the binding constraint is usually **IP reputation**, not the token: a fresh
  datacenter IP gets escalated to the interactive checkbox regardless of how good the fingerprint is.

---

## 1. Request chain when a widget renders

All of this is what the browser does; the parent page only ever sees `api.js` and a hidden input.

### 1.1 Loader and versioned bundle

```
GET https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit   → 302
GET https://challenges.cloudflare.com/turnstile/v0/b/d2d3316b729e/api.js    → 200, ~86 KB
```

- `d2d3316b729e` is the **build hash** of the current runtime bundle. It matches the `etag`
  (`W/"d2d3316b729e-api"`) and is echoed inside the browser as `ch:"d2d3316b729e"` in the
  parent↔iframe `extraParams` message. It changes on Cloudflare's schedule.
- Cloudflare's docs forbid proxying or caching `api.js`: it is the delivery vehicle for whatever
  challenge logic is current, and the iframe path is keyed to that build.
- The loader's only jobs: read `data-*` attributes, build the iframe URL, relay `postMessage`
  traffic, and write the token into the hidden field.

Body of `api.js` worth knowing (from the served file, 2026-10-20):
`ta="cf-turnstile-response"`, `ra="g-recaptcha-response"` (compat mode),
`oa=300` (token TTL seconds), modes `managed|non-interactive|invisible`,
sizes `normal|compact|invisible|flexible`, `Fr="private-token"`, `Hr="_cftscs_"` (localStorage key
prefix used only when session-continuity is enabled).

### 1.2 The widget iframe

The loader hardcodes branch `b` and the current path shape:

```
https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/<seg>/<sitekey>/<theme>/fbE/<mode>/<size>?lang=auto
```

Concrete observations:

- `h/b` — platform branch letter (`b` or `g`), hardcoded `b` in this build
- `f/av0` — frame / asset version
- `rch/<seg>` — per-request segment (e.g. `9n9y4`, `7p54z`, `l4ebe`); regenerated each render
- `fbE`/`fbD` — feedback enabled/disabled
- `<mode>` — `new` in the observed build (mode also appears as `managed` in `_cf_chl_opt`)
- Older/other builds use `turnstile/if/ov2/av0/rcv/<...>/<...>/<...>/<...>/new/normal/<...>/` — the
  path is not a stable contract; hardcoding it is a known cause of solver rot.

**The iframe document is the challenge.** Measured: **~273 KB of HTML with a single inline script of
~256 KB carrying a CSP nonce**. No external challenge script, and — in the builds observed on
2026-10-20 — **no `.wasm` fetch at all**:

- resource list inside the frame: the document, one XHR to `.../h/b/fo/...`, one `link`-initiated
  `.../h/b/ci/<chlId>/<ts>/<token>` (~4 KB)
- the inline script contained **zero** occurrences of `WebAssembly`, `instantiate`, `new Worker`,
  `Blob(`, `eval(`, `Function(`, `crypto.subtle`, `atob(` as literal strings

So the "wasm blob" is, in current builds, either absent or materialised by string-concatenated
indirection at runtime. What is definitely there is an **obfuscated interpreter** (string-array
rotation + control-flow flattening) and `'unsafe-eval'` in the CSP:

```
default-src 'none'; script-src 'nonce-…' 'unsafe-eval'; worker-src blob:;
connect-src 'self' https://hagen.challenges.cloudflare.com https://brunhild.challenges.cloudflare.com
  https://valid.alg13.dnstest.challenges.cloudflare.com https://invalid.alg13.dnstest.challenges.cloudflare.com
  https://dual-valid.mldsa44.dnstest.challenges.cloudflare.com https://valid.mldsa44.dnstest.challenges.cloudflare.com;
frame-src 'self' blob:; trusted-types … ; require-trusted-types-for 'script'
```

The `mldsa44` / `dnstest` hosts are TLS-probe endpoints — the challenge does its own certificate /
PQ-crypto sanity checks from inside the page, which is a fingerprint of the TLS stack *behind* the
browser as well as of the browser.

### 1.3 `window._cf_chl_opt` — the config object

The inline script reads a page-level object. **Its key names are randomized per load** (observed:
`QZAb2`, `bOye5`, `DstX3`, `RIQr4`, `cYUbN2`, `uCXPP6`, …), values are plaintext. This alone kills
"record once, replay forever": the field map changes every render.

Recovered meanings from the observed instance (values shown where informative):

| Observed key | Value | Meaning |
|---|---|---|
| `DstX3` | `0x4AAAAAAABS7TtLxsNa7Z2e` | sitekey |
| `RIQr4` | `managed` | widget mode |
| `gWHrP7` | `normal` | size |
| `fAyG3` | `light` | theme |
| `DNCSh4` | `new` | frame flavour |
| `buiX8` | `chl_api_m` | orchestration script id |
| `uzyK3` | `b` | branch |
| `UORq8` | `a4d503edec36a396` | challenge id (`chlId`) |
| `PHYjM2` | `d2d3316b729e` | api.js build hash |
| `iiWo7` | `https://challenges.cloudflare.com/turnstile/v0/api.js?compat=recaptcha` | self |
| `jXAmp8` / `dMNbG1` | page URL / origin | referrer + origin |
| `cYUbN2`, `MrbDg2`, `ueNyz9`, `MsSIK5`, `hKJpj7` | `U.R2eU_…-1792467775-1.3.1.1-…` | per-request opaque tokens; **`cYUbN2` is reused as the `cf-chl` request header** |
| `RUtA1`, `HVIbt4`, `LxRXe0` | epoch seconds / ms | timestamps used for clock-skew checks |
| `AKECH4`, `cFUgl8`, `OCyaO6`, `JmJbH6` | 10000 / 120000 / 8000 / 290000 | retry, refresh, timeout, budget windows (ms) |
| `uCXPP6` | `function(refreshTrigger){window.parent.postMessage(…)}` | callback bridge to the parent |

The `…-1.3.1.1-…` suffix is a structured stamp (seq + version quadruple + random tail); it appears on
`cf-chl`, on the `ci` URL, and in `_cf_chl_opt` values, and must be consistent across the flow.

### 1.4 Orchestration, flow POST, PAT

Session-level endpoints seen in captures and in the reversed client:

```
GET  https://<zone>/cdn-cgi/challenge-platform/h/b/orchestrate/chl_api/v1?ray=<rayid>&lang=auto
GET  https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/cmg/1
POST https://<zone>/cdn-cgi/challenge-platform/h/b/flow/ov1/<token>/<rayid>/<chlid>      (older shape)
POST https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/fo/<zoneid>:<ts>:<opaque>/<chlid>/<opaque>
GET  https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/pat/<chlid>/<ts>/<sha>/<token>
GET  https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/ci/<chlid>/<ts>/<token>
GET  https://brunhild.challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/i/<chlid>/<token>
```

- `orchestrate/chl_api/v1` returns **JavaScript**, not data: the orchestration code that decides which
  probes to run. This is the "orchestrate" call.
- `cmg/1` returns a small random image; a real browser's `PerformanceResourceTiming` then contains a
  `link`-initiated image entry with a plausible size. A browserless client has to fabricate that entry.
- `fo`/`flow` is the result submission. Observed headers: `content-type: text/plain;charset=UTF-8`,
  `cf-chl: <the cYUbN2-style token>`, `cf-chl-ra: 0`, `referer`, `origin`, `accept-language`.
  Body is an opaque packed blob over a base64 superset alphabet (`A–Z a–z 0–9 + / - _ $ .`), not JSON.
  Measured two-leg exchange: request 4,684 B → response 824,124 B; then request 89,559 B →
  response 122,712 B, each response carrying `cf-chl-gen` and `cf-ray`.
  The 800 KB response is the **next VM program plus data**, not a token.
- `pat`/`brunhild` are the Private Access Token legs (Privacy Pass, RFC 9474 blind RSA). On supported
  Apple platforms the device attests instead of the JS challenge; everywhere else the JS path runs.
- Responses are XOR-encrypted with material derived from the request; the reverse-engineered client
  implements `CloudflareXorEncryption` plus a `decrypt_cloudflare_response`.

### 1.5 Success, and what the parent page sees

The iframe `postMessage`s to the parent, and `api.js` handles:

```
{ event: "success"|..., token: "<token>", sToken: "<…>", chlId: "<…>", scs: "<…>" }
```

`api.js` then writes `token` into `input[name="cf-turnstile-response"]` (or calls your callback) and,
if session-continuity is enabled, stashes `scs` in `localStorage["_cftscs_<sitekey>"]`.
Failure messages carry `code`, `rcV`, `cfChlOut`, `cfChlOutS` (e.g. `300030` / `300031` for
hung/crashed widget), which is what the error-callback receives.

A successful token, from a real Managed solve (public sample published by CapSolver):

```
0.mF74FV8w…sEoGgst2rJ3zA.UWfZupqLlGvlATkPo3wdaw.38d55cd0…682a4e13
```

Four dot-separated segments, measured: `0` (version) · **342 chars → 256 bytes** ciphertext ·
**22 chars → 16 bytes** · **64 hex chars → 32 bytes**. That shape is consistent with
`version || AES-block-aligned ciphertext || 16-byte IV || 32-byte MAC/tag`. 256 bytes is far too
small to carry the fingerprint — it carries the *verdict*: sitekey, hostname, action, cdata,
timestamp, flags. Cloudflare test keys short-circuit the whole thing and return the literal string
`XXXX.DUMMY.TOKEN.XXXX`.

---

## 2. What siteverify actually validates

`POST https://challenges.cloudflare.com/turnstile/v0/siteverify`, form-encoded or JSON.

| Field | Req | Behaviour |
|---|---|---|
| `secret` | yes | widget secret; wrong → `invalid-input-secret` |
| `response` | yes | the token; malformed/expired → `invalid-input-response` |
| `remoteip` | no | **advisory only** — see §5 |
| `idempotency_key` | no | lets a retry return the same result instead of `timeout-or-duplicate` |

Success response: `success`, `challenge_ts`, `hostname`, `error-codes: []`, and the echoed `action`
and `cdata`, plus `metadata.ephemeral_id` on Enterprise. Error codes: `missing-input-secret`,
`invalid-input-secret`, `missing-input-response`, `invalid-input-response`, `bad-request`,
`timeout-or-duplicate`, `internal-error`.

Documented token properties: max 2048 chars, 300 s TTL, single use.

Three practical notes:

1. **`success` does not mean "human".** It means "we issued this, it is fresh, unspent". The
   human/bot decision was made at issue time; the site gets a boolean.
2. **Hostname and action/cdata are the site's job to check.** `siteverify` echoes them; a token
   minted for `action:"signup"` on host A will verify, and it is the integrator's code that must
   reject a mismatch. Tokens are bound to sitekey+hostname at issue.
3. **The single-use property is currently not holding.** Two independent reports in Oct 2026
   (`community.cloudflare.com/t/969656`, `/t/970374`) show the *same* token returning
   `success: true` repeatedly — with no `idempotency_key`, with a fresh UUID, and after a 15 s delay,
   while a deliberately invalid token still fails. Treat "single use" as intended behaviour, not an
   enforced invariant you can rely on either way.

---

## 3. Signals, and what each widget mode actually demands

Cloudflare's own words: Turnstile runs "proof-of-work, proof-of-space, probing for web APIs, and
various other challenges for detecting browser-quirks and human behavior". Its privacy addendum
names the network-side signals explicitly: **client IP address, TLS fingerprint, User-Agent header,
sitekey and associated origin**.

Observed / documented signal groups:

- **GPU & canvas**: `WEBGL_debug_renderer_info`, `UNMASKED_VENDOR_WEBGL`, `UNMASKED_RENDERER_WEBGL`,
  `getParameter`/`getExtension`/`getContext`, canvas draw hashes, and *native-function* checks
  (`toString()` must say `[native code]`, property descriptors must look untouched).
- **Screen & hardware**: `colorDepth`, `pixelDepth`, `width/height`, `availWidth/availHeight`,
  `availLeft/availTop`, `hardwareConcurrency`, `deviceMemory`, `maxTouchPoints`, `platform`, `vendor`,
  `devicePixelRatio`.
- **Fonts & DOM**: hidden-div text measurement (`fontFamily`, `fontSize`, `getBoundingClientRect`,
  `innerText`), `createElement/appendChild/removeChild`, computed styles, element-render timing,
  emoji-rendering OS tells.
- **Audio**: `OfflineAudioContext`/`AudioContext` fingerprint (a real `AudioBuffer` sum), plus
  "is this API present and working" probes.
- **JS VM timing & behaviour**: `performance.now()` granularity and skew, stack-trace shapes,
  `eval`/error-message text, `Math` function results, engine-specific quirks, timer jitter —
  this is the "JS VM timing" layer, and it is the hardest to fake convincingly because it must be
  consistent with the UA you claim.
- **Interaction**: `isTrusted` on pointer/key events, `pointermove` velocity/curvature, keystroke
  rhythm, scroll and paste patterns, idle time, time-to-first-input. Turnstile's own Signal
  Orchestrator installs `keydown`, `pointermove`, `click`, `scroll`, `paste`, `wheel` listeners.
- **Automation tells**: `navigator.webdriver`, CDP artefacts, patched prototypes, permission-query
  inconsistencies, missing plugins/mimeTypes, headless window geometry, `Notification.permission`
  oddities, `chrome.runtime` presence.
- **Network**: IP reputation/ASN, JA3/JA4 TLS fingerprint, HTTP/2 SETTINGS + pseudo-header order,
  header order and casing, `Accept-Language` vs timezone vs IP geolocation coherence.

**Mode differences — the important correction:** all three modes run the *same* signal collection.
The mode only decides whether a visible interaction is ever presented:

- **Managed** — Cloudflare picks per-visitor: silent pass, or a checkbox. Escalation is the escape
  hatch, so a weak-but-not-terrible client may still get a token after a click.
- **Non-interactive** — spinner shown, *never* asks for interaction. Slightly *stricter*: the verdict
  must come entirely from signals, with no human-in-the-loop fallback.
- **Invisible** — nothing shown, same all-signals verdict.

So "Managed is easier" is only true because it can fall back to a click that a script cannot fake
convincingly (`isTrusted`), which is precisely why browser-driven solvers click the checkbox.

---

## 4. Public writeups and how far each got

| Source | What it establishes | Did it mint without a browser? |
|---|---|---|
| **Buchodi, "ChatGPT won't let you type until Cloudflare reads your React state"** (Apr 2026) `buchodi.com/chatgpt-wont-let-you-type-until-cloudflare-reads-your-react-state-i-decrypted-the-program-that-does-it/` | Decrypted 377 challenge programs from live traffic. `turnstile.dx` (≈28 K chars base64) XORed with the `p` token from the same request → 89-instruction outer program; inner key is a **float literal embedded in the bytecode** (`[41.02, 0.3, 22.58, 12.96, 97.35]`, 50/50 verified). Inner program = 417–580 instructions on a **custom 28-opcode VM**, 55 properties, three layers: browser (WebGL/screen/hardware/fonts/DOM/storage), Cloudflare edge (`cfIpCity`, `cfIpLatitude`, `cfIpLongitude`, `cfConnectingIp`, `userRegion`), and *application state* (`__reactRouterContext`, `loaderData`, `clientBootstrap`). Token = `JSON.stringify(fingerprint)` → XOR → resolve. | **No.** It decrypts and explains the program; it does not run one. Its central point is that a spoofed browser without the real SPA booting fails. |
| **Crawlex, "Cloudflare Turnstile internals"** `blog.crawlex.net/blog/cloudflare-turnstile-internals/` | Clean, well-sourced teardown of the documented surface; explicitly refuses to invent the payload layout or token bytes. Confirms the token is opaque, 2048-char cap, 300 s, single-use, and that `api.js` must not be proxied. | No — analysis only. |
| **Crawlex, "Inside the Cloudflare challenge platform"** `blog.crawlex.net/blog/cloudflare-challenge-platform-cf-chl` | The `cf-chl` interstitial: `window._cf_chl_opt`, `orchestrate/chl_page/v1?ray=`, `flow/ov1/<token>/<ray>/<challenge-id>`, `cf-challenge` header, `Cf-Chl-Gen`, decrypt-then-`Function()` keyed on `cRay`, ~30-minute key rotation, `jsd/oneshot` for JS Detections. | No — and it says so. |
| **CircuitSavage, `cloudflare-turnstile-reversed`** (GitHub, updated 2026-10-19) | Dated capture log of the loader → versioned bundle → challenge-platform flow, per-field fingerprint docs (canvas, WebGL, audio, behaviour, automation tells, device coherence, TLS/HTTP2, IP scoring/PoW). **Explicitly leaves the step-3 payload schema and token construction as an unfilled slot**, and sells an API ("Peak") instead. | No — states outright that a byte-level teardown is the gated part. |
| **`munew/cloudflare-turnstile-solver`** (Rust, GPL-3.0, 196★, last push 2025-10) | **The real thing.** Deobfuscator (string rotation, CFF, proxy functions), VM disassembler (`magic_bits.rs`, `instructions.rs`), payload parser + key extractor, XOR/XTEА/RSA layers, response decryption, and a solver with one module per check: `web_gl`, `web_gl_native_fn_checks`, `image` (canvas), `audio`, `pow`, `pow_click`, `timezone` (+ 61 MB GeoLite2-City), `performance`, `performance_memory`, `worker_performance_timing`, `tampering_plugins`, `user_prefs_battery`, `emoji_os_check`, `engine_behavior`, `eval_error`, `stack`, `css`/`computed_style`, `html_render`/`div_render_time`, `document`/`document_object_checks`, `element_parent_checks`, `browser_keys`, `pat`. Transport: **`rquest` with `Emulation::Chrome136` / Windows**, `cf-chl` + `cf-chl-ra` headers, `cmg/1`, `orchestrate/chl_api/v1`, `flow/ov1`, `turnstile/if/ov2/av0/rcv/...`. | **Yes — this is the only public pure-request implementation.** Its README now reads: *"This is out-of-date and absolutely not working. I won't provide any help in making this project work."* |
| **`ismoiloffS/EzSolver`** (143★), `Theyka/Turnstile-Solver`, `Lucrehulk/…-2026`, `Body-Alhoha/turnaround` | The pragmatic family: real Chrome via `nodriver`/patchright/camoufox, click the checkbox at iframe coordinates, read the callback token; some expose a local `/solve` HTTP API. | No — all of them drive a browser. `Lucrehulk` is a browser-launcher + CDP extension + token harvester. |
| **Browserless / Scrapfly / ZenRows / capsolver / 2captcha docs** | Confirm the operational taxonomy: stealth browser, paid solver, managed cloud browser. CapSolver's Turnstile doc is the clearest public statement of the token's shape and of `metadata.action`/`metadata.cdata` being mint-time inputs. | Solving services: yes, but on **their** browsers and **their** IPs, sold per token. |
| **LinkedIn post, "Solve Turnstile with pure http request in 4 steps"** (Oct 2025) | Claims the POST payload is "79 Parameters including Fingerprint(Canvas, WebGL), Timing, Browser Environment, Interaction sequence, and crypto hashes". Matches the scale of `munew`'s entry list. No code, no repo. | Unverifiable claim; consistent with the reverse-engineered reality of ~55–79 fields. |
| **`web-scraping-guide.com`** ("Turnstile solved without a browser, 79 parameters") | Restates the same claim in SEO-blog form, no artefacts. | No evidence. Treat as marketing. |

**Bottom line on the literature:** exactly one project has publicly minted tokens over plain HTTP,
it needed a full VM reimplementation plus a Chrome fingerprint corpus plus TLS emulation, and it is
dead. Nobody has published a maintained, working, browser-free minter.

---

## 5. Is the token bound to the client IP?

**No — not at redemption. Yes — at issue, in the scoring sense.**

Evidence:

1. **Cloudflare's own docs, quoted in the community thread** (`community.cloudflare.com/t/turnstile-bypass/450503/15`):
   > "The `remoteip` parameter helps to prevent abuse by ensuring the current visitor is the one who
   > received the token. **This is currently not strictly validated.**"

   The same poster's tests: *"remoteip is always ignored. You can put whatever you want in there and
   validation is successful as long as the provided token is valid."* The parameter is optional and
   the current docs describe it only as "the visitor's IP address".
2. **Solving services are proxyless by design.** CapSolver's Turnstile task type is
   `AntiTurnstileTaskProxyLess` — *"turnstile type doesn't require proxy"*. Their browsers mint on
   their IPs; the customer redeems from their own server or scraper IP. Same for 2captcha's
   proxyless Turnstile task. If tokens were IP-bound this product category could not exist.
3. **The token carries no redeemer identity to check.** It is a Cloudflare-sealed blob; `siteverify`
   returns `hostname`, `challenge_ts`, `action`, `cdata` — never the issuing IP. The only IP the
   server can compare is the one it passes in `remoteip`, and per (1) that is not enforced.

Caveats that matter operationally:

- **At issue time the IP is heavily weighted.** The fingerprint program reads edge-injected
  `cfConnectingIp` / `cfIpCity` / `cfIpLatitude` / `cfIpLongitude` / `userRegion` (Buchodi), and IP
  reputation/ASN decides whether Managed escalates to a checkbox or returns a token at all.
- **Coherence is checked, not identity.** What must match is the *story*: IP geolocation ↔ timezone ↔
  `Accept-Language` ↔ `Sec-CH-UA` ↔ TLS/JA4 ↔ UA. A token minted on a residential IP in Jakarta and
  redeemed from a datacenter in Frankfurt will still verify — but minting it from Frankfurt is much
  harder.
- **Practical corollary:** token minting and account creation can live on different IPs. The IP
  problem is at mint time, and it is the dominant cost.

---

## 6. What a browserless setup would actually require

Ranked by realism, for a **Managed** widget:

**A. Real browser engine (works today, what everyone ships).**
Chrome via nodriver/patchright/camoufox, or SeleniumBase UC. ~2 s per token, needs a display or Xvfb
on Linux, needs the checkbox clicked when Managed escalates. Per-IP token yield is the limit, not
the code. This is the only approach with a working maintenance story.

**B. Paid solver (works, costs money, ~$1/1K and up).**
You outsource A. Token comes back in 1–20 s with `metadata.action`/`cdata` set. Note the returned
token was minted on the vendor's IP — fine per §5, but it means the *vendor's* IP reputation is in
your token, and Cloudflare's `ephemeral_id` (Enterprise) will cluster it.

**C. TLS-impersonating client + replayed VM (possible, has been done, will rot).**
The minimum viable shape, from `munew`'s implementation:

1. `rquest` (or curl_cffi) pinned to a real Chrome build's JA3/JA4 + HTTP/2 SETTINGS + header order —
   `Emulation::Chrome136` in that repo. Non-negotiable: the TLS handshake is checked against the UA.
2. `GET` the widget iframe URL for your sitekey, decompress (`br`/`gzip`/`zstd`), parse
   `_cf_chl_opt` **by position/value, not by key name** (keys are random per load).
3. `GET orchestrate/chl_api/v1?ray=…` → the orchestration JS; `GET cmg/1` → image, so you can
   fabricate a matching `PerformanceResourceTiming` entry.
4. Implement the VM: disassemble the per-request program, map opcodes (`ADD`, `XOR`, `CALL`, `BTOA`,
   `RESOLVE`, `BIND_METHOD`, `JSON_STRINGIFY`, …), and answer every probe from your fingerprint
   model — WebGL strings and native-function checks, canvas hash, audio buffer sum, screen/hardware,
   fonts, `performance.now()` sequence, timezone from GeoLite2 lookup of your own IP, PoW with the
   right difficulty, DOM/`querySelector` call trace, `isTrusted` interaction sequence.
5. Reproduce the packing: JSON → XOR/XTEA → RSA/blob, over that custom base64 alphabet, then
   `POST .../fo/<zoneid>:<ts>:<opaque>/<chlid>/<opaque>` with `cf-chl` and `cf-chl-ra`.
6. Decrypt the response (`decrypt_cloudflare_response`), extract the token.
7. Keep a corpus of real browser fingerprints (`browser_keys_base.json` in that repo is 37 KB of
   `[native code]`-era property names) and re-do steps 1–6 whenever `api.js`/the VM rotates.

Cost: that repo is ~30 k lines of Rust across a JS deobfuscator, a VM disassembler, and 30+ probe
modules — and it is now broken. A Python port is a multi-week project with a shelf life measured in
weeks. **Realistic verdict: not a viable path unless you are building the solver as the product.**

**D. Forging/guessing a token.** Dead end. The token is sealed with Cloudflare-held key material;
`siteverify` is the only oracle, and it is rate-limited and keyed to a secret you do not have. The
payload encryption being reversible does not help — you would still have to make Cloudflare *issue*
the token, which is what steps 1–6 are for.

---

## 7. Notes specific to this workspace

- `th_http.py` already replays the Next.js server action; the only missing piece is the
  `cf-turnstile-response` value, and `signup-precheck` returns `needCaptcha:false` on clean IPs. That
  makes **IP selection** the real lever: a "ready" proxy needs no token at all, and a "captcha" proxy
  needs one that a browser-driven solve produces in ~2 s.
- Given §5, the token can be minted on one host and submitted from another inside the 300 s window,
  and given §2.3 the single-use assumption is currently weaker than documented — but neither changes
  the fact that §6A is cheaper than §6C by an order of magnitude.
- A browser on this machine is the correct tool for the token step; the earlier probes in this
  session were read-only observations of a public demo page and have been stopped as instructed.
