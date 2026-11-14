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
