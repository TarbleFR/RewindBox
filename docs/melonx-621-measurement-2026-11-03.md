# MeloNX on IPA 621: Hogwarts Legacy (3 November 2026)

This note covers Hogwarts Legacy on build 621, Core `4ad8814e`, PID 990, on an iPhone 16 Pro Max. It compares
with the two 620 sessions, PIDs 66809 and 67233. The figures come from `tools/melonx/frame_report.py` and from
the 5.1 s core windows.

## Result

| Session | Game FPS mean / median | p50 / p95 / p99 | Pauses over 50 / 100 ms | Thermal state |
|---|---|---|---|---|
| 620, PID 66809 (128 s) | 15.1 / 13.1 | 67 / 100 / 133 ms | 1236 / 164 | fair, nominal |
| 620, PID 67233 (60 s) | 16.8 / 13.3 | 50 / 100 / 183 ms | 506 / 69 | fair, nominal |
| 621, PID 990 (117 s) | 14.1 / 12.0 | 67 / 117 / 133 ms | 1050 / 316 | fair, then serious from t=101 s |

- **Same phase of play (t 60-89 s).** The rate was about 13.2 FPS on 620 and about 12.0 FPS on 621. 621 then
  falls to 10 FPS at the serious thermal state.
- **Thermal starting point.** The 621 session started already at the fair thermal state, while 620 started at
  nominal.
- **Startup.** The gen0 GC budget worked. The first 5 s window had 88 collections with 516 ms of pauses, against
  610 collections and 903 ms on 620. Over the first 25 s, GC pauses fell from about 2 s to about 1.15 s.

## Why 621 did not help in play

- **The GPU region copy never ran.** The DMA summary gives `gpuRegionCopies 0` and `linearDestination 636`. All
  636 copies it saw have a linear destination, and they are the 637 slow source reads.
- **What these copies are.** Each one is a read-back: a region of a GPU-written render target copied into linear
  memory, about one per frame.
- **The cost, per 5.1 s window.** The GPU thread spends 3.0-4.4 s in the texture flushes of these read-backs:
  - `syncInvoke`: about 3.1 s waiting for the render thread;
  - `queueBackpressure`: 1.1 s;
  - its own work: about 0.9 s.
- **The render thread.** It is busy 4.9 s per window, of which 1.7 s are fence waits of the same flushes. It also
  converts the flushed texture to block-linear.
- **The next limit.** The rest of the render thread's time encodes about 107,000 draws per window.

## Changes for IPA 623 (not measured on the iPhone)

**The call that forces the end of rendering.** On the 621 path, a read-back reads its source tracked.
- The read runs `TextureGroup.FlushAction` on the GPU thread.
- That queues the flush to the render thread (`ThreadedRenderer.BackgroundContextAction`, then `InvokeCommand`)
  and waits for it: this wait is `syncInvoke`.
- The render thread then runs `TextureView.GetData()`. It calls `FlushAllCommands()`, which submits all the
  rendering so far, then `PersistentFlushBuffer.GetTextureData`, which waits with `WaitForFences()` for the
  host GPU to finish it: this wait is `bufferReadback`.

**Hogwarts Legacy only: the read-back is deferred (`TryReadBackGpuRegion`, in `adapt_hogwarts_dma_copies.py`).**
- **The copy.** The region is copied on the GPU into a linear texture over the destination. Guest memory is not
  written while the DMA engine runs. A strict host sync follows the copy, which submits it at once.
- **The first CPU access.** It runs the texture's flush action:
  - the flush waits for that sync, then writes the bytes;
  - linear textures are flushed on CPU access, also on 16 KiB pages;
  - a texture flushed often is copied into Ryujinx's flush buffer at its sync.
- **Lifetime.** A target evicted from the texture cache is flushed first
  (`AutoDeleteCache.RemoveLeastUsedTexture`).
