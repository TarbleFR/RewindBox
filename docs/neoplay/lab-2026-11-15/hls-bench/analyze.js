#!/usr/bin/env node
'use strict';
// Turns the raw samples of one run (page + origin) into the result JSON described in README.md.
// As a command: node analyze.js <result.raw.json> [--warmup 5] [--freeze-ms 100]  -> prints the result JSON.

const round = (v, digits = 1) => (v === null || v === undefined || !Number.isFinite(v) ? null : Math.round(v * 10 ** digits) / 10 ** digits);

function dist(values, digits = 1) {
  const v = Float64Array.from(values.filter((x) => Number.isFinite(x))).sort();
  if (!v.length) return { n: 0 };
  const q = (p) => v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))];
  let sum = 0; for (const x of v) sum += x;
  return { n: v.length, median: round(q(0.5), digits), mean: round(sum / v.length, digits), p05: round(q(0.05), digits), p25: round(q(0.25), digits), p75: round(q(0.75), digits), p95: round(q(0.95), digits), p99: round(q(0.99), digits), min: round(v[0], digits), max: round(v[v.length - 1], digits) };
}
const median = (values) => { const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b); return v.length ? v[v.length >> 1] : null; };

function slope(xs, ys) {       // least squares
  const n = xs.length; if (n < 3) return null;
  let sx = 0, sy = 0; for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; }
  const mx = sx / n, my = sy / n; let num = 0, den = 0;
  for (let i = 0; i < n; i++) { num += (xs[i] - mx) * (ys[i] - my); den += (xs[i] - mx) ** 2; }
  return den ? num / den : null;
}

