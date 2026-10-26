# MeloNX Persona performance/flicker investigation — 25 October 2026

The user reports heavy flickering and slowdowns with Persona 4 on the embedded
MeloNX (Switch) engine, and states the slowdowns were **not** present on the
standalone MeloNX app. This document records a root-cause analysis focused on
that standalone-vs-embedded difference, plus a frame-level analysis of the
supplied recording. It complements, and does not replace,
`docs/melonx-fermeture-persona-2026-10-25.md` (the close/teardown and
texture-disposal investigation, build 544). Investigation only: no Core, engine,
Dart or UI source is changed here, and no FPS or physical-device cure is claimed.

## Relation to the existing Persona investigation

`docs/melonx-fermeture-persona-2026-10-25.md` analysed `app (1)(1).log` and
`app (1)(3).log` and found: Persona 4 Golden shows **no confirmed rendering
error after the 530 fix** (clean first frame, 19–118 s sessions, `close passed`,
no missed compiles, no cache-budget hit, no syncpoint wait, no DeviceLost); the
Persona 5 Royal black regions remain an **unconfirmed** hypothesis tied to a
freed-then-reused texture (its candidate fix is the build-544 idempotent texture
disposal), with no clip available to that session. That analysis did **not**
examine backend threading, and did not have the screen recording.

This document adds two things that investigation did not have:

1. A frame-level analysis of the supplied **Persona 5 Royal** recording.
2. The observation that the embedded engine runs with **backend threading
   disabled**, whereas the standalone app forces it **enabled** — the direct,
   previously-unexamined explanation for "slower than standalone".

## Supplied evidence and limits

- `app.log` (10,467 lines). Latest process PID 87029 (Persona 5 Royal, 19:40–
  19:43 UTC). It carries the `Applied graphics:` effective-options prefix (build
  marker ≥ 539) and the 537 Apple audio lines, so the installed build is recent
  but predates the build-544 close/texture fix and does not include the 540
  pipeline candidate.
- A ~20 s screen recording of **Persona 5 Royal** at the main menu. Per-frame
  luminance analysis confirms real flicker: whole-frame brightness alternates
  between a rendered state and a near-black state (logo-region mean luma swings
  from ~95 to ~0.5 between neighbouring captured frames; whole frames go to
  near-black intermittently). The clip shows the symptom, not the internal
  mechanism, and it is Persona 5 Royal, not the Persona 4 title named in the
  request.
- In this `app.log`, the Persona 4 Golden session (PID 86981, 19:38 UTC) ran at
  `resolution=1` (integer); the Persona 5 Royal sessions ran at `resolution=0.75`
  (non-integer). Both Persona sessions here log a few `GPU processing thread is
  too slow, waiting on CPU...` warnings and the 128 MiB pipeline-cache-over-budget
  warning.

## Primary cause of the slowdowns: backend threading is forced off

The embedded engine builds its launch options in
`native/melonx/EmbeddedSession.cs:154` with `BackendThreading =
BackendThreading.Off` hardcoded (confirmed still present at `origin/Claude`
`6c6c624`), and `EmbeddedGraphicsSettings` does not expose a threading field, so
there is no per-game override through the RewindBox graphics dialog. Every
session journals `... threading=Off`.

The **standalone** MeloNX app does the opposite: `RyujinxController.startGame`
sets `settings.backendThreading = .on` unconditionally before each launch, and
its own default is `.on`.

With threading off, the engine runs the unthreaded renderer: guest GPU FIFO
processing, host Vulkan→Metal command recording/submission, pipeline creation
and presentation all run on **one** render thread, so any synchronous pipeline
compile or slow Metal submit stalls emulation and present together. With
threading on, `TryMakeThreaded` wraps the renderer in `ThreadedRenderer`, which
runs host submission on a dedicated `GPU.MainThread` decoupled from the guest
FIFO loop. Ryujinx's Vulkan renderer reports `PreferThreading => true`.

