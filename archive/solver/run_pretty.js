// Runs the *deobfuscated* challenge script in jsdom so stack traces point at
// readable lines. Prints each uncaught error with the offending source line.
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const htmlPath = process.argv[2];
const prettyPath = process.argv[3];
const iframeUrl = process.argv[4] ||
  "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/9n9y4/0x4AAAAAADBuC8Knz1EJZx9-/light/fbE/new/normal?lang=auto";

const html = fs.readFileSync(htmlPath, "utf8");
const pretty = fs.readFileSync(prettyPath, "utf8");
const prettyLines = pretty.split("\n");

// swap the single inline script for the deobfuscated one
const patched = html.replace(/<script([^>]*)>[\s\S]*?<\/script>/,
  (_m, attrs) => `<script${attrs}>\ntry{\n${pretty}\n}catch(e){console.error("SCRIPT_THROW", e && e.message, e && (e.stack||"").split("\\n").slice(0,8).join(" << "))}\n</script>`);

const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => {
  const msg = String(e.message || e);
  const st = (e.stack || "").split("\n");
  errors.push({ msg, st });
});
vc.on("log", (...a) => console.log("[page.log]", ...a.map(x=>String(x).slice(0,600))));
vc.on("error", (...a) => console.log("[console.error]", ...a.map(x=>String(x).slice(0,300))));

const dom = new JSDOM(patched, {
  url: iframeUrl,
  referrer: "https://tokenharbor.ai/",
  runScripts: "dangerously",
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(win) {
    Object.defineProperty(win.navigator, "webdriver", { get: () => undefined });
    win.chrome = { runtime: {}, app: { isInstalled: false } };
    const seen = new Set();
    const rec = (k) => { if (!seen.has(k)) { seen.add(k); } };
    win.__logAccess = rec;
  },
});

setTimeout(() => {
  console.log("=== errors:", errors.length);
  const uniq = new Map();
  for (const e of errors) {
    const key = e.msg.slice(0, 120);
    if (uniq.has(key)) continue;
    uniq.set(key, e);
    console.log("\n---", e.msg.slice(0, 300));
    for (const line of e.st.slice(0, 6)) console.log("   ", line.trim().slice(0, 200));
    // try to locate a pretty line from the stack
    const m = e.st.join("\n").match(/eval at .*?:(\d+):(\d+)/) || e.st.join("\n").match(/at .*?:(\d+):(\d+)/);
    if (m) {
      const ln = parseInt(m[1], 10);
      if (ln > 0 && ln <= prettyLines.length) {
        console.log("    SRC>", prettyLines.slice(Math.max(0, ln - 2), ln + 1).join(" ").trim().slice(0, 400));
      }
    }
    if (uniq.size >= 8) break;
  }
  process.exit(0);
}, 12000);
