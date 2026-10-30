# RPCS3 continuation: DMA correctness, renderer lifetime, texture work and bulk eviction

## Source and delivery status

This source lot continues `Claude` at `de8169848ecfa9c95946fc957861263a9fd1b879`.
Its pinned RPCS3 upstream remains XITRIX/rpcs3
`22f1152783cef1f7e04af7b1c895173e28fd5b03`. The starting canonical patch SHA256 is
`5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8`.
The pre-existing engine changes are preserved in the single canonical delta.

The final canonical patch SHA256 is
`099651cae54c7bc567ff325735acde0cf3e931ed6e25b2b5bbcc14e5f5ecf33b`.
Eight Core files change; the other 311 canonical postimages are unchanged.
The separate native NeoSwap Store is the ninth production file in this lot.
The remote `Claude` head was independently rechecked at the same base at
00:02:36 UTC on 30 October.

The user reported BO2 stutters, weapon/forearm corruption and a crash around
8 GB; a repeatable GOW3 scene freeze; and Assassin's Creed torch flicker and
frequent frame drops around 27 FPS. Those reports motivate the changed paths.
They are not before/after measurements of this candidate. No physical iPhone,
gameplay scene, Vulkan/Metal driver, new Apple Core build or IPA was exercised
for this lot. No push, CI dispatch, tag or release is part of this delivery.
The prior IPA596/Core delivery records remain historical.

The reviewable production changes, portable regression fixtures and exact
evidence are in [the continuation evidence directory](evidence/rpcs3-continuation-20261030/)
and [the source contract](../test/rpcs3_continuation_contract_test.py).

## 1. CELL/SPU: remove invalid DMA work and preserve MMIO dispatch

### Empty lists and zero-byte elements

`SPUThread.cpp::do_list_transfer()` now completes an empty list before reading
list memory. The immediate command path already did this; the deferred path
could read a list element and subtract eight from an unsigned zero size.

The inline RSX PUT path additionally requires a nonzero element size. A
zero-byte element with destination bit `0x10` set could previously execute its
16-byte alignment prologue and wrap the remaining size to `0xfffffff0`.
The correction prevents the copy while retaining the surrounding list stall
notification, acknowledgement, tag and queue semantics.

The source-extracted test executes the complete list-transfer and MFC-queue
functions, before and after the change. It covers 1,536 deferred empty lists,
512 zero-byte RSX elements, 1,300 nonempty transfers per version and 97
stall/acknowledgement cases. The candidate eliminates all observed invalid
list/VM accesses and the 256 old underflow paths. For the old underflow, the
adapter stops after detecting the invalid path; it deliberately does not
attempt a four-gigabyte overwrite.

