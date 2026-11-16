import { createFramesEngine, framesCapable } from './frames-engine.mjs';
import { createMp4Engine, mp4Capable } from './mp4-engine.mjs';

// RewindBox receiver application for Google Cast devices. It replaces Google's
// Default Media Receiver for NeoPlay so that the picture skips the TV's media
// player: the phone launches it with its own application ID, then talks to it
// on one custom namespace (JSON messages):
//   phone → TV  hello {v} · ping {id, t} · play {engine: 'frames'|'mp4', url, hud} · stop
//   TV → phone  caps {...} · pong {id, t, r} · playing {engine} · key · stats {...}
//               switch {engine: 'mp4', reason} · error {engine, reason}
// `frames` (WebCodecs) is the lowest delay; `mp4` (MediaSource) is for devices
// whose WebCodecs cannot decode the stream. The media itself never goes through
// Google: the TV reads it from the phone on the local network.
// Lab use without a Cast device: ?lab=1&engine=frames&url=http://… starts at once.
export const NAMESPACE = 'urn:x-cast:com.rewindbox.neoplay';
const FRAMEWORK = 'https://www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js';
const query = new URLSearchParams(location.search);
const lab = query.get('lab') === '1';
const french = (navigator.language || '').toLowerCase().startsWith('fr');
const words = french
  ? { waiting: 'En attente de l’iPhone…', connecting: 'Connexion au jeu…', unsupported: 'Changement de mode de lecture…', ended: 'Diffusion terminée' }
  : { waiting: 'Waiting for the iPhone…', connecting: 'Connecting to the game…', unsupported: 'Changing playback mode…', ended: 'Streaming ended' };
const $ = id => document.getElementById(id);
const splash = $('splash'), status = $('status'), canvas = $('canvas'), video = $('video'), hud = $('hud');
const sent = [];
let context = null, engine = null, generation = 0, statsTimer = 0, wakeLock = null, wakeError = null, showHud = query.get('hud') === '1';