function analyze(raw, options = {}) {
  const page = raw.page, stats = raw.originStats, meta = raw.meta || {};
  const warmup = options.warmup ?? meta.warmup ?? 5, freezeMs = options.freezeMs ?? meta.freezeMs ?? 100;
  const problems = [];
  const result = { schema: 'neoplay-bench/1', label: meta.label || null, startedAt: meta.startedAt || null, command: meta.command || null, options: meta.options || null };
  const clock = stats && stats.clock;
  const fps = clock ? clock.fps : (meta.options && meta.options.fps) || 60;
  const frameMs = 1000 / fps;

  // ---- clocks
  const c0 = page.clockStart, c1 = page.clockEnd || page.clockStart;
  const offsetAt = (t) => (!c0 ? 0 : c1.at === c0.at ? c0.offsetMs : c0.offsetMs + (c1.offsetMs - c0.offsetMs) * Math.min(1, Math.max(0, (t - c0.at) / (c1.at - c0.at))));
  const toOrigin = (t) => t + offsetAt(t);                 // page performance.now() -> origin clock (ms since epoch)
  const toPage = (o) => o - (c0 ? c0.offsetMs : 0);        // origin clock -> page time (start offset; error = clock drift over the run)
  result.clock = {
    pageToOriginRttMs: c0 ? { start: round(c0.rttMs, 2), end: round(c1.rttMs, 2) } : null,
    pageToOriginDriftMs: c0 ? round(c1.offsetMs - c0.offsetMs, 2) : null,
    captureResidualMs: clock ? clock.residualMs : null,
    captureDriftMs: clock ? clock.driftMs : null,
    note: 'delay = (expectedDisplayTime mapped to the origin clock) - (t0 + frame/fps). Mapping error <= RTT/2; capture grid error = captureResidualMs (ffmpeg pacing jitter around the nominal frame grid).',
  };
  if (!c0) problems.push('no clock comparison');
  else if (Math.max(c0.rttMs, c1.rttMs) > 10) problems.push(`clock ping RTT ${round(Math.max(c0.rttMs, c1.rttMs))} ms`);
  if (!clock) problems.push('no capture clock from the origin');
  // Lab health: other jobs on the machine starve ffmpeg, the page or the decoder and would pass for stutter.
  const tlRows = (page.timeline && page.timeline.rows) || [], sampleMs = (page.params && page.params.sampleMs) || 250;
  const timerLate = []; for (let i = 1; i < tlRows.length; i++) timerLate.push(tlRows[i][0] - tlRows[i - 1][0] - sampleMs);
  const late = dist(timerLate), pub = stats && stats.segments ? stats.segments.publishIntervalMs : null, segMs = stats ? stats.options.seg * 1000 : 0;
  result.labHealth = {
    captureResidualP99Ms: clock ? clock.residualMs.p99 : null, captureResidualMaxMs: clock ? clock.residualMs.max : null,
    publishIntervalMaxExcessMs: pub ? round(pub.max - segMs) : null,
    pageTimerLateP99Ms: late.n ? late.p99 : null, pageTimerLateMaxMs: late.n ? late.max : null,
    limits: { captureResidualP99Ms: 20, publishIntervalMaxExcessMs: 80, pageTimerLateP99Ms: 100 },
  };
  const H = result.labHealth, over = [];
  if (H.captureResidualP99Ms > H.limits.captureResidualP99Ms) over.push(`ffmpeg pacing p99 ${H.captureResidualP99Ms} ms`);
  if (H.publishIntervalMaxExcessMs > H.limits.publishIntervalMaxExcessMs && !(stats.options.longSegments)) over.push(`a segment was published ${H.publishIntervalMaxExcessMs} ms late`);
  if (H.pageTimerLateP99Ms > H.limits.pageTimerLateP99Ms) over.push(`page timers p99 ${H.pageTimerLateP99Ms} ms late`);
  H.ok = over.length === 0;
  if (over.length) problems.push('lab overloaded: ' + over.join(', '));

  // ---- frames
  const f = page.frames || { count: 0 };
  const N = f.count;
  const first = (() => { for (let i = 0; i < N; i++) if (f.frameNumber[i] >= 0) return i; return -1; })();
  const pixelRead = [], invalid = { noPicture: 0, grey: 0, parity: 0 };
  for (let i = 0; i < N; i++) { const n = f.frameNumber[i]; if (n === -2) invalid.noPicture += 1; else if (n === -3) invalid.grey += 1; else if (n === -4) invalid.parity += 1; else if (n >= 0) pixelRead.push(i); }
  const t0page = first >= 0 ? f.expectedDisplay[first] : (page.firstFrameAt ?? 0);
  const tS = (t) => (t - t0page) / 1000;
  result.durationS = N ? round(tS(f.expectedDisplay[N - 1]), 2) : 0;

  // Frame number of every sample. The counter read in the picture calibrates the mapping mediaTime -> frame
  // number (running median of the last 9 reads); the frame number then comes from metadata.mediaTime, which
  // belongs to the same frame as expectedDisplayTime. Reason: drawImage() in the callback sometimes returns
  // the NEXT frame (one frame early), which would bias the delay by one frame duration on those samples.
  // When picture and metadata disagree by more than two frames the mapping has moved (seek, gap, resync):
  // the picture wins.
  const number = new Float64Array(N).fill(NaN); let estimated = 0, offByOne = 0, remapped = 0;
  const offsets = [], recent = [];
  const med9 = () => { const v = recent.slice().sort((x, y) => x - y); return v[v.length >> 1]; };
  for (let i = 0; i < N; i++) {
    const n = f.frameNumber[i];
    if (n >= 0) {
      const offset = f.mediaTime[i] - n / fps; offsets.push(offset);
      recent.push(offset); if (recent.length > 9) recent.shift();
      const viaMedia = Math.round((f.mediaTime[i] - med9()) * fps);
      if (Math.abs(viaMedia - n) <= 2) { number[i] = viaMedia; if (viaMedia !== n) offByOne += 1; }
      else { number[i] = n; remapped += 1; recent.length = 0; recent.push(offset); }
    } else if (n === -1 && recent.length) { number[i] = Math.round((f.mediaTime[i] - med9()) * fps); estimated += 1; }
  }
  const delay = new Float64Array(N).fill(NaN), delayPresentation = new Float64Array(N).fill(NaN);
  if (clock) for (let i = 0; i < N; i++) if (!Number.isNaN(number[i])) {
    const captured = clock.t0 + number[i] * frameMs;
    delay[i] = toOrigin(f.expectedDisplay[i]) - captured;
    delayPresentation[i] = toOrigin(f.presentation[i]) - captured;
  }
  const inWindow = (from, to) => { const out = []; for (let i = 0; i < N; i++) { const t = tS(f.expectedDisplay[i]); if (t >= from && t < to && !Number.isNaN(delay[i])) out.push(delay[i]); } return out; };

  // ---- outages (origin clock -> seconds since first frame)
  const outages = ((stats && stats.outages) || []).map((o) => ({ startS: round(tS(toPage(o.start)), 2), endS: round(tS(toPage(o.end)), 2), mode: o.mode }));

  // ---- delay
  const perSecond = [];
  if (N && first >= 0) {
    const buckets = new Map();
    for (let i = 0; i < N; i++) { if (Number.isNaN(delay[i])) continue; const s = Math.floor(tS(f.expectedDisplay[i])); if (!buckets.has(s)) buckets.set(s, []); buckets.get(s).push(delay[i]); }
    const lastS = Math.floor(tS(f.expectedDisplay[N - 1]));
    for (let s = 0; s <= lastS; s++) { const b = buckets.get(s) || []; perSecond.push([s, b.length ? round(median(b)) : null, b.length ? round(Math.min(...b)) : null, b.length ? round(Math.max(...b)) : null, b.length]); }
  }
  const steadyRows = perSecond.filter((r) => r[0] >= warmup && r[1] !== null);
  const drift = slope(steadyRows.map((r) => r[0]), steadyRows.map((r) => r[1]));
  const end = result.durationS;
  result.delay = {
    unit: 'ms',
    atFirstFrame: first >= 0 ? round(delay[first]) : null,
    firstSecond: dist(inWindow(0, 1)),
    steady: dist(inWindow(warmup, Infinity)),
    whole: dist(inWindow(0, Infinity)),
    steadyPresentationTime: dist(Array.from(delayPresentation).filter((v, i) => tS(f.expectedDisplay[i]) >= warmup)),
    first10s: round(median(inWindow(warmup, warmup + 10))),
    last10s: round(median(inWindow(Math.max(warmup, end - 10), Infinity))),
    driftMsPerMin: drift === null ? null : round(drift * 60, 1),
    perSecondFields: ['second', 'median', 'min', 'max', 'frames'],
    perSecond,
  };
  // Independent cross-check of the delay, from quantities that do not use the frame counter:
  //   delay = age of the newest segment at the first playlist + its publish lag (origin log)
  //         + presentation delay (HOLD-BACK or three segments) + seekRange().end - currentTime (Shaka)
  //         + display latency (not modelled).
  if (stats) {
    const firstOk = (stats.requests || []).find((r) => r.kind === 'playlist' && r.status === 200);
    const rowsTl = ((page.timeline && page.timeline.rows) || []).filter((r) => tS(r[0]) >= warmup && !r[8]);
    const behind = median(rowsTl.map((r) => r[3] - r[1]));
    const newest = firstOk ? (stats.published || []).find((p) => p.sequence === firstOk.newest) : null;
    const presentation = stats.options.holdBack > 0 ? stats.options.holdBack : 3 * stats.options.seg;
    if (firstOk && newest && behind !== null && result.delay.steady.n) {
      const model = firstOk.newestAgeMs + (newest.publishLagMs || 0) + presentation * 1000 + behind * 1000;
      result.delay.model = { newestAgeAtFirstPlaylistMs: round(firstOk.newestAgeMs), publishLagMs: round(newest.publishLagMs), presentationDelayMs: round(presentation * 1000), behindSeekEndMs: round(behind * 1000), sumMs: round(model), measuredMinusModelMs: round(result.delay.steady.median - model), note: 'valid while the player never stalled or seeked after its start (stock non-LL playlists)' };
    }
  }
  if (outages.length) {
    const o = outages[0], settle = 6;
    const before = inWindow(Math.max(warmup, o.startS - 10), o.startS), after = inWindow(o.endS + settle, Infinity);
    let recovered = null;                                   // first frame presented after the outage began and after a freeze
    for (let i = 1; i < N; i++) { const t = tS(f.expectedDisplay[i]); if (t > o.startS && f.expectedDisplay[i] - f.expectedDisplay[i - 1] - Math.max(1, f.presentedFrames[i] - f.presentedFrames[i - 1]) * frameMs > freezeMs) { recovered = round(t, 2); } if (t > o.endS + 30) break; }
    result.outage = { startS: o.startS, endS: o.endS, mode: o.mode, delayBeforeMs: round(median(before)), delayAfterMs: round(median(after)), deltaMs: before.length && after.length ? round(median(after) - median(before)) : null, afterWindowS: [round(o.endS + settle, 1), end], lastFreezeEndS: recovered, all: outages };
  }

  // ---- cadence
  const interval = [], perFrame = [], freezes = [], jumps = [];
  let skipped = 0, longFrames = 0, over50 = 0, anomalies = 0, callbacksSteady = 0;
  const jumpFrames = Math.max(8, Math.round(fps * 0.2));
  let firstSteady = -1;
  for (let i = Math.max(1, first + 1); i < N; i++) {
    const t = tS(f.expectedDisplay[i]);
    const dt = f.expectedDisplay[i] - f.expectedDisplay[i - 1], dp = f.presentedFrames[i] - f.presentedFrames[i - 1];
    const dn = number[i] - number[i - 1];
    // A freeze is display time NOT covered by frames submitted for composition: a late callback (busy main
    // thread) during which the compositor kept presenting frames (dp > 1) is not one.
    if (dt - Math.max(1, dp) * frameMs > freezeMs) freezes.push({ atS: round(tS(f.expectedDisplay[i - 1]), 2), ms: round(dt - (Math.max(1, dp) - 1) * frameMs), framesPresented: dp, framesJumped: Number.isNaN(dn) ? null : dn });
    // a jump = the frame number moved by >= 0.2 s more than the frames presented meanwhile, or went backwards
    const jumped = !Number.isNaN(dn) && (dn - Math.max(1, dp) >= jumpFrames || dn < 0);
    if (jumped) jumps.push({ atS: round(t, 2), frames: dn, mediaMs: round(dn * frameMs), wallMs: round(dt) });
    if (t < warmup) continue;
    if (firstSteady < 0) firstSteady = i - 1;
    callbacksSteady += 1;
    interval.push(dt);
    if (dp >= 1) { perFrame.push(dt / dp); if (dt / dp > 1.5 * frameMs) longFrames += 1; }
    if (dt > 50) over50 += 1;
    if (!Number.isNaN(dn) && !jumped) { skipped += dn - dp; if (dn !== dp) anomalies += 1; }
  }
  const steadySpanMs = firstSteady >= 0 ? f.expectedDisplay[N - 1] - f.expectedDisplay[firstSteady] : 0;
  const presentedSteady = firstSteady >= 0 ? f.presentedFrames[N - 1] - f.presentedFrames[firstSteady] : 0;
  const streamSteady = firstSteady >= 0 ? number[N - 1] - number[firstSteady] : 0;
  result.frames = {
    nominalFps: fps,
    callbacks: N, callbacksSteady,
    presentedFps: steadySpanMs ? round(presentedSteady / steadySpanMs * 1000, 2) : null,       // frames submitted for composition per second (metadata.presentedFrames)
    callbackFps: steadySpanMs ? round(callbacksSteady / steadySpanMs * 1000, 2) : null,         // frames this page observed per second
    streamFps: steadySpanMs ? round(streamSteady / steadySpanMs * 1000, 2) : null,              // frame numbers advanced per second (1x speed = nominal)
    callbackIntervalMs: dist(interval),
    perPresentedFrameMs: dist(perFrame),
    longFrames,                                  // callbacks whose interval per presented frame exceeded 1.5 frame durations
    intervalsOver50ms: over50,
    skippedFrames: skipped,                      // net: frame numbers advanced minus frames submitted for composition, jumps excluded (> 0 = frames dropped by the renderer)
    unevenCallbacks: anomalies,                  // callbacks where the two counts differed (they cancel out unless frames were dropped)
    jumps,                                       // frame-number steps of >= 0.2 s or backwards (seek, gap jump, resync)
    quality: page.quality || null,               // HTMLVideoElement.getVideoPlaybackQuality()
    pixel: { read: pixelRead.length, estimatedFromMediaTime: estimated, pictureOneFrameOff: offByOne, mappingChanges: remapped, invalid, mediaTimeMinusFrameS: dist(offsets, 4) },
  };
  if (N === 0 || first < 0) problems.push('no frame was presented');
  if (f.overflow) problems.push(`frame buffer overflow (${f.overflow})`);
  if (invalid.grey + invalid.parity > Math.max(3, N * 0.005)) problems.push(`frame counter unreadable on ${invalid.grey + invalid.parity} frames`);

  // ---- stalls
  const events = page.events || [];
  const spans = (startTest, endTest) => {
    const list = []; let open = null;
    for (const e of events) {
      if (open === null && startTest(e)) open = e.t;
      else if (open !== null && endTest(e)) { list.push({ atS: round(tS(open), 2), ms: round(e.t - open) }); open = null; }
    }
    if (open !== null) list.push({ atS: round(tS(open), 2), ms: round((page.finishedAt || open) - open), open: true });
    return list;
  };
  const summarize = (list, fromS) => { const kept = list.filter((s) => s.atS >= fromS); return { count: kept.length, totalMs: round(kept.reduce((sum, s) => sum + s.ms, 0)), list: kept }; };
  const buffering = spans((e) => e.type === 'shaka.buffering' && e.buffering, (e) => e.type === 'shaka.buffering' && !e.buffering);
  const waiting = spans((e) => e.type === 'video.waiting', (e) => e.type === 'video.playing' || e.type === 'video.seeked' || e.type === 'video.canplay');
  result.stalls = {
    note: 'after the first presented frame; start-up buffering is in startup',
    shakaBuffering: summarize(buffering, 0.05),
    videoWaiting: summarize(waiting, 0.05),
    // the gap right after the very first frame is start-up (in startup.firstFramesFreezeMs) unless it lasts
    freezes: Object.assign({ thresholdMs: freezeMs }, summarize(freezes.filter((x) => x.atS >= 0.5 || x.ms >= 500), 0)),
    shakaStallsDetected: page.finalStats ? page.finalStats.stallsDetected : null,
    shakaGapsJumped: page.finalStats ? page.finalStats.gapsJumped : null,
    shakaBufferingTimeS: page.finalStats ? round(page.finalStats.bufferingTime, 2) : null,
  };

  // ---- continuous playback: seconds in which at least 90 % of the nominal frames were submitted for composition
  {
    const perSec = new Map();
    for (let i = Math.max(1, first + 1); i < N; i++) { const sec = Math.floor(tS(f.expectedDisplay[i])); perSec.set(sec, (perSec.get(sec) || 0) + (f.presentedFrames[i] - f.presentedFrames[i - 1])); }
    const total = Math.max(0, Math.floor(result.durationS)); let smooth = 0, firstSmooth = null;
    for (let sec = 0; sec < total; sec++) if ((perSec.get(sec) || 0) >= 0.9 * fps) { smooth += 1; if (firstSmooth === null) firstSmooth = sec; }
    const frozenMs = freezes.reduce((sum, x) => sum + x.ms, 0);
    result.playback = { smoothSeconds: smooth, totalSeconds: total, smoothShare: total ? round(smooth / total, 3) : null, firstSmoothSecond: firstSmooth, frozenMs: round(frozenMs), frozenShare: result.durationS ? round(frozenMs / 1000 / result.durationS, 3) : null };
  }

  // ---- live position
  const rows = (page.timeline && page.timeline.rows) || [], steadyRowsTl = rows.filter((r) => tS(r[0]) >= warmup);
  result.live = {
    behindSeekEndS: dist(steadyRowsTl.map((r) => r[3] - r[1]), 3),
    bufferedAheadS: dist(steadyRowsTl.map((r) => r[4]), 3),
    seekRangeWidthS: dist(steadyRowsTl.map((r) => r[3] - r[2]), 3),
    playbackRate: { min: steadyRowsTl.length ? Math.min(...steadyRowsTl.map((r) => r[6])) : null, max: steadyRowsTl.length ? Math.max(...steadyRowsTl.map((r) => r[6])) : null, samplesNot1: steadyRowsTl.filter((r) => r[6] !== 1).length },
    bufferingSamples: steadyRowsTl.filter((r) => r[8]).length, samples: steadyRowsTl.length,
    shakaLiveLatencyS: dist((page.statsSeries || []).filter((s) => tS(s.t) >= warmup).map((s) => s.liveLatency), 3),
  };

  // ---- seek-to-live rule
  const seeks = events.filter((e) => e.type === 'rule.seek' || e.type === 'rule.rate').map((e) => ({ atS: round(tS(e.t), 2), type: e.type, behindS: round(e.behind, 3), referenceS: round(e.reference, 3), action: e.action || null, rate: e.rate ?? null, fromS: round(e.from, 3), toS: round(e.to, 3) }));
  result.seeks = { rule: (page.params && page.params.seekRule) || { type: 'none' }, count: seeks.filter((s) => s.type === 'rule.seek').length, list: seeks };

  // ---- origin side
  if (stats) {
    const requests = stats.requests || [];
    const playlists = requests.filter((r) => r.kind === 'playlist'), segments = requests.filter((r) => r.kind === 'segment'), parts = requests.filter((r) => r.kind === 'part');
    const ok = playlists.filter((r) => r.status === 200);
    const firstOk = ok[0] || null, firstSegment = segments.find((r) => r.status === 200) || null;
    const segMs = stats.options.seg * 1000;
    const byStatus = {}; for (const r of requests) byStatus[r.status] = (byStatus[r.status] || 0) + 1;
    const steadyReq = (list) => list.filter((r) => tS(toPage(r.t)) >= warmup);
    const distinct = new Set(segments.filter((r) => r.status === 200).map((r) => r.sequence));
    result.origin = {
      options: stats.options, derived: stats.derived,
      segments: stats.segments, irregularFragments: stats.ffmpeg.irregularFragments, connections: stats.connections, shape: stats.shape,
      requests: {
        total: requests.length, byStatus,
        playlist: { count: playlists.length, intervalMs: dist(steadyReq(ok).slice(1).map((r, i) => r.t - steadyReq(ok)[i].t)), newestAgeMs: dist(steadyReq(ok).map((r) => r.newestAgeMs)), blockedMs: dist(ok.filter((r) => r.blockedMs !== undefined).map((r) => r.blockedMs)) },
        segment: { count: segments.length, distinct: distinct.size, notFound: segments.filter((r) => r.status === 404).length, ageAtRequestMs: dist(steadyReq(segments).filter((r) => r.status === 200).map((r) => r.ageMs)), behindNewest: dist(steadyReq(segments).filter((r) => r.status === 200).map((r) => r.behindNewest), 0) },
        part: { count: parts.length, ageAtRequestMs: dist(parts.filter((r) => r.status === 200).map((r) => r.ageMs)), blockedMs: dist(parts.filter((r) => r.status === 200).map((r) => r.blockedMs)) },
        dropped: requests.filter((r) => r.status < 0 || r.dropped).length,
      },
    };
    result.startup = {
      loadCallToFirstFrameMs: page.loadCallAt !== undefined && first >= 0 ? round(f.expectedDisplay[first] - page.loadCallAt) : null,
      loadCallToLoadedMs: page.loadedAt !== undefined ? round(page.loadedAt - page.loadCallAt) : null,
      firstPlaylist: firstOk ? { afterLoadCallMs: round(toPage(firstOk.t) - page.loadCallAt), segments: firstOk.count ?? null, newestSequence: firstOk.newest, newestAgeMs: round(firstOk.newestAgeMs), joinPhase: round(firstOk.newestAgeMs / segMs, 2) } : null,
      firstSegment: firstSegment ? { afterLoadCallMs: round(toPage(firstSegment.t) - page.loadCallAt), sequence: firstSegment.sequence, behindNewest: firstSegment.behindNewest } : null,
      playlist503: playlists.filter((r) => r.status === 503).length,
      delayAtFirstFrameMs: result.delay.atFirstFrame,
      startupBufferingMs: buffering.length && buffering[0].atS < 0.05 ? buffering[0].ms : 0,
      firstFramesFreezeMs: round(freezes.filter((x) => x.atS < 0.5).reduce((sum, x) => sum + x.ms, 0)),
    };
  }

  // ---- player
  result.player = {
    userAgent: page.userAgent, shakaVersion: page.shakaVersion, configRequested: page.params ? page.params.config : null, configAccepted: page.configAccepted,
    effective: page.effectiveConfig ? { rebufferingGoal: page.effectiveConfig.streaming.rebufferingGoal, bufferingGoal: page.effectiveConfig.streaming.bufferingGoal, stallThreshold: page.effectiveConfig.streaming.stallThreshold, lowLatencyMode: page.effectiveConfig.streaming.lowLatencyMode, liveSync: page.effectiveConfig.streaming.liveSync, updateIntervalSeconds: page.effectiveConfig.streaming.updateIntervalSeconds, segmentPrefetchLimit: page.effectiveConfig.streaming.segmentPrefetchLimit, hls: page.effectiveConfig.hls, defaultPresentationDelay: page.effectiveConfig.manifest.defaultPresentationDelay, defaultBandwidthEstimate: page.effectiveConfig.abr.defaultBandwidthEstimate } : null,
    isLive: page.isLive ?? null, manifestType: page.manifestType ?? null, tracks: page.tracks || null, video: page.video || null,
    errors: events.filter((e) => e.type === 'shaka.error' || e.type === 'video.error' || e.type === 'bench.error' || e.type.startsWith('window.')),
  };
  if (page.error) problems.push('page error: ' + page.error.split('\n')[0]);
  if (result.player.errors.length) problems.push(`${result.player.errors.length} player error event(s)`);
  result.shakaStats = page.finalStats || null;
  result.events = events.filter((e) => !['video.ratechange', 'shaka.ratechange'].includes(e.type) || true).map((e) => Object.assign({}, e, { atS: round(tS(e.t), 2) })).slice(0, 4000);
  result.timeline = page.timeline ? { fields: page.timeline.fields.concat(['atS']), rows: rows.map((r) => r.concat([round(tS(r[0]), 2)])) } : null;
  result.verdict = { ok: problems.length === 0, problems };
  return result;
}

