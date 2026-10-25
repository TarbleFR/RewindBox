# RewindBox MeloNX runtime corrections — Build 533 candidate

The maintainer requested fixes for the supplied two application journals and
two Persona 4 Golden screen recordings, followed by a private test IPA. Work
starts from Claude 41166699cd53509562dd811924ef31629c740062. No main/tag/release.

## Evidence and limits

- app(6).log contains many launches from 24 October 22:39 UTC through
  25 October 03:34 UTC, including installation changes and multiple PIDs.
  Earlier Persona failures report ErrorFeatureNotPresent in host-imported
  Vulkan buffers. PID 80243 later presents frames and closes sessions cleanly.
  Early user closes are not themselves evidence of a GPU crash.
- app (1).log also contains older startup/import history. The later Zelda
  Tears of the Kingdom sessions in PIDs 1021 and 1740 reach Metal presentation
  then report repeated syncpoint waits and ErrorDeviceLost. The underlying
  cause of device loss is not established by these journals.
- The videos show Persona 4 Golden rendering in both hosts, with different
  control/telemetry layouts. They do not establish a numerical FPS improvement.
- Build 532 engine run 40162516773 compiled its iPhone and simulator binaries
  but failed the original homebrew smoke test: stop was requested during
  startup, state remained stopping, and no GPU initialization milestone followed.
  It must not be called a validated delivery.

## Corrections

1. Window execution no longer skips GPU service when a stop arrived after
   guest creation. It seals input, starts rendering so guest shutdown can
   complete, joins it, then releases GPU resources. Cancellation before guest
   creation still returns without launching via EmbeddedSessionCoordinator.
2. Keep the existing short SDL3 callback fix from the undelivered 532. Publish
   each audio buffer's accounting before its PCM is visible to the callback.
   A deterministic callback interleaving previously consumed PCM with no
   matching queue entry, leaving played counts and guest recycling incorrect.
   SDL3 permits a short callback: https://wiki.libsdl.org/SDL3/SDL_SetAudioStreamGetCallback
3. Fence polls distinguish Timeout from Vulkan failures instead of mapping
   device loss and out-of-memory to an unsignalled fence. Teardown retains the
   original render exception as its inner exception, rather than hiding it
   behind the restart requirement. This improves failure handling, not a
   demonstrated cure for Zelda device loss. Quarantine remains mandatory.
4. Record effective resolution, shader cache, async shaders, VSync, memory
   tracking, recompression and threading after saved options are applied.
   No personal paths, keys or profile contents are added to diagnostics.

Existing 531 Vulkan-host-import fallback and synchronous shader defaults are
retained. Explicit saved settings, saves, keys, firmware and caches are not
reset. No other emulator is changed or rebuilt.

## Validation

The regression runner executes the actual adapted audio methods and Vulkan
fence helper against deterministic I/O doubles. It covers short/empty audio,
frame alignment, producer/callback interleaving, timeout, device loss and OOM.
The lifecycle suite now covers a pre-stopped window whose guest cannot finish
until renderer readiness. The old cancellation-before-run test is retained.
The candidate must also pass the actual two-session ARM64 simulator smoke,
then the Release iPhone assembly and downloaded-payload verification. None
of these constitutes physical iPhone gameplay/audio validation.
