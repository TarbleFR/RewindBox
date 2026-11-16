'use strict';
// node src/analyze.js out/a.json [out/b.json ...] [--statuses] [--json]
// Per run: which player Google's framework used, start-up time, glass delay of the picture on screen
// (bar code -> captured frame number -> capture time), freezes, MEDIA_STATUS summary.
const fs = require('fs');
const path = require('path');

const quantile = (sorted, q) => sorted.length ? sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))] : null;
const stats = (values) => { const s = values.slice().sort((a, b) => a - b); return s.length ? { n: s.length, min: s[0], p5: quantile(s, 0.05), median: quantile(s, 0.5), p95: quantile(s, 0.95), max: s[s.length - 1] } : null; };
const fmt = (x, d = 0) => (x === null || x === undefined || Number.isNaN(x)) ? 'n/a' : Number(x).toFixed(d);

function analyze(r, options = {}) {
  const out = { name: r.name, error: r.error || null };
  if (!r.page || !r.origin) return out;
  const fps = r.origin.options.fps, t0 = r.origin.t0, segMs = r.origin.options.segmentSeconds * 1000;
  // plain <video src> from another origin taints the canvas (bar code unreadable, n = -2): the element's own media time of the
  // presented picture (requestVideoFrameCallback) gives the captured frame number, the stream's time line being the encoder's.
  for (const s of r.page.samples) if (s.n === -2 && typeof s.mt === 'number' && r.origin.options.progressive) s.n = Math.round(s.mt * r.origin.options.fps);
  const m = r.marks, S = r.page.samples.filter((s) => s.n !== undefined);
  out.player = r.page.shakaLoads.length ? 'Shaka ' + r.page.shakaVersion : (r.page.mpl.loads.length || r.page.mpl.hosts ? 'MPL ' + (r.page.mpl.version || '') : (r.origin.options.progressive ? 'plain element' : 'none'));
  out.caf = r.page.cafVersion;
  out.loadToPlayingStatusMs = m.firstPlaying && m.loadSent ? m.firstPlaying - m.loadSent : null;
  // a sample "advances" when the picture on screen is a later captured frame than at the previous sample
  // (a forward skip larger than twice the elapsed time is a jump, not motion)
  const smooth = (a, b) => { const step = b.n - a.n, dt = b.w - a.w; return a.n >= 0 && step > 0 && step <= dt / 1000 * fps * 2 + 2; };
  let firstMotion = null;
  for (let i = 3; i < S.length; i++) { if (smooth(S[i - 3], S[i - 2]) && smooth(S[i - 2], S[i - 1]) && smooth(S[i - 1], S[i])) { firstMotion = S[i - 3].w; break; } }
  out.loadToFirstMotionMs = firstMotion && m.loadSent ? firstMotion - m.loadSent : null;
  const firstPicture = S.find((s) => s.n >= 0);
  out.loadToFirstPictureMs = firstPicture && m.loadSent ? firstPicture.w - m.loadSent : null;
  // steady-state window: from one second after the picture first moves (or, if it never moves, from `settle` seconds
  // after the first PLAYING status) to the end of the run or to the first scripted action; --from/--to (seconds after LOAD) override.
  const firstAction = (r.actionsDone || []).filter((a) => a.action.do !== 'snapshot').map((a) => a.t).sort((a, b) => a - b)[0];
  const from = (options.from !== undefined ? m.loadSent + options.from * 1000 : firstMotion ? firstMotion + 1000 : (m.firstPlaying || m.loadSent) + (r.config.settle || 5) * 1000);
  const to = options.to !== undefined ? m.loadSent + options.to * 1000 : (firstAction || Infinity);
  out.windowFrom = (from - m.loadSent) / 1000;
  const W = S.filter((s) => s.w >= from && s.w <= to && s.n >= 0);
  out.windowSeconds = W.length ? (W[W.length - 1].w - W[0].w) / 1000 : 0;
  const delayAll = [], delayMoving = [], behindNewest = [];
  let moving = 0, freezes = [], freezeStart = null, jumps = 0, backJumps = 0;
  const arrivals = r.origin.segments.map((s) => s.arrival);
  for (let i = 0; i < W.length; i++) {
    const s = W[i], delay = s.w - (t0 + s.n / fps * 1000);
    delayAll.push(delay);
    let newest = -1; for (let k = arrivals.length - 1; k >= 0; k--) { if (arrivals[k] <= s.w) { newest = k; break; } }
    if (newest >= 0) behindNewest.push(((newest + 1) * segMs - s.n / fps * 1000));
    if (i === 0) continue;
    const step = s.n - W[i - 1].n, dt = s.w - W[i - 1].w;
    if (smooth(W[i - 1], s)) { moving += 1; delayMoving.push(delay); if (freezeStart !== null) { freezes.push(W[i - 1].w - freezeStart); freezeStart = null; } }
    else if (freezeStart === null) freezeStart = W[i - 1].w;
    if (step < 0) backJumps += 1;
    if (step > 0 && !smooth(W[i - 1], s)) jumps += 1; // picture skipped forward by more than twice the elapsed time
  }
  if (freezeStart !== null && W.length) freezes.push(W[W.length - 1].w - freezeStart);
  const realFreezes = freezes.filter((f) => f >= 200);
  out.movingFraction = W.length > 1 ? moving / (W.length - 1) : null;
  out.delayMovingMs = stats(delayMoving); out.delayAllMs = stats(delayAll); out.behindNewestSegmentEndMs = stats(behindNewest);
  out.freezes = { count: realFreezes.length, totalMs: realFreezes.reduce((a, b) => a + b, 0), maxMs: realFreezes.length ? Math.max(...realFreezes) : 0 };
  out.forwardJumps = jumps; out.backwardJumps = backJumps;
  const last = W[W.length - 1], first = W[0];
  if (last && first) { out.framesDecoded = last.tf - first.tf; out.framesDropped = last.df - first.df; out.rvfcPresented = last.pf - first.pf; }
  // origin side
  const playlistTimes = r.origin.requests.filter((q) => q.resource.startsWith('index.m3u8') && q.status === 200).map((q) => q.at);
  const gaps = []; for (let i = 1; i < playlistTimes.length; i++) gaps.push(playlistTimes[i] - playlistTimes[i - 1]);
  out.playlistPollMs = stats(gaps);
  const ages = [];
  for (const q of r.origin.requests) { const k = /^segment-(\d+)/.exec(q.resource); if (k && r.origin.segments[+k[1]] && q.at >= from) ages.push(q.at - r.origin.segments[+k[1]].arrival); }
  out.segmentAgeAtRequestMs = stats(ages);
  out.requests = { playlists: playlistTimes.length, segments: r.origin.requests.filter((q) => /^segment-/.test(q.resource)).length, notFound: r.origin.requests.filter((q) => q.status === 404).length };
  // statuses
  const statuses = r.ipc.filter((x) => x.dir === 'from-receiver' && x.data && x.data.type === 'MEDIA_STATUS' && x.data.status && x.data.status[0]).map((x) => {
    const s = x.data.status[0], l = s.liveSeekableRange;
    return { t: (x.t - m.loadSent) / 1000, requestId: x.data.requestId, state: s.playerState, idleReason: s.idleReason, rate: s.playbackRate, currentTime: s.currentTime, start: l && l.start, end: l && l.end,
      behindEnd: l ? l.end - s.currentTime : null, isMovingWindow: l && l.isMovingWindow, isLiveDone: l && l.isLiveDone, commands: s.supportedMediaCommands,
      startAbsoluteTime: s.media ? s.media.startAbsoluteTime : undefined, duration: s.media ? s.media.duration : undefined, hasMedia: !!s.media };
  });
  out.statusCount = statuses.length;
  out.statusStates = statuses.reduce((a, s) => { a[s.state] = (a[s.state] || 0) + 1; return a; }, {});
  out.statusAfterSettle = statuses.filter((s) => s.t * 1000 + m.loadSent >= from).length;
  out.supportedMediaCommands = Array.from(new Set(statuses.map((s) => s.commands)));
  out.startAbsoluteTime = Array.from(new Set(statuses.filter((s) => s.hasMedia).map((s) => s.startAbsoluteTime)));
  out.behindEndAtStatus = stats(statuses.filter((s) => s.behindEnd !== null && s.t * 1000 + m.loadSent >= from).map((s) => s.behindEnd));
  out.statuses = statuses;
  out.otherMessages = r.ipc.filter((x) => x.dir === 'from-receiver' && x.data && x.data.type !== 'MEDIA_STATUS' && x.namespace && x.namespace.endsWith('.media')).map((x) => ({ t: (x.t - m.loadSent) / 1000, data: x.data }));
  const snap = r.shakaSnapshots.filter((x) => x.info).pop();
  if (snap) {
    const c = snap.info.configuration, tl = snap.info.timeline;
    out.shaka = { timeline: tl, stats: snap.info.stats && { stallsDetected: snap.info.stats.stallsDetected, gapsJumped: snap.info.stats.gapsJumped, bufferingTime: snap.info.stats.bufferingTime, playTime: snap.info.stats.playTime, liveLatency: snap.info.stats.liveLatency, droppedFrames: snap.info.stats.droppedFrames, decodedFrames: snap.info.stats.decodedFrames },
      streaming: c && c.streaming && { rebufferingGoal: c.streaming.rebufferingGoal, bufferingGoal: c.streaming.bufferingGoal, bufferBehind: c.streaming.bufferBehind, stallEnabled: c.streaming.stallEnabled, stallThreshold: c.streaming.stallThreshold, stallSkip: c.streaming.stallSkip, safeSeekOffset: c.streaming.safeSeekOffset, safeSeekEndOffset: c.streaming.safeSeekEndOffset, returnToEndOfLiveWindowWhenOutside: c.streaming.returnToEndOfLiveWindowWhenOutside, lowLatencyMode: c.streaming.lowLatencyMode, liveSync: c.streaming.liveSync, segmentPrefetchLimit: c.streaming.segmentPrefetchLimit, updateIntervalSeconds: c.streaming.updateIntervalSeconds, jumpLargeGaps: c.streaming.jumpLargeGaps, gapDetectionThreshold: c.streaming.gapDetectionThreshold },
      manifest: c && c.manifest && { defaultPresentationDelay: c.manifest.defaultPresentationDelay, availabilityWindowOverride: c.manifest.availabilityWindowOverride, hls: c.manifest.hls && { liveSegmentsDelay: c.manifest.hls.liveSegmentsDelay, sequenceMode: c.manifest.hls.sequenceMode, ignoreManifestProgramDateTime: c.manifest.hls.ignoreManifestProgramDateTime, useSafariBehaviorForLive: c.manifest.hls.useSafariBehaviorForLive } } };
  }
  out.shakaEvents = r.page.shakaEvents.reduce((a, e) => { const k = e.type + (e.type === 'buffering' ? ':' + e.buffering : ''); a[k] = (a[k] || 0) + 1; return a; }, {});
  out.actions = r.actionsDone.map((a) => ({ t: (a.t - m.loadSent) / 1000, action: a.action, requestId: a.requestId }));
  return out;
}

