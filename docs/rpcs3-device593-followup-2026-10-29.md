# RPCS3: corrections from the delivered IPA 593 logs

This candidate starts from the RPCS3 Core actually delivered in private IPA
593: source `c143be63f95751616f98d7bf9f1f34f297862df2`, successful Apple run
`40814736023`, canonical patch
`b07952f3b96deb3c446e9b739f29d8f9af9e749695465bd0bfde848ce0cde6f3`.
The application delivery receipt is commit
`571dbc0849caa55c76be797b649c8abf79de5053`. Concurrent MeloNX work on `Claude`
is retained. These are source changes after that delivery; they do not change
the contents or identity of the already delivered IPA.

No new Core compilation, IPA, public release or physical-device performance
result is claimed. No runtime instrumentation or player setting is added.

## Implemented changes

### 1. Correct texture coherence after CPU RSX writes

The CPU implementations of NV308A image writes, NV0039 memory copies and the
NV3089 scaled-image fallback modified guest texture memory without advancing
the iOS texture-validation epoch. A previously successful hash, or a speculative
hash completed by the prevalidation worker, could therefore be reused after
the bytes changed. Flushing the memory protection operation did not invalidate
that content-validation result.

The six successful CPU-write paths now advance the existing validation epoch
after their final writes. The unchanged GPU, failed and no-op paths do not
issue that notification. This restores necessary content checks; it is not a
claim of faster hashing. The change does not disable texture caches or enable
write-color/write-depth buffers globally.

A second bypass existed in the draw path: a texture that was already bound
could skip `upload_texture` entirely, so fixing the validation of a section
alone would not make that descriptor revisit the cache. The candidate also
records a validation stamp for the 16 fragment and four vertex bindings.
Synchronization points invalidate that stamp even when per-epoch hashing is
disabled. Scoped memory writes invalidate only bindings whose guest ranges
overlap, while unknown/tiled ranges take the conservative path.

The binding registry stores addresses and revisions rather than references to
cache sections or Vulkan resources. An unknown range and its revision are
registered under the cache reader lock before lookup. After lookup, the range
is refined from the actual section or composite already selected by the cache,
retaining the original stamp. No additional texture-size calculation is added.
Scoped writers use the exclusive cache lock: an intervening writer either
precedes the lookup or sees the conservative range and makes its stamp obsolete.
Disabled samplers retain their original fast path. Direct render targets retain
their own expiry protocol; composites and transformed local views are tracked
even when labeled `framebuffer_storage`. The existing section content check
remains responsible for deciding whether an upload is necessary. Unchanged,
unrelated bindings retain the fast path.

This is a reproduced texture-coherence defect and a relevant candidate for the
reported BO2 weapon/forearm corruption and Assassin's Creed flickering. The
logs do not identify the rendered texture or shader causing those symptoms;
their disappearance on the iPhone has not been established.

### 2. Select the actual MoltenVK presentation queue

RPCS3 reserves a second Vulkan queue for transfers where one is available.
The delivered encoding-marker path required exactly one captured MoltenVK
queue. With two queues, it returned no presentation ticket and acquisition
fell back to `vkQueueWaitIdle` every frame.

