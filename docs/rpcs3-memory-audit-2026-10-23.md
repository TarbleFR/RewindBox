# RPCS3 memory and ARM64 audit implementation — 23 October 2026

Requested implementation of the attached ten-page audit. Work starts from
RewindBox `932e4a9f12cf79772edc212fe615565736276e63` on Claude, in an isolated
checkout. XITRIX `22f1152783ce` and the single canonical delta remain the source
of the Core. Existing motion/frontend work, MeloNX and other engines are outside
this change. No main update, public release or tag is authorized.

| Finding | Implementation and limit |
| --- | --- |
| F1 | Gzip streams into the final LLVM-owned buffer with 64 KiB input scratch, exact output length, CRC/trailer verification, full reads, and explicit 256 MiB object/file bounds. Corrupt/truncated/trailing data cannot reach MCJIT. No compressed vector or final full-object memcpy. |
| F2 | Nanosecond mtime/ctime, device/inode, size and actual selected path identify validated PPU objects. A bounded 4096-entry index avoids repeat validation; at most 32 MiB of immutable object bytes can transfer directly to the linker. File mutation rejects reuse, parsing remains before execution, and pass exit releases retained buffers. |
| F3 | Minimal-object linker prototype validates architecture, entry and every symbolic external binding before engine mutation. The ARM64 two-process fixture tests external helper/data relocation without rebuilding IR bodies. Production SPU does **not** use this prototype: real-title helper/patchpoint registry coverage and gameplay proof are still required. |
| F4 | Memory samples inside compilation phases and approximately every 100 ms while LLVM is active; a shared throttle bounds expensive kernel queries across all hooks. Expensive per-thread sampling remains at 500 ms. JITMEM records observed footprint/headroom, active compilations, cache reuse, texture-hash work and VMA bytes. These are sampled observations, not exact instantaneous peaks. |
| F5 | PPU fragments and SPU compilations borrow the same host NeoSwap compiler coordinator. Actual headroom is checked before each admission; observed costs by guest-module size refine a stated conservative initial estimate. Explicit thread settings cannot bypass admission; one oversized module can proceed exclusively. Cancellation wakes/polls waits, committed LLVM work completes normally. File preparation is serial while fragment workers remain parallel, replacing the iOS file-size-times-2000 admission heuristic. Compiler promises reserve room in NeoSwap and wake its existing utility pass; speculative donor growth defers. Older hosts have a serialized fallback. |
| F6 | MADV_FREE advice only for complete, wholly free pages of non-executable data allocations. Shared boundary pages remain live. Arena addresses persist, allocation/reuse is zeroed, and code/RX/RW aliases are never purged or remapped. Counters mean successful advice, never RAM demonstrably reclaimed. |
| F7 | JITPAGES records title, footprint/headroom and arena observations before/after preparation and after stop. Existing live/free/largest-free/peak code/data metrics remain. Capacities are preserved pending device measurements; neither a global capacity reduction nor a forced 1 GiB arena is introduced. |
| F8 | Isolated fault-before-reservation portion of XITRIX b3d84f2d. Both PPU and precise SPU resolve protected write faults before owning the reservation and recheck time/data afterward. Existing NeoSwap, writer-lock prechecks, FIFO, fault-handler and savestate contracts remain. |
| F9 | XITRIX 34c5cf87 small-heap allocation policy: 32 MiB VMA blocks only for a reported device-local heap greater than zero and no larger than 4 GiB. Larger heaps keep VMA's default. Block bytes, useful allocation bytes and retained slack are observed separately; existing soft pressure policy remains. |

## ARM64/NEON and research recommendations

The actual selected LLVM CPU, detected CPU, target features and both internal
triples are logged. GHC, the pinned AArch64 spill fix and the x18-reserving
triple are preserved. No optional hardware feature is forced, no global
fast-math/FMA rewrite is introduced, and PPU EarlyCSE/Extended remain existing
selectable comparison modes. Texture hash byte/tick observations supplement the
existing SPU block profiling and LLVM phase profiles. Further hot-block NEON
rewrites require actual title traces and equivalence evidence; this change
makes no unmeasured instruction-count or FPS claim.

MFC countdown-series changes, unrelated FIFO trimming, generic eviction of
active guest/JIT pages and a direct Metal backend are not blindly imported.
The audit classifies them as dependent research or explicitly advises against
that shortcut. Deferred SPU compilation remains disabled.

## Validation and device protocol

`test/rpcs3_memory_audit_test.py` executes production gzip helpers, allocator page
selection, shared coordinator, actual compiler admission/cancellation and phase
sampling, and the actual PPU/SPU fault preludes with an injected reservation
change. With the LLVM SDK it also executes the production validated-object
window and the minimal-object ARM64 relocation prototype in two processes.
ASan/UBSan cover portable cases. LeakSanitizer cannot inspect `/proc` in the
local Linux sandbox; only that platform's leak pass is unavailable. The macOS
proof and iPhone Core build use the actual SDK and pinned LLVM dependency.

Historical Build 499 negative controls retain their full-file reference hashes:
the test undoes only the exact independently tested admission/fault-order edits
before reconstructing its pre-499 control. Its masks, branch and diagnostic
snippets execute from the current source. The Build 444 ownership assertion now
checks direct bounded output rather than the retired intermediate vector.
No assertion is removed to permit a failing Core.

Physical acceptance still requires the same legal title/update, firmware,
settings and thermal state across cold cache, warm cache and a second title.
Use God of War III, Fallout 3 and Bladestorm as suggested by the audit; compare
actual guest frames and p95/p99, PPU/SPU/RSX CPU time, JITPROF/SPUPROF,
RANGELOCKPROF, JITMEM/JITPAGES and post-stop footprint. Internal app logs suffice.
No game, firmware, key or device performance result is bundled or invented.

Build/run receipts are added only after their respective checks complete.

The first remote candidate 1956f35 / run 39868419517 passed the actual AArch64
minimal-object two-process proof, bounded ownership/mutation checks, compiler
cancellation, fault-order excerpts, shared-budget tests and the 35 LLVM kernel
comparisons. It stopped before the iPhone build at the historical Build 487
whole-interface freeze. The exact JIT API declarations, reviewed JITLLVM ownership/cache delta and
independently tested admission prelude are reversed for that old reference;
full historical hashes remain mandatory. Subsequent source also throttles
kernel memory queries across phase hooks and the sampler to approximately 10 Hz.
