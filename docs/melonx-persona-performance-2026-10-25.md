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
