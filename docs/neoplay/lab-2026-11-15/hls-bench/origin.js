#!/usr/bin/env node
'use strict';
// NeoPlay lab origin: stands in for the iPhone sender (NPMuxer + NPSegmentStore + NPHTTPServer).
//
//   ffmpeg (-re, test picture with a burnt-in binary frame counter + sine, x264 baseline zerolatency, AAC)
//     -> fragmented MP4 on a pipe -> THIS process cuts segments (and LL-HLS parts), keeps the bounded
//     store, writes the playlist and serves everything over HTTP/1.1 "Connection: close".
//
// Every playlist policy and every network impairment is a command-line parameter (lib/origin-options.js).
// The capture wall clock of every frame is recorded (showinfo line of frame n -> origin clock) and served
// on /control/capture, so the page can compute glass-to-glass delay from the frame number it reads in the
// picture. See README.md.

const net = require('net');
const { spawn } = require('child_process');
const { performance } = require('perf_hooks');
const { parseArgs, usage } = require('./lib/args');
const SPEC = require('./lib/origin-options');

const PATTERN = { block: 16, bits: 20, x: 0, y: 0 };            // [white][black][bit0..bit19][parity]
PATTERN.blocks = PATTERN.bits + 3;

// Origin clock: milliseconds since the Unix epoch, sub-millisecond, monotonic.
const oclock = () => performance.timeOrigin + performance.now();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));

function quantiles(values, qs = [0.01, 0.05, 0.5, 0.95, 0.99]) {
  if (!values.length) return null;
  const sorted = Float64Array.from(values).sort();
  const pick = (q) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))];
  const out = { n: sorted.length, min: sorted[0], max: sorted[sorted.length - 1] };
  for (const q of qs) out['p' + String(Math.round(q * 100)).padStart(2, '0')] = pick(q);
  for (const key of Object.keys(out)) if (key !== 'n') out[key] = Math.round(out[key] * 1000) / 1000;
  return out;
}

// ---------------------------------------------------------------- ISO BMFF helpers
function* boxes(buf, start = 0, end = buf.length) {
  let p = start;
  while (p + 8 <= end) {
    let size = buf.readUInt32BE(p), header = 8;
    const type = buf.toString('latin1', p + 4, p + 8);
    if (size === 1) { if (p + 16 > end) return; size = Number(buf.readBigUInt64BE(p + 8)); header = 16; } else if (size === 0) size = end - p;
    if (size < header || p + size > end) return;
    yield { type, start: p, end: p + size, body: p + header };
    p += size;
  }
}
const child = (buf, parent, type) => { for (const b of boxes(buf, parent.body, parent.end)) if (b.type === type) return b; return null; };

function parseMoov(buf) {
  const tracks = {};
  for (const top of boxes(buf)) {
    if (top.type !== 'moov') continue;
    for (const b of boxes(buf, top.body, top.end)) {
      if (b.type === 'trak') {
        const tkhd = child(buf, b, 'tkhd'), mdia = child(buf, b, 'mdia');
        if (!tkhd || !mdia) continue;
        const id = buf.readUInt32BE(tkhd.body + (buf[tkhd.body] === 1 ? 20 : 12));
        const mdhd = child(buf, mdia, 'mdhd'), hdlr = child(buf, mdia, 'hdlr');
        const timescale = buf.readUInt32BE(mdhd.body + (buf[mdhd.body] === 1 ? 20 : 12));
        const handler = buf.toString('latin1', hdlr.body + 8, hdlr.body + 12);
        tracks[id] = Object.assign(tracks[id] || {}, { id, timescale, handler });
      } else if (b.type === 'mvex') {
        for (const t of boxes(buf, b.body, b.end)) {
          if (t.type !== 'trex') continue;
          const id = buf.readUInt32BE(t.body + 4);
          tracks[id] = Object.assign(tracks[id] || {}, { defaultDuration: buf.readUInt32BE(t.body + 12), defaultFlags: buf.readUInt32BE(t.body + 20) });
        }
      }
    }
  }
  return tracks;
}

