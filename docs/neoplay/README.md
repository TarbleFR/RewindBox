# NeoPlay — first integration candidate

> Historical prototype record. The branch and validation status below describe
> this candidate, not a current branch or build request. Use the
> [shared task board](../AI_TASK_BOARD.md) and [branch protocol](../branch-archive.md)
> before resuming work; do not recreate the former remote branch automatically.

Branch: `feature/neoplay`. Base: release 0.0.2 / `f4583c6a3083b8aed358da28b2f8f849256e0e8b`.
This is not Apple's AirPlay protocol. It is NeoStation's opt-in local streaming feature.
No changes to `experimental`, NeoSwap, JIT, emulator cores, saves or libraries are required.

## Windows

A complementary **free NeoPlay Receiver** is required. The first candidate runs with Node.js 22+ and Edge/Chrome, using their built-in H.264/AAC media pipeline, not unsigned third-party FFmpeg DLLs.
In `tools/neoplay-receiver`: `npm ci`, then `npm start`. Open the localhost address, click Ready, then tap the **AirPlay icon in NeoStation’s main menu**, select the PC in the NeoPlay panel and enter the six-digit code.
The receiver announces `_neoplay._tcp` over Bonjour/mDNS. No account, external signalling service, internet relay or router port forwarding is used. A narrowly scoped Windows **private-network** firewall permission for the receiver may be needed; do not disable security protections globally.

## Chromecast

Tap the **AirPlay icon in the main menu** to open NeoPlay, then **Find screens**, allow iOS local-network access, and select the Chromecast before launching a game. The previous NeoPlay activation entry in **Settings → Tools** has been removed; the AirPlay action opens the same panel with Apple TV guidance, Chromecast and Windows receiver selection. Opening the panel or starting a game does not automatically search for a TV or start capture. The iPhone and Chromecast must be on the same local Wi-Fi network; guest/client isolation may prevent discovery. If access was denied, enable NeoStation's **Local Network** permission in iOS Settings, return to NeoPlay, and search again. A conventional Chromecast uses the Google default media receiver and does not need the Windows receiver application.

The discovery panel now retains a **Search again** action after the initial request and retries an explicitly requested search after a Settings/foreground round trip. Native diagnostics in `NeoPlay.jsonl` record Cast discovery requests, SDK-active state and total/eligible device counts; Bonjour errors and Cast-session errors retain their actual domain and code. These records distinguish a search request, a discovered video receiver and successful playback; an empty device list alone is not labelled permission denial. Real iPhone-to-Chromecast discovery/playback remains unvalidated.