This is the clearest configuration divergence from the standalone app and is
consistent with the journal signals (`GPU processing thread is too slow`;
repeated cold pipeline compilation because the >128 MiB cache is never
persisted). A log cannot measure FPS, so this is identified as the primary
candidate matching the "slower than standalone" report, not a measured gain. The
RewindBox frontend already *intends* threaded rendering: the migration layer in
`lib/services/melonx_migration_service.dart` emits `'backendThreading': 2` (On),
but the native parser drops it (only an imported standalone `config.json`, via
`EmbeddedPersonalOptions`, is read for this key), so the embedded engine runs
threading off regardless.

## Why threading is pinned off: a teardown deadlock, not an oversight

Enabling backend threading is **not** a default flip. The embedded single-session
lifetime (`native/melonx/EmbeddedWindowLifetime.cs`, applied over `WindowBase` by
`build-utils/melonx/adapt_session.py` — both unchanged by the build-544 work) is
built around the *unthreaded* renderer and will deadlock on teardown with
`ThreadedRenderer`:

- Unthreaded, `IRenderer.RunLoop(gpuLoop)` calls `gpuLoop()` inline and returns
  when the render loop exits; the lifetime's render worker then runs its
  `finally` and calls `releaseGpu()` (renderer dispose).
- Threaded, `ThreadedRenderer.RunLoop` starts `gpuLoop` on a new `GPU.MainThread`
  and **blocks the worker thread in `RenderLoop()`** until `_running` is cleared.
  `_running` is cleared only by `ThreadedRenderer.Dispose()`. But the only
  renderer dispose is inside `releaseGpu()`, which runs in the worker's `finally`
  **after** `Render()` returns — and `Render()` cannot return while the worker is
  blocked in `RenderLoop()`. Nothing on the controlling thread disposes the
  renderer (`stopGuest` disposes Horizon and cancels the shader-cache token, not
  the renderer). The worker spins forever.

So `BackendThreading.Off` is a deliberate workaround for this structural
mismatch. (The adapt script keeps the upstream `FlushThreadedCommands()` call
verbatim, which can misleadingly suggest the threaded path is wired; it is not
reachable end-to-end in the embedded lifetime.)

## Flicker contributors

The flicker is separate from the slowdown and has more than one candidate, none
yet confirmed on device:

1. **Freed-then-reused texture rendering black/stale data.** This is the
   build-544 investigation's leading hypothesis for the Persona 5 Royal black
   regions (`melonx-fermeture-persona-2026-10-25.md` §2.2, §6). Its candidate fix
   is the idempotent texture disposal delivered in **build 544**. The supplied
   recording visually corroborates intermittent whole-frame black output, which
   is consistent with that hypothesis, but neither this nor build 544 is
   validated on device. The user's current build predates 544.
2. **Speculative pipeline warm-up poisoning.** Addressed by the Build 540
   candidate (`build-utils/melonx/adapt_pipeline.py`), also unvalidated and not
   in the user's build.
3. **Non-integer resolution scale (Persona 5 Royal clip, `resolution=0.75`).**
   Scales below 1x and non power-of-two scales are a known source of scaling
   artefacts in this engine; `0.75x` is a plausible added contributor to the P5R
   flicker. Persona 4 Golden ran at `resolution=1`, so this does not apply to the
   Persona 4 complaint.
4. **Frame-pacing instability under single-thread GPU starvation** (the
   backend-threading cause above) degrades pacing and makes any of the above
   read worse than on the standalone app.

Note on the Persona 4 complaint specifically: the logs show no journaled Persona
4 Golden rendering fault after the 530 fix, and visual correctness is not
journaled, so the P4 flicker is most likely the un-journaled frame-pacing
instability (threading) and/or the texture-disposal hypothesis above, rather than
a distinct confirmed P4G rendering bug.

## Fix implemented

