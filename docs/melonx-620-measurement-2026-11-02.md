# MeloNX on IPA 620: Hogwarts Legacy and Super Smash Bros. Ultimate (2 November 2026)

iPhone 16 Pro Max (2868×1320 swapchain; A18 Pro: six cores, two of them performance cores), build 620, Core `1c836557`
(original core `58330ffd…`). The figures come from `tools/melonx/frame_report.py` and from the
5.1 s core windows.

## Hogwarts Legacy, PID 66809 (policy active, `titleMatched=true`)

### Time to the controllable character

| Stage | Time (UTC) | Note |
|---|---|---|
| Launch from RewindBox | 22:03:10 | |
| Engine start | 22:03:13 | entitlements, JIT probe 2 s, donor mapping |
| First Metal frame | 22:03:19 | |
| 3D menus, 2D menu screens | 22:03:34–22:03:56 | 3D menus at 8–19 FPS, 2D screens at 30 FPS |
| Loading after the save is chosen | 22:03:57–22:04:05 | loading CPU-bound in the game; 80 pipeline builds and a 1.2 s presentation gap at the end |
| Controllable | from 22:04:06 | about 9 s after the save choice |

- **The start runs on the game's own code.** The guest main thread is at 73–97 % of a core
  for 13 s, and at boot the Core retranslates all of it: the Lightning JIT has no disk cache
  (`DummyDiskCacheLoadState`; the `ptc=True` setting has no effect).
- **Allocations and GC.** The first 5 s window allocated 6.2 GB in 610 gen0 collections, with
  903 ms of pauses. In the first 25 s, 10 GB were allocated and the GC paused for about 2 s.
- **Pipelines.** 317 pipelines were rebuilt in the background, 2.2 s in total.

### In game, 60 s

- **Rate.** 13–16 FPS.
- **Frame times.** p50 67 ms, p95 100 ms, p99 133 ms.
- **Pauses.** 1236 over 50 ms and 164 over 100 ms, over the whole session.
- **The 620 GPU source copy never ran.** 23,552 copies went through guest memory, with 0 GPU
  copies and 22,810 declined because no linear texture was over the source.
- **The slow source reads are the copies that skip that lookup.** At every summary, the number
  of slow reads equals the number of copies that skip the lookup (8, 223, 322, 741): copies
  that are not a linear source into a block-linear destination. Each one runs the flush action
  of a GPU-written texture: one per frame, about 50 ms each.
- **The 618 note was wrong on one point.** It inferred that the copies came from linear memory,
  but it relied on signatures capped at 8 per reason, all logged at start.
- **What a flush costs.** 61–126 flush actions per window, 2.5–4.4 s of the GPU thread. During
  them the GPU thread waits for the render thread (`syncInvoke` 3.4–4.4 s), and the render
  thread waits for the GPU fence (`bufferReadback` 1.5–1.9 s; these waits are the
  `GetTextureData` of the flushes). These durations are nested and are not added up.
- **Thread priorities.** The render thread (`NeoStation.MeloNX.Render`, 55–65 % CPU) and
  `GPU.MainThread` run at priority 31 (default QoS). The system's GCD work runs above them at
  37–47.

## Super Smash Bros. Ultimate, PID 67058 (`titleMatched=false`)

- **Session.** 8 minutes at 57.6 FPS mean; p50, p95 and p99 at 17 ms.
- **Pauses.** 143 over 50 ms and 80 over 100 ms, up to 3.75 s.
- **What they are.** Each pause falls in a window of pipeline builds of 120–320 ms each, while
  the GPU thread waits for the render thread (up to 2.5 s per window) and the game waits for
  the GPU (`ServiceNv Wait`).
- **Why they come back every session.** The main pipeline cache loaded 383.81 MiB of its
  384 MiB budget and "will not be persisted until it fits". The worker 0 cache was recycled
  six times in 10 s at 64 MiB. Nothing a session compiles is kept, so the same pipelines are
  converted again, in game, every session.

## Changes for IPA 621 (none measured on the iPhone)

**Hogwarts Legacy only** (`adapt_hogwarts_dma_copies.py`):

1. **GPU region copy.** A copy from a block-linear surface held by a texture the GPU modified,
   into a block-linear surface, is copied on the GPU (`TryCopyGpuRegion`).
   - **Destination.** The texture of the destination surface is used if it exists. Otherwise one
     is created, the way the delivered GPU copy of complete copies creates its target, but only
     when no texture overlaps that surface. The creation would otherwise drop an overlapping
     texture the GPU wrote, or the source itself, without reading it back.
   - **Linear destination (a read-back).** Stays on the guest path, counted as
     `linearDestination` in the DMA summary line. A GPU buffer over that memory, or a CPU read
     right after the copy's semaphore, would miss bytes that only a texture holds. The 621
     journal gives the split between the two kinds of destination.
   - **Surface lookup.** It now only takes a texture that starts at the surface base: the cache
     returns any texture that contains it.
2. **Exact formats.** UNORM, sRGB and float formats, both GPU copies included.
3. **Precise reads.** The guest-path reads are signalled precisely (`SignalPreciseRead`): a
   texture that only shares a page with the copied bytes is no longer read back.

**Every title** (`adapt_host_qos_pipeline_budget.py`):

4. **Thread QoS.** The render thread, `GPU.MainThread` and the demand compile thread run at
   user-interactive QoS. A failed call is logged once.
   - **Load in game.** The process uses about two of the six cores. In Hogwarts: render thread
     47–70 %, `GPU.MainThread` 12–27 %, the game's threads 12–16 %. SSBU uses about 1.6 cores. The
     raised threads therefore leave room for the game's threads.
   - **Verification.** The journal's per-thread priorities show the result on the device.
5. **Pipeline cache.** The budget is 1 GiB: main 768 MiB, 128 MiB per worker.

**Every title**, in the app (`MeloNXRuntimeAPI.swift`):

6. **GC.** A 64 MiB gen0 budget (`DOTNET_GCgen0size`) is set before the engine loads.
   - **The variable is read.** Checked with NativeAOT 10.0.0, the Core's compiler, on
     linux-x64. `GC.GetConfigurationVariables` reports `GCGen0MaxBudget` 67108864, and there
     are 62 gen0 collections for 3.9 GB, against 30 at that machine's 130 MiB default.
   - **On the iPhone.** The default budget is about 10 MiB (610 collections for 6.2 GB).

**Considered but not changed:**
- **Setting already in place in RewindBox's MoltenVK configuration:** asynchronous MoltenVK
  submission (`SynchronousQueueSubmits=false`).
- **Already the MoltenVK 1.4 default:** Metal 3 argument buffers.
- **Measured, not a separate cost:** the buffer read-backs, which are the waits of the flushes.
- **A separate project:** a persistent translation cache for the Lightning JIT.
- **Explicit trade-offs, not applied:** a lower internal resolution or MetalFX.