The empty-list correction is corroborated by
[RPCS3 b225a29a](https://github.com/RPCS3/rpcs3/commit/b225a29a5421faaf76765e69ba5d23d828c8ae9c).

### Grouped SPU local-store DMA

Grouped-SPU MMIO addresses are translated to a target SPU local-store pointer
before copying. The accurate PUT helper must not reinterpret that synthetic
address as ordinary guest RAM. It is now restricted to addresses below
`RAW_SPU_BASE_ADDR`. `vm::range_lock_internal()` also recognizes the synthetic
MMIO range after performing its overlap/conflict checks. Normal RAM permission
checks remain in place.

The complete extracted DMA dispatcher eliminates 1,008 old group-PUT address
faults, including 75 incorrect atomic-helper routes. It preserves 1,008 group
GETs, 672 RAM transfers, 672 RawSPU transfers and 12 signal-notification cases;
240 invalid offsets are still rejected before copying. Separate range-lock
tests cover 100 RAM cases, 50 MMIO cases including 25 conflicts, and nine
unreadable cross-page RAM ranges.

This follows the address-domain correction in
[RPCS3 5935028e](https://github.com/RPCS3/rpcs3/commit/5935028e1626606ccee26f2b5cfe5052c277a84b).
All three CPU harnesses passed normal and ASan/UBSan execution. The atomic
128-byte helper is represented by an address-routing model, not its native
concurrent implementation. These tests do not execute ARM64 instructions or
the iOS SIMD copy specialization. Commands, limits and results are retained in
[cpu-results.json](evidence/rpcs3-continuation-20261030/cpu/cpu-results.json).

### Preserve compatible SPU objects for these host-only corrections

A final source audit proves that `SPUThread.cpp` is byte-identical outside the
two corrected native helper bodies. Translator code, structures, signatures
and constants are unchanged. Generated SPU calls use external symbols; the
current native addresses are registered again through `updateGlobalMapping`
before cached objects are loaded and their relocations resolved. The pinned
[LLVM MCJIT implementation](https://github.com/llvm/llvm-project/blob/ca7933e47d3a3451d81e72ac174dcb5aa28b59d1/llvm/lib/ExecutionEngine/MCJIT/MCJIT.cpp)
stores the unrelocated compiled object, not a previous process's loaded image.

`JITCacheCompatibility.cmake` therefore adds one exact mapping from the new
`SPUThread.cpp` hash `4d138e76…` to the immediate baseline `b9bc0cfe…`.
Unknown hashes and other inputs still invalidate normally. This preserves
PPU identity `a987639e9f838d1c` and SPU identity `477a3fa442d27917`; without
this narrowly justified mapping the SPU identity would become
`b7f2660b046076f6`. It avoids unnecessary invalidation of existing compatible
objects under the same other cache-key inputs. It is not an on-device object
replay benchmark or a measured startup-time result.

The [compatibility review](evidence/rpcs3-continuation-20261030/cpu/spu-cache-compatibility-review.json)
supersedes the initial CPU handoff's provisional no-alias recommendation.
Forty physical codegen inputs were checked; the unchanged external LLVM
frame-lowering input uses its previously locked digest and was not
materialized. No older pre-baseline identity is admitted by this new mapping.

## 2. RSX: honor late shader invalidation

`VKGSRender::load_program()` captures shader invalidation before the program
resolution helpers consume the flags. Its equal-fixed-state shortcut now
requires the programs to be unchanged as well.

This is a reachable stale-program bug: `begin()` may keep the old native
pipeline when only fixed state is dirty, then `load_texture_env()` discovers a
different host texture format and invalidates the fragment program. Equal
fixed pipeline properties previously allowed the old native shader to remain
bound despite that later invalidation.

The extracted production methods show 112 stale selections in a 4,608-state
matrix before the correction and zero afterward. A 20,000-draw sequence has
13,333 mismatches before and zero afterward. The actual late-invalidation
ordering also passes, while the tested clean paths perform zero additional
cache lookups. Both normal and ASan/UBSan candidate runs passed.

The equivalent invariant appears in RPCS3's newer state architecture in
[b4d4e2bd](https://github.com/RPCS3/rpcs3/commit/b4d4e2bd7d8d0bdc37cfdf1b5e7d06867704abec).
The harness models shader resolution and cache lookup; it does not render the
reported BO2 weapons or Assassin's Creed torches. The visual effect in those
games remains unverified.

## 3. Vulkan: preserve ownership until successful completion

`command_buffer_chunk::wait()` now checks `wait_for_fence()` before resetting
the fence, publishing an event completion, restoring heap snapshots or
marking the chunk reusable. Failed waits enter the existing Vulkan exception
path. The existing wait duration is unchanged.

The test extracts the complete chunk type, `command_buffer::reset()`,
`frame_context_cleanup()`, `wait_all()` and the pinned `die_with_error()`
implementation. All 36 injected failure cases previously violated retirement
invariants; none does after correction. The 12 success/interleaving checks
remain valid. The candidate has an ASan/UBSan execution receipt; no separate
unsanitized candidate execution is claimed for this harness.

This is an ownership correction, not a recovery algorithm for a stalled
producer. It follows the same requirement as
[RPCS3 3e4df518](https://github.com/RPCS3/rpcs3/commit/3e4df51852ae1e4ec9ea2c8529e205d080ccf67b).
The newer upstream recovery architecture was not transplanted into this fork.

### Reuse the command buffer's owned fence for texture DMA

The synchronous DMA cleanup path now submits with the command buffer's existing
fence, waits for it with the same timeout, and calls `begin()` only after
success. The existing `begin()` recycles the completed fence and resets the
buffer. A failure retains the pending state and the fence's owner; it cannot
destroy a still-submitted local stack fence. This also removes a Vulkan fence
creation and destruction from each affected readback. The asynchronous branch,
semaphore wait stages, occlusion-query restoration, event tags and heap
snapshots are preserved.

`imp_flush()` also checks its event wait before reading or flushing the DMA
result. Its event already has persistent ownership.

One comparative ASan/UBSan execution extracts the complete affected methods,
command-buffer lifecycle, fence constructor/destructor and `flush_all()` lock
scope. Per version it covers 32 fence-failure cases, 32 event-failure cases and
20 success cases. The old path has 24 pending-buffer resets, 24 pending-fence
destructions and eight premature readbacks; the candidate has none. Eight
successful affected readbacks create/destroy eight temporary fences before
and zero afterward. The post-success `begin()` observes the already completed
fence and does not wait again for pending work in these cases. Lock release,
query flags, tags and snapshot sentinels remain valid. These are API/lifetime
counts, not GPU timing or full driver-recovery proof.

## 4. Textures: release retired memory and avoid provably redundant work

### Prompt release under memory pressure

On iOS, detached recyclable images that have already passed GPU retirement are
destroyed directly after releasing both the pool and cache locks. Previously
they were sent through deferred disposal a second time, retaining their
allocations until a subsequent event completed. Active temporary textures
continue through the normal deferred-release path.

The final lifetime harness performs 6,429 checks, including 1,000 late driver
returns to the pool. In its explicit allocation model, the 256 MiB retired
batch is released and the 2 MiB active allocation remains retained. The old
path retains both. These numbers describe modeled allocation lifetime, not an
iPhone resident-memory measurement or a demonstrated resolution of BO2's
reported 8 GB crash.

### Skip clears only for complete small 2D atlases

Before clearing a color atlas, a bounded helper proves whether the destination
rectangles of up to eight copies cover the complete image. It evaluates their
union across at most 18 Y boundaries without allocating scratch memory.
Overlaps cannot hide gaps. Larger sets, empty/out-of-bounds regions, non-color
images, layers/mips, missing sources and source-equals-destination cases keep
the existing fallback. Copy order, image transitions and barriers are retained.

An independent texel painter checks 84,000 layouts and 694,279 assertions. The
candidate omits 22,263 redundant clear calls in that synthetic set; the other
61,737 clear decisions remain unchanged. Fourteen explicit unsafe cases fall
back and the helper allocates no heap memory. This proves omitted API work,
not its timing on MoltenVK or a percentage of real game frames.

### Texture arithmetic

Unnormalized 3D/cubemap depth scaling now occurs after the dimension switch has
assigned and validated `attributes.depth`. Previously that field was still
zero. In 69,120 configurations, 15,120 incorrect scales become zero mismatches;
1D/2D behavior and zero-pitch sampling are preserved.

Atlas coverage volume/percentage calculations use 64-bit arithmetic. Even
ordinary dimensions such as `256 × 256 × 512 × 90` exceed signed 32-bit range.
The existing 90/99-percent heuristic and overlap rules are preserved. The
117,756-case comparison detects 11,591 old decisions that disagree with the
wide oracle and preserves 99,928 cases whose entire old computation fits.
The candidate passes ASan/UBSan; a separate baseline probe reproduces signed
overflow. The four texture scopes have normal and sanitizer receipts, with
their extraction boundaries recorded in the texture report.

## 5. NeoSwap: batch victim selection during large purges

`native/neoswap-storage/Store.cpp::trim_to()` keeps the existing scan for the
first eight evictions. A larger purge builds and sorts a preallocated candidate
array once, ordered by cold/hot priority, age and original traversal ordinal.
This avoids scanning the entire entry map for every subsequent victim in
unpinned bulk cases.

Pinned candidates are included in the ordered set and their lease counts are
rechecked on every selection. A lease released outside the Store mutex can
therefore become eligible again. The mutex still protects entry ownership,
age, heat and accounting. Persistent pinned candidates can still require
repeated scans; no unconditional worst-case complexity improvement is claimed.

Metadata is reserved at Store construction: 16 KiB for the default 1,024
entries and 64 KiB at the 4,096-entry limit on the tested 64-bit host. No
allocation occurs inside the tested trim operations. The source-extracted
comparison covers 2,400 states, 12,000 purges and 16 controlled dynamic unpin
scenarios per mode. Selection visits fall from 46,712,043 to 14,367,269 while
the checked victim order, data, return values and statistics remain equal.
The controlled interleavings do not prove identical observations under every
possible simultaneous lease-release schedule.

The complete real POSIX Store suite also passes normal and ASan/UBSan runs,
covering disk round trips, working sets larger than managed RAM, compression,
lease safety, pressure, read/prefetch priorities, quotas, short I/O, ENOSPC,
sync/read failures, corruption, truncation, concurrency, teardown and extent
reuse. LeakSanitizer is disabled and is not claimed.

The benchmark uses seven alternating samples per workload on the host, timing
the extracted production trim method. These are not game frame times. The
complete matrix, including slower small-purge results, follows below; raw
samples and commands are in
[neoswap-bulk-plain.json](evidence/rpcs3-continuation-20261030/neoswap-bulk-plain.json).

| Entries | Evictions | Before median (µs) | After median (µs) | Time change |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 0 | 0.056 | 0.048 | -14.59% |
| 16 | 1 | 0.151 | 0.144 | -4.67% |
| 16 | 4 | 0.312 | 0.299 | -4.11% |
| 16 | 8 | 0.502 | 0.505 | +0.72% |
| 16 | 8 | 0.499 | 0.503 | +0.79% |
| 16 | 16 | 0.867 | 0.751 | -13.34% |
| 128 | 0 | 0.678 | 0.650 | -4.18% |
| 128 | 1 | 1.009 | 1.010 | +0.08% |
| 128 | 4 | 1.960 | 1.934 | -1.33% |
| 128 | 8 | 3.292 | 3.167 | -3.79% |
| 128 | 64 | 21.064 | 6.472 | -69.27% |
| 128 | 128 | 38.208 | 8.246 | -78.42% |
| 1,024 | 0 | 3.872 | 3.799 | -1.88% |
| 1,024 | 1 | 7.216 | 7.211 | -0.07% |
| 1,024 | 4 | 17.064 | 17.118 | +0.32% |
| 1,024 | 8 | 37.647 | 37.056 | -1.57% |
| 1,024 | 512 | 1759.910 | 62.179 | -96.47% |
| 1,024 | 1,024 | 3354.490 | 75.222 | -97.76% |
| 4,096 | 0 | 13.512 | 13.754 | +1.79% |
| 4,096 | 1 | 27.718 | 27.579 | -0.50% |
| 4,096 | 4 | 67.815 | 69.976 | +3.19% |
| 4,096 | 8 | 124.663 | 125.928 | +1.01% |
| 4,096 | 2,048 | 28149.200 | 287.657 | -98.98% |
| 4,096 | 4,096 | 58581.100 | 356.815 | -99.39% |

An earlier four-victim crossover was rejected after 13–36% regressions in
eight-victim workloads. The retained threshold is eight. The final small-purge
matrix still includes slower medians, up to approximately 3.19%; a universal
speedup is not claimed.

## Reproducibility and verification limits

The final source contract authenticates the canonical postimages, the exact
new source delta, frozen test inputs and the inverse reconstruction of the
starting files. It regenerates harnesses and compares their hashes to already
executed programs, without recompiling unchanged code. A fresh materialization
from the pinned upstream checks the canonical patch and all postimages once.
See [the test instructions](../test/rpcs3_continuation/README.md).

The completed [source-contract result](evidence/rpcs3-continuation-20261030/source-contract-result.json)
verifies 89 frozen repository/evidence inputs, all 319 canonical postimages,
the eight-file inverse delta, ten generation jobs and the NeoSwap program.
The [fresh materialization result](evidence/rpcs3-continuation-20261030/materialization-result.json)
also verifies the host-loaded export contract. Canonical application reports
five pre-existing whitespace warnings. The authored source diff passes the
scoped whitespace check; stored patch context, raw generated programs and
authenticated upstream fixtures retain their exact tested whitespace and are
excluded from that style-only check. The first generation-only contract attempt omitted the
unchanged VM locking header from its temporary baseline. Adding that verified
support input allowed the complete contract to pass; no production code or
native test expectation was changed for that correction.

Two preliminary complete-Store builds with `-Werror` stopped on existing
test-only unused-result warnings. The final build uses the suite's established
warning policy; the extracted trim harness retains `-Werror`. A first Store
invocation supplied a relative cache directory and was corrected to the
required absolute path. The first complete-DMA sanitizer execution hit its
30-second harness timeout without a sanitizer finding; the same unchanged
binary passed with a 120-second limit. These development incidents are not
misrepresented as product failures or successful earlier runs.

The NeoSwap execution JSONs originally recorded the Store and generated
harness hashes but not every included header/test source. A separate
[input attestation](evidence/rpcs3-continuation-20261030/neoswap-bulk-input-attestation.json)
records the current inputs and their equality to the baseline Git objects.
It does not retroactively claim that missing hashes were recorded during
execution. Future runner results include the local include closure and verify
it remains unchanged across the run. System headers and resolved library
binaries are not a hermetic toolchain snapshot.

## Next optimizations and remaining game checks

1. **GOW3 producer progress.** Existing evidence has a wait at RSX label
   `0x60300510`, expecting `0x6f0e` while observing `0x6f0d`. The missing
   increment's producer is still unproven. Follow the known command/MFC path
   through that scene; do not force the label, drop barriers or substitute a
   timeout for correct ordering. Reuse
   [the existing MFC audit](evidence/rpcs3-deep-audit-20261029/gow3-mfc-audit.md).
2. **One authorized Apple integration build, then the same scenes.** Compile
   this exact source and verify BO2 weapons/forearms, Assassin's Creed torches,
   the GOW3 freeze point, warm frame times and memory behavior on device.
   Source hashes and host models do not establish these outcomes.
   The historical Apple/deep-audit receipts retain their original inputs. A
   future build must run the continuation source contract and account for the
   affected new native checks before using the existing Core recipe; an old
   successful receipt must not be relabeled as validation of this lot.
3. **Further vertex/cache and native code work.** The next justified renderer
   target is the weak vertex-fingerprint/coherency path if the reported weapon
   corruption remains. Further LLVM/ARM64/NEON work should be tied to an actual
   costly emitted sequence or producer bottleneck in the existing evidence;
   the previous validated lowering and JIT work is preserved here. Full-buffer
   hashing, changed floating-point semantics or extra parallel compilation
   must not be introduced without showing their correctness and cost.

No FPS increase, solved game-specific crash, resolved GOW3 scene or reduced
iPhone resident-memory peak is asserted by this source lot.
