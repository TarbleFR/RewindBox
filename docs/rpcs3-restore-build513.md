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
