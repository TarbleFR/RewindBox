# RetroArch catalog shader crash — compiler symbol collision

The maintainer confirms Dolphin effects work on Wii/GameCube and reports an
immediate RetroArch catalog Apply crash in private Build 456. Dolphin code,
effects, catalog and core remain unchanged in this correction.

## Device evidence

The supplied `session.log` records NeoStation **0.0.7 (456)**, Azure Dreams
(European CHD), **Beetle PSX HW 0.9.44.1-GLES3 10e4b0c**, core
`mednafen_psx_hw`, **software** renderer, internal resolution 4x. The failing
selection is `slang:reshade/handheld-color-LUTs/PSP-2020.slangp`, attempt
`51F2952B-98CA-4379-9102-ACC85D9D49A2` at 16:21:26.050 UTC.

There is no compilation-completed or GPU activation entry. The earlier
`unfinished-session.log` describes the same game/core without a shader
attempt and cannot locate this crash. These application journals do not
themselves identify an iOS exception, GPU interruption or jetsam termination.
No additional device exception report is claimed or required from the user.

## Demonstrated native defect

The sealed Build 456 IPA contains exported glslang implementations in both
`DolphinCore.framework` and `neo_shader_kit.framework`; Runner loads Dolphin
first. Both export the weak explicit `TIntermediate::addSwizzle<int>` and
`addSwizzle<TMatrixSelector>` instantiations. Two-level symbol namespaces do
not isolate coalesced weak definitions. The shader kit uses glslang 16.3.0;
Dolphin's pinned source is `7cac54161659421ed95c2cd1c0b0746539a4cd38` and
contains an older incompatible compiler.

Native reproduction uses the unmodified compiler source lists from those
two revisions, separate arm64 macOS dylibs, release `-Os`, and Runner's
load order. Run **38601427898**, source
`28ccbb8565fd10008ad35c14b8c4da25b5e8d675`, crashes for all five tested
official presets before isolation. LLDB records:

```text
NeoSlangCompiler.cpp:577 — new kit TShader::parse
new kit TParseContext::handleDotSwizzle — ParseHelper.cpp:1139
old compiler TIntermediate::addSwizzle<int> — Intermediate.cpp:2662
old compiler TIntermNode::operator new — intermediate.h:1078
old compiler TPoolAllocator::allocate — PoolAlloc.cpp:245, ++numCalls
EXC_BAD_ACCESS: allocator this=0x25cc, access at 0x261c
```

The parser in one compiler calls the other compiler's weak instantiation
and allocator, whose thread-local pool is not the parser's pool. This is a
native CPU crash during GLSL parsing, before Metal compilation or resource
activation. The exact preset from the device journal reproduces it. Its two
LUTs are valid 1024x32 RGB PNGs; isolated translation also succeeds with a
256 KiB stack. Neither fact proves the complete iPhone runtime on its own.

The other reproduced presets are `crt-easymode`, `crt-geom`, the two-pass
`crt-geom-mini`, and `sharp-bilinear`. This fault is shared by cores using
the kit and presets that enter the affected vector/matrix swizzle parsing;
it does not depend on the PSX console or the software frame format. Do not
interpret five cases as a proof that every possible preset crashes.

## Correction and why earlier tests missed it

Commit `d457c8ff3b613799317f972b502878b776d8f2a0` adds a linker export list
to the pod. The public Objective-C/Neo C API remains exported; the C++ core,
glslang and SPIRV-Cross stay private to their framework. No shader is
substituted or globally disabled. No Dolphin/core source or native recipe is
changed. The same five presets compile successfully with both dylibs loaded
after applying this boundary. Regression tests preserve the exact old
faulting stack and verify the corrected result.

Earlier catalog tests linked only one compiler into a host executable;
embedded session probes similarly compiled the kit directly into their
small app. Neither process included the other compiler image that ships in
the full IPA. Storage validation, GPU lifetime fixes and recovery therefore
could not repair this distinct link-time problem.

`test/neo_shader_kit_ios_build.py` applies the actual pod's export setting
and checks its public API and absence of compiler exports. The delivery now
also checks the **final IPA's dyld export trie**, so a build that omits the
linker boundary is rejected. That gate rejects the actual sealed Build 456.

## Validation boundaries

- Linux: 141 portable core checks passed. Delivery guard regression: 15
  checks passed; preflight preserves the existing library and engine pins.
- macOS native: five old faults reproduced with LLDB, five corrected
  translations passed with the other compiler loaded (run above).
- iPhone toolchain: the pod compiles and links, public API remains visible,
  compiler implementation is hidden (run 38600951774, product `d457c8ff`).
- macOS Metal: **982 catalog entries rendered, zero failures**, including
  iPhone-targeted translation/offline Metal compilation; run 38600951774,
  product `d457c8ff`. Device reports Apple Paravirtual device (host Metal
  validation, not physical iOS).
- The strict fault-stack regression passed again on the delivery candidate
  `90f62c5c`, run 38602335265.
- Synthetic embedded session scenarios: six passed, source `28ccbb85`, run
  38601422411. Final six synthetic scenarios, including compilation failure and an
  unsupported texture, passed on `8543b760` in run **38607080426**.
- Official catalog session scenarios: **six passed**, same revision/run,
  iPhone SE (3rd generation) iOS 26.2 Simulator. Actual download and Apply
  menu handlers fetched `PSP-2020` with two LUTs and the two-pass
  `crt-geom-mini` over HTTPS. Presented drawable PNGs and pixel comparisons
  confirm the effect, parameter changes, repeated switches, disable,
  console-scope restoration and saved-preset relaunch. There were zero
  visual verdict problems. Evidence artifact **11915897285**, ZIP SHA-256
  `99bb9ce6fe3a0867b87ed7ef0a64e7493d72766fc49bfe1edcefe8dc1f83d0f3`.
- Physical iPhone: the user supplied the failing Build 456 test. No physical
  test of the correction has yet been performed. The Mac native reproduction
  strongly connects the demonstrated defect to the device journal but does
  not substitute for confirming the new IPA on that iPhone/Azure Dreams.

The simulator's official scenario uses the shipped catalog and production
HTTPS transport, existing entry/download/Apply handlers, shader parameters,
repeated switches, disable and stored selection on relaunch. Pixel evidence
comes from the actual embedded session's presented drawable. Its software
and Vulkan test cores are explicitly identified as test cores; DeSmuME is a
real delivered core running original homebrew content. Synthetic catalog
cases separately cover invalid/incomplete/missing-dependency failures and
recovery; they are not described as official server failures.

## Additional confirmed menu defect

The official scenario exposed a separate preference/runtime mismatch:
`activeShaderOptionWithScope:` used only the saved requested preset. After
crash recovery or a refused load, Apply could therefore be a no-op although
no matching slang program was active. Commit `8e6e1fe6` checks actual
activation. Commit `8543b760` separates the resolved requested value from
the active value so scope changes, removal and restoring console defaults
still load the requested shader correctly. The final official scenario
exercises the console default -> game override -> restore-console sequence
and its pixels, then saved override -> close -> relaunch. This change is
confined to `LibretroFrontendMenu.m`; Dolphin and the core binaries remain
unchanged.

Private delivery candidate is `8543b7609d1c793d4c4803b8d95cdecb7561f988`,
run **38608563662**, version **0.0.7 (457)**. Earlier runs 38602619474 and
38605838506 were cancelled before delivery to include the final menu fixes.
Final packaging evidence will be recorded in `build457-plan.md`.