function say(text) { status.textContent = text; splash.hidden = false; }
function send(message) {
  if (lab) { sent.push(message); if (sent.length > 200) sent.shift(); return; }
  try { context?.sendCustomMessage(NAMESPACE, undefined, message); } catch {}
}
async function keepAwake() {
  // A canvas does not count as playing media: ask the platform to keep the screen on.
  if (wakeLock || !navigator.wakeLock?.request) { if (!navigator.wakeLock?.request) wakeError = 'unavailable'; return; }
  try { wakeLock = await navigator.wakeLock.request('screen'); wakeLock.addEventListener('release', () => { wakeLock = null; }); wakeError = null; }
  catch (error) { wakeError = error?.message ?? String(error); }
}
async function capabilities() {
  const caps = { v: 1, ua: navigator.userAgent, frames: framesCapable(), mp4: mp4Capable(), worklet: typeof AudioWorkletNode === 'function',
    screen: { width: screen.width, height: screen.height, ratio: devicePixelRatio }, codecs: {}, hardware: null };
  if (caps.frames) {
    // The phone encodes H.264 High profile; 720p is what it sends to a Cast device.
    for (const codec of ['avc1.64001F', 'avc1.640028', 'avc1.42E01F']) {
      const result = {};
      for (const hardwareAcceleration of ['prefer-hardware', 'prefer-software']) {
        try { result[hardwareAcceleration] = (await VideoDecoder.isConfigSupported({ codec, codedWidth: 1280, codedHeight: 720, optimizeForLatency: true, hardwareAcceleration })).supported === true; }
        catch (error) { result[hardwareAcceleration] = `error: ${error?.message ?? error}`; }
      }
      caps.codecs[codec] = result;
    }
    caps.hardware = Object.values(caps.codecs).some(result => result['prefer-hardware'] === true);
    caps.frames = Object.values(caps.codecs).some(result => result['prefer-hardware'] === true || result['prefer-software'] === true);
  }
  caps.prefer = caps.frames ? 'frames' : caps.mp4 ? 'mp4' : null;
  return caps;
}
function stopEngine() {
  clearInterval(statsTimer); statsTimer = 0;
  engine?.close(); engine = null; generation++;
  canvas.hidden = true; video.hidden = true;
}
function play({ engine: kind, url }) {
  stopEngine();
  if (typeof url !== 'string' || !/^https?:\/\//.test(url)) { send({ type: 'error', engine: kind, reason: 'bad url' }); return; }
  const id = generation, mode = kind === 'mp4' ? 'mp4' : 'frames';
  const emit = event => {
    if (id !== generation) return;
    if (event.type === 'playing') { splash.hidden = true; (mode === 'mp4' ? video : canvas).hidden = false; send({ type: 'playing', engine: mode }); }
    else if (event.type === 'key') send({ type: 'key' });
    else if (event.type === 'unsupported') { say(words.unsupported); send(mode === 'frames' && mp4Capable() ? { type: 'switch', engine: 'mp4', reason: event.reason } : { type: 'error', engine: mode, reason: event.reason, fatal: true }); }
    else if (event.type === 'error') send({ type: 'error', engine: mode, reason: event.reason });
  };
  say(words.connecting);
  keepAwake();
  engine = mode === 'mp4' ? createMp4Engine({ url, video, emit }) : createFramesEngine({ url, canvas, emit });
  statsTimer = setInterval(() => {
    if (id !== generation || !engine) return;
    const stats = { type: 'stats', at: Math.round(performance.now()), wake: wakeLock ? 'held' : wakeError, ...engine.stats() };
    send(stats);
    if (showHud) { hud.hidden = false; hud.textContent = summary(stats); }
  }, 1000);
}
function summary(stats) {
  const parts = [stats.engine, `${stats.width}×${stats.height}`];
  if (stats.engine === 'frames') parts.push(`decoder ${stats.decoder}`, `decode ${stats.decodeMs?.mean ?? '–'} ms`, `arrival→screen ${stats.ageMs?.mean ?? '–'} ms`, `spread ${stats.spreadMs ?? '–'} ms`, `shown ${stats.second?.presented}/${stats.second?.pictures}`, `audio ${stats.audio?.fillMs ?? '–'}/${stats.audio?.targetMs ?? '–'} ms`);
  else parts.push(`lag ${stats.lagMs?.mean ?? '–'} ms`, `rate ${stats.rate}`, `stalls ${stats.stalls}`, `seeks ${stats.seeks}`);
  return parts.join(' · ');
}
async function onMessage(message) {
  switch (message?.type) {
    case 'hello': send({ type: 'caps', ...(await capabilities()) }); break;
    case 'ping': send({ type: 'pong', id: message.id, t: message.t, r: Math.round(performance.now() * 10) / 10 }); break;
    case 'play': if (typeof message.hud === 'boolean') showHud = message.hud; hud.hidden = !showHud; play(message); break;
    case 'stop': stopEngine(); say(words.ended); break;
  }
}
function loadFramework() {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = FRAMEWORK; script.onload = resolve; script.onerror = () => reject(new Error('Cast receiver framework unavailable'));
    document.head.append(script);
  });
}
async function start() {
  say(words.waiting);
  if (lab) {
    window.neoplayCast = { sent, onMessage, stats: () => engine?.stats() ?? null, get engine() { return engine?.mode ?? null; } };
    if (query.get('url')) onMessage({ type: 'play', engine: query.get('engine') ?? 'frames', url: query.get('url'), hud: true });
    return;
  }
  await loadFramework();
  const framework = globalThis.cast.framework;
  context = framework.CastReceiverContext.getInstance();
  context.addCustomMessageListener(NAMESPACE, event => { onMessage(event.data).catch(() => {}); });
  // The phone ended its session: the application closes. It lost the connection: it may come back for a minute.
  let alone = 0;
  context.addEventListener(framework.system.EventType.SENDER_CONNECTED, () => { clearTimeout(alone); alone = 0; });
  context.addEventListener(framework.system.EventType.SENDER_DISCONNECTED, event => {
    if (context.getSenders().length) return;
    const close = () => { stopEngine(); context.stop(); };
    if (event.reason === framework.system.DisconnectReason.REQUESTED_BY_SENDER) close();
    else { clearTimeout(alone); alone = setTimeout(() => { if (!context.getSenders().length) close(); }, 60_000); }
  });
  const options = new framework.CastReceiverOptions();
  options.disableIdleTimeout = true;   // no media session: the framework must not close the application by itself
  options.skipPlayersLoad = true;      // neither Shaka nor MPL: this page plays the stream itself
  options.statusText = 'RewindBox';
  options.customNamespaces = { [NAMESPACE]: framework.system.MessageType.JSON };
  context.start(options);
}
start().catch(error => say(error?.message ?? String(error)));
