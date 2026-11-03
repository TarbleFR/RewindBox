# MeloNX on IPA 629: Hogwarts Legacy draw encoding (3 November 2026)

Reference: private IPA 629 (`3bb3f7ad`), MeloNX Core 628 (source `1ce1cd14`, iPhone library `1699cf38…`,
packaged `dfd9061e…`). Session PID 3558, the only 629 session in the journals: the launch journal names
"Application 0.0.8 (629); MeloNX source 1ce1cd14a965; original core SHA256 prefix 1699cf38d609", the pin's values.
Figures from `tools/melonx/frame_report.py` (performance, core, the two stderr files concatenated) and from the 5 s
Vulkan, render-thread and detail lines of the core journal. 1x, 90 s session, no pause markers: there are no passes,
and the time from Continue to control is not measured.

## Result of the reference session

| Seconds 15-90 | Value |
|---|---|
| Game FPS mean / median / min | 16.3 / 14.2 / 1.4 |
| Frame time p50 / p95 / p99 | 50 / 100 / 150 ms |
| Pauses over 50 / 100 ms | 699 / 87 |
| Thermal state | nominal, then fair |

## Where the render thread's time goes (heavy play, 11:15:50-11:16:29)

The render thread is busy 46.7 ms per presented frame, 85 % of the window. The GPU is busy 19.2 ms per frame
(`MetalGpuTimer`, overlapping command buffers merged): the GPU does not set the limit.

| Cost | File, function | Journal line | ms per frame | Calls per frame |
|---|---|---|---|---|
| Compute descriptor updates | `DescriptorSetUpdater.UpdateAndBindDescriptorSets` (compute), from `PipelineBase.PrepareComputeDispatch` | "Vulkan render stages", compute prepare, descriptors | 30.7 | 57.7 dispatches (532 µs each) |
| `DispatchCompute` command | `ThreadedRenderer` command time | "Render thread commands" | 26.6 | 50 (534 µs each) |
| Graphics draw encoding (the target) | `DrawIndexed` command: `PipelineBase.PrepareGraphicsDraw` and the draw | "Render thread commands" | 9.5 | 1026 (9.3 µs each) |
| Of which draw descriptor updates | `DescriptorSetUpdater.UpdateAndBindDescriptorSets` (graphics) | "Vulkan render stages", draw prepare, descriptors | 7.6 of 9.7 | 1191 draws |
| Submission | `CreateSync` → `PipelineFull.FlushCommandsImpl`, queue part `CommandBufferPool.ReturnAndRent` | "Render thread commands"; submits, queue | 5.4; 7.2 (queue 7.1) | 12; 15.2 submits |
| Metal encoding (MoltenVK thread) | MoltenVK 1.4.0 | stderr "Encode VkCommandBuffer to MTLCommandBuffer" | 24.3 (last 300 frames) | 17.9 command buffers |

The two frame counts differ slightly: the render-thread lines are divided by the presented frames of the per-second
lines, the Vulkan lines by their own present count. Nested durations are never added.

**Passes and barriers.** 85 render passes begun per frame, 20.7 of them again on the framebuffer the last one ended on
(after `DrawIndexed` 8.5, `ReportCounter` 1.8, `SetProgram` 1.6, `CopyBuffer` 0.8, `ClearBuffer` 0.3 per frame over the
session). In-pass read barriers: 0.1 deferred and 18.1 kept per frame, kept because the texture is an attachment of
the active pass (a feedback loop): the 628 deferral almost never applies.

**DMA.** 305 read-backs on the GPU, 299 into buffers over textures, none declined: the 628 change works; the
first-access flushes are 6 (109 ms in all).

## Why the compute descriptor updates first

- **They are the largest cost**, 30.7 ms per frame, and they do not depend on the number of dispatches but on the
  bindless array updates. Over the twelve windows, the compute descriptor time follows the `arrayDelta` passes of the
  GPU thread (`TextureBindingsArrayCache` delta updates, core-performance lines): r = 0.992, **7.7 ms per pass**; it
  follows the dispatch count much less (r = 0.74).