// One line per run, for tables.
function summary(result) {
  const d = result.delay.steady, s = result.stalls, o = result.origin ? result.origin.options : {};
  return {
    label: result.label, seg: o.seg, holdBack: o.holdBack || null, part: o.part || null,
    joinPhase: result.startup && result.startup.firstPlaylist ? result.startup.firstPlaylist.joinPhase : null,
    startupMs: result.startup ? result.startup.loadCallToFirstFrameMs : null,
    delayFirstMs: result.delay.atFirstFrame, delayMedianMs: d.median ?? null, delayP05Ms: d.p05 ?? null, delayP95Ms: d.p95 ?? null, delayMaxMs: d.max ?? null,
    driftMsPerMin: result.delay.driftMsPerMin,
    bufferedAheadS: result.live.bufferedAheadS.median ?? null, bufferedAheadMinS: result.live.bufferedAheadS.min ?? null, behindSeekEndS: result.live.behindSeekEndS.median ?? null,
    bufferingCount: s.shakaBuffering.count, bufferingMs: s.shakaBuffering.totalMs, freezeCount: s.freezes.count, freezeMs: s.freezes.totalMs,
    smoothShare: result.playback.smoothShare, firstSmoothSecond: result.playback.firstSmoothSecond, frozenShare: result.playback.frozenShare,
    presentedFps: result.frames.presentedFps, streamFps: result.frames.streamFps, skippedFrames: result.frames.skippedFrames, longFrames: result.frames.longFrames, jumps: result.frames.jumps.length,
    seeks: result.seeks.count,
    outageDeltaMs: result.outage ? result.outage.deltaMs : null, delayBeforeMs: result.outage ? result.outage.delayBeforeMs : null, delayAfterMs: result.outage ? result.outage.delayAfterMs : null,
    ok: result.verdict.ok, problems: result.verdict.problems.join('; '),
  };
}

module.exports = { analyze, summary, dist };

if (require.main === module) {
  const fs = require('fs');
  const args = process.argv.slice(2); const file = args.find((a) => !a.startsWith('--'));
  if (!file) { console.error('usage: node analyze.js <result.raw.json> [--warmup S] [--freeze-ms MS] [--summary]'); process.exit(2); }
  const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? Number(args[i + 1]) : undefined; };
  const result = analyze(JSON.parse(fs.readFileSync(file, 'utf8')), { warmup: opt('--warmup'), freezeMs: opt('--freeze-ms') });
  console.log(JSON.stringify(args.includes('--summary') ? summary(result) : result, null, 1));
}
