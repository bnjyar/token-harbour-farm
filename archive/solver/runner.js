// Turnstile challenge runner — executes the real challenge document in jsdom
// (no browser binary) and logs every network attempt for protocol mapping.
//
// usage: node runner.js <challenge.html> [iframe-url]

const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const htmlPath = process.argv[2] || "/home/god/.hermes/cache/scratch/challenge.html";
const iframeUrl = process.argv[3] ||
  "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/h/b/turnstile/f/av0/rch/9n9y4/0x4AAAAAADBuC8Knz1EJZx9-/light/fbE/new/normal?lang=auto";

const html = fs.readFileSync(htmlPath, "utf8");
const log = (...a) => console.log("[run]", ...a);

const vc = new VirtualConsole();
vc.on("jsdomError", (e) => log("JSDOM ERROR:", (e.stack || e.message || "").split("\n").slice(0, 4).join(" | ")));
vc.on("error", (...a) => log("CONSOLE ERROR:", ...a));
vc.on("warn", (...a) => log("CONSOLE WARN:", ...a));

function glStub(win) {
  const params = {
    37445: "Google Inc. (NVIDIA)",
    37446: "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
    7936: "WebKit", 7937: "WebKit WebGL", 7938: "WebGL 1.0 (OpenGL ES 2.0 Chromium)",
    35724: "WebGL GLSL ES 1.0 (OpenGL ES GLSL ES 1.0 Chromium)",
  };
  const ext = { UNMASKED_VENDOR_WEBGL: true, UNMASKED_RENDERER_WEBGL: true };
  return {
    getParameter: (p) => params[p] ?? 8192,
    getExtension: (n) => (ext[n] ? { UNMASKED_VENDOR_WEBGL: 37445, UNMASKED_RENDERER_WEBGL: 37446 } : null),
    getSupportedExtensions: () => Object.keys(ext),
    getShaderPrecisionFormat: () => ({ rangeMin: 127, rangeMax: 127, precision: 23 }),
    getContextAttributes: () => ({ alpha: true, antialias: true, depth: true, stencil: false }),
    drawingBufferWidth: 300, drawingBufferHeight: 150,
    readPixels() {}, clearColor() {}, enable() {}, disable() {}, clear() {},
    createBuffer: () => ({}), bindBuffer() {}, bufferData() {},
    createProgram: () => ({}), createShader: () => ({}), shaderSource() {}, compileShader() {},
    attachShader() {}, linkProgram() {}, useProgram() {}, getProgramParameter: () => true,
    getShaderParameter: () => true, getAttribLocation: () => 0, getUniformLocation: () => ({}),
    vertexAttribPointer() {}, enableVertexAttribArray() {}, uniformMatrix4fv() {}, drawArrays() {},
    viewport() {}, getError: () => 0, isContextLost: () => false,
  };
}

const stats = { xhr: [], fetch: [], total: 0 };

function installNetworkLogging(win) {
  const XHR = win.XMLHttpRequest;
  const open = XHR.prototype.open;
  const send = XHR.prototype.send;
  XHR.prototype.open = function (m, u, ...rest) {
    this.__m = m; this.__u = u;
    return open.call(this, m, u, ...rest);
  };
  XHR.prototype.send = function (body) {
    stats.total++;
    stats.xhr.push({ m: this.__m, u: String(this.__u), len: body ? String(body).length : 0 });
    log(`XHR ${this.__m} ${String(this.__u).slice(0, 160)} body=${body ? String(body).length : 0}`);
    this.addEventListener("loadend", () => log(`XHR< ${this.status} ${String(this.__u).slice(0, 80)} resp=${(this.responseText || "").length}`));
    this.addEventListener("error", () => log(`XHR! error ${String(this.__u).slice(0, 80)}`));
    return send.call(this, body);
  };

  win.fetch = (u, o = {}) => {
    stats.total++;
    stats.fetch.push({ u: String(u), body: o.body ? String(o.body).length : 0 });
    log(`FETCH ${String(u).slice(0, 160)} body=${o.body ? String(o.body).length : 0}`);
    return Promise.reject(new Error("blocked-by-runner"));
  };
}

const dom = new JSDOM(html, {
  url: iframeUrl,
  referrer: "https://tokenharbor.ai/",
  runScripts: "dangerously",
  pretendToBeVisual: true,
  virtualConsole: vc,
  beforeParse(win) {
    Object.defineProperty(win.navigator, "webdriver", { get: () => undefined });
    Object.defineProperty(win.navigator, "hardwareConcurrency", { get: () => 8 });
    Object.defineProperty(win.navigator, "deviceMemory", { get: () => 8 });
    Object.defineProperty(win.navigator, "languages", { get: () => ["id-ID", "id", "en-US", "en"] });
    win.chrome = { runtime: {}, app: { isInstalled: false }, csi: () => ({}), loadTimes: () => ({}) };

    const origGetContext = win.HTMLCanvasElement.prototype.getContext;
    win.HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
      if (/webgl/i.test(type)) return glStub(win);
      const ctx = { canvas: this, fillRect() {}, fillText() {}, drawImage() {}, measureText: () => ({ width: 42 }),
        getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }), putImageData() {},
        createLinearGradient: () => ({ addColorStop() {} }), beginPath() {}, arc() {}, fill() {}, stroke() {},
        save() {}, restore() {}, translate() {}, rotate() {}, scale() {}, setTransform() {},
        font: "", fillStyle: "", globalCompositeOperation: "source-over" };
      return ctx;
    };
    win.AudioContext = win.webkitAudioContext = function () {
      return { sampleRate: 48000, state: "running", destination: {}, createOscillator: () => ({ connect() {}, start() {}, stop() {}, frequency: { value: 0 }, type: "sine" }), createGain: () => ({ connect() {}, gain: { value: 0 } }), createAnalyser: () => ({ connect() {}, fftSize: 2048, getByteFrequencyData() {} }), createDynamicsCompressor: () => ({ connect() {} }) };
    };
    win.OfflineAudioContext = function () {
      return { sampleRate: 44100, length: 5000, startRendering: () => Promise.resolve({ getChannelData: () => new Float32Array(5000) }), createOscillator: () => ({ connect() {}, start() {}, frequency: { value: 0 }, type: "sine" }), createGain: () => ({ connect() {}, gain: { value: 0 } }), destination: {} };
    };
    installNetworkLogging(win);
  },
});

log("document ready, waiting 30s for challenge flow");
setTimeout(() => {
  log("SUMMARY xhr=" + stats.xhr.length + " fetch=" + stats.fetch.length + " total=" + stats.total);
  for (const x of stats.xhr) log("  xhr", x.m, x.u.slice(0, 120), "b=" + x.len);
  const w = dom.window;
  log("globals:", Object.keys(w).filter((k) => /cf|chl|turnstile/i.test(k)).slice(0, 20).join(","));
  log("textarea/input values:", [...w.document.querySelectorAll("input,textarea")].map((e) => e.name + "=" + (e.value || "").slice(0, 40)));
  process.exit(0);
}, 30000);
