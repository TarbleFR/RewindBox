// Progressive fragmented-MP4 experiment: one endless HTTP response played by <video src>, as the default
// receiver's plain media element path does (a.src = url; a.autoplay = true). Measures glass-to-glass delay.
const http = require('http'); const { spawn } = require('child_process'); const path = require('path');
const { chromium } = require(process.env.PW || 'playwright');
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i > 0 ? process.argv[i + 1] : d; };
const DURATION = +arg('duration', 40), FRAG = arg('frag', 'frame'), FPS = +arg('fps', 60), AUDIO = arg('audio', 'aac');
const OUTAGE_AT = +arg('outage-at', 0), OUTAGE_SECS = +arg('outage-secs', 0), RATE_RULE = arg('rate-rule', 'none');
const PLAY_AFTER = +arg('play-after', -1), BACKLOG = +arg('backlog', 0), GOP = +arg('gop', 1), CHUNK_DELAY = +arg('net-delay', 0), LABEL = arg('label', 'prog');
let init = null, clients = new Set(), frags = [], pending = Buffer.alloc(0), boxes = [], vTimescale = 0, vTrack = 1, paused = false, held = [];
function u32(b, o) { return b.readUInt32BE(o); }
function walk(buf, start, end, cb) { let o = start; while (o + 8 <= end) { const size = u32(buf, o); const type = buf.toString('latin1', o + 4, o + 8); if (size < 8 || o + size > end) break; cb(type, o + 8, o + size); o += size; } }
function parseInit(buf) { // find video track id + its mdhd timescale
  walk(buf, 0, buf.length, (t, s, e) => { if (t !== 'moov') return; walk(buf, s, e, (t2, s2, e2) => { if (t2 !== 'trak') return; let id = 0, ts = 0, handler = '';
    walk(buf, s2, e2, (t3, s3, e3) => { if (t3 === 'tkhd') { const v = buf[s3]; id = u32(buf, s3 + (v === 1 ? 20 : 12)); }
      if (t3 === 'mdia') walk(buf, s3, e3, (t4, s4) => { if (t4 === 'mdhd') { const v = buf[s4]; ts = u32(buf, s4 + (v === 1 ? 20 : 12)); } if (t4 === 'hdlr') handler = buf.toString('latin1', s4 + 8, s4 + 12); }); });
    if (handler === 'vide') { vTrack = id; vTimescale = ts; } }); });
}
function fragTime(buf) { let out = null; walk(buf, 0, buf.length, (t, s, e) => { if (t !== 'moof') return; walk(buf, s, e, (t2, s2, e2) => { if (t2 !== 'traf') return; let id = 0, dt = null;
  walk(buf, s2, e2, (t3, s3) => { if (t3 === 'tfhd') id = u32(buf, s3 + 4); if (t3 === 'tfdt') { const v = buf[s3]; dt = v === 1 ? Number(buf.readBigUInt64BE(s3 + 4)) : u32(buf, s3 + 4); } });
  if (id === vTrack && dt !== null) out = dt / vTimescale; }); }); return out; }
function send(chunk, t) { for (const c of clients) {
  if (c.state === 'wait') { if (t === null) continue; const idx = Math.round(t * FPS); if (idx % Math.round(FPS * GOP) !== 0) continue; c.state = 'fill'; c.t0 = t; c.buf = []; }
  if (c.state === 'fill') { c.buf.push(chunk); if (t !== null && (t - c.t0) * 1000 >= BACKLOG) { c.res.write(Buffer.concat(c.buf)); c.buf = null; c.state = 'live'; c.startT = c.t0; } continue; }
  if (CHUNK_DELAY) setTimeout(() => c.res.write(chunk), CHUNK_DELAY); else c.res.write(chunk); } }
function onData(d) { pending = Buffer.concat([pending, d]);
  for (;;) { if (pending.length < 8) return; const size = u32(pending, 0); const type = pending.toString('latin1', 4, 8); if (size < 8 || pending.length < size) return;
    const box = pending.subarray(0, size); pending = pending.subarray(size);
    if (!init) { boxes.push(box); if (type === 'moov') { init = Buffer.concat(boxes); boxes = []; parseInit(init); } continue; }
    boxes.push(box); if (type === 'mdat') { const frag = Buffer.concat(boxes); boxes = []; const t = fragTime(frag); const now = Date.now();
      if (t !== null) frags.push([t, now]); if (paused) held.push([frag, t]); else send(frag, t); } } }
