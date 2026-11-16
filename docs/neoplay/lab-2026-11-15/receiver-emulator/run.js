'use strict';
// One experiment = one live origin + one emulated cast shell + Google's real Default Media Receiver
// page in headless Chromium + a scripted "iOS sender". Writes out/<name>.json.
//
//   node src/run.js --name base --duration 30
//   node src/run.js --name mpl --flags '{"use_shaka_for_hls":false}'
//   node src/run.js --name hb15 --playlist '{"holdBack":1.5}'
//   node src/run.js --name seek --actions '[{"at":12,"do":"hold","ms":2500},{"at":22,"do":"media","msg":{"type":"SEEK","currentTime":4294967296,"resumeState":"PLAYBACK_START"}}]'
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('playwright');
const { listen } = require('./wsserver.js');
const { startOrigin } = require('./origin.js');

const ROOT = path.resolve(__dirname, '..');
const SNAPSHOT = path.join(ROOT, 'google');
const RECEIVER_URL = 'https://www.gstatic.com/cast/sdk/default_receiver/1.0/app.html?skin=https://www.gstatic.com/eureka/player/0000/skins/cast/skin.css';
const USER_AGENTS = {
  // Chromecast (3rd gen), Linux cast shell; version numbers are of the published form, the exact build is not known here
  chromecast3: 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.225 Safari/537.36 CrKey/1.56.500000 DeviceType/Chromecast',
  // Chromecast with Google TV (Android TV cast shell)
  googletv: 'Mozilla/5.0 (Linux; Android 12.0; Build/STTL.240206.002) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.146 Safari/537.36 CrKey/1.56.500000 DeviceType/AndroidTV',
  none: null, // headless Chromium's own user agent (no CrKey)
};
const NS_SYSTEM = 'urn:x-cast:com.google.cast.system';
const NS_MEDIA = 'urn:x-cast:com.google.cast.media';

function parseArgs(argv) {
  // startMode 'app': like NPController - the capture (origin) starts once the cast session is ready and the LOAD leaves as soon as the
  //   store holds three segments, plus loadDelay ms for the trip iPhone -> Chromecast. 'early': the origin runs before the receiver starts.
  const out = { name: 'run', duration: 30, ua: 'chromecast3', platform: true, flags: null, playlist: {}, actions: [], poll: 0, loadExtra: null, mediaExtra: null, debug: false, settle: 5, ipcPort: 0, startMode: 'app', loadDelay: 100 };
  for (let i = 2; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, ''), value = argv[i + 1];
    if (['flags', 'playlist', 'actions', 'loadExtra', 'mediaExtra', 'platformValues'].includes(key)) out[key] = JSON.parse(value);
    else if (['duration', 'poll', 'settle', 'ipcPort', 'loadDelay', 'playOnStatus'].includes(key)) out[key] = Number(value);
    else if (['platform', 'debug'].includes(key)) out[key] = value === 'true' || value === '1';
    else out[key] = value;
  }
  return out;
}

