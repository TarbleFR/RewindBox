// RewindBox Cast receiver bench: node run.mjs [frames|mp4] [seconds]
// Plays the stand-in phone's stream in the receiver page (lab mode, no Cast framework) in Chromium and measures, per
// picture, the time from leaving the encoder to being drawn: frames engine = the drawImage call of that picture
// (decoded VideoFrame timestamp), mp4 engine = the expected display time that requestVideoFrameCallback reports.
// The bar code of the picture is read back once a second to check that the right picture is the one shown.
// Not measured here: the Chromecast's own decoder and compositor, the TV, Wi-Fi, ReplayKit and VideoToolbox.
import { execFileSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { startPhone } from './phone.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const engine = process.argv[2] === 'mp4' ? 'mp4' : 'frames', seconds = Number(process.argv[3] ?? 20);
const site = mkdtempSync(join(tmpdir(), 'rewindbox-cast-site-'));
execFileSync('node', [join(here, '../../../../tools/neoplay-cast-receiver/site.mjs'), site], { stdio: 'inherit' });
const scratch = process.env.REPLAY_DIR;
const phone = await startPhone({ site, replay: engine === 'mp4' && scratch ? { file: join(scratch, 'stream-normal.mp4'), times: join(scratch, 'stream-normal.times') } : null });
const { chromium } = createRequire(import.meta.url)('playwright');
const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const logs = []; page.on('console', message => logs.push(message.text())); page.on('pageerror', error => logs.push(`pageerror ${error.message}`));
await page.addInitScript(() => {
  window.benchDraws = [];
  const draw = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (image, ...rest) {
    if (typeof VideoFrame === 'function' && image instanceof VideoFrame) window.benchDraws.push([image.timestamp, performance.timeOrigin + performance.now()]);
    return draw.call(this, image, ...rest);
  };
});
const url = `http://127.0.0.1:${phone.port}/cast/index.html?lab=1&engine=${engine}&url=${encodeURIComponent(`http://127.0.0.1:${phone.port}/s/lab/${engine === 'mp4' ? 'live.mp4' : 'frames'}`)}`;
await page.goto(url);
await page.evaluate(() => {
  window.benchShown = []; window.benchChecks = { ok: 0, wrong: 0 };
  const video = document.getElementById('video'), canvas = document.getElementById('canvas');
  const probe = new OffscreenCanvas(1280, 720), context = probe.getContext('2d', { willReadFrequently: true });
  const barcode = source => { context.drawImage(source, 0, 0, 1280, 720); const row = context.getImageData(0, 20, 1280, 1).data; let n = 0; for (let bit = 0; bit < 16; bit++) if (row[(bit * 80 + 40) * 4] > 128) n |= 1 << bit; return n; };
  if (typeof video.requestVideoFrameCallback === 'function') {
    const onFrame = (now, meta) => { window.benchShown.push([Math.round(meta.mediaTime * 60), performance.timeOrigin + (meta.expectedDisplayTime ?? now)]); video.requestVideoFrameCallback(onFrame); };
    video.requestVideoFrameCallback(onFrame);
  }
  setInterval(() => {
    const draws = window.benchDraws, shown = window.benchShown;
    const expected = !canvas.hidden && draws.length ? Math.round(draws[draws.length - 1][0] * 60 / 1e6) % 65536 : !video.hidden && shown.length ? shown[shown.length - 1][0] % 65536 : null;
    if (expected === null) return;
    const read = barcode(canvas.hidden ? video : canvas);
    if (Math.abs(read - expected) <= 1) window.benchChecks.ok++; else window.benchChecks.wrong++;
  }, 1000);
});
await page.waitForTimeout(seconds * 1000);
const audioTrail = await page.evaluate(() => window.neoplayCast.sent.filter(message => message.type === 'stats').map(message => [message.at, message.audio?.fillMs, message.audio?.targetMs, message.audio?.underruns, message.second?.presented]));
const result = await page.evaluate(() => ({ draws: window.benchDraws, shown: window.benchShown, checks: window.benchChecks, stats: window.neoplayCast.sent.filter(message => message.type === 'stats').slice(-3, -2)[0] ?? null, sent: window.neoplayCast.sent.map(message => message.type) }));
const times = await (await fetch(`http://127.0.0.1:${phone.port}/times`)).json();
const samples = engine === 'mp4' ? result.shown : result.draws.map(([pts, at]) => [Math.round(pts * 60 / 1e6), at]);
const start = times.produced.find(Boolean) + 3000, seen = new Set(), latencies = [];
for (const [n, at] of samples) { if (seen.has(n) || !times.produced[n] || times.produced[n] < start) continue; seen.add(n); latencies.push(at - times.produced[n]); }
latencies.sort((a, b) => a - b);
const pick = q => latencies.length ? Math.round(latencies[Math.min(latencies.length - 1, Math.floor(latencies.length * q))] * 10) / 10 : null;
const producedAfter = times.produced.filter(t => t >= start).length;
console.log(JSON.stringify({ audioTrail, engine, seconds, pictures: { produced: producedAfter, shown: latencies.length }, latencyMs: { p5: pick(0.05), median: pick(0.5), p95: pick(0.95), max: pick(0.999) }, barcode: result.checks, messages: [...new Set(result.sent)], stats: result.stats, logs: logs.slice(-8), phoneErrors: phone.state.stderr().slice(-300) }, null, 1));
await browser.close(); phone.stop();
