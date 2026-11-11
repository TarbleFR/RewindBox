# MeloNX lot 9 — device protocol (IPA with Core 727)

Core 727 is Core 725 plus two adapters; everything in the [Core 725 protocol](../melonx-725-gates/device-protocol.md)
applies unchanged (inputs to check, route, export with `MeloNX-core.log.1`, verdict, pipeline variants, memory). This
page lists only what Core 727 adds. Nothing here was run on an iPhone.

## Pause (what `adapt_pause_checkpoint_growth` changes)
IPA 724 for reference: paused at t=192-196 s; "pipelineCache written: main 793,10 MiB in 10909 ms" for "+1,06 MiB since
the file was written 191 s ago"; 0-0.3 FPS from t=197 to 205 (gaps of 6 461 and 3 880 ms).
1. After five minutes of play, pause for 30 s, resume, note the second of the resume.
2. `MeloNX-core.log`: `pipelineCache checkpointSkipped` at the pause when the cache grew by less than 8 MiB since its
   file (expected in a warm session), or `pipelineCache checkpoint` + `written` when it grew by 8 MiB or more.
3. `MeloNX-performance.log`: the ten seconds after the resume. Expected with a skipped write: no window at 0-0.3 FPS
   after the resume. A write of 8 MiB or more still costs its whole duration (about 11 s for 793 MiB): report it with
   its growth; that case is the remaining defect (the file is rewritten whole), not a regression.
Would refute: a `checkpointSkipped` pause followed by the same seconds at 0-0.3 FPS — the freeze has another cause.

## Vulkan device memory (what `adapt_vulkan_memory_journal` adds; diagnostic only)
`MeloNX-core.log`, `vulkanMemory sample` lines (the first at the first render window, then about every 30 s, at most
60): "Vulkan device memory: N blocks X MiB (dedicated D MiB, mapped M MiB, pooled free F MiB) in L lists; type T
buffers|images: ..." (the four largest lists). Read with the `memoryInventory` samples of the same seconds (texture
cache, buffer cache) and MoltenVK's "GPU memory allocated" in `MeloNX-stderr.log`. IPA 724 for reference: MoltenVK
1 269 MB allocated, texture cache 157 MiB, buffer cache 133 MiB.
- `pooled free` large against the total: the allocator keeps blocks mostly empty (a release rule is the lever).
- `mapped` large: host-visible memory (buffers the CPU writes), counted in the app's footprint.
- `dedicated` large on `images`: big textures or render targets outside the pools (the texture cache's own ledger says
  which).
- total near the caches' sum: the allocator is not where the missing GiB is.