Backend threading is now enabled by default for the embedded engine, matching
the standalone app. Because enabling it alone would deadlock the session
teardown, the lifetime was restructured first. The change is in two parts:

1. **Teardown restructure** (`native/melonx/EmbeddedWindowLifetime.cs`,
   `build-utils/melonx/adapt_session.py`). The GPU render loop now reports it has
   drained through `EmbeddedWindowLifetime.NotifyRenderDrained()` (called where
   the upstream `_gpuDoneEvent` signal was), and the renderer is disposed
   (`releaseGpu`) from the controlling thread after that signal, not from the
   render worker. With the threaded renderer the worker is parked in
   `RenderLoop()`; disposing from the controlling thread unblocks it, mirroring
   the standalone `WindowBase.Execute`/`Exit` split. The unthreaded path is
   unchanged in effect (render returns on its own, then the dispose runs). The
   quarantine guarantees are preserved: on a guest-stop failure the renderer and,
   when threaded, the parked background render worker are left rooted until
   process exit, and the worker is not joined (its `RenderLoop` would never
   return); `GuestStopFailed`, `EmbeddedGpuReleased`, exactly-once release and
   `FinalizeWindowRenderer` after `DisposeGpu` all still hold. The build-544
   idempotent GPU-texture disposal (`adapt_gpu_lifetime.py`) makes this release
   path safe even if a dispose step throws.
2. **Threading default + per-game override.** `EmbeddedSession.cs` now builds
   options with `BackendThreading.On`. `EmbeddedGraphicsSettings` parses a
   per-game `backendThreading` boolean (absent = base On; `false` = the escape
   hatch for a title that misbehaves threaded). The RewindBox graphics dialog has
   a "Backend threading" toggle (default on, localized in all twelve locales),
   and `migratedGraphics` carries the setting over from an imported standalone
   `config.json`. The effective-options journal already logs `threading=…`.

**Validation status.** Updated the managed lifecycle test
(`test/melonx_session_test.py`: GPU release now asserted on the controlling
thread, plus a new threaded-render-loop case that disposes from outside the
parked worker) and the effective-graphics test
(`test/melonx_effective_graphics_journal_test.py`: default preserved when the
key is absent, explicit `threading=On` override). These are managed-host
coverage. The change is concurrency-critical and touches the session teardown;
it **must be built and validated on a physical iPhone** before acceptance (no
iPhone here, and no Core rebuild or IPA was produced). Suggested on-device check:
launch Persona, confirm the journal shows `threading=On`, play, then close from
RewindBox and from in-game (including during a load) and confirm `close passed`,
`memory released` and a clean return to the playlist, with no stuck "Closing the
game…" route — reusing the build-544 close probe.

## Immediate workaround (until the rebuilt Core is installed)

- For Persona 5 Royal, set the per-game **Resolution to 1.0x** (integer) in the
  RewindBox graphics dialog to remove the non-integer-scale flicker contributor.
  Persona 4 Golden already runs at 1.0x, so this does not apply there.
- Reinstall the latest test build (544) to pick up the texture-disposal and
  close fixes. The threading change above needs a new Core build on top of that.

No tags, main-branch changes, builds or releases were produced by this work. The
threading change is committed to the `Claude` branch for review and an
authorized Core rebuild; it is not validated on device.

## In-game FPS counter

To make slowdowns measurable without the standalone app, the in-game RAM overlay
("RewindBox RAM", toggled by the existing **RAM graph** setting and menu entry)
now also shows the game's frame rate, right-aligned on its title row (`60 FPS`).
The value is the engine's own `Device.Statistics.GetGameFrameRate()`: the game
FPS that standalone MeloNX reports through its `push_statistics` callback, which
the embedded host never registers.

- **Core.** `native/melonx/EmbeddedPerformance.cs` exports
  `neostation_melonx_performance_snapshot(generation, double *values, 3)`: game
  FPS, frame time (ms) and FIFO percent. It goes through the same session gate
  as the live aspect ratio (stale, stopped or ended generations return 2) and
  zeroes non-finite values (frame time is `1000 / 0` before the first measured
  frame). It is in the required exported ABI of `build_core.sh`.
