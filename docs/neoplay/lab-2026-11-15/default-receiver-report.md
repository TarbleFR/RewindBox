# What Google's Default Media Receiver does with RewindBox's live HLS stream

Investigator: caf-internals. Date of all fetches and runs: 2026-11-15. Read-only on the repository.

Labels used: **VERIFIED** (how is stated), **EMULATED** (measured here in headless Chromium, not on a
Chromecast), **INFERRED** (derived from code that was read, not observed running), **UNKNOWN**.
Nothing in this report was measured on a Chromecast, an iPhone or the owner's network.

## 0. Material and method

| What | Where it came from | Identity |
|---|---|---|
| Web Receiver framework | `https://www.gstatic.com/cast/sdk/libs/caf_receiver/v3/cast_receiver_framework.js` | sha256 `269c68fd…ecaa9` (identical to the local copy), `last-modified: Tue, 10 Nov 2026`, `cast.o.VERSION = "3.0.0157"` |
| Default Media Receiver page | `https://www.gstatic.com/cast/sdk/default_receiver/1.0/app.html` | sha256 `b177f05f…d1fa`, 1884 bytes |
| App id -> page mapping | `https://clients3.google.com/cast/chromecast/device/app?a=CC1AD845` | JSON: `"display_name":"Default Media Receiver"`, `"url":"https://www.gstatic.com/cast/sdk/default_receiver/1.0/app.html?skin=…/eureka/player/0000/skins/cast/skin.css"` |
| Shaka Player as loaded by the framework | `https://ajax.googleapis.com/ajax/libs/shaka-player/4.15.56/shaka-player.compiled(.debug).js` | `shaka.Player.version = v4.15.56`, sha256 `0a370230…2137` (compiled), `d7dd496f…89a3` (debug) |
| MPL (old player) | `https://www.gstatic.com/cast/sdk/libs/mediaplayer/1.0.0/media_player.js` | sha256 `60b5baf5…f7f3`, 230 KB |
| iOS sender headers | local GoogleCast 4.8.6 headers | read only |
| Official pages | developers.google.com/cast: `docs/web_receiver/shaka_migration`, `docs/release-notes`, `docs/web_receiver/live`, `docs/reference/web_receiver/cast.framework.CastReceiverOptions`, `…PlaybackConfig` | fetched 2026-11-15 |

The three JavaScript files were pretty-printed with the preinstalled prettier (print width 160) and read.
Line numbers below refer to those pretty-printed copies (`src/crf.pretty.js`, `src/shaka-4.15.56.debug.pretty.js`,
`src/mpl.pretty.js`). The longer extracts are in `evidence/extracts.md` (56 extracts, tagged E1…E16, S1…S7, M1…M3).

Two things were executed, both in the preinstalled Playwright Chromium (headless Chrome 153, which
supports H.264/AAC in MSE here):

1. `tools/dump_config.js`: loads Google's Shaka 4.15.56 build under a Chromecast user agent (`…CrKey/1.56…`), applies
   the configuration object the framework builds, prints `player.getConfiguration()` (`out/config_dump_crkey_linux.json`).
2. `tools/livesim.js`: a local HTTP server that publishes a sliding HLS playlist shaped like `NPSegmentStore`
   (version 7, `TARGETDURATION:1`, six fMP4 segments of 0.5 s, `EXT-X-MAP`, no PDT, `Connection: close`,
   a segment is listed only once complete) plus Shaka 4.15.56 configured like the receiver. It is **not** the
   receiver page and **not** a Chromecast: it shows player logic only. Results in `out/res_A|B|C.json`.

## 1. Short answers

1. **Shaka version**: `"4.15.56"` hard-coded default; a platform flag (`experiment_shaka_version`, then
   `default_shaka_version`) can replace it per device; the receiver app could pin one but the default receiver does not.
2. **Shaka or MPL for HLS**: Shaka when the flag `use_shaka_for_hls` is true (default true when absent) and the
   **receiver application id** is not in the flag `forced_opt_out_of_shaka_for_hls`; otherwise MPL. Flags come from the
   Cast platform (`cast.__platform__.queryPlatformValue("receiver-flags")`), never from the sender.
   `hlsSegmentFormat`/`hlsVideoSegmentFormat` play no part in the choice; they are only passed to MPL.
