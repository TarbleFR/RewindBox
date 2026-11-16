#!/usr/bin/env node
'use strict';
// One measurement run: origin.js (sender model) + headless Chromium with Shaka Player (receiver model).
// Non-interactive; exits by itself; kills ffmpeg, the origin and the browser it started. See README.md.

const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn, execFileSync } = require('child_process');
const { parseArgs, usage, toArgv } = require('./lib/args');
const ORIGIN_SPEC = require('./lib/origin-options');
const { analyze, summary } = require('./analyze');

const HERE = __dirname;
const RETRY = { maxAttempts: 4, baseDelay: 400, backoffFactor: 2, timeout: 30000 };
// What Google's Web Receiver framework passes to player.configure() for the Shaka version it loads by
// default (cast_receiver_framework.js, function "ko"): see README.md, "Receiver configuration".
const RECEIVER_CONFIG = {
  abr: { defaultBandwidthEstimate: 2e6, removeLatencyFromFirstPacketTime: false },
  manifest: { retryParameters: RETRY },
  streaming: { rebufferingGoal: 10, stallThreshold: 5, retryParameters: RETRY, dispatchAllEmsgBoxes: true },
  mediaSource: { codecSwitchingStrategy: 'reload' },
};
const DEFAULT_SHAKA = '4.15.56';   // cast_receiver_framework.js: default_shaka_version || "4.15.56"

