# MeloNX on IPA 624: Hogwarts Legacy (3 November 2026)

This note covers Hogwarts Legacy on build 624: MeloNX Core 623 (`5c20e0cb`, packaged `27f1afa1…`), PID 1835, on an
iPhone 16 Pro Max. It compares with build 621, PID 990
([621 note](melonx-621-measurement-2026-11-03.md)). The figures come from
`tools/melonx/frame_report.py --stderr`, the 5 s render-thread and Vulkan lines and MoltenVK's statistics.

## Result

| Session | Game FPS mean / median | p50 / p95 / p99 | Pauses over 50 / 100 ms | Thermal state |
|---|---|---|---|---|
| 621, PID 990 (117 s) | 14.1 / 12.0 | 67 / 117 / 133 ms | 1050 / 316 | fair, then serious from t=101 s |
| 624, PID 1835 (121 s) | 15.0 / 13.2 | 67 / 100 / 117 ms | 1281 / 165 | nominal throughout |

The run has no pause markers, so the time from Continue to control is not measured.

## Why 623 did not remove the wait

- **The deferred read-back almost never applied.** The DMA summary gives `gpuReadBacks 4 of 751`: 747 were
  declined because a buffer of the cache holds the destination.
- **What the copy is.** The one logged copy is a whole 1x1 R16G16B16A16Float texture (8 bytes, the eye-adaptation
  value) into linear memory, about once per frame. The 747 declined copies are this copy with a buffer over the
  destination.
- **What it costs.** Each one still flushes the texture. The GPU thread waits about 57 ms per frame for the render
  thread and the host GPU. The render thread spends 19-25 ms per frame in that flush (`Action`), almost all of it
  fence waits (26-31 ms per read).

## What the new journals show (624, per presented frame)

- **Render thread commands.** Over all windows they take 48.5 ms, and 66.2 ms over the slow ones:
  - `DispatchCompute`: 21-29 ms for 37-51 dispatches, about 0.56 ms each;
  - `Action` (the flush): 19-25 ms;
  - `DrawIndexed`: 5-8 ms for 670-940 draws.
- **Draw preparation.** It takes 6-16 ms, mostly descriptor updates (4.7-14.6 ms). Pipelines take little outside
  loading.
- **Render passes.** 68-92 are begun per frame, and 14-23 of them begin again on the framebuffer the last one
  ended on. A compute dispatch between draws ends the pass.
- **Submissions.** 13-23 per frame, 0.8-1.7 ms.
- **MoltenVK.**
  - Metal encoding takes 23-31 ms per frame on MoltenVK's submission thread.
  - The Metal command buffers run 77-97 ms of GPU time per frame, for a frame interval of 72-83 ms. The command
    buffers overlap, so the GPU's real busy time is lower but unknown.
  - Drawable waits are near zero.
- **Ceilings.**

  | Limit | Ceiling |
  |---|---|
  | GPU thread with its read-back waits, all windows | 20 FPS |
  | GPU thread with its read-back waits, slow windows | 16 FPS |
  | Render thread's own work, all windows | 37 FPS |
  | Render thread's own work, slow windows | 25 FPS |
  | GPU (overlapping command buffers counted apart) | 21 FPS |

## Changes for IPA 625 (not measured on the iPhone)

**Hogwarts Legacy only: the read-back into a buffer (`TryReadBackIntoBuffer`).** When the copy covers the whole
source texture and no texture overlaps the destination:
- **The copy.** The texture level is copied on the GPU into the buffer that holds the destination
  (`BufferCache.TryCopyTextureToBuffer`, which runs `ITexture.CopyTo` into the buffer range).
- **The buffer.** The range is marked GPU-modified, as a buffer to buffer copy does: a GPU read uses the buffer, and
  a CPU read flushes it.
- **The sync.** A forced host sync follows the copy. It seals the modification, so a guest-memory read before the
  guest's own sync waits for the copy too.
- **A partial region** keeps the guest path, counted as `partial`.
- **The DMA summary** counts the read-backs into buffers apart.

**Every title: the compute dispatch preparation, timed.** `RenderStageTimer` also logs compute pipelines, barriers
and descriptor updates, and the render passes that dispatches end.

**Expected effect.**
- **Removed:** the GPU thread's wait of about 57 ms per frame and the render thread's flush of 19-25 ms.
- **Next limits:** the render thread (25-37 FPS ceilings), MoltenVK's encoding thread (23-31 ms) and the GPU, whose
  real busy time the next run will bound better.
- **No 30 FPS claim.** If the GPU becomes the limit, the image and swapchain waits will rise in the Vulkan lines.
