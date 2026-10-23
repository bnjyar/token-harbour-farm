"""Static deobfuscator for the Turnstile challenge bundle.

Obfuscation observed (2026-10 build):
  table  : <backtick string with ';' separated entries>.split(`;`)
  decoder: function y(i){ i = i-245; s = table[i]; return reverse(s) }
  calls  : y(0x1f3) / a1(547) / a2(idx, off)

Transforms every numeric decoder call into the plain string literal, dumps the
decoded table, and leaves the rest of the code intact for beautifying.
"""
import json
import re
import sys
from pathlib import Path

src_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/god/.hermes/cache/scratch/chl_inline.js")
out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "/home/god/.hermes/cache/scratch/deob")
out_dir.mkdir(parents=True, exist_ok=True)
src = src_path.read_text()

# --- 1. locate the table: the last `<...>.split(`;`)` in the file
m = re.search(r"`([^`]{500,})`\.split\(`;`\)", src)
if not m:
    sys.exit("table not found")
table = m.group(1).split(";")
BASE = 245
words = [w[::-1] for w in table]
(out_dir / "strings.txt").write_text(
    "\n".join(f"{i:5d} {w}" for i, w in enumerate(words)))
print(f"table entries: {len(words)}  (base index {BASE})")


def decode(idx):
    j = idx - BASE
    if 0 <= j < len(words):
        return words[j]
    return None


# --- 2. rewrite numeric decoder calls
COUNT = {"hit": 0, "miss": 0}


def repl(mo):
    fn, a, b = mo.group(1), int(mo.group(2), 0), mo.group(3)
    if b is not None:
        a = a + int(b, 0)
    s = decode(a)
    if s is None:
        COUNT["miss"] += 1
        return mo.group(0)
    COUNT["hit"] += 1
    return json.dumps(s)


pat = re.compile(r"\b(y|a1|a2|ac)\((\s*0x[0-9a-fA-F]+|\s*\d+)\s*(?:,\s*(0x[0-9a-fA-F]+|\d+)\s*)?\)")
deob = pat.sub(repl, src)
print(f"rewrote {COUNT['hit']} calls, {COUNT['miss']} unresolved")
(out_dir / "chl_inline.deob.js").write_text(deob)

# --- 3. endpoint / API surface report
hits = {}
for kw in ["cf-chl", "/cdn-cgi", "orchestrate", "cmg", "turnstile", "WebGL", "canvas", "audio",
           "querySelector", "getContext", "navigator", "toString", "Worker", "fetch", "XMLHttpRequest",
           "sendBeacon", "postMessage", "performance", "crypto", "eval", "Function(", "atob"]:
    hits[kw] = deob.count(kw)
for k, v in sorted(hits.items(), key=lambda x: -x[1]):
    print(f"  {k:18} {v}")

# strings that look like endpoints
eps = sorted({w for w in words if re.search(r"(/cdn-cgi|https?://|cf-chl|chl_api|orchestrate|/fo/|/pat/|/ci/|cmg|turnstile)", w)})
print("\nendpoint-ish strings:")
for e in eps:
    print("  ", e[:160])