- **The arrays have 524 288 elements** (`arrFullElems` 524 288 per full rebuild, the texture pool's `MaximumId + 1`). A
  delta pass changes about 40 of them (`arrDeltaChanged` / passes), and there are 250-350 passes per 5 s.
- **The cause** is in `TextureArray` and `ResourceArray`: any `SetTextures` / `SetSamplers` releases the array's
  descriptor set (`ResourceArray.SetDirty` → `ReleaseDescriptorSet`), so the next bind (`BindExtraSets` →
  `TextureArray.GetDescriptorSets`) takes another set and writes all 524 288 descriptors (`GetImageInfos` walks the
  whole array, the template pushes 12.6 MB, `vkUpdateDescriptorSetWithTemplate` writes every element). Every new
  command buffer walks the whole array again to add its references.
- **The draws pay a second defect**, MeloNX's own. The template path of `DescriptorSetUpdater.UpdateAndBind`
  indexes `_textures` and `_bufferTextures` (32 entries) and `_images` and `_bufferImages` (16 entries) by
  binding number. A fragment texture is at binding 64-95, a buffer texture at 32-63 (+64 per stage), a buffer
  image at 16-31. So each texture or image set update with such a binding throws `IndexOutOfRangeException`. The
  `try/catch` of `UpdateAndBindDescriptorSets` catches it and the fallback rewrites the set one descriptor at a
  time, in a second descriptor set. The journal counts 326 439 first-chance `IndexOutOfRangeException` in 1067
  frames, 493 per frame in heavy play.

So the change of this build (Hogwarts Legacy policy, reversible, counted):
1. the array keeps descriptor sets of its own and brings an idle one up to date by writing only the elements changed
   since it was last written, and references per command buffer only its distinct textures and samplers;
2. the template path's scratch arrays are sized by binding number (`MaxTextureBindings * 2`, `MaxImageBindings * 2`),
   so no exception and no per-descriptor fallback.

The draw target is the `DrawIndexed` time per frame of this reference, 9.5 ms: 30-40 % less is 5.7-6.7 ms. Compute
gains are reported apart and do not count toward it.

## The change, as written for build 631 (sources only so far)

Policy: `EncodingPolicy` (PipelineBase.cs), two flags assigned per session by the Library with the other Hogwarts
policies (`adapt_hogwarts_dma_copies.LIBRARY_NEW`); both off for every other title, where both paths are the delivered
ones. Hunks in `build-utils/melonx/adapt_host_qos_pipeline_budget.py` (`ENCODING_HUNKS`, five files).

| Flag | What changes | Counted in the detail line |
|---|---|---|
| `BindingSizedDescriptorScratch` | `DescriptorSetUpdater`: the four template scratch arrays are allocated like the references (`MaxTextureBindings * 2`, `MaxImageBindings * 2`); the template path takes them whole (off: `AsSpan(0, one stage)`, as delivered). No more `IndexOutOfRangeException` and per-descriptor fallback for bindings past one stage. | template fallbacks by set (uniform/storage/texture/image) |
| `IncrementalArrayDescriptors` | `TextureArray` (texture arrays, not buffer arrays): changes logged by range (1024 ranges); values resolved from the changed ranges; each command buffer references the distinct views and samplers once (counted incrementally up to 4096 elements per update); up to 8 descriptor sets of its own, an idle one (`PipelineLayoutCacheEntry.IsManualDescriptorSetCollectionIdle`: held by no pending command buffer) brought up to date by writing the changed ranges, whole past the log or a quarter of the array; `ResourceArray` releases them at disposal. A destroyed view or sampler found among the references is recorded as a change of its elements (they take the dummy): the delivered path kept binding a cached set holding the destroyed handle until the next update. Another binding size, or every set pending: the delivered path. | sets written whole (elements), by range (elements written, kept), write time, reference passes (references, time), current binds, sets added, delivered path |

What the gates check (none run yet, see below):
- `hogwarts-dma-copies` (169 checks): each of the five files is the delivered one plus its hunks; flags off by default and
  assigned once; template scratch only through the policy; fallbacks counted before the delivered fallback; idle-only
  writes; every anchor drifted makes the adapter fail; the real `RenderDetail` logs the new sections and resets them.
- `scalar-texture-descriptors`, `fallback-descriptor-scratch` (receipts that declare `DescriptorSetUpdater.cs`): delivered
  members against final members, policy off and on: same semantics, traces and counts; the final members are the
  delivered ones with the hunks only. New case: a fragment texture at binding 64 and a fragment image at binding 32 take
  the fallback (2 `IndexOutOfRangeException`) without the policy and the template with it.
- `single-resource-bindings`, `bounded-binding-snapshots` (receipts that declare `TextureArray.cs`): GAL files and the other
  backends unchanged byte for byte; the final setters only read the caller's array; both TextureArrays compiled whole
  (`test/melonx_array_descriptor_ranges/`): policy off equal to delivered (descriptor writes hashed in order), policy on
  with every bound set holding the array's elements, no set written while a pending command buffer uses it, ownership of
  every referenced view and sampler, caller arrays overwritten at once, a destroyed view, a log overrun, every set pending,
  another binding size, another program of the layout, disposal.
- `fragmented-reads` compiles the GPU and Vulkan assemblies from the final source and binds the five files.

Not done in this session: the session cannot reach NuGet, the .NET SDK download or the Actions artifact storage
(`*.blob.core.windows.net`, proxy 403 at 12:17, 12:22, 12:36 and 13:09 UTC). So no C# fixture has been compiled here, the
contract is not refrozen (`freeze_dma_core.py` needs the 614 archive and local receipts of the ten gates), and no Core CI
or IPA was started. The 614 control was rebuilt locally from `b181cbe1` and matches every frozen digest (171 prepared,
28 untouched, 3 unadapted members); the candidate prepared tree has 131 inputs and 176 members.

Next safe step, in a session with that access: install the .NET 10.0.100 SDK, materialize the four controls from the 614
archive, run the ten gates against them with `--candidate-source` on a fresh preparation, run `freeze_dma_core.py` with
`--receipts` and `--control`, then the two contract tests; then the Core CI (`[melonx-dma-core]`), and with its pin set
`FRESH_GATES = 10` in `.github/diagnostics/melonx_dma_core_component.py` (kept out of the source commit so that a delivery
of the pinned 628 Core still verifies).

## After 631: the next limit, and what MoltenVK 1.4.0 does on iOS (3 Nov 2026, 13:30 UTC)

629, slow windows (7 windows below the median game FPS, 472 frames): the render thread is busy 46.4 ms per frame, of which
`DispatchCompute` 25.6 ms (46 calls), `DrawIndexed` 9.9 ms (998 calls), `CreateSync` 5.8 ms (11 calls), every other command
under 1 ms. Build 631 targets the descriptor parts of the first two (compute descriptors 30-34 ms per frame in those
windows; draw descriptors 6.7-17.9 ms with 25 000-50 000 first-chance exceptions per window); how much goes away is for
the iPhone to say. The other ceilings of the same report: the GPU thread's own work 18.9 ms per frame (slow windows),
MoltenVK's Metal encoding 13.8 ms per frame over the session and 24.3 ms in its heaviest block (17.9 command buffers per
frame), the GPU 13.2 ms per frame (26.8 ms in the heaviest window). Once the render thread is relieved, MoltenVK's
submission thread is the nearest ceiling, and its time is not broken down by the logs.