- **Host.** `MeloNXRuntimeAPI` resolves the symbol optionally, so an older
  Core leaves the overlay RAM-only instead of failing to launch. The session
  view merges the snapshot for its live generation into the overlay's existing
  0.5 s sample; nothing new is polled while the overlay is hidden or the app
  is inactive.
- **Validation.** `test/melonx_display_native_test.py` runs the production
  export against a statistics double (argument refusal, no window, live values,
  NaN/Infinity, stale and stopped generations). `test/melonx_memory_graph_test.py`
  checks the label in UIKit (`60 FPS`, empty without a session, `30 FPS`).
  `test/melonx_runtime_smoke.py` resolves the export in the real NativeAOT image
  and checks that stale and ended generations are refused. The homebrew session
  presents no frames, so a real game frame rate is only visible on device.

## Private build 549

Build 549 combines three validated deliveries on the 546 delivery tree, which
do not share a file: the RPCS3 547 Core files (as delivered in 547), the Liquid
Glass interface (as delivered in 548) and the MeloNX threading default and FPS
counter above. Installing 549 over 547 or 548 loses nothing from either.

- Recipe: `.github/diagnostics/melonxthreading549_tree.py` (pin),
  `melonxthreading549_delivery.py` (source contract, components by artifact ID
  and digest), `build-utils/validate_melonx_threading549_ipa.py` and
  `validate_liquid_glass549_ipa.py`, workflow `melonx-threading549-delivery.yml`.
- Engine 9bf068b run 40235589254 (attempt 2, artifact 12614789426) and host run
  40235589280 (artifact 12615322102).
- Frontend re-run on the exact pinned tree (`docs/evidence/melonx-threading549-local.json`):
  12 import, close-status (negative control reproduced), 5 audio, 7 route,
  11 launch-flow, 4 display and 3 threading tests, the 342-test Liquid Glass
  suite and the full-application analyzer (no error or warning).
  `test/melonx_transfer_test.dart` fails one Liquid Glass Import-icon contrast
  case identically on the delivered 548 tree; it is not changed here.
- On iPhone, check: the journal line `threading=On`; Persona 4 Golden fluidity
  and flicker against the standalone app; the `NN FPS` counter in the RAM
  overlay; closing from RewindBox and in game, then relaunching.

## Standalone parity after 549 (build 552)

The 549 report (`threading=On`, no more "GPU too slow") left the Persona 5
Royal flicker and the Persona 4 Golden stutter. A second comparison with the
standalone app at the pinned revision found these differences; 552 closes them
or makes them testable.

- **MoltenVK binary.** The standalone app links its own
  `src/MeloNX/MeloNX/Dependencies/libMoltenVK.dylib` (reports MoltenVK 1.4.0,
  SHA-256 `5735ca4a…6bfa5`); RewindBox builds Khronos MoltenVK v1.3.0 from
  source. By the maintainer's explicit exception, 552 ships both:
  `MeloNXMoltenVKStandalone.framework` holds the unmodified standalone bytes
  (only the install name changes; `build-utils/melonx/package_standalone_moltenvk.py`,
  Apache-2.0 notice in `Legal/MeloNX/StandaloneMoltenVK`). The host selects one
  per process before the engine loads (`neostation_melonx_select_moltenvk`);
  the standalone one is the default. The in-game menu entry *MoltenVK version*
  switches, applied at the next RewindBox start. The journal's `frameworks`
  line names the loaded binary and its hash prefix.
- **MoltenVK's own reports.** The standalone app sends stdout and stderr to its
  log file; MoltenVK writes there (device loss, failed command buffers).
  During a session RewindBox now copies stderr into `app.log` as
  `[MeloNX:stderr]` lines (2000 per session, same redaction as the journal).
