// Browser-surface shims for running the Turnstile challenge document inside jsdom.
// Goal: satisfy the realm / anti-tamper probes that jsdom fails by default
// (native-function toString, Worker, OffscreenCanvas, plugins, screen, ...).

function installShims(win) {
  // ---- 1. native-looking Function.prototype.toString -------------------------
  const realToString = win.Function.prototype.toString;
  const nativeCache = new WeakMap();
  const NATIVE_BODY = "{ [native code] }";

  function fakeToString() {
    if (nativeCache.has(this)) return nativeCache.get(this);
    const src = realToString.call(this);
    // jsdom / shim functions look like JS; present the standard browser shape.
    const name = this.name || "";
    if (/\[native code\]/.test(src)) return src;
    return `function ${name}() ${NATIVE_BODY}`;
  }
  Object.defineProperty(win.Function.prototype, "toString", {
    value: fakeToString, writable: true, configurable: true,
  });
  const markNative = (fn, name) => { nativeCache.set(fn, `function ${name || fn.name}() ${NATIVE_BODY}`); return fn; };

  // ---- 2. Worker (blob based, evaluated in a fresh vm context) --------------
  const vm = require("vm");
  class ShimWorker {
    constructor(url) {
      this.onmessage = null;
      this.onerror = null;
      this._url = String(url);
      this._ctx = null;
    }
    postMessage(data) {
      // Best effort: Cloudflare workers mostly self-run; we just echo errors.
      try { this.onmessage && this.onmessage({ data: { type: "noop" } }); } catch (_) {}
    }
    terminate() {}
    addEventListener(t, f) { if (t === "message") this.onmessage = f; }
    removeEventListener() {}
  }
  win.Worker = markNative(ShimWorker, "Worker");

  // ---- 3. canvas 2d / OffscreenCanvas / ImageData ---------------------------
  class ShimImageData {
    constructor(w, h) {
      if (typeof w === "object" && w) { this.width = w.width; this.height = w.height; this.data = w.data; }
      else { this.width = w; this.height = h; this.data = new Uint8ClampedArray(w * h * 4); }
    }
  }
  win.ImageData = markNative(ShimImageData, "ImageData");
  win.OffscreenCanvas = markNative(class OffscreenCanvas {
    constructor(w, h) { this.width = w; this.height = h; }
    getContext() { return win.document.createElement("canvas").getContext("2d"); }
    convertToBlob() { return Promise.resolve(new win.Blob([])); }
  }, "OffscreenCanvas");

  const ctxProto = {
    canvas: null, fillStyle: "#000", strokeStyle: "#000", font: "10px sans-serif",
    globalAlpha: 1, globalCompositeOperation: "source-over", textBaseline: "alphabetic",
    lineWidth: 1, shadowBlur: 0, shadowColor: "rgba(0,0,0,0)",
    fillRect() {}, clearRect() {}, strokeRect() {}, beginPath() {}, closePath() {},
    moveTo() {}, lineTo() {}, arc() {}, arcTo() {}, bezierCurveTo() {}, quadraticCurveTo() {},
    fill() {}, stroke() {}, save() {}, restore() {}, translate() {}, rotate() {}, scale() {},
    setTransform() {}, transform() {}, drawImage() {}, fillText() {}, strokeText() {},
    measureText(t) { return { width: String(t).length * 6.2 }; },
    createLinearGradient() { return { addColorStop() {} }; },
    createRadialGradient() { return { addColorStop() {} }; },
    createPattern() { return {}; }, clip() {}, rect() {},
    getImageData(x, y, w, h) { return new ShimImageData(w, h); },
    putImageData() {},
    createImageData(w, h) { return new ShimImageData(w, h); },
    setLineDash() {}, getLineDash() { return []; },
  };
  win.CanvasRenderingContext2D = markNative(function CanvasRenderingContext2D() {}, "CanvasRenderingContext2D");
  for (const k of Object.keys(ctxProto)) {
    if (typeof ctxProto[k] === "function") markNative(ctxProto[k], k);
  }

  const origGetContext = win.HTMLCanvasElement.prototype.getContext;
  win.HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
    if (/webgl/i.test(type)) return win.__glStub();
    const c = Object.create(ctxProto);
    c.canvas = this;
    return c;
  };

  // ---- 4. navigator / screen / misc ----------------------------------------
  const nav = win.navigator;
  const def = (obj, k, v) => Object.defineProperty(obj, k, { get: () => v, configurable: true });
  def(nav, "webdriver", false);
  def(nav, "platform", "Win32");
  def(nav, "vendor", "Google Inc.");
  def(nav, "product", "Gecko");
  def(nav, "hardwareConcurrency", 8);
  def(nav, "deviceMemory", 8);
  def(nav, "maxTouchPoints", 0);
  def(nav, "languages", ["id-ID", "id", "en-US", "en"]);
  def(nav, "language", "id-ID");
  def(nav, "doNotTrack", null);
  def(nav, "cookieEnabled", true);
  def(nav, "onLine", true);
  def(nav, "pdfViewerEnabled", true);
  Object.defineProperty(nav, "plugins", {
    get: () => [{ name: "PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format", length: 5 }],
    configurable: true,
  });
  Object.defineProperty(nav, "mimeTypes", { get: () => [{ type: "application/pdf" }], configurable: true });

  def(win.screen, "width", 1920); def(win.screen, "height", 1080);
  def(win.screen, "availWidth", 1920); def(win.screen, "availHeight", 1040);
  def(win.screen, "colorDepth", 24); def(win.screen, "pixelDepth", 24);
  def(win, "devicePixelRatio", 1);
  def(win, "innerWidth", 1280); def(win, "innerHeight", 800);
  def(win, "outerWidth", 1280); def(win, "outerHeight", 900);
  def(win, "screenX", 0); def(win, "screenY", 0);

  win.chrome = win.chrome || {};
  win.chrome.runtime = win.chrome.runtime || {};
  win.chrome.app = { isInstalled: false, InstallState: { DISABLED: "disabled" }, RunningState: { RUNNING: "running" } };
  win.chrome.csi = () => ({ onloadT: Date.now(), startE: Date.now() - 500, tran: 15 });
  win.chrome.loadTimes = () => ({ requestTime: Date.now() / 1000 - 1, startLoadTime: Date.now() / 1000 - 1, commitLoadTime: Date.now() / 1000 - 0.5, finishDocumentLoadTime: Date.now() / 1000 - 0.2, finishLoadTime: Date.now() / 1000 - 0.1, firstPaintTime: Date.now() / 1000 - 0.3, firstPaintAfterLoadTime: 0, navigationType: "Other", wasFetchedViaSpdy: true, wasNpnNegotiated: true, npnNegotiatedProtocol: "h2", wasAlternateProtocolAvailable: false, connectionInfo: "h2" });

  win.Notification = markNative(class Notification {
    static permission = "denied";
    static requestPermission() { return Promise.resolve("denied"); }
  }, "Notification");
  win.requestIdleCallback = win.requestIdleCallback || function (cb) { return setTimeout(() => cb({ didTimeout: false, timeRemaining: () => 50 }), 1); };
  win.cancelIdleCallback = win.cancelIdleCallback || function (id) { clearTimeout(id); };
  win.matchMedia = win.matchMedia || function (q) {
    return { matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } };
  };
  win.speechSynthesis = win.speechSynthesis || { getVoices: () => [{ name: "Google US English", lang: "en-US", voiceURI: "Google US English", localService: false, default: true }] };
  win.HTMLMediaElement.prototype.canPlayType = function () { return "probably"; };
  win.HTMLMediaElement.prototype.play = function () { return Promise.resolve(); };
  win.HTMLMediaElement.prototype.load = function () {};

  return { markNative };
}

module.exports = { installShims };
