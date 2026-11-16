// Stand-in for the iPhone on the RewindBox Cast receiver bench. ffmpeg encodes
// in real time (H.264 High, no B-frames, 60 fps, one fMP4 fragment per picture)
// a test picture whose top strip carries the picture number as a 16-bit bar code.
// Served like NPHTTPServer:
//   /s/lab/frames    NeoPlay v2 packets (3 config, 4 picture, 5 PCM), each preceded by its u32 length, one endless
//                    chunked response that starts on a key picture (NPFramesStream)
//   /s/lab/live.mp4  the fragmented MP4 itself, from a key fragment (NPDirectStream)
//   /times           when each picture left the encoder (epoch ms): the receiver page reports when it showed it
//   /cast/…          the assembled receiver site (node tools/neoplay-cast-receiver/site.mjs <dir>)
import http from 'node:http';
import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { join, extname } from 'node:path';

// replay: {file, times} — live.mp4 replays a stream written by the app's own NPDirectStream (Swift check output, one line per
// write: milliseconds and bytes) instead of ffmpeg's, whose live per-picture fragments carry no picture duration.
export async function startPhone({ site, port = 0, fps = 60, size = '1280x720', bitrate = '4M', gop = 60, replay = null } = {}) {
  const [width, height] = size.split('x').map(Number);
  const cell = Math.floor(width / 16);
  const filters = [`testsrc2=size=${size}:rate=${fps}`, `drawbox=x=0:y=0:w=${width}:h=40:color=black:t=fill`];
  for (let bit = 0; bit < 16; bit++) filters.push(`drawbox=x=${bit * cell + 4}:y=4:w=${cell - 8}:h=32:color=white:t=fill:enable='gte(mod(n,${2 ** (bit + 1)}),${2 ** bit})'`);
  const args = ['-hide_banner', '-loglevel', 'error', '-nostdin',
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', filters.join(','),
    '-re', '-readrate_initial_burst', '0', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
    '-map', '0:v', '-map', '1:a',
    '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'ultrafast', '-tune', 'zerolatency', '-threads', '1',
    '-x264-params', `keyint=${gop}:min-keyint=${gop}:scenecut=0:bframes=0:sliced-threads=0`,
    '-b:v', bitrate, '-maxrate', bitrate, '-bufsize', bitrate, '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2',
    '-video_track_timescale', '90000', '-f', 'mp4', '-movflags', '+frag_every_frame+empty_moov+default_base_moof', '-flush_packets', '1', 'pipe:1'];
  const ffmpeg = spawn('ffmpeg', args, { stdio: ['ignore', 'pipe', 'pipe'] });
  let stderr = ''; ffmpeg.stderr.on('data', data => { stderr += data; });
  const state = { init: null, avcC: null, videoTrack: 1, produced: [], origin: null, frames: new Set(), mp4: new Set(), audioSamples: 0, stderr: () => stderr };
  const u32 = (b, at) => b.readUInt32BE(at);
  const boxes = (b, from, to) => { const out = []; for (let at = from; at + 8 <= to;) { const size = u32(b, at); out.push({ type: b.toString('latin1', at + 4, at + 8), at, size }); if (size < 8) break; at += size; } return out; };
  function findAvcC(moov) { const i = moov.indexOf(Buffer.from('avcC')); return i < 0 ? null : moov.subarray(i + 4, i - 4 + u32(moov, i - 4)); }
  // Video samples of one moof + mdat (default-base-is-moof, trun with data offset and sample sizes).
  function videoSamples(fragment) {
    const moof = boxes(fragment, 0, fragment.length)[0], samples = [];
    for (const traf of boxes(fragment, moof.at + 8, moof.at + moof.size).filter(box => box.type === 'traf')) {
      const inner = boxes(fragment, traf.at + 8, traf.at + traf.size);
      const tfhd = inner.find(box => box.type === 'tfhd'), trun = inner.find(box => box.type === 'trun');
      if (!tfhd || !trun || u32(fragment, tfhd.at + 12) !== state.videoTrack) continue;
      // tfhd: optional base offset (u64), description index, default duration, default size (what ffmpeg uses), default flags
      const headerFlags = u32(fragment, tfhd.at + 8) & 0xffffff;
      let field = tfhd.at + 16, defaultSize = 0;
      if (headerFlags & 1) field += 8;
      if (headerFlags & 2) field += 4;
      if (headerFlags & 8) field += 4;
      if (headerFlags & 0x10) defaultSize = u32(fragment, field);
      const flags = u32(fragment, trun.at + 8) & 0xffffff, count = u32(fragment, trun.at + 12);
      let at = trun.at + 16, offset = 0;
      if (flags & 1) { offset = fragment.readInt32BE(at); at += 4; }
      if (flags & 4) at += 4;
      for (let i = 0; i < count; i++) {
        if (flags & 0x100) at += 4;
        const size = flags & 0x200 ? u32(fragment, at) : defaultSize; if (flags & 0x200) at += 4;
        if (flags & 0x400) at += 4;
        if (flags & 0x800) at += 4;
        samples.push(fragment.subarray(moof.at + offset, moof.at + offset + size)); offset += size;
      }
    }
    return samples;
  }
  const isKey = au => { for (let at = 0; at + 4 < au.length;) { const size = u32(au, at); if ((au[at + 4] & 31) === 5) return true; at += 4 + size; } return false; };
  const framed = packet => { const head = Buffer.alloc(4); head.writeUInt32BE(packet.length); return Buffer.concat([head, packet]); };
  const chunk = data => Buffer.concat([Buffer.from(data.length.toString(16) + '\r\n'), data, Buffer.from('\r\n')]);
  function config() { const p = Buffer.alloc(10); p[0] = 3; p.writeUInt16BE(width, 1); p.writeUInt16BE(height, 3); p.writeUInt32BE(48000, 5); p[9] = 2; return Buffer.concat([p, state.avcC]); }
  let pending = Buffer.alloc(0), pictures = 0;
  ffmpeg.stdout.on('data', data => {
    pending = pending.length ? Buffer.concat([pending, data]) : data;
    for (;;) {
      const list = boxes(pending, 0, pending.length);
      if (!state.init) {
        const moov = list.find(box => box.type === 'moov');
        if (!moov || moov.at + moov.size > pending.length) return;
        state.init = pending.subarray(0, moov.at + moov.size); state.avcC = findAvcC(state.init);
        pending = pending.subarray(moov.at + moov.size); continue;
      }
      if (list.length < 2 || list[0].type !== 'moof' || list[1].type !== 'mdat' || list[1].at + list[1].size > pending.length) return;
      const fragment = Buffer.from(pending.subarray(0, list[1].at + list[1].size)); pending = pending.subarray(fragment.length);
      const now = Date.now(), samples = videoSamples(fragment);
      let keyFragment = false;
      for (const au of samples) {
        const n = pictures++, key = isKey(au); keyFragment ||= key;
        state.origin ??= now; state.produced[n] = now;
        const packet = Buffer.alloc(10 + au.length); packet[0] = 4; packet.writeBigUInt64BE(BigInt(Math.round(n * 1e6 / fps)), 1); packet[9] = key ? 1 : 0; au.copy(packet, 10);
        for (const client of state.frames) {
          if (client.waiting && !key) continue;
          if (client.waiting) { client.waiting = false; client.res.write(chunk(framed(config()))); }
          client.res.write(chunk(framed(packet)));
        }
      }
      for (const client of state.mp4) {
        if (client.waiting && !keyFragment) continue;
        if (client.waiting) { client.waiting = false; client.res.write(chunk(state.init)); }
        client.res.write(chunk(fragment));
      }
    }
  });
  // PCM of the frames route: a 440 Hz tone in 1024-frame packets on the pictures' time line.
  const tone = setInterval(() => {
    if (state.origin === null) return;
    const due = Math.floor((Date.now() - state.origin) * 48);
    while (state.audioSamples + 1024 <= due) {
      const packet = Buffer.alloc(9 + 4096); packet[0] = 5; packet.writeBigUInt64BE(BigInt(Math.round(state.audioSamples * 1e6 / 48000)), 1);
      for (let i = 0; i < 1024; i++) { const v = Math.round(Math.sin(2 * Math.PI * 440 * (state.audioSamples + i) / 48000) * 6000); packet.writeInt16LE(v, 9 + i * 4); packet.writeInt16LE(v, 11 + i * 4); }
      state.audioSamples += 1024;
      for (const client of state.frames) if (!client.waiting) client.res.write(chunk(framed(packet)));
    }
  }, 10);
  function replayTo(res, req) {
    const bytes = readFileSync(replay.file), lines = readFileSync(replay.times, 'utf8').trim().split('\n').map(line => line.split(' ').map(Number));
    const begin = Date.now(), first = lines[0][0]; let at = 0, index = 0, closed = false; req.on('close', () => { closed = true; });
    state.produced = [];
    const step = () => {
      while (!closed && index < lines.length && Date.now() - begin >= lines[index][0] - first) {
        const piece = bytes.subarray(at, at + lines[index][1]); at += lines[index][1]; index++;
        // Video fragment: tfdt of track 1 (90 kHz) gives the picture number on the 60 fps time line.
        for (let i = piece.indexOf('tfhd'); i > 0; i = piece.indexOf('tfhd', i + 4)) {
          if (piece.readUInt32BE(i + 8) !== 1) continue;
          const tfdt = piece.indexOf('tfdt', i); if (tfdt < 0) break;
          const ticks = piece[tfdt + 4] ? Number(piece.readBigUInt64BE(tfdt + 8)) : piece.readUInt32BE(tfdt + 8);
          state.produced[Math.round(ticks / 90000 * fps)] = Date.now();
        }
        res.write(chunk(piece));
      }
      if (!closed && index < lines.length) setTimeout(step, 2);
    };
    step();
  }
  const types = { '.html': 'text/html', '.mjs': 'text/javascript', '.js': 'text/javascript' };
  const server = http.createServer((req, res) => {
    const path = req.url.split('?')[0];
    if (path === '/s/lab/frames' || path === '/s/lab/live.mp4') {
      if (!state.init) { res.writeHead(503, { 'access-control-allow-origin': '*' }); res.end(); return; }
      res.socket.setNoDelay(true);
      res.writeHead(200, { 'content-type': path.endsWith('mp4') ? 'video/mp4' : 'application/octet-stream', 'transfer-encoding': 'chunked', 'cache-control': 'no-store', 'access-control-allow-origin': '*' });
      res.flushHeaders();
      const client = { res, waiting: true }, set = path.endsWith('mp4') ? state.mp4 : state.frames;
      // The receiver's response object must not end: hand raw chunks to the socket.
      res.write = data => res.socket.write(data);
      if (replay && path.endsWith('mp4')) { replayTo(res, req); return; }
      set.add(client); req.on('close', () => set.delete(client));
      return;
    }
    if (path === '/times') { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify({ fps, produced: state.produced })); return; }
    const file = join(site, path.replace(/\.\./g, ''));
    if (site && path.startsWith('/cast/') && existsSync(file)) { res.writeHead(200, { 'content-type': types[extname(file)] ?? 'application/octet-stream' }); res.end(readFileSync(file)); return; }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  return { port: server.address().port, state, stop() { clearInterval(tone); ffmpeg.kill('SIGKILL'); server.closeAllConnections?.(); server.close(); } };
}
