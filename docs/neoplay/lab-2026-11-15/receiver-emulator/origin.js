'use strict';
// Live HLS origin standing in for the iPhone (NPMuxer + NPSegmentStore + NPHTTPServer).
// ffmpeg encodes in real time (H.264 Baseline, no B-frames, 60 fps, AAC-LC 48 kHz stereo) into a
// fragmented MP4 on stdout, one fragment per key-picture interval. A fragment is published only once
// complete, like AVAssetWriter's segments. The playlist copies NPSegmentStore.response("index.m3u8").
// Every picture carries its frame number as a 16-bit bar code (top strip) so that the receiver page
// can tell which captured picture is on screen, whatever the player's own timeline is.
const http = require('http');
const { spawn } = require('child_process');

const DEFAULTS = {
  segmentSeconds: 0.5, fps: 60, size: '640x360', videoBitrate: '700k',
  // playlist policy (defaults = NPPolicy.swift on branch Claude, 15 Nov 2026)
  version: 7, targetDuration: 1, windowSegments: 6, windowSeconds: 3.0, startSegments: 3,
  pdt: 'none',        // 'none' | 'first' | 'all'  -> EXT-X-PROGRAM-DATE-TIME
  holdBack: null,     // number -> EXT-X-SERVER-CONTROL:HOLD-BACK=<n>
  start: null,        // number -> EXT-X-START:TIME-OFFSET=<n>
  independent: false, // EXT-X-INDEPENDENT-SEGMENTS
  discontinuitySequence: true,
  privateNetworkHeader: false,
  // experiment: the first playlist answer hides its newest `firstLag` segments (they appear from the second answer on)
  firstLag: 0,
  // exploration: MPEG-DASH description of the same segments (live.mpd)
  dashDelay: 1.0, dashMinBuffer: 0.5, dashAstMarginMs: 40, dashUpdateSeconds: 30,
  // exploration: one endless fragmented MP4 response (live.mp4), one fragment per picture, for the receiver's plain <video src> path
  progressive: false, progGop: 1.0, progBacklogMs: 0, progFragMs: 0, replayFile: null,
};

function barcodeFilter(fps, size) {
  const [w] = size.split('x').map(Number);
  const cell = Math.floor(w / 16);
  const parts = [`testsrc2=size=${size}:rate=${fps}`, `drawbox=x=0:y=0:w=${w}:h=40:color=black:t=fill`];
  for (let bit = 0; bit < 16; bit++) {
    const period = 2 ** (bit + 1), half = 2 ** bit;
    parts.push(`drawbox=x=${bit * cell + 4}:y=4:w=${cell - 8}:h=32:color=white:t=fill:enable='gte(mod(n,${period}),${half})'`);
  }
  return parts.join(',');
}

