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

## Second player, two more 621 sessions (received 3 November 2026, session 012mUASkkFGHaPcEUx9dsp8q)

Inputs: `MeloNX-stderr(1).log` (584 009 bytes, `61cbc6f2…`), `MeloNX-core(5).log` (189 386 bytes, `f3c9f52c…`),
`MeloNX-performance(1).log` (1 049 984 bytes, `d9644d20…`): build 621, Core `4ad8814e`, Hogwarts Legacy
`0100f7e00c70e000`. The logs are private and are not in the repository; the figures below are derived from them. The
GC reports 8 016 MiB of total memory and the process limit is about 6 143 MiB (footprint plus headroom): an 8 GiB
iPhone, model not established. Sessions are kept apart by PID, session and timestamp:

| Session | PID | Span | Note |
|---|---|---|---|
| A, `12AAAE01` | 57222 | 01:51:55-01:57:02, about 5 min, `close: passed` | mostly paused (menus); four short passes |
| B, `2F562F0F` | 63461 | 23:27:44-23:41:32, about 14 min, no close line | continuous play, then thermal `serious` in the last minute |
| C | 67481 | 23:46:33, stops at the firmware stage | not a game session |

Frame report (`tools/melonx/frame_report.py --passes`; pass = stretch between paused lines): A median game FPS 11.5,
p50/p95/p99 50/150/267 ms, 206 pauses over 100 ms in 233 s; B median 8.8, p50/p95/p99 100/233/483 ms, 3 465 pauses
over 100 ms in 551 s.

| # | Finding | Disposition |
|---|---|---|
| 1 | Read-back flushes dominate both sessions: GPU thread waits for the render thread 37-110 ms per presented frame, texture flush actions 2.3-4.3 s per 5 s window, `gpuRegionCopies 0`, `linearDestination 238` | Already corrected: same signature as PID 990 above; 623 deferred read-back, 625 copy into the buffer, 628 occupied destinations (629 shows 299 of 305 read-backs into buffers). Not reopened |
| 2 | Device-short trims: B 68 trims "releasing" 2 008 MiB in 13 min (A 5, 193 MiB) at 880-1 570 MiB of process headroom; device share stays 4-7 %, footprint 4.8 → 5.3 GiB; the texture cache sits at its 96 MiB floor and loses 15-45 MiB every 10 s; windows with a trim: texture flushes median 52 ms (A, max 301 ms) and up to 120 ms (B) against 0-6.5 ms without, texture synchronisation +6 ms, buffer loads +26-29 ms | Defect established, corrected: `adapt_device_short_trim.py` (below) |
| 3 | Late B (23:35-23:41): the 5 s core windows stretch to 24-72 s with 8.7, 25.2, 12.2, 13.6 and 13.8 s of GC pause; one non-concurrent gen0 compaction takes 1.8-3.6 s; display-link callbacks late by up to 16 s and the per-second journal itself skips 10-30 s; total CPU 29-75 %; device 4-10 %, GC memory load 91-92 % | Established symptom, cause to settle: waits, not work (CPU low), under device-wide pressure. `adapt_gc` (575) already sets the GC mode for high device load; not reopened. Missing datum, named: per collection the suspension time apart from the GC work, and this process's compressed and paged-in memory (`TASK_VM_INFO` compressed, `proc_pid_rusage` page-ins) in the per-second line. With it: page-ins mean memory to give back first (footprint), suspension means the threads that do not reach a safe point |
| 4 | Footprint: B 1.97 → 5.25 GiB; managed heap 760-845 MiB (fragmented up to 304 MiB); GPU caches about 95 MiB of textures and 70-190 MiB of buffers; MoltenVK pipeline caches loaded at 569 MiB main plus two worker snapshots, main reaching its 768 MiB budget in A | Hypothesis: about 4 GiB is not attributed by these logs. The pipeline caches are the largest identified host consumer (budget 1 GiB, persistent across launches); lowering it trades memory for recompilation, so not changed blind. Same missing datum as #3, plus MoltenVK's GPU memory statistics (623 and later) |
| 5 | Pipelines: B 937 graphics pipeline builds (about 9 s) in the first 20 s after loading 2 189 cached shaders; A 626 builds (5.1 s) entering a new area; no "Background pipeline compile missed" line | Expected startup warm-up (`adapt_cached_shader_startup`) and new states in play; no miss to attribute (PR #153 targets misses, none here) |
| 6 | A only: 15 shaders not loaded from the disk cache, 8 of them "Texture array length missing from the cache file" | One-time after a translator change; B, later, loads 2 189 shaders with no error. Constraint, no change |
| 7 | Syncpoint waits over 1 s: A 1, B 3 (23:35:53-23:36:38) | Inside the stall of #3 and with the read-backs of #1; 631 queues report increments. No separate cause shown |
| 8 | Thermal: B `fair` from 23:33, `serious` only in the last minute | FPS falls earlier with #1 and #3; not the main cause here |

### Correction: device-short trims without flushes or pretend releases (`build-utils/melonx/adapt_device_short_trim.py`)

`adapt_device_memory` (586) made `GpuContext.TrimCaches` act whenever the device share is 7 % or less, whatever this
process's headroom, and every 10 s while it lasts. `AutoDeleteCache.Trim` then evicts in LRU order whatever the
texture is. A texture a pool still references only leaves the cache (its bytes are counted as released, nothing is
freed). One with GPU-written data is flushed to guest memory first, which costs a render-thread round trip. Now, only
when the device is short while the process keeps 768 MiB or more of headroom, the texture cache evicts only textures
it alone holds (`HasOneReference`) whose group has no GPU-written handle (`AnyHandleModified`). Each eviction then
destroys its texture without a flush. As the delivered eviction does, it first synchronises the dependents of a texture whose memory the CPU has not
dirtied (`SynchronizeDependents`). An independent review (`rb-core-review`, Opus/high) found that the first version
skipped this. A copy another handle deferred from the evicted texture would then have read its released host texture.
Fixed before commit; the fixture now fails if dependents are synchronised after the release. The bytes kept are added to the trim line. The following are unchanged: targets,
the floor, intervals, the buffer cache, every trim under this process's own pressure (under 768 MiB, under 256 MiB,
or headroom unknown), and the ordinary capacity eviction.

Proof (fresh, Linux x86_64, SDK 10.0.100, [receipt](evidence/melonx-device-short-trim/checks.json)):
`python3 test/melonx_device_short_trim_test.py <prepared tree>` compiles the complete production `AutoDeleteCache.cs`
with the production `Texture` reference and view members, control (631) and candidate. Storage and group handles are
doubles. Results:
- The delivered trim is identical in both variants and reproduces the 621 behaviour: 80 MiB "released", 48 MiB
  destroyed, 2 flushes, 2 pool-referenced textures dropped.
- The device-short trim destroys every byte it evicts, flushes nothing, keeps pool-referenced and GPU-written textures
  in LRU order, frees a view and then its storage, respects the floor and reports what it kept.
- The whole candidate GPU assembly compiles.

Not measured on the iPhone. Its effect on stalls and memory is not claimed. Expected: no trim flushes, and trims that
actually free what they report.
