> Final compatibility decision: the later source audit in `spu-cache-compatibility-review.json` justifies an exact alias to the immediate baseline. It supersedes the provisional no-alias recommendation below; PPU and SPU identities are preserved.

# CPU / MFC corrections — continuation audit

## Delivered changes

The isolated source changes are confined to `rpcs3/Emu/Cell/SPUThread.cpp` and `rpcs3/Emu/Memory/vm.cpp`. No LLVM IR generation, cache compatibility alias, settings, diagnostics, or telemetry has been added. The normal PPU/SPU code-generation identity must be recalculated when the parent integrates these source changes.

### 1. Complete a queued zero-length DMA list without reading local storage

`process_mfc_cmd` already accepts an immediate zero-length list. A list deferred behind a fence or barrier can instead reach `do_list_transfer` from `do_mfc` without that short circuit. The old function then reads its list address and subtracts eight from unsigned zero. The new early return completes that command without reading a nonexistent element. Normal queue draining and tag completion remain in the existing caller.

Upstream RPCS3 independently fixed this case in commit [b225a29a5421faaf76765e69ba5d23d828c8ae9c](https://github.com/RPCS3/rpcs3/commit/b225a29a5421faaf76765e69ba5d23d828c8ae9c).

### 2. Skip a zero-length list element before the RSX inline PUT path

The inline list PUT condition checked nonzero size only for its ordinary RAM alternative. An RSX local-memory address therefore selected the copy path even for a zero-byte element. A destination with bit `0x10` set caused a 16-byte prologue store followed by unsigned size underflow to `0xfffffff0`. Adding `size &&` to the common condition skips that copy. The later stall-and-notify code is retained: a skipped zero-byte element can still stall, and the final element still ignores its stall flag as before.

The [Cell Broadband Engine Architecture v1.02](https://www.cresco.enea.it/LA1/cresco_sp14_ylichron/CBE-docs/CBEA_v1.02_11Oct2007_pub.pdf) explicitly allows zero transfer size and skipped zero-byte DMA-list elements (printed pages 120 and 135–136). Its list-stall description on printed page 63 requires an intermediate stall to be acknowledged and ignores the last element's stall flag. This second condition defect was also still present in the upstream master source inspected during this audit.

### 3. Preserve the selected LS pointer for SPU MMIO DMA

Group SPU DMA uses synthetic effective addresses at `0xF...`. The dispatcher validates the LS offset and selects the target SPU's host LS pointer. Two later paths incorrectly treated that synthetic address as an ordinary guest RAM mapping:

- The accurate 128-byte PUT helper resolves the effective address again, losing the selected host pointer. Accurate PUT's RAM-only path is now entered only below `RAW_SPU_BASE_ADDR`.
- The range-lock slow path checks ordinary page readability after obtaining range exclusion. It now exempts addresses at or above `RAW_SPU_BASE_ADDR` from that ordinary-page test. Overlapping range-lock checks still run before the exemption. All ordinary RAM paths retain `vm::check_addr` and the existing fault handling.

These are the two relevant semantic changes in upstream commit [5935028e1626606ccee26f2b5cfe5052c277a84b](https://github.com/RPCS3/rpcs3/commit/5935028e1626606ccee26f2b5cfe5052c277a84b). The separate upstream cleanup of offset expressions was not needed here and was not imported.

Bounds: a `u32` group effective address produces a group index at most 255 and an offset at most `0xfffff`; command size is `u16`, so `offset + size` is at most `0x10fffe` and cannot overflow `u32`. Existing MMIO validation rejects ranges extending beyond the target LS before any copy. RawSPU invalid MMIO offsets also retain their existing rejection. The permission exemption is not an independent MMIO dispatcher: actual memory accesses still use the selected/mapped host pointer and can fault for unmapped accesses, as before. These changes do not authorize ordinary RAM writes to unreadable pages.

## Verification

All three host harnesses extract the real production bodies from both the immutable baseline and the isolated edited source. The only production-body substitutions are function/class names to compile both versions in one program. Each harness passes in normal mode and AddressSanitizer + UndefinedBehaviorSanitizer mode, with `-Wall -Wextra -Werror`.

| Harness | Verified cases | Result |
|---|---|---|
| Complete `do_list_transfer` and `do_mfc` | 1,536 deferred empty lists | Original touches LS in all cases; corrected version completes without that access and drains tags/fences |
| Same list harness | 512 zero-byte RSX elements | Original makes 512 unnecessary VM accesses and 256 unsigned-underflow copy paths; corrected version makes neither |
| Same list harness | 1,300 nonempty transfer cases for each version; 97 stall/ack cases | Data agrees with the independent copy oracle; stalls and tag readiness remain correct |
| Complete `range_lock`, `range_lock_internal`, and range-lock sweep | 100 ordinary cases, 50 MMIO cases including 25 conflicting locks, 9 unreadable cross-page RAM cases | MMIO no longer causes the artificial page fault; conflicts still wait and unreadable ordinary RAM still faults |
| Complete `do_dma_transfer` | 1,008 grouped PUT cases | 1,008 old address faults versus zero after correction; 75 old atomic-address misroutes versus zero after |
| Same full DMA harness | 1,008 grouped GETs, 672 RAM transfers, 672 RawSPU transfers | Expected bytes preserved; RAM atomic/range-lock path counts agree |
| Same full DMA harness | 240 invalid MMIO offset cases; 12 SNR cases | Invalid offsets rejected before copying; SNR payload/routing preserved |

The detailed commands, source-body SHA256 values, executable-source SHA256 values and outputs are in `evidence/*-result.json`. All final runs report zero failures. `cpu-fixes.patch` is a unified diff against the original canonical postimages now preserved in `rpcs3-baseline`. `cpu-results.json` records file-level before/after hashes and the full evidence manifest.

After parent integration, the portable scripts generated the three harness programs from `rpcs3-baseline` and the integrated `rpcs3-full` candidate. All three SHA256 values matched the earlier passing executions exactly. This final verification generated source only; no unchanged binary was rebuilt or re-executed. The generation reports record `executed: false` in `integration-verified/`.

### Limits of the evidence

The harnesses provide bounded VM, lock, atomic, scheduler and SIMD storage adapters. The 128-byte atomic helper adapter models its address resolution; it does not emulate the helper's actual concurrent implementation. The full range-lock implementation is tested separately with deterministic interleavings. The iOS vector-copy specialization and ARM64 machine instructions are not compiled/executed by these x86-64 host harnesses.

The old zero-element underflow is stopped by the copy adapter after the initial 16-byte store and before the next 128-byte copy; the test does not execute a four-GiB overwrite. That proves entry into the defective path without deliberately corrupting the host test process.

Initial harness compile failures came from adapter declarations only (missing alias / stray template typo for VM; a trivial perf-meter destructor triggering `-Werror` in DMA). Their logs are retained. The first full DMA sanitizer run exceeded its initial 30-second harness timeout without a sanitizer report. The exact same compiled executable and unchanged test set then passed with a 120-second execution allowance; no production body or assertion was changed to get that result. No RPCS3/IPA build was run.

These are correctness fixes demonstrated in production-extracted host tests. No measured FPS gain, iPhone memory reduction, or resolution of the reported BO2/GOW3/Assassin's Creed scenes is claimed. In particular, the historic GOW3 RSX label producer remains unidentified.

## Reviewed alternatives not imported

- A BO2 SPURS HLE WRCH-abort workaround exists in a separate fork. Its affected HLE registrations are disabled in the exact target source, and its caller does not implement the advertised retry. There is no demonstrated active path here, so it was not applied.
- Recent upstream MFC shuffling and SPU-group termination refactors are broader semantic changes without a target-scene reproduction. They were not blindly backported.
- Existing SNR, full-MFC-queue, IRQ-before-acceptance, JIT free-interval and NEON DMA fixes were verified as already integrated. Repeating them would not add an optimization.
- A prospective NEON list-copy rewrite lacks ARM hardware evidence and would duplicate existing native vector copies. No FPS benefit was asserted or speculative rewrite added.

## Next optimization targets

The three reported games still require validation on device against the exact frozen scenes/workloads. For CPU work, the next justified target is the remaining producer path of GOW3's observed missing RSX label increment; the current MFC fixes remove real failure mechanisms but do not establish that connection. The parent's independently tested NeoSwap bulk-trim optimization has also been reviewed for entry lifetime, pin rechecks and accounting: no new defect was found in those areas. Its timing/visit-count evidence is separate from this CPU report.
