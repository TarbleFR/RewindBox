# Hogwarts Legacy outdoors on the iPhone: what the IPA 759 journals say, ranked — 16 November 2026

Maintainer request: the game stays very unstable outdoors and the frame rate still swings widely; use the journals
and measurements already available to find the causes and fix them; rank them by impact; for each change give the
problem, the cause, the fix and the checks; keep what is measured apart from what waits for the device.

Source: one Hogwarts Legacy session of IPA 759 (Core `127b72b9`, iPhone 16 Pro Max, 8 GB), 3 min 30 s, of which
about 70 s in the open world, and two Super Smash Bros. Ultimate sessions as a control (60 FPS, steady). The journals
are private; everything below is counts and times. Tools: `tools/melonx/hot_spots.py` with the Core's symbol map, the
`[MeloNX:freeze]` records decoded with the same map, the per-second lines, the 5 s render and collector records.

## 1. The session, second by second

| Phase | Seconds | Frame rate | Footprint | Device memory free | Pages decompressed per second | Threads ready but waiting for a core |
| --- | --- | --- | --- | --- | --- | --- |
| Menu and loading | 56-76 | 30 (two loading gaps) | 3.6-3.8 GiB | 8-11 % | 0-1 200, 11 400 in a loading gap | 7-37 % |
| Entering the world | 77-79 | one gap of 1.48 s | 3.76 → 4.53 GiB in one second | 5-8 % | 19 600-23 900 | 62-151 % |
| First 20 s in the world | 80-99 | 29.6 on average | 4.28-4.51 GiB | 5-10 % | 800-17 900, median 4 900 | 37-172 % |
| Moving through the world | 100-139 | 19.5 on average (3.9 to 28.8) | 4.49-4.82 GiB | 4-6 % | mostly 5 000-22 000, peaks 43 800 and 70 100 | 48-304 % |

The session ends because the player leaves (pause at 09:35:51, then the next game); no crash and no kill by iOS is
recorded. iOS sent two memory warnings, at the world entry and at second 122.

Not a cause here, by the journals: pipeline compilation (no pipeline compiled on the render thread in the session,
1 304 variants ready before their first draw, 131 late creations for 409 ms in all), the iPhone's GPU (busy 13 to
17 ms per frame, 34 % of the time), heat (thermal state nominal until second 104, then "fair").

## 2. Causes, ranked

### 2.1 The open world costs the engine twice the processor time per frame (largest)

Render thread, two 5 s windows of the same session:

| | Light scene (09:34:52-57) | Outdoors (09:35:22-27) |
| --- | --- | --- |
| Frames in the window | 132 | 100 |
| Draws per frame | 697 | 1 303 (up to 1 950 in later windows) |
| Render thread busy, per frame | 11.0 ms | 33.3 ms |
| of which descriptor updates for draws | 3.8 ms | 10.7 ms |
| compute dispatches (54 per frame) | 2.4 ms | 3.9 ms |
| host syncs and submits | 1.7 ms | 3.1 ms |
| buffer updates (`BufferSetData`) | 0.5 ms | 2.5 ms |
| Command buffers submitted per frame | 5.6 | 9.9 |
| Time per draw in draw preparation | 6.4 µs | 9.7 µs (11 to 13 later, 30 to 44 in the worst windows) |

Per-thread processor share (per-second lines): the render thread goes from 12.9 to 29.9 ms of processor per frame,
the GPU thread from 8.5 to 20.8 ms, the game's own main thread from 13.3 to 17.8 ms. With 33 ms of render-thread
work per frame the engine cannot hold 30 FPS even with a whole fast core, and it does not get one: the six threads
that matter want about three cores between two fast and four slow ones, and the kernel's compressor takes its part.

So two things multiply: twice the draws, and each draw costs up to twice as long because the thread is interrupted
(waiting for a core, page faults on compressed memory).

### 2.2 Memory: the phone works out of its compressor

At second 90 the process has 1.0 GiB of its own memory resident and 5.0 GiB in the compressor (guest memory
included), plus 0.9 GiB of graphics memory, which cannot be compressed. The 1 GiB code arena is in the footprint from
launch (one byte written per page by the JIT helper) but costs almost nothing once compressed; the footprint
overstates the pressure, the decompression rate does not: 5 000 to 22 000 pages per second while moving outdoors
(80 to 350 MiB per second).

What the engine itself holds at that point: graphics 0.9-1.0 GiB (textures 413-451 MiB, buffers 164-268 MiB and
growing, the rest Metal's own), native heap 0.84 GiB (MoltenVK's SPIR-V copies 205 MiB, Metal libraries 129 MiB,
descriptor pools 103 MiB, the JIT's address table 50 MiB), managed heap 0.78-0.83 GiB committed (large object heap
450-460 MiB of which 145-156 MiB free; a compaction during a pause gives 237 to 274 MiB of footprint back, and the
heap is fragmented again 30 s later).

### 2.3 Garbage collections: a stop every 2 to 3 s, and a storm every 15 s

- Ephemeral collections in the world: 21 in 53 s, 22 to 341 ms each (gen1: 40 to 114 ms, 13 to 48 MiB promoted). The
  341 ms one is the world entry; it ran on the render thread inside the 1.48 s gap, with 35 696 pages decompressed.
- Background gen2 collections: one every 15.3 s (the keep-alive's cadence; the runtime's own would be 14 to 22 s
  apart in streaming, measured in IPA 739-740). Each marks the whole 600-760 MiB heap. The worst seconds of the
  session sit on them: 09:34:55 (gap of 400 ms), 09:35:11 (17 then 13 FPS), 09:35:26 (gap of 650 ms, 3.9 FPS,
  43 797 pages decompressed in the second, second memory warning), 09:35:51 (116 869 pages).
- Who allocates is known for about 30 % (GPU-thread scopes and the render thread's drain); the rest comes from threads
  that are not instrumented.

### 2.4 The runtime's locks yield with a priority drop (fixed in Core `9943a5ca`)

97 of 640 and 109 of 753 running samples of the six busiest threads in the two slow profiles; see
[the note of the same day](melonx-ryujinx-update-2026-11-16.md). Compiled and pinned; not yet on a device.

### 2.5 Frame gaps by what ran inside them (15 gaps of 100 ms or more in play, 11 with samples)

| Gaps | What ran | Cause |
| --- | --- | --- |
| 2 (250, 200 ms, during loading) | The game's main thread, 227-269 ms of processor in translated code, with samples in the JIT translator | The game's own work and first translation of new code |
| 1 (100 ms, loading) | Game loading threads and the file system server | Loading |
| 1 (1 484 ms, world entry) | Render thread 578 ms (282 in the kernel) inside a gen0 collection, background collector 344 ms, 2.7 GiB compressed | Collection during the memory jump |
| 1 (104 ms) | Background collector 64 ms with the render thread 67 ms | Background collection |
| 6 (100 to 650 ms, outdoors) | Render thread 25-276 ms and GPU thread 36-421 ms of processor, a tenth to a half of it in the kernel, 1 000 to 13 600 pages decompressed | Engine work slowed by page faults |

## 3. Rendering quality

Nothing in these journals reports a rendering fault in the session (no engine error, no descriptor fallback, no
dummy texture substituted, no draw skipped, no pipeline unavailable). There is no screen capture with the journals,
so what the picture looked like is not known from them. A report of a visual defect needs a capture or a
description of the place and the moment.
