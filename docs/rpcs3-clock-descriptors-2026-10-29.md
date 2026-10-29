# RPCS3 — clock and descriptor followup, 29 October 2026

Three additional source optimizations on `Claude`, after the texture and pipeline
candidate `c4d59884667ae0e05c9c3352385418e78911dab2`. The maintainer authorized the
push and requested further optimization first. No Core build, IPA or release is
produced. The delivered binary remains application 587 / Core 591.

## Implemented changes

| Native path | Change | Preserved behavior |
| --- | --- | --- |
| `rpcs3/Emu/Cell/lv2/sys_time.cpp` | Specialize the observed 1 GHz counter: microseconds use `tsc / 1000`; 80 MHz ticks use `(tsc / 25) * 2 + (tsc % 25 >= 13)`. | Exact across the entire `u64` timestamp range. Preserve the original wrapping multiplication by clock scale, division by 100 and offset order. Other counter frequencies and zero-frequency fallback keep their original arithmetic. |
| `rpcs3/Emu/RSX/VK/vkutils/descriptors.h`, `descriptors.cpp` | Reserve a typed temporary pool at its first use, while empty, instead of reserving all three pools during initialization. | Original capacity of 16,448 entries per used pool; stable deferred pointers, retained allocation after clear, driver writes/copies, dynamic offsets and handle reuse. No pool is shrunk. |
| Same descriptor paths | Queue each descriptor once for deferred flush. The existing manager mutex protects the membership flag. | All pending writes still flush. Flush, deregistration and manager destruction reset membership; a later registration is accepted. |

All new changes are guarded by `RPCS3_IOS`. Removing the iOS branches reproduces
the exact earlier source text. The three files were unmodified upstream files
before this followup; the previous four optimized native files remain identical.

## Verified results and limits

The clock test compiles both actual production helper bodies with runtime
counter/configuration adapters and an independent `uint128` oracle. The descriptor
test compiles the actual class, typed stores, pushes, initialization, flush,
manager and `simple_array`; Vulkan calls, device capabilities and the surrounding
renderer are adapters.

| Check | Before → after / result |
| --- | --- |
| Exact clock comparisons | 459,200 cases pass, including 271,291 scale overflows, 291,023 generic-frequency cases and six zero-frequency fallback cases. |
| Generated LLVM 22.1.8 / A18, each 1 GHz helper path | Two executed `UDIV` → zero. Path-aware control-flow checks confirm the generic divisions are bypassed. |
| Generated 24 MHz fallback | Still two `UDIV`; frequency check adds four path instructions for timebase, three for system time. |
| Synthetic host median, one million calls, seven alternating runs | System: 4.14261 → 1.46250 ms; timebase: 4.19398 → 2.25502 ms. GCC 13.3.0 / Linux x86_64; no prediction of iPhone timing. |
| Initial typed-pool allocation requests per descriptor | 921,088 → 0 bytes. |
| Buffer-only descriptor allocation requests | 921,088 → 394,752 bytes. These are requested reserved bytes, not physical RAM measurements. |
| 10,000 registrations of the same descriptor | 10,000 → one queue entry and flush visit. |
| Captured driver contents | 10,076 descriptor write/copy records identical. |
| Pointer stability and lifecycle | 16,448 entries per pool; image arrays, copies, dynamic offsets, handle swap, cache generation, teardown/reuse and four concurrent registrars pass. |
| Compilers and sanitizers | GCC 13.3.0 and Clang 22.1.8 at `-O3`, assertions enabled. ASan/UBSan pass for both suites; descriptor TSan passes. LeakSanitizer is disabled in this environment. |

An empty volatile inline assembly statement inside each fast branch prevents
LLVM from if-converting the specialization and executing the generic divisions
before selecting the result. It has no memory clobber, emits no instruction,
and adds no CPU fence or synchronization. This code-generation property is
verified for the recorded LLVM 22/A18 output and must be rechecked if the compiler
changes. The specialized paths use more simple instructions than the original
paths; avoiding divisions is not a claim of fewer total instructions.

The A18 assembly is generated from the actual function bodies with external
inputs and the ARM counter read, targeting `aarch64-macos` without an Apple SDK.
It is not linked Core code, an iOS executable or a device measurement.

Evidence:

- Clock: [GCC and A18 paths](evidence/rpcs3-followup-2026-10-29/clock-plain.json),
  [assembly](evidence/rpcs3-followup-2026-10-29/clock-a18.aarch64.s),
  [ASan/UBSan](evidence/rpcs3-followup-2026-10-29/clock-asan-ubsan.json),
  [Clang 22](evidence/rpcs3-followup-2026-10-29/clock-clang22-host.json).
- Descriptors: [GCC](evidence/rpcs3-followup-2026-10-29/descriptor-plain.json),
  [ASan/UBSan](evidence/rpcs3-followup-2026-10-29/descriptor-asan.json),
  [TSan](evidence/rpcs3-followup-2026-10-29/descriptor-tsan.json),
  [Clang 22](evidence/rpcs3-followup-2026-10-29/descriptor-clang22.json).
- Integration: [canonical materialization](evidence/rpcs3-followup-2026-10-29/canonical.json),
  [unchanged harness and proof reuse](evidence/rpcs3-followup-2026-10-29/proof-reuse.json).

## Source integration and reproduction

The single canonical patch reproduces all 308 postimages from pinned upstream
`22f1152783cef1f7e04af7b1c895173e28fd5b03`. All 305 previous candidate postimages
remain identical. PPU/SPU codegen identities remain `a987639e9f838d1c` /
`d070cb361bdef607`; no generated-code cache invalidation is needed.

The first candidate's native suites are reused by exact generated-harness and
source digests. The descriptor runner now obtains optional preimages from the
pinned upstream Git commit by default; this generates exactly the tested C++
harness. Its historical reports retain their original runner digest. The first
candidate's strict manifest test now accepts exactly these three additional
reviewed paths and checks their preimages, postimages and unchanged codegen IDs.
No historical engine suites or native compilations are repeated for this change.

On an already materialized candidate, run only the new checks when needed:

```sh
python test/rpcs3_clock_scale_test.py /path/to/core --benchmark --zig /path/to/zig
python test/rpcs3_clock_scale_test.py /path/to/core --sanitize
python test/rpcs3_descriptor_reserve_test.py /path/to/core
python test/rpcs3_descriptor_reserve_test.py /path/to/core --sanitize
python test/rpcs3_descriptor_reserve_test.py /path/to/core --thread-sanitize
```

## Next optimizations

Validate these sources once with the real Apple SDK before any delivery, then
compare the same restored scenes with the existing counters. Blocking shader
compilation in Assassin's Creed and the texture/SPU cost in God of War III remain
the next device workloads; the attached baseline logs do not measure this patch.

The deeper CPU review found that SPU NEON, persistent objects and per-thread
counters already exist. Skipping more IR work on object-cache hits needs a proof
with the pinned LLVM loader, relocations and a second process before changing that
path. Combining PUTLLC comparison with scans could change observations of
externally writable local storage; blanket DMA `memcpy` would bypass reservation
and overlap protocols. These are research leads, not implemented optimizations.
The current logs do not justify a new NeoSwap pressure policy. No new telemetry,
compatibility setting, precision reduction or iPhone FPS gain is introduced.
