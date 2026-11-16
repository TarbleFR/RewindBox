// Runs in the receiver page BEFORE any of Google's scripts (Playwright addInitScript).
// Two jobs, both outside Google's code (their bytes are served unmodified):
//  1. play the device side of the cast shell: window.cast.__platform__ (optional);
//  2. observe: the <video> element, the bar code on screen, the Shaka instance, MPL hosts, UMA metrics.
// The configuration token below is replaced by the runner.
(() => {
  const cfg = __LAB_CONFIG__;
  const lab = window.__lab = {
    cfg, samples: [], events: [], platformAccess: {}, platformQueries: [], canDisplay: [], metrics: [],
    shaka: null, shakaConfigure: [], shakaLoads: [], shakaEvents: [], mpl: { hosts: 0, loads: [], version: null }, errors: [], rvfc: { count: 0, last: null },
  };
  const now = () => Date.now();
  const safe = (value, depth = 0) => {
    if (typeof value === 'function') return '[function]';
    if (value === null || typeof value !== 'object') return (typeof value === 'number' && !isFinite(value)) ? String(value) : value;
    if (depth > 8) return '[deep]';
    if (value instanceof Date) return value.toISOString();
    if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer) return '[bytes]';
    if (Array.isArray(value)) return value.map((x) => safe(x, depth + 1));
    if (typeof Map !== 'undefined' && value instanceof Map) return { '[map]': Array.from(value.entries()).map((x) => safe(x, depth + 1)) };
    if (value instanceof Node) return '[node ' + value.nodeName + ']';
    const out = {};
    for (const key of Object.keys(value)) { try { out[key] = safe(value[key], depth + 1); } catch (e) { out[key] = '[throws]'; } }
    return out;
  };
  lab.safe = safe;
  window.addEventListener('error', (e) => lab.errors.push({ t: now(), message: String(e.message), source: e.filename, line: e.lineno }));
  window.addEventListener('unhandledrejection', (e) => lab.errors.push({ t: now(), rejection: String(e.reason && (e.reason.stack || e.reason.message || e.reason)) }));

  // ---- 1. cast shell, device side -------------------------------------------------------------
  if (cfg.platform) {
    const values = Object.assign({ 'port-for-web-server': String(cfg.ipcPort) }, cfg.platformValues || {});
    if (cfg.flags) values['receiver-flags'] = cfg.flags;
    const metric = (kind) => function () { if (lab.metrics.length < 20000) lab.metrics.push([now(), kind].concat(Array.from(arguments))); };
    const target = {
      queryPlatformValue(key) { lab.platformQueries.push([now(), key, key in values]); return values[key]; },
      canDisplayType(type) {
        let ok = false;
        try {
          const text = String(type);
          const main = text.split(';')[0].trim();
          const codecs = (/codecs="?([^";]+)"?/.exec(text) || [])[1];
          const width = Number((/width=(\d+)/.exec(text) || [])[1] || 0), height = Number((/height=(\d+)/.exec(text) || [])[1] || 0);
          const framerate = Number((/framerate=([\d.]+)/.exec(text) || [])[1] || 0);
          const probe = codecs ? `${main}; codecs="${codecs}"` : main;
          ok = (codecs ? MediaSource.isTypeSupported(probe) : document.createElement('video').canPlayType(main) !== '')
            && width <= cfg.maxWidth && height <= cfg.maxHeight && framerate <= 60 && !/eotf=|dvh|hev1\.2|spatialRendering/.test(text);
        } catch (e) {}
        if (lab.canDisplay.length < 500) lab.canDisplay.push([String(type), ok]);
        return ok;
      },
      // UMA sink: any method the libraries call is accepted and recorded (MPL also calls setMplVersion, ...)
      metrics: new Proxy({ logBoolToUma: metric('bool'), logEventToUma: metric('event'), logHistogramValueToUma: metric('histogram'), logIntToUma: metric('int') },
        { get(t, key) { if (typeof key !== 'string') return t[key]; if (!(key in t)) t[key] = metric(key); return t[key]; } }),
    };
    window.cast = window.cast || {};
    window.cast.__platform__ = new Proxy(target, {
      get(t, key) { if (typeof key === 'string') lab.platformAccess[key] = (lab.platformAccess[key] || 0) + 1; return t[key]; },
      has(t, key) { if (typeof key === 'string') lab.platformAccess['in:' + key] = (lab.platformAccess['in:' + key] || 0) + 1; return key in t; },
    });
  }
  if (cfg.deviceMemory) try { Object.defineProperty(Navigator.prototype, 'deviceMemory', { get: () => cfg.deviceMemory, configurable: true }); } catch (e) {}
  if (cfg.hardwareConcurrency) try { Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', { get: () => cfg.hardwareConcurrency, configurable: true }); } catch (e) {}

  // ---- 2a. Shaka: catch the instance the framework creates, and every configure()/load() ----------
  let shakaValue;
  const patchShaka = (ns) => {
    if (!ns || !ns.Player || ns.Player.__lab) return;
    ns.Player.__lab = true;
    const proto = ns.Player.prototype;
    const adopt = (player) => {
      if (lab.shaka === player) return;
      lab.shaka = player;
      for (const name of ['buffering', 'stalldetected', 'gapjumped', 'error', 'loading', 'loaded', 'streaming', 'manifestparsed', 'adaptation', 'variantchanged', 'ratechange', 'started', 'firstquartile']) {
        try {
          player.addEventListener(name, (e) => {
            const item = { t: now(), type: name };
            if (name === 'buffering') item.buffering = e.buffering;
            if (name === 'error') item.detail = safe(e.detail && { code: e.detail.code, category: e.detail.category, severity: e.detail.severity, data: e.detail.data });
            if (name === 'gapjumped' || name === 'stalldetected') item.currentTime = player.getMediaElement() && player.getMediaElement().currentTime;
            lab.shakaEvents.push(item);
          });
        } catch (e) {}
      }
    };
    const configure = proto.configure;
    proto.configure = function () { adopt(this); lab.shakaConfigure.push({ t: now(), args: safe(Array.from(arguments)) }); return configure.apply(this, arguments); };
    const load = proto.load;
    proto.load = function () { adopt(this); lab.shakaLoads.push({ t: now(), args: safe(Array.from(arguments)) }); return load.apply(this, arguments); };
  };
  try {
    Object.defineProperty(window, 'shaka', { configurable: true, enumerable: true, get() { return shakaValue; }, set(v) { shakaValue = v; try { patchShaka(v); } catch (e) { lab.errors.push({ t: now(), hook: String(e) }); } } });
  } catch (e) {}
  lab.shakaInfo = () => {
    const p = lab.shaka; if (!p) return null;
    const out = { version: window.shaka && window.shaka.Player && window.shaka.Player.version, t: now() };
    const tryCall = (name, f) => { try { out[name] = safe(f()); } catch (e) { out[name] = '[throws ' + e + ']'; } };
    tryCall('isLive', () => p.isLive()); tryCall('seekRange', () => p.seekRange()); tryCall('stats', () => p.getStats());
    tryCall('configuration', () => p.getConfiguration()); tryCall('manifestType', () => p.getManifestType && p.getManifestType());
    tryCall('loadMode', () => p.getLoadMode && p.getLoadMode()); tryCall('bufferedInfo', () => p.getBufferedInfo());
    tryCall('presentationStartTimeAsDate', () => p.getPresentationStartTimeAsDate()); tryCall('playheadTimeAsDate', () => p.getPlayheadTimeAsDate());
    tryCall('variantTracks', () => p.getVariantTracks().map((t) => ({ codecs: t.codecs, mimeType: t.mimeType, width: t.width, height: t.height, frameRate: t.frameRate, bandwidth: t.bandwidth, active: t.active })));
    tryCall('timeline', () => {
      const m = p.getManifest(); if (!m) return null; const tl = m.presentationTimeline;
      return { delay: tl.getDelay(), isLive: tl.isLive(), isInProgress: tl.isInProgress(), maxSegmentDuration: tl.getMaxSegmentDuration(), duration: tl.getDuration(),
        availabilityStart: tl.getSegmentAvailabilityStart(), availabilityEnd: tl.getSegmentAvailabilityEnd(), seekRangeStart: tl.getSeekRangeStart(), seekRangeEnd: tl.getSeekRangeEnd(),
        presentationStartTime: tl.getPresentationStartTime(), sequenceMode: m.sequenceMode, type: m.type, minBufferTime: m.minBufferTime, isLowLatency: m.isLowLatency, serviceDescription: m.serviceDescription };
    });
    return out;
  };

  // ---- 2b. MPL: count hosts/loads if the framework goes that way -----------------------------------
  const mplTimer = setInterval(() => {
    const api = window.cast && window.cast.player && window.cast.player.api;
    if (!api || !api.Host || !api.Player) return;
    clearInterval(mplTimer);
    lab.mpl.present = true; lab.mpl.version = api.VERSION || null;
    try {
      const Host = api.Host;
      const Wrapped = function (options) { lab.mpl.hosts += 1; lab.mpl.lastHostOptions = safe({ url: options && options.url, keys: options && Object.keys(options) }); const h = new Host(options); lab.mpl.host = h; return h; };
      Wrapped.prototype = Host.prototype; api.Host = Wrapped;
      const load = api.Player.prototype.load;
      api.Player.prototype.load = function (protocol, time) { lab.mpl.loads.push({ t: now(), time: safe(time) }); lab.mpl.player = this; return load.apply(this, arguments); };
    } catch (e) { lab.errors.push({ t: now(), mplHook: String(e) }); }
  }, 2);

  // ---- 2c. the <video> element, the bar code and the sampler ---------------------------------------
  const findVideo = (root) => {
    const direct = root.querySelector && root.querySelector('video'); if (direct) return direct;
    const all = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (const el of all) { if (el.shadowRoot) { const v = findVideo(el.shadowRoot); if (v) return v; } }
    return null;
  };
  let video = null, canvas = null, context = null;
  const watch = (v) => {
    video = v; lab.videoFound = now();
    for (const name of ['loadstart', 'loadedmetadata', 'loadeddata', 'canplay', 'playing', 'waiting', 'stalled', 'seeking', 'seeked', 'pause', 'play', 'ratechange', 'ended', 'error', 'emptied', 'durationchange']) {
      v.addEventListener(name, () => lab.events.push({ t: now(), type: name, ct: v.currentTime, rate: v.playbackRate, rs: v.readyState }));
    }
    const frame = (stamp, meta) => { lab.rvfc.count += 1; lab.rvfc.last = { mediaTime: meta.mediaTime, presentedFrames: meta.presentedFrames, w: now() }; v.requestVideoFrameCallback(frame); };
    if (v.requestVideoFrameCallback) v.requestVideoFrameCallback(frame);
  };
  const readCode = () => {
    if (!video || video.readyState < 2 || !video.videoWidth) return -1;
    if (!canvas) { canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 8; context = canvas.getContext('2d', { willReadFrequently: true }); }
    try {
      const stripe = video.videoHeight * (8 / 360);
      context.drawImage(video, 0, video.videoHeight * (16 / 360), video.videoWidth, stripe, 0, 0, 640, 8);
      const data = context.getImageData(0, 4, 640, 1).data;
      let n = 0;
      for (let bit = 0; bit < 16; bit++) { const x = (bit * 40 + 20) * 4; if (data[x] + data[x + 1] + data[x + 2] > 384) n |= (1 << bit); }
      return n;
    } catch (e) { return -2; }
  };
  lab.sample = () => {
    const current = findVideo(document);
    if (current && current !== video) watch(current);
    const s = { w: now() };
    if (video) {
      s.ct = video.currentTime; s.rs = video.readyState; s.p = video.paused; s.r = video.playbackRate; s.n = readCode(); s.vw = video.videoWidth;
      const b = video.buffered; s.b = []; for (let i = 0; i < b.length; i++) s.b.push([+b.start(i).toFixed(3), +b.end(i).toFixed(3)]);
      const q = video.getVideoPlaybackQuality && video.getVideoPlaybackQuality(); if (q) { s.tf = q.totalVideoFrames; s.df = q.droppedVideoFrames; }
      s.pf = lab.rvfc.last ? lab.rvfc.last.presentedFrames : 0; s.mt = lab.rvfc.last ? lab.rvfc.last.mediaTime : null;
    }
    if (lab.shaka) {
      try { const r = lab.shaka.seekRange(); s.sr = [+r.start.toFixed(3), +r.end.toFixed(3)]; } catch (e) {}
      try { s.sb = lab.shaka.isBuffering(); } catch (e) {}
    }
    lab.samples.push(s);
  };
  lab.timer = setInterval(lab.sample, cfg.sampleMs || 50);
})();
