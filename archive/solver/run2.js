// Runs the deobfuscated challenge script with the shim layer and reports the
// first failures + every outbound request. This is the iteration harness.
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const { installShims } = require("./shims");

const htmlPath = process.argv[2];
const prettyPath = process.argv[3];
const iframeUrl = process.argv[4] ||
  "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/9n9y4/0x4AAAAAADBuC8Knz1EJZx9-/light/fbE/new/normal?lang=auto";

const html = fs.readFileSync(htmlPath, "utf8");
const pretty = fs.readFileSync(prettyPath, "utf8");
const prettyLines = pretty.split("\n");
const patched = html.replace(/<script([^>]*)>[\s\S]*?<\/script>/,
  (_m, attrs) => `<script${attrs}>\ntry{\n${pretty}\n}catch(e){console.error("SCRIPT_THROW", e && e.message, e && (e.stack||"").split("\\n").slice(0,6).join(" << "))}\n</script>`);

const errors = [];
const net = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => errors.push(String(e.message || e) + " :: " + (e.stack || "").split("\n")[1]));
vc.on("log", (...a) => console.log("[page]", ...a.map((x) => String(x).slice(0, 400))));
vc.on("error", (...a) => console.log("[page.err]", ...a.map((x) => String(x).slice(0, 400))));

function glStub() {
  const P = { 37445: "Google Inc. (NVIDIA)", 37446: "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)", 7936: "WebKit", 7937: "WebKit WebGL", 7938: "WebGL 1.0 (OpenGL ES 2.0 Chromium)", 35724: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)" };
  const E = { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446, WEBGL_debug_renderer_info: true };
  return {
    getParameter: (p) => P[p] ?? 8192, getExtension: (n) => (E[n] ? E : null), getSupportedExtensions: () => ["WEBGL_debug_renderer_info"],
    getShaderPrecisionFormat: () => ({ rangeMin: 127, rangeMax: 127, precision: 23, precisionLow: 23 }),
    getContextAttributes: () => ({ alpha: true, antialias: true, depth: true, stencil: false, premultipliedAlpha: true, preserveDrawingBuffer: false, powerPreference: "default" }),
    drawingBufferWidth: 300, drawingBufferHeight: 150, readPixels() {}, clearColor() {}, enable() {}, disable() {}, clear() {},
    createBuffer: () => ({}), bindBuffer() {}, bufferData() {}, createProgram: () => ({}), createShader: () => ({}),
    shaderSource() {}, compileShader() {}, attachShader() {}, linkProgram() {}, useProgram() {},
    getProgramParameter: () => true, getShaderParameter: () => true, getAttribLocation: () => 0, getUniformLocation: () => ({}),
    vertexAttribPointer() {}, enableVertexAttribArray() {}, uniformMatrix4fv() {}, drawArrays() {}, viewport() {},
    getError: () => 0, isContextLost: () => false,
  };
}

const dom = new JSDOM(patched, {
  url: iframeUrl, referrer: "https://tokenharbor.ai/",
  runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
  beforeParse(win) {
    win.__glStub = glStub;
    installShims(win);

    const XHR = win.XMLHttpRequest;
    const open = XHR.prototype.open, send = XHR.prototype.send;
    XHR.prototype.open = function (m, u, ...r) { this.__m = m; this.__u = String(u); return open.call(this, m, u, ...r); };
    XHR.prototype.send = function (b) {
      net.push({ m: this.__m, u: this.__u, len: b ? String(b).length : 0 });
      console.log("[net]", this.__m, this.__u.slice(0, 140), "len=" + (b ? String(b).length : 0));
      this.addEventListener("loadend", () => console.log("[net<]", this.status, "resp=" + (this.responseText || "").length));
      return send.call(this, b);
    };
    win.fetch = (u, o = {}) => {
      net.push({ u: String(u), len: o.body ? String(o.body).length : 0 });
      console.log("[fetch]", String(u).slice(0, 140), "len=" + (o.body ? String(o.body).length : 0));
      return Promise.reject(new Error("blocked"));
    };
  },
});

setTimeout(() => {
  const uniq = [...new Set(errors.map((e) => e.split(" :: ")[0].slice(0, 160)))];
  console.log("\n=== errors (" + errors.length + ", unique " + uniq.length + ")");
  uniq.slice(0, 6).forEach((u) => console.log("  -", u));
  console.log("=== net", net.length);
  const w = dom.window;
  console.log("__cf token-ish:", Object.keys(w).filter((k) => /token|turnstile|cf/i.test(k)).slice(0, 10));
  process.exit(0);
}, 20000);
