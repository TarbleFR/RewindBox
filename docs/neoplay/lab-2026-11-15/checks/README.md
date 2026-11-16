# Checks of 15–16 November 2026 (Linux, Swift 6.0.3, Swift 5 mode)

Each `*_check.swift` is compiled together with the files of `packages/neoplay_bridge/ios/Classes` it names at its
top (`swiftc -swift-version 5 -O <classes> <check>.swift`). The media inputs are ffmpeg test patterns (see the
headers). `apple_and_cast_standins.swift` holds the stand-ins (written from the GoogleCast 4.8.6 headers and Apple's
documentation) used to type-check the files that import Apple frameworks: strip their `import` lines, replace the
unchanged UI parts of `NPController.swift` (overlay window, volume view) by empty stand-ins, and run
`swiftc -typecheck` on everything. Only `NPHTTPServer.wifiAddress` (unchanged, Darwin's `sockaddr.sa_len`) does not
type-check on Linux. None of this is a compilation for iOS or a device test.

| File | What it checks |
|---|---|
| `fragmented_mp4_check.swift` | init segment + one fragment per picture from real H.264/AAC; ffprobe reads 300 pictures and 235 AAC packets |
| `fragmented_mp4_edges_check.swift` | 405 KB pictures, audio-only fragments, several AAC packets, time stamps beyond 2^32 ticks |
| `direct_stream_check.swift` | `NPDirectStream` in seven scenarios (normal, silence, sound absent at start, queue overflow, stall, new picture size, pictures stopping) |
| `audio_timeline_check.swift` | `NPAudioTimeline` with sound arriving 0–300 ms later than the pictures, after a silence, at start |
| `lag_controller_check.swift` | `NPLagController` against five simulated receivers, `NPBitrateLadder` |
| `still_screen_stream.swift` | a still screen at 30 repeats a second through `NPDirectStream`, replayed on the receiver emulator |
| `progressive_plain_page.js` | the plain media element in Chromium, autoplay versus an explicit play |