- **Engine options journal.** A `configuration/engine` line lists every other
  option the engine consumes (PTC, macro HLE, docked, memory manager, scaling,
  language, region, custom VSync, MoltenVK) for a field-by-field comparison
  with the standalone config.
- **Unbounded present target.** The standalone app calls
  `set_unbounded_present_target_fps(screen.maximumFramesPerSecond)` on every
  layout; RewindBox never did, so VSync *Unbounded* was capped at 60 by the
  engine default. Now sent on layout and at the first frame.
- **Game Mode.** `LSSupportsGameMode`, `GCSupportsGameMode` and
  `LSApplicationCategoryType = public.app-category.games`, as in the standalone
  Info.plist and project.
- **Auto-lock** is disabled during a session, as in the standalone app.
- **Imported backend threading.** The standalone config stores Off by default
  but forces On at launch; RewindBox no longer imports that stored value.

Not changed: `CADisableMinimumFrameDurationOnPhone` stays in RewindBox (the
120 Hz interface needs it). The standalone app lacks it, so on a ProMotion
iPhone its game layer is capped at 60 Hz while RewindBox's is not; this remains
a candidate for the Persona 4 Golden frame pacing. Shader cache defaults
(standalone: off) stay a per-game setting.

### Review before the build, and numbering

An adversarial review of the parity change (four dimensions, two independent
skeptics per finding) confirmed one defect and split on three:

- **Confirmed, fixed (`6633588`).** Builds 549 to 551 imported the standalone
  config's stored threading Off as `backendThreading: false`. Any per-game save
  (RAM graph, screen format, the per-game dialog, a library move) kept it as
  if chosen, so removing the import was not enough. `graphicsForGame` now
  clears that value once per game when the imported config holds Off. A later
  explicit choice is kept (`test/melonx_threading_residue553_test.dart`).
- **Fixed (`a487268`).** While fd 2 is a pipe, NSLog copies its messages there
  too, and on iOS .NET's `Console` (Ryujinx stubs and info) goes through
  NSLog. Those lines could use up the 2000-line budget before MoltenVK's own
  writes. They now have a separate 500-line budget, and the pump runs at
  `userInitiated`. The MoltenVK preference falls back only when the private
  frameworks fail to load.
- **Accepted limits.** Lines still in the pipe when the process dies are lost.
  The unbounded-present target is set again on layout, but not when a title
  relaunches itself into a new Switch context; with VSync Switch it has no
  effect.

552 went to the urgent RPCS3 551 launch-crash fix. This change ships as
**private 553** on that 552 tree, so the fix is kept. A dry run of the change
on the 551 tree (run 40331958399) passed every job, including the macOS Swift
capture and the signed-IPA validators. It was not delivered.

## Private build 553

- Private IPA **0.0.8 (553)**, run 40342988817 on `4a4d0fc`: the delivered
  552 tree (551 tree + RPCS3 launch-crash fix) with the parity files of
  `62626c0`, `a487268` and `6633588`. 187,987,716 bytes, SHA-256
  `82abd248…1997a`. Receipt: `docs/evidence/melonx-parity553-delivery.json`.
- The standalone app's MoltenVK is not a Khronos release: its `MVK_GIT_REV`
  (`85d607a1…`) is not in KhronosGroup/MoltenVK. It is a fork build that
  reports 1.4.0. The latest Khronos release is v1.4.2, which RewindBox's RPCS3
  already uses. 553 compares the standalone binary with RewindBox's 1.3.0, one
  variable at a time. If the standalone binary removes the flicker, a later
  build can offer Khronos 1.4.2 as a third choice to see whether a traceable
  release is enough.
- On iPhone, check:
  - the `frameworks` journal line names `MeloNXMoltenVKStandalone sha256:…`;
  - `[MeloNX:stderr]` lines appear during a session;
  - the `configuration/engine` line is present;
  - Persona 5 Royal flicker and Persona 4 Golden stutter with the default,
    then with "MoltenVK version: RewindBox (1.3.0)" after restarting
    RewindBox.