What MoltenVK 1.4.0 does with Hogwarts' 524 288-element arrays on iOS (source read at tag `v1.4.0`; the iPhone runs the
"MeloNX 1.4.0 (standalone)" binary, the default variant):
- `MTLResidencySet` is enabled on macOS only (`MVKDevice.mm:2956`, `#if MVK_XCODE_16 && MVK_MACOS`).
- Without it, `MVKResourcesCommandEncoderState::encodeMetalArgumentBuffer` (`MVKCommandEncoderState.mm:723`) runs, at each
  dirty encode of the resources state and for every binding the pipeline uses, a loop over every element of the binding
  that tests its usage-dirty bit, and calls `encodeResourceUsage` for each dirty element: for compute one
  `useResource:usage:` per descriptor with no deduplication (`:1341`), for graphics `useResource:usage:stages:` with a
  per-pass stage map (`:1178`).
- All the bits are set again when another descriptor set is bound at that index (`bindDescriptorSet`, `:691`), at every
  new Metal encoder (`endCurrentMetalEncoding` marks the compute resources dirty, `MVKCommandBuffer.mm:1096`; every render
  pass begun marks the graphics resources dirty, `MVKCommandEncoderState.h:70`), and when MoltenVK runs its own compute
  work in the command buffer: copies by compute, image clears, `vkCmdFillBuffer` and the occlusion-query accumulation at
  the end of a render pass with queries (`getMTLComputeEncoder(..., true)`, `MVKCmdTransfer.mm:1044, 1669, 1843`,
  `MVKCommandEncoderState.mm:1398`).