// Returns, per track id, { count, duration (ticks), base (ticks), key (first sample is a sync sample) }.
function parseMoof(buf, tracks) {
  const out = {};
  for (const top of boxes(buf)) {
    if (top.type !== 'moof') continue;
    for (const traf of boxes(buf, top.body, top.end)) {
      if (traf.type !== 'traf') continue;
      let id = 0, defDuration = null, defFlags = null, base = 0, count = 0, duration = 0, firstFlags = null;
      for (const b of boxes(buf, traf.body, traf.end)) {
        if (b.type === 'tfhd') {
          const flags = buf.readUInt32BE(b.body) & 0xffffff; let p = b.body + 4;
          id = buf.readUInt32BE(p); p += 4;
          if (flags & 0x1) p += 8;
          if (flags & 0x2) p += 4;
          if (flags & 0x8) { defDuration = buf.readUInt32BE(p); p += 4; }
          if (flags & 0x10) p += 4;
          if (flags & 0x20) { defFlags = buf.readUInt32BE(p); p += 4; }
        } else if (b.type === 'tfdt') {
          base = buf[b.body] === 1 ? Number(buf.readBigUInt64BE(b.body + 4)) : buf.readUInt32BE(b.body + 4);
        } else if (b.type === 'trun') {
          const flags = buf.readUInt32BE(b.body) & 0xffffff; let p = b.body + 4;
          const n = buf.readUInt32BE(p); p += 4;
          if (flags & 0x1) p += 4;
          let first = null;
          if (flags & 0x4) { first = buf.readUInt32BE(p); p += 4; }
          const track = tracks[id] || {};
          for (let i = 0; i < n; i++) {
            if (flags & 0x100) { duration += buf.readUInt32BE(p); p += 4; } else duration += defDuration ?? track.defaultDuration ?? 0;
            if (flags & 0x200) p += 4;
            if (flags & 0x400) { if (i === 0 && first === null) first = buf.readUInt32BE(p); p += 4; }
            if (flags & 0x800) p += 4;
          }
          if (count === 0) firstFlags = first ?? defFlags ?? track.defaultFlags ?? 0;
          count += n;
        }
      }
      if (id) out[id] = { count, duration, base, key: count > 0 && !(firstFlags & 0x10000) };
    }
  }
  return out;
}

// frag_every_frame output of ffmpeg carries unusable video timing (sample duration 0, repeated tfdt): rewrite it.
// Constant frame rate: frame n starts at base and lasts `duration` ticks.
function patchVideoTiming(moof, videoId, base, duration) {
  for (const top of boxes(moof)) {
    if (top.type !== 'moof') continue;
    for (const traf of boxes(moof, top.body, top.end)) {
      if (traf.type !== 'traf') continue;
      let id = 0, tfhd = null, tfdt = null;
      for (const b of boxes(moof, traf.body, traf.end)) { if (b.type === 'tfhd') { tfhd = b; id = moof.readUInt32BE(b.body + 4); } else if (b.type === 'tfdt') tfdt = b; }
      if (id !== videoId) continue;
      if (tfhd) { const flags = moof.readUInt32BE(tfhd.body) & 0xffffff; let p = tfhd.body + 8; if (flags & 0x1) p += 8; if (flags & 0x2) p += 4; if (flags & 0x8) moof.writeUInt32BE(duration, p); }
      if (tfdt) { if (moof[tfdt.body] === 1) moof.writeBigUInt64BE(BigInt(base), tfdt.body + 4); else moof.writeUInt32BE(base, tfdt.body + 4); }
    }
  }
}

