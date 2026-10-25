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
source will additionally be compiled for iPhone and iOS Simulator by the native
workflow. The 22 previously executed settings/journal checks are retained only
when every source input still matches.

These checks establish the source correction, not the cause or resolution of
the supplied Persona pixels. No physical iPhone or commercial-game rendering test
has been performed. Build 540 is reserved for this private candidate because
concurrent RPCS3 work is using 539. Final engine, IPA and verification identities
will be recorded after successful compilation and inspection.
