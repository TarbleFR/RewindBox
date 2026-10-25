# Build 513 — RPCS3 restore memory and LLVM JIT accounting

Approved follow-up to God of War III logs from builds 511 and 512. Base application:
`83efcc4c1e633586b372c11be8fbb6c42f0baa9c`; delivered build 512 source
`02a0273494c50bc849b092c0fff395d9e5fd7ebf`, run `39959490510`.

The single canonical delta now owns `rpcs3/Loader/TAR.cpp`. On iOS the transfer
ring holds at most four 1 MiB buffers, and successfully copied streaming chunks
release consumed serial data. Desktop constants and non-streaming release
behavior are preserved. The other two changed files recognize the actual
transient `LLVM JIT` worker in both CPU groups and compiler accounting.

No settings precedence change, forced GameDB profile, deferred SPU compilation,
NEON instruction rewrite or cache deletion is included. No device performance
or physical memory saving is claimed from the portable fixtures.

Canonical patch SHA-256:
`db839d645eee6dc8dabba55a1580cb41a8314cbac0cb6c5e26f6c8a1be0f4f61`.
It was regenerated with `regenerate_canonical_delta.py`, applied afresh to the
pinned upstream revision, and every manifest postimage verified. The source
closure retains all other native blocks; only Git index abbreviations change
when the canonical delta is regenerated.

The targeted regression driver executes production TAR/read/thread-loop and
profiler regions with explicit portable adapters. It verifies byte integrity,
zero/tail/chunk/ring boundaries, a 257 MiB + 123 byte stream, non-streaming and
desktop controls, and the exact pre-fix sources as negative controls. Local
ASan/UBSan and the syntax-command preservation tests passed. CI authenticates
Core 510's immutable proof archive, retains unchanged 510/508 proofs, reruns the
new regressions with the selected macOS SDK, syntax checks all 33 iPhone units
including TAR.cpp, compiles the real Core and compares actual CMake PPU/SPU
codegen IDs with Core 510. The build script and dependency cache key are unchanged.

The private IPA must freeze the new successful Core source/run, preserve the
build 512 application and unrelated engine inputs, and validate the packaged
Core payload against that exact artifact. Final CI, IPA digest and physical
device observations are recorded separately after they exist.

## Verified private delivery

Build **0.0.8 (513)** was compiled from `f3f953c15a86463427e75a921adba814fe6e759d`.
[Delivery run 39969103515](https://github.com/TarbleFR/RewindBox/actions/runs/39969103515)
and [Core run 39968584447](https://github.com/TarbleFR/RewindBox/actions/runs/39968584447)
completed successfully. The exact new Core source is
`c5e54c5817f848e6f667b757931f91364e9faeda`.

The decrypted private IPA is `RewindBox-Build513.ipa` (186,123,825 bytes), SHA-256
`ba645e5a043738a4b3fff4518a39b76a306b890b513f015d4741b53145464b33`.
The encrypted delivery artifact is `12508788492`; the clear IPA and independent
verification report are provided in the conversation. Apple re-signing through
SideStore is required.

Five targeted macOS ASan/UBSan fixture variants passed. All 33 actual iPhone SDK
syntax units passed, including TAR.cpp; the complete Core compiled and passed
ABI 30, export and passive-dlopen gates. Actual CMake PPU/SPU identities remained
`8f9b154eb34feabb` / `7c226c2359020e20`, preserving valid object cache namespaces.

Independent verification of the downloaded final IPA checked its source-bound
Core payload, all seven app/extension versions, 86 ARM64 iOS images, 116
CodeDirectories and 132,645 code page hashes. No encrypted Mach-O image remains.
The compiled Core fingerprint is
`717909248184643b7a6ee9851bc304a314a904994dde9ef302f9d83fc853a175`.
[Machine-readable evidence](evidence/rpcs3-restore513-delivery.json) records the
artifact digests and validation scope. Physical memory/FPS gains and full game
restoration still require device testing with internal logs.

This IPA freezes the approved RPCS3 lot and delivered 512 app. Later concurrent
MeloNX development is outside this immutable candidate; the evidence-only commit
preserves that development on Claude.
