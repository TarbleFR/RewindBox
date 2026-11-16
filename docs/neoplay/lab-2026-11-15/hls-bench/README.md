# NeoPlay receiver bench

A measurement bench for RewindBox's Chromecast streaming (NeoPlay). It stands in for both ends:

- `origin.js` imitates the **sender** (NPMuxer + NPSegmentStore + NPHTTPServer): a real-time H.264 Baseline + AAC
  fragmented-MP4 stream cut into HLS segments, a playlist written by the bench itself, a tiny HTTP/1.1 server.
  Every playlist policy and every network impairment is a command-line parameter.
- `player.html` + `run.js` imitate the **receiver**: Shaka Player (the version Google's Web Receiver framework
  loads) in the preinstalled headless Chromium, configured as the framework configures it, sampled with
  `requestVideoFrameCallback`.

The output of a run is one JSON file with the glass-to-glass delay (capture wall clock of the frame -> wall
clock at which the page presents it), the frame cadence, stalls, the live position, Shaka's statistics and the
origin's request log.

No iPhone, no Chromecast, no Cast protocol here: see "What the lab cannot tell".

## Quick start

```sh
cd <bench>
export NODE_PATH=/opt/node-tools/node_modules     # where playwright is installed (run.js also tries this path itself)

# one run: IPA 743 playlist (0.5 s segments), receiver configuration, 60 s
node run.js --label demo --seg 0.5 --duration 60

# same stream, a player that is allowed to start at once (Shaka's own default rebufferingGoal = 0)
node run.js --label demo-rg0 --seg 0.5 --duration 60 --config-merge '{"streaming":{"rebufferingGoal":0}}'

# HOLD-BACK, an induced 2 s outage 20 s after the first frame, the sender's seek-to-live rule
node run.js --label hb --seg 0.5 --hold-back 1.0 --config-merge '{"streaming":{"rebufferingGoal":0}}' \
            --outage-at-play 20 --outage-secs 2 --seek-rule tracker --duration 60 --raw

# a whole plan (sequential by default; overloaded runs are repeated), then the tables
node matrix.js --plan plans/first.json --out-dir results/first --raw
cat results/first/summary.md

# only the origin (to look at the playlist, or to point another player at it)
node origin.js --port 8765 --seg 0.5 --hold-back 1.0 --exit-after 30 &
curl -s http://127.0.0.1:8765/s/lab/index.m3u8
curl -s http://127.0.0.1:8765/control/stats | head -c 600
```

`run.js` prints one JSON line (the summary) on stdout, writes `results/<label>.json` (or `--out`), exits 0 when
the run is valid and 1 otherwise (`verdict.problems` in the JSON says why). It needs no input, picks free ports
by default (`--port 0 --page-port 0`), and kills ffmpeg, the origin and the browser it started, also on
SIGINT/SIGTERM and on its own watchdog. Check afterwards with:

```sh
ps -eo pid,args | grep -E 'lab/bench|ffmpeg|chrome-headless' | grep -v grep
```

## Files

| file | role |
|---|---|
| `origin.js` | sender model: ffmpeg -> fMP4 -> segments/parts -> playlist -> HTTP, network shaping, capture clock |
| `player.html` | receiver model: Shaka Player page, per-frame sampling, seek-to-live rules |
| `run.js` | one run: starts origin + page server + Chromium, drives the page, writes the result |
| `analyze.js` | raw samples -> result JSON (also a command: `node analyze.js x.raw.json [--summary]`) |
| `matrix.js` | runs a plan of runs, writes `summary.json` and `summary.md` |
| `lib/origin-options.js` | the origin's options (single source for `origin.js`, `run.js`, `matrix.js`) |
| `plans/*.json` | the plans behind the tables below |
| `vendor/` | Shaka builds fetched from `ajax.googleapis.com` (cached) |
| `results/` | results of the first matrix (`*.json` result, `*.raw.json` raw samples, `summary.md`) |

