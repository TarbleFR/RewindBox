# MeloNX engine optimizations — 29 October 2026

Reference: `Claude` at `67e0c010`, delivered private IPA 587, engine
`b2a28defbeafe67addf7b2d295ffd928b39e91ea`, upstream MeloNX
`13700519f3abc4e6d7ed8a065b118b2cc59bcd67`, .NET 10.0.100.
The baseline engine artifact SHA-256 was independently checked:
`f284dd5ce66d11761e0491d91dd83461a1e5ec7d028683c7b5dd05a07315b2d5`.
The changes below are new source changes, not contents of the attached IPA 587.

## Implemented

| Path | Change | Verified scope and result |
| --- | --- | --- |
| LightningJit context transfers | Adjacent live NEON Q slots use LDP/STP; individual transfers remain for holes or unencodable offsets. | 120,246 mask/offset cases, real assembler words independently decoded. Full Q context: 32 to 16 load instructions and 32 to 16 store instructions. Same slots, masks, 128-bit contents and ABI. Generated ARM64 was not executed. |
| LightningJit block partition | Linear merge of sorted targets and ordered blocks; each resulting instruction range is copied once. Unusual/wrapping/unaligned layouts keep the previous algorithm. | 10,405 layouts compare instructions, flags, masks and control-flow links. Dense 2,048-instruction/511-target fixture: 21,208,760 to 188,704 allocated bytes; external-target scans also reduced. Host fixture, not a game benchmark. |
| LightningJit code reader | Keep two code pages during a translation, so loop look-ahead does not evict the page being decoded. Reset both for each translation. | 16 boundary/invalidation checks; 2 page copies for 2,000 alternating reads. Additional retained storage: 4 KiB per decoder thread. |
| Vulkan texel-buffer views | Compare the actual BufferHolder when the global buffer generation changes. Keep a view if its own buffer, range and format remain valid. | Complete TextureBuffer with Vulkan boundaries doubled: 513 to 1 view creations in 512 unrelated-buffer events. Recycled handles and changed ranges invalidate correctly. |
| Pipeline snapshots | Dirty generations replace byte-size equality; skip repeated clean merges/exports, retain shared snapshots, retry failed merges/saves, and mark rejected input dirty. | 16 checks using the real manager and real file I/O, Vulkan doubled. Same-length changed blobs persisted; failed saves retried; rejected snapshots replaced. |
| GPU upload pool | Retain holder and detached list nodes with the leased array; reuse empty per-length lists. Existing byte cap, expiry and eviction policy remain. | 16,000 reused uploads: 177 to 32 auxiliary allocated bytes per operation. This is pool bookkeeping, not total upload memory or process footprint. |
| Command FIFO | Return prefetched rented arrays in finally, and drain queued rented entries only after guest/render shutdown. | 24 combined pool/FIFO checks, including exceptions, concurrency, no-prefetch and timer/lease ownership. Negative control lost both returns; candidate returns 8/8 across tested failure/stop cases. |
| GPU memory range checks | Carry the previous next-PTE through the contiguous-range loop rather than reading it again. No persistent mapping cache. | 100,035 equivalent range results. A 512-page contiguous range uses 512 instead of 1,023 PTE reads. |
| Native controller snapshots | Copy buttons and sticks with one state lock; leases use that atomic snapshot and return neutral state after disconnect/close. | 31,034 input/ownership checks including randomized equivalence and concurrent reset. One acquisition instead of 29 per snapshot. |
| Native vibration packets | Pass the unchanged packed unmanaged payload from stack storage to the synchronous callback. | Payload contents and managed-copy lifetime checked in the input suite; no AllocHGlobal/FreeHGlobal per packet. |
| Program creation queue | Once all eight compile slots are occupied, permit SpinWait's bounded 1 ms sleep while polling for the first free slot. Do not block on one arbitrary compile or increase the concurrency cap. | Real queue: about 1.63 million to 904 backend polls during the controlled 100 ms wait; same admission order and one creation per request. Host scheduling result, not frame-time evidence. |
| Shader teardown | Cancel all undemanded queued cache warm-ups before the renderer's first wait. Handle late module completion/enqueue; running and demanded work still joins. | 19 checks execute the real scheduler, shader methods and renderer close prefix. 128 queued speculative warm-ups cancelled; late continuations and active/demanded ownership covered. |

## Validation and boundaries

- The existing full decoder/compiler regression suite passes with all three
  CPU adaptations applied together to the real CPU/ARMeilleure/Memory projects.
- Full `prepare_embedded.py` runs against the pinned source, records the new
  adapters in `embedded-inputs.json` and includes their actual adapted files.
- Release managed builds cover the real Vulkan, GPU and complete embedded
  library. Linux library compilation disables publishing/NativeAOT and uses
  the unchanged, verified source-built LibHac package from the baseline artifact;
  these test-only switches do not change the production project or runtime knobs.
- Behavioral checks, their input digests and compilation receipts are retained
  in `docs/evidence/melonx-engine-optimization-2026-10-29/`.
- The engine CI includes the new targeted checks before NativeAOT publishing.
  Existing unchanged framework, firmware, key and dependency proofs remain reusable.
- Independent code review found no blocking defect. It prompted the rejected
  pipeline-snapshot test and verification of late warm-up enqueue ordering.

Apple build completed successfully in run
[40794453036](https://github.com/TarbleFR/RewindBox/actions/runs/40794453036)
at commit `7be2a83bd2b5b6938560c520783584f9b8e9e9ff` (15 min 19 s end to end;
15 min 16 s for the job). All new behavioral checks passed on the Mac runner;
NativeAOT compilation produced both iPhone and ARM64 simulator libraries.
The actual simulator engine passed two homebrew initialization/session/close
cases. This smoke test does not test game rendering or guest JIT performance.
Independent download verification checked the archive digest, both Mach-O
ARM64 platform commands and binary digests, 47 required exports in each
binary, all 57 adaptation input digests and 12 groups of adapted-source
markers. Exact identities and limits:
[apple-native-build.json](evidence/melonx-engine-optimization-2026-10-29/apple-native-build.json).

No new player setting, application telemetry or diagnostic was added. Existing
bindless fixes, title-specific JIT arena, RAM donor ownership, memory-pressure
trimming, saves, imports, audio timing, MoltenVK selection and other engines are
preserved. Standalone parity for threading, MoltenVK, presentation and controller
ownership was already present; it is not counted as new work here.

There is no new iPhone gameplay measurement. No FPS, crash-disappearance or
whole-process RAM result is inferred from these host checks. Hogwarts Legacy and
Persona 4 use the common changed paths; neither is claimed fixed on an iPhone.
No new IPA number or public release is created by this source task.

## Next priorities

1. Execute the emitted NEON transfers in a dedicated native context check and
   compare the combined engine in existing equivalent Hogwarts/Persona scenes
   on iPhone with retained caches. Apple compilation and simulator session
   checks are complete; perceptible gameplay benefit remains to be measured.
2. Investigate remaining read-back ownership across guest unmap/remap. A plain
   mapped-range check cannot provide a lifetime lease; preserve GPU ordering
   rather than removing waits without proof.
3. Examine real Metal pipeline compile serialization and texture revalidation
   using the existing measurements. Descriptor mirrors, feedback and write-back
   hazards rule out blindly skipping validation or increasing worker counts.

Primary API contracts checked during review:
[Vulkan cache data](https://docs.vulkan.org/refpages/latest/refpages/source/vkGetPipelineCacheData.html),
[ArrayPool return ownership](https://learn.microsoft.com/dotnet/api/system.buffers.arraypool-1.return).
