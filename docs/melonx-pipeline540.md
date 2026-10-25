# MeloNX pipeline recovery candidate — 25 October 2026

The short supplied clip shows black regions in the Persona 5 Royal main menu.
The second clip shows Persona 4 Golden rendering normally; it does not establish
a same-game, same-scene comparison. The latest Persona session in the supplied
journal reaches its first frame and closes cleanly. No pipeline compilation
failure is recorded there. The Zelda `ErrorDeviceLost` report is separate.

## Reproduced source defect

Pinned MeloNX `13700519f3abc4e6d7ed8a065b118b2cc59bcd67` performs a speculative
pipeline warm-up even with asynchronous shaders disabled. The synchronous path
marks the whole shader program failed if creation against its initial dummy
render pass throws. Valid modules are then unavailable to a draw with a different,
valid pipeline state. Temporary native pipeline state is also not disposed when
creation throws. The asynchronous path already distinguishes module validity from
an unsuccessful pipeline warm-up.

`adapt_pipeline.py` retains valid modules after a recoverable synchronous warm-up
error, disposes temporary state in `finally`, and preserves fatal device/memory
errors as exceptions. Actual graphics pipeline failures previously cached a null
pipeline silently; they now emit a single error for that state with result code,
stage count and sample count. The existing effective-options journal fix is also
included. Saved graphics settings and caches are not reset.

## Executed checks

`test/melonx_pipeline_failure_test.py` runs extracted, unmodified production
methods and their adapted versions against deterministic Vulkan I/O doubles:
29 assertions on each version. The original reproduces program poisoning,
temporary-state leakage and silent graphics errors; the adapted methods preserve
a valid subsequent draw, module-error rejection, successful compilation, fatal
error propagation and non-error `PipelineCompileRequired` handling. The full
source compiled successfully for iPhone and iOS Simulator in native run
`40196037086`, with all 43 expected exports. Two actual ARM64 Simulator
sessions passed using the original non-graphical homebrew guest. The 22 previously executed settings/journal checks are retained only
when every source input still matches.

These checks establish the source correction, not the cause or resolution of
the supplied Persona pixels. No physical iPhone or commercial-game rendering test
has been performed. Private Build 540 is delivered as this MeloNX test candidate. It contains the
previous import, update targeting and Apple audio corrections. Its frozen RPCS3
component is `cd85227e95b75284f25308a753060ad622719489` (run `40195752177`);
subsequent concurrent RPCS3 changes are not represented as part of this IPA.

## Delivered artifact

- IPA source: `8e4c773fe70daf6ab94c1baabf79ebbd1e65d765`.
- Delivery run: `40196217049`; checks and Release device build succeeded.
- MeloNX source: `97915e506fa71be02ab38794529e81fad6780803`, native run `40196037086`.
- Device core SHA-256: `5cf5deac13ffeecc2908954bd50699275fd188626885a06f6fb831f678411b69`.
- File: `RewindBox-Build540.ipa`, version `0.0.8 (540)`, ARM64, iOS 18 minimum.
- Size: **186,338,636 bytes**.
- IPA SHA-256: `ccdaa9a1991e98004e80289bb8bda93a444de68f1a1e50df0b8b3bb11d071fe3`.
- Four encrypted transport pieces, decrypted package checksum and final payload
  identity agree. 87 ad hoc signatures passed CI verification. SideStore must
  re-sign the package for installation.
- Independent inspection of the downloaded IPA confirms its version, architecture,
  core source identity, actual new diagnostic string, absence of the old fatal
  warm-up marker and retained audio/import identities.

Evidence: `docs/evidence/melonx-pipeline540-engine-ci.json` and
`docs/evidence/melonx-pipeline540-delivery.json`. No physical-device visual cure,
Zelda device-loss cure or gameplay performance improvement is claimed.