const args = ['-hide_banner', '-loglevel', 'error', '-re', '-f', 'lavfi', '-i', `testsrc2=size=640x360:rate=${FPS}`];
if (AUDIO !== 'none') args.push('-re', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000');
args.push('-c:v', 'libx264', '-profile:v', 'baseline', '-preset', 'ultrafast', '-tune', 'zerolatency', '-g', String(Math.round(FPS * GOP)), '-keyint_min', String(Math.round(FPS * GOP)), '-sc_threshold', '0', '-b:v', '1000k', '-pix_fmt', 'yuv420p', '-video_track_timescale', '90000');
if (AUDIO === 'aac') args.push('-c:a', 'aac', '-b:a', '128k', '-ac', '2');
const mov = FRAG === 'frame' ? 'frag_every_frame+empty_moov+default_base_moof' : 'empty_moov+default_base_moof';
args.push('-movflags', mov); if (FRAG !== 'frame') args.push('-frag_duration', String(Math.round(+FRAG * 1e6)));
args.push('-f', 'mp4', 'pipe:1');
const ff = spawn('ffmpeg', args, { stdio: ['ignore', 'pipe', 'inherit'] }); ff.stdout.on('data', onData);
const server = http.createServer((req, res) => {
  if (req.url.startsWith('/live.mp4')) { res.writeHead(200, { 'Content-Type': 'video/mp4', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*', 'Connection': 'close' }); res.write(init); const c = { res, state: 'wait' }; clients.add(c); req.on('close', () => clients.delete(c)); return; }
  if (req.url === '/') { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(`<!doctype html><video id=v muted playsinline style="width:640px;height:360px"></video><script>
    const v = document.getElementById('v'); window.samples = []; window.events = [];
    for (const e of ['waiting','stalled','playing','canplay','loadedmetadata','error','ratechange']) v.addEventListener(e, () => events.push([e, performance.timeOrigin + performance.now(), v.currentTime]));
    const cb = (now, m) => { samples.push([performance.timeOrigin + m.expectedDisplayTime, m.mediaTime, m.presentedFrames]); v.requestVideoFrameCallback(cb); }; v.requestVideoFrameCallback(cb);
    v.src = '/live.mp4'; v.autoplay = ${PLAY_AFTER < 0}; if (${PLAY_AFTER} >= 0) setTimeout(() => v.play().catch(e => events.push(['playerr', 0, 0])), ${PLAY_AFTER});</script>`); return; }
  res.writeHead(404); res.end(); });
(async () => {
  while (!init) await new Promise(r => setTimeout(r, 50));
  await new Promise(r => server.listen(0, '127.0.0.1', r)); const port = server.address().port;
  const browser = await chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] }); const page = await browser.newPage();
  const t0 = Date.now(); await page.goto(`http://127.0.0.1:${port}/`);
  if (OUTAGE_AT) { setTimeout(() => { paused = true; }, OUTAGE_AT * 1000); setTimeout(() => { paused = false; for (const [f, t] of held) send(f, t); held = []; }, (OUTAGE_AT + OUTAGE_SECS) * 1000); }
  let rateTimer = null;
  if (RATE_RULE !== 'none') { const [hi, lo, rate] = RATE_RULE.split(',').map(Number); // lag above hi -> rate; below lo -> 1
    rateTimer = setInterval(async () => { try { const ct = await page.evaluate(() => [document.getElementById('v').currentTime, document.getElementById('v').playbackRate]); const newest = frags.length ? frags[frags.length - 1][0] : 0; const lag = newest - ct[0];
      if (lag > hi && ct[1] === 1) await page.evaluate(r => { document.getElementById('v').playbackRate = r; }, rate); else if (lag < lo && ct[1] !== 1) await page.evaluate(() => { document.getElementById('v').playbackRate = 1; }); } catch (e) {} }, 250); }
  await new Promise(r => setTimeout(r, DURATION * 1000)); if (rateTimer) clearInterval(rateTimer);
  const { samples, events } = await page.evaluate(() => ({ samples: window.samples, events: window.events }));
  await browser.close(); ff.kill('SIGKILL'); server.close();
  // join: capture wall clock of media time t = arrival of the fragment whose tfdt is the largest <= t
  let j = 0; const lat = []; for (const [wall, mt] of samples) { while (j + 1 < frags.length && frags[j + 1][0] <= mt + 1e-4) j++; if (frags[j][0] <= mt + 1e-4) lat.push([wall, wall - frags[j][1], mt]); }
  const q = (a, p) => { const s = [...a].sort((x, y) => x - y); return s.length ? Math.round(s[Math.min(s.length - 1, Math.floor(p * s.length))]) : null; };
  const seg = (from, to) => lat.filter(x => x[0] >= t0 + from * 1000 && x[0] < t0 + to * 1000).map(x => x[1]);
  const gaps = []; for (let i = 1; i < samples.length; i++) gaps.push(samples[i][0] - samples[i - 1][0]);
  const first = samples.length ? samples[0][0] - t0 : null; const steady = seg(5, DURATION);
  const out = { label: LABEL, frag: FRAG, gop: GOP, playAfter: PLAY_AFTER, backlog: BACKLOG, audio: AUDIO, fps: FPS, firstFrameMs: first && Math.round(first), frames: samples.length, presentedFps: +(samples.length / Math.max(1, DURATION - (first || 0) / 1000)).toFixed(1),
    delayMs: { median: q(steady, 0.5), p05: q(steady, 0.05), p95: q(steady, 0.95), max: q(steady, 0.999) }, first5s: q(seg(0, 5), 0.5), last5s: q(seg(DURATION - 5, DURATION), 0.5),
    longGapsOver50ms: gaps.filter(g => g > 50).length, longestGapMs: Math.round(Math.max(0, ...gaps)), events: events.map(e => e[0]).reduce((m, e) => (m[e] = (m[e] || 0) + 1, m), {}) };
  if (OUTAGE_AT) out.outage = { beforeMs: q(seg(Math.max(5, OUTAGE_AT - 6), OUTAGE_AT - 0.5), 0.5), afterMs: q(seg(OUTAGE_AT + OUTAGE_SECS + 3, OUTAGE_AT + OUTAGE_SECS + 9), 0.5), endMs: q(seg(DURATION - 5, DURATION), 0.5) };
  console.log(JSON.stringify(out)); process.exit(0);
})();