So each array update (another set: the delivered path takes another set of the manual cache, 631 another of its own idle
sets, the same count), each new command buffer and each encoder switch can cost a walk of 524 288 descriptors on
MoltenVK's thread, and every dirty dispatch or draw that uses the array a scan of 524 288 bits. The 17.9 command buffers
per frame (11 of them from strict `CreateSync` flushes) multiply it. The share of the 13.8-24.3 ms is not measured.

What would remove it. Each means recompiling MoltenVK 1.4.0 or replacing the kept binary
(`src/MeloNX/MeloNX/Dependencies/libMoltenVK.dylib`, SHA-256 `5735ca4a…`), so none is done without the maintainer's
agreement, and each build should add a MoltenVK performance tracker around `encodeMetalArgumentBuffer` so that the gain
is measured on the iPhone:
1. Residency sets on iOS 18 (Apple6 and later): the loop stops at the first used binding. MoltenVK then also orders work
   with `MTLFence`s instead of Metal's per-encoder resource tracking (`MVKCommandBuffer.mm:644-692`), a path it only
   enables on macOS. Largest expected gain, largest risk.
2. Keep `useResource`, but once per distinct resource and encoder, and iterate the set bits only: the same Metal
   semantics, a smaller gain (after a set change every element is still resolved).
No option of `MVKInitialization.cs` reaches this path (heaps, prefill, argument buffers: arrays of this size need
argument buffers).

C#-side lever considered and not written: syncpoint increments create strict syncs (`HostSyncFlags.StrictSyncpoint`, 11
flushes per frame in the slow windows), each a new command buffer, hence new MoltenVK encoders and every descriptor set
bound again by the backend. Non-strict syncs for Hogwarts would cut command buffers, but a guest that polls GPU-written
memory instead of waiting on a sync would then wait for the next flush. That needs the waits it moves measured on the
iPhone first, not a change written blind.

Network at 13:28 UTC: the GitHub API answers (runs, artifact metadata, the 302 to an artifact), but the artifact storage
(`productionresultssa*.blob.core.windows.net`), the .NET SDK (`builds.dotnet.microsoft.com`, `dotnetcli.azureedge.net`),
NuGet (`api.nuget.org`, `globalcdn.nuget.org`) and the Ubuntu archive are still refused (proxy 403 to `CONNECT`), and
PyPI and npm, reached without the proxy, do not answer. The next safe step above is unchanged.
