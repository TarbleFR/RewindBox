import { mp4Mime } from './protocol.mjs';
import { initializationEnd, Spread, EdgeChase } from './stream-packets.mjs';

// MediaSource engine of the RewindBox Cast receiver, for devices whose
// WebCodecs cannot decode the stream. It reads the same endless fragmented MP4
// as Google's receiver on the direct route (NPDirectStream: one fragment per
// picture, AAC sound), but the play head is kept at the live edge here, ten
// times a second, without a round trip to the phone: a jump when far behind,
// a slightly faster rate when a little behind.
export function mp4Capable() {
  return typeof MediaSource === 'function' && MediaSource.isTypeSupported('video/mp4; codecs="avc1.640028, mp4a.40.2"') && typeof fetch === 'function';
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export function createMp4Engine({ url, video, emit }) {
  const counters = { connections: 0, reconnects: 0, bytes: 0, appends: 0, initializations: 0, stalls: 0, seeks: 0, trims: 0 };
  const lags = new Spread(), chase = new EdgeChase();
  let media = null, buffer = null, mime = null, closed = false, playing = false, started = false, abort = null, lastError = null;
  let queue = [], queued = 0, head = new Uint8Array(0), needInit = true, shown = null, frameCallback = 0, failingSince = null, lastTrim = 0;

  video.muted = false; video.autoplay = false; video.playsInline = true;
  const opened = new Promise(resolve => {
    media = new MediaSource();
    media.addEventListener('sourceopen', resolve, { once: true });
    video.src = URL.createObjectURL(media);
  });
  function pump() {
    if (!buffer || buffer.updating || !queue.length || media.readyState !== 'open') return;
    const data = queue.shift(); queued -= data.byteLength;
    try { buffer.appendBuffer(data); counters.appends++; }
    catch (error) {
      lastError = error.message;
      // A full buffer: drop what was already played and try again.
      if (error.name === 'QuotaExceededError') { queue.unshift(data); queued += data.byteLength; trim(true); }
      else emit({ type: 'unsupported', reason: `append: ${error.message}` });
    }
  }
  function trim(force = false) {
    if (!buffer || buffer.updating || !buffer.buffered.length) return;
    const start = buffer.buffered.start(0), keep = video.currentTime - (force ? 1 : 6);
    if (keep - start > (force ? 0.2 : 4)) { try { buffer.remove(start, keep); counters.trims++; } catch {} }
  }
  // Appends the bytes of the response as they come; the first ones must hold the initialization segment, which names the codecs.
  async function accept(bytes) {
    if (needInit) {
      const joined = new Uint8Array(head.length + bytes.length); joined.set(head); joined.set(bytes, head.length);
      const end = initializationEnd(joined);
      if (end < 0) { head = joined; return; }
      head = new Uint8Array(0); needInit = false; counters.initializations++;
      if (!buffer) {
        await opened; if (closed) return;
        mime = mp4Mime(joined.subarray(0, end));
        if (!MediaSource.isTypeSupported(mime)) { emit({ type: 'unsupported', reason: `type ${mime}` }); return; }
        buffer = media.addSourceBuffer(mime); buffer.mode = 'segments';
        buffer.addEventListener('updateend', pump);
        buffer.addEventListener('error', () => { lastError = 'SourceBuffer error'; });
      }
      bytes = joined;
    }
    queue.push(bytes); queued += bytes.byteLength; pump();
    if (queued > 16 * 1024 * 1024) { emit({ type: 'unsupported', reason: 'append backlog' }); }
  }
  function control() {
    if (closed || !buffer || !buffer.buffered.length) return;
    const ranges = buffer.buffered, last = ranges.length - 1, edge = ranges.end(last), now = performance.now(), time = video.currentTime;
    if (!started) {
      // The media element's audio renderer wants about 0.2 s ahead before it plays (Chromium): start with the target held.
      if (edge - ranges.start(last) < chase.target) return;
      started = true; video.currentTime = Math.max(ranges.start(last), edge - chase.target);
      video.play().catch(error => { lastError = `play: ${error.message}`; });
      return;
    }
    // A gap (a reconnection starts after one) or the end of an older range: move to the next range, never back.
    let inside = -1;
    for (let i = 0; i < ranges.length; i++) if (time >= ranges.start(i) - 0.002 && time <= ranges.end(i)) { inside = i; break; }
    if (inside < 0 || (inside < last && ranges.end(inside) - time < 0.05)) {
      let next = null;
      for (let i = 0; i < ranges.length; i++) if (ranges.start(i) > time) { next = ranges.start(i); break; }
      if (next !== null) { video.currentTime = Math.max(next, edge - chase.seekAbove); counters.seeks++; }
      return;
    }
    const lag = edge - time;
    lags.add(lag * 1000);
    const decision = chase.sample(lag, now);
    if (decision.seek) { video.currentTime = edge - chase.target; counters.seeks++; }
    if (video.playbackRate !== decision.rate) video.playbackRate = decision.rate;
    if (now - lastTrim > 5_000) { lastTrim = now; trim(); }
  }
  const timer = setInterval(control, 100);
  const onWaiting = () => { if (started) { counters.stalls++; chase.stalled(performance.now()); } };
  const onPlaying = () => { if (!playing) { playing = true; emit({ type: 'playing' }); } };
  video.addEventListener('waiting', onWaiting); video.addEventListener('playing', onPlaying);
  // The picture on screen and when: what the phone compares with the capture time of that picture.
  if (typeof video.requestVideoFrameCallback === 'function') {
    const onFrame = (now, meta) => { shown = { pts: Math.round(meta.mediaTime * 1e6), at: Math.round((meta.expectedDisplayTime ?? now) * 10) / 10 }; if (!closed) frameCallback = video.requestVideoFrameCallback(onFrame); };
    frameCallback = video.requestVideoFrameCallback(onFrame);
  }
  async function run() {
    while (!closed) {
      const controller = new AbortController(); abort = controller;
      let received = false;
      try {
        const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
        if (response.status === 503) { await sleep(150); continue; }
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
        counters.connections++; needInit = true; head = new Uint8Array(0);
        const reader = response.body.getReader();
        for (;;) {
          const { value, done } = await reader.read();
          if (done || closed) break;
          received = true; failingSince = null; counters.bytes += value.byteLength;
          await accept(value);
        }
      } catch (error) { if (closed) break; lastError = error?.message ?? String(error); }
      if (closed) break;
      counters.reconnects++;
      const now = performance.now();
      if (!received) {
        failingSince ??= now;
        if (now - failingSince > 8_000) { emit({ type: 'error', reason: `network: ${lastError ?? 'no data'}` }); failingSince = now; }
      }
      await sleep(received ? 0 : 250);
    }
  }
  run();
  return {
    mode: 'mp4',
    stats() {
      const quality = video.getVideoPlaybackQuality?.();
      return {
        engine: 'mp4', playing, ...counters, mime, lagMs: lags.summary(), targetMs: Math.round(chase.target * 1000), rate: video.playbackRate,
        width: video.videoWidth, height: video.videoHeight, dropped: quality?.droppedVideoFrames ?? null, frames: quality?.totalVideoFrames ?? null,
        queued, shown, error: lastError ?? (video.error ? `media ${video.error.code}` : null),
      };
    },
    close() {
      closed = true; abort?.abort(); clearInterval(timer);
      if (frameCallback && typeof video.cancelVideoFrameCallback === 'function') video.cancelVideoFrameCallback(frameCallback);
      video.removeEventListener('waiting', onWaiting); video.removeEventListener('playing', onPlaying);
      video.pause(); const source = video.src; video.removeAttribute('src'); video.load();
      if (source.startsWith('blob:')) URL.revokeObjectURL(source);
      queue = []; buffer = null; media = null;
    },
  };
}
