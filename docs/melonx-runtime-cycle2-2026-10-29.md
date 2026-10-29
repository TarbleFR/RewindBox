# MeloNX runtime optimization, second cycle — 29 October 2026

Source baseline: `Claude` at `075d84a49e3540cdae5352908fd81bc411b78942`.
Latest delivered application: private IPA588, engine `7be2a83b`, RPCS3 Core592.
All earlier optimizations remain. This cycle adds seven changes, with no new
player option, telemetry, GC knob or application diagnostic.

## Device evidence and identity limits

`app(20261029-022732).log` contains two Hogwarts Legacy v1.0.5 sessions
(`0100F7E00C70E000`) in the same process: asynchronous shaders on, then off.
Both use 1x resolution, backend threading, standalone MoltenVK, a 1 GiB JIT
arena and 4 GiB of donor memory. Median positive, unpaused game FPS is 3.1
in each. During the slow positive-FPS seconds, visible background-GC CPU
medians are 54.5% and 54%; GPU-emulation-thread medians 61% and 55%.
The top-six list is censored; absence of a thread is not zero CPU use.

The process retains at least 2,397 MiB of headroom. Device available memory
never reaches the existing 7% trim trigger; the recorded GPU caches are small
relative to their caps. Short approximately 30 FPS phases occur at similar
device availability, so a memory-percentage threshold alone is not the cause.
Neither session reproduces a crash or stuck close. No Persona 4 session is
present. The log includes no application build or engine SHA: it cannot prove
that IPA588 was installed or establish a regression against engine7be.
Scenes and durations differ; shader-mode averages are not a controlled A/B.

Only sanitized aggregates and the input digest are committed:
`evidence/melonx-runtime-cycle2-2026-10-29/device-log-summary.json`.
The raw user log is not published.

## Implemented changes

| Change | Production path | Verified host result |
| --- | --- | --- |
| Targeted JIT dataflow propagation | `LightningJit/Graph/DataFlow.cs`: visit only affected dependencies, hoist fixed predecessor masks, calculate a single-block unit directly. Bounded stack/pool scratch is returned on failure. | 25,288 equivalent graphs, including 5,000 real Block graphs. 2,000 fragments emit exactly the same 64,085,248 ARM64 bytes with a shared real function table. Corpus compile time 825 to 709 ms on this host; timing is indicative. |
| Expire cold upload-pool primaries | `MemoryOwner<T>`: extend the existing 3-second idle window to primary arrays, which previously had no timed expiry. Leased arrays are never trimmed. Linear in-place compaction avoids repeated shifts under the pool lock. | 32 cold lengths retain 35,586,048 bytes before expiry in the control, zero in the candidate. A 1,000-length interleaved hot/cold case preserves sorted hot data. Existing 24 pool/FIFO checks pass against the final pool. |
| Reuse slow-format comparison snapshots | `Texture.SynchronizeFull`: copy changed source bytes into the private snapshot when its length matches; replace it with an exact new length otherwise. | 128 changed 1 MiB snapshots: 134,220,800 allocated bytes in the control, zero after initialization in the candidate. Unchanged data still skips upload; resize and native-format paths are preserved. |
| Lease fragmented guest texture data | `PhysicalMemory`, `Texture`, `TextureGroup`: borrow contiguous spans; otherwise rent a private conversion snapshot and return it through using/finally. Clear holes and short-read tails only, preserving the old zero-filled-array behavior. | 192 full/partial fragmented uploads: 201,353,728 to 28,672 allocated bytes. 219 rents/219 returns, including read/conversion failures. Payload, tracking, holes, short/empty guest spans and early returns checked. |
| Reuse fenced native texture storage | `TextureView`, `BufferManager`, `StagingBuffer`: lazy dedicated 16 MiB texture ring, independent of vertex/buffer staging. Full, large, NPOT and failed-allocation cases retain temporary buffers without waiting for ring space. | 1,024 uploads: 1,024 native buffers to one persistent ring. 4,098 uploads with ring saturation: 4,098 to one ring plus two temporaries. 16 payload hashes agree across mips, layers, 3D, compression, subrects and depth conversion. |
| Correct nonzero buffer-offset copies | `TextureView.CopyFromOrToBuffer`: size is a remaining byte count, independent of the backing-buffer offset. Both upload and public CopyTo paths use the correct bounds. | Offset512/byte-count1280 case: zero copied mips in the control, two correct mips after correction. |
| Preserve worker pipeline cache work | `PipelineCacheManager`: merge a retiring worker into the main cache under its creation lock when premeasured sizes fit the existing snapshot budget. Keep an accepted/successfully written worker checkpoint when its replacement has seen no new compilation attempt. | Real manager/file I/O with Vulkan doubled: successful unions persist, old handles retire, valid checkpoints survive empty replacements, rejected snapshots remain replaceable, failed merges and insufficient-space cases keep the old bounded recycle behavior. |