Google's [iOS permissions and discovery guide](https://developers.google.com/cast/docs/ios_sender/permissions_and_discovery) requires an explicit `startDiscovery` call for a custom picker, the `_googlecast._tcp` and receiver-ID Bonjour declarations, and local-network permission. These requirements were already present in the delivered Build399 IPA. Google's [local-network help](https://support.google.com/chromecast/answer/10063094) describes enabling an application's permission under **iOS Settings → Privacy & Security → Local Network**; its [discovery troubleshooting guide](https://developers.google.com/cast/docs/discovery) covers same-network and client-isolation checks. The supplied RPCS3/NeoSwap logs do not contain the separate `NeoPlay.jsonl` discovery record, so they cannot establish which network or permission condition caused the user's empty list.

The separately integrated Google Cast iOS SDK discovers video-capable Cast receivers and starts Google's default media receiver. No Windows PC and no extra app on a conventional Chromecast are required. The iPhone serves a token-scoped H.264/AAC fragmented-MP4 HLS stream from a bounded RAM ring with a fixed HLS target duration and separately retained recent payloads.
The media stays on the LAN, but Google's receiver/SDK initialization may need internet access. This is not a promise of fully offline Google Cast.
The default receiver does not expose the attached television's EDID or pixel dimensions to the sender. The compatibility profile is capped at 720p/60; the receiver scales to the destination with aspect preservation. Exact TV-resolution feedback and adaptive bitrate are **not implemented in this first candidate**.
The HLS path has a higher buffering delay than the Windows path. No claim of competitive-gaming latency is made. A future native Google TV receiver can use a lower-latency transport; that is not the same as a classic Chromecast.

## Capture and performance boundaries

ReplayKit captures the NeoStation application screen (including its menus), and app audio, **never microphone audio**. The user explicitly opens discovery, selects a receiver, and authorizes capture. Nothing is captured or encoded at app startup.
AVAssetWriter multiplexes H.264 and AAC using one source timestamp domain. Windows uses short fMP4 fragments over a bounded WebSocket; Chromecast uses an independently served HLS playlist. The first fragment targets are 250 ms (Windows) and 0.5 s (Cast; 1 s before 14 November 2026), not measured end-to-end latencies.
Encoding dimensions fit inside the destination and codec budget without stretching; receiver display uses `object-fit: contain`. Native orientation changes create a new initialization segment; HLS marks discontinuities. Queues and encoded media retention are bounded. Congestion stops only NeoPlay rather than growing RAM without a bound.
The visible NeoPlay × overlay disconnects without becoming the key window. Network/capture errors and late callbacks cannot call emulator stop/reset APIs. Existing AVAudioSession configuration is not changed.
Transport data in this prototype is **not encrypted**. Pairing and per-session random URL capabilities restrict accidental access, but they do not protect against an observer on an untrusted Wi-Fi. Use only a trusted private LAN.

## Validation status

The integration is **not finished** until Windows, Chromecast and Apple TV have separate physical-device evidence, and controller battery behavior is checked during actual gameplay.
- Windows: automated protocol, authentication, geometry and lifecycle tests; real iPhone game/audio playback still pending.
- Chromecast: real SDK compilation and native HLS/lifecycle contract tests; actual Chromecast playback, TV scaling and latency still pending.
- Required: 4:3/16:9/ultrawide/portrait; audio-video synchronization; connect/disconnect/reconnect during each embedded emulator; receiver disappearance; local-network denial; 30-minute thermal/pressure run; confirm game and saves remain intact.
- CI success is not physical-device success. No public release, stable-baseline promotion or merge is authorized by this implementation.

Primary API references: Apple ReplayKit `RPScreenRecorder.startCapture`, AVFoundation segmented `AVAssetWriter`; Google Cast iOS integration, supported media and iOS local-network permissions; W3C Media Source Extensions.

## First-candidate boundaries and diagnostics

The current image source is the **application screen**, not an emulator's isolated framebuffer. Consequently, letterboxing already rendered on the phone is preserved inside the shared picture. Removing that extra border without cropping the game requires an explicit game-viewport/render integration; it is not yet implemented. Do not advertise perfect game-only screen filling from these tests.

The NeoPlay panel opened from the main menu’s AirPlay icon can connect before launching a game. Apple TV screen selection remains managed by iOS Control Center. The native pass-through overlay disconnects a running stream. Opening a first receiver-selection UI from every already-running embedded emulator is a separate integration task and has not been validated.

Windows viewport changes are reported back to iOS and debounced before restarting only the encoder when its output dimensions must change. This is not an emulator restart. There is no HEVC mode or network-adaptive bitrate controller in this candidate.

`Documents/NeoPlay.jsonl` records connection/stop events, encoder dimensions and underlying error domains/codes on a utility queue. It rotates at 512 KiB to `NeoPlay.jsonl.previous`. Pairing codes, receiver addresses, URL capabilities and game paths are not logged.

For Chromecast HLS, the advertised window contains the newest segments, at least six of them and at least three seconds (three target durations), while the encoded ring retains up to 24 segments / 24 MiB, including recently unlisted payloads. Target duration stays fixed; unusually long fragments are rejected rather than silently changing the stream contract. This does not establish a real TV playback or latency result.

A private manual IPA workflow is configured only on this branch. The isolated native harness compiles the native capture/Cast implementation, but it is **not a complete NeoStation IPA build**. Device acceptance additionally requires the full host/plugin build and manual tests on iPhone plus each destination.

External emulator applications are outside the scope of this app-screen capture. Moving NeoStation to the background ends its NeoPlay stream; it does not capture another application's screen.

Before any public binary distribution, review the Google Cast SDK terms, required notices and compatibility with the project's distribution obligations. Only the SDK dependency declaration is committed here; there is no public NeoPlay binary release or completed license review.

## Recorded software verification — 2026-10-02

`validation-2026-10-02.json` binds the tested code commit, GitHub Actions run, generated media hashes and local Windows measurements. All four jobs passed: frontend, native iOS simulator, Windows protocol and Windows playback. The same production-encoder fixture was also decoded successfully in Edge on the owner's Windows PC, with nonzero audio samples, video frames, aspect containment, playback acknowledgement and disconnection checks. Local Windows mDNS publication/discovery passed separately.

These are **software and simulator results**, not an iPhone-to-TV acceptance result. The passive Chromecast probe found no receiver visible from the PC at that time. Physical iPhone/Windows Wi-Fi gameplay, actual Chromecast playback, game-only viewport integration, full IPA compilation, sustained thermal/memory testing and measured interactive latency remain open.

## Apple TV and independent controller battery HUD

See `APPLE_TV_AND_CONTROLLER_BATTERY.md` for the native iOS screen-mirroring path, explicit audio/video status distinctions, and the independent GameController battery overlay beside existing native game menus. The iOS system, not an audio route picker or a private API, selects the Apple TV.

`companion-validation-2026-10-02.json` records the dedicated companion checks and their exact source commit separately from the initial prototype report. Physical Apple TV/Chromecast playback and controller readings remain unvalidated; no full IPA or stable release is claimed.

## Chromecast delay — 14 November 2026

Report: about one second between an action on the iPhone and the TV picture through a Chromecast.
The Cast route is HLS played by Google's default receiver, which the sender cannot configure. Two parts of the delay
scale with the segment length: a segment is published only once complete (one whole segment late), and the
receiver's player starts behind the newest segment (three segments for Shaka Player, the Web Receiver's HLS player
since May 2026, when the playlist carries no HOLD-BACK; RFC 8216 6.3.3). A stall (Wi-Fi, decoder) also leaves the
player that much further behind for the rest of the session: it does not catch up by itself.