function line(a) {
  if (!a.player) return `${a.name}: ${a.error}`;
  const d = a.delayMovingMs, all = a.delayAllMs, b = a.behindNewestSegmentEndMs;
  return [a.name.padEnd(22), a.player.padEnd(15), `window=${fmt(a.windowFrom, 1)}s+${fmt(a.windowSeconds, 1)}s`, 'start(motion)=' + (a.loadToFirstMotionMs === null ? 'never' : fmt(a.loadToFirstMotionMs / 1000, 2) + 's'), 'moving=' + fmt(a.movingFraction * 100) + '%',
    'delay(moving) med/p5/p95=' + (d ? `${fmt(d.median)}/${fmt(d.p5)}/${fmt(d.p95)}` : 'n/a') + 'ms', 'delay(all) med/p95=' + (all ? `${fmt(all.median)}/${fmt(all.p95)}` : 'n/a') + 'ms',
    'behindNewest med=' + (b ? fmt(b.median) : 'n/a') + 'ms', `freezes=${a.freezes.count} (total ${fmt(a.freezes.totalMs / 1000, 1)}s, max ${fmt(a.freezes.maxMs / 1000, 1)}s)`, 'jumps=' + a.forwardJumps,
    'statuses=' + JSON.stringify(a.statusStates), a.error ? 'ERROR ' + a.error : ''].join('  ');
}