## Tester report on 553: flicker gone, stutter remains (26 October 2026)

With the standalone app's MoltenVK (553 default), the flicker is gone. A
23 s recording and app.log were analysed: four independent analyses (video
pacing, log timeline, engine, host parity) plus a skeptical synthesis.

- **The clip is Persona 4 Golden's anime FMV** (limousine intro, session pid
  96631), not real-time 3D. The FPS overlay reads 60-62 FPS while one movie
  image stays on screen for up to 14 refreshes: the renderer is not the
  bottleneck.
- **Movie images arrive irregularly.** 161 holds over 19.4 s: mean 7.23
  refreshes, sd 2.67, range 1-14. The ideal is 8 for the 7.5 Hz pan and 6 for
  the 10 Hz pan. No image is skipped, and the movie keeps real time on
  average, wandering by up to about 0.44 s.
- **The game audio cuts out at the same time:** about 30% digital silence, 9-12
  gaps per second, up to 380 ms. The same build's P5R session logged 23 CRI
  "Output buffer underrun" lines. Leading hypothesis (unproven): the guest's
  CRI audio and movie threads, or the audio renderer's DSP thread, sometimes
  run too late.
- **Ruled out as the difference from standalone:**
  - shaders (0 pipeline misses in the P4G session);
  - MoltenVK;
  - the 120 Hz screen (at most ±1 refresh);
  - the Flutter UI, the RAM graph and the stderr capture;
  - the FFmpeg build;
  - the iOS audio session (48 kHz and about 5 ms I/O in both apps);
  - the audio backend (the same AVAudioEngine driver);
  - the NativeAOT project settings (identical csproj, `ConserveMemory=9`).

  Not ruled out: emulation-thread QoS, device temperature, and the scene
  itself. The standalone was never recorded on the same scene.
- **P5R (separate issue):** its per-game shader cache was Off from 12:57Z on.
  That was the no-build flicker test. 83 synchronous pipeline compiles on the
  render thread were logged, 76 within 13.6 s. Earlier P5R sessions with the
  shader cache On had none. Now that MoltenVK fixed the flicker, the shader
  cache should go back On.
- **Logging gaps:**
  - the 500-line NSLog budget ran out at 11.9 s of emulation, so the recorded
    window has no engine lines;
  - the Dart logger overwrote a native app.log line (line 22805 starts
    mid-line);
  - thermal state is not journaled during a session.

## MeloNX measurement build 558

Number 555 is the RPCS3 Cell work (`f508f1b`, not this session); 557 is the
interface session's library-file fix. The maintainer asked for this build on
26 October, together with a real fix for the log after a data migration and
the macOS tests on every push, and then asked for it to be compiled on top of
557 once 557 finished. It was first prepared as 556 on the 554 tree; 556 was
never armed nor delivered, and the same change ships as 558 on the delivered
557 tree (recipe in `AGENTS.md`), so 558 also carries 557's library-file fix.
558 adds measurement only and changes nothing in emulation; the one new
setting, the in-game priority choice below, keeps today's behaviour by
default. The comparison the tester runs with it: P5R with its shader cache
back On, then the same scene in RewindBox and in the standalone app.