async function startOrigin(options = {}) {
  const o = Object.assign({}, DEFAULTS, options);
  const secret = 'lab' + Math.random().toString(16).slice(2, 14);
  if (o.progressive) o.segmentSeconds = 1 / o.fps; // one fragment per picture: the t0() rule below then holds per picture
  const gop = o.progressive ? Math.round(o.progGop * o.fps) : Math.round(o.segmentSeconds * o.fps);
  const args = ['-hide_banner', '-loglevel', 'error', '-nostdin',
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', barcodeFilter(o.fps, o.size),
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
    '-map', '0:v', '-map', '1:a',
    '-c:v', 'libx264', '-profile:v', 'baseline', '-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '2',
    '-x264-params', `keyint=${gop}:min-keyint=${gop}:scenecut=0:bframes=0`,
    '-b:v', o.videoBitrate, '-maxrate', o.videoBitrate, '-bufsize', o.videoBitrate, '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '96k', '-ar', '48000', '-ac', '2',
    '-video_track_timescale', '90000', '-f', 'mp4', '-movflags', o.progressive ? (o.progFragMs ? '+empty_moov+default_base_moof' : '+frag_every_frame+empty_moov+default_base_moof') : '+frag_keyframe+empty_moov+default_base_moof', ...(o.progressive && o.progFragMs ? ['-frag_duration', String(Math.round(o.progFragMs * 1000))] : []), '-flush_packets', '1', 'pipe:1'];
  const state = {
    options: o, secret, init: null, segments: [], requests: [], spawnedAt: Date.now(), ffmpegArgs: args,
    holdUntil: 0, stderr: '', firstByteAt: null, exited: null, playlistsServed: 0, firstPlaylist: null, dashStart: null,
  };
  // replayFile: a fragmented MP4 written by another muxer (the app's NPFragmentedMP4) is replayed in real time instead of ffmpeg's output
  const ffmpeg = o.replayFile ? { kill() {}, stdout: new (require('events').EventEmitter)() } : spawn('ffmpeg', args, { stdio: ['ignore', 'pipe', 'pipe'] });
  if (!o.replayFile) { ffmpeg.stderr.on('data', (d) => { state.stderr += d.toString(); }); ffmpeg.on('exit', (code, signal) => { state.exited = { code, signal, at: Date.now() }; }); }
  const replayTimers = [];
  if (o.replayFile) setImmediate(() => {
    const file = require('fs').readFileSync(o.replayFile); let at = 0, head = [], index = 0; const begin = Date.now() + 50;
    while (at + 8 <= file.length) { const size = file.readUInt32BE(at), type = file.toString('latin1', at + 4, at + 8), box = file.subarray(at, at + size); at += size;
      if (type === 'ftyp') { head.push(box); continue; }
      if (type === 'moov') { head.push(box); const init = Buffer.concat(head); head = []; replayTimers.push(setTimeout(() => ffmpeg.stdout.emit('data', init), 0)); continue; }
      head.push(box);
      if (type === 'mdat') { const frag = Buffer.concat(head); head = []; index += 1; replayTimers.push(setTimeout(() => ffmpeg.stdout.emit('data', frag), Math.max(0, begin + index * 1000 / o.fps - Date.now()))); } }
  });

  // --- progressive clients: each gets init, then starts on a key picture (optionally after a backlog), then every fragment as it comes ---
  const clients = new Set();
  const u32 = (b, at) => b.readUInt32BE(at);
  const walk = (buf, start, end, cb) => { let at = start; while (at + 8 <= end) { const size = u32(buf, at); if (size < 8 || at + size > end) break; cb(buf.toString('latin1', at + 4, at + 8), at + 8, at + size); at += size; } };
  let videoTrack = 1, videoTimescale = 90000;
  const readInit = (buf) => walk(buf, 0, buf.length, (t, s, e) => { if (t !== 'moov') return; walk(buf, s, e, (t2, s2, e2) => { if (t2 !== 'trak') return; let id = 0, scale = 0, handler = '';
    walk(buf, s2, e2, (t3, s3, e3) => { if (t3 === 'tkhd') id = u32(buf, s3 + (buf[s3] === 1 ? 20 : 12));
      if (t3 === 'mdia') walk(buf, s3, e3, (t4, s4) => { if (t4 === 'mdhd') scale = u32(buf, s4 + (buf[s4] === 1 ? 20 : 12)); if (t4 === 'hdlr') handler = buf.toString('latin1', s4 + 8, s4 + 12); }); });
    if (handler === 'vide') { videoTrack = id; videoTimescale = scale; } }); });
  const videoTime = (buf) => { let out = null; walk(buf, 0, buf.length, (t, s, e) => { if (t !== 'moof') return; walk(buf, s, e, (t2, s2, e2) => { if (t2 !== 'traf') return; let id = 0, dt = null;
    walk(buf, s2, e2, (t3, s3) => { if (t3 === 'tfhd') id = u32(buf, s3 + 4); if (t3 === 'tfdt') dt = buf[s3] === 1 ? Number(buf.readBigUInt64BE(s3 + 4)) : u32(buf, s3 + 4); });
    if (id === videoTrack && dt !== null) out = dt / videoTimescale; }); }); return out; };
  function feed(bytes, frame) {
    for (const c of clients) {
      if (c.state === 'wait') { if (frame === null || (frame % gop !== 0 && !(o.progFragMs && frame % gop < Math.ceil(o.progFragMs / 1000 * o.fps) && false))) continue; c.state = 'fill'; c.first = frame; c.buffer = []; }
      if (c.state === 'fill') { c.buffer.push(bytes); if (frame !== null && (frame - c.first) / o.fps * 1000 >= o.progBacklogMs) { c.write(Buffer.concat(c.buffer)); c.buffer = null; c.state = 'live'; c.startedAt = Date.now(); c.firstFrame = c.first; } continue; }
      c.write(bytes);
    }
  }
  // --- split the fragmented MP4 byte stream into init + media segments ---
  let pending = Buffer.alloc(0), initParts = [], current = [];
  ffmpeg.stdout.on('data', (chunk) => {
    const now = Date.now();
    if (state.firstByteAt === null) state.firstByteAt = now;
    pending = pending.length ? Buffer.concat([pending, chunk]) : chunk;
    for (;;) {
      if (pending.length < 8) return;
      let size = pending.readUInt32BE(0);
      const type = pending.toString('latin1', 4, 8);
      if (size === 1) { if (pending.length < 16) return; size = Number(pending.readBigUInt64BE(8)); }
      if (size < 8 || pending.length < size) return;
      const box = pending.subarray(0, size); pending = pending.subarray(size);
      if (type === 'ftyp' || type === 'moov') { initParts.push(box); if (type === 'moov') { state.init = Buffer.concat(initParts); readInit(state.init); } }
      else if (type === 'moof' || type === 'styp' || type === 'sidx') current.push(box);
      else if (type === 'mdat') {
        current.push(box);
        const bytes = Buffer.concat(current); current = [];
        if (o.progressive) {
          const t = videoTime(bytes), frame = t === null ? null : Math.round(t * o.fps);
          if (frame !== null) state.segments.push({ sequence: frame, epoch: 0, duration: o.segmentSeconds, bytes: Buffer.alloc(0), arrival: now, size: bytes.length });
          feed(bytes, frame);
        } else {
          const sequence = state.segments.length;
          state.segments.push({ sequence, epoch: 0, duration: o.segmentSeconds, bytes, arrival: now });
        }
      }
    }
  });

  function advertised() {
    const s = state.segments; let start = s.length, total = 0;
    while (start > 0 && (s.length - start < o.windowSegments || total < o.windowSeconds)) { start -= 1; total += s[start].duration; }
    return s.slice(start);
  }
  // Wall-clock time at which frame 0 was produced: fragment k is complete (and reaches us) as soon as the
  // key picture of fragment k+1 leaves the encoder, i.e. at t0 + (k+1)*segmentSeconds + small muxing delay.
  function t0() {
    let best = Infinity;
    for (const s of state.segments) best = Math.min(best, s.arrival - (s.sequence + 1) * o.segmentSeconds * 1000);
    return best;
  }
  function playlist(hide = 0) {
    let list = advertised();
    if (list.length < o.startSegments) return null;
    if (hide > 0) list = list.slice(0, Math.max(1, list.length - hide));
    const lines = ['#EXTM3U', `#EXT-X-VERSION:${o.version}`, `#EXT-X-TARGETDURATION:${o.targetDuration}`];
    if (o.holdBack != null) lines.push(`#EXT-X-SERVER-CONTROL:HOLD-BACK=${Number(o.holdBack).toFixed(3)}`);
    if (o.independent) lines.push('#EXT-X-INDEPENDENT-SEGMENTS');
    if (o.start != null) lines.push(`#EXT-X-START:TIME-OFFSET=${Number(o.start).toFixed(3)}`);
    lines.push(`#EXT-X-MEDIA-SEQUENCE:${list[0].sequence}`);
    if (o.discontinuitySequence) lines.push(`#EXT-X-DISCONTINUITY-SEQUENCE:${list[0].epoch}`);
    lines.push('#EXT-X-MAP:URI="init-0.mp4"');
    const origin = t0();
    list.forEach((item, index) => {
      if (o.pdt === 'all' || (o.pdt === 'first' && index === 0)) {
        lines.push('#EXT-X-PROGRAM-DATE-TIME:' + new Date(Math.round(origin + item.sequence * o.segmentSeconds * 1000)).toISOString());
      }
      lines.push(`#EXTINF:${item.duration.toFixed(6)},`, `segment-${item.sequence}.m4s`);
    });
    return lines.join('\n') + '\n';
  }
  function respond(resource) {
    if (resource === 'index.m3u8') {
      const text = playlist(state.playlistsServed === 0 ? o.firstLag : 0);
      if (text !== null) { if (state.playlistsServed === 0) state.firstPlaylist = { at: Date.now(), text }; state.playlistsServed += 1; }
      return text === null ? [503, 'text/plain', Buffer.alloc(0)] : [200, 'application/vnd.apple.mpegurl', Buffer.from(text)];
    }
    if (resource === 'master.m3u8') {
      // experiment only (the app serves no multivariant playlist): tells the player the codecs before any media is fetched
      if (advertised().length < o.startSegments) return [503, 'text/plain', Buffer.alloc(0)];
      const [w, h] = o.size.split('x');
      return [200, 'application/vnd.apple.mpegurl', Buffer.from(['#EXTM3U', `#EXT-X-VERSION:${o.version}`, '#EXT-X-INDEPENDENT-SEGMENTS',
        `#EXT-X-STREAM-INF:BANDWIDTH=900000,CODECS="avc1.42c01f,mp4a.40.2",RESOLUTION=${w}x${h},FRAME-RATE=${o.fps}.000`, 'index.m3u8'].join('\n') + '\n')];
    }
    if (resource === 'live.mpd') {
      // exploration only (the app serves HLS): the same segments described as MPEG-DASH live, number-based template.
      // Segment k becomes available at availabilityStartTime + (k+1)*d: the receiver needs no playlist polling.
      if (advertised().length < o.startSegments) return [503, 'text/plain', Buffer.alloc(0)];
      if (state.dashStart === null) state.dashStart = t0() + o.dashAstMarginMs; // fixed for the session, like the app would stamp its first frame
      const [w, h] = o.size.split('x'), d = o.segmentSeconds, iso = (ms) => new Date(Math.round(ms)).toISOString();
      const xml = `<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="dynamic" profiles="urn:mpeg:dash:profile:isoff-live:2011" availabilityStartTime="${iso(state.dashStart)}" publishTime="${iso(Date.now())}" minimumUpdatePeriod="PT${o.dashUpdateSeconds}S" minBufferTime="PT${o.dashMinBuffer}S" timeShiftBufferDepth="PT${o.windowSeconds}S" suggestedPresentationDelay="PT${o.dashDelay}S" maxSegmentDuration="PT${d}S">
 <Period id="0" start="PT0S">
  <AdaptationSet contentType="video" mimeType="video/mp4" segmentAlignment="true" startWithSAP="1">
   <Representation id="v" codecs="avc1.42c01f,mp4a.40.2" bandwidth="900000" width="${w}" height="${h}" frameRate="${o.fps}">
    <SegmentTemplate timescale="1000" duration="${Math.round(d * 1000)}" startNumber="0" initialization="init-0.mp4" media="segment-$Number$.m4s"/>
   </Representation>
  </AdaptationSet>
 </Period>
</MPD>
`;
      return [200, 'application/dash+xml', Buffer.from(xml)];
    }
    if (resource === 'init-0.mp4' && state.init) return [200, 'video/mp4', state.init];
    const match = /^segment-(\d+)\.m4s$/.exec(resource);
    // NPSegmentStore keeps the last 24 segments in RAM (older ones answer 404)
    if (match) { const n = Number(match[1]); const s = state.segments[n]; if (s && n >= state.segments.length - 24) return [200, 'video/iso.segment', s.bytes]; }
    return [404, 'text/plain', Buffer.alloc(0)];
  }
  const reasons = { 200: 'OK', 204: 'No Content', 403: 'Forbidden', 404: 'Not Found', 503: 'Service Unavailable' };
  const server = http.createServer((req, res) => {
    const at = Date.now(), prefix = `/s/${secret}/`;
    let result;
    if (!req.url.startsWith(prefix)) result = [403, 'text/plain', Buffer.alloc(0)];
    else if (req.method === 'OPTIONS') result = [204, 'text/plain', Buffer.alloc(0)];
    else if (req.method !== 'GET' && req.method !== 'HEAD') { req.socket.destroy(); return; }
    else if (o.progressive && req.url.slice(prefix.length).split('?')[0] === 'live.mp4' && req.method === 'GET') {
      const entry = { at, method: req.method, resource: 'live.mp4', status: 200, newest: state.segments.length - 1, held: 0 };
      state.requests.push(entry);
      res.writeHead(200, 'OK', { 'Content-Type': 'video/mp4', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store', 'Connection': 'close' });
      res.write(state.init);
      const client = { state: 'wait', write: (b) => { const wait = state.holdUntil - Date.now(); if (wait > 0) setTimeout(() => res.write(b), wait); else res.write(b); } };
      clients.add(client); state.progClients = (state.progClients || []); state.progClients.push(client);
      req.on('close', () => { clients.delete(client); entry.closedAt = Date.now(); });
      return;
    }
    else result = respond(req.url.slice(prefix.length).split('?')[0]);
    const newest = state.segments.length - 1;
    const entry = { at, method: req.method, resource: req.url.slice(prefix.length), status: result[0], newest, held: 0 };
    state.requests.push(entry);
    const send = () => {
      const headers = {
        'Content-Type': result[1], 'Content-Length': result[2].length, 'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS', 'Access-Control-Allow-Headers': 'Range',
        'Cache-Control': 'no-store', 'Connection': 'close',
      };
      if (o.privateNetworkHeader) headers['Access-Control-Allow-Private-Network'] = 'true';
      res.writeHead(result[0], reasons[result[0]] || 'Error', headers);
      res.end(req.method === 'HEAD' ? undefined : result[2]);
      entry.sentAt = Date.now();
    };
    // simulated link outage: every response is held until the outage is over
    const wait = state.holdUntil - at;
    if (wait > 0) { entry.held = wait; setTimeout(send, wait); } else send();
  });
  server.keepAliveTimeout = 0;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const port = server.address().port;
  return {
    state, port, t0,
    url: `http://127.0.0.1:${port}/s/${secret}/index.m3u8`,
    playlist,
    hold(ms) { state.holdUntil = Date.now() + ms; },
    async waitReady(timeout = 15000) {
      const end = Date.now() + timeout;
      while (Date.now() < end) {
        if (state.exited) throw new Error('ffmpeg exited: ' + state.stderr);
        if (advertised().length >= o.startSegments) return;
        await new Promise((r) => setTimeout(r, 20));
      }
      throw new Error('origin not ready: ' + state.stderr);
    },
    async stop() {
      try { ffmpeg.kill('SIGKILL'); } catch (e) {} for (const t of replayTimers) clearTimeout(t);
      await new Promise((r) => { server.close(() => r()); server.closeAllConnections && server.closeAllConnections(); });
    },
  };
}

module.exports = { startOrigin, DEFAULTS };

if (require.main === module) {
  // standalone: node src/origin.js '{"holdBack":1.5}'  -> prints the URL, runs until Ctrl-C
  (async () => {
    const origin = await startOrigin(process.argv[2] ? JSON.parse(process.argv[2]) : {});
    await origin.waitReady();
    console.log(origin.url);
    process.on('SIGINT', async () => { await origin.stop(); process.exit(0); });
    process.on('SIGTERM', async () => { await origin.stop(); process.exit(0); });
  })().catch((e) => { console.error(e); process.exit(1); });
}