if (require.main === module) {
  const args = process.argv.slice(2), files = args.filter((x) => !x.startsWith('--'));
  const option = (name) => { const i = args.indexOf('--' + name); return i >= 0 ? Number(args[i + 1]) : undefined; };
  const numeric = new Set(); for (const name of ['from', 'to']) { const i = args.indexOf('--' + name); if (i >= 0) numeric.add(args[i + 1]); }
  for (const file of files.filter((f) => !numeric.has(f))) {
    const a = analyze(JSON.parse(fs.readFileSync(path.resolve(file), 'utf8')), { from: option('from'), to: option('to') });
    if (args.includes('--json')) { const copy = Object.assign({}, a); if (!args.includes('--statuses')) delete copy.statuses; console.log(JSON.stringify(copy, null, 1)); continue; }
    console.log(line(a));
    if (args.includes('--statuses') && a.statuses) {
      for (const s of a.statuses) console.log(`    ${fmt(s.t, 2).padStart(7)}s req=${String(s.requestId).padEnd(4)} ${String(s.state).padEnd(9)} rate=${s.rate} cur=${fmt(s.currentTime, 3)} live=[${fmt(s.start, 3)}, ${fmt(s.end, 3)}] end-cur=${fmt(s.behindEnd, 3)} cmds=${s.commands}${s.hasMedia ? ' media(startAbsoluteTime=' + s.startAbsoluteTime + ', duration=' + s.duration + ')' : ''}${s.idleReason ? ' idle=' + s.idleReason : ''}`);
      for (const o of a.otherMessages) console.log('    other ' + fmt(o.t, 2) + 's ' + JSON.stringify(o.data));
      for (const o of a.actions) console.log('    action ' + fmt(o.t, 2) + 's ' + JSON.stringify(o.action) + (o.requestId ? ' requestId=' + o.requestId : ''));
    }
  }
}
module.exports = { analyze, stats, line };