- **Conditions.** Otherwise the copy keeps the synchronous path.
  - **Rows:** whole contiguous rows on 4 bytes, because a strided linear flush writes zeros between rows. The real
    `LayoutConverter` shows it in the byte model.
  - **Buffers:** no buffer of the cache over the destination (`BufferCache.HasBufferInRange`, read-only). A
    buffer reads guest memory, which would lack the bytes.
  - **Textures:** no other texture over the destination; the target is reused when its layout and format match.
- **Byte model (`melonx_hogwarts_dma_copies_test.py`).** It checks four cases against the reference copy through
  guest memory, with guard bytes around the destination:
  - a read right after the copy;
  - a read one frame later, after the source was rendered again;
  - a partial read;
  - a rewrite before any read, followed by a new read-back.
- **The DMA summary.** It counts:
  - read-back candidates and deferred read-backs;
  - declines by reason, which keep the synchronous path;
  - the first-access flushes of read-back textures: number, total and longest duration, and how many ran on the
    GPU thread.

**Every title: the render thread's own work, by command.** `ThreadedRenderer` times each command it runs by type
and logs to `MeloNX-core.log`, every 5 s of rendering, the 8 command types with the most time.
- `tools/melonx/frame_report.py` ranks them over all windows and over the slow ones, in milliseconds per presented
  frame.
- Per window and over the session, it also separates per frame:
  - the GPU-thread waits for the render thread;
  - queue backpressure;
  - render-thread fence waits;
  - render-thread work;
  - pipeline builds.

**Every title: what the render thread's draws and frames are made of (`RenderStageTimer`, Vulkan backend).** Every
5 s of presentation, one line in `MeloNX-core.log` ("Vulkan render stages over") gives:
- the draw preparation (`RecreateGraphicsPipelineIfNeeded`), whole and in parts: pipeline creation or lookup,
  barrier flush, descriptor updates, auto-flushes;
- the render passes begun, and how many begin again on the framebuffer the last one ended on (a split pass);
- the command buffer submissions, with their queue part (`vkQueueSubmit` and the wait for a free command buffer);
- the buffer fence waits, on the render thread (before a direct buffer write, or for a read) and on other threads
  (a guest thread reading a deferred read-back);
- the presentation: whole, swapchain image acquisition, queue present.

**Every title: MoltenVK's own statistics.** MoltenVK 1.4.0 logs them to `MeloNX-stderr.log` every 300 presented
frames. They give the GPU execution of each Metal command buffer, the Metal encoding of each command buffer on
MoltenVK's submission thread, the drawable waits and the frame interval.

**The report.** `tools/melonx/frame_report.py --stderr MeloNX-stderr.log` reads these lines too. For each
resource it gives a ceiling, 1000 divided by its own busy milliseconds per presented frame:
- the GPU thread;
- the render thread: its command time minus its own fence and image waits;
- MoltenVK's encoding;
- the GPU.

The lowest ceiling names the limit to remove next. The report also gives the waits per distinct game frame.

**Not in this IPA: the draw encoding fix.** Nothing measured on the device yet attributes the render thread's work
to a particular command or state change. Host measurement is not possible: there is no Metal or MoltenVK here,
and no Vulkan driver. One 623 run gives the ranking and the stage split that choose that fix.

**What 621 already shows.** On the 621 journals, the report's ceilings over the slow half of the windows are:
- **GPU thread with its read-back waits:** 71.7 ms per frame, so 14 FPS. This is the cost the deferred read-back
  removes.
- **Render thread's own work:** 44.6 ms per frame, so 22 FPS. The figure is busy time minus all buffer fence
  waits, so it includes the conversion and guest write of each read-back flush. The deferred read-back removes
  that part as well.
- **GPU thread's own work:** 10.3 ms per frame, so 97 FPS.

**Expected effect.**
- **Removed:** most of the GPU thread's 3.1 s of flush waits and the render thread's 1.7 s, per 5.1 s window.
- **Estimate:** 18-25 FPS, with the render thread's own work as the next limit.
- **No 30 FPS claim.** In heavy scenes, 30 FPS needs the render thread's own work to fall from 44.6 ms to under
  33 ms per frame, unless most of it was the read-back flushes.