Change (`NPPolicy`, `NPMuxer`, `NPGoogleCast`):
- Cast segments and key pictures every 0.5 s instead of 1 s (`NPPolicy.castSegmentSeconds`); the target duration
  stays 1, the first load still waits for three segments (now 1.5 s instead of 3 s), the playlist keeps at least six
  segments and three seconds.
- While playing, the sender reads once a second how far the player is behind the end of the seekable range
  (`approximateLiveSeekableRangeEnd` − `approximateStreamPosition`). The smallest lag of the session is the
  reference; more than 1 s above it on two checks in a row asks for one seek to the live edge (`seekToInfinite`),
  at most once per 15 s; the reference is learnt again 3 s after (`NPLiveLagTracker`). A failed seek is not a
  session error.
- `NeoPlay.jsonl` gains `cast.live.lag` (every 10 s: `behind`, `best`, seconds) and `cast.live.resync`
  (`behind`, `count`). They measure the player's distance from its seekable end, not the end-to-end delay.

Expected, not measured: the two segment-bound parts halved, and no accumulated delay after a stall. Checked here:
`NPPolicy.swift` compiles with Swift 6.0.3 (Linux) and a local script (not committed) passed the existing native
playlist expectations, the 0.5 s window and the tracker cases; `NPGoogleCast.swift` type-checks against stand-ins
with the Swift names of the GoogleCast 4.8.6 headers. Neither is the real iOS compilation, nor a TV result. The
historical Build397/421 integration gate (`test/neoplay_build397_integration_test.py`) already did not match this
tree before the change (`NPController.swift` postimage); it is not run by the current recipe and was not updated.

Limit: this route cannot be free of delay. Encoding, segment publication and the default receiver's buffer remain.
Lower delays need another path: AirPlay to an Apple TV (system mirroring, see `APPLE_TV_AND_CONTROLLER_BATTERY.md`),
a wired HDMI adapter (expected to use the same external-screen path; not tested here), the Windows NeoPlay receiver
(per-picture frames), or a custom Cast Web Receiver fed with those frames, which needs a Cast application ID
registered by the owner in the Google Cast SDK Developer Console and an HTTPS-hosted receiver page (not done).

Delivery: private test IPA 743 (run 43570281800, IPA `8150de8b…`, base 742), verified offline and handed over on
14 November 2026; receipt `docs/evidence/rewind743/delivery.json`. The Release compilation on Xcode 26.3 with the
GoogleCast 4.8.6 SDK compiled this Swift (the first real compilation of the change); `NPLiveLagTracker` and
`cast.live.resync` are in the signed `Runner`. Images changed from the base: `Runner` (declared) and, undeclared,
the armsx2, dolphin and rpcs3 bridge frameworks, whose sources are unchanged in the effective tree (only the three
NeoPlay files differ); bridges changing without a source change also appear in 739–742. The base IPA can no longer
be decrypted here, so no section-by-section comparison was made. Not yet observed on an iPhone or a TV.

## Chromecast: direct route and repaired segments route — 15 November 2026

