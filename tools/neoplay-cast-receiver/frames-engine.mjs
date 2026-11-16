import { KIND, MAX_PACKET, parseConfig, parseVideo, parseAudio } from './protocol.mjs';
import { noReorderDescription } from './h264-sps.mjs';
import { PacketSplitter, Spread, SlowWatch } from './stream-packets.mjs';

// Lowest-delay engine of the RewindBox Cast receiver. The phone's encoder
// output (one H.264 access unit per picture, raw PCM) is read from one endless
// HTTP response and decoded with WebCodecs. Nothing buffers a picture: the
// newest decoded one is drawn at the next display refresh, older ones that the
// refresh did not reach are dropped. The TV's media pipeline (and its
// one-second refill after any underrun) is not involved. Sound goes through an
// AudioWorklet ring (audio-ring.mjs: 80 ms cushion, adaptive) and is not
// waited for: the picture is never delayed to match it.
export function framesCapable() {
  return typeof VideoDecoder === 'function' && typeof EncodedVideoChunk === 'function' && typeof fetch === 'function' && typeof ReadableStream === 'function';
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const same = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);

// emit({type}): 'playing', 'key' (the next picture should be a key picture),
// 'unsupported' {reason} (this device cannot use this engine: use MediaSource),
// 'error' {reason} (the stream cannot be reached).
export function createFramesEngine({ url, canvas, emit, audioModule = new URL('./audio-worklet.mjs', import.meta.url).href }) {
  const draw = canvas.getContext('2d', { alpha: false, desynchronized: true });
  const counters = { connections: 0, reconnects: 0, bytes: 0, pictures: 0, decoded: 0, presented: 0, replaced: 0, skipped: 0, keyRequests: 0, decodeErrors: 0, configurations: 0, pcm: 0 };
  const decodeTimes = new Spread(), ages = new Spread(), transits = new Spread(), slow = new SlowWatch();
  const inflight = new Map(); // pts → {arrived, decoding}, insertion order = decode order
  let decoder = null, config = null, settings = null, waitKey = true, closed = false, raf = 0, newest = null, shown = null;
  let audio = null, node = null, workletReady = null, audioClock = null, audioError = null, lastError = null;
  let playing = false, unsupported = false, lastKey = -Infinity, errors = [], chain = Promise.resolve(), abort = null;
  let previous = { pictures: 0, presented: 0, skipped: 0, replaced: 0 }, failingSince = null;

  function present() {
    raf = 0;
    if (closed || !newest) return;
    const frame = newest; newest = null;
    if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) { canvas.width = frame.displayWidth; canvas.height = frame.displayHeight; }
    draw.drawImage(frame, 0, 0, canvas.width, canvas.height);
    const at = performance.now(), pts = frame.timestamp;
    frame.close(); counters.presented++; shown = { pts, at: Math.round(at * 10) / 10 };
    for (const [time, entry] of inflight) { if (time > pts) break; if (time === pts) ages.add(at - entry.arrived); inflight.delete(time); }
    if (!playing) { playing = true; emit({ type: 'playing' }); }
  }
  function output(frame) {
    counters.decoded++;
    const entry = inflight.get(frame.timestamp);
    if (entry) decodeTimes.add(performance.now() - entry.decoding);
    if (newest) { newest.close(); counters.replaced++; }
    newest = frame;
    if (!raf) raf = requestAnimationFrame(present);
  }
  function requestKey() {
    const now = performance.now();
    if (now - lastKey < 500) return;
    lastKey = now; counters.keyRequests++; emit({ type: 'key' });
  }
  function giveUp(reason) { if (unsupported || closed) return; unsupported = true; emit({ type: 'unsupported', reason }); }
  function createDecoder() {
    try { if (decoder && decoder.state !== 'closed') decoder.close(); } catch {}
    decoder = new VideoDecoder({
      output,
      error: error => {
        counters.decodeErrors++; lastError = error?.message ?? String(error);
        if (closed) return;
        // A broken reference chain closes the decoder: build it again and wait for a key picture.
        const now = performance.now(); errors = errors.filter(time => now - time < 10_000); errors.push(now);
        if (errors.length >= 4) { giveUp(`decode: ${lastError}`); return; }
        createDecoder(); requestKey();
      },
    });
    decoder.configure(settings); waitKey = true; inflight.clear();
  }
  async function configure(packet) {
    const next = parseConfig(packet);
    if (config && decoder?.state === 'configured' && next.width === config.width && next.height === config.height && same(next.avcC, config.avcC)) { waitKey = true; return; }
    // NPFrameEncoder never reorders pictures; saying so in the SPS keeps hardware decoders from holding pictures back.
    const description = noReorderDescription(next.avcC, { senderNeverReorders: true });
    let candidate = null;
    for (const hardwareAcceleration of ['prefer-hardware', 'no-preference']) {
      const option = { codec: next.codec, codedWidth: next.width, codedHeight: next.height, description, optimizeForLatency: true, hardwareAcceleration };
      try { if ((await VideoDecoder.isConfigSupported(option)).supported) { candidate = option; break; } } catch {}
    }
    if (closed) return;
    if (!candidate) { giveUp(`codec ${next.codec} ${next.width}x${next.height}`); return; }
    config = next; settings = candidate; counters.configurations++;
    createDecoder();
    // Pictures never wait for the sound to be ready: sound packets that come before the worklet are simply not played.
    startAudio(next);
  }
  async function startAudio(next) {
    if (typeof AudioWorkletNode !== 'function' || typeof AudioContext !== 'function') { audioError = 'no AudioWorklet'; return; }
    try {
      audio ??= new AudioContext({ sampleRate: 48000, latencyHint: 'interactive' });
      workletReady ??= audio.audioWorklet.addModule(audioModule);
      await workletReady;
      if (closed) return;
      if (!node) {
        node = new AudioWorkletNode(audio, 'neoplay-audio', { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [2] });
        node.port.onmessage = ({ data }) => { if (data?.type === 'clock') audioClock = data; };
        node.connect(audio.destination);
      }
      node.port.postMessage({ type: 'configure', sampleRate: next.sampleRate, channels: next.channels });
      if (audio.state !== 'running') await audio.resume().catch(error => { audioError = error.message; });
    } catch (error) { audioError = error?.message ?? String(error); }
  }
  function picture(packet, arrived) {
    counters.pictures++;
    if (!decoder || decoder.state !== 'configured') return;
    const { pts, key, data } = parseVideo(packet);
    transits.add(arrived - pts / 1000);
    if (waitKey && !key) { counters.skipped++; requestKey(); return; }
    // A decoder that falls behind would add its queue to the delay: skip to the next key picture instead. Eight, as the
    // Windows receiver: hardware decoders keep a few pictures in flight while keeping up.
    if (!key && decoder.decodeQueueSize > 8) { counters.skipped++; waitKey = true; requestKey(); return; }
    waitKey = false;
    inflight.set(pts, { arrived, decoding: performance.now() });
    if (inflight.size > 120) inflight.delete(inflight.keys().next().value);
    decoder.decode(new EncodedVideoChunk({ type: key ? 'key' : 'delta', timestamp: pts, data }));
  }
  function sound(packet) {
    if (!node || !config) return;
    const { pts, samples } = parseAudio(packet, config.channels);
    counters.pcm++;
    node.port.postMessage({ type: 'pcm', pts, samples }, [samples.buffer]);
  }
  function receive(packet, arrived) {
    const kind = packet[0];
    if (kind === KIND.CONFIG) { chain = chain.then(() => configure(packet)).catch(error => { lastError = error.message; }); return; }
    const handle = kind === KIND.VIDEO ? () => picture(packet, arrived) : kind === KIND.AUDIO ? () => sound(packet) : null;
    if (!handle) return;
    chain = chain.then(handle).catch(error => { lastError = error.message; });
  }
  async function run() {
    while (!closed) {
      const controller = new AbortController(); abort = controller;
      let received = false;
      try {
        const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
        // The phone answers 503 until its encoder has produced the first configuration.
        if (response.status === 503) { await sleep(150); continue; }
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
        counters.connections++;
        const reader = response.body.getReader(), splitter = new PacketSplitter(MAX_PACKET);
        for (;;) {
          const { value, done } = await reader.read();
          if (done || closed) break;
          const arrived = performance.now();
          received = true; failingSince = null; counters.bytes += value.byteLength;
          for (const packet of splitter.push(value)) receive(packet, arrived);
        }
      } catch (error) { if (closed) break; lastError = error?.message ?? String(error); }
      if (closed) break;
      // The phone closes the connection when its send queue stalls: a new one starts again on a key picture.
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
    mode: 'frames',
    // One second of figures; also decides whether this device keeps up.
    stats() {
      const delta = { pictures: counters.pictures - previous.pictures, presented: counters.presented - previous.presented, skipped: counters.skipped - previous.skipped, replaced: counters.replaced - previous.replaced };
      previous = { pictures: counters.pictures, presented: counters.presented, skipped: counters.skipped, replaced: counters.replaced };
      const decode = decodeTimes.summary(), age = ages.summary(), transit = transits.summary();
      if (playing && slow.sample({ pictures: delta.pictures, presented: delta.presented, queue: decoder?.decodeQueueSize ?? 0 })) giveUp(`slow: ${slow.reason}`);
      return {
        engine: 'frames', playing, ...counters, second: delta, decoder: settings?.hardwareAcceleration ?? null, queue: decoder?.decodeQueueSize ?? 0,
        width: config?.width ?? 0, height: config?.height ?? 0, codec: config?.codec ?? null,
        decodeMs: decode, ageMs: age, spreadMs: transit ? Math.round((transit.p95 - transit.min) * 10) / 10 : null, shown,
        audio: audio ? { state: audio.state, baseMs: Math.round((audio.baseLatency ?? 0) * 1000), outputMs: Math.round((audio.outputLatency ?? 0) * 1000), fillMs: Math.round((audioClock?.fillSeconds ?? 0) * 1000), targetMs: Math.round((audioClock?.targetSeconds ?? 0) * 1000), underruns: audioClock?.stats?.underruns ?? 0, skips: audioClock?.stats?.skips ?? 0, error: audioError } : { error: audioError },
        error: lastError,
      };
    },
    close() {
      closed = true; abort?.abort(); if (raf) cancelAnimationFrame(raf); raf = 0;
      newest?.close(); newest = null; inflight.clear();
      try { if (decoder && decoder.state !== 'closed') decoder.close(); } catch {}
      decoder = null;
      if (node) { node.port.postMessage({ type: 'close' }); node.disconnect(); node = null; }
      audio?.close().catch(() => {}); audio = null;
    },
  };
}
