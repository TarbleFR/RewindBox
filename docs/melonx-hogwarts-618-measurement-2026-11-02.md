# Hogwarts Legacy on IPA 618 — the per-frame source read and the GPU source copy (2 November 2026)

Session: build 618, PID 66181, Core `a8f67bfd` (original core `106dba53797b…`), title
`0100f7e00c70e000`, 19:35:26–19:37:39 UTC, first Metal presentation 19:35:35, clean close.
Hogwarts policy active (`titleMatched=true`). Historical reference: build 617, PID 65478.
Sessions with `titleMatched=false` are not compared. Seconds 59–118 of the session (60 s of
play, thermal `nominal`), from `tools/melonx/frame_report.py`.

## Result of 618 against 617 (60 s of play each)

| | 617 (PID 65478, t 48–107) | 618 (PID 66181, t 59–118) |
|---|---|---|
| Game FPS (engine, per second) | mean 13.5, median 13.2, min 10.9 | mean 13.4, median 13.6, min 11.3 |
| Presented frames | 805 | 803 |
| Texture flush actions per 5.1 s window | 63–85, 2.5–4.2 s | 62–83, 2.6–3.9 s |
| Render-thread syncs per window | 2.7–4.3 s | 2.8–4.3 s |
| Buffer read-backs per window | 1.5–1.8 s | 1.4–1.8 s |

No frame-time percentiles: these builds log only the longest gap per second (618: up to
133 ms). The region upload of 618 changed nothing measurable: 12 uploads in the session
against 21,274 `noTarget` declines.

## What the flush is (DmaClass.DmaCopy, guest-memory path)

- The 618 attribution counts **944 source reads over 2 ms against 6 slow destination
  writes**. From 19:36:25.6 to 19:37:08.0 (42.3 s of play): 1024 copies through guest memory,
  814 partial and 210 complete, all from linear memory into block-linear destinations,
  567 slow source reads, 3 region uploads. At about 13 FPS that is about one slow read per
  frame, and the 62–83 flushes per window match it.
- The read is `GetReadOnlyRegion(src, size, tracked: true)`. The tracking runs the flush
  action of every GPU-modified texture overlapping the source range
  (`TextureGroup.FlushAction`). On the GPU thread it clears the handle, then
  `BackgroundContextAction` runs on the render thread after everything already queued. That
  wait is `syncInvoke`. Then `FlushSliceRange` reads the handle's slices back. On the GPU
  thread there is no flush buffer (`inBuffer` is false): it is a `GetData` that waits for the
  GPU fence, then writes guest memory. The range made coherent is the whole handle range of
  that texture, not only the copied rows.
- One write, one wait: the action unregisters itself and is registered again only when the
  GPU next modifies the texture. Several reads do not pay for the same GPU write. One flush
  per frame is one GPU write of that texture per frame read back.
- The durations are nested: `texFlushAction` runs inside `dma`, which runs on the GPU
  thread, and the flush waits in `syncInvoke` and in a fence read-back. During it the GPU
  thread cannot process further commands. The flush time is therefore a lower bound of the
  GPU-thread time lost per frame (2.6–3.9 s of each 5.1 s window), not an addition to it.

## Decision and change (IPA 620, Core run 41519432972, packaged `c5627b99…`)

The source of these copies is GPU-written: only a GPU-modified texture over the source makes
the read run a flush. When that texture can be read on the GPU, the read back is not needed.
For Hogwarts Legacy only (`GraphicsConfig.HogwartsDmaRegionUpload`), before the read:

1. `TextureCache.FindOverlapsInRange` (new, under the texture read lock) finds the textures
   over the source range.
2. The copy runs on the GPU only when all of these hold:
   - **source texture:** one linear texture with the copy's stride holds the whole source in
     one physical region, and no other texture group overlaps it;
   - **source state:** it has no incompatible overlap and holds data the GPU wrote and guest
     memory lacks (`TextureGroup.AnyHandleModified`, new and read-only). That is exactly the
     case of a slow read;
   - **source layout:** single-level 2D, uncompressed colour, scale 1, the rectangle on whole
     texels inside the stride;
   - **destination:** the texture of the destination surface (`FindRegionTarget`), same format,
     another group, no incompatible overlap;
   - **format:** UNORM only, since a partial region is blitted and the blit is exact only for
     UNORM. The host must not convert the format, so the target can still be flushed.
   
   Both textures are then synchronised with their memory, the host copies the region
   (`ITexture.CopyTo` with extents, queued after the GPU writes) and the destination is marked
   modified, as the upstream GPU copy of block-linear sources does. Any other case keeps the
   reference guest-memory path.
3. Under the policy, the guest path reads its destination tracked unless the region was
   uploaded. A later partial copy then cannot roll back texels a GPU copy left in the
   texture.
4. Every slow source read that remains is attributed to the textures over the source:
   - **counted by kind:** none, linear holding the source, other linear, block-linear;
   - **logged once per signature:** format, target, size, layers, levels, layout, stride or
     GOB height, byte size, offset, destination found, read time. At most 8 signatures.
   
   The GPU copies and their declines (no texture, layout, no target, format, not modified)
   are added to the summary line.
5. The performance journal now lists every presentation gap per second (`gaps=`) and counts
   gaps over 50 and 100 ms (`long=`), for p50/p95/p99 frame times and pauses.

Correctness checks:
- **Host fixture:** 57 checks locally, 58 in the producer. It covers the copy region on
  doubles, the synchronisation order, every decline copying nothing, the tracked
  destination read and the attribution.
- **Route gates:** the five gates of the DMA route ran on the final source, and the GPU
  assembly compiled locally.
- **Reviews:** two independent reviews. The second one found the stale-source, format,
  inexact-blit and rollback cases, all addressed above. Only `noTarget` declines remain
  legitimate.
- **Not covered:** no device or byte-level host test of the Vulkan blit. Images are checked
  on the iPhone.

## What the next run reads

- **Presence of the new path:** `DMA GPU source copy (Hogwarts policy): …` appears once.
- **What remains of the flush:** in `DMA guest-memory copies:`, `gpuSourceCopies` against
  `declined noTexture/layout/noTarget/format/notModified`, and `slowReads by source …`.
  `DMA slow source read #n: …` lines name each remaining case.
- **If the path does not engage:** those lines name the texture. A block-linear source would
  call for a different copy; a destination missing from the cache (`noTarget`) calls for a
  wider destination lookup, for example to mip levels.
- **Per-frame windows:** `texFlushAction` and `syncInvoke` per window.
- **Frame times:** `tools/melonx/frame_report.py`, which computes them from the `gaps=` lists.

## Other leads in these logs

- **ServiceNv Wait / pipeline miss:** at 19:36:18 two `ServiceNv Wait: GPU processing thread is
  too slow` frame a `Background pipeline compile missed on draw`. That window has 94 pipeline
  builds (408 ms) and 257 ms of queue back-pressure: a scene change with new pipelines, not
  the steady state. In the minute of play pipeline builds are 0–3 per window, with one window
  of 102 builds (425 ms) and one of 24 (91 ms). They cause hitches; the flush costs every frame.
- **Not attributed to FPS:** the EBADF warnings and the 4 GiB mapping.
- **Next limit expected after the flush:** the render thread, at 55–70 % CPU and 96 % busy,
  part of which is the flush's fence wait. Then the buffer read-backs, at 1.4–1.8 s per
  window.