const RUN_SPEC = {
  'label': { type: 'string', default: 'run', help: 'name of the run (also the default file name)' },
  'out': { type: 'string', default: '', help: 'result file (default results/<label>.json)' },
  'raw': { type: 'bool', default: false, help: 'also write <out>.raw.json with every sample (re-analysable with analyze.js)' },
  'duration': { type: 'number', default: 60, help: 'seconds measured after the first presented frame' },
  'warmup': { type: 'number', default: 5, help: 'seconds after the first frame left out of the "steady" statistics' },
  'freeze-ms': { type: 'number', default: 100, help: 'a gap between two presented frames longer than this is a freeze' },
  'page-port': { type: 'number', default: 0, help: 'port of the page server (0 = any free port)' },
  'origin-url': { type: 'string', default: '', help: 'use an origin that is already running (its playlist URL) instead of starting one' },
  'shaka-version': { type: 'string', default: DEFAULT_SHAKA, help: 'Shaka Player version, fetched once from ajax.googleapis.com into vendor/' },
  'shaka-file': { type: 'string', default: '', help: 'use this local shaka-player build instead' },
  'shaka-debug': { type: 'bool', default: false, help: 'load shaka-player.compiled.debug.js' },
  'config': { type: 'string', default: 'receiver', help: 'player.configure() argument: "receiver" (what the Cast framework sets), "shaka" (nothing), JSON, or @file' },
  'config-merge': { type: 'json', default: null, help: 'JSON merged over --config, e.g. \'{"streaming":{"rebufferingGoal":2}}\'' },
  'seek-rule': { type: 'string', default: 'none', help: 'none | tracker (NPLiveLagTracker) | rate | JSON {type,period,excess,checks,settle,cooldown,reference,action,margin,rate,release}' },
  'seek-action': { type: 'string', default: '', help: 'currentTime (video.currentTime = seekRange().end) or goToLive (player.goToLive()); overrides the rule' },
  'outage-at-play': { type: 'number', default: -1, help: 'induce an outage this many seconds after the first presented frame (-1 = none); length and mode: --outage-secs, --outage-mode' },
  'load-delay': { type: 'number', default: 2, help: 'seconds between "playlist stops answering 503" and player.load() (Cast LOAD round trip + receiver start)' },
  'join-phase': { type: 'number', default: -1, help: '0..1: call player.load() at this fraction of a segment after a segment is published (-1 = wherever --load-delay falls)' },
  'pixel-every': { type: 'number', default: 1, help: 'read the burnt-in frame counter on every Nth presented frame (0 = never: no delay figures)' },
  'sample-ms': { type: 'number', default: 250, help: 'period of the timeline samples (seekRange, currentTime, buffered ahead)' },
  'muted': { type: 'bool', default: false, help: 'mute the video element' },
  'browser-channel': { type: 'string', default: '', help: 'Playwright channel: "" = headless shell (default), "chromium" = full Chromium in new headless mode' },
  'browser-args': { type: 'json', default: [], help: 'extra Chromium arguments, JSON array' },
  'console-filter': { type: 'string', default: '', help: 'keep only the browser console lines matching this regular expression (useful with --shaka-debug)' },
  'console-lines': { type: 'number', default: 300, help: 'number of browser console lines kept in the result' },
  'start-timeout': { type: 'number', default: 40, help: 'seconds allowed between player.load() and the first presented frame' },
  'quiet': { type: 'bool', default: false, help: 'print nothing but errors' },
  'help': { type: 'bool', default: false, help: 'show this help' },
};
const SPEC = Object.assign({}, ORIGIN_SPEC, RUN_SPEC);
SPEC.port = Object.assign({}, ORIGIN_SPEC.port, { default: 0 });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
function requirePlaywright() {
  for (const candidate of ['playwright', '/opt/node-tools/node_modules/playwright']) { try { return require(candidate); } catch (_) { /* next */ } }
  throw new Error('playwright not found (set NODE_PATH)');
}
function getJson(url, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { agent: false }, (response) => {
      const chunks = []; response.on('data', (c) => chunks.push(c));
      response.on('end', () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch (error) { reject(error); } });
    });
    request.setTimeout(timeoutMs, () => request.destroy(new Error('timeout ' + url)));
    request.on('error', reject);
  });
}
function merge(base, extra) {
  const out = Array.isArray(base) ? base.slice() : Object.assign({}, base);
  for (const [key, value] of Object.entries(extra || {})) out[key] = value && typeof value === 'object' && !Array.isArray(value) && out[key] && typeof out[key] === 'object' ? merge(out[key], value) : value;
  return out;
}
function shakaFile(O) {
  if (O.shakaFile) return path.resolve(O.shakaFile);
  const variant = O.shakaDebug ? 'compiled.debug' : 'compiled';
  const file = path.join(HERE, 'vendor', `shaka-player-${O.shakaVersion}.${variant}.js`);
  if (!fs.existsSync(file) || fs.statSync(file).size < 100000) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const url = `https://ajax.googleapis.com/ajax/libs/shaka-player/${O.shakaVersion}/shaka-player.${variant}.js`;
    execFileSync('curl', ['-fsSL', '--max-time', '60', '-o', file + '.part', url], { stdio: ['ignore', 'ignore', 'inherit'] });
    fs.renameSync(file + '.part', file);
  }
  return file;
}
function seekRule(O) {
  let rule;
  if (O.seekRule === 'none' || !O.seekRule) rule = { type: 'none' };
  else if (O.seekRule === 'tracker') rule = { type: 'tracker' };
  else if (O.seekRule === 'rate') rule = { type: 'rate' };
  else rule = JSON.parse(O.seekRule);
  if (O.seekAction && rule.type !== 'none') rule.action = O.seekAction;
  return rule;
}

const cleanups = []; let cleaned = false;
async function cleanup() { if (cleaned) return; cleaned = true; for (const fn of cleanups.reverse()) { try { await fn(); } catch (_) { /* best effort */ } } }