- **`[MeloNX:perf]` lines in app.log, one per second during a game**
  (`MeloNXPerfJournal.swift`). Format, with illustrative values:
  `t=42 fps=59.8/16.7/38 pres=60/34.1/2/0 dsp=200/3/7.5/3.1/0 out=200/1/12.0/12.0 cpu=245 NeoStation.MeloNX.Render:88/37 … th=nominal lp=0`
  - `fps`: the engine's game FPS / frame time ms / FIFO %.
  - `pres`: frames presented / longest gap between two presentations ms /
    gaps over 20 ms / gaps over 40 ms. A pause restarts the gap
    measurement. At 60 fps a gap over 20 ms is a held frame. At 30 fps
    (P5R) every frame is over 20 ms, so read the 40 ms count.
  - `dsp`: 5 ms audio DSP periods / late episodes / their lateness ms / the
    longest ms / periods skipped. An episode is a period more than 2 ms late
    plus the catch-up periods that follow it, counted once by its first
    lateness, so a 20 ms stall counts 20 ms, not 20+15+10+5.
  - `out`: audio buffers played / times the output queue ran dry / total
    silence until the next buffer ms / the longest ms. A guest stop is not
    counted, nor is a completion that races a new buffer.
  - A RewindBox pause (the menu, the app in the background) stops the guest
    and its audio. The engine marks each resume (`Horizon.TogglePauseEmulation`).
    DSP periods due before the resume, plus 50 ms of catch-up, are not
    counted as late or skipped. An output starvation that began during the
    pause is not counted either.
  - `cpu`: process CPU % (100 = one core), then the six busiest threads as
    `name:CPU %/base priority` (47 user-interactive, 37 user-initiated,
    31 default, 20 utility, 4 background).
  - `th`, `lp`: thermal state and Low Power Mode; `paused` while the game is
    paused.

  The journal is capped at 1800 lines, then writes an end summary; its
  game-FPS average leaves out paused seconds and boot seconds at 0 FPS. Its
  lines may go past app.log's 5 MiB general cap, up to 8 MiB, so a long
  stderr capture cannot cut them off.
- **Engine audio counters** (`EmbeddedAudioPacing.cs`, exported as
  `neostation_melonx_audio_pacing`). They feed `dsp` and `out`, and were
  added by `adapt_audio_pacing.py`, which only adds lines around the
  unchanged wait loop. `test/melonx_audio_pacing_test.py` runs them with
  the adapted Apple session against the timed AVFoundation double.
- **Dart no longer overwrites native lines.** `AppendFileOutput` writes each
  event with C `fopen(path, "a")` (O_APPEND) through `dart:ffi`. Reopening
  with dart:io was not enough: it seeks to the end, then writes later, and
  lost 6 of 20,000 lines from a concurrent `>>` writer in the local
  stress test. With `fopen` it lost none (`test/logger_append_test.dart`).
- **The live log follows a user-data migration.** `migrateData` copied
  app.log like any owned file: its size check raced the logger's writes, the
  lines logged after the copy were deleted with the source, and later lines
  recreated app.log in the old folder. The log being written is now left out
  of the generic copy; once every other copy is verified,
  `LoggerService.moveLogFile` copies it to the destination, writes there and
  deletes the old file, synchronously, before any source is deleted
  (`test/user_data_migration_log_test.dart`, which fails on the 557
  migration).
- **The macOS Swift tests run on every push.** `melonx-host.yml` now runs
  `test/melonx_perf_journal_test.py` and `test/melonx_standalone_parity_test.py`
  (approved by the maintainer); both passed on macOS in host run 40385961915.
- **Repeated NSLog stubs are copied once.** The key ignores both NSLog's
  timestamp and Ryujinx's own clock (`00:00:00.715 |S| …`). Later repeats
  are counted, the ten most repeated are listed at the end, and the 500-line
  budget keeps distinct messages.
- **"Emulation priority" in the in-game menu**, applied at the next game:
  - "High (RewindBox)" (default) keeps the user-initiated session thread;
  - "Default (MeloNX app)" lowers it to default QoS before the engine runs,
    like the standalone app's plain thread.

  The `session/emulationPriority` journal line gives the status and the
  class in effect. The `cpu` field shows whether the render and guest
  threads follow.
- **Reading a stutter:**
  - `pres` gaps with `dsp` lateness and high CPU on guest threads point to
    scheduling;
  - `out` starvations with on-time `dsp` point to the producer;
  - gaps with `th=serious` point to heat;
  - gaps with nothing else point to the game or scene.

  Compare the A/B lines of the same scene.
