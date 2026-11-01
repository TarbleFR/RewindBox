# MeloNX fragmented guest reads — 1 November 2026

Status: **Core compiled and simulator-validated (run
[41347064464](https://github.com/TarbleFR/RewindBox/actions/runs/41347064464));
private IPA 611 in preparation; iPhone measurement pending.** No FPS or
device-allocation gain is claimed.

## 1. Measured symptom (IPA 609, Hogwarts Legacy 1.0.5, iPhone 16 Pro Max)

Source: the MeloNX performance journal of three 609 sessions (sanitised
metrics in [evidence](evidence/hogwarts609-device-20261101/hogwarts609-device-metrics.json);
raw journals are not committed).

| Measure (5 s windows, GPU dispatch busy > 4 s) | Value |
|---|---|
| Windows | 15 (of 35 non-final 609 windows) |
| GPU-thread allocation (`gpuDispatch` bytes) | 1.03–1.76 GB per window |
| Correlation with dispatch busy time (21 windows > 1 s busy) | r = 0.947, about 311 MB per busy second |
| Collections per window | 10–93 in total, 6–10 gen 2 |
| Gen 2 share of collections | 53–75 % in steady windows, 9–41 % after a scene change; 35 % over all heavy windows |
| GC pause | 271–1031 ms per window |

Draws alone do not set the bytes (r = 0.73 against 0.947 for busy time):
three consecutive windows rendering exactly 3,366 draws allocate 0.1–0.2 MB
each, and the 2D loading-screen window 6.8 MB, while 9,000–12,000-draw 3D
windows (including the title menu with the 3D character) allocate 1.4–1.8 GB.
The bytes follow guest data the game rewrites, which the GPU must reload.

## 2. Cause

- iOS uses 16 KiB host pages, so `ArmProcessContextFactory` cannot use a
  host-mapped address space (it requires ≤ 4 KiB pages) and selects
  `MemoryManagerHostTracked` even with `memoryManager=HostMappedUnsafe`.
- `MemoryManagerHostTracked.GetSpan` borrows a range only when
  `TryGetVirtualContiguous` finds it in one host block: guest physical pages
  adjacent in the backing block, or one private allocation covering the whole
  range. Any other range (non-adjacent guest physical pages, a range only
  partly private, private allocations that are not one block) is returned as
  `new byte[size]` filled by `Read`.
- The GPU reads guest memory that way for every buffer upload
  (`Buffer.SynchronizeMemory`/`LoadRegion`), single-range texture snapshot,
  command prefetch, copy-engine source and destination, and the CPU mirror of
  buffer-to-buffer copies. Buffer and texture ranges are usually ≥ 85,000
  bytes, so each copy lands in the large-object heap, which drives gen 2.

Established in code and on the host; **not yet measured on the iPhone**: the
fraction of the 609 bytes that came from these copies. The new counters below
measure exactly that.

## 3. Change (`build-utils/melonx/adapt_fragmented_reads.py`)

| File | Function | Mechanism |
|---|---|---|
| `Ryujinx.Memory/IVirtualMemoryManager.cs` | `TryGetContiguousSpan(va, size, tracked)` (new, default interface method) | Default is exactly `GetSpan(va, size, tracked)`: every manager other than HostTracked makes its previous single call |
| `Ryujinx.Cpu/Jit/MemoryManagerHostTracked.cs` | `TryGetContiguousSpan`, `GetSpan` | Same order as `GetSpan` (size 0, tracking signal, borrow); answers false instead of copying; the remaining `GetSpan` copy is counted |
| `Ryujinx.Graphics.Gpu/Memory/PhysicalMemory.cs` | `GetReadOnlyRegion(address, size)`, `ReadInto`, `GetReadOnlyRegion(MultiRange)` | Borrow through the manager, or the same `Read` into a cleared pooled snapshot owned by the region; `ReadInto` copies into the caller's span |
| `Ryujinx.Graphics.Gpu/Memory/MemoryManager.cs` | `GetReadOnlyRegion`, `ReadInto`, `ReadImpl` | Same entry points for GPU virtual addresses; page runs are read with `ReadInto` |
| `Ryujinx.Graphics.Gpu/Memory/Buffer.cs` | both `SetBufferData` uploads | Region disposed after the synchronous `SetBufferData` copy |
| `Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs` | `CommandBuffer.Prefetch` | Reads straight into the pooled word array |
| `Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs` | `DmaCopy` | Source region lives until the copy block ends; destination read with `ReadInto` |
| `Ryujinx.Graphics.Gpu/Memory/BufferCache.cs` | `CopyBufferSingleRange` | CPU mirror written from a region |

Unchanged: bytes read, tracking calls and their order (tracking is signalled
before the read, as `GetSpan` did), exceptions, and the zero-fill contract
(bytes a handled invalid access leaves unread are zero, as in the array
`GetSpan` returned). No quality, accuracy or timing setting changes.

Diagnostics (`native/melonx/EmbeddedPerformanceDiagnostics.cs`,
`adapt_gpu_work_diagnostics.py`): counters `readCopies`, `readCopyBytes`
(fresh copies that remain), `pooledReads`, `pooledReadBytes` (reads now
served from the pool), and twelve `gpuWork` rows `[calls, wallMs,
allocatedKiB]` per window: draw, compute, dma, i2m, texSync, texFlush,
texFlushAction, bufLoad, bufFlush, poolSync, shader (misses only), bindings.

## 4. Host validation

`test/melonx_fragmented_reads_test.py` compiles the GPU assembly closure twice
(delivered prepared source; final prepared source) with a test-only probe and
drives the real `MemoryManagerHostTracked`, software `MemoryManager`,
`PhysicalMemory`, `Buffer.LoadRegion`, GPU `MemoryManager` and
`GPFifoDevice.CommandBuffer.Prefetch` on scrambled guest pages, an unmapped
hole, tracked reads and a private-partition layout. Receipt:
[fragmented-reads-checks.json](evidence/melonx-fragmented-reads-20261101/fragmented-reads-checks.json).

| Operation (x64 Release, managed bytes per call) | 609 source | Final source |
|---|---:|---:|
| 1 MiB fragmented buffer upload | 1,048,688 | 120 |
| 192 KiB fragmented partial upload | 196,720 | 120 |
| Small fragmented upload | 880 | 120 |
| Contiguous upload | 88 | 88 |
| 1 MiB single-range texture snapshot | 1,048,600 | 32 |
| Multi-range texture snapshot | 229,456 | 32 |
| 96 KiB command prefetch | 98,464 | 136 |
| GPU `GetSpan` (not converted, counted) | 1,048,600 | 1,048,600 |

Same bytes, tracking actions and zero-fill everywhere (64 checks), with the
same allocation results on Linux x64 (4 KiB pages) and on the macOS ARM64 Core
runner (16 KiB pages, protection mirrors as on iOS). A range crossing two
private 32 MiB partitions was borrowed by both builds on both hosts (88 B):
the private allocator placed both halves in one block, so this layout is not
a copy source. The Apple receipt's generated note attributes this to
partition bridging; the observation (no copy in the control) is what holds.

An independent adversarial review (five dimensions: lifetimes and aliasing,
semantic equivalence, concurrency, other memory managers and callers, GPU
memory manager and engines; each finding re-checked by a separate verifier)
found no defect on the iOS paths (56 checks recorded clean) and confirmed one
low-severity divergence for `MemoryManagerHostMapped`, which production
selects only with 4 KiB host pages: a tracked read crossing a 128 KiB tracking
word that holds an unmapped page threw, where the delivered
`GetSpan(tracked: true)` returned the data. The flag now travels with
`TryGetContiguousSpan`, so that manager makes exactly its previous call. The
fixture gained a HostMapped scenario (tracked, partial, unarmed, untracked and
empty reads across a hole, and a tracked `ReadInto`) whose control and
candidate results must be identical; it runs wherever HostMapped exists (66
checks on Linux x64) and reports itself as not applicable on 16 KiB hosts.

The four collector-dependent fixtures also pass against the final source:
pipeline checkpoint, counter-report compaction, single virtual dependency
(4939 assertions, semantic digest `d6683e2dce9156cd` unchanged) and
performance diagnostics (121 runtime and 22 source checks).

## 5. Core increment

`build-utils/melonx/verify_reads_core.py` and the frozen
`reads-core-contract.json` rebuild the 609 engine (liveness Core run
`41323968050`, artifact `13090479414`) with 128 preparation inputs, 171
prepared members and 17 production changes. Five fresh gates bind the final
prepared source; 27 unchanged historical receipts are authenticated without
replay; 22 stay historical-only. The finalizer also requires the twelve GPU
work rows and four read counters in both simulator sessions' final payloads.

| Core identity | Value |
|---|---|
| Source | `b99e754de165661437548121918cf75ae24649ae` (supersedes `a8d22fe`, run `41339055246`, before the HostMapped fix) |
| Run / job | `41347064464` / `124969067860`, attempt 1, success (10 min) |
| Artifact | `13099194047`, 88,369,353 bytes, SHA-256 `052857e37772f7ab8b855a564f5293b0ee8ae77674d81b846b25e81bba74d534` |
| `ios-arm64` library | 37,765,760 bytes, SHA-256 `e45d1b3229ecbe804b4c8c48719f089443466ea3d599500fd10bda47443fc3ac`; packaged fingerprint `98ecdb25671822974488ad5449ef88d4c84d6ae38f763a4a5d523d4d5448f915` |
| Simulator library | 38,060,920 bytes, SHA-256 `2822c4fadaba50817a259044acd0d8e572917df9912eb952173b531b1b97dd51` |
| Gates on Apple ARM64 | 5/5 passed (84 s); two NativeAOT simulator sessions, backing released |

Summary: [core-summary.json](evidence/melonx-reads-core-20261101/core-summary.json);
Apple receipt: [fragmented-reads-checks-apple.json](evidence/melonx-reads-core-20261101/fragmented-reads-checks-apple.json).
Status `compiled-and-simulator-validated-not-gameplay-tested`.

## 5b. Private IPA 611

At the maintainer's request, 611 is built on top of delivered 610 with the
standard delivery recipe (see AGENTS.md): this MeloNX Core, the RPCS3 Core 611
carrying the RetroAchievements PS3 Core patch (RPCS3 Core route) and the
RetroAchievements commits. A first 609-based 611 run (`41340417135`) was
cancelled during its Xcode step at the maintainer's request; nothing was
delivered and its `rewind611_*` recipe is superseded.

## 6. Not done, and why

- GC configuration changes (thresholds, conserve memory): rejected earlier;
  they move pauses without removing the allocations.
- Quality reductions: none.
- Not converted yet, but counted by `readCopies`: shader code comparison
  (`ShaderCache.IsShaderEqual` via `GetSpanMapped`), non-prefetched command
  words (`GPFifoDevice.GetWords`), constant-buffer and bindless reads through
  `GetSpan(MultiRange)`, `LayoutConverter` pool misses. They are next only if
  the iPhone counters show they matter.

## 7. iPhone measurement protocol

Same save and scene as the 609 recording, then Super Smash Bros. Ultimate as a
control. From the MeloNX performance journal, per 5 s window: `gpuDispatch`
bytes, `managed.collections` and `gcPauseMs`, `readCopies`/`readCopyBytes`,
`pooledReads`/`pooledReadBytes`, and the `gpuWork` rows; plus the overlay FPS.
Success means fewer `gpuDispatch` bytes and gen 2 collections in comparable
windows with unchanged images; `readCopyBytes` shows what is left.