## The sender model (`origin.js`)

What is imitated, from `packages/neoplay_bridge/ios/Classes`:

- one muxed fMP4 rendition, H.264 Baseline without B-frames + AAC-LC 48 kHz stereo, one `EXT-X-MAP` init segment;
- media segments of `--seg` seconds, each starting on a key picture, **published only once complete**
  (ffmpeg's mp4 muxer emits a fragment when the next key picture arrives; the origin publishes it on arrival);
- the playlist of `NPSegmentStore.response`: `#EXT-X-VERSION:7`, `#EXT-X-TARGETDURATION:1` (fixed),
  `MEDIA-SEQUENCE`, `DISCONTINUITY-SEQUENCE`, `EXTINF` with 6 decimals, no `PROGRAM-DATE-TIME`, the newest
  segments only (at least 6 **and** at least 3 s), 503 until 3 segments exist, 24 segments kept in the store
  and still served after they left the playlist;
- the HTTP server of `NPHTTPServer`: raw TCP, one request per connection, `Connection: close`,
  `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`, GET/HEAD/OPTIONS, 403 outside the prefix, at most
  8 connections, each cut 8 s after accept. No `Date` header, no Range support (as the sender).

What differs: the picture is a 640x360 test pattern at about 1 Mbit/s (not 1280x720 at 11-12 Mbit/s), the
encoder is x264 `ultrafast`/`zerolatency`, the muxer is ffmpeg's (not AVAssetWriter), the transport is loopback.

ffmpeg does **not** write the playlist. It writes fragmented MP4 to a pipe; the origin parses the box stream
(`ftyp`+`moov` = init segment, each `moof`+`mdat` = a fragment, video sample count and key flag read from
`trun`/`tfhd`) and does segmentation, playlist and serving itself.

### Origin options

`node origin.js --help` prints the list (from `lib/origin-options.js`). `run.js` and `matrix.js` accept the same
names and pass them through.

| option | default | meaning |
|---|---|---|
| `--port` | 8765 (`run.js`: 0) | TCP port; 0 = any free port (the real one is in the `ready` line on stdout) |
| `--host` | 127.0.0.1 | listen address |
| `--prefix` | `/s/lab/` | URL prefix of the stream (the sender uses `/s/<secret>/`) |
| `--seg` | 0.5 | segment length, seconds (whole number of frames): 1 = pre-743 sender, 0.5 = IPA 743 |
| `--gop` | 0 | key picture interval, seconds; 0 = one per segment (as the sender); must divide `--seg` |
| `--long-segments` | (none) | comma-separated sequence numbers of segments made twice as long (irregular EXTINF) |
| `--fps` | 60 | frame rate |
| `--size` | 640x360 | picture size (width >= 368 for the frame counter) |
| `--bitrate` / `--audio-bitrate` | 1000 / 96 | kbit/s |
| `--window-segments` | 6 | playlist advertises at least this many segments |
| `--window-seconds` | 3 | ... and at least this many seconds |
| `--start-segments` | 3 | 503 until this many segments exist |
| `--target-duration` | 1 | `#EXT-X-TARGETDURATION`; `auto` = ceil(segment length) |
| `--hls-version` | 7 | `#EXT-X-VERSION` |
| `--store-segments` | 24 | segments kept and served after leaving the playlist |
| `--hold-back` | 0 | adds `#EXT-X-SERVER-CONTROL:HOLD-BACK=<s>` (0 = no tag, as the sender) |
| `--pdt` | off | adds `#EXT-X-PROGRAM-DATE-TIME` (capture wall clock) before every segment |
| `--extra-tags` | (none) | extra header lines, separated by `\|` |
| `--part` | 0 | LL-HLS part length, seconds (0 = off); see "LL-HLS" |
| `--part-hold-back` | 3 x part | `PART-HOLD-BACK` |
| `--can-block-reload` | on | with parts: `CAN-BLOCK-RELOAD=YES`, `_HLS_msn` / `_HLS_part` honoured |
| `--parts-segments` | 3 | with parts: newest complete segments that still list their parts |
| `--preload-hint` | on | with parts: `#EXT-X-PRELOAD-HINT`, the hinted part request blocks until it exists |
| `--delay-ms` | 0 | delay added to every stream response (half before the content is chosen, half before the first byte) |
| `--jitter-ms` | 0 | uniform random +-jitter on that delay, per response |
| `--rate-kbps` | 0 | throughput cap shared by all stream responses (token bucket, ~10 ms chunks); 0 = none |
| `--outage-at` | -1 | induced outage, seconds after **origin start** (`run.js --outage-at-play` is relative to the first frame) |
| `--outage-secs` | 2 | outage length |
| `--outage-mode` | hold | `hold`: requests received during the outage and bodies in flight freeze, then resume with the content of that moment (lost Wi-Fi with TCP retransmission); `reset`: connections are destroyed during the outage |
| `--conn-timeout` | 8 | a connection is cut this many seconds after accept (0 = never) |
| `--max-conns` | 8 | connections beyond this are refused (0 = unlimited) |
| `--exit-after` | 0 | the origin exits by itself after this many seconds |
| `--max-seconds` | 3600 | safety: ffmpeg stops by itself |
| `--log` | off | one JSON line per event on stdout |

Control endpoints (never shaped, never in an outage, CORS open), under `http://host:port/control/`:
`time` (origin clock), `stats` (everything: options, capture clock, every published segment, every request),
`capture` (capture wall clock of every frame), `playlist` (current text, readiness), `outage?in=S&secs=S&mode=hold|reset`,
`shape?delay-ms=&jitter-ms=&rate-kbps=` (change shaping while running), `stop`.

With no throughput cap a body is written in one call: on loopback it is in the kernel at once, so a `hold`
outage delays requests but cannot freeze a body half-way. Use `--rate-kbps` to make bodies take time.

### LL-HLS (experimental)

`--part 0.1` makes the origin ask ffmpeg for one fragment per sample (`frag_every_frame`), regroup them into
parts of exactly that many frames, and write `EXT-X-PART-INF`, `EXT-X-PART` (for the newest `--parts-segments`
segments and the one in progress), `EXT-X-PRELOAD-HINT`, `EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES,PART-HOLD-BACK=...`;
`_HLS_msn`/`_HLS_part` requests and the hinted part block until the part exists. ffmpeg writes unusable video
timing in that mode (sample duration 0, repeated `tfdt`); the origin rewrites `tfhd`/`tfdt` of the video track.
State: Shaka 4.15.56 with `streaming.lowLatencyMode=true` loads parts and plays about 0.7 s closer to live,
but it skips parts from time to time in this lab (holes, then freezes); not investigated further. With
`lowLatencyMode=false` (what the receiver framework leaves) the parts are ignored and nothing is gained.
Try: `node run.js --seg 0.5 --part 0.1 --hls-version 9 --config-merge '{"streaming":{"rebufferingGoal":0,"lowLatencyMode":true}}'`.

## The receiver model (`player.html`, `run.js`)

`run.js` serves `player.html` and the Shaka build from its own port (another origin than the stream, so CORS is
exercised as on the receiver), opens it in headless Chromium, waits for the playlist to stop answering 503 (the
sender issues LOAD at that moment), waits `--load-delay` seconds (LOAD round trip + receiver start, unknown on
a real device), optionally aligns to `--join-phase`, calls `player.load(url, undefined, 'application/vnd.apple.mpegurl')`,
measures `--duration` seconds from the first presented frame, collects, cleans up.

### Receiver configuration

Read in `lab/caf/cast_receiver_framework.js` (downloaded today):

- default Shaka version: function `Id()` returns `experiment_shaka_version` or `default_shaka_version` from the
  device's receiver flags, else **`"4.15.56"`**; the script comes from
  `//ajax.googleapis.com/ajax/libs/shaka-player/<version>/shaka-player.compiled.js`;
- HLS goes to Shaka unless the device flags say otherwise (`use_shaka_for_hls` defaults to true,
  `forced_opt_out_of_shaka_for_hls` can exclude a device, an application can set `useShakaForHls`);
- what the framework passes to `player.configure()` (function `ko`), for a version >= 4.15 and < 5:

```json
{ "abr": { "defaultBandwidthEstimate": 2000000, "removeLatencyFromFirstPacketTime": false },
  "manifest": { "retryParameters": { "maxAttempts": 4, "baseDelay": 400, "backoffFactor": 2, "timeout": 30000 } },
  "streaming": { "rebufferingGoal": 10, "stallThreshold": 5, "dispatchAllEmsgBoxes": true,
                 "retryParameters": { "maxAttempts": 4, "baseDelay": 400, "backoffFactor": 2, "timeout": 30000 } },
  "mediaSource": { "codecSwitchingStrategy": "reload" } }
```

`rebufferingGoal` is `playbackConfig.autoResumeDuration || 10`, `defaultBandwidthEstimate` is
`playbackConfig.initialBandwidth || 2e6`. The framework may add device-specific Shaka settings from its flags
(function `io`): unknown here. This object is `--config receiver` (the default). `--config shaka` passes
nothing; note that Shaka's own default `codecSwitchingStrategy` ("smooth") makes it call `changeType` to a
video-only type on this muxed stream and fail with error 3014, so keep `receiver` and override single keys
with `--config-merge`.

### Run options

Origin options (table above) plus:

| option | default | meaning |
|---|---|---|
| `--label` | run | name of the run, default file name |
| `--out` | `results/<label>.json` | result file |
| `--raw` | off | also write `<out>.raw.json` (every sample; `analyze.js` recomputes the result from it) |
| `--duration` | 60 | seconds measured after the first presented frame |
| `--warmup` | 5 | seconds after the first frame left out of the "steady" statistics |
| `--freeze-ms` | 100 | display time without a new frame beyond which a freeze is counted |
| `--page-port` | 0 | port of the page server |
| `--origin-url` | (none) | use a running origin (its playlist URL) instead of starting one |
| `--shaka-version` | 4.15.56 | fetched once from ajax.googleapis.com into `vendor/` (through `curl`, proxy honoured) |
| `--shaka-file` / `--shaka-debug` | | a local build / the `compiled.debug` build |
| `--config` | receiver | `receiver`, `shaka`, a JSON object, or `@file` |
| `--config-merge` | (none) | JSON merged over `--config` |
| `--seek-rule` | none | `none`, `tracker`, `rate`, or JSON (below) |
| `--seek-action` | (rule's) | `currentTime` (`video.currentTime = player.seekRange().end`) or `goToLive` (`player.goToLive()`) |
| `--outage-at-play` | -1 | induce an outage this many seconds after the first presented frame (`--outage-secs`, `--outage-mode`) |
| `--load-delay` | 2 | seconds between "playlist ready" and `player.load()` |
| `--join-phase` | -1 | 0..1: call `player.load()` at this fraction of a segment after a segment was published |
| `--pixel-every` | 1 | read the frame counter in the picture on every Nth presented frame (0 = never, no delay figures) |
| `--sample-ms` | 250 | period of the timeline samples |
| `--muted` | off | mute the video element |
| `--browser-channel` | (headless shell) | `chromium` = the full Chromium build in new headless mode |
| `--browser-args` | [] | extra Chromium arguments (JSON array); `--autoplay-policy=no-user-gesture-required` is always set |
| `--console-filter`, `--console-lines` | | keep only matching browser console lines (useful with `--shaka-debug`) |
| `--start-timeout` | 40 | seconds allowed between `player.load()` and the first presented frame |
| `--quiet` | off | print nothing but errors |

Seek-to-live rules (`--seek-rule`), evaluated in the page every `period` seconds while the player is playing
(not paused, not seeking, not buffering), on `behind = player.seekRange().end - video.currentTime`, which is
what the sender reads through `approximateLiveSeekableRangeEnd() - approximateStreamPosition()`:

- `tracker`: a port of `NPLiveLagTracker` (`period` 1, `excess` 1, `checks` 2, `settle` 3, `cooldown` 15; the
  reference is the smallest lag seen, learnt again after each seek). Action: `currentTime` or `goToLive`.
- JSON, to change anything: `{"type":"tracker","excess":0.5,"checks":1,"cooldown":5,"reference":0.2,"action":"goToLive","margin":0}`
  (`reference`: a fixed reference lag instead of the learnt minimum; `margin`: seconds kept before `seekRange().end`).
- `rate`: catch up with `video.playbackRate` instead of seeking:
  `{"type":"rate","excess":0.5,"checks":2,"rate":1.1,"release":0.25}`.

The lab reads the exact values every period; the real sender reads values extrapolated from Cast media status.

### Plans (`matrix.js`)

```json
{ "defaults": { "duration": 60, "config-merge": { "streaming": { "rebufferingGoal": 0 } } },
  "runs": [ { "label": "seg0.5", "args": { "seg": 0.5 }, "phases": [0.1, 0.5, 0.9], "note": "stock" } ] }
```

Keys are `run.js` option names without the dashes; `phases` gives `--join-phase` for each repetition (`repeat`
for plain repetitions). `node matrix.js --plan P --out-dir D [--concurrency 1] [--retries 2] [--only text] [--raw]`;
`--summarize [--reanalyze]` rebuilds the tables from the files present (and recomputes results from raw samples).
A run whose verdict says "lab overloaded" is repeated (the first attempt is kept as `*.attemptN.json`).

## How the delay is measured, and how far to trust it

1. **Frame counter in the picture.** ffmpeg burns a binary counter into the top-left 368x16 pixels of every
   frame (`drawbox` filters enabled by expressions on the frame number `n`): one white reference block, one
   black, 20 bits, one parity bit, 16 px each. The page reads it back from a canvas in the frame callback.
2. **Capture clock.** The last filter is `showinfo`: ffmpeg prints one line per frame on stderr when the frame
   leaves the filter graph for the encoder. The origin timestamps each line with its clock
   (`performance.timeOrigin + performance.now()`). ffmpeg reads its inputs with `-re -readrate_initial_burst 0`,
   so frame `n` leaves at `t0 + n/fps`; `t0` is the median of `(line time - n/fps)` (first 2 s ignored: ffmpeg
   starts late and catches up). The capture time of a frame is `t0 + n/fps`.
3. **Presentation clock.** `requestVideoFrameCallback` gives `expectedDisplayTime` (when the frame is expected on
   glass) on the page's `performance.now()` scale. The page compares that scale with the origin clock by request
   / response midpoint against `/control/time` (best of 15, at the start and at the end of the run).
4. **Delay** of a presented frame = `expectedDisplayTime` mapped to the origin clock - `(t0 + n/fps)`.
   `metadata.mediaTime` of the callback identifies the frame; the picture reads calibrate the mapping
   mediaTime -> frame number (running median of 9 reads). Reason: `drawImage()` in the callback returns the
   *next* frame on about 6 % of the callbacks, which would bias those samples by one frame duration. If picture
   and metadata disagree by more than two frames (seek, gap jump), the picture wins.

Verified empirically (numbers from the runs in `results/`, see `clock`, `frames.pixel`, `delay.model` in each JSON):

<<VERIFY>>

The lab's own error on a delay figure is therefore about one frame duration (16.7 ms at 60 fps) plus the
capture grid jitter (ffmpeg hands a frame to the encoder between 3 ms early and 10 ms late around the nominal
grid, `clock.captureResidualMs`).

What a delay figure **contains**: x264 zero-latency encoding, the wait for the segment to be complete, ffmpeg's
muxing lag (the fragment leaves ffmpeg 50-70 ms after the capture of the following key picture: AAC encoder
delay + interleaving; `origin.segments.publishLagMs`), loopback HTTP, Shaka's buffer, software decoding, and the
headless compositor's `expectedDisplayTime`. What it **does not contain**: ReplayKit capture and scaling, the
iPhone's hardware encoder and AVAssetWriter, Wi-Fi, the Chromecast's decoder and video pipeline, the TV.

### Lab health

Other jobs on the machine starve ffmpeg, the page's main thread (Shaka runs there) or the decoder, and would pass
for stutter. Each result has `labHealth` (ffmpeg pacing p99, latest segment publication, lateness of the page's
250 ms timer); beyond its limits the verdict says `lab overloaded` and `matrix.js` repeats the run. Freezes are
counted from display time **not covered by frames submitted for composition** (`presentedFrames`), so a late
callback alone is not a freeze. In this headless Chromium the callback observes about 75-85 % of the presented
frames (the others are submitted between two callbacks; `frames.presentedFps` counts them all).

## Result JSON (`schema: "neoplay-bench/1"`)

Times `atS` / `...S` are seconds since the first presented frame; delays are milliseconds. Distributions are
`{ n, median, mean, p05, p25, p75, p95, p99, min, max }`.

| key | content |
|---|---|
| `label`, `startedAt`, `command`, `options` | identification; `options` = every `run.js` option of the run |
| `durationS` | time between first and last presented frame |
| `verdict` | `{ ok, problems[] }` |
| `labHealth` | `captureResidualP99Ms`, `captureResidualMaxMs`, `publishIntervalMaxExcessMs`, `pageTimerLateP99Ms`, `pageTimerLateMaxMs`, `limits`, `ok` |
| `clock` | `pageToOriginRttMs {start,end}`, `pageToOriginDriftMs`, `captureResidualMs`, `captureDriftMs` |
| `startup` | `loadCallToFirstFrameMs`, `loadCallToLoadedMs`, `firstPlaylist { afterLoadCallMs, segments, newestSequence, newestAgeMs, joinPhase }`, `firstSegment { sequence, behindNewest }`, `playlist503`, `delayAtFirstFrameMs`, `startupBufferingMs`, `firstFramesFreezeMs` |
| `delay` | `atFirstFrame`, `firstSecond`, `steady` (after `--warmup`), `whole`, `steadyPresentationTime` (same with `presentationTime` instead of `expectedDisplayTime`), `first10s`, `last10s`, `driftMsPerMin` (slope of the per-second medians), `perSecond` rows `[second, median, min, max, frames]`, `model` (independent cross-check, below) |
| `outage` | only with an outage: `startS`, `endS`, `mode`, `delayBeforeMs` (median of the 10 s before), `delayAfterMs` (median from 6 s after the end to the end of the run), `deltaMs`, `lastFreezeEndS` |
| `frames` | `presentedFps` (frames submitted for composition per second), `callbackFps`, `streamFps` (frame numbers per second: 60 = real time), `callbackIntervalMs`, `perPresentedFrameMs`, `longFrames` (> 1.5 frame durations per presented frame), `intervalsOver50ms`, `skippedFrames` (stream frames never submitted, jumps excluded), `jumps[] { atS, frames, mediaMs, wallMs }` (steps >= 0.2 s or backwards), `quality` (`getVideoPlaybackQuality()`), `pixel { read, estimatedFromMediaTime, pictureOneFrameOff, mappingChanges, invalid, mediaTimeMinusFrameS }` |
| `playback` | `smoothSeconds` / `totalSeconds` / `smoothShare` (seconds with >= 90 % of the nominal frames), `firstSmoothSecond`, `frozenMs`, `frozenShare` |
| `stalls` | `shakaBuffering { count, totalMs, list[] }` (Shaka `buffering` events after the first frame), `videoWaiting`, `freezes { thresholdMs, count, totalMs, list[] { atS, ms, framesPresented, framesJumped } }`, `shakaStallsDetected`, `shakaGapsJumped`, `shakaBufferingTimeS` |
| `live` | steady-state distributions of `behindSeekEndS` (`seekRange().end - currentTime`), `bufferedAheadS`, `seekRangeWidthS`, `shakaLiveLatencyS`; `playbackRate { min, max, samplesNot1 }`; `bufferingSamples` / `samples` |
| `seeks` | `rule`, `count`, `list[] { atS, type, behindS, referenceS, action, fromS, toS, rate }` |
| `origin` | `options`, `derived`, `segments { published, bytes, publishLagMs, publishIntervalMs }`, `connections`, `shape`, `requests { total, byStatus, playlist { count, intervalMs, newestAgeMs, blockedMs }, segment { count, distinct, notFound, ageAtRequestMs, behindNewest }, part {...}, dropped }` |
| `player` | `userAgent`, `shakaVersion`, `configRequested`, `configAccepted`, `effective` (what `getConfiguration()` returned: rebufferingGoal, bufferingGoal, stallThreshold, lowLatencyMode, liveSync, hls, ...), `isLive`, `tracks`, `errors[]` |
| `shakaStats` | final `player.getStats()` (without the histories) |
| `events` | every player / video / rule event `{ t, atS, type, ... }` (`buffered` ranges on `waiting`, `seeking`, `gapjumped`) |
| `timeline` | `fields` + `rows`, every `--sample-ms`: `t, currentTime, seekStart, seekEnd, bufferedAhead, bufferedEnd, playbackRate, readyState, buffering, paused, ranges, atS` |
| `browser` | Chromium version, channel, console lines |

`delay.model` is the cross-check that does not use the frame counter:
`newestAgeAtFirstPlaylistMs + publishLagMs + presentationDelayMs (HOLD-BACK or three segments) + behindSeekEndMs`,
and `measuredMinusModelMs` (expected: about one display frame). It only holds while the player has not stalled
or seeked since it started.

The raw file (`--raw`) is `{ meta, page, originStats }`: `page.frames` holds the per-callback arrays
(`callbackTime`, `expectedDisplay`, `presentation`, `mediaTime`, `currentTime`, `presentedFrames`, `frameNumber`,
`processing`), `originStats` is `/control/stats` at the end of the run.

<<RESULTS>>

## What the lab cannot tell

- The Chromecast's decode and display delay, its video pipeline, its TV: not in any figure.
- Wi-Fi: loopback here. `--delay-ms`, `--jitter-ms`, `--rate-kbps` and outages only imitate it.
- The receiver's real firmware, flags and player choice: the framework can take another Shaka version or
  device-specific Shaka settings from its flags, or use its own HLS player instead of Shaka on some devices.
- Cast itself: LOAD, media status, the timing of the sender's lag readings and of its SEEK.
- ReplayKit, the iPhone encoder and AVAssetWriter: capture delay, the real publication lag of a segment, real
  segment durations (the lab's are exact).
- Display cadence: headless Chromium has a synthetic 60 Hz display. Judder from 60 fps content on a 50 or
  59.94 Hz output cannot be seen; freezes, skipped frames, jumps and rate changes can.
- CPU pressure on the receiver: the picture is small and decoded in software on a shared 4-core machine.

## Troubleshooting

- `verdict.problems` contains `lab overloaded`: run it again, alone (`matrix.js` does it).
- `shaka error 3014` right after the start: `--config shaka` (see "Receiver configuration").
- Nothing plays with the default configuration: expected, see the results. Add
  `--config-merge '{"streaming":{"rebufferingGoal":0}}'` to study playlist policies with a player that starts.
- Leftovers after a crash: `pkill -f lab/bench/run.js; pkill -f lab/bench/origin.js` (ffmpeg dies with its origin).