3. **Shaka configuration for our load**: Shaka defaults plus `streaming.rebufferingGoal = 10`,
   `streaming.stallThreshold = 5`, `abr.defaultBandwidthEstimate = 2e6`, retry parameters
   `{maxAttempts 4, baseDelay 400 ms, backoff 2, timeout 30 s}`, `mediaSource.codecSwitchingStrategy = reload`,
   `stallSkip = 0` (Shaka's own Chromecast adjustment). `lowLatencyMode = false`, `liveSync.enabled = false`,
   `manifest.defaultPresentationDelay = 0`, `hls.liveSegmentsDelay = 3`, `bufferingGoal = 10`,
   `segmentPrefetchLimit = 1`, gap jumping at defaults. A platform flag can add per-device overrides (values UNKNOWN).
4. **Sender levers in LOAD**: none on buffering or live delay. `currentTime` only moves the start point, and every
   value other than "absent" makes it worse or equal. `customData` is echoed, `streamType` is cosmetic.
   The real levers are in the **playlist the phone serves** (`EXT-X-SERVER-CONTROL:HOLD-BACK`, `EXT-X-START`, the
   content and timing of the first playlist response, segment length) and in two media commands
   (`SEEK`, `SET_PLAYBACK_RATE` 0.5–2).
5. **MEDIA_STATUS for live**: `currentTime` and `liveSeekableRange` are Shaka's values minus the seek-range start
   seen at load; `liveSeekableRange.end` is Shaka's live edge minus its presentation delay, a pure wall-clock
   extrapolation locked at the first playlist parse. `media.startAbsoluteTime` is only filled when the sender put
   `sectionStartAbsoluteTime` in the metadata, and then it is `receiver now − liveSeekableRange.end`.
   `EXT-X-PROGRAM-DATE-TIME` changes none of these.
6. **Commands**: SEEK is clamped to the live range and **ignored when it would move the position by less than 1 s**;
   SET_PLAYBACK_RATE accepts 0.5 to 2 and is applied to the media element; PLAY after a pause may seek.
7. **MPL**: plays `3 × TARGETDURATION` (integer) behind the end of the playlist, reloads the playlist every
   `TARGETDURATION`, pauses below 1 s of buffer and resumes at `min(3 segments, 10 s)`, supports fMP4, and declares
   the stream finished after three unchanged reloads.
8. **Stalls**: Shaka's buffering state drives BUFFERING; with `rebufferingGoal = 10` a live stream that plays less
   than 10 s behind the edge can only leave that state when its buffer reaches Shaka's wall-clock live edge.
   **EMULATED: with RewindBox's playlist shape this left playback frozen at start in 9 of 10 runs (0.5 s segments)
   and 4 of 5 runs (1 s segments).** Critical Shaka errors end in IDLE/ERROR; recoverable ones only send an ERROR message.

## 2. The default receiver page (VERIFIED: read the page)

The whole application is:

```js
a = cast.framework.CastReceiverContext.getInstance();
a.getPlayerManager().setMessageInterceptor(cast.framework.messages.MessageType.LOAD, g);   // g: media.entity -> contentId only
a.start({supportedCommands: cast.framework.messages.Command.ALL_BASIC_MEDIA | cast.framework.messages.Command.STREAM_TRANSFER})
```

No `playbackConfig`, no `shakaVersion`, no `useShakaForHls`, no handling of `customData`. `ALL_BASIC_MEDIA` is 12303
(PAUSE 1, SEEK 2, STREAM_VOLUME 4, STREAM_MUTE 8, EDIT_TRACKS 4096, PLAYBACK_RATE 8192). `enforceSupportedCommands`
is not set, so commands are executed without checking the mask (E10e, E15).

## 3. Question 1: the Shaka version

VERIFIED (framework, E1b, E3):

```js
Hd = function (a) { return Gd(a, "experiment_shaka_version"); };
Id = function () { var a = Ad.K(), b = Hd(a); return b ? b : Gd(a, "default_shaka_version") || "4.15.56"; };
…
g = g ? Gn(g) : Id();                       // g = CastReceiverOptions.shakaVersion, absent for the default receiver
a || (Cn(d || "//ajax.googleapis.com/ajax/libs/shaka-player/" + g + "/shaka-player." + (b === "DEBUG" ? "compiled.debug" : "compiled") + ".js", Ct), …
```

- Order: flag `experiment_shaka_version`, else flag `default_shaka_version`, else `"4.15.56"`.
- A receiver app may pass `shakaVersion` (validated by `Gn`: below 2.5.6 or at/above 6.0.0 falls back to the default) or
  `shakaUrl`; the default receiver passes neither.
- Official confirmation: release notes, "July 16, 2026 (Web Receiver 3.0.0156): The default Shaka Player version used by
  CAF is updated from 4.9.2 to 4.15.56" and "Default useShakaForHls to true"; `CastReceiverOptions.shakaVersion`:
  "for example "4.15.56" (the current default) … Supported versions are >=4.15.56 <6.0.0".
- So a device, through its platform flags, **can** run another version. The flag values on a given Chromecast are UNKNOWN.

## 4. Question 2: Shaka or MPL

VERIFIED (framework, E4, E2):

```js
Xo = function (a) { …
  b = cast.o.rf.get();                                        // CastReceiverOptions given to start()
  var n = Ad.K(), p = Gd(n, "forced_opt_out_of_shaka_for_hls");
  p = p ? p.split(";") : [];
  c = n.j && p.includes(n.j) ? !1 : Ed(n, "use_shaka_for_hls", !0);
  ((d = b) == null ? void 0 : d.useShakaForHls) !== void 0 && (c = b.useShakaForHls);
  …
  switch (e) {                                                 // e = mime type, lower case
    case "application/x-mpegurl": case "application/vnd.apple.mpegurl": case "audio/mpegurl": case "audio/x-mpegurl":
      if (c) return (…, m.return(cast.o.media.Fc.Fc.create(a, zo.create)));      // Shaka
    case "application/vnd.ms-sstr+xml": case "application/dash+xml":
      return ((k = No.create), (l = Ro.create), cast.o.common.zd.aj && e === "application/dash+xml" && (…Shaka…), m.return(k(a, l)));   // MPL
  }
  return e.startsWith("image/") ? m.return(Promise.resolve(new On(a))) : m.return(new Co(a, Go));   // plain <video src=url>
```

- `n.j` is **not** a device model. It is set by `Ad.K().j = a.L.id` where `a.L = { id: b.applicationId, … }` (E2): the
  forced opt-out list is a `;`-separated list of **receiver application ids**. Whether `CC1AD845` is on a device's list is UNKNOWN.
- Flag source: `Dd = function (a) { a.h = a.h || Qc("receiver-flags") || null; … }` with
  `Qc = function (a) { if (cast.__platform__ && cast.__platform__.queryPlatformValue) return cast.__platform__.queryPlatformValue(a); … }` (E1).
  The values are handed over by the Cast shell of the device. They were looked for in the public
  `clients3.google.com/cast/chromecast/device/baseconfig` (2.7 MB, 594 experiments) and are **not there**
  (searched for `shaka`, `receiver_flags`, `use_shaka`, `forced_opt_out`): UNKNOWN for any real device.
- The mime type comes from the LOAD (`contentType`), or from the URL extension when the declared type is not a
  streaming type (`m3u8 -> application/x-mpegurl`) (E5). Our `application/vnd.apple.mpegurl` goes to the HLS branch.
- `hlsSegmentFormat` and `hlsVideoSegmentFormat` appear in exactly one consumer: the MPL protocol factory
  `Mo(a.j.mimeType, a.j.hlsSegmentFormat, a.j.hlsVideoSegmentFormat, a.B)` (E16). The Shaka branch never reads them
  (grep of the whole file). TS or fMP4 makes no difference to the choice.
- Official timeline (`shaka_migration`): phase 2 "changed the default player to Shaka Player", start date May 18 '26.
  The same page says of MPL: "new HLS features won't be added to the player".
- Third path, VERIFIED in code only: any other content type (for instance `video/mp4` on a URL that does not end in
  `.m3u8/.mpd/.ism`) is played by `Co`, which does `a.src = c.j.url; a.autoplay = b` and nothing else. See section 12.

How a sender can tell which player is running (INFERRED from the code read, cheap to check on the device):

| Sign | Shaka path | MPL path |
|---|---|---|
| Playlist reloads seen by the phone | every last-`EXTINF` (0.5 s) (S1b, S1c; EMULATED: median 499–500 ms) | every `TARGETDURATION` (1 s) (M3b) |
| Requests right after the first playlist | one init + one probe segment at once, then the three newest segments (EMULATED log) | starts from the oldest advertised segment (seek to `end − 3 s`) |
| `liveSeekableRange` in MEDIA_STATUS | present, `end − start` = playlist span − delay | absent for a 3 s playlist (`start == end` is reported as none, E9c) and SEEK is removed from `supportedMediaCommands` (E9d) |
| `playbackRate` in MEDIA_STATUS during a stall | 0 (section 10) | stays 1 (MPL pauses the element instead) |

## 5. Question 3: the Shaka configuration actually applied

VERIFIED (framework E6, then run in `tools/dump_config.js` under a `CrKey` user agent):

```js
e = {
  abr: { defaultBandwidthEstimate: b.initialBandwidth || 2e6 },
  drm: { retryParameters: co, servers: eo(b) },
  manifest: { retryParameters: co },
  streaming: { rebufferingGoal: b.autoResumeDuration || 10, retryParameters: e, stallThreshold: 5 },
};                                                             // co = { maxAttempts: 4, baseDelay: 400, backoffFactor: 2, timeout: 3e4 }
ho(a, "4.0.0") && (e.streaming.jumpLargeGaps = !0);            // ho(a, v) means "loaded Shaka is OLDER than v": not applied to 4.15.56
…
e.mediaSource.codecSwitchingStrategy = shaka.config.CodecSwitchingStrategy.RELOAD;      // unless flag use_change_type_for_codec_switching
Ed(f, "dispatch_all_emsg_boxes", !0) && (ho(a, "5.0.0") ? (e.streaming.dispatchAllEmsgBoxes = !0) : …);
if ((f = hg(a.j.mimeType) === 2)) (f = !Ed(f, "should_deprecate_special_mpeg2_ts_handling", !0) || ho(a, "3.1.0"));
f && (e.manifest.availabilityWindowOverride = 50);             // HLS only, and only for Shaka < 3.1.0 or when the flag is false: not applied
!ho(a, "4.15.0") && ho(a, "5.0.0") && (e.abr.removeLatencyFromFirstPacketTime = !1);
io(e);                                                         // flag per_device_type_shaka_config_defaults: extra "a.b.c = value" pairs per brand/os/model
if (b.shakaConfig) { … jo(a, e, b.shakaConfig); }              // PlaybackConfig.shakaConfig: receiver app only, absent here
a.h.configure(e);
```

`b` is the `PlaybackConfig`; the default receiver has none, so `autoResumeDuration` and `initialBandwidth` are undefined.

Resulting configuration, as printed by Shaka 4.15.56 itself (values that matter here; full dump in `out/`):

| Key | Value | Origin |
|---|---|---|
| `streaming.rebufferingGoal` | **10** | framework (Shaka default 0) |
| `streaming.stallThreshold` | **5** | framework (Shaka default 1) |
| `streaming.stallSkip` | 0 | Shaka's Chromecast device class (S4b; default elsewhere 0.1) |
| `streaming.bufferingGoal` | 10 | Shaka default |
| `streaming.bufferBehind` | 30 | Shaka default |
| `streaming.lowLatencyMode` | **false** | Shaka default; no `autoLowLatencyMode` key exists in this build (it is only a deprecated alias) |
| `streaming.liveSync.enabled` | **false** (targetLatency 0.5, maxPlaybackRate 1.1 unused) | Shaka default |
| `streaming.segmentPrefetchLimit` | 1 | Shaka default |
| `streaming.updateIntervalSeconds` | 1 | Shaka default; the wait for a new segment is `min(last segment duration / 2, this)` = 0.25 s here (S6) |
| `streaming.gapDetectionThreshold` / `gapPadding` / `gapJumpTimerTime` | 0.5 / 0 / 0.25 | Shaka default |
| `streaming.safeSeekOffset` / `safeSeekEndOffset` | 5 / 0 | Shaka default |
| `streaming.inaccurateManifestTolerance` | 2 | Shaka default |
| `streaming.returnToEndOfLiveWindowWhenOutside` | false | Shaka default |
| `streaming.retryParameters`, `manifest.retryParameters` | maxAttempts 4, baseDelay 400, backoffFactor 2, fuzzFactor 0.5, timeout 30000, stallTimeout 5000, connectionTimeout 10000 | framework over Shaka default |
| `manifest.defaultPresentationDelay` | **0** (so the HLS rule applies) | Shaka default |
| `manifest.hls.liveSegmentsDelay` | **3** | Shaka default |
| `manifest.hls.sequenceMode` | true | Shaka default for the device |
| `manifest.hls.ignoreManifestProgramDateTime` | false | Shaka default |
| `manifest.availabilityWindowOverride` | NaN | Shaka default |
| `abr.defaultBandwidthEstimate` | 2000000 | framework |
| `mediaSource.codecSwitchingStrategy` | reload | framework |

What these mean for a live HLS load, VERIFIED by reading Shaka 4.15.56 (S1…S6):

- **Presentation delay** (`changePresentationTimelineToLive_`, S1b): `manifest.defaultPresentationDelay` if set, else
  `PART-HOLD-BACK` (low-latency mode only), else **`EXT-X-SERVER-CONTROL:HOLD-BACK` as given, with no minimum**, else
  the sum of the `EXTINF` of the last `liveSegmentsDelay` (3) segments. For our playlist: 1.5 s (3 s before 14 November).
  Then `this.startTime_ && this.startTime_ < 0 && ((b = Math.min(-this.startTime_, b)), (this.startTime_ += b))`, where
  `startTime_` comes only from `EXT-X-START:TIME-OFFSET` (S1): a negative offset smaller than the delay **replaces** the delay.
- **Live edge**: `getLiveEdge_() = now − maxSegmentDuration − presentationStartTime`; the HLS parser sets the start time
  once, from the newest segment of the **first** playlist it parses, and then calls `lockStartTime()` (S2, S2c).
  From then on the live edge is `end of that segment + wall-clock time elapsed on the Chromecast`. Later playlists do not move it.
- **Start position** when the load carries no start time: `getSeekRangeEnd()` = live edge − delay (S5).
- **Playlist reload period**: `lastTargetDuration_ = min(last EXTINF, previous)`, not `EXT-X-TARGETDURATION` (S1b, S1c):
  0.5 s for us. EMULATED: median gap 499–500 ms.
- **Low-latency HLS** (parts, blocking reload, preload hints): needs `streaming.lowLatencyMode`, which is false and
  which no sender message can set. Publishing LL-HLS tags would change nothing on the default receiver. INFERRED from the
  config and from `this.lowLatencyMode_ && this.partialTargetDuration_` in S1b.
- **Buffering state** (S3): `bufferObserver_.setThresholds(rebufferingGoal, Math.min(0.5, rebufferingGoal / 2))`, so with
  the framework's value the player enters "starving" below **0.5 s** of buffer and leaves it only with **10 s** of
  buffer or when `isBufferedToEnd()` is true, which for live is `bufferEnd >= getSegmentAvailabilityEnd()`, the
  wall-clock live edge above. While starving, `playRateController_.setBuffering(true)` sets the element's
  `playbackRate` to 0. The initial state is starving (`setState(STARVING)` in `startBufferManagement_`).
  A stream that plays 1.5 s behind the edge can never hold 10 s, so only `isBufferedToEnd()` can release it. Section 9 shows what that does.
- **Stall detector**: after 5 s without progress while more than 0.5 s is buffered ahead, `video.play()` then
  `pause()`/`play()` (no skip, `stallSkip` 0), at most three attempts 5 s apart.
- **Falling behind**: every 0.25 s, if the element is not paused and the position is more than
  `max(seek range width, 3 s)` behind the seek-range end, Shaka itself jumps forward (`minSeekRange_ = 3`, S5b).

## 6. Question 4: what the sender's LOAD can change

VERIFIED by following every field of the request through `Em`/`Dm` (MediaManager), `Br`/`oq` (PlayerManager) and the Shaka wrapper.

| Field | What the default receiver does with it |
|---|---|
| `media.contentUrl`, `media.contentId` | `c.contentUrl || c.contentId` is the URL (E10). Equivalent. |
| `media.contentType` | Chooses the player (section 4). |
| `media.hlsSegmentFormat`, `hlsVideoSegmentFormat` | MPL only (E16). Keep them for a device that is opted out. |
| `media.streamType` | Not used to decide anything about playback. Live is detected from the manifest (`h.isLive()`). It is only corrected when missing, shown in the UI and counted in metrics. |
| `media.duration` | Overwritten (−1 for live). |
| `media.customData`, request `customData` | Stored and echoed in MEDIA_STATUS. No code path reads a key (grep of every use). |
| `media.startAbsoluteTime` | Cleared or recomputed after load (E9d); never used by the player. |
| `media.metadata.sectionStartAbsoluteTime` | Only switches on the reporting of `media.startAbsoluteTime` (section 7). |
| `currentTime` (iOS `startTime`) | Becomes `startTime` of the load: `c.h.load(c.j.url, c.j.startTime, c.j.mimeType)` (E7b). See below. |
| `playbackRate` | Must be 0.5 to 2 or the LOAD is refused (`zm`, E11b); applied to the element after load. |
| `autoplay` | Sets `video.autoplay`. |
| `activeTrackIds`, tracks, text style, queue data, credentials | Irrelevant to timing. |

`currentTime` on a live Shaka load (E7c, E7d):

```js
a.isLiveStream() && ((c = -1), a.j.startTime !== void 0 && (a.jc = !0));          // after load
…
_.h.kl = function () {                                                           // media element "play" event
  var a = this.h.seekRange();
  this.B === null && (this.B = a.start);
  if (this.jc) {
    var b = this.j.startTime + this.B;
    b < a.start ? (…"Start time is out of seek range, jump to the seek start point."…, (b = a.start))
                : b > a.end && (…"Start time is out of seek range, jump to live."…, (b = a.end));
    this.mediaElement.currentTime = b; this.jc = !1;
  }
};
```

- absent (what `GCKMediaLoadRequestDataBuilder` sends by default; its header documents "if playing live streams, it
  starts from live edge"): Shaka starts at live edge − delay. This is the best case.
- `0`: starts at the **start** of the seek range, the oldest point (up to playlist span − delay later).
- negative: clamped to the start of the seek range as well. (Shaka alone would read it as "from the live edge", the wrapper overrides that.)
- very large: jumps to the seek-range end, the same place as "absent" with one extra seek.

So there is **no sender-side lever on buffering or on live delay in the LOAD message** for the default receiver.
RewindBox already sends the best LOAD. The levers that exist are outside the LOAD:

1. the playlist: `HOLD-BACK`, `EXT-X-START`, which segments the first response lists and when it is sent, segment length;
2. media commands: SEEK and SET_PLAYBACK_RATE (section 8);
3. the content type, which selects a different player (section 12);
4. a receiver application of one's own, where `playbackConfig.shakaConfig` or `autoResumeDuration` is available (section 12).

EMULATED check that Shaka honours the two tags (Shaka defaults, phase 0.25 s, 120 ms per segment transfer):
`HOLD-BACK=1.0` gave delay 1.0 and latency 1.62 s with 0 rebuffer in 15 s; `HOLD-BACK=0.5` gave delay 0.5, latency 1.1–1.6 s
with 1 rebuffer and the buffer down to 0.02 s; `EXT-X-START:TIME-OFFSET=-1.0` and `-0.5` gave the same delays (1.0 and 0.5) and the same
picture (0 and 2 rebuffers). (Latency here means wall-clock time minus the capture time of the picture, in the simulation, with a
segment listed only when complete.)

## 7. Question 5: how MEDIA_STATUS is built for a live stream

VERIFIED (E7, E8b, E9, E9b, E9d).

- Base status (`tm`): `mediaSessionId`, `playbackRate` (the manager's copy of the element's rate), `playerState`,
  `currentTime`, `supportedMediaCommands`, `volume`, `videoInfo`, `media` when asked. Then `Player.fh` overwrites
  `currentTime` and adds `liveSeekableRange`.
- Shaka wrapper:

```js
_.h.getLiveSeekableRange = function () { …
  var a = this.Ya();                                   // this.h.seekRange(), null when {0,0}
  this.B === null && (this.B = a.start);               // B: seek-range start the first time it is seen
  var b = this.Dc(), c = this.isLiveDone();
  return new _.Ti(a.start - this.B, a.end - this.B, b, c);     // start, end, isMovingWindow = !isInProgress(), isLiveDone
};
_.h.getCurrentTimeSec = function () { var a = …mediaElement.currentTime; if (this.A != 6 && this.isLiveStream() && a) { if (this.B === null) return 0; a -= this.B; } return a; };
_.h.getStartAbsoluteTime = function () { …
  var a = Date.now() / 1e3 - liveSeekableRange.end,   // base class
      b = raw currentTime - relative currentTime;      // = B
  return a && b && Math.abs(a - b) < 1800 ? b : a;
};
```

- `liveSeekableRange.end` therefore equals `E0 + (receiver time since first parse) − delay − B`, where `E0` is the end
  of the newest segment in the first playlist the receiver parsed. It advances with the Chromecast's clock whether or
  not new segments arrive. `end − currentTime` is "how far the position is behind Shaka's nominal start point"; it is
  about 0.1–0.2 s after a clean start (EMULATED) and grows by the length of every freeze.
- A range with `start === end` is reported as no range and removes SEEK from `supportedMediaCommands` (E9c, E9d).
- `media.startAbsoluteTime` (`Gl`, E9d): for a live stream it is set to `undefined` unless
  `media.metadata.sectionStartAbsoluteTime` is present. With it (and no `sectionStartTimeInMedia`) the receiver writes
  `media.startAbsoluteTime = player.getStartAbsoluteTime()` and `metadata.sectionStartTimeInMedia`. The value is a
  snapshot of `receiver clock − liveSeekableRange.end`: it restates the same lag on the receiver's clock and adds nothing.
- **Program date time**: the framework contains no call to Shaka's `getPlayheadTimeAsDate` or
  `getPresentationStartTimeAsDate` (grep: no `AsDate`). In Shaka the tag only sets `initialProgramDateTime` and
  aligns streams against the lowest date, so times still start near 0 (`syncStreamsWithProgramDateTime_`), and the
  1800 s test above can never match. EMULATED: a playlist with PDT behaved exactly like one without.
  **A sender cannot get the wall-clock time of the displayed picture from MEDIA_STATUS.**
- Statuses are event-driven, not periodic: state change, rate change, buffering change, seek, and `TIME_DRIFTED`, which
  the 500 ms watchdog raises when the position is more than 500 ms away from `rate × elapsed` (E8c). The iOS
  `approximateStreamPosition` / `approximateLiveSeekableRangeEnd` extrapolate between them, so the lag the sender
  computes has a resolution of roughly half a second.

What the sender can compute instead (INFERRED, all inputs are on the phone): Shaka's time zero is the start of the first
segment of the first playlist response of that load, and its live edge is anchored when that response is parsed. The phone
knows which segments that response listed, when it sent it, and when the newest of them was published (call that age φ).
Then: delay of the displayed picture behind the newest published picture ≈ presentation delay (1.5 s, or `HOLD-BACK`)
+ φ + the time the receiver needed to finish its first parse (before anchoring it downloads the init segment and one
whole media segment to detect codecs) + (`liveSeekableRange.end − currentTime`). Capture, encoding, the wait for the
segment to be complete, decoding and display come on top. In the simulation the identity matched the measurement
(control runs: 1.5 + 0.05 + 0.14 + 0.19 = 1.88 s, measured 1.88 s; 1.5 + 0.45 + 0.14 + 0.18 = 2.27 s, measured 2.27 s;
0.14 s is the first-parse time with the 120 ms segment transfer of the simulation).

## 8. Question 6: media commands on a live stream

VERIFIED (E10b–E10e, E11, E8).

- **SEEK**. The manager requires `currentTime` or `relativeTime` (`Gs`). The player manager computes
  `d = c.relativeTime !== void 0 ? this.getCurrentTimeSec() + c.relativeTime : Number(c.currentTime)` and calls
  `seek(d, c.resumeState)`. Negative values become 0; a seek while another is running is rejected with INVALID_REQUEST.
  Then, in the base player:

```js
if (c.isLiveStream()) { d = c.getLiveSeekableRange(); if (!d) return …reject("INVALID_REQUEST");
  a < d.start ? (…, (a = d.start)) : a > d.end && (…"Seek time is not available yet, jump to live edge."…, (a = d.end)); }
if (Math.abs(c.getCurrentTimeSec() - a) < 1) return (_.E(gl, "ignore seek which tries to jump to too close time"), f.Z(2));
e = c.Wd(a);                                                    // mediaElement.currentTime = a + B
```

  The iOS `seekToInfinite` sends a large constant (`kSeekInfinityValue` in `GCKMediaControlChannel.m`; the string
  "Seek to infinite because seeked position (%f) is close to seekable range end (%f)." is in the binary; the numeric
  value was not extracted). Whatever it is, the receiver lands on `liveSeekableRange.end`, that is live edge − delay,
  and **does nothing when the position is already within 1 s of it**. `resumeState: PLAYBACK_START` calls `play()` if paused.
- **SET_PLAYBACK_RATE**. `if (typeof c !== "number" || c < 0.5 || c > 2) return (…"Bad value for playback rate"…, INVALID_REQUEST/INVALID_PARAMS)`.
  Otherwise `mediaElement.playbackRate = rate`. Shaka adopts a rate set from outside
  (`onRateChange_` -> `playRateController_.set(a)`, S7) and re-applies it after buffering. EMULATED: setting the element
  to 1.5 for 1.8 s brought the latency down by 0.3–0.6 s without a stall in 7 of 8 runs; the eighth stalled once
  (0.6 s) and gained nothing.
- **PLAY** after a pause: if the position is before the range start, seek to the start; if SEEK is not in the supported
  mask or there is no range, `seek(Infinity)` ("Jump to live head").
- **PAUSE**, **STOP**, volume: as usual. The supported-command mask is not enforced.
- While Shaka is in its buffering state it forces the rate back to 0 (`calculateCurrentRate_ = isBuffering_ ? 0 : rate_`),
  so neither a seek nor a rate command releases a frozen stream. EMULATED: a seek to the range end and a rate of 1.5 on a
  frozen stream left it frozen.

## 9. The buffering trap (EMULATED; the most important result)

Why (INFERRED from S2, S3, then reproduced): after the first parse the live edge moves with the clock. A new segment
ending at `E0 + n × 0.5` is published `φ` earlier than the live edge reaches it (φ = age of the newest segment when the
first playlist was answered, between 0 and one segment). The receiver then needs a playlist reload, up to 0.25 s of
Shaka's own polling, and the transfer. Its buffer reaches the live edge only if all of that takes less than φ plus the
time the first parse took (first playlist, init segment and one probe segment). Playlist reloads run at the same 0.5 s period as publication, so the phase
stays where it started. With the default-receiver configuration that is the only way out of "starving".

Runs (`out/res_A.json`; DMR configuration = the object of section 5; "phase" = φ; per-segment transfer delay added by the server):

| Stream | Configuration | Runs | Never played in 20 s | Played |
|---|---|---|---|---|
| 0.5 s segments, 6 in playlist | default receiver | 10 (φ 0.05…0.45 s × 20 and 120 ms) | **9** | 1 (φ 0.45, 120 ms): start after 1.15 s, latency 3.0 s |
| 1 s segments, 6 in playlist (shape before 14 November) | default receiver | 5 (φ 0.1…0.9 s, 120 ms) | **4** | 1 (φ 0.9): start after 2.35 s, latency 5.7 s |
| 0.5 s segments | Shaka defaults (`rebufferingGoal` 0) | 2 controls here, 1 earlier | 0 | start 0.45–0.55 s, latency 1.88–2.27 s, 0 rebuffer |
| 0.5 s segments, random 0–150 ms transfer jitter, 30 s | default receiver | 2 | 1 | 1: latency 3.3 s |

In a frozen run the element is not paused, `playbackRate` is 0, `player.isBuffering()` is true, the buffer holds 3–4 s,
and the position jumps forward about every 3 s when it leaves the window (4–10 jumps counted per run): a slide show.

A playlist-side way out, tested in the same simulation (`out/res_B.json`, `res_C.json`): answer the **first** playlist
request of a load without the newest *k* segments, and list everything from the second answer on. Shaka's live edge is
then anchored *k* segments behind what is really available, `isBufferedToEnd()` is true most of the time, and the
buffering state stays satisfied. `HOLD-BACK` can give the *k* segments back.

| First answer omits | `HOLD-BACK` | Runs (φ 0.05 / 0.25 / 0.45) | Frozen | Rebuffer events in 24 s | Start | Latency |
|---|---|---|---|---|---|---|
| 1 segment | none (1.5 s) | 3 | 0 | 0 | 1.1–1.5 s | 3.1–3.6 s |
| 2 | none | 3 | 0 | 0 | 1.4–1.55 s | 3.7–4.1 s |
| 3 | none | 3 | 0 | 0 | 1.2–1.5 s | 4.1–4.8 s |
| 1 | 1.0 | 3 | 0 | 0 | 1.1–1.45 s | 2.6–2.9 s |
| 2 | 1.0 | 3 | 0 | 0 | 1.2–1.3 s | 3.0–3.4 s |
| 2 | 0.5 | 3 | 0 | 0 | 1.25–1.55 s | 2.6–3.0 s |
| 3 | 0.5 | 3 | 0 | 0 | 1.25–1.5 s | 3.2–3.6 s |
| 1 | 0.5, then rate 1.5 for 1.8 s | 2 (80 ms jitter) | 0 | 1 in one run | 1.45–1.8 s | 2.2–2.5 s at the end |
| 1 | 1.0, then rate 1.5 for 1.8 s | 2 (80 ms jitter) | 0 | 0 | 1.45–1.6 s | 2.3–2.8 s at the end |

All 21 anchored runs of the first seven rows played without a freeze. Part of the latency (0.8–1.0 s) is the initial
freeze before the first "buffered to end", which leaves the position that far behind the range end; it is under the 1 s
that a SEEK needs, so only a playback rate above 1 can take it back.

Limits of this evidence: desktop Chromium, loopback network, synthetic 640×360 video, the framework's configuration
re-created by hand rather than the receiver page, 20–30 s per run, a handful of runs per cell. It contradicts the
owner's report that the stream does play, so one of these holds on the owner's Chromecast: the device is on MPL, or it
receives per-device Shaka overrides, or real timing lets the buffer touch the live edge often enough, or the stream
the owner saw was in the frozen-and-jumping mode. Only the phone's own logs can tell (section 13).

## 10. Question 8: stalls, buffering, and the states the sender sees

VERIFIED by reading; the sequence of statuses is INFERRED and was not observed.

- Player state mapping (`zl`, `fd`): loading -> BUFFERING; then `R && isPaused() ? "PAUSED" : isBuffering() ? "BUFFERING" : "PLAYING"`; ended or failed -> IDLE.
- Two writers of "is buffering":
  1. Shaka's `buffering` event: `a.Rb(a.h.isBuffering())` (E13).
  2. the framework's 500 ms watchdog (E8c): `a.Rb(Math.abs(c) < 100 * a.fb)`, where `c` is the progress in ms over
     the last 500 ms and `fb` the last rate seen on `ratechange`.
- When Shaka starves it sets the rate to 0. The element fires `ratechange`, the framework stores `fb = 0`, and the next
  watchdog tick computes `|c| < 0`, false. Expected sequence for the sender: `BUFFERING` for at most about 0.5 s, then
  **`PLAYING` with `playbackRate: 0`** for the rest of the freeze (the rate is broadcast by `Rr`, E14b), then
  `playbackRate: 1`. The same applies to the frozen start of section 9: the sender would be told PLAYING.
  For RewindBox this means `playerState == .playing` does not prove the picture moves; `playbackRate == 0`, or a
  stream position that does not advance, does.
- A decoder stall with data buffered: Shaka's detector after 5 s (section 5). The watchdog reports BUFFERING after 0.5 s.
- Network errors: playlist reload failures are RECOVERABLE in Shaka (`raiseFatalErrorOnManifestUpdateRequestFailure`
  false, retry after 0.1 s); requests retry 4 times from 400 ms with factor 2.
- Error path (E12, E12b): `Yk(…)` dispatches an ERROR event and, when the severity is not 1 (RECOVERABLE), ends the
  player with "ERROR". The player manager sends an `ERROR` media message to all senders for every error event, and for
  non-recoverable ones `Bm(a, "ERROR", !0)`: MEDIA_STATUS `IDLE` with `idleReason: ERROR`. A failed load answers the
  requester with `LOAD_FAILED`. The flag `tear_down_on_recoverable_error` (default false) would make recoverable errors fatal.
- Nothing in the receiver reloads the stream by itself. A stream whose segment timeline falls behind the wall clock
  (publication paused for longer than the delay) leaves the position ahead of all content: starving with no exit,
  no error, no IDLE (INFERRED from S2 and S3).

## 11. Question 7: MPL, for a device that is opted out

VERIFIED by reading `media_player.js` (M1–M3) and the wrapper (E16, E16b).

- Host defaults: `initialBandwidth = 3145728; autoResumeDuration = 10; autoResumeNumberOfSegments = 3; autoPauseDuration = 1`.
  The default receiver overrides none of them.
- Buffer logic, every tick: pause when a non-text stream has less than `autoPauseDuration` (1 s) buffered; resume when
  every stream has `segment duration × autoResumeNumberOfSegments`, capped at `autoResumeDuration` (for 0.5 s
  segments: 1.5 s); stop requesting above 20 s.
- Live seekable range: `a = last.Qa + last.duration; this.l.X && ((a -= 3 * this.l.eh), a < b && (a = b)); return { start: b, end: a }`
  with `eh = parseInt(EXT-X-TARGETDURATION)`. For our playlist the end is 3 s before the newest segment, which is the
  start of a 3 s playlist: `start == end`.
- Start: the wrapper, on `loadedmetadata`, `if (this.isLiveStream() && this.j.startTime === void 0) { var c = this.Ya(); c && c.end && (b = this.seek(c.end)); }`.
  So MPL plays about **3 s (3 × TARGETDURATION) behind the newest listed segment**, from the oldest segment of our
  playlist. A negative start time is honoured as an offset from that end.
- Playlist reload: `c = this.F.eh * 1e3; this.la = setTimeout(this.In, c)`: once per `TARGETDURATION` (1 s) after each
  parse. Three reloads in a row with the same first and last segment set `Qe`, "live done", and reloading stops.
- fMP4: `cast.player.api.CreateHlsStreamingProtocol(host, Jo(hlsSegmentFormat), videoFormat)` with
  `HlsSegmentFormat.FMP4` and `HlsVideoSegmentFormat.FMP4`; this is where the two LOAD fields are used.
- MPL does not read `EXT-X-SERVER-CONTROL` or `EXT-X-START` (not in its tag list). It parses PDT for date ranges only.
- Consequences for RewindBox on such a device (INFERRED): about 3 s + reload phase behind the newest segment, no
  `liveSeekableRange` in the status (so `NPGoogleCast.checkLive` silently does nothing), and the stream ends for the
  player if no new segment appears for about 3 s.

## 12. Two paths that avoid the trap altogether (options, not measured)

- **Plain media element.** For a content type that is neither HLS, DASH nor Smooth, and a URL without such an
  extension, the default receiver runs `a.src = c.j.url; a.autoplay = b` (class `Co`). No Shaka, no MPL, no buffering
  goals in JavaScript; SET_PLAYBACK_RATE still works, `liveSeekableRange` is absent. An endless fragmented MP4 sent as
  one long HTTP response is the kind of stream this path would play. VERIFIED: the code path. UNKNOWN: Chromium's own
  start-up buffering and behaviour on a Chromecast for such a stream, so no latency figure is offered.
- **A receiver application of one's own** (an HTML page behind an application id; the Chromecast itself is untouched).
  There `CastReceiverOptions.playbackConfig` exists: `autoResumeDuration` maps straight to `rebufferingGoal`, and
  `shakaConfig` is merged last ("overriding … Shaka configuration with custom value"), which opens `lowLatencyMode`,
  `liveSync`, `manifest.defaultPresentationDelay`. VERIFIED: E6 and the `PlaybackConfig` reference ("This object is merged
  with CAF's default Shaka configurations"). EMULATED: with `rebufferingGoal` 0 the same stream started in 0.5 s and held 1.9–2.3 s.

## 13. What this means for RewindBox

In `packages/neoplay_bridge/ios/Classes`:

- `NPGoogleCast.load`: the LOAD is already the best possible. Keep `startTime` unset. `hlsSegmentFormat`/
  `hlsVideoSegmentFormat = .FMP4` matter only for MPL; keep them. `streamType = .live` is harmless and useless.
- `NPGoogleCast.remoteMediaClient(_:didUpdate:)` treats `.playing` as "the picture is on the TV". On the Shaka path
  that state is expected during a freeze, with `playbackRate` 0.
- `NPLiveLagTracker`: (a) it learns the smallest lag as reference, so a start that is already 0.9–3 s behind becomes
  the norm; (b) the receiver ignores a seek of less than 1 s, so the 1 s `excess` is the floor of what a seek can
  recover; (c) Shaka already jumps by itself beyond 3 s; (d) a seek cannot release the buffering state.
- `NPSegmentStore.response("index.m3u8")` is where the delay and the anchor are decided: tags and the first answer.
- `NPHTTPServer` sees everything needed to identify the player and the device and logs none of it.
- `NPController` sends the LOAD once (`didLoadCast`); nothing reloads a stream that stays frozen.

Recommended order (each step is a measurement or a small reversible change; none is a measured gain on a Chromecast):

1. **Log on the phone** per load: time and User-Agent of each request, the playlist sequence range of each answer,
   the age of the newest segment at the first answer; from MEDIA_STATUS: `playerState`, `playbackRate`,
   `liveSeekableRange` (or its absence), `supportedMediaCommands`, stream position. One session then tells Shaka from
   MPL (table in section 4), the Chromecast model and Chrome version (User-Agent), the frozen time
   (`playbackRate == 0`), and the delay by the formula of section 7.
2. If the device is on Shaka and freezes are seen: try the anchored first answer (omit the newest 1 segment, then 2)
   together with `#EXT-X-SERVER-CONTROL:HOLD-BACK=1.0`, and compare frozen time and computed delay against today's playlist.
3. Replace the learned reference of the lag tracker by an absolute rule, and use `setPlaybackRate` (for instance 1.25
   until `end − position` is under 0.3 s, then 1.0) for lags under 1 s; keep the seek for more than 1 s.
4. Treat `playbackRate == 0` or a position that has not advanced for about 3 s as a failed stream and LOAD again
   (a new load re-anchors the live edge).
5. Decide between a shorter segment, the plain media element path and a receiver application only after step 1 has
   shown what the owner's device actually runs.

## 14. Open points

- Flag values on real devices: `use_shaka_for_hls`, `forced_opt_out_of_shaka_for_hls` (does it contain `CC1AD845`
  anywhere?), `default_shaka_version`, `experiment_shaka_version`, `per_device_type_shaka_config_defaults` (could carry a
  different `streaming.rebufferingGoal` for some models).
- Whether the frozen start of section 9 happens on a Chromecast with the real receiver page. A parallel lab in this
  study runs the real page (`lab/cafemu`); its result should replace section 9 where they differ.
- The status sequence of section 10 (PLAYING with rate 0) was derived, not seen.
- The numeric value of the iOS `kSeekInfinityValue`.
- `CastReceiverOptions.useShakaForHls` reference text still says "Defaults to false"; the framework code and the
  release notes say true. The code was taken as authoritative.

## 15. Files

All under `<scratch>/research/caf-internals/`:

- `report.md` (this file), `evidence/extracts.md` (code extracts with line numbers)
- `src/crf.pretty.js`, `src/shaka-4.15.56.debug.pretty.js`, `src/mpl.pretty.js` (pretty-printed copies)
- `dl/` (files as fetched: framework, Shaka compiled and debug, MPL, `dmr/app.html`, `dmr/app_CC1AD845.raw`, `dmr/baseconfig.raw`)
- `tools/dump_config.js`, `out/config_dump_crkey_linux.json`
- `tools/livesim.js`, `tools/show.py`, `out/set_*.json` (run plans), `out/res_*.json` and `out/res_*.log` (results)
- `media/s05`, `media/s10` (synthetic test streams made with ffmpeg)

To repeat a batch: `node tools/livesim.js out/set_A.json out/res_A2.json 6` from the `tools` directory.