Owner's report: stutter and about one second between an action and the picture on a Chromecast 4K; goal: as close
to an Apple TV as an unmodified Chromecast allows. Nothing below was measured on an iPhone or a Chromecast: the
figures come from a lab on this branch's tooling (`lab-2026-11-15/`), which runs Google's real Default Media
Receiver page and Web Receiver framework 3.0.0157 (fetched 15 November 2026) in headless Chromium behind an emulated
cast shell, against an origin that imitates the sender.

### Cause (three independent reproductions)

Since mid-2026 the default receiver plays HLS with Shaka Player 4.15.56 and configures it with
`streaming.rebufferingGoal = 10` (`lab-2026-11-15/default-receiver-report.md`, sections 5 and 9). A live stream
that plays a second or two behind its edge can never hold 10 s, so Shaka leaves its buffering state only when its
buffer reaches a live edge that it anchors on the newest segment of the first playlist answer and then advances
with its own clock. With every segment listed in that first answer the buffer stays behind that edge.
Observed on the receiver page with the playlist of IPA 743: 10–14 s before the picture moves (median 12.5 s over
six runs), then 1.9–4.5 s behind; with 1 s segments (before 743) the picture never moved in two runs of three;
with `HOLD-BACK=0.5` alone, never. The same was found with Shaka alone in two other labs (0.3 to 10 pictures per
second presented). Google's older player (MPL, for receivers opted out of Shaka) refused the stream at once
because the load declared `hlsSegmentFormat = fmp4` (the audio format) for a muxed stream.

### Change

- **Direct route (default).** The per-picture H.264 encoder of the Windows route (`NPFrameEncoder`) also feeds
  `NPDirectStream`, which writes a fragmented MP4 by hand (`NPFragmentedMP4`; AAC-LC from `NPAACEncoder`): an
  initialization segment, then one `moof`+`mdat` per picture with the sound that is due. `NPHTTPServer` serves it
  as one endless chunked response (`/live.mp4`). The load declares `video/mp4`, which the receiver plays with its
  plain media element (no Shaka, no MPL). `NPGoogleCast` orders PLAY on the first status of the load (the
  element's autoplay otherwise waits three seconds, kept as delay), reads the receiver's position four times a
  second and compares it with the time stamp of the newest picture produced; `NPLagController` asks for a playback
  rate of 1.1 to 1.5 to come back to its target (0.55 s at first; raised when the receiver stalls while catching
  up, lowered slowly when it holds), or for a new load. A send queue above 0.35 s of stream skips pictures until
  a key picture and lowers the bit rate by 30 % (`NPBitrateLadder`, back up by 15 % per quiet half minute); a queue
  that does not drain for 2.5 s, or a new picture size, closes the connection and loads again. The sound track is
  kept continuous (`NPAudioTimeline`): silence fills what the capture does not deliver, but never the span by which
  the capture's sound arrives later than its pictures, which is measured all along (without that, sound arriving
  100 ms or more behind the pictures was lost for the whole session after its first silence). Every fragment that
  carries a picture is padded to 2–8 KB (by bit rate): Chromium reads a progressive response in 32 KB blocks, so
  small pictures would otherwise reach the player a block at a time.
- **Segments route (HLS; fallback, and the "Compatible" setting).** The first playlist answer of a load leaves
  out its two newest segments (`NPPolicy.castFirstAnswerHeldBack`), `hlsSegmentFormat` is no longer sent, the
  seek-to-live rule starts from an absolute reference.
- **Both.** A still screen repeats its last picture (`repeatIfStill`): on the direct route thirty times a second
  once no picture was captured for 0.1 s (a game at 20 or 30 pictures a second is not still; the receiver's element
  starts after about twenty pictures), on the segments route five times a second; the picture gate is
  13.5 ms instead of 1/61 s (which lost a 60 Hz picture stamped 0.3 ms early); the capture watchdog no longer ends
  a session while ReplayKit still records; the phone's volume is lowered while the TV plays (best effort, restored
  at the end; the Windows route already did); the route follows `NPCastMode` (automatic, direct, compatible; three
  chips in the panel), automatic falling back to segments inside the same Cast session after two failed starts and
  remembering a receiver model on which the direct route never started; the panel shows the route and the lag.

### Lab results (receiver page in Chromium, loopback, 640x360 test stream)