The candidate selects the presentation queue using the exact family and index
passed to `vkGetDeviceQueue`. Queue labels are parsed against the pinned
[MoltenVK 1.4.2 queue-name format](https://github.com/KhronosGroup/MoltenVK/blob/v1.4.2/MoltenVK/MoltenVK/GPUObjects/MVKQueue.mm#L296-L324).
Missing, ambiguous, malformed or overflowing identities
retain the existing conservative fallback. Queue references are retained under
the registry mutex. A presentation marker waits for preceding work on that
queue without waiting for unrelated transfers or work enqueued after it.
Explicit drains and device-lifetime guards remain.

The delivered GoW3 restored-game interval contains **973 full drains for 973
frames**, totaling **2,566.601 ms of aggregate call time**. The same fallback was
already present in the older logs. These observations justify correcting queue
selection; they do not measure how much time the new marker saves on iOS, and
they do not identify this fallback as the cause of the later freeze.

### 3. Reduce successful JIT cache-read I/O without changing generated code

The iOS object reader obtains file metadata once, rejects directories before
reading, and reads compressed objects of at most 4 KiB into a stack buffer with
positional I/O. Gzip footer inspection and decompression use that same snapshot.
Larger objects retain streaming decompression but use positional reads without
repeated seeks. Raw objects reuse the already obtained size. Short reads, gzip
CRC/length checks, output limits and malformed-file recovery remain covered.

A successful cache hit no longer performs a redundant existence probe.
Existence is checked after a failed load to distinguish an ordinary miss from
an invalid cached object. Per-object messages for already preloaded SPU objects
move from notice to trace on iOS; existing aggregate measurements remain.

In the targeted small-object test, successful reads change from **two metadata
queries, two seeks and two reads** to **one metadata query, no seeks and one
positional read**. A 1 MiB streaming case removes all 18 seeks while retaining
the same read count. Warm 3 KiB object medians on the Linux host were:

| Compiler | Delivered reader | Candidate reader |
|---|---:|---:|
| GCC 13.3 | 3.99493 µs | 3.27326 µs |
| Clang 22.1.8 | 3.90431 µs | 3.10110 µs |

These are host filesystem measurements with LLVM buffer adapters. They are not
iPhone timings, decompression-throughput claims or FPS gains. BO2's early second
session records 6,221 object reads and 3,918.311 ms of aggregate read time in
37.293 s; the sum includes work on different threads and is not one long stall.

Only three I/O-related method bodies in `Utilities/JITLLVM.cpp` change. Restoring
those bodies recovers the exact delivered file, including its SHA256. Object
emission, symbol validation, linking and relocation code remain byte-identical.
An exact path-and-hash compatibility alias preserves PPU `a987639e9f838d1c` and
SPU `d070cb361bdef607`. A future synthetic source hash is rejected by the alias
and changes both cache identities, as required. No cache deletion is needed.

### 4. Match queue-submission allocation and destruction

The multithreaded Vulkan command stream allocated a `queue_submit_t` with `new`
and `VKGSRender::renderctl` released it with `free`. The candidate uses `delete`.
The actual production fragments reproduce an allocation/deallocation mismatch
under ASan before the change and pass after it. Submission ordering, fences and
payload ownership are unchanged. This one-line correction also applies outside
iOS. Neither a speed improvement nor a link to the GoW3 freeze is asserted.

## What the existing iPhone results establish

The evidence summary separates sessions, rotated files and repeated snapshots.
The first 3,488 lines of `RPCS3-performance.1.log` belong to build 588 and
Bladestorm; they are not results from the new BO2/GoW3/AC process. The new process
identifies build 593, PID 47785 and Apple A18 Pro. Duplicate diagnostics are not
added to counters. The prior artifact receipt establishes what IPA 593 contains;
the new logs do not provide an independent runtime hash of the loaded binary.

| Interval | Verified observation | Consequence for this candidate |
|---|---|---|
| BO2, second session, windows 7–13 | 6,228 SPU cache hits, 128 misses; 6,221 reads totaling 3.918 s; 128 codegens totaling 1.606 s | Successful cache-read overhead is material; preserve cached native objects. Read time is included in the broader SPU build total. |
| BO2, windows 14–22 | 32 long pipeline creations, 218.876–1,085.744 ms each, 19.926 s aggregate | The I/O change cannot eliminate these first-use Metal pipeline stalls. |
| GoW3, restored session, windows 3–11 | 973 frames, 973 drains; no SPU read/build/codegen or cold pipeline | Correct the queue fallback. Recompilation is not the cause of slowdown in this interval. |
| AC, windows 28–43 | 2,262 frames / 82.778834 s = 27.325826 FPS; no SPU or shader compilation | The sustained limit needs RSX/rendering work, not cache clearing. |
| Same AC interval | 64,721 synchronous submissions, 21.414545 s aggregate; 95.6–97.2% FIFO busy | Submission cost is significant, but some work already overlaps on the RSX offloader; 9.467 ms/frame is not all recoverable serial time. |

Later AC stalls have distinct causes: new fragment pipelines in windows 49 and
57, pipeline relinking in window 55, and SPU reads/codegen in window 58. Treating
the entire run as one sustained compilation bottleneck would conflate those
phases.

During the available AC diagnostics, NeoSwap has two donors, no donor loss and
no mapping failure. Only 18 new maps occur over 132.046 s, requesting about
1.18 MB. The increasing `swap_failures` field counts failed client allocation
attempts, distinct from failures to map guest memory. The observations do not justify another NeoSwap
allocator or memory-threshold change for these stutters.

## GoW3 freeze remains unresolved

The RSX waits at guest label `0x60300510` for `0x71B4` and sees `0x71B3`.
Three complete subsequent windows cover **15.178217 s without frames, draws or
submissions**. They still contain **69,872 successful PUTLLC operations** and
**3,609 completed SPU event waits**. This is partial guest progress, not proof
that every SPU is permanently blocked or that a general notification was lost.
The bounded reservation wait rechecks both the reservation generation and the
128-byte contents.

Comparable one-behind label waits already occurred in builds 583 and 587.
The logs do not identify the guest instruction that should write the missing
value. They therefore do not justify forcing the label, skipping the acquire,
advancing the FIFO or changing its timeout. The proposed
[upstream PR 18913](https://github.com/RPCS3/rpcs3/pull/18913) was closed unmerged;
its [hot-spin premise was disputed during review](https://github.com/RPCS3/rpcs3/pull/18913#issuecomment-4748486239)
and is not observed here. It is not integrated as a supposed freeze fix.

The older and new GoW3 intervals differ in scene, draw load and restore state.
Their average FPS are not an A/B comparison. The earlier BO2 file has lost the
relevant rolling counters. The user's perceived BO2 improvement is preserved
as their observation, without inventing a measured percentage.

## Verification and evidence

New tests compile the affected production functions or headers; their reports
identify adapters and platform limits. Existing native suites are not replayed.

| Check | Verified result | Scope |
|---|---|---|
| JIT object I/O | 95 cases pass with GCC, Clang 22 and ASan/UBSan | Real POSIX I/O and zlib; LLVM buffer/validator adapters; no iPhone execution. |
| RSX CPU writes and bound samplers | GCC, Clang 22, ASan/UBSan and TSan pass; 234 stale content acceptances and 48 stale logical sampler payloads become zero | Production write handlers, binding guards, section sync and prehash rejection; NV3089 conversion and GPU/resource boundaries are modeled. |
| MoltenVK queue registry | 240 checks pass in each of GCC, Clang 22, ASan/UBSan and TSan modes; delivered two-queue failure reproduced | Production registry with a Linux serial-queue adapter; native GCD/Metal pending. |
| Submit-packet lifetime | Six assertions pass with ASan/UBSan; baseline reproduces `operator new`/`free` mismatch | Production allocation, structure and destruction fragments with Vulkan adapters. |
| Cache identities | Real CMake 3.31.10 yields unchanged PPU/SPU IDs; 14 candidate and three baseline alias cases pass | 40 source inputs directly rehashed; unchanged LLVM backend digest explicitly reused from its authenticated receipt. |
| Canonical integration | All 311 postimages reproduce on a fresh authenticated upstream snapshot; all 13 delivered preimages reverse byte-for-byte, including CRLF | 298 delivered postimages unchanged; three existing upstream files newly covered; ABI header and 88 export declarations unchanged. No linked binary built. |

The final RSX harness executes 2,808 CPU writes and 96 sampler scenarios. It
preserves 19,200 unchanged-sampler fast paths and avoids extra lookup/hash/upload
work for 4,000 draws after disjoint scoped writes. Thirteen boundary/provenance
cases and 200 controlled reader/writer interleavings pass. The corrected CPU
write sequence performs 936 hashes instead of 702: the extra 234 checks are the
validations incorrectly skipped by the delivered implementation. This correctness
cost is explicit; the test does not assert a net device performance improvement.

Detailed device observations and the exact host results are in
[`evidence/rpcs3-device593-20261029/`](evidence/rpcs3-device593-20261029/).
The canonical delta and baseline reconstruction are recorded under
`runtime_device593_followup_20261029` in `canonical-source.json` and
`test/fixtures/rpcs3_device593_20261029.diff`.

## Next optimization work

1. Validate the texture-coherence corrections on the exact BO2 weapon scene and
   AC torch scene, and the presentation-queue correction in the existing GoW3
   route. The relevant outcomes are disappearance of the artifact, frame-time
   behavior and preservation of the scene, not merely successful boot.
2. Identify the guest producer of GoW3's missing label value using the same
   reproducible scene/state when available. The current logs narrow the failure
   but do not support a safe semaphore workaround.
3. Work on the demonstrated first-use Metal fragment/pipeline stalls in BO2 and
   later AC. Any scheduling change must preserve shader/layout lifetime and
   avoid moving deferred compiler work onto the active SPU hot path.
4. Reduce AC submissions only after proving which independent command batches
   can be combined without violating uploads, queries, resource lifetime or
   semaphore ordering. Existing aggregate counts do not identify that dependency
   structure. No new automatic async profile or manual settings experiment is
   imposed on the player.