async function main() {
  let O;
  try { O = parseArgs(process.argv.slice(2), SPEC).options; } catch (error) { console.error(error.message); process.exit(2); }
  if (O.help) { console.log('node run.js [options]\n\nRun options:\n' + usage(RUN_SPEC) + '\n\nOrigin options (passed to origin.js):\n' + usage(ORIGIN_SPEC)); process.exit(0); }
  const log = (...a) => { if (!O.quiet) console.error(`[${O.label}]`, ...a); };
  const outFile = path.resolve(O.out || path.join(HERE, 'results', `${O.label}.json`));
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  const config = O.config === 'receiver' ? RECEIVER_CONFIG : O.config === 'shaka' ? {} : JSON.parse(O.config.startsWith('@') ? fs.readFileSync(O.config.slice(1), 'utf8') : O.config);
  const playerConfig = merge(config, O.configMerge || {});
  const rule = seekRule(O);
  const shaka = shakaFile(O);

  const bail = (code) => cleanup().then(() => process.exit(code));
  for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => bail(130));
  const watchdog = setTimeout(() => { console.error(`[${O.label}] watchdog: run exceeded its time budget`); bail(3); }, (O.duration + O.startTimeout + O.loadDelay + 90) * 1000);
  cleanups.push(() => clearTimeout(watchdog));

  // ---- origin
  let manifestUrl = O.originUrl, controlUrl, origin = null;
  if (!manifestUrl) {
    const args = [path.join(HERE, 'origin.js'), ...toArgv(O, ORIGIN_SPEC)];
    origin = spawn(process.execPath, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    cleanups.push(() => new Promise((resolve) => {
      if (origin.exitCode !== null || origin.signalCode) return resolve();
      origin.once('exit', resolve); origin.kill('SIGTERM');
      setTimeout(() => { try { origin.kill('SIGKILL'); } catch (_) { /* gone */ } resolve(); }, 1500);
    }));
    let stderr = ''; origin.stderr.on('data', (c) => { stderr = (stderr + c).slice(-2000); });
    const ready = await new Promise((resolve, reject) => {
      let buffer = '';
      origin.stdout.on('data', (c) => {
        buffer += c; let i;
        while ((i = buffer.indexOf('\n')) >= 0) {
          const line = buffer.slice(0, i); buffer = buffer.slice(i + 1);
          try { const e = JSON.parse(line); if (e.event === 'ready') resolve(e); if (e.event === 'fatal') reject(new Error('origin: ' + e.error + ' ' + (e.log || []).join(' | '))); } catch (_) { /* not JSON */ }
        }
      });
      origin.once('exit', (code) => reject(new Error(`origin exited (${code}) ${stderr}`)));
      setTimeout(() => reject(new Error('origin did not start')), 10000);
    });
    manifestUrl = ready.url; controlUrl = ready.control;
    log(`origin ${ready.url} (ffmpeg pid ${ready.ffmpegPid})`);
  } else controlUrl = new URL('/control/', manifestUrl).toString();

  // ---- page server (another origin than the stream, as on the receiver: CORS applies)
  const server = http.createServer((request, response) => {
    const name = request.url.split('?')[0];
    const file = name === '/player.html' ? path.join(HERE, 'player.html') : name === '/shaka.js' ? shaka : null;
    if (!file) { response.writeHead(404); response.end(); return; }
    response.writeHead(200, { 'Content-Type': name.endsWith('.js') ? 'text/javascript' : 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    fs.createReadStream(file).pipe(response);
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(O.pagePort, '127.0.0.1', resolve); });
  cleanups.push(() => new Promise((resolve) => { server.close(resolve); server.closeAllConnections && server.closeAllConnections(); }));
  const pageBase = `http://127.0.0.1:${server.address().port}`;

  // ---- browser
  const { chromium } = requirePlaywright();
  const launch = { headless: true, args: ['--autoplay-policy=no-user-gesture-required', ...O.browserArgs] };
  if (O.browserChannel) launch.channel = O.browserChannel;
  const browser = await chromium.launch(launch);
  cleanups.push(() => Promise.race([browser.close(), sleep(5000)]));
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  const consoleLog = [];
  const consoleFilter = O.consoleFilter ? new RegExp(O.consoleFilter, 'i') : null;
  page.on('console', (m) => { const text = m.text(); if (consoleLog.length < O.consoleLines && (!consoleFilter || consoleFilter.test(text))) consoleLog.push(`${m.type()}: ${text.slice(0, 400)}`); });
  page.on('pageerror', (e) => consoleLog.push('pageerror: ' + String(e).slice(0, 400)));

  const originStats0 = await getJson(controlUrl + 'stats');
  const fps = originStats0.options.fps;
  const params = {
    manifestUrl, controlUrl, shakaUrl: pageBase + '/shaka.js', config: playerConfig, seekRule: rule, muted: O.muted,
    pattern: originStats0.derived.pattern, pixelEvery: O.pixelEvery, sampleMs: O.sampleMs,
    maxFrames: Math.ceil((O.duration + O.startTimeout + 30) * fps * 1.3),
  };
  const meta = { label: O.label, startedAt: new Date().toISOString(), command: process.argv.slice(2), options: O, warmup: O.warmup, freezeMs: O.freezeMs, browserVersion: browser.version(), shakaFile: path.basename(shaka), node: process.version };

  let pageData = null, failure = null;
  try {
    await page.goto(`${pageBase}/player.html#${encodeURIComponent(JSON.stringify(params))}`);
    await page.waitForFunction(() => window.bench && (window.bench.state === 'ready' || window.bench.state === 'error'), null, { timeout: 20000, polling: 50 });
    if (await page.evaluate(() => window.bench.state) === 'error') throw new Error('page: ' + await page.evaluate(() => window.bench.error));

    // the sender issues LOAD when the playlist stops answering 503
    const deadline = Date.now() + 30000; let info;
    for (;;) { info = await getJson(controlUrl + 'playlist'); if (info.ready) break; if (Date.now() > deadline) throw new Error('playlist never became ready'); await sleep(20); }
    await sleep(O.loadDelay * 1000);
    if (O.joinPhase >= 0) {
      info = await getJson(controlUrl + 'playlist');
      const since = info.now - info.lastPublishedAt, target = O.joinPhase * info.segmentMs;
      await sleep(((target - since) % info.segmentMs + info.segmentMs) % info.segmentMs);
    }
    log('player.load()');
    await page.evaluate(() => { window.bench.go(); });
    await page.waitForFunction(() => window.bench.firstFrameAt !== null || window.bench.state === 'error', null, { timeout: O.startTimeout * 1000, polling: 20 });
    if (await page.evaluate(() => window.bench.state) === 'error') throw new Error('page: ' + await page.evaluate(() => window.bench.error));
    log(`first frame; measuring ${O.duration} s`);
    if (O.outageAtPlay >= 0) { await getJson(`${controlUrl}outage?in=${O.outageAtPlay}&secs=${O.outageSecs}&mode=${O.outageMode}`); log(`outage of ${O.outageSecs} s scheduled in ${O.outageAtPlay} s (${O.outageMode})`); }
    await sleep(O.duration * 1000);
  } catch (error) { failure = error; }
  try { pageData = await page.evaluate(() => window.bench.finish()); } catch (error) { failure = failure || error; }
  let originStats = null;
  try { originStats = await getJson(controlUrl + 'stats', 10000); } catch (error) { failure = failure || error; }
  await cleanup();

  if (!pageData) { console.error(`[${O.label}] FAILED: ${failure && failure.message}`); if (consoleLog.length) console.error(consoleLog.slice(-10).join('\n')); process.exit(1); }
  const raw = { meta, page: pageData, originStats };
  const result = analyze(raw);
  result.browser = { version: meta.browserVersion, channel: O.browserChannel || 'headless-shell', console: consoleLog.slice(0, O.consoleLines) };
  if (failure) { result.verdict.ok = false; result.verdict.problems.push('run: ' + failure.message); }
  fs.writeFileSync(outFile, JSON.stringify(result));
  if (O.raw) fs.writeFileSync(outFile.replace(/\.json$/, '') + '.raw.json', JSON.stringify(raw));
  const line = summary(result); line.file = outFile;
  if (!O.quiet) console.log(JSON.stringify(line));
  process.exit(result.verdict.ok ? 0 : 1);
}

main().catch(async (error) => { console.error('run.js: ' + (error && error.stack || error)); await cleanup(); process.exit(1); });