| Route | Start | Behind the capture | Smoothness |
|---|---|---|---|
| HLS as in IPA 743 (0.5 s segments) | 10–14 s | 1.9–4.5 s | frozen until then |
| HLS as before 743 (1 s segments) | never in 2 of 3 | 5.3 s | frozen |
| HLS, first answer without its two newest segments | 0.2–0.7 s | 2.2–2.7 s | no freeze in 90 s |
| MPL with the corrected load | 0.2 s | 2.3–2.8 s | no freeze |
| Direct, autoplay only | 3.4 s | 3.0 s | smooth |
| Direct with the PLAY order (as shipped) | 1.0 s | 0.65 s | smooth |
| Direct, after a rate of 1.25 for 0.8 s | – | 0.56 s | smooth; pushed further, one 0.3 s stall |
| Direct after a 2.5 s outage, rate 1.5 | – | 2.7 s back to 0.7–1.1 s in 5 s | one short stall at the end |
| Direct, still screen, 5 repeats a second, no padding | 7.5–17.5 s | 6.6–16.6 s | stalls |
| Direct, still screen, as shipped (30 repeats a second, padding) | 0.7 s after the first picture | 0.93–1.0 s | none |

`NPFragmentedMP4` and `NPDirectStream` were run on Linux (Swift 6.0.3) with real H.264 and AAC and their output
played by that receiver page (0.65 s, no freeze) and checked with ffprobe in seven scenarios (start on a key
picture, silence, sound absent at start, send-queue overflow, stall, new picture size, pictures stopping);
`NPLagController` in five simulated receivers (`lab-2026-11-15/checks/`).

### Review before the test IPA

Three independent reviewers read the change (compilation and platform APIs; threads, lifetimes and state machines;
stream format and control logic, the last one stopped by a usage limit after its first checks). Fixed from their
reports: the still-screen start above; the lost sound above; a receiver model remembered as failing after a
mid-session Wi-Fi drop (`everStarted`), and never forgotten (`clearDirectFailed`); `started` taken from the SDK's
extrapolated position instead of positions the receiver reported; the receiver's own lag measure believed beyond
the 3.4 s where it stops; a retain cycle on the stream; the lag controller and counters surviving a session; a
rebuilt encoder (rotation) back at the nominal bit rate; a second stop answering before ReplayKit stopped; no
start timer after a fallback; late statuses and replaced or cancelled loads of a previous media session taken as
errors; Nagle's delay on the stream socket; a key picture request stuck while pictures were skipped. All changed
Swift files type-check (Swift 6.0.3, Swift 5 mode) against stand-ins written from the GoogleCast 4.8.6 headers and
Apple's documentation; the pure files compile and run; the stream output was checked with ffprobe/ffmpeg (pictures
of 405 KB, audio-only fragments, time stamps beyond 2^32 ticks) and played on Google's receiver page. Not run: the
Flutter tests and the native XCTest suite (no SDK here; the delivery recipe does not run them either).

### Not known until a device test

Which player the owner's Chromecast uses for HLS and what its media pipeline adds (Chromium's cast pipeline starts
once up to 1 s is buffered, `chromecast/media/cma/pipeline/media_pipeline_impl.cc`, for every load type:
`cast_renderer.cc` hard-codes the media-source thresholds); the real ReplayKit cadence and capture format on an
iPhone 16 Pro Max (`video.path` and `cast.stats` now log them on the Cast routes); the delay added by decoding and
the TV. The direct route targets about half a second plus those, not an Apple TV's tenth of a second.

### Reading a session (`Documents/Diagnostics/System/NeoPlay/NeoPlay.jsonl`)

`cast.route` (route, mode, receiver model), `cast.load`, `cast.receiver.agent` (the receiver's User-Agent: model
and Chrome version), `cast.play.ordered`, `cast.direct.started` (ms after the load, lag), `cast.direct.lag` every
10 s (mean, min, max, target, rate, stalls, loads), `cast.direct.rate`, `cast.direct.bitrate`,
`cast.direct.trouble` / `reset` / `fallback`, `cast.stats` every 10 s (pictures received from ReplayKit, dropped,
sent, skipped, silence), `video.path` (capture size, pixel format, orientation), and on the segments route
`cast.live.lag` / `cast.live.resync`.

### Next step for a delay close to an Apple TV

HTTP media on the default receiver cannot go below the media element's own buffer. Two ways exist. Cast Streaming
(Google's mirroring protocol) is not offered to iOS applications and would mean launching Google's own mirroring
receiver from a third-party sender: not pursued (the session's safety layer refused the preparatory work as
unauthorized access). A receiver application of RewindBox's own (a web page the Chromecast loads; per-picture
stream, as the Windows receiver does) is the authorised way; it needs a one-time registration by the owner in the
Google Cast SDK Developer Console (5 USD) and a public HTTPS page. The owner will decide after trying the direct route.