// ---------------------------------------------------------------- main
function main() {
  let O;
  try { O = parseArgs(process.argv.slice(2), Object.assign({ help: { type: 'bool', default: false, help: 'show this help' } }, SPEC)).options; }
  catch (error) { console.error(String(error.message)); process.exit(2); }
  if (O.help) { console.log('node origin.js [options]\n' + usage(SPEC)); process.exit(0); }

  const [width, height] = O.size.split('x').map(Number);
  const fps = O.fps;
  const frames = (seconds, what) => {
    const n = Math.round(seconds * fps);
    if (n < 1 || Math.abs(n / fps - seconds) > 1e-6) { console.error(`--${what} ${seconds}: not a whole number of frames at ${fps} fps`); process.exit(2); }
    return n;
  };
  const segFrames = frames(O.seg, 'seg');
  const gopFrames = O.gop > 0 ? frames(O.gop, 'gop') : segFrames;
  const partFrames = O.part > 0 ? frames(O.part, 'part') : 0;
  if (segFrames % gopFrames) { console.error('--gop must divide --seg'); process.exit(2); }
  if (partFrames && segFrames % partFrames) { console.error('--part must divide --seg'); process.exit(2); }
  if (!(width >= PATTERN.block * PATTERN.blocks) || !(height >= 2 * PATTERN.block)) { console.error('--size too small for the frame counter'); process.exit(2); }
  const targetDuration = O.targetDuration === 'auto' ? Math.ceil(O.seg - 1e-9) : Number(O.targetDuration);
  const partHoldBack = partFrames ? (O.partHoldBack > 0 ? O.partHoldBack : 3 * O.part) : 0;
  const prefix = O.prefix.endsWith('/') ? O.prefix : O.prefix + '/';
  const longSegments = new Set(O.longSegments.split(',').filter(Boolean).map(Number));

  const S = {
    startedAt: oclock(),
    init: {},                 // epoch -> Buffer
    epoch: -1,
    segments: [],             // complete segments still in the store
    open: null,               // segment being received (parts mode: its complete parts are already served)
    nextSequence: 0,
    published: [],            // light record of every segment ever published
    frameCount: 0,            // video frames received from ffmpeg (= index of the next frame)
    videoSamples: 0,
    capture: [],              // capture[n] = origin clock when frame n left the filter graph for the encoder
    requests: [],
    outages: [],              // { start, end, mode }
    shape: { delayMs: O.delayMs, jitterMs: O.jitterMs, rateKbps: O.rateKbps },
    bucketFree: 0,
    sockets: new Set(),
    conns: { accepted: 0, refused: 0, timedOut: 0 },
    waiters: [],
    ffmpegLog: [],
    ffmpegExit: null,
    irregular: 0,
    firstPlaylistOkAt: null,
  };
  const emit = (event, data) => { if (O.log || event === 'ready' || event === 'fatal') process.stdout.write(JSON.stringify(Object.assign({ event, t: Math.round((oclock() - S.startedAt) * 10) / 10 }, data)) + '\n'); };

  // ------------------------------------------------------------ ffmpeg
  const B = PATTERN.block;
  const bit = (k) => `mod(floor(n/${2 ** k}),2)`;
  const vf = [
    `drawbox=x=${PATTERN.x}:y=${PATTERN.y}:w=${B * PATTERN.blocks}:h=${B}:color=black:t=fill`,
    `drawbox=x=${PATTERN.x}:y=${PATTERN.y}:w=${B}:h=${B}:color=white:t=fill`,
    ...Array.from({ length: PATTERN.bits }, (_, k) => `drawbox=x=${PATTERN.x + (2 + k) * B}:y=${PATTERN.y}:w=${B}:h=${B}:color=white:t=fill:enable='eq(${bit(k)},1)'`),
    `drawbox=x=${PATTERN.x + (2 + PATTERN.bits) * B}:y=${PATTERN.y}:w=${B}:h=${B}:color=white:t=fill:enable='eq(mod(${Array.from({ length: PATTERN.bits }, (_, k) => bit(k)).join('+')},2),1)'`,
    'showinfo=checksum=0',
  ].join(',');
  const ffArgs = [
    '-hide_banner', '-nostats', '-nostdin', '-loglevel', 'info',
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', `testsrc2=size=${width}x${height}:rate=${fps}`,
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
    '-filter:v', vf, '-fps_mode', 'passthrough',
    '-c:v', 'libx264', '-profile:v', 'baseline', '-preset', 'ultrafast', '-tune', 'zerolatency', '-pix_fmt', 'yuv420p',
    '-g', String(gopFrames), '-keyint_min', String(gopFrames), '-sc_threshold', '0', '-bf', '0',
    '-b:v', `${O.bitrate}k`, '-maxrate', `${O.bitrate}k`, '-bufsize', `${Math.round(O.bitrate / 2)}k`,
    '-c:a', 'aac', '-b:a', `${O.audioBitrate}k`, '-ar', '48000', '-ac', '2',
    '-t', String(O.maxSeconds),
    '-f', 'mp4', '-movflags', (partFrames ? '+frag_every_frame' : '+frag_keyframe') + '+empty_moov+default_base_moof',
    '-flush_packets', '1', 'pipe:1',
  ];
  const ff = spawn(O.ffmpeg, ffArgs, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stopping = false;
  const stop = (code) => {
    if (stopping) return; stopping = true;
    try { ff.kill('SIGKILL'); } catch (_) { /* gone */ }
    for (const socket of S.sockets) socket.destroy();
    server.close();
    setTimeout(() => process.exit(code), 50);
  };
  ff.on('error', (error) => { emit('fatal', { error: 'ffmpeg: ' + error.message }); stop(1); });
  ff.on('exit', (code, signal) => { S.ffmpegExit = { code, signal, at: oclock() }; if (!stopping) { emit('fatal', { error: `ffmpeg exited (${code ?? signal})`, log: S.ffmpegLog.slice(-8) }); stop(1); } });

  // stderr: one showinfo line per frame = the capture clock
  let errTail = '';
  const showinfo = /Parsed_showinfo[^\]]*\]\s+n:\s*(\d+)\s+pts:/;
  ff.stderr.on('data', (chunk) => {
    const now = oclock();
    const lines = (errTail + chunk.toString('latin1')).split(/\r?\n/); errTail = lines.pop();
    for (const line of lines) {
      const m = showinfo.exec(line);
      if (m) S.capture[Number(m[1])] = now;
      else if (!/Parsed_showinfo/.test(line) && line.trim()) { S.ffmpegLog.push(line); if (S.ffmpegLog.length > 60) S.ffmpegLog.shift(); }
    }
  });

  // stdout: box stream -> init, fragments
  let pendingBuf = Buffer.alloc(0), initParts = [], prefixBoxes = [], moof = null, tracks = {}, videoId = 0;
  ff.stdout.on('data', (chunk) => {
    pendingBuf = pendingBuf.length ? Buffer.concat([pendingBuf, chunk]) : chunk;
    let consumed = 0;
    for (const box of boxes(pendingBuf)) {
      onBox(box.type, pendingBuf.subarray(box.start, box.end)); consumed = box.end;
    }
    if (consumed) pendingBuf = pendingBuf.subarray(consumed);
  });
  function onBox(type, data) {
    if (type === 'ftyp') { initParts = [data]; return; }
    if (type === 'moov') {
      initParts.push(data);
      const init = Buffer.concat(initParts);
      tracks = parseMoov(init);
      videoId = Number(Object.keys(tracks).find((id) => tracks[id].handler === 'vide'));
      S.epoch += 1; S.init[S.epoch] = init;
      emit('init', { epoch: S.epoch, bytes: init.length, tracks });
      return;
    }
    if (type === 'moof') { moof = data; return; }
    if (type === 'mdat') {
      if (!moof) return;
      if (partFrames) {       // one sample per fragment in this mode
        const timescale = tracks[videoId].timescale, ticks = Math.round(timescale / fps);
        if ((parseMoof(moof, tracks)[videoId] || {}).count === 1) patchVideoTiming(moof, videoId, Math.round(1024 / 48000 * timescale) + S.videoSamples * ticks, ticks);
      }
      const info = parseMoof(moof, tracks)[videoId] || { count: 0, duration: 0, base: 0, key: false };
      S.videoSamples += info.count;
      onFragment({ bytes: Buffer.concat([...prefixBoxes, moof, data]), frames: info.count, ticks: info.duration, key: info.key, at: oclock() });
      moof = null; prefixBoxes = [];
      return;
    }
    if (type === 'styp' || type === 'sidx' || type === 'prft' || type === 'emsg') prefixBoxes.push(data);
  }

  function onFragment(fragment) {
    const timescale = tracks[videoId].timescale;
    if (!S.open) {
      // A segment must start on a key picture; anything before the first one (audio priming) is dropped.
      if (!(fragment.frames > 0 && fragment.key)) {
        if (fragment.frames > 0) { S.irregular += 1; S.frameCount += fragment.frames; } else if (S.frameCount > 0) carry.push(fragment.bytes);
        return;
      }
      S.open = { sequence: S.nextSequence++, epoch: S.epoch, chunks: [], frames: 0, ticks: 0, firstFrame: S.frameCount, parts: [], part: null };
    }
    const open = S.open;
    if (partFrames && !open.part) open.part = { index: open.parts.length, chunks: [], frames: 0, ticks: 0, independent: false, firstFrame: S.frameCount };
    if (partFrames && open.part.frames === 0 && fragment.frames > 0) open.part.independent = fragment.key;
    const pieces = carry.splice(0).concat([fragment.bytes]);     // audio received since the previous segment closed
    open.chunks.push(...pieces); open.frames += fragment.frames; open.ticks += fragment.ticks;
    S.frameCount += fragment.frames;
    if (partFrames) {
      const part = open.part;
      part.chunks.push(...pieces); part.frames += fragment.frames; part.ticks += fragment.ticks;
      if (part.frames >= partFrames) {
        open.parts.push({ index: part.index, bytes: Buffer.concat(part.chunks), duration: part.ticks / timescale, independent: part.independent, firstFrame: part.firstFrame, frames: part.frames, availableAt: fragment.at });
        open.part = null;
        emit('part', { sequence: open.sequence, index: part.index, frames: part.frames });
      }
    }
    if (open.frames >= segFrames * (longSegments.has(open.sequence) ? 2 : 1)) {
      if (open.frames % segFrames) S.irregular += 1;
      const segment = { sequence: open.sequence, epoch: open.epoch, duration: open.ticks / timescale, bytes: Buffer.concat(open.chunks), firstFrame: open.firstFrame, frames: open.frames, parts: open.parts, publishedAt: fragment.at };
      S.open = null;
      S.segments.push(segment);
      S.published.push({ sequence: segment.sequence, firstFrame: segment.firstFrame, frames: segment.frames, duration: segment.duration, bytes: segment.bytes.length, publishedAt: segment.publishedAt });
      prune();
      emit('segment', { sequence: segment.sequence, frames: segment.frames, duration: segment.duration, bytes: segment.bytes.length });
    }
    wake();
  }
  const carry = [];   // audio-only fragments received between two segments (parts mode): prepended to the next one

  function prune() {
    const bytes = () => S.segments.reduce((sum, s) => sum + s.bytes.length, 0);
    while (S.segments.length > O.storeSegments || bytes() > 24 * 1024 * 1024) S.segments.shift();
    const needed = new Set(S.segments.map((s) => s.epoch).concat([S.epoch]));
    for (const key of Object.keys(S.init)) if (!needed.has(Number(key))) delete S.init[key];
  }

  // ------------------------------------------------------------ capture clock
  function captureClock() {
    // Frames of the first two seconds are ignored: ffmpeg starts late and catches up (start-up transient).
    const n = S.capture.length, skip = Math.min(2 * fps, Math.floor(n / 2));
    if (n < 4) return null;
    const step = 1000 / fps, residual = [];
    for (let i = skip; i < n; i++) if (S.capture[i] !== undefined) residual.push(S.capture[i] - i * step);
    if (!residual.length) return null;
    const sorted = Float64Array.from(residual).sort();
    const t0 = sorted[sorted.length >> 1];
    // drift of ffmpeg's -re pacing against the origin clock: median residual of the last tenth minus the first tenth
    const tenth = Math.max(1, Math.floor(residual.length / 10));
    const med = (values) => { const v = Float64Array.from(values).sort(); return v[v.length >> 1] - t0; };
    return { fps, frames: n, ignoredFrames: skip, t0, residualMs: quantiles(Array.from(sorted, (v) => v - t0)), driftMs: Math.round((med(residual.slice(-tenth)) - med(residual.slice(0, tenth))) * 1000) / 1000 };
  }
  const nominalCapture = (clock, frame) => clock.t0 + frame * 1000 / fps;

  // ------------------------------------------------------------ playlist
  const fmt = (n) => String(Math.round(n * 1e6) / 1e6);
  function advertised() {
    let start = S.segments.length, total = 0;
    while (start > 0 && (S.segments.length - start < O.windowSegments || total < O.windowSeconds)) { start -= 1; total += S.segments[start].duration; }
    return S.segments.slice(start);
  }
  function playlist() {
    const list = advertised();
    if (list.length < O.startSegments) return null;
    const lines = ['#EXTM3U', `#EXT-X-VERSION:${O.hlsVersion}`, `#EXT-X-TARGETDURATION:${targetDuration}`];
    const control = [];
    if (partFrames && O.canBlockReload) control.push('CAN-BLOCK-RELOAD=YES');
    if (O.holdBack > 0) control.push(`HOLD-BACK=${fmt(O.holdBack)}`);
    if (partFrames) control.push(`PART-HOLD-BACK=${fmt(partHoldBack)}`);
    if (control.length) lines.push('#EXT-X-SERVER-CONTROL:' + control.join(','));
    if (partFrames) lines.push(`#EXT-X-PART-INF:PART-TARGET=${fmt(O.part)}`);
    if (O.extraTags) lines.push(...O.extraTags.split('|').filter(Boolean));
    lines.push(`#EXT-X-MEDIA-SEQUENCE:${list[0].sequence}`, `#EXT-X-DISCONTINUITY-SEQUENCE:${list[0].epoch}`);
    let previous = null;
    const pdt = (frame) => { const at = S.capture[frame]; if (O.pdt && at !== undefined) lines.push('#EXT-X-PROGRAM-DATE-TIME:' + new Date(at).toISOString()); };
    const partLines = (sequence, parts) => { for (const p of parts) lines.push(`#EXT-X-PART:DURATION=${p.duration.toFixed(6)},URI="part-${sequence}-${p.index}.m4s"${p.independent ? ',INDEPENDENT=YES' : ''}`); };
    list.forEach((item, index) => {
      if (item.epoch !== previous) {
        if (previous !== null) lines.push('#EXT-X-DISCONTINUITY');
        lines.push(`#EXT-X-MAP:URI="init-${item.epoch}.mp4"`); previous = item.epoch;
      }
      pdt(item.firstFrame);
      if (partFrames && index >= list.length - O.partsSegments) partLines(item.sequence, item.parts);
      lines.push(`#EXTINF:${item.duration.toFixed(6)},`, `segment-${item.sequence}.m4s`);
    });
    if (partFrames) {
      const open = S.open;
      if (open && open.parts.length) { pdt(open.firstFrame); partLines(open.sequence, open.parts); }
      if (O.preloadHint) lines.push(`#EXT-X-PRELOAD-HINT:TYPE=PART,URI="part-${open ? open.sequence : S.nextSequence}-${open ? open.parts.length : 0}.m4s"`);
    }
    return { text: lines.join('\n') + '\n', newest: list[list.length - 1], first: list[0], count: list.length };
  }
  function findPart(sequence, index) {
    if (S.open && S.open.sequence === sequence) return S.open.parts[index] || null;
    const segment = S.segments.find((s) => s.sequence === sequence);
    return segment ? segment.parts[index] || null : null;
  }
  const partReached = (sequence, index) => {
    const last = S.segments.length ? S.segments[S.segments.length - 1].sequence : -1;
    if (last >= sequence) return true;
    return !!S.open && S.open.sequence === sequence && index >= 0 && S.open.parts.length > index;
  };
  function wake() { const pending = S.waiters; S.waiters = []; for (const w of pending) { if (w.test()) w.resolve(true); else S.waiters.push(w); } }
  function waitFor(test, timeoutMs) {
    if (test()) return Promise.resolve(true);
    return new Promise((resolve) => {
      const waiter = { test, resolve };
      S.waiters.push(waiter);
      setTimeout(() => { const i = S.waiters.indexOf(waiter); if (i >= 0) { S.waiters.splice(i, 1); resolve(false); } }, timeoutMs);
    });
  }

  // Stream resources. Returns [status, contentType, body, logExtra].
  async function resource(name, query) {
    if (name === 'index.m3u8') {
      if (partFrames && O.canBlockReload && query.has('_HLS_msn')) {
        const msn = Number(query.get('_HLS_msn')), part = query.has('_HLS_part') ? Number(query.get('_HLS_part')) : -1;
        if (!Number.isFinite(msn) || msn > S.nextSequence + 1) return [400, 'text/plain', Buffer.alloc(0), { kind: 'playlist', blocked: true }];
        const blockedFrom = oclock();
        const ok = await waitFor(() => partReached(msn, part) && !!playlist(), 3000 * targetDuration);
        if (!ok) return [503, 'text/plain', Buffer.alloc(0), { kind: 'playlist', blocked: true }];
        const made = playlist();
        return [200, 'application/vnd.apple.mpegurl', Buffer.from(made.text), { kind: 'playlist', blockedMs: oclock() - blockedFrom, newest: made.newest.sequence, first: made.first.sequence, newestAgeMs: oclock() - made.newest.publishedAt }];
      }
      const made = playlist();
      if (!made) return [503, 'text/plain', Buffer.alloc(0), { kind: 'playlist' }];
      if (S.firstPlaylistOkAt === null) S.firstPlaylistOkAt = oclock();
      return [200, 'application/vnd.apple.mpegurl', Buffer.from(made.text), { kind: 'playlist', newest: made.newest.sequence, first: made.first.sequence, count: made.count, newestAgeMs: oclock() - made.newest.publishedAt }];
    }
    let m = /^init-(\d+)\.mp4$/.exec(name);
    if (m && S.init[m[1]]) return [200, 'video/mp4', S.init[m[1]], { kind: 'init' }];
    m = /^segment-(\d+)\.m4s$/.exec(name);
    if (m) {
      const segment = S.segments.find((s) => s.sequence === Number(m[1]));
      if (segment) return [200, 'video/iso.segment', segment.bytes, { kind: 'segment', sequence: segment.sequence, ageMs: oclock() - segment.publishedAt, behindNewest: S.segments[S.segments.length - 1].sequence - segment.sequence }];
      return [404, 'text/plain', Buffer.alloc(0), { kind: 'segment', sequence: Number(m[1]) }];
    }
    m = /^part-(\d+)-(\d+)\.m4s$/.exec(name);
    if (m && partFrames) {
      const sequence = Number(m[1]), index = Number(m[2]);
      const blockedFrom = oclock();
      // the hinted part (and a little beyond) blocks until it exists
      if (!findPart(sequence, index) && sequence <= S.nextSequence + 1 && index < segFrames / partFrames) await waitFor(() => !!findPart(sequence, index) || partReached(sequence + 1, -1), 3000 * targetDuration);
      const part = findPart(sequence, index);
      if (part) return [200, 'video/iso.segment', part.bytes, { kind: 'part', sequence, index, blockedMs: oclock() - blockedFrom, ageMs: oclock() - part.availableAt }];
      return [404, 'text/plain', Buffer.alloc(0), { kind: 'part', sequence, index }];
    }
    return [404, 'text/plain', Buffer.alloc(0), { kind: 'other' }];
  }

  // ------------------------------------------------------------ network shaping
  const outageEnd = () => { const now = oclock(); for (const o of S.outages) if (now >= o.start && now < o.end) return o; return null; };
  async function gate() {      // false = the connection must be dropped (reset mode)
    for (;;) {
      const outage = outageEnd();
      if (!outage) return true;
      if (outage.mode === 'reset') return false;
      await sleep(outage.end - oclock());
    }
  }
  function scheduleOutage(inSeconds, seconds, mode) {
    const outage = { start: oclock() + inSeconds * 1000, end: oclock() + (inSeconds + seconds) * 1000, mode: mode === 'reset' ? 'reset' : 'hold' };
    S.outages.push(outage);
    if (outage.mode === 'reset') setTimeout(() => { for (const socket of S.sockets) if (!socket.isControl) socket.destroy(); }, inSeconds * 1000);
    emit('outage', { inSeconds, seconds, mode: outage.mode });
    return outage;
  }
  async function take(bytes) {
    const now = oclock(), start = Math.max(now, S.bucketFree);
    S.bucketFree = start + bytes * 8 / S.shape.rateKbps;
    if (start > now) await sleep(start - now);
  }

  // ------------------------------------------------------------ HTTP/1.1, one request per connection
  const REASONS = { 200: 'OK', 204: 'No Content', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 503: 'Service Unavailable' };
  const head = (status, type, length) => Buffer.from(`HTTP/1.1 ${status} ${REASONS[status] || 'Error'}\r\nContent-Type: ${type}\r\nContent-Length: ${length}\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, HEAD, OPTIONS\r\nAccess-Control-Allow-Headers: Range\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n`);

  const server = net.createServer({ noDelay: true }, (socket) => {
    S.sockets.add(socket);
    socket.on('close', () => S.sockets.delete(socket));
    socket.on('error', () => socket.destroy());
    let header = Buffer.alloc(0), handled = false;
    socket.on('data', (data) => {
      if (handled) return;
      header = Buffer.concat([header, data]);
      if (header.length > 8192) { socket.destroy(); return; }
      const text = header.toString('latin1');
      if (!text.includes('\r\n\r\n')) return;
      handled = true;
      const first = text.split('\r\n')[0].split(' ');
      if (first.length !== 3 || !['GET', 'HEAD', 'OPTIONS'].includes(first[0])) { socket.destroy(); return; }
      serve(socket, first[0], first[1]).catch(() => socket.destroy());
    });
  });

  async function serve(socket, method, target) {
    const receivedAt = oclock();
    const url = new URL(target, 'http://origin');
    if (url.pathname.startsWith('/control/')) { socket.isControl = true; control(socket, url); return; }
    // limits of NPHTTPServer: 8 connections, each cut 8 s after accept
    S.conns.accepted += 1;
    const live = [...S.sockets].filter((s) => !s.isControl && s.isStream).length;
    if (O.maxConns > 0 && live >= O.maxConns) { S.conns.refused += 1; socket.destroy(); return; }
    socket.isStream = true;
    if (O.connTimeout > 0) { const timer = setTimeout(() => { if (!socket.destroyed) { S.conns.timedOut += 1; socket.destroy(); } }, O.connTimeout * 1000); socket.on('close', () => clearTimeout(timer)); }
    const entry = { t: receivedAt, method, resource: url.pathname + url.search, status: 0, bytes: 0 };
    S.requests.push(entry);
    const finish = (status, extra) => { Object.assign(entry, extra || {}, { status }); socket.on('close', () => { entry.doneMs = Math.round((oclock() - receivedAt) * 100) / 100; }); emit('request', entry); };
    const delay = Math.max(0, S.shape.delayMs + (Math.random() * 2 - 1) * S.shape.jitterMs);
    if (!(await gate())) { finish(-1, { dropped: 'outage' }); socket.destroy(); return; }
    if (delay > 0) await sleep(delay / 2);
    let status, type, body, extra;
    if (!url.pathname.startsWith(prefix)) [status, type, body, extra] = [403, 'text/plain', Buffer.alloc(0), { kind: 'other' }];
    else if (method === 'OPTIONS') [status, type, body, extra] = [204, 'text/plain', Buffer.alloc(0), { kind: 'options' }];
    else [status, type, body, extra] = await resource(url.pathname.slice(prefix.length), url.searchParams);
    if (delay > 0) await sleep(delay / 2);
    if (!(await gate())) { finish(-1, { dropped: 'outage' }); socket.destroy(); return; }
    if (socket.destroyed) { finish(-2, extra); return; }
    entry.heldMs = Math.round((oclock() - receivedAt) * 100) / 100;      // request received -> first byte
    entry.bytes = body.length;
    finish(status, extra);
    const payload = method === 'HEAD' ? Buffer.alloc(0) : body;
    if (!(S.shape.rateKbps > 0) || payload.length === 0) { socket.end(Buffer.concat([head(status, type, body.length), payload])); return; }
    socket.write(head(status, type, body.length));
    const chunk = Math.max(1448, Math.min(8192, Math.round(S.shape.rateKbps * 1000 / 8 / 100)));   // about 10 ms of link time
    for (let offset = 0; offset < payload.length; offset += chunk) {
      await take(Math.min(chunk, payload.length - offset));
      if (!(await gate()) || socket.destroyed) { entry.dropped = 'outage'; socket.destroy(); return; }
      socket.write(payload.subarray(offset, offset + chunk));
    }
    socket.end();
  }

  function stats() {
    const clock = captureClock();
    const lag = [], interval = [];
    if (clock) S.published.forEach((p, i) => {
      p.publishLagMs = Math.round((p.publishedAt - nominalCapture(clock, p.firstFrame + p.frames)) * 100) / 100;
      lag.push(p.publishLagMs); if (i) interval.push(p.publishedAt - S.published[i - 1].publishedAt);
    });
    return {
      now: oclock(), startedAt: S.startedAt, pid: process.pid,
      options: O, derived: { segFrames, gopFrames, partFrames, targetDuration, partHoldBack, pattern: PATTERN, width, height },
      ffmpeg: { pid: ff.pid, args: ffArgs, exit: S.ffmpegExit, irregularFragments: S.irregular },
      clock,
      firstPlaylistOkAt: S.firstPlaylistOkAt,
      segments: { published: S.published.length, inStore: S.segments.length, bytes: quantiles(S.published.map((p) => p.bytes)), publishLagMs: quantiles(lag), publishIntervalMs: quantiles(interval) },
      published: S.published,
      outages: S.outages,
      shape: S.shape,
      connections: S.conns,
      requests: S.requests,
    };
  }

  function control(socket, url) {
    const reply = (status, object) => { const body = Buffer.from(JSON.stringify(object)); socket.end(Buffer.concat([head(status, 'application/json', body.length), body])); };
    const q = url.searchParams, name = url.pathname.slice('/control/'.length);
    if (name === 'time') return reply(200, { now: oclock() });
    if (name === 'stats') return reply(200, stats());
    if (name === 'capture') return reply(200, { fps, clock: captureClock(), wall: S.capture.map((v) => (v === undefined ? null : Math.round(v * 100) / 100)) });
    if (name === 'playlist') { const made = playlist(); return reply(200, { ready: !!made, text: made ? made.text : null, lastPublishedAt: S.published.length ? S.published[S.published.length - 1].publishedAt : null, segmentMs: O.seg * 1000, now: oclock() }); }
    if (name === 'outage') return reply(200, scheduleOutage(Number(q.get('in') || 0), Number(q.get('secs') || O.outageSecs), q.get('mode') || O.outageMode));
    if (name === 'shape') {
      for (const [key, field] of [['delay-ms', 'delayMs'], ['jitter-ms', 'jitterMs'], ['rate-kbps', 'rateKbps']]) if (q.has(key)) S.shape[field] = Number(q.get(key));
      return reply(200, S.shape);
    }
    if (name === 'stop') { reply(200, { stopping: true }); setTimeout(() => stop(0), 20); return; }
    reply(404, { error: 'unknown control endpoint' });
  }

  server.on('error', (error) => { emit('fatal', { error: 'listen: ' + error.message }); stop(1); });
  server.listen(O.port, O.host, () => {
    const port = server.address().port;
    emit('ready', { port, pid: process.pid, ffmpegPid: ff.pid, url: `http://${O.host}:${port}${prefix}index.m3u8`, control: `http://${O.host}:${port}/control/` });
  });
  if (O.outageAt >= 0) scheduleOutage(O.outageAt, O.outageSecs, O.outageMode);
  if (O.exitAfter > 0) setTimeout(() => stop(0), O.exitAfter * 1000);
  for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => stop(0));
  process.on('exit', () => { try { ff.kill('SIGKILL'); } catch (_) { /* gone */ } });
  // If the parent (run.js) dies without signalling, its end of our stdout pipe closes: stop too.
  process.stdout.on('error', () => stop(0));
}

main();
