# Shader recovery and Dolphin menu follow-up — 14 October 2026

Work on `Claude`, starting from `29b24945b2e7041f08e02d7d70e8c90ffe8a1c24`.
No public release or IPA publication is authorized by this task. No new IPA
or build number has been produced; `0.0.7+455` remains the existing version.

## Evidence and scope

The maintainer reports a crash after downloading, installing and applying
a preset through the embedded RetroArch in-game menu. The exact preset,
core, renderer and installed binary are not identified by a device log.
The maintainer has no `.ips` files and explicitly asks never to request them
again. **The cause of that device crash is not demonstrated.** The defects
below are demonstrated in the sources and have executable regression tests;
they must not be presented as a reproduced iPhone crash.

1. `LibretroSession.applySlangShader` previously reported success immediately
   after selecting a compiled program, before its first GPU frame. A chain
   failing at the current output size could therefore be saved as active.
2. The installation presence check accepted a corrupt or truncated regular
   file after installation; it did not revalidate the catalog manifest before
   compilation.
3. Dolphin wrote `GFX.ini` before checking/writing the selected effect's
   options in `Dolphin.ini`. An invalid options file returned failure after
   the effect selection had already changed.
4. Dolphin effects were nested inside the display/pacing page, with no direct
   effects entry in the in-game Graphics menu.

The shared libretro presenter already normalizes supported software, GLES
and Vulkan inputs to BGRA before the slang chain. An integer texture mismatch
was investigated, not assumed: all **982 catalog presets** from
`libretro/slang-shaders@e1d75632a205c70f14a4cc947c46d5abb7b3f7f1`
translated successfully on Linux; none has an integer framebuffer pass.
This rules out that specific explanation for the shipped catalog, not all
possible texture, device, memory or synchronization faults.

## Changes

- Validate the pinned revision, complete file list, sizes and SHA-256 values
  off the UI/render threads before compilation. Missing or changed inputs
  are refused; downloading again repairs them.
- Treat selection as provisional until the actual presenter command buffer
  completes successfully. Refuse chain/GPU failures, restore the previous
  selection on the emulation thread, and ignore superseded callbacks.
- Keep a separate durable `shader-attempts.json` marker before compilation
  and while a downloaded shader is active. Clear it on handled failure,
  disabling or normal session closure. After an unexpected termination,
  skip automatic application for that core/game/preset; preserve the user's
  preferences and allow an explicit retry. A termination is not attributed
  to the shader simply because a marker exists.
- Journal the exact preset, core/version, renderer, compilation and GPU
  activation stages. Translate user-facing explanations in all twelve
  app languages; technical codes remain diagnostics.
- Add **Graphics → Post-processing effect** for both GameCube and Wii,
  opening the existing Dolphin page. Preflight both configuration files
  and restore options if the final effect-selection write fails.
- Keep Dolphin's retained core/ABI unchanged. Effects and parameters take
  effect at the next game launch; the menu says so. The badge now specifies
  a Metal test, rather than implying a real GameCube/Wii test.

## Mattias CRT

The upstream revision is still
`pakovm-git/Mattias-CRT-Dolphin@a7b5603e5954563df9d111049c9645db7a0d860c`.
The six authentic standalone shaders use the Dolphin API already supplied
by the pinned engine, with `M_CURVATURE`, `M_SCAN_SPEED` and `M_EXPOSURE`.
No generic replacement or change to those files is introduced.

The upstream `NOTICE.md` still supplies no explicit redistribution grant.
No Mattias file is bundled or automatically downloaded. The existing local
`.glsl` import, original credits and parameters remain available. See
`shaders-mattias-crt.md`. Compilation or the standalone Metal harness does
not prove that Mattias reaches the integrated Dolphin game image.

## Validation

Local checks executed before CI:

- Portable shader core: **141 checks, 0 failures** (Linux, g++/CMake).
- All 982 catalog presets: portable GLSL/SPIR-V/MSL translation, **982
  successes**; no GPU rendering in this check.
- Dolphin host wiring and twelve-language generation: passed.
- Built-in shader catalog, unchanged baseline scope, Python syntax and
  whitespace checks: passed.

New or extended CI tests:

- Actual `LibretroMetalPresenter`, offscreen Metal pixel readback on macOS:
  supported input formats, GL orientation, simple/multipass presets,
  repeated switches, parameters, GPU confirmation, `CHAIN_MEMORY` refusal,
  fallback and supersession.
- Native storage and durable recovery classes: complete/incomplete
  downloads, corruption, truncated manifests, missing dependencies,
  interrupted compilation/active session, retry, shutdown and late callbacks.
- iOS Simulator sessions: software test core, Vulkan test core and real
  DeSmuME; verified download/install/apply, simple and complex presets,
  real drawable PNG readback, repeated changes, parameters, disabling,
  invalid/missing inputs and relaunch with a stored choice. These tests use
  NeoStation's actual session and presenter, not a Dolphin substitute.
- Dolphin real-file staging regression, including the old source's partial
  write reproduced at the starting commit; iPhone compilation and UIKit
  navigation for GameCube/Wii in twelve languages. This UIKit test does
  not execute the Dolphin core.

CI outcomes and commit/run identifiers will be recorded after execution.
No physical iOS device test has been performed. Dolphin's integrated engine
has not been run with the chosen effects during this task. No performance or
stability claim on iPhone is justified by these checks.

The existing `ppsspp-crowded` assertions remain intact. Their known simulator
probe limitation is unrelated unless new evidence establishes a link. A
separate shader job prevents that existing scenario from hiding shader test
results. A stale, unrelated `dolphin_achievements_hacks_menu_test.py` assertion
for `UIBlurEffectStyleSystemChromeMaterial` is absent in the starting source
as well; it is not changed to obtain a passing result.