The JIT fixture's adverse 1,000-block graph performs 5,002 edge reads rather
than 2,008,000. This is algorithmic evidence, not a game-speed claim. Four
failure injections verify scratch return, including failure of the second rent.
The single-block path removes two temporary register-mask arrays.

The shader-cache opportunity is visible in session1: worker0 checkpoints
31.34 MiB, then recycles at 69.06 MiB. Previously, its post-checkpoint work
was destroyed without entering the main cache. No claim is made that every
byte was a unique new shader or that all compilation pauses came from this.

## Ownership, regression checks and tradeoffs

- A first shared-ring experiment displaced a subsequent vertex upload into
  `FlushAllCommands` in the mixed-load test. It is not shipped. Dedicated
  texture staging keeps the original buffer ring untouched and costs up to
  16 MiB additional retained native storage per renderer after first use.
- The optional ring may fail while a small temporary buffer still fits.
  Null allocation and Vulkan host/device OOM use that fallback, with no
  repeated ring attempt during the session. Device loss and unexpected
  errors still propagate. Repeated disposal releases both rings once and
  leaves no fence references in the harness.
- Expiry can require reallocation if an array is used again after 3 seconds.
  Hot reuse and active leases are preserved. No forced collection or global
  GC configuration change is introduced.
- Fragmented input leases end only after synchronous conversion has produced
  an independent output owner for the asynchronous renderer. The original
  unowned GetSpan API remains for its other callers. The change does not
  introduce a guest mapping lease or claim to solve concurrent unmap races.
- Pipeline cache data is opaque: sum of sizes is an admission estimate, not
  a hard live-memory cap. Actual size is measured after merging. Overshoot
  prevents further preservation admissions; the existing refusal to persist
  an oversized main snapshot remains. A fake driver that grows beyond the
  estimate is covered. Budgets remain unchanged, and the main cache is not
  replaced while callers could have captured its handle.
- Independent review found and resolved the shared-ring wait displacement
  and optional-allocation failure cases before publishing this candidate.
  Dataflow equations, ownership, short reads, failure cleanup and cache
  lock order were reviewed independently.

## Validation and next priorities

The new behavioral/codegen receipts and their exact input digests are in
`evidence/melonx-runtime-cycle2-2026-10-29/`. The full pinned engine adaptation
chain and Release managed embedded-library build pass on .NET10.0.100/Linux.
These test-only managed/Linux build switches do not change the iOS project.
The production engine workflow runs the new targeted tests before NativeAOT.

No iPhone gain is measured. These results establish reduced allocations,
native allocation calls and compiler work on host paths, not whole-process
RAM reduction, FPS improvement or visual compatibility on a physical iPhone.
Saves, caches, imports, audio, controller behavior, donor/JIT ownership,
the standalone MoltenVK choice, RPCS3 Core592 and other engines are preserved.
No application build number, IPA or public release is created by this cycle.

Next: compare the candidate on existing equivalent Hogwarts and Persona4
scenes, with retained caches; assess the dedicated-ring/idle-expiry tradeoffs
using existing frame and memory measurements. Further changes to read-back
mapping lifetimes or JIT compile deduplication require their own ownership
and concurrency proof. Do not remove synchronization or recycle JIT arenas
merely to shorten waits.