async function main() {
  const cfg = parseArgs(process.argv);
  const result = { name: cfg.name, config: cfg, startedAt: Date.now(), ipc: [], console: [], network: { served: [], missing: [], aborted: [], other: [] }, marks: {}, actionsDone: [], shakaSnapshots: [] };
  const mark = (name) => { if (!(name in result.marks)) result.marks[name] = Date.now(); };
  let origin = null, shell = null, browser = null;
  const cleanup = async () => {
    try { if (browser) await browser.close(); } catch (e) {}
    try { if (shell) await shell.close(); } catch (e) {}
    try { if (origin) await origin.stop(); } catch (e) {}
  };
  process.on('SIGINT', async () => { await cleanup(); process.exit(130); });
  process.on('SIGTERM', async () => { await cleanup(); process.exit(143); });
  try {
    // ---- the "iPhone": live HLS origin ---------------------------------------------------------
    if (cfg.startMode === 'early') { origin = await startOrigin(cfg.playlist); await origin.waitReady(); }

    // ---- the cast shell: IPC web socket ---------------------------------------------------------
    const sessionId = crypto.randomUUID(), transport = crypto.randomUUID() + '.2:';
    const senderId = transport + 'sender-neoplay', launcher = senderId;
    let peer = null, requestId = 100, mediaSessionId = null, receiverReady = null;
    const waiters = [];
    const send = (namespace, sender, data) => {
      const text = JSON.stringify(data);
      result.ipc.push({ t: Date.now(), dir: 'to-receiver', namespace, senderId: sender, data });
      peer.send(JSON.stringify({ namespace, senderId: sender, data: text }));
    };
    const sendMedia = (message) => {
      const full = Object.assign({ requestId: ++requestId }, message);
      if (full.type !== 'LOAD' && full.type !== 'GET_STATUS' && mediaSessionId !== null && full.mediaSessionId === undefined) full.mediaSessionId = mediaSessionId;
      if (full.mediaSessionId === null) delete full.mediaSessionId;
      send(NS_MEDIA, senderId, full);
      return full.requestId;
    };
    shell = await listen(cfg.platform ? cfg.ipcPort : 8008, '/v2/ipc', (p) => {
      peer = p; mark('ipcOpen');
      p.on('message', (text) => {
        const t = Date.now();
        let envelope; try { envelope = JSON.parse(text); } catch (e) { result.ipc.push({ t, dir: 'from-receiver', raw: text }); return; }
        let data = envelope.data; try { data = JSON.parse(envelope.data); } catch (e) {}
        result.ipc.push({ t, dir: 'from-receiver', namespace: envelope.namespace, senderId: envelope.senderId, data });
        if (envelope.namespace === NS_SYSTEM && data && data.type === 'ready') {
          mark('receiverReady'); receiverReady = data;
          // what a cast shell answers (order and fields as recorded from real devices by chromecast-device-emulator)
          send(NS_SYSTEM, 'SystemSender', { applicationId: 'CC1AD845', applicationName: 'Default Media Receiver', closedCaption: {},
            deviceCapabilities: { bluetooth_supported: false, display_supported: true, focus_state_supported: true, hi_res_audio_supported: false },
            launchingSenderId: launcher, messagesVersion: '1.0', sessionId, type: 'ready', version: '1.56.500000' });
          send(NS_SYSTEM, 'SystemSender', { level: 1.0, muted: false, type: 'volumechanged' });
          send(NS_SYSTEM, 'SystemSender', { type: 'visibilitychanged', visible: true });
          send(NS_SYSTEM, 'SystemSender', { type: 'standbychanged', standby: false });
          send(NS_SYSTEM, 'SystemSender', { hdrType: 'sdr', type: 'hdroutputtypechanged' });
          send(NS_SYSTEM, 'SystemSender', { senderId, type: 'senderconnected', userAgent: 'iOS CastSDK,4.8.6,iPhone17,2,iOS,18.6' });
          for (const w of waiters.splice(0)) w();
        }
        if (envelope.namespace === NS_MEDIA && data && data.type === 'MEDIA_STATUS' && data.status && data.status[0]) {
          const s = data.status[0];
          if (s.mediaSessionId !== undefined) mediaSessionId = s.mediaSessionId;
          if (s.playerState === 'PLAYING') mark('firstPlaying');
          if (s.playerState === 'BUFFERING') mark('firstBuffering');
        }
      });
      p.on('close', () => mark('ipcClosed'));
    });
    result.ipcPort = shell.port;

    // ---- the Chromecast's browser ---------------------------------------------------------------
    // The cast shell lets the receiver page (https, public origin) talk to the device's own socket and to hosts on the LAN;
    // desktop Chromium needs its Local Network Access checks switched off for that. Autoplay needs no gesture on a cast device.
    browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required', '--disable-features=LocalNetworkAccessChecks'] });
    result.browserVersion = browser.version();
    const contextOptions = { viewport: { width: 1280, height: 720 } };
    if (USER_AGENTS[cfg.ua]) contextOptions.userAgent = USER_AGENTS[cfg.ua];
    const context = await browser.newContext(contextOptions);
    const platformValues = Object.assign({}, cfg.platformValues || {});
    if (cfg.debug) platformValues['log-level-cast-receiver'] = 0; // the shell's own switch for the framework's debug log
    const inpage = fs.readFileSync(path.join(__dirname, 'inpage.js'), 'utf8').replace('__LAB_CONFIG__', JSON.stringify({
      platform: cfg.platform, ipcPort: shell.port, flags: cfg.flags, platformValues, maxWidth: 1920, maxHeight: 1080,
      deviceMemory: cfg.deviceMemory ? Number(cfg.deviceMemory) : null, hardwareConcurrency: cfg.hardwareConcurrency ? Number(cfg.hardwareConcurrency) : null, sampleMs: 50,
    }));
    await context.addInitScript({ content: inpage });
    // Google's hosts are answered from the local snapshot (bytes unmodified); the page never reaches the Internet.
    await context.route((url) => url.hostname !== '127.0.0.1' && url.hostname !== 'localhost', async (route) => {
      const url = new URL(route.request().url());
      const file = path.join(SNAPSHOT, url.hostname, decodeURIComponent(url.pathname));
      if ((url.hostname === 'www.gstatic.com' || url.hostname === 'ajax.googleapis.com') && file.startsWith(SNAPSHOT) && fs.existsSync(file) && fs.statSync(file).isFile()) {
        result.network.served.push({ t: Date.now(), url: url.href });
        const type = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : file.endsWith('.png') ? 'image/png' : 'application/octet-stream';
        await route.fulfill({ status: 200, contentType: type, body: fs.readFileSync(file), headers: { 'access-control-allow-origin': '*' } });
      } else if (url.hostname === 'www.gstatic.com' || url.hostname === 'ajax.googleapis.com') {
        result.network.missing.push({ t: Date.now(), url: url.href });
        await route.fulfill({ status: 404, body: '' });
      } else {
        result.network.aborted.push({ t: Date.now(), url: url.href });
        await route.abort();
      }
    });
    const page = await context.newPage();
    page.on('console', (m) => { if (result.console.length < 6000) result.console.push({ t: Date.now(), type: m.type(), text: m.text().slice(0, 3000) }); });
    page.on('pageerror', (e) => result.console.push({ t: Date.now(), type: 'pageerror', text: String(e && (e.stack || e.message)) }));
    page.on('requestfailed', (r) => result.network.other.push({ t: Date.now(), failed: r.url(), error: r.failure() && r.failure().errorText }));
    page.on('websocket', (ws) => result.network.other.push({ t: Date.now(), websocket: ws.url() }));
    mark('navigate');
    await page.goto(RECEIVER_URL, { waitUntil: 'load' });
    mark('pageLoaded');
    await new Promise((resolve, reject) => { if (receiverReady) resolve(); else { waiters.push(resolve); setTimeout(() => reject(new Error('the receiver never sent "ready" on the IPC socket')), 15000); } })
      .catch(async (e) => { result.error = String(e.message); });

    if (!result.error) {
      // ---- the iOS sender: GET_STATUS, then the LOAD of NPGoogleCast.load(_:) -------------------
      await new Promise((r) => setTimeout(r, 300));
      sendMedia({ type: 'GET_STATUS' });
      if (!origin) { origin = await startOrigin(cfg.playlist); await origin.waitReady(); } // NPController: capture starts when the session is ready
      result.contentUrl = origin.url;
      result.originReadyAt = Date.now();
      await new Promise((r) => setTimeout(r, cfg.loadDelay));
      const entryUrl = cfg.entry === 'master' ? origin.url.replace('index.m3u8', 'master.m3u8') : cfg.entry === 'dash' ? origin.url.replace('index.m3u8', 'live.mpd') : cfg.entry === 'prog' ? origin.url.replace('index.m3u8', 'live.mp4') : origin.url;
      if (cfg.entry === 'prog') cfg.mediaExtra = Object.assign({ contentType: 'video/mp4', hlsSegmentFormat: null, hlsVideoSegmentFormat: null }, cfg.mediaExtra || {});
      if (cfg.entry === 'dash') cfg.mediaExtra = Object.assign({ contentType: 'application/dash+xml', hlsSegmentFormat: null, hlsVideoSegmentFormat: null }, cfg.mediaExtra || {});
      const media = Object.assign({ contentUrl: entryUrl, contentType: 'application/vnd.apple.mpegurl', streamType: 'LIVE',
        hlsSegmentFormat: 'fmp4', hlsVideoSegmentFormat: 'fmp4', metadata: { metadataType: 0, title: 'NeoPlay' } }, cfg.mediaExtra || {});
      for (const key of Object.keys(media)) if (media[key] === null) delete media[key]; // --mediaExtra '{"hlsSegmentFormat":null}' removes a field
      mark('loadSent');
      sendMedia(Object.assign({ type: 'LOAD', sessionId, media, autoplay: true }, cfg.loadExtra || {}));
      if (cfg.playOnStatus !== undefined) { // the sender answers the first status of this load with PLAY (after playOnStatus ms)
        const before = mediaSessionId, deadline = Date.now() + 15000;
        while ((mediaSessionId === null || mediaSessionId === before) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 5));
        await new Promise((r) => setTimeout(r, Number(cfg.playOnStatus)));
        mark('playSent'); sendMedia({ type: 'PLAY' });
      }

      // wait for PLAYING (or give up), then run the scripted actions
      const playingDeadline = Date.now() + 25000;
      while (!result.marks.firstPlaying && Date.now() < playingDeadline) await new Promise((r) => setTimeout(r, 20));
      const base = result.marks.firstPlaying || Date.now();
      if (!result.marks.firstPlaying) result.error = 'no PLAYING status within 25 s of LOAD';
      const actions = (cfg.actions || []).slice().sort((a, b) => a.at - b.at);
      const snapshotTimes = [3, cfg.duration - 1];
      let nextPoll = cfg.poll ? base + cfg.poll * 1000 : Infinity;
      const end = base + (result.error ? 3 : cfg.duration) * 1000;
      while (Date.now() < end) {
        const elapsed = (Date.now() - base) / 1000;
        while (actions.length && actions[0].at <= elapsed) {
          const action = actions.shift(), entry = { t: Date.now(), at: action.at, action };
          if (action.do === 'media') entry.requestId = sendMedia(action.msg);
          else if (action.do === 'hold') origin.hold(action.ms);
          else if (action.do === 'eval') entry.value = await page.evaluate(action.js).catch((e) => 'error: ' + e.message);
          else if (action.do === 'snapshot') result.shakaSnapshots.push({ at: action.at, info: await page.evaluate(() => window.__lab.shakaInfo()).catch(() => null) });
          result.actionsDone.push(entry);
        }
        while (snapshotTimes.length && snapshotTimes[0] <= elapsed) {
          const at = snapshotTimes.shift();
          result.shakaSnapshots.push({ at, info: await page.evaluate(() => window.__lab.shakaInfo()).catch(() => null) });
        }
        if (Date.now() >= nextPoll) { sendMedia({ type: 'GET_STATUS' }); nextPoll += cfg.poll * 1000; }
        await new Promise((r) => setTimeout(r, 10));
      }
    }
    // ---- collect ----------------------------------------------------------------------------------
    result.page = await page.evaluate(() => {
      const lab = window.__lab; clearInterval(lab.timer);
      const info = { samples: lab.samples, events: lab.events, platformAccess: lab.platformAccess, platformQueries: lab.platformQueries, canDisplay: lab.canDisplay,
        metrics: lab.metrics, shakaConfigure: lab.shakaConfigure, shakaLoads: lab.shakaLoads, shakaEvents: lab.shakaEvents, errors: lab.errors, rvfcCount: lab.rvfc.count,
        mpl: { present: !!lab.mpl.present, version: lab.mpl.version, hosts: lab.mpl.hosts, loads: lab.mpl.loads, lastHostOptions: lab.mpl.lastHostOptions || null },
        userAgent: navigator.userAgent, hasShaka: !!lab.shaka, shakaVersion: window.shaka && window.shaka.Player ? window.shaka.Player.version : null,
        cafVersion: window.cast && cast.framework ? cast.framework.VERSION : null, scripts: Array.from(document.scripts).map((s) => s.src).filter(Boolean) };
      try { const ctx = cast.framework.CastReceiverContext.getInstance(); info.deviceInformation = lab.safe(ctx.getDeviceCapabilities && ctx.getDeviceCapabilities()); info.applicationData = lab.safe(ctx.getApplicationData && ctx.getApplicationData()); } catch (e) {}
      try { const pm = cast.framework.CastReceiverContext.getInstance().getPlayerManager(); info.playerManager = lab.safe({ state: pm.getPlayerState(), currentTime: pm.getCurrentTimeSec(), live: pm.getLiveSeekableRange(), startAbsoluteTime: pm.getStartAbsoluteTime && pm.getStartAbsoluteTime(), absolute: pm.getAbsoluteTimeForMediaTime && pm.getAbsoluteTimeForMediaTime(pm.getCurrentTimeSec()), supported: pm.getSupportedMediaCommands(), stats: pm.getStats(), playbackConfig: pm.getPlaybackConfig() }); } catch (e) { info.playerManagerError = String(e); }
      return info;
    }).catch((e) => ({ error: String(e) }));
    if (origin) result.origin = {
      options: origin.state.options, t0: origin.t0(), spawnedAt: origin.state.spawnedAt, firstByteAt: origin.state.firstByteAt, ffmpegArgs: origin.state.ffmpegArgs,
      segments: origin.state.segments.map((s) => ({ sequence: s.sequence, arrival: s.arrival, bytes: s.bytes.length })),
      requests: origin.state.requests, stderr: origin.state.stderr, firstPlaylist: origin.state.firstPlaylist, lastPlaylist: origin.playlist(),
    };
  } catch (e) {
    result.error = (result.error ? result.error + ' | ' : '') + String(e && (e.stack || e));
  } finally {
    await cleanup();
  }
  result.finishedAt = Date.now();
  fs.mkdirSync(path.join(ROOT, 'out'), { recursive: true });
  const file = path.join(ROOT, 'out', cfg.name + '.json');
  fs.writeFileSync(file, JSON.stringify(result));
  console.log((result.error ? 'ERROR ' + result.error + '\n' : '') + 'wrote ' + file);
  process.exit(0);
}

main();
